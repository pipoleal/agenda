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

# (início, texto na legenda, texto falado — quando a pronúncia precisa de ajuda).
# Cada fala é sintetizada inteira (entonação natural); a velocidade fica entre 1,0 e 1,08
# para caber até o início da próxima fala.
SCRIPT = [
    (0.2, "Seu negócio tem site? Mas ele realmente vende por você?", None),
    (4.4, "Confuso, lento, desatualizado, com cara de rascunho?", None),
    (8.3, "Aí o cliente vai pro concorrente.", None),
    (10.3, "Eu sou o Felipe Leal, e levo seu site do rascunho ao sucesso.", None),
    (14.15, "Design responsivo, perfeito em qualquer tela.", "Dizáin responsivo, perfeito em qualquer tela."),
    (16.95, "Landing pages que transformam visitantes em clientes.", None),
    (20.25, "Identidade exclusiva, nada de template.", None),
    (23.1, "Tudo sob medida pro seu negócio.", None),
    (26.05, "Já fiz pra confeitaria, odontologia, projetos criativos e muito mais.", None),
    (30.4, "O próximo pode ser o seu!", None),
    (33.1, "Bora tirar sua ideia do papel? Me chama e peça seu orçamento!", None),
]
MAX_SPEED = 1.08


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


def chunks_of(text, pat=r"[,.?!:]$"):
    """Quebra o texto em trechos terminados em pontuação."""
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if re.search(pat, w):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def gaps_of(x, sr, min_gap=0.12):
    r, hop = rms_frames(x, sr)
    v = r > 0.012
    out, i = [], 0
    while i < len(v):
        if not v[i]:
            j = i
            while j < len(v) and not v[j]:
                j += 1
            if i > 0 and j < len(v) and (j - i) * hop >= min_gap:
                out.append((i * hop, j * hop))
            i = j
        else:
            i += 1
    return out


def synth(tts, text, speed):
    """Sintetiza a fala inteira de uma vez (sem cortes) e estima o tempo de cada palavra:
    pausas reais entre frases ancoram as frases; dentro delas, os trechos seguem a duração
    relativa de cada trecho sintetizado isolado, e as palavras, o número de sílabas."""
    a = tts.generate(text, sid=SID, speed=speed)
    sr = a.sample_rate
    x = trim(np.array(a.samples, dtype=np.float32), sr)
    D = len(x) / sr
    sents = chunks_of(text, r"[.?!]$")
    gaps = sorted(gaps_of(x, sr), key=lambda g: g[0] - g[1])[: len(sents) - 1]
    gaps = sorted(gaps) if len(gaps) == len(sents) - 1 else None
    # duração relativa de cada trecho (entre vírgulas) para distribuir o tempo
    rel = {}
    for ch in chunks_of(text):
        b = tts.generate(" ".join(ch), sid=SID, speed=speed)
        rel[" ".join(ch)] = len(trim(np.array(b.samples, dtype=np.float32), b.sample_rate)) / b.sample_rate
    sent_w = [sum(rel[" ".join(c)] for c in chunks_of(" ".join(s))) for s in sents]
    spans, t = [], 0.0
    for k, s_ in enumerate(sents):
        if gaps:
            end = gaps[k][0] if k < len(gaps) else D
        else:
            end = t + D * sent_w[k] / sum(sent_w)
        spans.append((t, end, s_))
        t = gaps[k][1] if gaps and k < len(gaps) else end
    words = []
    for a0, a1, s_ in spans:
        chs = chunks_of(" ".join(s_))
        tot = sum(rel[" ".join(c)] for c in chs)
        acc = a0
        for c in chs:
            d = (a1 - a0) * rel[" ".join(c)] / tot
            n = sum(syl(w) + .5 for w in c)
            for w in c:
                dw = d * (syl(w) + .5) / n
                words.append({"w": w, "t0": round(acc, 3), "t1": round(acc + dw, 3)})
                acc += dw
    return x, sr, words


def main():
    tts = kokoro()
    track = np.zeros(int(SR_OUT * DURATION), dtype=np.float32)
    caps = []
    for n, (start, shown, spoken) in enumerate(SCRIPT):
        say = spoken or shown
        slot = (SCRIPT[n + 1][0] if n + 1 < len(SCRIPT) else DURATION - .6) - start - .08
        x, sr, wt = synth(tts, say, 1.0)
        dur = len(x) / sr
        speed = 1.0
        if dur > slot:
            speed = min(MAX_SPEED, dur / slot)
            x, sr, wt = synth(tts, say, speed)
            dur = len(x) / sr
        # troca o texto falado pelo texto da legenda (mesmo número de palavras)
        for o, w in zip(wt, shown.split()):
            o["w"] = w
        y = np.interp(np.arange(int(len(x) * SR_OUT / sr)) * sr / SR_OUT, np.arange(len(x)), x).astype(np.float32)
        i0 = int(start * SR_OUT)
        track[i0: i0 + len(y)] += y[: len(track) - i0]
        caps.append({"t0": start, "t1": round(start + dur, 3),
                     "words": [{**o, "t0": round(start + o["t0"], 3), "t1": round(start + o["t1"], 3)} for o in wt]})
        print(f"{start:5.2f}s +{dur:4.2f}s (vel {speed:.2f}, espaço {slot:.2f}s{' ESTOURA' if dur > slot else ''})  {shown}")
    track /= max(1e-6, np.abs(track).max()) / 0.89
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    sf.write(os.path.join(HERE, "out", "narracao_raw.wav"), track, SR_OUT)
    with open(os.path.join(HERE, "captions.js"), "w") as f:
        f.write("window.CAPTIONS=" + json.dumps(caps, ensure_ascii=False) + ";\n")


if __name__ == "__main__":
    main()
