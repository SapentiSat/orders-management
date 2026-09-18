@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "connector\requirements.txt" (
  echo BLAD: brak connector\requirements.txt — uruchom z folderu projektu.
  pause
  exit /b 1
)

python -m pip install -q -r connector\requirements.txt
python -m connector.server
pause
