# Desplegar en tu PC con Ubuntu (server casero)

Guía para correr Mini Chat 24/7 en tu propio equipo y usarlo desde cualquier
dispositivo de tu casa (LAN).

## 1. Dejar el proyecto en el server

Copia la carpeta `chat-app` al server (por SSH, USB, git, como prefieras).
Supongamos que queda en `/home/pedro/chat-app`.

## 2. Crear el entorno virtual e instalar

```bash
cd /home/pedro/chat-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env          # cambia SECRET_KEY por algo largo y aleatorio
```

Genera un SECRET_KEY decente con:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 3. Probar a mano una vez

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` es la clave: hace que el server escuche en todas las
interfaces de red, no solo en localhost, para que otros equipos lo alcancen.

Averigua la IP local del server:
```bash
hostname -I        # ej: 192.168.1.50
```

Desde otro equipo de la casa, abre `http://192.168.1.50:8000`. Si funciona,
para con Ctrl+C y sigue al paso 4 para dejarlo permanente.

## 4. Abrir el puerto en el firewall (si usas ufw)

```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

## 5. Correrlo como servicio (arranca solo al encender)

1. Edita `deploy/minichat.service` y ajusta `User` y las rutas a tu caso.
2. Instálalo:

```bash
sudo cp deploy/minichat.service /etc/systemd/system/minichat.service
sudo systemctl daemon-reload
sudo systemctl enable --now minichat
```

Comandos útiles:
```bash
systemctl status minichat        # ¿está corriendo?
journalctl -u minichat -f        # ver logs en vivo
sudo systemctl restart minichat  # reiniciar tras un cambio de código
```

A partir de aquí el chat queda disponible en `http://IP-DEL-SERVER:8000`
para toda tu red local, y vuelve solo después de un reinicio.

## Notas para más adelante

- **Acceso desde fuera de casa**: no abras el puerto del router directo a
  internet. Mejor usa **Tailscale** (red privada, gratis para uso personal) o
  un **Cloudflare Tunnel**. Ambos te dan acceso remoto seguro sin exponer el PC.

- **HTTPS y screen share**: cuando llegues a la fase de voz/compartir pantalla,
  el navegador exige un "contexto seguro" (HTTPS) para capturar pantalla y
  micrófono — `http://IP-local` no basta. Las salidas más simples en LAN son
  Tailscale (te da HTTPS automático) o generar un certificado local con
  `mkcert`. `localhost` sí cuenta como seguro, por eso en pruebas locales en el
  propio server no da problema.

- **Recursos**: con SQLite y un worker esto consume del orden de decenas de MB
  de RAM en reposo. Perfecto para un PC casero.

---

# Despliegue COMPLETO con voz/pantalla (LiveKit)

Lo de arriba sirve para el chat. Para **voz, compartir pantalla y música** hace
falta además el servidor **LiveKit** (SFU) y servir todo por **HTTPS** desde un
único origen. Piezas:

| Pieza | Cómo corre | Para qué |
|---|---|---|
| Backend FastAPI | systemd (`minichat.service`) | chat, perfiles, tokens de voz |
| Bot de música | systemd (`kurug-bot.service`) | publica el audio en la voz de general |
| LiveKit (SFU) | Docker (`docker-compose.yml`) | reparte el audio/vídeo entre los 10 |
| Caddy (reverse proxy) | systemd (lo instala su paquete) | HTTPS + une SPA + API + LiveKit |

## 1. Dependencias del sistema

```bash
sudo apt update
sudo apt install -y ffmpeg            # lo necesita el bot de música
# Docker (para LiveKit):  https://docs.docker.com/engine/install/ubuntu/
# Caddy:                  https://caddyserver.com/docs/install
```

## 2. Claves de LiveKit

Genera un secret y elige una "api key" corta (ej. `kurug`):
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Pon el MISMO par en tres sitios:
- `chat-app/.env` → `LIVEKIT_API_KEY` y `LIVEKIT_API_SECRET`
- `deploy/livekit.yaml` → bajo `keys:` (`kurug: <secret>`)
- (el bot las toma del `.env`)

## 3. Construir la SPA

```bash
cd chat-app/web
npm install
npm run build            # genera web/dist (lo sirve Caddy)
```

