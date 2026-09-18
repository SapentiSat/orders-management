@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "connector\requirements.txt" (
  echo.
  echo BLAD: Uruchom ten plik z folderu projektu Orders Management
  echo        oczekiwany plik: connector\requirements.txt
  echo        biezacy folder: %CD%
  echo.
  pause
  exit /b 1
)

echo Instalacja zaleznosci...
python -m pip install -q -r connector\requirements.txt
if errorlevel 1 (
  echo BLAD pip install
  pause
  exit /b 1
)

netstat -ano | findstr /C:":8765" | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
  echo.
  echo UWAGA: Port 8765 jest juz zajety — Nexo Connector prawdopodobnie juz dziala.
  echo Otworz: http://127.0.0.1:8765/setup
  echo.
  echo Jesli to stary proces: zamknij poprzednie okno z lacznikiem
  echo albo zamknij proces Python w Menedzerze zadan ^(szczegoly^).
  echo.
  pause
  exit /b 1
)

echo.
echo Nexo Connector: http://127.0.0.1:8765/setup
echo Zamknij okno aby zatrzymac serwer.
echo.
python -m connector.server
pause
