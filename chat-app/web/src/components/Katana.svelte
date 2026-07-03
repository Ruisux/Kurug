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
  <rect x="90" y="22" width="7" height="8.5" rx="1.5" fill="#9a9488" />

  <!-- Hoja: lomo (mune) RECTO (línea recta desde la guarda a la punta) y filo
       curvo abajo que sube hasta el kissaki. -->
  <path
    d="M97 20.6 L356 15.1 C315 18 200 23.4 97 29.2 Z"
    fill="#c7c0b3"
  />
  <!-- Yokote: línea corta que delimita la punta (kissaki). -->
  <path d="M344 15.4 L345.6 17.4" stroke="#8f887b" stroke-width="0.7" opacity="0.55" fill="none" />
  <!-- Shinogi: cresta recta junto al lomo. -->
  <path d="M100 21.8 L350 16.2" stroke="#efe9dc" stroke-width="0.5" opacity="0.4" fill="none" />
  <!-- Hamon: línea de temple junto al filo. -->
  <path
    d="M103 27.2 C200 22.6 300 18.4 349 15.6"
    stroke="#efe9dc"
    stroke-width="0.8"
    opacity="0.45"
    fill="none"
  />
</svg>
