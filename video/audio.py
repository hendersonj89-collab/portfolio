#!/usr/bin/env python3
"""
Procedural soundtrack, track B: felt-piano ostinato + strings, G major, 96 BPM,
building with bass and soft percussion, a written lead line, transition whooshes
timed to the scene cuts in render.py. Everything synthesised with numpy/scipy.

    python audio.py   -> out/audio.wav (48 kHz stereo)
"""
import math
import os

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
DUR = 60.0
N = int(SR * DUR)
BPM = 96.0
BEAT = 60.0 / BPM            # 0.625 s
BAR = 4 * BEAT               # 2.5 s
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CUTS = [7.0, 17.0, 29.0, 39.0, 49.0, 55.0]   # must match SCENES in render.py

rng = np.random.default_rng(7)

def hz(m): return 440.0 * 2 ** ((m - 69) / 12)

class Bus:
    def __init__(self): self.L = np.zeros(N); self.R = np.zeros(N)
    def add(self, sig, start, pan=0.0, gain=1.0):
        i0 = int(start * SR)
        if i0 >= N or i0 < 0: return
        sig = sig[: N - i0]; a = (pan + 1) / 2 * math.pi / 2
        self.L[i0:i0 + len(sig)] += sig * gain * math.cos(a)
        self.R[i0:i0 + len(sig)] += sig * gain * math.sin(a)

def lowpass(x, fc, order=4):
    return signal.sosfilt(signal.butter(order, fc / (SR / 2), "low", output="sos"), x)

def highpass(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc / (SR / 2), "high", output="sos"), x)

def bandpass(x, f0, f1, order=4):
    return signal.sosfilt(signal.butter(order, [f0 / (SR / 2), f1 / (SR / 2)], "band", output="sos"), x)

def env_adsr(n, a, d, s, r):
    e = np.ones(n); ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    if ai: e[:ai] = np.linspace(0, 1, ai)
    if di: e[ai:ai + di] = np.linspace(1, s, min(di, max(0, n - ai)))
    e[ai + di:] = s
    if ri and n > ri: e[-ri:] *= np.linspace(1, 0, ri)
    return e

# ----------------------------------------------------------------------------- harmony: G  Em  C  D  (5 s per chord)
PROG = [("G", 55, 4), ("Em", 52, 3), ("C", 48, 4), ("D", 50, 4)] * 2 + [("G", 55, 4), ("Em", 52, 3), ("C", 48, 4), ("G", 55, 4)]
CHORD_LEN = 2 * BAR

def chord_at(t): return PROG[min(int(t / CHORD_LEN), len(PROG) - 1)]

# ----------------------------------------------------------------------------- instruments
def piano(f, dur=2.2, vel=0.8):
    """felt piano: inharmonic partials, per-partial decay, soft hammer noise"""
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros(n); B = 0.00025
    for k in range(1, 9):
        fk = f * k * math.sqrt(1 + B * k * k)
        if fk > 18000: break
        amp = (1 / k ** (1.15 + (1 - vel) * 0.8))
        dec = (0.9 + 0.0009 * f) * (1 + 0.55 * (k - 1))
        out += amp * np.sin(2 * np.pi * fk * t + rng.uniform(0, 6)) * np.exp(-dec * t)
    out *= 1 - np.exp(-t * 2500)
    hammer = lowpass(rng.standard_normal(int(0.012 * SR)), 2500) * np.linspace(1, 0, int(0.012 * SR)) * 0.5 * vel
    out[: len(hammer)] += hammer
    out = lowpass(out, 3200 + 5000 * vel)
    return out / 2.2 * vel

