"""Gera a narração (voz neural local, sherpa-onnx/Kokoro) e as legendas sincronizadas.

Uso: python3 narration.py <pasta-dos-modelos> [sid]
  sid 43 = pm_alex (masculina, padrão) · 42 = pf_dora (feminina) · 44 = pm_santa
Saída: out/narracao.wav e captions.js (lido pelo index.html).
"""
import json, os, re, sys
import numpy as np, soundfile as sf
import sherpa_onnx as so

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = sys.argv[1]
SID = int(sys.argv[2]) if len(sys.argv) > 2 else 43
SR_OUT, DURATION = 48000, 38.0

# (início, fim máximo, texto na legenda, texto falado — quando a pronúncia precisa de ajuda)
SCRIPT = [
    (0.25, 3.9, "Seu negócio tem site? Mas ele realmente vende por você?", None),
    (4.45, 7.6, "Confuso, lento, desatualizado... com cara de rascunho.", None),
    (8.35, 10.15, "E o cliente vai pro concorrente.", None),
    (10.15, 12.6, "Eu sou o Felipe Leal: sites sob medida.", None),
    (12.65, 14.1, "Do rascunho ao sucesso.", None),
    (14.2, 17.05, "Design responsivo: perfeito em qualquer tela.", "Dizáin responsivo: perfeito em qualquer tela."),
    (17.15, 20.1, "Landing pages que convertem visitantes em clientes.", None),
    (20.15, 23.1, "Identidade exclusiva. Nada de template.", None),
    (23.2, 25.95, "Tudo sob medida pro seu negócio.", None),
    (26.05, 30.3, "Já fiz para confeitaria, odontologia, projetos criativos e muito mais.", None),
    (30.5, 32.9, "O próximo pode ser o seu!", None),
    (33.15, 37.3, "Bora tirar sua ideia do papel? Me chama e peça seu orçamento!", None),
]


def kokoro():
    d = os.path.join(MODELS, "kokoro-multi-lang-v1_0")
    cfg = so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(
        kokoro=so.OfflineTtsKokoroModelConfig(
            model=f"{d}/model.onnx", voices=f"{d}/voices.bin", tokens=f"{d}/tokens.txt",
            data_dir=f"{d}/espeak-ng-data", dict_dir=f"{d}/dict", lexicon=f"{d}/lexicon-us-en.txt", lang="pt-br"),
        num_threads=4))
    return so.OfflineTts(cfg)


def rms_frames(x, sr, hop=0.01):
    h = int(sr * hop)
    n = len(x) // h
    return np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(1)), hop


def trim(x, sr, thr=0.01):
    r, hop = rms_frames(x, sr)
    on = np.where(r > thr)[0]
    a, b = on[0], on[-1] + 1
    return x[max(0, int((a - 4) * hop * sr)): int((b + 2) * hop * sr)]


def syl(w):
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõà]+", w.lower())))


def chunks_of(text):
    """Quebra o texto em trechos terminados em pontuação."""
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if re.search(r"[,.?!:]$|\.\.\.$", w):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def pause_after(word):
    return 0.07 if word.endswith((",", ":")) else 0.18


def synth(tts, text, speed):
    """Sintetiza trecho a trecho: devolve o áudio e o tempo de cada palavra
    (início/fim exatos por trecho; dentro do trecho, proporcional às sílabas)."""
    parts, words, t = [], [], 0.0
    chs = chunks_of(text)
    for k, ch in enumerate(chs):
        a = tts.generate(" ".join(ch), sid=SID, speed=speed)
        sr = a.sample_rate
        x = trim(np.array(a.samples, dtype=np.float32), sr)
        d = len(x) / sr
        tot = sum(syl(w) for w in ch)
        acc = t
        for w in ch:
            dw = d * syl(w) / tot
            words.append({"w": w, "t0": round(acc, 3), "t1": round(acc + dw, 3)})
            acc += dw
        parts.append(x)
        t += d
        if k < len(chs) - 1:
            gap = pause_after(ch[-1]) / speed
            parts.append(np.zeros(int(gap * sr), dtype=np.float32))
            t += gap
    return np.concatenate(parts), sr, words


def main():
    tts = kokoro()
    track = np.zeros(int(SR_OUT * DURATION), dtype=np.float32)
    caps = []
    for start, limit, shown, spoken in SCRIPT:
        say = spoken or shown
        slot = limit - start
        speed = 1.0
        for _ in range(4):
            x, sr, wt = synth(tts, say, speed)
            dur = len(x) / sr
            if dur <= slot or speed >= 1.22:
                break
            speed = min(1.22, speed * dur / slot * 1.03)
        # troca o texto falado pelo texto da legenda (mesmo número de palavras)
        for o, w in zip(wt, shown.split()):
            o["w"] = w
        y = np.interp(np.arange(int(len(x) * SR_OUT / sr)) * sr / SR_OUT, np.arange(len(x)), x).astype(np.float32)
        i0 = int(start * SR_OUT)
        track[i0: i0 + len(y)] += y[: len(track) - i0]
        caps.append({"t0": start, "t1": round(start + dur, 3),
                     "words": [{**o, "t0": round(start + o["t0"], 3), "t1": round(start + o["t1"], 3)} for o in wt]})
        print(f"{start:5.2f}s +{dur:4.2f}s (vel {speed:.2f}, limite {slot:.2f}s)  {shown}")
    track /= max(1e-6, np.abs(track).max()) / 0.89
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    sf.write(os.path.join(HERE, "out", "narracao_raw.wav"), track, SR_OUT)
    with open(os.path.join(HERE, "captions.js"), "w") as f:
        f.write("window.CAPTIONS=" + json.dumps(caps, ensure_ascii=False) + ";\n")


if __name__ == "__main__":
    main()
