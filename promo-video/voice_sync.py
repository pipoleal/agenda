"""Encaixa uma narração gravada (voz real) nas cenas do vídeo e gera as legendas.

Uso: python3 voice_sync.py <gravacao.m4a>
Saída: out/narracao.wav e captions.js (lido pelo index.html).

Cada fala é recortada da gravação (início/fim em segundos), limpa e posicionada no
tempo da cena. Trechos com mais de um pedaço têm as pausas longas encurtadas.
"""
import json, os, re, subprocess, sys, tempfile
import numpy as np, soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SR, DURATION = 48000, 38.0

# Tratamento: tira ruído de fundo e grave de manuseio, suaviza "s", dá presença e nivela.
CLEAN = ("highpass=f=80,afftdn=nf=-44:nr=12:tn=1,deesser=i=0.35,"
         "equalizer=f=300:t=q:w=1:g=-2,equalizer=f=3200:t=q:w=1.2:g=2,"
         "acompressor=threshold=-21dB:ratio=2.5:attack=6:release=140")

# (pedaços [(início, fim)] na gravação, posição no vídeo, velocidade, texto da legenda)
CLIPS = [
    ([(0.62, 3.80)], 0.5, 1.0, "Seu negócio tem site? Mas ele realmente vende por você?"),
    ([(4.25, 7.38)], 4.25, 1.0, "Confuso, lento, desatualizado, com cara de rascunho?"),
    ([(7.58, 9.64)], 8.25, 1.0, "Aí o cliente vai para o concorrente."),
    ([(10.01, 13.45)], 10.35, 1.0, "Eu sou Felipe Leal e levo o seu site do rascunho ao sucesso."),
    ([(13.71, 16.84)], 14.0, 1.0, "Design responsivo, perfeito em qualquer tela."),
    ([(17.02, 20.24)], 17.2, 1.0, "Landing pages que transformam visitantes em clientes."),
    ([(20.32, 23.26)], 20.48, 1.0, "Identidade exclusiva, nada de template."),
    ([(23.51, 25.56)], 23.5, 1.0, "Tudo sob medida para o seu negócio."),
    ([(25.73, 28.46), (29.72, 31.70)], 25.75, 1.08, "Já fiz para confeitaria, odontologia, projetos criativos e muito mais."),
    ([(31.74, 33.10)], 30.42, 1.0, "O próximo pode ser o seu!"),
    ([(33.56, 35.02)], 33.15, 1.0, "Bora tirar sua ideia do papel?"),
    ([(35.11, 36.88)], 34.8, 1.0, "Me chama e peça seu orçamento!"),
]
JOIN_GAP = 0.2  # pausa entre pedaços de uma mesma fala


def ffmpeg_af(x, af):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        sf.write(a, x, SR)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", a, "-af", af, "-ar", str(SR), "-ac", "1", b], check=True)
        return sf.read(b, dtype="float32")[0]


def fade(x, ms=15):
    n = min(len(x) // 2, int(SR * ms / 1000))
    x = x.copy()
    x[:n] *= np.linspace(0, 1, n)
    x[-n:] *= np.linspace(1, 0, n)
    return x


def rms_db(x, hop=0.01):
    h = int(SR * hop)
    n = len(x) // h
    return 20 * np.log10(np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(1)) + 1e-9)


def syl(w):
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõà]+", w.lower())))


def word_times(x, text):
    """Tempo de cada palavra: pausas reais ancoram os trechos entre pontuações
    (quando o número bate); dentro de cada trecho, proporcional às sílabas."""
    r = rms_db(x)
    on = np.where(r > -40)[0]
    a, b = on[0] / 100, (on[-1] + 1) / 100
    quiet = r < -40
    gaps, i = [], on[0]
    while i < on[-1]:
        if quiet[i]:
            j = i
            while j < on[-1] and quiet[j]:
                j += 1
            if j - i >= 10:
                gaps.append((i / 100, j / 100))
            i = j
        else:
            i += 1
    chunks, cur = [], []
    for w in text.split():
        cur.append(w)
        if re.search(r"[,.?!:]$", w):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    sel = sorted(sorted(gaps, key=lambda g: g[0] - g[1])[: len(chunks) - 1])
    if len(sel) != len(chunks) - 1:
        chunks, sel = [text.split()], []
    out, t = [], a
    for k, ch in enumerate(chunks):
        end = sel[k][0] if k < len(sel) else b
        tot = sum(syl(w) + .5 for w in ch)
        acc = t
        for w in ch:
            d = (end - t) * (syl(w) + .5) / tot
            out.append({"w": w, "t0": round(acc, 3), "t1": round(acc + d, 3)})
            acc += d
        t = sel[k][1] if k < len(sel) else end
    return out


def main():
    src = sys.argv[1]
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "src.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ac", "1", "-ar", str(SR), "-af", CLEAN, wav], check=True)
        voice = sf.read(wav, dtype="float32")[0]
    track = np.zeros(int(SR * DURATION), dtype=np.float32)
    caps, prev_end = [], 0.0
    for pieces, at, tempo, text in CLIPS:
        parts = []
        for k, (a, b) in enumerate(pieces):
            parts.append(fade(voice[int(a * SR): int(b * SR)]))
            if k < len(pieces) - 1:
                parts.append(np.zeros(int(JOIN_GAP * SR), dtype=np.float32))
        x = np.concatenate(parts)
        if tempo != 1.0:
            x = fade(ffmpeg_af(x, f"atempo={tempo}"))
        dur = len(x) / SR
        assert at >= prev_end - 1e-6, f"sobreposição em '{text}' ({at:.2f} < {prev_end:.2f})"
        i0 = int(at * SR)
        track[i0: i0 + len(x)] += x[: len(track) - i0]
        caps.append({"t0": at, "t1": round(at + dur, 3),
                     "words": [{**w, "t0": round(at + w["t0"], 3), "t1": round(at + w["t1"], 3)} for w in word_times(x, text)]})
        prev_end = at + dur
        print(f"{at:5.2f}s → {prev_end:5.2f}s  {text}")
    track = ffmpeg_af(track, "loudnorm=I=-16:TP=-1.5:LRA=9")[: len(track)]
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    sf.write(os.path.join(HERE, "out", "narracao.wav"), track, SR)
    with open(os.path.join(HERE, "captions.js"), "w") as f:
        f.write("window.CAPTIONS=" + json.dumps(caps, ensure_ascii=False) + ";\n")


if __name__ == "__main__":
    main()
