# App de escritorio (Tauri): build, logo y auto-actualización

La app de escritorio empaqueta la SPA y se **auto-actualiza** (botón "Actualizar
y reiniciar") tirando de **GitHub Releases**. Atajos globales y notificaciones
nativas ya están cableados.

## Logo
El icono se genera desde `src-tauri/icon-source.png` (anillo dorado + 刃). Para
regenerar todo el set tras cambiarlo:
```
cd chat-app/web
npx tauri icon src-tauri/icon-source.png
```

## A qué servidor apunta la app
La app empaquetada NO tiene proxy, así que hay que decirle dónde está el servidor
al **compilar**, con la variable `VITE_KURUG_SERVER` (tu MagicDNS de Tailscale):
```
# macOS/Linux
VITE_KURUG_SERVER=https://kurug-pc.tuTailnet.ts.net npm run desktop:build
# Windows (PowerShell)
$env:VITE_KURUG_SERVER="https://kurug-pc.tuTailnet.ts.net"; npm run desktop:build
```
En desarrollo (`npm run desktop`) no hace falta: usa el proxy de Vite.

> Pendiente conocido: las imágenes/avatares se sirven como rutas `/static/...`.
> Para que se vean en el binario hay que prefijarlas con `VITE_KURUG_SERVER`
> (helper `mediaUrl`). Texto, voz, música y archivos ya usan la base correcta.
> Pídemelo y lo remato (son ~4 componentes con `<img>`).

## Firma del updater (una sola vez)
Tauri firma cada actualización; la app solo instala binarios con tu firma.
```
cd chat-app/web
npm run tauri signer generate -- -w "$HOME/.tauri/kurug.key"
```
- Imprime una **clave pública**: pégala en `src-tauri/tauri.conf.json` →
  `plugins.updater.pubkey`.
- Guarda el archivo `kurug.key` (privado) y su **contraseña** a buen recaudo.

## Publicar una versión (auto-update)
1. Crea un repo en GitHub (puede ser privado) y sube el proyecto.
2. En `src-tauri/tauri.conf.json`, en `plugins.updater.endpoints`, pon
   `https://github.com/TU_USUARIO/TU_REPO/releases/latest/download/latest.json`.
3. En GitHub → Settings → Secrets → Actions, añade:
   - `TAURI_SIGNING_PRIVATE_KEY` = contenido del archivo `kurug.key`
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` = su contraseña
4. Sube la versión y una etiqueta:
   ```
   # sube la versión en src-tauri/tauri.conf.json y package.json, luego:
   git tag v0.1.1 && git push --tags
   ```
   El workflow `.github/workflows/release.yml` compila Windows/Mac/Linux,
   los firma y publica el release con `latest.json`.
5. Reparte el instalador **una vez**. A partir de ahí, cuando publiques una
   etiqueta nueva, a cada uno le saldrá el banner **"Actualización disponible →
   Actualizar y reiniciar"**.

## Atajos globales y selector de pantalla
- Los atajos de silenciar/ensordecer son **globales** en la app (plugin
  `global-shortcut`); se configuran en Ajustes de audio.
- El selector de compartir pantalla es el **nativo del sistema** (Tauri no
  permite uno propio; eso es exclusivo de Electron).
