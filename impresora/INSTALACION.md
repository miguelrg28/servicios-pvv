# Servicio de impresión — instalación

Programa chiquito que corre en una computadora **Windows** de la empresa (el servidor o la caja) y
saca por sus impresoras lo que le manda el panel, **sin abrir ventanas**: PDF (la hoja del cuadre,
facturas en carta) y tickets de factura en crudo para impresoras de recibos (Star SP500, Epson TM…).

Es independiente: no necesita nada más de este repositorio ni de ningún otro. Una empresa que solo
quiera imprimir instala **solo esta carpeta**.

Hay **dos formas de conectarlo**, y conviene elegir antes de empezar:

| | **A — esta computadora llama al panel** | **B — el panel llama aquí** |
|---|---|---|
| Qué hace | Sale a buscar lo que haya que imprimir | Se queda escuchando en un puerto |
| Necesita | Nada: la salida a internet que ya tiene | Que el panel la alcance → **ZeroTier** |
| Hay que abrir | Nada | El puerto 8766 en el cortafuegos |
| Para qué | **Una caja**, una computadora del mostrador | El servidor del taller, que ya está en esa red |

**En una caja usa la A.** Imprimir un ticket no es motivo para meter la computadora del mostrador
en la red privada donde viven el ERP y la base de datos: si esa máquina se infecta —y es la que
más manos toca—, desde ahí se llega a todo lo demás. Saliendo no hay nada abierto y nada que
vigilar.

La **B** es la de siempre y sigue bien donde la máquina ya está en esa red por otros motivos.

**Qué papel sale y a qué hora NO se configura aquí.** Eso vive en el panel. Este programa no sabe
ni qué día es: solo imprime lo que le llega.

> **¿Hace falta para imprimir tickets en una impresora USB de la caja?** No. Si la impresora está
> conectada a la computadora donde se factura, el panel imprime desde el navegador (Ajustes →
> Impresión de facturas → «Desde el navegador de la caja»). Este servicio es para imprimir **sin
> ventanas** o en una impresora que no está en la caja.

---

## 1. Instalar

Necesita **Python 3.10 o más nuevo** (`py --version`). Cada servicio de este repositorio lleva **su
propio venv**, dentro de su carpeta: así se actualiza o se borra uno sin tocar los demás.

```bat
cd C:\
git clone https://github.com/miguelrg28/servicios-pvv.git
cd servicios-pvv\impresora
py -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
copy .env.ejemplo .env
notepad .env
```

Si se instala en otra carpeta que no sea `C:\servicios-pvv`, cambiar las dos rutas de
`tarea.xml` antes del paso 6. `correr.bat` no tiene rutas fijas.

## 2. SumatraPDF (hace falta)

Es la forma fiable de imprimir un PDF en Windows **sin abrir ventanas**. Un solo ejecutable,
portable, sin instalador:

<https://www.sumatrapdfreader.org/download-free-pdf-viewer>

Se baja la versión **portable 64-bit**, se renombra a `SumatraPDF.exe` y se deja en esta carpeta
(`C:\servicios-pvv\impresora\SumatraPDF.exe`). Si se prefiere en otro sitio, se pone la
ruta en `SUMATRA_EXE` del `.env`.

> **¿Por qué no imprimir con Acrobat o con el "printto" de Windows?** Porque abren el lector
> gráfico, y en un servidor sin nadie delante el trabajo se queda esperando a que alguien cierre un
> diálogo que nadie ve. No falla: se cuelga, que es peor.

## 3. La clave (token): una por computadora

**Cada computadora con el servicio tiene su propia clave.** Se escribe en dos sitios:

| Dónde | Qué |
|---|---|
| `C:\servicios-pvv\impresora\.env` (este equipo) | `IMPRESORA_TOKEN=...` |
| Panel → **Ajustes → Servicios de impresión** (de la empresa dueña de este equipo) | la misma clave, con la dirección de este equipo |

Nada de esto va en el `.env` del panel: el panel es de varias empresas, y cada una apunta allí
**solo sus** computadoras. Una clave abre una sola computadora, y la de una empresa no sirve para
imprimir en la de otra.

Generar una clave **nueva para cada computadora**:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

- **No** reutilizar ningún otro token (el del reloj, el del lector de placas…): son puertas
  distintas, y si una se filtra las otras siguen cerradas.
- **No** se reutiliza entre computadoras: si una se filtra o se jubila un equipo, se cambia solo esa.
- **No** va en el repositorio (`.env` está en `.gitignore`). En el panel se guarda de solo
  escritura: después de guardarla, la pantalla solo enseña sus 4 últimas letras.
- Si falta o mide menos de 20 caracteres, el servicio responde **503** a todo: una variable
  olvidada cierra la puerta, no la abre.

### Forma A — esta computadora llama al panel

