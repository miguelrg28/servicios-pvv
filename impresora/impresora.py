"""
Servicio de impresión (servicios-pvv).

Corre en una computadora Windows de la empresa —el servidor o la caja— y saca por sus impresoras
lo que le manda el panel, sin abrir ventanas. Es general: lo puede instalar cualquier empresa del
panel; no sabe nada de ninguna en concreto.

Dos formas de recibir trabajo, y la segunda es la que hay que usar en una caja
--------------------------------------------------------------------------
1. **El panel llama aquí** (modo de siempre). Levanta un servidor con dos puertas:
     · POST /imprimir        → un PDF (la hoja del cuadre, una factura en carta…), con SumatraPDF.
     · POST /imprimir-crudo  → bytes en el idioma de una impresora de recibos (Star Line Mode,
                               ESC/POS): tickets de factura, con corte y gaveta. RAW por win32print.
   Y dos de consulta: GET /salud y GET /impresoras.
   Exige que el panel pueda ALCANZAR esta máquina: o sea, ZeroTier.

2. **Esto llama al panel** (`PANEL_URL` en el `.env`). Sale una petición por HTTPS a la misma
   dirección que se abre en el navegador y se queda esperando; cuando hay papel, el panel contesta
   con el trabajo, aquí se imprime y se le dice qué pasó.

   Por qué existe: una caja no tiene por qué estar en la red privada de la empresa. Meterla ahí
   para imprimir un ticket le da de paso alcance al ERP y a la base de datos, y una caja es el
   equipo más expuesto de una tienda. Saliendo no hace falta abrir ningún puerto ni entrar en
   ninguna red: no hay nada que vigilar.

Las dos pueden convivir, y de hecho comparten todo lo de abajo: cambia de dónde llega el trabajo,
no cómo se imprime.

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
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.3.1"
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

# ── Modo «esto llama al panel» ──
# La dirección del panel de la empresa, la misma que se abre en el navegador. Vacío = modo de
# siempre (el panel llama aquí) y no se sale a ninguna parte.
PANEL_URL = _limpiar(os.environ.get("PANEL_URL")).rstrip("/")
# Qué computadora es, según el panel: sale en Ajustes → Servicios de impresión.
SERVICIO_ID = _limpiar(os.environ.get("SERVICIO_ID"))

# El panel deja la espera abierta unos 25 s; el margen es para que el corte lo dé él y no nosotros.
TIMEOUT_ESPERA = 40
TIMEOUT_REPORTE = 20
# Al fallar la red se espera cada vez un poco más, hasta un minuto: una caja sin internet no puede
# convertirse en mil peticiones por minuto contra el panel.
ESPERA_MIN, ESPERA_MAX = 2, 60
# Las impresoras no cambian cada 25 s. Se recuerdan unos minutos para no preguntarle a Windows en
# cada vuelta.
CACHE_IMPRESORAS = 300


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
        # Que la impresora exista con ESE nombre exacto. Si no, Sumatra solo devuelve 1 y no dice
        # por qué; aquí se dice cuál falta y cuáles hay, que es lo que hace falta para corregirlo.
        if impresora:
            hay = [p["nombre"] for p in listar_impresoras()]
            if hay and impresora not in hay:
                parecida = next((n for n in hay if n.lower() == impresora.lower()), None)
                if parecida:
                    impresora = parecida
                else:
                    return False, (
                        f"No hay ninguna impresora llamada «{impresora}» en este equipo. "
                        f"Las que hay: {', '.join(hay)[:300]}. Elige una en Ajustes con «Ver sus impresoras»."
                    )
        destino = ["-print-to", impresora] if impresora else ["-print-to-default"]
        for _ in range(copias):
            r = subprocess.run(
                [SUMATRA, *destino, "-silent", "-exit-when-done", str(ruta)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                # Sumatra escribe su registro de cómo leyó la orden («ParseFlags: …»): no es el error
                # y tapaba el mensaje de verdad. Se quita para que se vea lo que importa.
                detalle = " ".join(
                    l.strip() for l in (r.stderr or r.stdout or "").splitlines()
                    if l.strip() and not l.strip().startswith("ParseFlags")
                )
                return False, (
                    f"SumatraPDF no pudo imprimir en «{impresora or 'la de por defecto'}» (código {r.returncode}). "
                    + (detalle[:200] if detalle else
                       "Suele ser que el controlador de esa impresora no está bien instalado o no acepta el tamaño del papel.")
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


# ──────────────────── Modo «esto llama al panel» (la cola) ────────────────────
#
# El panel no puede llamar a una caja, y es justo lo que se quiere: una caja no tiene por qué estar
# en la red privada de la empresa. Así que se invierte el sentido. Esto es todo el mecanismo:
#
#   1. POST {PANEL_URL}/api/cola-impresion/esperar   → se queda abierta hasta ~25 s.
#        · 204          = no hay nada; se vuelve a preguntar.
#        · 200 {trabajo}= hay papel.
#   2. Se imprime con las mismas funciones de arriba.
#   3. POST {PANEL_URL}/api/cola-impresion/<id>/hecho → qué pasó. Al otro lado hay alguien
#      esperando para decirle a una persona «salió» o «no salió, y por esto».
#
# La clave es la misma de siempre (IMPRESORA_TOKEN), y la empresa la dice el subdominio de
# PANEL_URL. No hay una segunda credencial que mantener.

_impresoras_cache = {"cuando": 0.0, "lista": []}


def _impresoras_para_el_panel():
    """
    Las impresoras de este equipo, recordadas unos minutos.

    Van en CADA espera porque en este modo el panel no puede preguntarlas: al revés no se puede
    llamar, que es el punto de todo esto. Con ellas, la pantalla de Ajustes sigue pudiendo ofrecer
    la lista para elegir cuál usar.
    """
    ahora = time.time()
    if ahora - _impresoras_cache["cuando"] > CACHE_IMPRESORAS:
        _impresoras_cache["lista"] = listar_impresoras()
        _impresoras_cache["cuando"] = ahora
    return _impresoras_cache["lista"]


def _al_panel(ruta, cuerpo, timeout, metodo="POST"):
    """Una llamada al panel. Devuelve el JSON, o None si contestó 204 (nada que hacer)."""
    datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(
        f"{PANEL_URL}{ruta}",
        data=datos,
        method=metodo,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
            # Sin esto, un proxy por medio puede quedarse con la respuesta vacía del 204.
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(peticion, timeout=timeout) as r:
        if r.status == 204:
            return None
        crudo = r.read().decode("utf-8") or "{}"
        return json.loads(crudo)


def _imprimir_trabajo(trabajo):
    """Saca el papel. Devuelve (salió, explicación) igual que las funciones de arriba."""
    try:
        # Los espacios y saltos se quitan antes de validar: hay codificadores que parten la cadena
        # en renglones, y eso no es un documento mal codificado, es el mismo documento con pinta
        # distinta. Rechazarlo costaría una visita al taller por nada.
        limpio = "".join((trabajo.get("datos_base64") or "").split())
        datos = base64.b64decode(limpio, validate=True)
    except Exception:
        return False, "El documento no venía bien codificado."
    if not datos:
        return False, "El trabajo venía vacío."

    nombre = str(trabajo.get("nombre") or "documento")
    impresora = str(trabajo.get("impresora") or "").strip()
    copias = trabajo.get("copias") or 1

    if trabajo.get("tipo") == "crudo":
        return imprimir_crudo(datos, impresora, copias, nombre)

    if not datos.startswith(b"%PDF"):
        return False, "Eso no es un PDF."
    # A un temporal y se borra siempre: en la caja no se queda tirado el cuadre de cada día.
    tmp = Path(tempfile.gettempdir()) / f"vl-{int(time.time() * 1000)}.pdf"
    try:
        tmp.write_bytes(datos)
        return imprimir_pdf(tmp, impresora, copias)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


def _una_vuelta():
    """Pregunta, imprime si hay algo, y cuenta qué pasó. Devuelve True si hubo trabajo."""
    respuesta = _al_panel(
        "/api/cola-impresion/esperar",
        {"equipo": EQUIPO, "version": VERSION, "impresoras": _impresoras_para_el_panel()},
        TIMEOUT_ESPERA,
    )
    trabajo = (respuesta or {}).get("trabajo")
    if not trabajo:
        return False

    arranque = time.time()
    try:
        ok, detalle = _imprimir_trabajo(trabajo)
    except Exception as e:
        ok, detalle = False, str(e)[:200]
    ms = int((time.time() - arranque) * 1000)
    print(f"[impresora] {'✔' if ok else '✖'} {trabajo.get('nombre')} (cola) → {detalle} ({ms} ms)")

    # Que el papel saliera y no se pueda avisar es el único fallo de verdad feo de todo esto: al
    # otro lado hay alguien mirando la pantalla. Por eso el aviso va en su propio try, y si no
    # llega se dice con todas las letras.
    try:
        _al_panel(
            f"/api/cola-impresion/{trabajo.get('id')}/hecho",
            {"ok": bool(ok), "detalle": str(detalle)[:300], "impresora": detalle if ok else "", "ms": ms},
            TIMEOUT_REPORTE,
        )
    except Exception as e:
        print(f"[impresora] El papel salió pero no se pudo avisar al panel: {e}", file=sys.stderr)
    return True


def _saludar_al_panel():
    """
    Una llamada al arrancar para que el log diga de una vez si esto está bien puesto.

    Sin ella, un `.env` con la dirección equivocada se ve como «no sale el papel» días después. Y
    de paso avisa si el SERVICIO_ID no es el de la clave: quien manda es la clave, así que esto
    seguiría funcionando igual, pero un `.env` armado a medias entre dos computadoras es justo lo
    que acaba en «¿por qué imprime en la caja 2?».
    """
    try:
        d = _al_panel("/api/cola-impresion/", None, 20, metodo="GET") or {}
    except urllib.error.HTTPError as e:
        cuerpo = ""
        try:
            cuerpo = json.loads(e.read().decode("utf-8")).get("mensaje", "")
        except Exception:
            pass
        print(f"[impresora] El panel contestó {e.code} al saludar: {cuerpo or 'sin detalle'}", file=sys.stderr)
        return
    except Exception as e:
        print(f"[impresora] No se pudo saludar al panel: {str(e)[:160]}", file=sys.stderr)
        return

    servicio = d.get("servicio") or {}
    print(f"[impresora] Conectado al panel de «{d.get('empresa')}» como «{servicio.get('nombre')}».")
    if SERVICIO_ID and servicio.get("id") and SERVICIO_ID != servicio.get("id"):
        print(
            f"[impresora] AVISO: el SERVICIO_ID del .env ({SERVICIO_ID}) no es el de esta clave "
            f"({servicio.get('id')}). Manda la clave, así que se imprimirá igual, pero revisa el .env.",
            file=sys.stderr,
        )


def trabajar_con_el_panel():
    """
    El bucle. Vive en su propio hilo para que el servidor de arriba siga atendiendo si alguien lo
    usa, y porque así una caída de internet no se lleva por delante nada más.
    """
    espera = ESPERA_MIN
    _saludar_al_panel()
    print(f"[impresora] Esperando trabajo de {PANEL_URL} como «{SERVICIO_ID}»...")
    while True:
        try:
            # Una vuelta con trabajo encadena con la siguiente sin pausa: si hay tres tickets en
            # cola, salen los tres seguidos y no uno cada 25 segundos.
            _una_vuelta()
            espera = ESPERA_MIN
        except urllib.error.HTTPError as e:
            cuerpo = ""
            try:
                cuerpo = json.loads(e.read().decode("utf-8")).get("mensaje", "")
            except Exception:
                pass
            if e.code in (401, 403):
                # Reintentar más rápido no va a cambiar la clave. Se dice claro y se baja el ritmo.
                print(
                    f"[impresora] El panel rechazó la credencial ({e.code}): {cuerpo or 'sin detalle'}\n"
                    f"            Revisa IMPRESORA_TOKEN y SERVICIO_ID contra Ajustes → Servicios de impresión.",
                    file=sys.stderr,
                )
                espera = ESPERA_MAX
            else:
                print(f"[impresora] El panel contestó {e.code}: {cuerpo or 'sin detalle'}", file=sys.stderr)
                espera = min(ESPERA_MAX, espera * 2)
            time.sleep(espera)
        except Exception as e:
            # Sin internet, el panel reiniciándose, un corte de la espera... nada de esto merece un
            # rastro de pila de veinte líneas cada dos segundos en el impresora.log.
            print(f"[impresora] Sin conexión con el panel ({type(e).__name__}): {str(e)[:120]}", file=sys.stderr)
            time.sleep(espera)
            espera = min(ESPERA_MAX, espera * 2)


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
    #
    # Con PANEL_URL puesto, el valor por defecto pasa a ser 127.0.0.1 y no 0.0.0.0. Una caja que
    # sale a buscar su trabajo no tiene por qué dejar un puerto abierto a la red de la tienda, y
    # el que instala no tiene por qué acordarse de cerrarlo: lo seguro tiene que ser lo que pasa
    # cuando nadie toca nada.
    escuchar_env = _limpiar(os.environ.get("IMPRESORA_ESCUCHAR"))
    ap = argparse.ArgumentParser(description="Servicio de impresión (servicios-pvv).")
    ap.add_argument("--escuchar", default=escuchar_env or ("127.0.0.1" if PANEL_URL else "0.0.0.0"))
    ap.add_argument("--puerto", type=int, default=int(_limpiar(os.environ.get("IMPRESORA_PUERTO")) or 8766))
    ap.add_argument(
        "--sin-servidor", action="store_true",
        default=_limpiar(os.environ.get("IMPRESORA_SERVIDOR")) in ("0", "no", "false"),
        help="No levantar el servidor: solo salir a buscar trabajo al panel (hace falta PANEL_URL).",
    )
    args = ap.parse_args()

    if len(TOKEN) < 20:
        print("AVISO: IMPRESORA_TOKEN no está puesto (o es corto). El servicio responderá 503.")
    print(f"Equipo: {EQUIPO} · impresoras: {[i['nombre'] for i in listar_impresoras()] or 'ninguna'}")

    sale = bool(PANEL_URL)
    if PANEL_URL and not SERVICIO_ID:
        print(
            "AVISO: hay PANEL_URL pero falta SERVICIO_ID, así que NO se va a buscar trabajo al panel.\n"
            "       El id de esta computadora sale en el panel, en Ajustes → Servicios de impresión.",
            file=sys.stderr,
        )
        sale = False

    if args.sin_servidor:
        if not sale:
            print("No hay nada que hacer: --sin-servidor sin PANEL_URL (y SERVICIO_ID) válidos.", file=sys.stderr)
            sys.exit(1)
        try:
            trabajar_con_el_panel()
        except KeyboardInterrupt:
            print("\nHasta luego.")
        return

    if sale:
        # Demonio: si el bucle se queda colgado en una espera, cerrar el programa no tiene que
        # depender de que esa espera termine.
        threading.Thread(target=trabajar_con_el_panel, name="cola", daemon=True).start()

    http = ThreadingHTTPServer((args.escuchar, args.puerto), _manejador())
    http.daemon_threads = True
    print(f"Esperando peticiones en http://{args.escuchar}:{args.puerto} (Ctrl+C para salir)...")
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego.")


if __name__ == "__main__":
    main()