## 4. Arrancar LiveKit (Docker)

Edita `deploy/livekit.yaml`: pon el `node_ip` correcto (ver red, abajo) y tu
secret. Luego:
```bash
cd chat-app/deploy
docker compose up -d
docker compose logs -f livekit      # comprueba que arranca
```

## 5. Backend y bot como servicios

```bash
# Backend (ajusta User/rutas dentro del archivo)
sudo cp deploy/minichat.service /etc/systemd/system/
# Bot (ajusta User/rutas; ya apunta LIVEKIT_URL a 127.0.0.1)
sudo cp deploy/kurug-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now minichat kurug-bot
journalctl -u kurug-bot -f          # ver que se conecta a LiveKit
```

## 6. La red: dos caminos

LiveKit necesita que **(a)** la señalización llegue por **wss** (mismo origen que
la app) y **(b)** su **media UDP** sea alcanzable desde cada dispositivo. Elige:

### Camino A — Tailscale (recomendado para los 10, sin abrir el router)
1. Instala Tailscale en el server y en los dispositivos de los 10
   (`https://tailscale.com/`); todos en la misma tailnet.
2. `node_ip` en `livekit.yaml` = la IP `100.x.y.z` del server en Tailscale
   (`tailscale ip -4`). El media viaja cifrado por el túnel, **sin tocar el router**.
3. HTTPS del mismo origen con **Tailscale Serve** (te da un dominio `*.ts.net`
   con certificado válido) o Caddy escuchando en la IP de la tailnet.
   - Con Serve, enruta `/` a Caddy o directamente a los puertos; lo más simple es
     dejar que Caddy sirva todo (Caddyfile) y Serve solo termine TLS.
4. `.env` → `LIVEKIT_URL=wss://<tu-nombre>.ts.net`.

Ventaja: nada de puertos en el router ni IP pública. Coste: cada uno instala
Tailscale una vez.

### Camino B — Dominio público + router (cualquiera con navegador)
1. Un dominio que apunte a tu IP pública (si es dinámica, usa DDNS).
2. En el router, **reenvía** al server:
   - TCP **80** y **443** (Caddy / Let's Encrypt).
   - TCP **7881** y UDP **50000-50200** (media de LiveKit).
3. `node_ip` en `livekit.yaml` = tu IP pública (o `use_external_ip: true`).
4. `ufw`:
   ```bash
   sudo ufw allow 80,443/tcp
   sudo ufw allow 7881/tcp
   sudo ufw allow 50000:50200/udp
   ```
5. `.env` → `LIVEKIT_URL=wss://kurug.tudominio.com`.

## 7. Caddy (HTTPS + unir todo)

Edita `deploy/Caddyfile` (dominio y ruta a `web/dist`) e instálalo:
```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl restart caddy
```
Caddy obtiene el certificado solo, sirve la SPA, y enruta `/auth …/ws` al backend
y `/rtc` a LiveKit. Tras cualquier cambio en `.env`, reinicia el backend
(`sudo systemctl restart minichat`).

## 8. Comprobar

- `https://tu-dominio` carga la app.
- Dos personas en **#general** → botón **Voz** → se oyen.
- En la pestaña **música**, añade una canción → suena en la voz de general.
- Si la voz "conecta" pero no hay audio: casi siempre es `node_ip` mal o los
  **puertos UDP** sin abrir (camino B) / Tailscale caído (camino A).

## Acceso de administración (tú, en remoto)

Instala Tailscale en el server y entra por **SSH sobre la tailnet** desde
cualquier sitio, sin abrir puertos:
```bash
ssh tu-usuario@<ip-tailscale-del-server>
```
Deploys = `git pull` + `sudo systemctl restart minichat kurug-bot` (y
`docker compose pull && up -d` para actualizar LiveKit). Activa "encender al
recuperar corriente" en la BIOS para que vuelva solo tras un apagón.

## Qué pedirle a tu amigo (dueño del server)
- **Subida de internet** decente y simétrica si puede (es el techo de calidad
  con 10 personas y vídeo).
- Permitir las **conexiones entrantes** que pida el sistema/Docker.
- Camino A: instalar Tailscale. Camino B: reenviar los puertos del router.
- Crearte un usuario con `sudo` para administrar en remoto.
