# Vídeo de divulgação — Felipe Leal · Sites sob medida

Motion graphics 1080×1920 (9:16), 30 fps, 38 s, sem áudio.

- `index.html` — animação inteira em HTML/CSS/JS; cada frame é função do tempo `render(t)`.
  - Prévia ao vivo: abra `index.html?play` no navegador.
  - Frame específico: `index.html?t=12.5`.
- `render.js` — captura os frames com Playwright/Chromium e codifica com ffmpeg.
  - `node render.js` → `out/felipe-leal-promo.mp4` (sem voz/legenda) + `out/capa.png` (frame em 37,5 s)
  - `node render.js --narrado` → `out/felipe-leal-promo-narrado.mp4` (legendas + narração)
  - `node render.js --stills 3.5,20,37.5` → PNGs de teste em `out/stills/`
- `narration.py` — gera a narração com voz neural local (sherpa-onnx + Kokoro, voz pt-BR `pm_alex`)
  e o `captions.js` com o tempo de cada palavra (legenda com a palavra falada em destaque).
  - `pip install sherpa-onnx soundfile numpy`; modelo `kokoro-multi-lang-v1_0` dos releases do sherpa-onnx (tts-models).
  - `python3 narration.py <pasta-dos-modelos> [sid]` (43 = masculina, 42 = feminina), depois masterizar:
    `ffmpeg -i out/narracao_raw.wav -af "highpass=f=75,equalizer=f=180:t=q:w=1:g=2,equalizer=f=6500:t=q:w=1.5:g=-2.5,acompressor=threshold=-20dB:ratio=2:attack=8:release=150,aecho=0.9:0.7:17|31:0.07|0.04,loudnorm=I=-16:TP=-1.5:LRA=9" -ar 48000 -ac 1 out/narracao.wav`
  - Prévia sem legenda: `index.html?play&nocap`.
- `fonts/` — Space Mono e Quicksand (SIL Open Font License, via Fontsource).

Zona segura respeitada: nada importante nos 250 px de cima, 350 px de baixo e 120 px da direita.
