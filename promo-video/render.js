// Renderiza index.html frame a frame e gera o MP4 via ffmpeg.
// Uso: node render.js                 -> out/felipe-leal-promo.mp4 (sem legenda/voz) + out/capa.png
//      node render.js --narrado       -> out/felipe-leal-promo-narrado.mp4 (legendas + out/narracao.wav)
//      node render.js --stills 1.2,5  -> PNGs de teste em out/stills/ (com legendas)
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
let chromium;
try { ({ chromium } = require('playwright')); } catch { ({ chromium } = require('/opt/node-tools/node_modules/playwright')); }

const FPS = 30, DURATION = 38, COVER_T = 37.5;
const OUT = path.join(__dirname, 'out');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'index.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => Promise.all([...document.fonts].map(f => f.load())));

  const narrado = process.argv.includes('--narrado');
  const shot = async (t, file, captions = true) => {
    await page.evaluate(([t, captions]) => window.render(t, { captions }), [t, captions]);
    return page.screenshot({ path: file, type: 'png' });
  };

  const si = process.argv.indexOf('--stills');
  if (si > -1) {
    const dir = path.join(OUT, 'stills'); fs.mkdirSync(dir, { recursive: true });
    for (const t of process.argv[si + 1].split(',').map(Number)) await shot(t, path.join(dir, `t${t.toFixed(2)}.png`));
    await browser.close(); return;
  }

  const mp4 = path.join(OUT, narrado ? 'felipe-leal-promo-narrado.mp4' : 'felipe-leal-promo.mp4');
  const audio = narrado ? ['-i', path.join(OUT, 'narracao.wav'), '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-shortest'] : [];
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    ...audio, '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-r', String(FPS),
    '-movflags', '+faststart', mp4], { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = FPS * DURATION;
  for (let i = 0; i < total; i++) {
    const buf = await shot(i / FPS, undefined, narrado);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 60 === 0) process.stdout.write(`frame ${i}/${total}\n`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  if (!narrado) await shot(COVER_T, path.join(OUT, 'capa.png'), false);
  await browser.close();
  console.log('ok ->', mp4);
})();
