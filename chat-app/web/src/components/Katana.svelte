<script>
  // Katana decorativa (sumi-e), de izquierda a derecha:
  // pomo · mango con envoltura (ito) · guarda (tsuba) · hoja curva hasta la punta.
  export let width = "100%";
</script>

<svg
  viewBox="0 0 360 40"
  style="display:block;width:{width};height:auto;overflow:visible"
  aria-hidden="true"
>
  <rect x="13" y="20.5" width="11" height="11" rx="3" fill="#2a2018" />

  <rect x="24" y="20" width="58" height="12" rx="3" fill="#3a2d22" />
  <path
    d="M30 20 L40 32 M40 20 L50 32 M50 20 L60 32 M60 20 L70 32 M70 20 L80 32"
    stroke="var(--shu)"
    stroke-width="1.2"
    opacity="0.9"
    fill="none"
  />
  <path
    d="M40 20 L30 32 M50 20 L40 32 M60 20 L50 32 M70 20 L60 32 M80 20 L70 32"
    stroke="var(--shu)"
    stroke-width="1.2"
    opacity="0.55"
    fill="none"
  />
  <circle cx="53" cy="26" r="1.6" fill="var(--gold)" />

  <ellipse cx="86" cy="26" rx="3.4" ry="10.5" fill="var(--gold)" />
  <ellipse cx="86" cy="26" rx="1.4" ry="6" fill="#3a2d22" />
  <rect x="90" y="21.5" width="7" height="9" rx="1.5" fill="#9a9488" />

  <!-- Hoja: ancho CONSTANTE (gruesa) y CENTRADA en el mismo eje que el mango
       (y=26). Lomo (mune) recto y horizontal arriba, filo recto abajo; solo se
       afina en la punta (kissaki), donde el filo sube al lomo. -->
  <path
    d="M97 21.5 L333 21.5 L358 22.8 L333 30.5 L97 30.5 Z"
    fill="#c7c0b3"
  />
  <!-- Yokote: línea que separa la punta (kissaki) del resto de la hoja. -->
  <path d="M333 21.5 L333 30.5" stroke="#8f887b" stroke-width="0.8" opacity="0.55" fill="none" />
  <!-- Shinogi: cresta recta junto al lomo. -->
  <path d="M101 23 L329 23" stroke="#efe9dc" stroke-width="0.5" opacity="0.4" fill="none" />
  <!-- Hamon: línea de temple recta junto al filo. -->
  <path d="M104 28.6 L329 28.6" stroke="#efe9dc" stroke-width="0.8" opacity="0.4" fill="none" />
</svg>
