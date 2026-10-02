@echo off
setlocal enableextensions
REM ============================================================
REM  OpoTrack - Aviso diario de novedades por Telegram
REM  Lo lanza la tarea programada de Windows (ver NOTIFICACIONES.md).
REM  Tambien puedes ejecutarlo a mano para probar.
REM ============================================================
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
set "LOGFILE=logs\notificar.log"

echo.>> "%LOGFILE%"
echo ===== %date% %time% =====>> "%LOGFILE%"

REM Busca en todas las fuentes activas y envia el resumen por Telegram.
python cli.py notificar >> "%LOGFILE%" 2>&1

REM --- Opcional: hibernar el equipo tras avisar (util con encendido por RTC).
REM     Descomenta la linea siguiente si quieres que se apague solo despues.
REM shutdown /h

endlocal
