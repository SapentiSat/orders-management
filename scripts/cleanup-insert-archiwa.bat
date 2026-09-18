@echo off
setlocal EnableExtensions

rem Jeden plik: czyszczenie archiwow InsERT + log (zawsze nadpisywany).
rem Zostawia 2 najnowsze foldery lub .zip, reszte usuwa na stale (bez Kosza).

set "TARGET=C:\Users\suuhouse01_admin\Documents\InsERT\Archiwa InsERT nexo"
set "KEEP=2"
set "LOG=%~dp0cleanup-insert-archiwa.log"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$target=$env:TARGET; $keep=[int]$env:KEEP; $log=$env:LOG;" ^
  "function W([string]$m){ Add-Content -LiteralPath $log -Value $m -Encoding UTF8 };" ^
  "Set-Content -LiteralPath $log -Value ('Start: {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -Encoding UTF8;" ^
  "try {" ^
  "  W ('Target: {0}' -f $target);" ^
  "  W ('Keep: {0}' -f $keep);" ^
  "  if (-not (Test-Path -LiteralPath $target)) { throw ('Brak folderu: {0}' -f $target) };" ^
  "  $items=@();" ^
  "  $items+=@(Get-ChildItem -LiteralPath $target -Directory -EA SilentlyContinue);" ^
  "  $items+=@(Get-ChildItem -LiteralPath $target -File -Filter '*.zip' -EA SilentlyContinue);" ^
  "  $sorted=@($items | Sort-Object LastWriteTime -Descending);" ^
  "  $keepCount=[Math]::Min($keep,$sorted.Count);" ^
  "  W ('Znaleziono: {0} (foldery + zip)' -f $sorted.Count);" ^
  "  W ('Zachowuje: {0}' -f $keepCount);" ^
  "  foreach($i in ($sorted | Select-Object -First $keepCount)){ W ('  KEEP  {0}  {1}' -f $i.LastWriteTime.ToString('yyyy-MM-dd HH:mm'), $i.Name) };" ^
  "  $del=@($sorted | Select-Object -Skip $keep);" ^
  "  W ('Do usuniecia: {0}' -f $del.Count);" ^
  "  foreach($i in $del){ W ('  DEL   {0}  {1}' -f $i.LastWriteTime.ToString('yyyy-MM-dd HH:mm'), $i.Name); Remove-Item -LiteralPath $i.FullName -Recurse -Force };" ^
  "  W ('Koniec: {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'));" ^
  "  W 'Gotowe.';" ^
  "  exit 0" ^
  "} catch {" ^
  "  W ('BLAD: {0}' -f $_.Exception.Message);" ^
  "  exit 1" ^
  "}"

set "ERR=%ERRORLEVEL%"
echo Log: "%LOG%"
if exist "%LOG%" type "%LOG%"
exit /b %ERR%
