"""
Servicio de impresión (servicios-pvv).

Corre en una computadora Windows de la empresa —el servidor o la caja— y saca por sus impresoras
lo que le manda el panel, sin abrir ventanas. Es general: lo puede instalar cualquier empresa del
panel; no sabe nada de ninguna en concreto.

Dos puertas:
  · POST /imprimir        → un PDF (la hoja del cuadre, una factura en carta…), con SumatraPDF.
  · POST /imprimir-crudo  → bytes en el idioma de una impresora de recibos (Star Line Mode,
                            ESC/POS): tickets de factura, con corte y gaveta. RAW por win32print.
Y dos de consulta: GET /salud y GET /impresoras.

Por qué el horario NO está aquí
-------------------------------
Este programa no sabe qué día es ni qué hay que imprimir: solo recibe y manda a la impresora. El
calendario vive en el panel, donde se puede ver y cambiar desde una pantalla. Un horario escondido
en el Programador de tareas de una máquina es un horario que nadie vuelve a mirar.

Instalación (Windows): ver INSTALACION.md. En corto:
    cd C:\\servicios-pvv\\impresora
    py -m venv venv
    venv\\Scripts\\python -m pip install -r requirements.txt
    copy .env.ejemplo .env     (y poner IMPRESORA_TOKEN)
    venv\\Scripts\\python impresora.py

Se prueba desde la propia máquina:
    curl -H "Authorization: Bearer EL_TOKEN" http://127.0.0.1:8766/impresoras
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.2"
AQUI = Path(__file__).resolve().parent

# Un PDF de una hoja pesa 100 kB. El tope está por si alguien manda un documento de doscientas
# páginas sin querer: mejor un rechazo claro que llenar la memoria del equipo.
MAX_PDF_BYTES = 12 * 1024 * 1024
# Un ticket en comandos de la impresora pesa 2 o 3 kB. 256 kB sobra incluso con un logo.
MAX_CRUDO_BYTES = 256 * 1024


def _limpiar(valor):
    """Quita comillas y espacios de un valor de `.env`."""
    if valor is None:
        return ""
    return str(valor).strip().strip('"').strip("'")


def _cargar_env(ruta=AQUI / ".env"):
    """Lee el `.env` de al lado SIN pisar lo que ya venga del entorno."""
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave = clave.strip()
            if clave and clave not in os.environ:
                os.environ[clave] = _limpiar(valor)
    except FileNotFoundError:
        pass


_cargar_env()

TOKEN = _limpiar(os.environ.get("IMPRESORA_TOKEN"))
SUMATRA = _limpiar(os.environ.get("SUMATRA_EXE")) or str(AQUI / "SumatraPDF.exe")
EQUIPO = platform.node() or "servidor"


# ──────────────────────────── Las impresoras del equipo ────────────────────────────

def listar_impresoras():
    """
    Las impresoras que ve este equipo, con cuál es la de por defecto.

    En Windows se pregunta con `win32print`. Fuera de Windows se usa `lpstat`, que sirve para
    probar el servicio en un Mac o un Linux sin tener que montar la máquina Windows.
    """
    if os.name == "nt":
        try:
            import win32print  # type: ignore

            pordefecto = ""
            try:
                pordefecto = win32print.GetDefaultPrinter()
            except Exception:
                pass
            nivel = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            salida = []
            for p in win32print.EnumPrinters(nivel, None, 1):
                nombre = p[2]
                salida.append({"nombre": nombre, "pordefecto": nombre == pordefecto})
            return salida
        except ImportError:
            # Sin pywin32 no se puede listar, pero sí imprimir con Sumatra a la de por defecto.
            return []
        except Exception as e:
            print(f"[impresora] No se pudieron listar: {e}", file=sys.stderr)
            return []

    try:
        crudo = subprocess.run(["lpstat", "-p", "-d"], capture_output=True, text=True, timeout=8)
        nombres, pordefecto = [], ""
        for linea in (crudo.stdout or "").splitlines():
            if linea.startswith("printer "):
                nombres.append(linea.split()[1])
            elif "destination:" in linea:
                pordefecto = linea.split(":")[-1].strip()
        return [{"nombre": n, "pordefecto": n == pordefecto} for n in nombres]
    except Exception:
        return []


def imprimir_pdf(ruta: Path, impresora: str, copias: int) -> tuple[bool, str]:
    """
    Manda el PDF a la impresora y devuelve (salió, explicación).

    En Windows se usa **SumatraPDF**: es la forma fiable de imprimir un PDF sin abrir ventanas ni
    depender de qué lector esté instalado. `ShellExecute(..., "printto", ...)` parece más simple
    pero abre Acrobat, y en un servidor sin sesión interactiva se queda colgado esperando a que
    alguien cierre un diálogo que nadie ve.

    Las copias se mandan de una en una a propósito: el parámetro de copias de Sumatra depende del
    controlador, y una hoja repetida dos veces es algo que el papel enseña enseguida.
    """
    copias = max(1, min(10, int(copias or 1)))

    if os.name == "nt":
        if not Path(SUMATRA).exists():
            return False, (
                f"No encuentro SumatraPDF en «{SUMATRA}». Déjalo en la carpeta del servicio o "
                "pon su ruta en SUMATRA_EXE."
            )
        destino = ["-print-to", impresora] if impresora else ["-print-to-default"]
        for _ in range(copias):
            r = subprocess.run(
                [SUMATRA, *destino, "-silent", "-exit-when-done", str(ruta)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                return False, (
                    f"SumatraPDF devolvió {r.returncode}. "
                    f"{(r.stderr or r.stdout or '').strip()[:160]}"
                )
        return True, impresora or "(la de por defecto)"

    # Mac y Linux: para poder probar el servicio fuera de Windows.
    cmd = ["lp", "-n", str(copias)]
    if impresora:
        cmd += ["-d", impresora]
    cmd.append(str(ruta))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "lp falló").strip()[:160]
    return True, impresora or "(la de por defecto)"


def imprimir_crudo(datos: bytes, impresora: str, copias: int, nombre: str) -> tuple[bool, str]:
    """
    Manda BYTES tal cual a la impresora, sin pasar por el dibujo del controlador.

    Es lo que piden las impresoras de recibos (Star SP500, Epson TM, Bixolon…): el panel ya arma el
    ticket en el idioma de la impresora —Star Line Mode o ESC/POS— con negritas, corte de papel y
    apertura de la gaveta, y aquí solo hay que entregárselo al spooler como «RAW». En una
    matricial como la SP500 la diferencia se nota: un PDF lo imprime como dibujo, línea a línea y
    despacio; en crudo usa su propia letra y sale en un par de segundos.

    En Windows se usa `win32print` con el tipo de datos RAW. Fuera de Windows, `lp -o raw`.
    """
    copias = max(1, min(10, int(copias or 1)))

    if os.name == "nt":
        try:
            import win32print  # type: ignore
        except ImportError:
            return False, "Falta pywin32 en este equipo (pip install pywin32)."
        destino = impresora
        if not destino:
            try:
                destino = win32print.GetDefaultPrinter()
            except Exception:
                return False, "No hay impresora por defecto y no se dijo cuál usar."
        try:
            h = win32print.OpenPrinter(destino)
        except Exception as e:
            return False, f"No se pudo abrir «{destino}»: {str(e)[:160]}"
        try:
            for _ in range(copias):
                win32print.StartDocPrinter(h, 1, (nombre[:60] or "ticket", None, "RAW"))
                try:
                    win32print.StartPagePrinter(h)
                    win32print.WritePrinter(h, datos)
                    win32print.EndPagePrinter(h)
                finally:
                    win32print.EndDocPrinter(h)
        except Exception as e:
            return False, f"El spooler rechazó el trabajo: {str(e)[:160]}"
        finally:
            win32print.ClosePrinter(h)
        return True, destino

    tmp = Path(tempfile.gettempdir()) / f"vl-{int(time.time() * 1000)}.bin"
    try:
        tmp.write_bytes(datos)
        cmd = ["lp", "-o", "raw", "-n", str(copias)]
        if impresora:
            cmd += ["-d", impresora]
        cmd.append(str(tmp))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "lp falló").strip()[:160]
        return True, impresora or "(la de por defecto)"
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


# ──────────────────────────────── El servidor ────────────────────────────────

def _manejador():
    class Manejador(BaseHTTPRequestHandler):
        server_version = f"ServicioImpresionPVV/{VERSION}"

        def log_message(self, formato, *a):  # noqa: N802  (lo impone BaseHTTPRequestHandler)
            print(f"[impresora] {self.address_string()} {formato % a}")

        def _json(self, codigo, cuerpo):
            datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def _autorizado(self):
            # Sin token configurado la puerta queda CERRADA, no abierta. Una variable que se olvida
            # no puede dejar la impresora abierta a la red.
            if len(TOKEN) < 20:
                self._json(503, {"mensaje": "IMPRESORA_TOKEN sin definir o con menos de 20 caracteres."})
                return False
            cabecera = self.headers.get("Authorization", "")
            if cabecera != f"Bearer {TOKEN}":
                self._json(401, {"mensaje": "Credencial incorrecta."})
                return False
            return True

        def _cuerpo(self):
            largo = int(self.headers.get("Content-Length") or 0)
            if largo <= 0:
                return {}
            if largo > MAX_PDF_BYTES * 2:  # base64 crece un tercio; el doble es margen de sobra
                self._json(413, {"mensaje": "El documento es demasiado grande."})
                return None
            return json.loads(self.rfile.read(largo).decode("utf-8"))

        def do_GET(self):  # noqa: N802
            if not self._autorizado():
                return
            ruta = self.path.split("?")[0].rstrip("/") or "/"
            if ruta in ("/", "/salud"):
                self._json(200, {"ok": True, "equipo": EQUIPO, "version": VERSION})
            elif ruta == "/impresoras":
                self._json(200, {"equipo": EQUIPO, "impresoras": listar_impresoras()})
            else:
                self._json(404, {"mensaje": f"No existe {ruta}."})

        def do_POST(self):  # noqa: N802
            if not self._autorizado():
                return
            ruta = self.path.split("?")[0].rstrip("/") or "/"
            if ruta not in ("/imprimir", "/imprimir-crudo"):
                self._json(404, {"mensaje": f"No existe {ruta}."})
                return
            try:
                cuerpo = self._cuerpo()
            except Exception as e:
                self._json(400, {"mensaje": f"El cuerpo no es JSON: {e}"})
                return
            if cuerpo is None:
                return
            if ruta == "/imprimir-crudo":
                self._imprimir_crudo(cuerpo)
                return

            b64 = cuerpo.get("pdf_base64") or ""
            if not b64:
                self._json(400, {"mensaje": "Falta el PDF."})
                return
            try:
                pdf = base64.b64decode(b64, validate=True)
            except Exception:
                self._json(400, {"mensaje": "El PDF no venía bien codificado."})
                return
            if len(pdf) > MAX_PDF_BYTES:
                self._json(413, {"mensaje": "El PDF pasa del tamaño máximo."})
                return
            # Un PDF empieza por «%PDF». Comprobarlo evita mandarle basura al spooler, que en
            # Windows se queda con el trabajo encallado y hay que ir a limpiarlo a mano.
            if not pdf.startswith(b"%PDF"):
                self._json(400, {"mensaje": "Eso no es un PDF."})
                return

            nombre = str(cuerpo.get("nombre") or "documento.pdf")
            impresora = str(cuerpo.get("impresora") or "").strip()
            copias = cuerpo.get("copias") or 1

            arranque = time.time()
            # Se escribe en un temporal y se borra siempre: en el equipo no se queda
            # tirado el cuadre de caja de cada día.
            tmp = Path(tempfile.gettempdir()) / f"vl-{int(arranque * 1000)}.pdf"
            try:
                tmp.write_bytes(pdf)
                ok, detalle = imprimir_pdf(tmp, impresora, copias)
            except Exception as e:
                ok, detalle = False, str(e)[:200]
            finally:
                try:
                    tmp.unlink()
                except Exception:
                    pass

            ms = int((time.time() - arranque) * 1000)
            print(f"[impresora] {'✔' if ok else '✖'} {nombre} → {detalle} ({ms} ms)")
            if ok:
                self._json(200, {"ok": True, "impresora": detalle, "ms": ms})
            else:
                self._json(502, {"mensaje": detalle})

        def _imprimir_crudo(self, cuerpo):
            """Los tickets de las impresoras de recibos: bytes en el idioma de la impresora."""
            try:
                datos = base64.b64decode(cuerpo.get("datos_base64") or "", validate=True)
            except Exception:
                self._json(400, {"mensaje": "Los datos no venían bien codificados."})
                return
            if not datos:
                self._json(400, {"mensaje": "Faltan los datos a imprimir."})
                return
            if len(datos) > MAX_CRUDO_BYTES:
                self._json(413, {"mensaje": "El ticket pasa del tamaño máximo."})
                return
            nombre = str(cuerpo.get("nombre") or "ticket")
            impresora = str(cuerpo.get("impresora") or "").strip()
            arranque = time.time()
            try:
                ok, detalle = imprimir_crudo(datos, impresora, cuerpo.get("copias") or 1, nombre)
            except Exception as e:
                ok, detalle = False, str(e)[:200]
            ms = int((time.time() - arranque) * 1000)
            print(f"[impresora] {'✔' if ok else '✖'} {nombre} (crudo) → {detalle} ({ms} ms)")
            if ok:
                self._json(200, {"ok": True, "impresora": detalle, "ms": ms})
            else:
                self._json(502, {"mensaje": detalle})

    return Manejador


def main():
    # Dónde escuchar sale del `.env`, como en el lector de placas: el .bat que lanza la tarea
    # programada no sabe leer un `.env`, así que si esto no viniera de aquí habría que escribir la
    # IP de ZeroTier dentro del .bat — y entonces cambiar de red obligaría a editar dos archivos.
    ap = argparse.ArgumentParser(description="Servicio de impresión (servicios-pvv).")
    ap.add_argument("--escuchar", default=_limpiar(os.environ.get("IMPRESORA_ESCUCHAR")) or "0.0.0.0")
    ap.add_argument("--puerto", type=int, default=int(_limpiar(os.environ.get("IMPRESORA_PUERTO")) or 8766))
    args = ap.parse_args()

    if len(TOKEN) < 20:
        print("AVISO: IMPRESORA_TOKEN no está puesto (o es corto). El servicio responderá 503.")
    print(f"Equipo: {EQUIPO} · impresoras: {[i['nombre'] for i in listar_impresoras()] or 'ninguna'}")

    http = ThreadingHTTPServer((args.escuchar, args.puerto), _manejador())
    http.daemon_threads = True
    print(f"Esperando peticiones en http://{args.escuchar}:{args.puerto} (Ctrl+C para salir)...")
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego.")


if __name__ == "__main__":
    main()
