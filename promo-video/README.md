# Vídeo de divulgação — Felipe Leal · Sites sob medida

Motion graphics 1080×1920 (9:16), 30 fps, 38 s, sem áudio.

- `index.html` — animação inteira em HTML/CSS/JS; cada frame é função do tempo `render(t)`.
  - Prévia ao vivo: abra `index.html?play` no navegador.
  - Frame específico: `index.html?t=12.5`.
- `render.js` — captura os frames com Playwright/Chromium e codifica com ffmpeg.
  - `node render.js` → `out/felipe-leal-promo.mp4` + `out/capa.png` (frame em 37,5 s)
  - `node render.js --stills 3.5,20,37.5` → PNGs de teste em `out/stills/`
- `fonts/` — Space Mono e Quicksand (SIL Open Font License, via Fontsource).

Zona segura respeitada: nada importante nos 250 px de cima, 350 px de baixo e 120 px da direita.
