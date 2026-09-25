#!/usr/bin/env python3
"""
Voice-over for the spot: Kokoro neural TTS (offline, ONNX), one cue per scene, timed to
SCENES in render.py. Then mixes with out/audio.wav, ducking the music under the voice.

    python voiceover.py             # -> out/voice.wav, out/mix.wav
    python voiceover.py --voice bm_george --speed 0.9

Model files (not committed, ~350 MB):
  tts/kokoro-v1.0.onnx  tts/voices-v1.0.bin
  from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
"""
import argparse
import os

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SR = 48000

# (start time, text) — timed to the 90 s cut; each line must finish inside its scene
CUES = [
    (2.4, "Every log has to travel from the stump to the road. How it gets there depends on the ground, and it shapes the cost of every cubic metre."),
    (12.4, "On gentle slopes, we harvest from the ground. A feller-buncher cuts and bunches the trees. A skidder drags them to the roadside, "
          "where a processor bucks them to length and a loader fills the truck. Machines drive to the tree, so cycles are short and the cost per cubic metre is low."),
    (34.4, "On steep ground, machines can't drive to the tree, so the tree comes to the machine. A cable yarder stands on the road, a skyline runs down to an anchor, "
           "and a carriage pulls each turn of logs uphill. It takes a bigger crew, each cycle is longer, and the cost per cubic metre is higher."),
    (59.4, "Tethered harvesting stretches ground-based logging onto slopes that used to need a yarder, or a hand faller. "
           "An anchor on the road keeps a winch line tight, giving a feller-buncher the traction to work the slope, cutting each tree and laying it in a bunch. "
           "A tethered skidder then drags the bunch up to the road, where it's bucked and loaded as before. Safer than hand falling, but more machines to own and move."),
    (87.4, "Here's the challenge. Each turn on the yarder costs about the same, whether it carries three large logs or eight small ones. "
           "As piece size drops, so do the cubic metres per turn, and the cost of every cubic metre climbs."),
    (112.4, "Moving is expensive too. A yarder travels by lowbed, and a move can take days. Wages, equipment payments and insurance keep running while no logs are produced. "
            "Smaller blocks mean more moves, and every move comes straight out of a contractor's margin."),
    (132.4, "Connected machines change the picture. Live data on production, hours, fuel and location lets us plan blocks and moves together, cut idle time, "
            "match the right machine to the right ground, and pay contractors on accurate numbers."),
    (154.0, "Better data. Better decisions. Stronger contractors."),
    (158.4, "Mosaic Forest Management."),
]
SCENE_ENDS = [11.0, 33.0, 58.0, 86.0, 111.0, 131.0, 153.0, 161.0, 161.0]
PRONOUNCE = {"Mosaic": "moʊzˈeɪɪk", "Koksilah": "kˈoʊksaɪlə", "contractors": "kˈɑːntɹæktɚz"}   # IPA overrides

def synth(voice, speed):
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(HERE, "tts", "kokoro-v1.0.onnx"), os.path.join(HERE, "tts", "voices-v1.0.bin"))
    lang = "en-gb" if voice.startswith("b") else "en-us"
    # the phonemizer gets these wrong (Mosaic -> "muh-SAY-ik"), so patch the phoneme string
    fixes = {w: (k.tokenizer.phonemize(w, lang=lang).strip(), ipa) for w, ipa in PRONOUNCE.items()}
    cues = []
    for (t0, txt), end in zip(CUES, SCENE_ENDS):
        ph = k.tokenizer.phonemize(txt, lang=lang)
        for w, (bad, good) in fixes.items(): ph = ph.replace(bad, good)
        s, sr = k.create(ph, voice=voice, speed=speed, lang=lang, is_phonemes=True)
        s = signal.resample_poly(s, SR, sr).astype(np.float64)
        s = s / (np.max(np.abs(s)) + 1e-9)
        dur = len(s) / SR
        flag = "" if t0 + dur <= end - 0.4 else "   <-- runs past scene end!"
        print(f"  {t0:5.1f}s  {dur:5.1f}s  ends {t0 + dur:5.1f} / {end}{flag}")
        cues.append((t0, s))
    return cues

def voice_track(cues):
    n = int(161 * SR); v = np.zeros(n)
    for t0, s in cues:
        i0 = int(t0 * SR); s = s[: n - i0]
        v[i0:i0 + len(s)] += s
    # broadcast-ish chain: gentle high-pass, presence lift, soft limiter
    v = signal.sosfilt(signal.butter(2, 80 / (SR / 2), "high", output="sos"), v)
    pres = signal.sosfilt(signal.butter(2, [2500 / (SR / 2), 6000 / (SR / 2)], "band", output="sos"), v)
    v = v + 0.12 * pres
    return v / np.max(np.abs(v))

def duck_envelope(v, depth_db=-9.0, attack=0.08, release=0.9):
    """1.0 when the voice is silent, depth when it speaks; smoothed attack/release"""
    env = np.abs(signal.hilbert(v)) if len(v) < 2 ** 22 else np.abs(v)
    env = signal.sosfilt(signal.butter(1, 20 / (SR / 2), "low", output="sos"), env)
    gate = (env > 0.02).astype(float)
    out = np.zeros_like(gate); g = 0.0
    a = 1 / (attack * SR); r = 1 / (release * SR)
    for i in range(len(gate)):  # one-pole follower
        target = gate[i]
        g += (target - g) * (a if target > g else r)
        out[i] = g
    depth = 10 ** (depth_db / 20)
    return 1 - out * (1 - depth)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--voice-gain", type=float, default=0.8)
    a = ap.parse_args()
    print(f"synthesising with {a.voice} @ {a.speed}")
    v = voice_track(synth(a.voice, a.speed))
    wavfile.write(os.path.join(OUT, "harvest_voice.wav"), SR, (v * 32767 * 0.9).astype(np.int16))
    sr, m = wavfile.read(os.path.join(OUT, "harvest_audio.wav")); m = m / 32768
    assert sr == SR and len(m) >= len(v)
    print("ducking")
    duck = duck_envelope(v)
    mix = m[: len(v)] * duck[:, None] + (v * a.voice_gain)[:, None]
    mix = np.tanh(mix * 1.05) / np.tanh(1.05)
    mix *= 0.92 / np.max(np.abs(mix))
    wavfile.write(os.path.join(OUT, "harvest_mix.wav"), SR, (mix * 32767).astype(np.int16))
    print("wrote out/harvest_voice.wav, out/harvest_mix.wav")

if __name__ == "__main__":
    main()
