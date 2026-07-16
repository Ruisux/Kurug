# Despliega en ESTE PC (Windows) la ultima version del servidor Kurug.
#
# Hace, en orden:
#   1. git pull (trae lo que subiste desde el Mac)
#   2. amplia la sesion en .env si aun tiene el valor viejo (1 dia -> 1 ano)
#   3. recompila el frontend que sirve Caddy (web/dist)
#   4. actualiza dependencias del backend (si cambiaron)
#   5. aplica migraciones de la base de datos (alembic)
#   6. reinicia backend + bot (si estan como servicios NSSM)
#
# Uso:  desde PowerShell ->  .\deploy\update-kurug.ps1
# Los SECRETOS (livekit.yaml, start-kurug.bat, y las claves del .env) NO se
# tocan: son locales. Del .env solo se migra ACCESS_TOKEN_EXPIRE_MINUTES, que
# no es un secreto, y unicamente si sigue con el default viejo.

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
Step "1/6  git pull"
Push-Location $repoRoot
try {
    git fetch --all --prune
    # --ff-only evita merges accidentales; si falla, avisa y para.
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        throw "git pull --ff-only fallo. Puede que tengas commits locales sin subir o un conflicto. Resuelvelo a mano."
    }
} finally { Pop-Location }

# 2) Sesion larga ----------------------------------------------------------
# El .env manda sobre el default del codigo, asi que el valor viejo (1440 = 1
# dia) haria que la app pidiera login cada vez que se reinicia el PC. Solo se
# cambia si sigue EXACTAMENTE con ese default; si pusiste otro valor a mano, se
# respeta.
Step "2/6  Sesion larga (.env)"
$envFile = Join-Path $chatApp ".env"
$oldExpiry = '(?m)^\s*ACCESS_TOKEN_EXPIRE_MINUTES\s*=\s*1440\s*$'
if (Test-Path $envFile) {
    $envTxt = Get-Content $envFile -Raw
    if ($envTxt -match $oldExpiry) {
        ($envTxt -replace $oldExpiry, 'ACCESS_TOKEN_EXPIRE_MINUTES=525600') |
            Set-Content -Path $envFile -Encoding UTF8 -NoNewline
        Write-Host "  Sesion ampliada de 1 dia a 1 ano: ya no pedira login al reiniciar el PC." -ForegroundColor Green
    } else {
        Write-Host "  Sin cambios (el .env ya no tiene el valor viejo 1440)." -ForegroundColor Yellow
    }
} else {
    Write-Host "  No encuentro .env; me lo salto." -ForegroundColor Yellow
}

# 3) Frontend --------------------------------------------------------------
Step "3/6  Recompilar frontend (web/dist)"
Push-Location (Join-Path $chatApp "web")
try {
    npm ci
    npm run build          # el frontend del server usa mismo origen; no necesita VITE_KURUG_SERVER
} finally { Pop-Location }

# 4) Dependencias del backend ---------------------------------------------
Step "4/6  Dependencias del backend (pip)"
if (-not (Test-Path $venvPy)) { throw "No encuentro el venv del backend en $venvPy" }
& $venvPy -m pip install -r (Join-Path $chatApp "requirements.txt")

# 5) Migraciones de BD -----------------------------------------------------
Step "5/6  Migraciones de base de datos (alembic)"
Push-Location $chatApp
try {
    & $venvPy -m alembic upgrade head
} finally { Pop-Location }

# 6) Reiniciar servicios ---------------------------------------------------
Step "6/6  Reiniciar backend + bot"
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
