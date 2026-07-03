# Experimentos con `additionalBrowserArgs` (WebView2 / Windows)

Objetivo: intentar **quitar la barra flotante "está compartiendo su pantalla ·
dejar de presentar / ocultar"** que pinta el WebView2 (Chromium) durante el
screen share en la app de escritorio.

## Aviso honesto

- Esa barra es un **indicador de seguridad de Chromium** pensado para NO poder
  ocultarse fácilmente. **Es muy probable que ninguna bandera la quite.**
- El **selector de fuente** ("elige qué compartir") es obligatorio y no se quita.
- Esto **no se puede verificar desde el Mac**; hay que probarlo en Windows con
  `npm run desktop`. Si no funciona, se revierte sin consecuencias.

## Dónde se configura

En `tauri.conf.json` → `app.windows[0].additionalBrowserArgs`.

⚠️ Al definir esta clave se **reemplazan** los args por defecto de Tauri, por eso
SIEMPRE hay que conservar el bloque base:

```
--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection
```

Valor actual (base, sin experimento): equivale a lo que Tauri pone por defecto,
así que no cambia nada todavía. Es el punto de partida para experimentar.

## Cómo probar cada candidato

1. Edita `additionalBrowserArgs` con UNO de los valores de abajo.
2. `cd chat-app/web && npm run desktop`.
3. Comparte pantalla y observa si la barra sigue apareciendo.
4. Si no mejora, vuelve al valor base (revertir) y prueba el siguiente.

Revertir = dejar solo el valor base:
```json
"additionalBrowserArgs": "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection"
```

## Candidatos

### A) Saltarse el SELECTOR de fuente (efecto seguro, pero invasivo)
Auto-selecciona una fuente por su título, sin mostrar el selector. Puede que al
no ser una captura "iniciada por el usuario" cambie o quite la barra. **Contra:**
comparte SIEMPRE esa fuente (pierdes elegir ventana concreta). Ajusta el título
al idioma/monitor ("Entire screen", "Pantalla completa", "Screen 1"…).

```json
"additionalBrowserArgs": "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection --auto-select-desktop-capture-source=Entire screen"
```

### B) Desactivar features de captura (tiro a ciegas)
No hay un nombre de feature público y fiable para la barra; esto es prueba y
error. Se añaden nombres a la lista `--disable-features`. Si Chromium no reconoce
el nombre, simplemente lo ignora (no rompe nada). Candidatos a añadir:

```json
"additionalBrowserArgs": "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection,MediaStreamNotificationBar"
```
(otros nombres que se pueden probar añadiendo: `GlobalMediaControls`,
`DesktopCaptureMacV2`; casi con seguridad no aplican, pero son inocuos si no
existen).

### C) Sin experimento (recomendado si A y B no funcionan)
Deja el valor base. La barra seguirá, pero es lo estable y limpio.

## Conclusión esperada

Lo más probable es que el candidato **A** sea el único que produzca algún cambio
(porque cambia CÓMO se inicia la captura), a costa de perder el selector. Si eso
no te compensa, quédate con **C**.
