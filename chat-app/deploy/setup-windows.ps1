# Setup automático de Kurug en Windows (parte mecánica).
# Ejecutar desde la carpeta chat-app:  powershell -ExecutionPolicy Bypass -File deploy\setup-windows.ps1
#
# Hace: entornos Python (backend + bot) + dependencias + build del frontend +
# base de datos + genera secretos y crea un .env inicial.
# NO hace (manual): DuckDNS, abrir puertos del router, y rellenar GIPHY/SMTP.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")   # -> carpeta chat-app
Write-Host "== Carpeta: $(Get-Location)" -ForegroundColor Cyan

# --- 1. Entorno Python del backend ---
Write-Host "`n== Backend: entorno + dependencias" -ForegroundColor Cyan
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip -q
.\.venv\Scripts\pip install -r requirements.txt -q

# --- 2. Entorno Python del bot ---
Write-Host "`n== Bot: entorno + dependencias" -ForegroundColor Cyan
python -m venv bot\.venv
.\bot\.venv\Scripts\pip install -r bot\requirements.txt -q

# --- 3. Secretos ---
$SECRET = (.\.venv\Scripts\python -c "import secrets;print(secrets.token_hex(32))").Trim()
$LKSECRET = (.\.venv\Scripts\python -c "import secrets;print(secrets.token_hex(32))").Trim()

# --- 4. .env inicial (si no existe) ---
if (-not (Test-Path ".env")) {
  Write-Host "`n== Creando .env inicial" -ForegroundColor Cyan
  $domain = Read-Host "Tu subdominio DuckDNS (ej. kurug.duckdns.org)"
  @"
SECRET_KEY=$SECRET
DATABASE_URL=sqlite:///./chat.db
# 525600 min = 1 ano: se inicia sesion una vez, no en cada reinicio del PC.
ACCESS_TOKEN_EXPIRE_MINUTES=525600
MAX_UPLOAD_MB=2048

# Rellena estos a mano:
GIPHY_API_KEY=
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_NAME=Kurug

LIVEKIT_URL=wss://$domain
LIVEKIT_API_KEY=kurug
LIVEKIT_API_SECRET=$LKSECRET
"@ | Set-Content -Encoding UTF8 .env
  Write-Host "  .env creado. Falta poner GIPHY_API_KEY, SMTP_USER y SMTP_PASSWORD." -ForegroundColor Yellow
  Write-Host "  Pon este MISMO secret en deploy\livekit.yaml -> keys: kurug: $LKSECRET" -ForegroundColor Yellow
} else {
  Write-Host "`n== .env ya existe, no lo toco." -ForegroundColor Yellow
}

# --- 5. Base de datos ---
Write-Host "`n== Base de datos (alembic)" -ForegroundColor Cyan
.\.venv\Scripts\alembic upgrade head

# --- 6. Build del frontend ---
Write-Host "`n== Frontend: npm ci + build" -ForegroundColor Cyan
Set-Location web
npm ci
npm run build
Set-Location ..

Write-Host "`n== LISTO. Siguiente:" -ForegroundColor Green
Write-Host "  1) Rellena GIPHY/SMTP en .env y el secret en deploy\livekit.yaml"
Write-Host "  2) Ajusta deploy\Caddyfile-windows (tu dominio y la ruta de web\dist)"
Write-Host "  3) Abre puertos del router (80,443 TCP / 7882 UDP) y arranca con deploy\start-kurug.bat"
