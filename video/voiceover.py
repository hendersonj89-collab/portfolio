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
    (3.2, "Moe-zay-ick Forest Management. Where innovation and stewardship meet."),
    (11.2, "We're redefining the forest economy. Forestry, renewable energy, watershed services, recreation, real estate, and carbon. "
           "One landscape, serving the public good."),
    (25.0, "In the Coke-sigh-la Watershed, we're piloting a new approach: longer growth periods, harvest designs that protect water, "
           "stronger stream protection and smaller road footprints, with seven hundred and fifteen hectares of older forest set aside."),
    (43.2, "It's why we're called Moe-zay-ick. Small patches on their own clocks, so the forest is never all one age, and never all one use."),
    (56.2, "And BC mills come first. Every log is offered to domestic manufacturers before export. "
           "Over sixty mills rely on Moe-zay-ick. Thirty of them, here on Vancouver Island."),
    (71.2, "Keeping fibre flowing to BC mills, forestry workers and contractors busy, and coastal communities strong."),
    (81.8, "Moe-zay-ick Forest Management. Innovation and stewardship meet here."),
]
SCENE_ENDS = [10.0, 24.0, 42.0, 55.0, 70.0, 80.0, 90.0]

def synth(voice, speed):
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(HERE, "tts", "kokoro-v1.0.onnx"), os.path.join(HERE, "tts", "voices-v1.0.bin"))
    lang = "en-gb" if voice.startswith("b") else "en-us"
    cues = []
    for (t0, txt), end in zip(CUES, SCENE_ENDS):
        s, sr = k.create(txt, voice=voice, speed=speed, lang=lang)
        s = signal.resample_poly(s, SR, sr).astype(np.float64)
        s = s / (np.max(np.abs(s)) + 1e-9)
        dur = len(s) / SR
        flag = "" if t0 + dur <= end - 0.4 else "   <-- runs past scene end!"
        print(f"  {t0:5.1f}s  {dur:5.1f}s  ends {t0 + dur:5.1f} / {end}{flag}")
        cues.append((t0, s))
    return cues

def voice_track(cues):
    n = int(90 * SR); v = np.zeros(n)
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
    ap.add_argument("--speed", type=float, default=0.95)
    ap.add_argument("--voice-gain", type=float, default=0.8)
    a = ap.parse_args()
    print(f"synthesising with {a.voice} @ {a.speed}")
    v = voice_track(synth(a.voice, a.speed))
    wavfile.write(os.path.join(OUT, "voice.wav"), SR, (v * 32767 * 0.9).astype(np.int16))
    sr, m = wavfile.read(os.path.join(OUT, "audio.wav")); m = m / 32768
    assert sr == SR and len(m) >= len(v)
    print("ducking")
    duck = duck_envelope(v)
    mix = m[: len(v)] * duck[:, None] + (v * a.voice_gain)[:, None]
    mix = np.tanh(mix * 1.05) / np.tanh(1.05)
    mix *= 0.92 / np.max(np.abs(mix))
    wavfile.write(os.path.join(OUT, "mix.wav"), SR, (mix * 32767).astype(np.int16))
    print("wrote out/voice.wav, out/mix.wav")

if __name__ == "__main__":
    main()
