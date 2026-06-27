# Mini Chat — backend en FastAPI

Chat propio, liviano y auto-hospedado. MVP funcional con:

- Registro y login de usuarios (contraseñas con bcrypt, sesiones con JWT)
- Canales (crear / listar)
- Mensajería en tiempo real por WebSocket con broadcast por canal
- Persistencia en base de datos (SQLite por defecto, Postgres opcional)
- Cliente web mínimo para probar todo desde el navegador

## Stack

FastAPI · SQLAlchemy 2.0 · Pydantic v2 · WebSockets · SQLite/PostgreSQL

## Estructura

```
chat-app/
├── app/
│   ├── main.py          # arranca la app y conecta los routers
│   ├── config.py        # configuración (lee .env)
│   ├── database.py      # motor y sesión de SQLAlchemy
│   ├── models.py        # tablas: User, Channel, Message
│   ├── schemas.py       # validación de entrada/salida (Pydantic)
│   ├── security.py      # hashing de contraseñas + JWT
│   ├── deps.py          # dependencias: sesión de BD, usuario actual
│   ├── ws_manager.py    # gestor de conexiones WebSocket (broadcast)
│   └── routers/
│       ├── auth.py      # /auth/register, /auth/login
│       ├── channels.py  # /channels, /channels/{id}/messages
│       └── ws.py        # /ws/{channel_id}  (WebSocket)
└── static/
    └── index.html       # cliente de prueba
```

## Cómo correrlo

```bash
cd chat-app
python -m venv .venv && source .venv/bin/activate   # opcional pero recomendado
pip install -r requirements.txt
cp .env.example .env        # SECRET_KEY es OBLIGATORIA, ver abajo
alembic upgrade head        # crea/actualiza el esquema de la BD
uvicorn app.main:app --reload
```

El esquema lo gestiona **Alembic**, no la app. Tras clonar o tras cambiar los
modelos, corre `alembic upgrade head`. Para crear una nueva migración después de
editar `app/models.py`:

```bash
alembic revision --autogenerate -m "describe el cambio"
alembic upgrade head
```

`SECRET_KEY` debe ser una cadena propia: la app **no arranca** con el valor
placeholder ni vacío. Genera una con:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Tests

```bash
pytest -q
```

Abre **http://localhost:8000** en dos pestañas (o dos navegadores), regístrate
con dos usuarios distintos, crea un canal y verás los mensajes en vivo en ambas.

La documentación interactiva de la API está en **http://localhost:8000/docs**.

## Pasar a PostgreSQL

1. `pip install "psycopg[binary]"`
2. En `.env`:
   `DATABASE_URL=postgresql+psycopg://usuario:password@localhost:5432/chatdb`

No hay que tocar más código.

## Qué sigue (roadmap)

Ordenado de más fácil/útil a más difícil:

1. **Migraciones con Alembic** — para cambiar el esquema sin borrar la BD.
2. **Lista de usuarios conectados** por canal (presencia) — el `ConnectionManager`
   ya sabe quién está; solo hay que emitir eventos de "entró/salió".
3. **Mensajes directos (DMs)** — reutiliza la lógica de canales con un canal
   privado entre dos usuarios.
4. **Bot de música** — un proceso aparte que se conecta como un cliente más;
   escucha comandos tipo `!play <url>` y responde. La reproducción de audio real
   en una sala de voz depende del punto 6.
5. **Roles y permisos** — quién puede crear canales, borrar mensajes, etc.
6. **Voz y compartir pantalla** — la parte pesada. NO se escribe a mano:
   - Grupo pequeño: WebRTC peer-to-peer; este servidor solo hace de señalización
     (intercambia "ofertas/respuestas" SDP por WebSocket, que ya tienes montado).
   - Salas grandes: integrar un SFU ya hecho como **LiveKit** o **mediasoup**.

## Notas técnicas

- El `ConnectionManager` vive en memoria: funciona con un solo proceso. Para
  escalar a varias instancias necesitarás Redis Pub/Sub.
- La sesión de BD del WebSocket dura toda la conexión. Para producción con
  muchos usuarios conviene revisar ese patrón (abrir/cerrar por mensaje o usar
  un pool async con SQLAlchemy async).