Primero en el panel, entrando con la empresa dueña del equipo: **Ajustes → Servicios de impresión →
«+ Agregar una computadora»**:

- **Nombre:** cómo la conoce la gente («Caja 1»).
- **¿Quién llama a quién?:** *Ella llama al panel*.
- **Clave:** la que se generó arriba.

Al guardar, la pantalla enseña debajo del nombre el **`SERVICIO_ID`** de esa computadora. Con eso,
el `.env` de aquí:

```
IMPRESORA_TOKEN=...
PANEL_URL=https://miempresa.perspectivve.com   ← la misma dirección que se abre en el navegador
SERVICIO_ID=a1b2c3d4e5                         ← el que enseña la pantalla
# SUMATRA_EXE=...                              ← solo si SumatraPDF.exe no está en esta carpeta
```

No hace falta tocar el cortafuegos (sección 4) ni ZeroTier. Con `PANEL_URL` puesto, el servicio
solo escucha en `127.0.0.1`, así que tampoco deja nada abierto a la red de la tienda; si no se
quiere ni eso, `IMPRESORA_SERVIDOR=0` lo apaga del todo.

### Forma B — el panel llama aquí (ZeroTier)

```
IMPRESORA_TOKEN=...
IMPRESORA_ESCUCHAR=10.147.x.x     ← IP de ZeroTier de ESTE equipo (zerotier-cli info)
IMPRESORA_PUERTO=8766
# SUMATRA_EXE=...                 ← solo si SumatraPDF.exe no está en esta carpeta
```

Y en el panel, **Ajustes → Servicios de impresión → «+ Agregar una computadora»**:

- **Nombre:** cómo la conoce la gente («Servidor del taller»).
- **¿Quién llama a quién?:** *El panel la llama*.
- **Dirección:** `10.147.x.x:8766` (la IP de ZeroTier de este equipo y el puerto).
- **Clave:** la misma `IMPRESORA_TOKEN` de arriba.

### Las dos

Guardar y pulsar **«Probar»**: tiene que decir «Contesta …». No hace falta reiniciar el panel.
En la forma A, «Probar» no llama a nadie —no puede—: contesta con lo último que dijo esta
computadora al ponerse a esperar, así que hay que tener el servicio corriendo y darle unos
segundos tras arrancarlo.
Si la empresa tiene varias computadoras, la marcada **«Por defecto»** es la que usan las
impresiones programadas; en cada impresora de factura se puede elegir otra.

> **Villa Lubri (empresa principal):** mientras no se agregue aquí, el panel sigue usando
> `IMPRESORA_URL` / `IMPRESORA_TOKEN` de su `.env` como respaldo. Aparece en la lista como
> «Servidor del taller (.env)». Ninguna otra empresa puede usar ese respaldo.

## 4. Abrir el puerto en el cortafuegos de Windows (solo en la forma B)

> En la forma A **sáltate esta sección entera**: no hay ningún puerto que abrir, que es justamente
> la gracia.


Arrancado desde el Programador de tareas no sale el aviso de «Permitir acceso», así que Windows
bloquea las peticiones del panel en silencio. En una consola **como administrador**:

```bat
netsh advfirewall firewall add rule name="Servicio de impresion PVV (ZeroTier)" dir=in action=allow protocol=TCP localport=8766 remoteip=10.147.0.0/16
```

`remoteip` es la red de ZeroTier (ajustarla si la vuestra no es 10.147.x.x): así el puerto queda
cerrado para la red local y para cualquier otra.

## 5. Probar a mano

```bat
venv\Scripts\python impresora.py
```

Al arrancar dice el nombre del equipo y **las impresoras que ve**.

En la **forma A** tiene que salir además:

```
[impresora] Esperando trabajo de https://miempresa.perspectivve.com como «a1b2c3d4e5»...
```

Si en vez de eso aparece *«El panel rechazó la credencial (401)»*, la clave o el `SERVICIO_ID` no
coinciden con los de Ajustes → Servicios de impresión. Si aparece *«Sin conexión con el panel»*,
es la dirección de `PANEL_URL` o la salida a internet del equipo.

En la **forma B**, desde el propio equipo, en otra consola:

```bat
curl -H "Authorization: Bearer EL_TOKEN" http://127.0.0.1:8766/salud
curl -H "Authorization: Bearer EL_TOKEN" http://127.0.0.1:8766/impresoras
```

Y desde el panel, en *Administración → Impresiones programadas* → **«Probar la conexión»**: tiene
que contestar con el nombre de este equipo.

## 6. Que arranque solo, en segundo plano

Una tarea programada que corre como **LOCAL SERVICE**, sin sesión
iniciada y sin guardar contraseñas. Cierra antes el servicio de prueba (Ctrl+C). En **PowerShell
como administrador**:

