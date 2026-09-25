#!/usr/bin/env python3
"""
Procedural soundtrack for the harvest explainer (track C arrangement, 150 s). Warm string ensemble on slow
chords, sub drone, sparse marimba motif, soft pulse, low taiko hits and a shimmer
layer that build across the 90 s cut, leaving room for the voice-over.
F major, 72 BPM. Everything synthesised with numpy/scipy.

    python audio.py   -> out/audio.wav (48 kHz stereo)
"""
import math
import os

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
DUR = 153.0
N = int(SR * DUR)
BPM = 72.0
BEAT = 60.0 / BPM            # 0.8333 s
BAR = 4 * BEAT               # 3.333 s
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CUTS = [11.0, 33.0, 58.0, 78.0, 103.0, 123.0, 145.0]   # must match SCENES in render_harvest.py

rng = np.random.default_rng(3)

def hz(m): return 440.0 * 2 ** ((m - 69) / 12)

class Bus:
    def __init__(self): self.L = np.zeros(N); self.R = np.zeros(N)
    def add(self, sig, start, pan=0.0, gain=1.0):
        i0 = int(start * SR)
        if i0 >= N or i0 < 0: return
        sig = sig[: N - i0]; a = (pan + 1) / 2 * math.pi / 2
        self.L[i0:i0 + len(sig)] += sig * gain * math.cos(a)
        self.R[i0:i0 + len(sig)] += sig * gain * math.sin(a)

def lowpass(x, fc, order=4): return signal.sosfilt(signal.butter(order, fc / (SR / 2), "low", output="sos"), x)
def highpass(x, fc, order=2): return signal.sosfilt(signal.butter(order, fc / (SR / 2), "high", output="sos"), x)
def bandpass(x, f0, f1, order=4): return signal.sosfilt(signal.butter(order, [f0 / (SR / 2), f1 / (SR / 2)], "band", output="sos"), x)

def env_adsr(n, a, d, s, r):
    e = np.ones(n); ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    if ai: e[:ai] = np.linspace(0, 1, ai) ** 1.5
    if di: e[ai:ai + di] = np.linspace(1, s, min(di, max(0, n - ai)))
    e[ai + di:] = s
    if ri and n > ri: e[-ri:] *= np.linspace(1, 0, ri) ** 1.5
    return e

# ----------------------------------------------------------------------------- harmony: Fmaj7  Am7  Dm7  Bbmaj7   (7.5 s each)
# (name, chord tones as midi)
PROG = [("Fmaj7", [53, 57, 60, 64]), ("Am7", [57, 60, 64, 67]), ("Dm7", [50, 57, 60, 65]), ("Bbmaj7", [46, 53, 57, 62])] * 5 + [("Fmaj7", [53, 57, 60, 64])]
CHORD_LEN = 7.5

def chord_at(t): return PROG[min(int(t / CHORD_LEN), len(PROG) - 1)]

# ----------------------------------------------------------------------------- instruments
def strings(f, dur, voices=5, bright=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros(n)
    for v in range(voices):
        dt = (v - (voices - 1) / 2) * 0.0045
        vib = 1 + 0.0035 * np.sin(2 * np.pi * (4.2 + 0.4 * v) * t + rng.uniform(0, 6)) * np.clip(t / 2.0, 0, 1)
        ph = 2 * np.pi * np.cumsum(f * (1 + dt) * vib) / SR
        for h in range(1, 12): out += np.sin(h * ph + rng.uniform(0, 6)) / h ** 1.1
    out = lowpass(out, 1800 * bright); out = highpass(out, 120)
    out *= 0.5 / (np.max(np.abs(out)) + 1e-9)
    return out * env_adsr(n, 2.2, 0, 1, 2.6)

def marimba(f, dur=1.2, vel=0.7):
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.sin(2 * np.pi * f * t) * np.exp(-t * 5) + 0.35 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 14) + 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 30)
    out *= 1 - np.exp(-t * 3000)
    return out / 1.4 * vel