def strings(f, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros(n)
    vib = 1 + 0.003 * np.sin(2 * np.pi * 4.6 * t + rng.uniform(0, 6)) * np.clip(t / 1.5, 0, 1)
    for dt in (-0.006, 0, 0.006):
        ph = 2 * np.pi * np.cumsum(f * (1 + dt) * vib) / SR
        for h in range(1, 11): out += np.sin(h * ph + rng.uniform(0, 6)) / h
    out = lowpass(out, 2200); out = highpass(out, 160)
    return out / 8 * env_adsr(n, 1.2, 0, 1, 1.4)

def lead(f, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    vib = 1 + 0.007 * np.sin(2 * np.pi * 5.0 * t) * np.clip((t - 0.2) / 0.5, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    out = np.sin(ph) + 0.45 * np.sin(2 * ph) + 0.18 * np.sin(3 * ph) + 0.08 * np.sin(4 * ph)
    out = lowpass(out, 3500)
    return out / 1.6 * env_adsr(n, 0.08, 0.25, 0.75, 0.3)

def kick(soft=1.0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = 48 + 90 * np.exp(-t * 22)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11) * soft

def shaker(accent=0.0):
    n = int(0.06 * SR); t = np.arange(n) / SR
    return highpass(rng.standard_normal(n), 5000) * np.exp(-t * (70 - 25 * accent)) * (0.5 + 0.5 * accent)

def snare():
    n = int(0.22 * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 30)
    return (bandpass(rng.standard_normal(n), 900, 5000) * np.exp(-t * 20) * 0.8 + body * 0.6)

def whoosh(dur=1.6):
    n = int(dur * SR); t = np.arange(n) / SR
    up = (t / (dur * 0.72)) ** 2.4
    env = np.where(t < dur * 0.72, up, np.exp(-(t - dur * 0.72) * 9))
    x = bandpass(rng.standard_normal(n), 300, 5000); xb = bandpass(rng.standard_normal(n), 2000, 12000)
    return (x * (1 - up * 0.6) + xb * up * 0.6) * env

def boom(dur=1.4, f0=55):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f0 * (1 + 0.7 * np.exp(-t * 9))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.8)

def reverb(x, t60=2.2, wet=0.28, damp=4000):
    n = int(t60 * SR); t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / t60); ir = lowpass(ir, damp); ir /= np.sqrt(np.sum(ir ** 2))
    return x + wet * signal.fftconvolve(x, ir)[: len(x)]

# ----------------------------------------------------------------------------- arrangement
music = Bus(); fx = Bus(); amb = Bus()

print("piano")
E = BEAT / 2
for i in range(int(DUR / E)):
    t = i * E
    name, root, third = chord_at(t)
    pat = [0, 7, 12, 12 + third, 19, 12 + third, 12, 7]
    k = i % 8
    m = root + pat[k] + (12 if (i // 16) % 4 == 3 and k in (2, 6) else 0)
    # intro: sparse (every other), full ostinato from the first cut
    if t < 7 and k % 2 == 1: continue
    if t >= 55 and k not in (0, 2, 4): continue
    vel = 0.85 if k == 0 else 0.55 + 0.2 * (k % 2 == 0) + 0.06 * rng.random()
    if t < 7: vel *= 0.8
    music.add(piano(hz(m), 2.4, vel), t + rng.uniform(-0.004, 0.004), pan=(m - 67) / 30, gain=0.34)
# left hand: bass octave on beat 1, fifth on beat 3
for bar in range(int(DUR / BAR)):
    t = bar * BAR; name, root, third = chord_at(t)
    music.add(piano(hz(root - 12), 3.0, 0.75), t, pan=-0.25, gain=0.30)
    if t >= 7: music.add(piano(hz(root - 5), 2.4, 0.55), t + 2 * BEAT, pan=-0.2, gain=0.22)

print("strings")
for ci, (name, root, third) in enumerate(PROG):
    t0 = ci * CHORD_LEN
    if t0 + CHORD_LEN <= 7: continue
    dur = CHORD_LEN + 1.6
    swell = 0.55 if t0 < 17 else 0.8 if t0 < 29 else 1.0
    for k, iv in enumerate([12, 12 + third, 19, 24]):
        music.add(strings(hz(root + iv), dur), t0, pan=(k - 1.5) * 0.4, gain=0.045 * swell)

print("bass")
for bar in range(int(DUR / BAR)):
    t = bar * BAR
    if t < 17 or t >= 55: continue
    name, root, third = chord_at(t)
    for beat, iv, g in ((0, 0, 1.0), (2, 0, 0.8), (3.5, 7, 0.55)):
        n = int(1.2 * BEAT * SR); tt = np.arange(n) / SR; f = hz(root - 24)
        b = (np.sin(2 * np.pi * f * hz(iv + 69) / 440 * tt) + 0.25 * np.sin(4 * np.pi * f * hz(iv + 69) / 440 * tt)) * env_adsr(n, 0.015, 0.25, 0.6, 0.25)
        music.add(lowpass(b, 300), t + beat * BEAT, gain=0.42 * g)

print("percussion")
for beat in range(int(DUR / BEAT)):
    t = beat * BEAT
    if t < 29 or t >= 55: continue
    build = 0.75 if t < 39 else 1.0
    music.add(kick(build), t, gain=0.55)
    if t >= 39 and beat % 2 == 1: music.add(snare(), t, gain=0.16)
    for s in range(4):
        music.add(shaker(accent=1.0 if s == 2 else 0.2), t + s * BEAT / 4, pan=0.35, gain=0.05 * build)

print("lead")
MELODY = [(64, 2, 79), (66, 1, 81), (67, 1, 83), (68, 3, 86), (72, 2, 83), (74, 1, 81), (75, 1, 79), (76, 3, 81),
          (80, 2, 79), (82, 1, 76), (83, 1, 79), (84, 3, 83), (88, 2, 81), (90, 1, 79), (91, 1, 78), (92, 4, 79)]
for (b, ln, m) in MELODY:
    music.add(lead(hz(m), ln * BEAT), b * BEAT, pan=0.15, gain=0.16)

print("transitions")
for c in CUTS:
    wl = whoosh(); wr = whoosh(); n = len(wl); pan = np.linspace(-0.8, 0.8, n)
    i0 = int((c - 1.15) * SR)
    fx.L[i0:i0 + n] += wl * 0.09 * (1 - pan) / 2 * 1.4; fx.R[i0:i0 + n] += wr * 0.09 * (1 + pan) / 2 * 1.4
    fx.add(boom(), c - 0.05, gain=0.30 if c < 55 else 0.42)
fx.add(boom(1.8, 48), 1.3, gain=0.35)   # wordmark lands

print("ambience")
def pink(n):
    return signal.lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400], rng.standard_normal(n))
t = np.arange(N) / SR
for buf, ph in ((amb.L, 0.0), (amb.R, 1.7)):
    w = bandpass(pink(N), 150, 2000)
    lfo = 0.55 + 0.45 * np.sin(2 * np.pi * 0.05 * t + ph) * np.sin(2 * np.pi * 0.013 * t + ph * 2)
    buf += w * np.clip(lfo, 0.1, 1.2) * 0.012

def chirp():
    sig = []
    for _ in range(rng.integers(2, 5)):
        d = rng.uniform(0.05, 0.11); n = int(d * SR); tt = np.arange(n) / SR
        f0 = rng.uniform(2600, 4600); f = f0 + (f0 * rng.uniform(0.7, 1.4) - f0) * (tt / d) ** 1.5
        sig += [np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(n), np.zeros(int(rng.uniform(0.04, 0.1) * SR))]
    return np.concatenate(sig)
for _ in range(14):
    tt = rng.uniform(0.5, 58.0)
    if any(abs(tt - c) < 1.2 for c in CUTS): continue
    amb.add(chirp(), tt, pan=rng.uniform(-0.9, 0.9), gain=rng.uniform(0.015, 0.03))

# ----------------------------------------------------------------------------- mix / master
print("mix")
L = reverb(music.L) + fx.L + amb.L
R = reverb(music.R) + fx.R + amb.R
mix = np.stack([L, R], 1)
# gentle bus compression via soft clip, then normalise
mix = np.tanh(mix * 1.1) / math.tanh(1.1)
mix *= 0.9 / np.max(np.abs(mix))
fi = int(0.3 * SR); mix[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(3.0 * SR); mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.4
os.makedirs(OUT, exist_ok=True)
wavfile.write(os.path.join(OUT, "audio.wav"), SR, (mix * 32767).astype(np.int16))
print("wrote", os.path.join(OUT, "audio.wav"))