```powershell
# Permiso de escritura en la carpeta (impresora.log)
icacls C:\servicios-pvv /grant "LOCAL SERVICE:(OI)(CI)M"

Register-ScheduledTask -TaskName "Servicio de impresion PVV" -Force `
  -Xml (Get-Content C:\servicios-pvv\impresora\tarea.xml -Raw)

Start-ScheduledTask -TaskName "Servicio de impresion PVV"
```

Lo que imprime el servicio va a `impresora.log` en esta carpeta: ahí se ve qué papel salió y a qué
hora.

> ### ⚠️ La trampa de LOCAL SERVICE y las impresoras
>
> LOCAL SERVICE ve las impresoras **locales de la máquina**, no las que un usuario haya conectado
> en **su** sesión. Si la impresora está puesta como impresora de red de un usuario, a mano
> funciona y desde la tarea **no aparece**. Se ve enseguida: `/impresoras` no la lista, o la lista
> de la pantalla del panel sale vacía.
>
> Se arregla instalándola **como local, por IP** (Panel de control → Dispositivos e impresoras →
> Agregar → «Agregar una impresora mediante una dirección TCP/IP»). Entonces la ve todo el equipo.

## 7. Impresiones programadas (la hoja del cuadre)

Ya en el panel, con permiso **«Impresiones programadas»**:

1. *Administración → Impresiones programadas* → **«Probar la conexión»**.
2. **«Programar una»** → *Hoja de cuadre diario*, hora **08:00**, los días que abre el negocio, la
   impresora y 1 copia.
3. **«Imprimir ahora»** una vez, para ver el papel de verdad antes de confiar en la madrugada.

**La hoja de las 8 es la del día ANTERIOR**: a esa hora el día de hoy no ha pasado y su hoja
saldría en blanco.

## 8. Tickets de factura en impresoras de recibos (Star SP500, Epson TM…)

Desde la versión 1.1 el servicio tiene una segunda puerta, `POST /imprimir-crudo`, para los
tickets de factura. El panel arma el ticket **en el idioma de la impresora** (Star Line Mode o
ESC/POS: negritas, corte y gaveta incluidos) y aquí solo se entrega al spooler como `RAW`.

1. Instalar el controlador de Star (o del fabricante) en este equipo. Si la impresora está en
   otra computadora, compartirla en la red de Windows e instalarla aquí como local.
2. `pywin32` es **obligatorio** para esto (ya viene en `requirements.txt`).
3. En el panel: *Ajustes → Impresión de facturas* → agregar el equipo con «Cómo llega» = *Servicio
   de impresión* y «Idioma» = *Star* (SP500 en modo Star) o *ESC/POS*. «Imprimir prueba».

El idioma tiene que coincidir con el modo de la impresora (en la SP500, los interruptores DIP
eligen entre Star y ESC/POS). Si sale basura o caracteres raros, es eso.

## 9. Reglas de operación

- El servicio **no** consulta ninguna base de datos: solo imprime lo que le llega.
- **No** acepta en `/imprimir` nada que no sea un PDF (lo comprueba por los primeros bytes) ni
  mayor de 12 MB: mandarle basura al spooler de Windows deja trabajos encallados que hay que
  limpiar a mano. `/imprimir-crudo` acepta hasta 256 kB, que es cien veces un ticket.
- El PDF se escribe en el temporal del sistema y **se borra siempre**, salga o no el papel: los
  cuadres de caja de cada día no se quedan tirados en el disco.
- **Si un papel no sale, no hace ruido.** El sitio donde se ve es *«Últimos intentos»* en la
  pantalla del panel, que apunta cada intento salga o no. Mirarlo de vez en cuando es la única
  forma de enterarse de que la bandeja lleva tres días sin papel.


## 10. Si venía de `bridge-punch` (Villa Lubri)

Hasta la versión 1.1 este servicio vivía en `C:\bridge-punch-villalubri\impresora`, con el venv
del reloj. Para pasarlo aquí **sin tocar el panel** (mismo token, misma IP y mismo puerto):

```powershell
# 1. Parar y quitar la tarea vieja (PowerShell como administrador)
Stop-ScheduledTask -TaskName "Impresora Villa Lubri"
Unregister-ScheduledTask -TaskName "Impresora Villa Lubri" -Confirm:$false
```

2. Hacer el paso 1 de esta guía (clonar, venv, requirements).
3. Copiar el `.env` y `SumatraPDF.exe` de `C:\bridge-punch-villalubri\impresora\` a
   `C:\servicios-pvv\impresora\`.
4. Hacer el paso 6 (permiso, registrar la tarea nueva y arrancarla).
5. En el panel, *Administración → Impresiones programadas* → **«Probar la conexión»**.

La regla del cortafuegos vieja sigue sirviendo (es el mismo puerto). El reloj y el lector de placas
no se tocan.
