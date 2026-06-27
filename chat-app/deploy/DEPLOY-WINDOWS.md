# Desplegar Kurug en tu PC con Windows (router + DuckDNS)

Servir Kurug 24/7 desde tu Windows, accesible para los 10 por internet, con
HTTPS de confianza y voz/pantalla funcionando. Gratis (solo hay que abrir
puertos del router).

Piezas que corren en el PC:
- **Backend** (FastAPI/uvicorn) en `127.0.0.1:8000`
- **LiveKit** (voz/pantalla) en `:7880` (señalización) + **UDP 7882** (media)
- **Bot de música** (proceso aparte)
- **Caddy** = reverse proxy con HTTPS automático (un solo origen)
- **DuckDNS** = dominio gratis que sigue tu IP de casa

> Cuello de botella: compartir pantalla a N personas sube **una copia por
> espectador** desde tu casa. Tu **velocidad de SUBIDA** es el techo. Regla
> rápida: pantalla 720p ≈ 2-3 Mbps por espectador. Con 10 Mbps de subida,
> ~3-4 espectadores a la vez; baja el preset si va justo.

---

## 1. Requisitos (instalar una vez)
1. **Python 3.11+** (https://python.org, marca "Add to PATH")
2. **Node 20+** (https://nodejs.org)
3. **ffmpeg** (https://www.gyan.dev/ffmpeg/builds/ — añade `bin` al PATH; lo usa el bot)
4. **LiveKit server (Windows)** — `.exe` de https://github.com/livekit/livekit/releases
5. **Caddy (Windows)** — `caddy.exe` de https://caddyserver.com/download

## 2. DuckDNS (dominio gratis)
1. Entra en https://www.duckdns.org con tu cuenta Google/GitHub.
2. Crea un subdominio, p. ej. `kurug` → quedará `kurug.duckdns.org`.
3. Copia tu **token** de DuckDNS.
4. Mantén la IP al día: crea una **Tarea programada** de Windows que cada 5 min
   abra esta URL (pon tu subdominio y token):
   ```
   https://www.duckdns.org/update?domains=kurug&token=TU_TOKEN&ip=
   ```
   (PowerShell: `Invoke-RestMethod "https://www.duckdns.org/update?domains=kurug&token=TU_TOKEN&ip="`)

## 3. Router: reenviar puertos al PC
Apunta estos puertos a la **IP local** de tu PC (mira `ipconfig`, algo como 192.168.1.x):
- **TCP 80**  → 80   (Caddy saca el certificado HTTPS por aquí)
- **TCP 443** → 443  (web + API + señalización)
- **UDP 7882** → 7882 (media de voz/pantalla de LiveKit)
- *(opcional)* **TCP 7881** → 7881 (respaldo de LiveKit si el UDP del cliente está bloqueado)

Y en el **Firewall de Windows**, permite `caddy.exe`, `livekit-server.exe` y Python
(la primera vez que arrancan, Windows pregunta: acepta para redes privadas y públicas).

## 4. Configuración (`chat-app/.env`)
Copia `.env.example` a `.env` y rellena:
```
SECRET_KEY=<python -c "import secrets;print(secrets.token_hex(32))">
DATABASE_URL=sqlite:///./chat.db
GIPHY_API_KEY=<tu key>
SMTP_USER=<tu gmail>
SMTP_PASSWORD=<contraseña de aplicación>
MAX_UPLOAD_MB=2048

LIVEKIT_URL=wss://kurug.duckdns.org      # la que reciben los navegadores (vía Caddy)
LIVEKIT_API_KEY=kurug
LIVEKIT_API_SECRET=<python -c "import secrets;print(secrets.token_hex(32))">
```
Pon ese mismo secret en `deploy/livekit.yaml` (`keys: kurug: <secret>`).

## 5. Compilar el frontend (una vez)
```powershell
cd chat-app\web
npm ci
npm run build
```
Ajusta en `deploy\Caddyfile-windows`:
- `tunombre.duckdns.org` → `kurug.duckdns.org`
- la ruta de `root *` → la carpeta `dist` real (p. ej. `C:\kurug\chat-app\web\dist`)

## 6. Arrancar todo
Edita `deploy\start-kurug.bat` (pon `KURUG_DIR`, `MAGICDNS`→tu dominio y `BOT_SECRET`)
y ejecútalo. Lanza LiveKit + backend + bot + Caddy, cada uno en su ventana.

## 7. Acceso de los amigos
Cada uno entra en el navegador a:  **`https://kurug.duckdns.org`**
Certificado válido (sin avisos), micro y pantalla funcionan. Se registran con su
correo (les llega el código por email).

## 8. Que arranque solo (24/7, opcional)
Instala cada proceso como servicio con [NSSM](https://nssm.cc/): uno para `caddy`,
otro para `livekit-server`, otro para `uvicorn` (backend) y otro para el `bot`.

## Si la voz no conecta
- Confirma que **UDP 7882** está reenviado al PC y permitido en el Firewall.
- Comprueba que `use_external_ip: true` está en `livekit.yaml` (anuncia tu IP pública).
- Algunos routers no hacen "NAT hairpin": tú mismo, desde casa, podrías tener
  problemas aunque a los de fuera les funcione. Pruébalo con alguien externo.
- Si a alguien le falla el UDP, el respaldo TCP 7881 (si lo abriste) lo cubre.
