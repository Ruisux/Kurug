# Despliega en ESTE PC (Windows) la ultima version del servidor Kurug.
#
# Hace, en orden:
#   1. git pull (trae lo que subiste desde el Mac)
#   2. recompila el frontend que sirve Caddy (web/dist)
#   3. actualiza dependencias del backend (si cambiaron)
#   4. aplica migraciones de la base de datos (alembic)
#   5. reinicia backend + bot (si estan como servicios NSSM)
#
# Uso:  desde PowerShell ->  .\deploy\update-kurug.ps1
# Los secretos (.env, livekit.yaml, start-kurug.bat) NO se tocan: son locales.

$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }

# Rutas robustas a partir de la ubicacion de este script (deploy/).
$deployDir = $PSScriptRoot
$chatApp   = Split-Path $deployDir -Parent          # C:\kurug\chat-app
$repoRoot  = Split-Path $chatApp   -Parent          # C:\kurug
$venvPy    = Join-Path $chatApp ".venv\Scripts\python.exe"

Write-Host "Repo:    $repoRoot"
Write-Host "chatApp: $chatApp"

# 1) Traer cambios ---------------------------------------------------------
Step "1/5  git pull"
Push-Location $repoRoot
try {
    git fetch --all --prune
    # --ff-only evita merges accidentales; si falla, avisa y para.
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        throw "git pull --ff-only fallo. Puede que tengas commits locales sin subir o un conflicto. Resuelvelo a mano."
    }
} finally { Pop-Location }

# 2) Frontend --------------------------------------------------------------
Step "2/5  Recompilar frontend (web/dist)"
Push-Location (Join-Path $chatApp "web")
try {
    npm ci
    npm run build          # el frontend del server usa mismo origen; no necesita VITE_KURUG_SERVER
} finally { Pop-Location }

# 3) Dependencias del backend ---------------------------------------------
Step "3/5  Dependencias del backend (pip)"
if (-not (Test-Path $venvPy)) { throw "No encuentro el venv del backend en $venvPy" }
& $venvPy -m pip install -r (Join-Path $chatApp "requirements.txt")

# 4) Migraciones de BD -----------------------------------------------------
Step "4/5  Migraciones de base de datos (alembic)"
Push-Location $chatApp
try {
    & $venvPy -m alembic upgrade head
} finally { Pop-Location }

# 5) Reiniciar servicios ---------------------------------------------------
Step "5/5  Reiniciar backend + bot"
$services = @("kurug-backend", "kurug-bot")
$anyService = $false
foreach ($s in $services) {
    $svc = Get-Service -Name $s -ErrorAction SilentlyContinue
    if ($svc) {
        $anyService = $true
        Write-Host "Reiniciando servicio $s ..."
        Restart-Service -Name $s -Force
    }
}
if (-not $anyService) {
    Write-Host "No hay servicios NSSM (kurug-backend/kurug-bot)." -ForegroundColor Yellow
    Write-Host "Cierra las ventanas del backend y del bot y vuelve a lanzarlas" -ForegroundColor Yellow
    Write-Host "(o ejecuta deploy\start-kurug.bat de nuevo)." -ForegroundColor Yellow
    Write-Host "LiveKit y Caddy normalmente NO necesitan reinicio." -ForegroundColor Yellow
}

Write-Host "`nListo. Servidor actualizado." -ForegroundColor Green
