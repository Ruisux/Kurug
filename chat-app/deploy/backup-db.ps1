# Backup CONSISTENTE de chat.db (usa el backup online de SQLite, seguro aunque
# el backend este escribiendo) con rotacion. Pensado para una tarea programada.
#
# Probar a mano:   C:\kurug\chat-app\deploy\backup-db.ps1
# Programar diario (una vez, en PowerShell como ADMINISTRADOR):
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\kurug\chat-app\deploy\backup-db.ps1"
#   $t = New-ScheduledTaskTrigger -Daily -At 4am
#   Register-ScheduledTask -TaskName "Kurug DB Backup" -Action $a -Trigger $t -RunLevel Highest

$ErrorActionPreference = "Stop"
$deployDir = $PSScriptRoot
$chatApp   = Split-Path $deployDir -Parent
$repoRoot  = Split-Path $chatApp   -Parent
$py        = Join-Path $chatApp ".venv\Scripts\python.exe"
$src       = Join-Path $chatApp "chat.db"
$backupDir = Join-Path $repoRoot "backups"
$keep      = 14   # cuantas copias conservar

if (-not (Test-Path $src)) { throw "No existe la BD: $src" }
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$dst = Join-Path $backupDir ("chat-{0}.db" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

# Backup ONLINE via la API de sqlite3 (bloqueo minimo, copia coherente).
& $py -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $src $dst
Write-Host "Backup creado: $dst"

# Rotacion: conservar solo los $keep mas recientes.
Get-ChildItem $backupDir -Filter "chat-*.db" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $keep |
    ForEach-Object { Remove-Item $_.FullName -Force; Write-Host "Borrado antiguo: $($_.Name)" }
