@echo off
REM Lo que lanza la tarea "Servicio de impresion PVV" (tarea.xml) al iniciar el equipo.
REM `cd /d "%~dp0"` mueve a la carpeta del .bat: la tarea puede arrancar desde C:\Windows\System32
REM y entonces el .env y SumatraPDF.exe se buscarian donde no estan. Asi funciona en cualquier
REM carpeta: no hay ninguna ruta fija.
REM
REM Python: el venv de ESTA carpeta (venv\). Si no existe, el `py` del sistema.
REM
REM El servicio se queda corriendo. Si se cae (al arrancar el equipo ZeroTier aun no tiene IP...)
REM se relanza a los 30 s. Lo que imprime va a impresora.log.
REM La espera es con ping y no con `timeout`: `timeout` falla sin una consola de verdad.
cd /d "%~dp0"
set PY=venv\Scripts\python.exe
if not exist "%PY%" set PY=py
REM Si no hay venv Y el `py` del sistema tampoco esta, el error que sale es "py no se reconoce",
REM que no dice nada a quien instala. Casi siempre es que Python se instalo solo para mi: el
REM lanzador queda en la carpeta del usuario y LOCAL SERVICE, que es quien corre esta tarea, no lo
REM ve. Se dice aqui, con el arreglo, en vez de dejarlo en el aire.
if "%PY%"=="py" (
  where py >nul 2>&1 || (
    echo [%date% %time%] NO HAY PYTHON PARA ESTA CUENTA. >> impresora.log
    echo     Falta el venv de esta carpeta, y el py del sistema no lo ve LOCAL SERVICE. >> impresora.log
    echo     Arreglo: crea el venv con   py -m venv venv   y luego >> impresora.log
    echo              venv\Scripts\python -m pip install -r requirements.txt >> impresora.log
    echo     Si el venv tampoco arranca, Python esta instalado solo para un usuario: >> impresora.log
    echo     reinstalalo marcando "Install for all users" y vuelve a crear el venv. >> impresora.log
  )
)
:inicio
echo [%date% %time%] Arrancando el servicio de impresion con %PY% >> impresora.log
"%PY%" -u impresora.py >> impresora.log 2>&1
echo [%date% %time%] El servicio se detuvo; se relanza en 30 s >> impresora.log
ping -n 31 127.0.0.1 > nul
goto inicio
