#Requires -RunAsAdministrator
# Instala los 4 procesos de Kurug como SERVICIOS de Windows (con NSSM) para que
# arranquen solos al encender el PC y se reinicien si se caen.
#
# Ejecutar UNA vez, en PowerShell ABIERTO COMO ADMINISTRADOR:
#   C:\kurug\chat-app\deploy\setup-nssm.ps1
#
# Es idempotente: si ya existen los servicios, los recrea. Lee los secretos
# del .env en caliente (no van escritos en este script).
#
# Gestion despues:
#   Get-Service kurug-*                 # ver estado
#   nssm restart kurug-backend          # reiniciar uno
#   Get-Content C:\kurug\logs\kurug-backend.log -Tail 40   # ver logs

$ErrorActionPreference = "Stop"
function Info($m){ Write-Host "`n==== $m ====" -ForegroundColor Cyan }

# --- Rutas ---
$deployDir = $PSScriptRoot
$chatApp   = Split-Path $deployDir -Parent          # C:\kurug\chat-app
$repoRoot  = Split-Path $chatApp   -Parent          # C:\kurug
$binDir    = Join-Path $repoRoot "bin"
$logDir    = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$venvPy  = Join-Path $chatApp ".venv\Scripts\python.exe"
$botPy   = Join-Path $chatApp "bot\.venv\Scripts\python.exe"
$livekit = Join-Path $binDir  "livekit-server.exe"
$caddy   = (Get-Command caddy -ErrorAction SilentlyContinue).Source
if (-not $caddy) { throw "No encuentro caddy en el PATH." }
foreach ($p in @($venvPy, $botPy, $livekit)) {
    if (-not (Test-Path $p)) { throw "No existe: $p" }
}

# --- NSSM (descarga a bin\ si no esta) ---
Info "Comprobando NSSM"
$nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $nssm) { $nssm = Join-Path $binDir "nssm.exe" }
if (-not (Test-Path $nssm)) {
    Write-Host "Descargando NSSM..."
    $zip = Join-Path $env:TEMP "nssm.zip"
    $ext = Join-Path $env:TEMP "nssm_ext"
    Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip
    Remove-Item $ext -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive $zip $ext -Force
    Copy-Item (Join-Path $ext "nssm-2.24\win64\nssm.exe") $nssm -Force
}
Write-Host "nssm: $nssm"

# --- Leer secretos del .env ---
Info "Leyendo secretos del .env"
$envMap = @{}
Get-Content (Join-Path $chatApp ".env") | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') { $envMap[$matches[1]] = $matches[2].Trim() }
}
$secretKey = $envMap['SECRET_KEY']
$lkKey     = $envMap['LIVEKIT_API_KEY']
$lkSecret  = $envMap['LIVEKIT_API_SECRET']
if (-not $secretKey -or -not $lkSecret) { throw "Faltan SECRET_KEY / LIVEKIT_API_SECRET en .env" }

# --- Parar procesos sueltos de esta sesion (liberar puertos) ---
Info "Parando procesos sueltos (si los hay)"
Get-Process livekit-server, caddy -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn|bot\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 2

# --- Helper: (re)crear un servicio ---
function Set-Svc($name, $exe, $svcArgs, $dir, [string[]]$envExtra, [string[]]$deps) {
    if (Get-Service $name -ErrorAction SilentlyContinue) {
        & $nssm stop $name confirm 2>$null | Out-Null
        Start-Sleep 1
        & $nssm remove $name confirm 2>$null | Out-Null
        Start-Sleep 1
    }
    & $nssm install $name $exe $svcArgs | Out-Null
    & $nssm set $name AppDirectory $dir | Out-Null
    & $nssm set $name Start SERVICE_AUTO_START | Out-Null
    & $nssm set $name AppStdout (Join-Path $logDir "$name.log") | Out-Null
    & $nssm set $name AppStderr (Join-Path $logDir "$name.log") | Out-Null
    & $nssm set $name AppRotateFiles 1 | Out-Null
    & $nssm set $name AppRotateBytes 5000000 | Out-Null
    & $nssm set $name AppExit Default Restart | Out-Null
    & $nssm set $name AppRestartDelay 3000 | Out-Null
    if ($envExtra) { & $nssm set $name AppEnvironmentExtra $envExtra | Out-Null }
    if ($deps)     { & $nssm set $name DependOnService $deps | Out-Null }
    Write-Host "  servicio $name listo"
}

Info "Creando servicios"
Set-Svc "kurug-livekit" $livekit "--config deploy\livekit.yaml" $chatApp $null $null
Set-Svc "kurug-backend" $venvPy "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" $chatApp $null $null
Set-Svc "kurug-bot" $botPy "bot.py" (Join-Path $chatApp "bot") `
    @("SECRET_KEY=$secretKey", "LIVEKIT_URL=ws://localhost:7880", "LIVEKIT_API_KEY=$lkKey", "LIVEKIT_API_SECRET=$lkSecret") `
    @("kurug-backend", "kurug-livekit")
Set-Svc "kurug-caddy" $caddy "run --config deploy\Caddyfile-windows" $chatApp $null $null

Info "Arrancando servicios"
foreach ($s in "kurug-livekit", "kurug-backend", "kurug-bot", "kurug-caddy") {
    & $nssm start $s 2>$null | Out-Null
    Start-Sleep 2
    Write-Host ("  {0,-16} -> {1}" -f $s, (Get-Service $s).Status)
}

Start-Sleep 4
Info "Puertos en escucha (deben salir 80, 443, 7880, 7881, 8000)"
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 80, 443, 8000, 7880, 7881 } |
    Select-Object LocalPort, OwningProcess | Sort-Object LocalPort | Format-Table -AutoSize

Write-Host "`nListo. Los 4 servicios arrancaran solos al encender el PC y se reinician si se caen." -ForegroundColor Green
Write-Host "Ver estado:  Get-Service kurug-*" -ForegroundColor Green
Write-Host "Logs en:     $logDir" -ForegroundColor Green