def shimmer(f, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * 5.5 * t + rng.uniform(0, 6))
    ph = 2 * np.pi * np.cumsum(f * (1 + 0.002 * np.sin(2 * np.pi * 0.3 * t))) / SR
    out = (np.sin(ph) + 0.5 * np.sin(2 * ph + 1) + 0.25 * np.sin(3 * ph + 2)) * trem
    return highpass(out, 800) / 1.7 * env_adsr(n, 3.0, 0, 1, 3.0)

def sub(f, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.15 * np.sin(2 * np.pi * f * 2 * t)) * env_adsr(n, 1.5, 0, 1, 2.0)

def taiko(big=1.0):
    n = int(0.9 * SR); t = np.arange(n) / SR
    f = 52 + 80 * np.exp(-t * 14)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5)
    skin = lowpass(rng.standard_normal(n), 900) * np.exp(-t * 28) * 0.6
    return (tone + skin) * big

def pulse():
    n = int(0.25 * SR); t = np.arange(n) / SR
    return lowpass(bandpass(rng.standard_normal(n), 200, 1200), 1400) * np.exp(-t * 26)

def cello(f, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.0 * t) * np.clip((t - 0.3) / 0.6, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    out = np.zeros(n)
    for h in range(1, 14): out += np.sin(h * ph + rng.uniform(0, 6)) / h
    out = lowpass(out, 1400)
    return out / 4 * env_adsr(n, 0.35, 0.2, 0.85, 0.5)

def whoosh(dur=1.7):
    n = int(dur * SR); t = np.arange(n) / SR
    up = (t / (dur * 0.72)) ** 2.4
    env = np.where(t < dur * 0.72, up, np.exp(-(t - dur * 0.72) * 9))
    x = bandpass(rng.standard_normal(n), 250, 4000); xb = bandpass(rng.standard_normal(n), 1500, 9000)
    return (x * (1 - up * 0.6) + xb * up * 0.6) * env

def boom(dur=1.6, f0=50):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f0 * (1 + 0.7 * np.exp(-t * 8))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)

def reverb(x, t60=3.2, wet=0.35, damp=3500):
    n = int(t60 * SR); t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / t60); ir = lowpass(ir, damp); ir /= np.sqrt(np.sum(ir ** 2))
    return x + wet * signal.fftconvolve(x, ir)[: len(x)]

# ----------------------------------------------------------------------------- arrangement
music = Bus(); fx = Bus(); amb = Bus()

print("strings + sub")
for ci, (name, tones) in enumerate(PROG):
    t0 = ci * CHORD_LEN; dur = CHORD_LEN + 2.8
    level = 0.7 if t0 < 11 else 0.8 if t0 < 58 else 0.9 if t0 < 123 else 1.0
    if t0 >= 145: level = 0.7
    bright = 0.8 if t0 < 33 else 1.0 if t0 < 123 else 1.15
    for k, m in enumerate(tones):
        music.add(strings(hz(m + 12), dur, bright=bright), t0, pan=(k - 1.5) * 0.45, gain=0.13 * level)
    if t0 >= 11: music.add(strings(hz(tones[0]), dur, voices=3, bright=0.7), t0, pan=0, gain=0.11 * level)   # low octave
    if t0 >= 33: music.add(sub(hz(tones[0] - 12), dur), t0, gain=0.11 * level)
    if t0 >= 123 and t0 < 145:
        for k, m in enumerate(tones[1:3]): music.add(shimmer(hz(m + 24), dur), t0, pan=(k - 0.5) * 0.8, gain=0.02)

print("marimba motif")
E = BEAT / 2
motif = [0, 2, 1, 3, 2, 3, 1, 2]   # indices into chord tones, rising then falling
for i in range(int(DUR / E)):
    t = i * E
    if t < 11 or t >= 145: continue
    name, tones = chord_at(t)
    k = i % 8
    if t < 33 and k % 2 == 1: continue            # sparse at first
    if t < 78 and k in (5, 7): continue
    m = tones[motif[k]] + 24
    vel = 0.8 if k == 0 else 0.45 + 0.25 * rng.random()
    music.add(marimba(hz(m), 1.2, vel), t + rng.uniform(-0.006, 0.006), pan=(m - 78) / 24, gain=0.16)

