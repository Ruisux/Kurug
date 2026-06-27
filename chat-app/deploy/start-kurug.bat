@echo off
REM Arranca toda la pila de Kurug en Windows (cada parte en su ventana).
REM Ajusta KURUG_DIR a donde tengas el proyecto.
set KURUG_DIR=C:\kurug\chat-app
set MAGICDNS=kurug-pc.tuTailnet.ts.net
REM El bot necesita el MISMO SECRET_KEY que el backend (ponlo aqui):
set BOT_SECRET=PEGA_AQUI_EL_MISMO_SECRET_KEY

REM 1) LiveKit (voz/pantalla)
start "Kurug LiveKit" cmd /k "cd /d %KURUG_DIR% && livekit-server --config deploy\livekit.yaml"

REM 2) Backend (un solo worker)
start "Kurug Backend" cmd /k "cd /d %KURUG_DIR% && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM 3) Bot de musica
start "Kurug Bot" cmd /k "cd /d %KURUG_DIR%\bot && set SECRET_KEY=%BOT_SECRET% && set LIVEKIT_URL=ws://localhost:7880 && .venv\Scripts\python bot.py"

REM 4) Caddy (HTTPS / reverse proxy)
start "Kurug Caddy" cmd /k "cd /d %KURUG_DIR% && caddy run --config deploy\Caddyfile-windows"

echo Kurug arrancado. Entra en https://%MAGICDNS%
