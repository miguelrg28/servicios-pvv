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
:inicio
echo [%date% %time%] Arrancando el servicio de impresion >> impresora.log
"%PY%" -u impresora.py >> impresora.log 2>&1
echo [%date% %time%] El servicio se detuvo; se relanza en 30 s >> impresora.log
ping -n 31 127.0.0.1 > nul
goto inicio