print("pulse + taiko")
for beat in range(int(DUR / BEAT)):
    t = beat * BEAT
    if 33 <= t < 145:
        for s in (0, 0.5):
            music.add(pulse(), t + s * BEAT, pan=0.2 if s else -0.2, gain=0.09 * (0.6 if t < 78 else 1.0) * (1.0 if s == 0 else 0.55))
    if 78 <= t < 145 and beat % 4 == 0:
        music.add(taiko(1.0 if t >= 123 else 0.7), t, gain=0.42)
    if 123 <= t < 145 and beat % 4 == 2:
        music.add(taiko(0.5), t, gain=0.3)
# rolls into the later cuts
for c in (103.0, 123.0, 145.0):
    for k in range(8):
        tt = c - 1.6 + k * 0.2
        music.add(taiko(0.35 + 0.08 * k), tt, gain=0.25)

print("cello line")
CELLO = [(0, 3, 65), (3, 1, 64), (4, 4, 60), (8, 3, 62), (11, 1, 64), (12, 4, 65), (16, 2, 67), (18, 2, 69), (20, 4, 65), (24, 3, 62), (27, 1, 60), (28, 4, 57)]
for (b, ln, m) in CELLO:
    music.add(cello(hz(m), ln * BEAT), 123.0 + b * BEAT, pan=-0.15, gain=0.13)

print("transitions")
for c in CUTS:
    wl = whoosh(); wr = whoosh(); n = len(wl); pan = np.linspace(-0.8, 0.8, n)
    i0 = int((c - 1.2) * SR)
    fx.L[i0:i0 + n] += wl * 0.07 * (1 - pan) / 2 * 1.4; fx.R[i0:i0 + n] += wr * 0.07 * (1 + pan) / 2 * 1.4
    fx.add(boom(), c - 0.05, gain=0.32 if c < 145 else 0.45)
fx.add(boom(2.0, 45), 1.3, gain=0.35)   # wordmark lands

print("ambience")
def pink(n):
    return signal.lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400], rng.standard_normal(n))
t = np.arange(N) / SR
for buf, ph in ((amb.L, 0.0), (amb.R, 1.7)):
    w = bandpass(pink(N), 150, 2000)
    lfo = 0.55 + 0.45 * np.sin(2 * np.pi * 0.05 * t + ph) * np.sin(2 * np.pi * 0.013 * t + ph * 2)
    buf += w * np.clip(lfo, 0.1, 1.2) * 0.014

def chirp():
    sig = []
    for _ in range(rng.integers(2, 5)):
        d = rng.uniform(0.05, 0.11); n = int(d * SR); tt = np.arange(n) / SR
        f0 = rng.uniform(2600, 4600); f = f0 + (f0 * rng.uniform(0.7, 1.4) - f0) * (tt / d) ** 1.5
        sig += [np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(n), np.zeros(int(rng.uniform(0.04, 0.1) * SR))]
    return np.concatenate(sig)
for _ in range(30):
    tt = rng.uniform(0.5, 151.0)
    if any(abs(tt - c) < 1.2 for c in CUTS): continue
    amb.add(chirp(), tt, pan=rng.uniform(-0.9, 0.9), gain=rng.uniform(0.015, 0.03))

# ----------------------------------------------------------------------------- mix / master
print("mix")
L = reverb(music.L) + fx.L + amb.L
R = reverb(music.R) + fx.R + amb.R
mix = np.stack([L, R], 1)
mix = np.tanh(mix * 1.1) / math.tanh(1.1)
mix *= 0.9 / np.max(np.abs(mix))
fi = int(0.3 * SR); mix[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(3.5 * SR); mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.4
os.makedirs(OUT, exist_ok=True)
wavfile.write(os.path.join(OUT, "harvest_audio.wav"), SR, (mix * 32767).astype(np.int16))
print("wrote", os.path.join(OUT, "harvest_audio.wav"))
