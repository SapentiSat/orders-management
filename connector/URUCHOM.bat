@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "connector\requirements.txt" (
  echo.
  echo BLAD: Rozpakuj caly folder NexoConnector i uruchom ten plik.
  echo        Brak: connector\requirements.txt
  echo        Folder: %CD%
  echo.
  pause
  exit /b 1
)

netstat -ano | findstr /C:":8765" | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
  echo Port 8765 zajety — lacznik juz dziala: http://127.0.0.1:8765/setup
  pause
  exit /b 0
)

echo Instalacja zaleznosci (pierwszy raz moze potrwac)...
python -m pip install -q -r connector\requirements.txt
if errorlevel 1 (
  echo BLAD instalacji — sprawdz czy masz Python 3.10+
  pause
  exit /b 1
)

echo.
echo === Nexo Connector ===
echo Konfiguracja: http://127.0.0.1:8765/setup
echo Token API skopiuj z panelu web - Integracje - Nexo Connector
echo.
python -m connector.server
pause
