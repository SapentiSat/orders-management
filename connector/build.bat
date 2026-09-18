@echo off
setlocal
cd /d %~dp0..
echo Instalacja zaleznosci...
python -m pip install -q -r connector\requirements.txt pyinstaller
echo Budowa EXE...
python -m PyInstaller --noconfirm --clean ^
  --name NexoConnector ^
  --onefile ^
  --console ^
  --paths . ^
  --add-data "sample_data;sample_data" ^
  --hidden-import=uvicorn.logging ^
  --hidden-import=uvicorn.loops ^
  --hidden-import=uvicorn.loops.auto ^
  --hidden-import=uvicorn.protocols ^
  --hidden-import=uvicorn.protocols.http ^
  --hidden-import=uvicorn.protocols.http.auto ^
  --hidden-import=uvicorn.protocols.websockets ^
  --hidden-import=uvicorn.protocols.websockets.auto ^
  --hidden-import=uvicorn.lifespan ^
  --hidden-import=uvicorn.lifespan.on ^
  connector\server.py
if exist dist\NexoConnector.exe (
  echo OK: dist\NexoConnector.exe
  copy /Y dist\NexoConnector.exe dist\NexoConnector.zip >nul 2>&1
) else (
  echo BLAD budowy — uzyj NexoConnector.zip z panelu
  exit /b 1
)
endlocal
