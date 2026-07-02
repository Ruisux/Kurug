@echo off
REM Arranca Kurug en modo PRUEBA LAN (solo chat, por HTTP) para tus dispositivos.
REM Sirve la SPA + API en http://<tu-IP-local>:8080 (este PC: 192.168.1.28).
REM Voz/compartir pantalla NO funcionan por HTTP (los navegadores exigen HTTPS
REM fuera de localhost). Para eso usa el despliegue con dominio/Tailscale.
set KURUG_DIR=C:\kurug\chat-app

REM 1) Backend (un solo worker, solo escucha en localhost; Caddy lo expone)
start "Kurug Backend (LAN)" cmd /k "cd /d %KURUG_DIR% && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM 2) Caddy: unico origen en :8080 (todas las interfaces) sirviendo SPA + proxy
start "Kurug Caddy (LAN)" cmd /k "cd /d %KURUG_DIR% && caddy run --config deploy\Caddyfile-lan"

echo.
echo Kurug (LAN) arrancado. Desde tus dispositivos en la MISMA WiFi entra en:
echo     http://192.168.1.28:8080
echo.
echo (Registro: llega un codigo por email. Chat OK; voz/pantalla NO por HTTP.)
