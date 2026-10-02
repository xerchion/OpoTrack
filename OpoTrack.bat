@echo off
setlocal enableextensions
title OpoTrack
cd /d "%~dp0"

echo ============================================
echo    OpoTrack - iniciando...
echo ============================================
echo.

REM --- 1) Comprobar que Python esta disponible ---
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se ha encontrado Python en el PATH.
  echo Instala Python 3.10 o superior desde https://www.python.org/downloads/
  echo y marca la casilla "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

REM --- 2) Instalar dependencias si falta alguna ---
python -c "import flask, bs4, sqlalchemy, requests" 1>nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias, espera un momento...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias.
    echo.
    pause
    exit /b 1
  )
)

REM --- 3) Preparar la base de datos y los datos iniciales (idempotente) ---
echo Preparando la base de datos...
python cli.py seed

REM --- 4) Abrir el navegador tras un breve retardo (da tiempo al servidor) ---
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:5000'"

REM --- 5) Arrancar el servidor web ---
echo.
echo ============================================
echo    OpoTrack funcionando en http://127.0.0.1:5000
echo    Cierra esta ventana o pulsa Ctrl+C para detenerlo.
echo ============================================
echo.
python run_web.py

endlocal
