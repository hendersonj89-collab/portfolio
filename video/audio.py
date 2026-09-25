#!/usr/bin/env python3
"""
Procedural soundtrack for the Mosaic Forest Management spot.
Everything is synthesised with numpy/scipy: warm pad, additive plucks, a written
lead melody, sub bass + heartbeat, pink-noise wind, birds, and transition whooshes
timed to the scene cuts in render.py.

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
BPM = 80.0
BEAT = 60.0 / BPM          # 0.75 s
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CUTS = [7.0, 17.0, 29.0, 39.0, 49.0, 55.0]   # must match SCENES in render.py

rng = np.random.default_rng(42)
L = np.zeros(N); R = np.zeros(N)

def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)

def add(buf_l, buf_r, sig, start, pan=0.0, gain=1.0):
    """mix mono sig into L/R at time start (s); pan -1..1 (equal power)"""
    i0 = int(start * SR)
    if i0 >= N: return
    sig = sig[: N - i0]
    a = (pan + 1) / 2 * math.pi / 2
    buf_l[i0:i0 + len(sig)] += sig * gain * math.cos(a)
    buf_r[i0:i0 + len(sig)] += sig * gain * math.sin(a)

def env_adsr(n, a, d, s, r):
    e = np.ones(n)
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    if ai: e[:ai] = np.linspace(0, 1, ai)
    if di: e[ai:ai + di] = np.linspace(1, s, min(di, max(0, n - ai)))
    e[ai + di:] = s
    if ri and n > ri: e[-ri:] *= np.linspace(1, 0, ri)
    return e

def lowpass(x, fc, order=4):
    sos = signal.butter(order, fc / (SR / 2), "low", output="sos")
    return signal.sosfilt(sos, x)

def bandpass(x, f0, f1, order=4):
    sos = signal.butter(order, [f0 / (SR / 2), f1 / (SR / 2)], "band", output="sos")
    return signal.sosfilt(sos, x)

# ----------------------------------------------------------------------------- harmony
# 20 bars, chord changes every 2 bars. D major: D  Bm  G  A  | D  Bm  G  A | D  D
CHORDS = {
    "D": [50, 57, 61, 64, 66],      # D A C# E F#  (Dmaj9-ish)
    "Bm": [47, 54, 57, 62, 66],     # B F# A D F#
    "G": [43, 50, 54, 59, 66],      # G D F# B F#
    "A": [45, 52, 57, 61, 64],      # A E A C# E
}
PROG = ["D", "Bm", "G", "A", "D", "Bm", "G", "A", "D", "D"]
CHORD_LEN = 8 * BEAT   # 6 s

def chord_at(t):
    return PROG[min(int(t / CHORD_LEN), len(PROG) - 1)]

# ----------------------------------------------------------------------------- pad
def pad_note(f, dur, detune=0.004):
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros(n)
    vib = 1 + 0.0025 * np.sin(2 * np.pi * 0.23 * t + rng.uniform(0, 6))
    for dt in (-detune, 0, detune):
        ff = f * (1 + dt) * vib
        ph = 2 * np.pi * np.cumsum(ff) / SR
        for h in range(1, 7):
            out += np.sin(h * ph + rng.uniform(0, 6)) / h ** 1.4
    return out / 6

print("pad")
for ci, name in enumerate(PROG):
    t0 = ci * CHORD_LEN
    dur = CHORD_LEN + 2.5 if ci < len(PROG) - 1 else DUR - t0
    for k, m in enumerate(CHORDS[name]):
        sig = pad_note(hz(m), dur)
        e = env_adsr(len(sig), 1.8 if ci else 3.0, 0.0, 1.0, 2.4)
        # gentle swell across the chord
        e *= 0.85 + 0.15 * np.sin(np.linspace(0, math.pi, len(sig)))
        add(L, R, sig * e, t0, pan=(-0.5 + k / 4) * 0.7, gain=0.085)
# darken pad
L[:] = lowpass(L, 1500); R[:] = lowpass(R, 1500)
pad_l, pad_r = L.copy(), R.copy()
L[:] = 0; R[:] = 0

# ----------------------------------------------------------------------------- pluck / arpeggio
def pluck(f, dur=0.9, bright=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros(n)
    for h in range(1, 8):
        dec = 2.2 + h * 1.6 * (2 - bright)
        out += np.sin(2 * np.pi * f * h * t) * np.exp(-dec * t) / h ** 1.1
    out *= 1 - np.exp(-t * 900)      # click-free attack
    return out / 3

def density(t):
    if t < 8: return 0.0
    if t < 19: return 0.45
    if t < 30: return 0.65
    if t < 56: return 0.85
    return 0.0

print("arpeggio")
step = BEAT / 2
prev_idx = 2
for i in range(int(DUR / step)):
    t = i * step
    d = density(t)
    if d == 0 or rng.random() > d: continue
    tones = CHORDS[chord_at(t)]
    idx = int(np.clip(prev_idx + rng.choice([-2, -1, -1, 1, 1, 2]), 0, len(tones) - 1))
    prev_idx = idx
    m = tones[idx] + 24 + (12 if rng.random() < 0.18 else 0)
    vel = 0.9 if i % 4 == 0 else 0.55 + 0.25 * rng.random()
    add(L, R, pluck(hz(m), 1.1), t, pan=(m - 78) / 20, gain=0.16 * vel)

# ----------------------------------------------------------------------------- lead melody (written)
MELODY = [  # (start beat, length beats, midi)
    (9, 2, 81), (11, 1, 78), (12, 3, 74),
    (17, 2, 79), (19, 1, 81), (20, 3, 83),
    (25, 2, 81), (27, 1, 85), (28, 4, 76),
    (33, 2, 78), (35, 1, 81), (36, 4, 86),
    (41, 2, 83), (43, 1, 81), (44, 3, 78),
    (49, 1.5, 79), (50.5, 1.5, 81), (52, 2, 83), (54, 2, 86),
    (57, 2, 88), (59, 1, 85), (60, 4, 81),
    (65, 2, 78), (67, 1, 76), (68, 5, 74),
]

def lead(f, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.2 * t) * np.clip((t - 0.25) / 0.6, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    out = np.sin(ph) + 0.28 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
    breath = bandpass(rng.standard_normal(n), f * 0.9, f * 3.5) * 0.06
    out = (out + breath) * env_adsr(n, 0.12, 0.2, 0.8, 0.35)
    return out / 1.4

print("lead")
for (b, ln, m) in MELODY:
    add(L, R, lead(hz(m), ln * BEAT), b * BEAT, pan=0.1, gain=0.13)

# ----------------------------------------------------------------------------- bass + heartbeat
print("bass / heartbeat")
for bar in range(20):
    t0 = bar * 4 * BEAT
    if t0 < 19 - 0.01 or t0 >= 56: continue
    root = CHORDS[chord_at(t0)][0] - 12
    for beat in (0, 2):
        tt = t0 + beat * BEAT
        n = int(1.4 * BEAT * SR); t = np.arange(n) / SR
        b = np.sin(2 * np.pi * hz(root) * t) + 0.15 * np.sin(2 * np.pi * hz(root) * 2 * t)
        b *= env_adsr(n, 0.02, 0.3, 0.55, 0.3)
        add(L, R, b, tt, gain=0.20 if beat == 0 else 0.13)
    # heartbeat kick on beat 1, softer on beat 2.5 (lub-dub)
    for off, g in ((0.0, 0.5), (0.5 * BEAT, 0.28)):
        n = int(0.45 * SR); t = np.arange(n) / SR
        f = 42 + 70 * np.exp(-t * 18)
        k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
        add(L, R, k, t0 + off, gain=g)

# ----------------------------------------------------------------------------- transitions
print("whooshes")
def whoosh(dur=1.1):
    n = int(dur * SR); t = np.arange(n) / SR
    x = bandpass(rng.standard_normal(n), 400, 6000)
    up = (t / (dur * 0.7)) ** 2.2
    env = np.where(t < dur * 0.7, up, np.exp(-(t - dur * 0.7) * 14))
    # sweep the tone up by cross-fading a brighter band in
    xb = bandpass(rng.standard_normal(n), 2000, 12000)
    return (x * (1 - up * 0.6) + xb * up * 0.6) * env

def boom(dur=1.2, f0=60):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f0 * (1 + 0.8 * np.exp(-t * 10))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)

for c in CUTS:
    wl = whoosh(); wr = whoosh()
    n = len(wl); pan = np.linspace(-0.8, 0.8, n)
    i0 = int((c - 0.75) * SR)
    L[i0:i0 + n] += wl * 0.11 * (1 - pan) / 2 * 1.4
    R[i0:i0 + n] += wr * 0.11 * (1 + pan) / 2 * 1.4
    add(L, R, boom(), c - 0.05, gain=0.35 if c < 56 else 0.5)

# title reveal hit + shimmer chord at 2.4 s, final chord shimmer at 56.6 s
add(L, R, boom(1.6, 50), 2.35, gain=0.45)
for k, m in enumerate([74, 78, 81, 86, 90]):
    add(L, R, pluck(hz(m), 2.5, bright=1.3), 2.45 + k * 0.06, pan=(k - 2) / 3, gain=0.10)
    add(L, R, pluck(hz(m), 3.5, bright=1.3), 56.6 + k * 0.07, pan=(k - 2) / 3, gain=0.11)

# ----------------------------------------------------------------------------- reverb on the musical bus
print("reverb")
def reverb(x, t60=1.6, wet=0.22):
    n = int(t60 * SR); t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / t60)
    ir = lowpass(ir, 4500); ir /= np.sqrt(np.sum(ir ** 2))
    return x + wet * signal.fftconvolve(x, ir)[: len(x)]

L[:] = reverb(L); R[:] = reverb(R)
L += pad_l; R += pad_r

# ----------------------------------------------------------------------------- ambience: wind + birds
print("ambience")
def pink(n):
    w = rng.standard_normal(n)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    return signal.lfilter(b, a, w)

t = np.arange(N) / SR
for buf, ph in ((L, 0.0), (R, 1.7)):
    w = bandpass(pink(N), 120, 2200)
    lfo = 0.55 + 0.45 * np.sin(2 * np.pi * 0.05 * t + ph) * np.sin(2 * np.pi * 0.013 * t + ph * 2)
    lfo += 0.25 * lowpass(rng.standard_normal(N), 0.5) * 30
    buf += w * np.clip(lfo, 0.1, 1.5) * 0.018

def chirp():
    notes = rng.integers(2, 6); sig = []
    for _ in range(notes):
        d = rng.uniform(0.05, 0.12); n = int(d * SR); tt = np.arange(n) / SR
        f0 = rng.uniform(2400, 4600); f1 = f0 * rng.uniform(0.7, 1.4)
        f = f0 + (f1 - f0) * (tt / d) ** 1.5
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(n)
        gap = np.zeros(int(rng.uniform(0.04, 0.12) * SR))
        sig += [s, gap]
    return np.concatenate(sig)

for _ in range(26):
    tt = rng.uniform(1.0, 54.0)
    if any(abs(tt - c) < 0.9 for c in CUTS): continue
    add(L, R, chirp(), tt, pan=rng.uniform(-0.9, 0.9), gain=rng.uniform(0.02, 0.045))

# ----------------------------------------------------------------------------- master
print("master")
mix = np.stack([L, R], 1)
mix = np.tanh(mix * 1.15) / math.tanh(1.15)
mix *= 0.89 / np.max(np.abs(mix))
fi = int(0.4 * SR); mix[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(2.6 * SR); mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
os.makedirs(OUT, exist_ok=True)
wavfile.write(os.path.join(OUT, "audio.wav"), SR, (mix * 32767).astype(np.int16))
print("wrote", os.path.join(OUT, "audio.wav"))
