#!/usr/bin/env python3
"""
Mosaic Forest Management — 60s motion-graphics spot (brand v2: light, contour lines, Jost).
Rendered entirely in code: numpy + scipy + contourpy + pycairo, encoded with ffmpeg.

    python render.py                 # full 1080p30 render -> out/video.mp4
    python render.py --stills 0 90   # dump PNG stills for given frame numbers
    python render.py --scale 0.5     # quick low-res render
"""
import argparse
import math
import os
import subprocess
from multiprocessing import Pool

import cairo
import contourpy
import numpy as np
from scipy.spatial import Voronoi

W, H = 1920, 1080
FPS = 30
DUR = 60.0
NFRAMES = int(DUR * FPS)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ----------------------------------------------------------------------------- palette (from mosaicforests.com)
def hexc(s, a=1.0):
    s = s.lstrip("#")
    return (int(s[0:2], 16) / 255, int(s[2:4], 16) / 255, int(s[4:6], 16) / 255, a)

C = dict(
    white=hexc("#ffffff"), paper=hexc("#f7f6f2"), paper2=hexc("#efede6"),
    taupe=hexc("#a9a596"), taupe2=hexc("#9a9686"), contour=hexc("#d3d0c4"),
    navy=hexc("#1c2b3f"), ink=hexc("#2a2f33"), grey=hexc("#6b6f70"), mute=hexc("#9aa0a0"),
    aqua=hexc("#6ccfd4"), aqua2=hexc("#2fb0aa"), lime=hexc("#b8d45c"), green=hexc("#4f9d3c"),
    green2=hexc("#2e7d4f"), forest=hexc("#1f5a3a"), water=hexc("#bfe0e4"), water2=hexc("#8fcdd3"),
    earth=hexc("#c9b895"), amber=hexc("#e2a85a"),
)
GRAD = [C["aqua"], C["lime"], C["aqua2"], C["green"]]   # the site's step gradient

def lerp(a, b, t): return a + (b - a) * t
def lerpc(c1, c2, t): return tuple(lerp(a, b, t) for a, b in zip(c1, c2))
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x

def gradc(t):
    """colour along the brand gradient, t in [0,1]"""
    t = clamp(t) * (len(GRAD) - 1); i = min(int(t), len(GRAD) - 2)
    return lerpc(GRAD[i], GRAD[i + 1], t - i)

# ----------------------------------------------------------------------------- easing
def ease_out_cubic(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_in_out(t): t = clamp(t); return t * t * (3 - 2 * t)
def ease_out_expo(t): t = clamp(t); return 1 if t >= 1 else 1 - 2 ** (-10 * t)
def ease_out_back(t, s=1.7):
    t = clamp(t); t -= 1
    return 1 + t * t * ((s + 1) * t + s)
def seg(t, t0, t1): return clamp((t - t0) / (t1 - t0)) if t1 > t0 else float(t >= t0)

def hsh(i, j=0, k=0):
    n = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791)
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0

# ----------------------------------------------------------------------------- textures / fields
_TEX = {}

def _value_noise(shape, cells, rng):
    h, w = shape
    g = rng.random((cells + 2, cells * 2 + 2))
    ys = np.linspace(0, cells, h, endpoint=False); xs = np.linspace(0, cells * 2, w, endpoint=False)
    iy = np.floor(ys).astype(int); ix = np.floor(xs).astype(int)
    fy = ys - iy; fx = xs - ix; fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
    a = g[np.ix_(iy, ix)]; b = g[np.ix_(iy, ix + 1)]; c = g[np.ix_(iy + 1, ix)]; d = g[np.ix_(iy + 1, ix + 1)]
    return (a * (1 - fx) + b * fx) * (1 - fy[:, None]) + (c * (1 - fx) + d * fx) * fy[:, None]

def make_textures():
    if _TEX: return
    rng = np.random.default_rng(11)
    shape = (108, 192)
    f = np.zeros(shape)
    for cells, amp in [(3, 1.0), (6, 0.5), (12, 0.22), (24, 0.08)]:
        f += _value_noise(shape, cells, rng) * amp
    f = (f - f.min()) / (f.max() - f.min())
    _TEX["field"] = f
    _TEX["field2"] = f.copy()
    xs = np.linspace(0, W, shape[1]); ys = np.linspace(0, H, shape[0])
    _TEX["cg"] = contourpy.contour_generator(x=xs, y=ys, z=f, line_type="Separate")
    # grain
    gr = []
    for k in range(3):
        v = (rng.random((270, 480)) * 255).astype(np.uint8)
        garr = np.dstack([v, v, v, np.full_like(v, 255)]).copy()
        gr.append((garr, cairo.ImageSurface.create_for_data(memoryview(garr), cairo.FORMAT_ARGB32, 480, 270, 480 * 4)))
    _TEX["grain"] = gr

def contours(ctx, t, color, alpha=1.0, levels=14, width=1.3, reveal=1.0, drift=1.0, ox=0.0, oy=0.0):
    """topographic contour lines; reveal wipes them in left->right, drift breathes the levels"""
    make_textures()
    cg = _TEX["cg"]
    ctx.save(); ctx.set_line_width(width); ctx.set_line_join(cairo.LINE_JOIN_ROUND); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.translate(ox, oy)
    if reveal < 1:
        ctx.rectangle(-ox, -oy, W * ease_in_out(reveal) * 1.05, H); ctx.clip()
    for k in range(levels):
        lv = (k + 0.5) / levels + 0.012 * math.sin(t * 0.25 * drift + k)
        if not 0 < lv < 1: continue
        for line in cg.lines(lv):
            if len(line) < 3: continue
            ctx.move_to(line[0, 0], line[0, 1])
            for p in line[1:]: ctx.line_to(p[0], p[1])
        ctx.set_source_rgba(color[0], color[1], color[2], alpha)
        ctx.stroke()
    ctx.restore()

# ----------------------------------------------------------------------------- cairo helpers
def set_col(ctx, c, a=None):
    ctx.set_source_rgba(c[0], c[1], c[2], c[3] if a is None else a)

def font(ctx, fam="Jost Light"):
    ctx.select_font_face(fam, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)

def text_width(ctx, s, tracking=0.0):
    if tracking == 0: return ctx.text_extents(s).x_advance
    return sum(ctx.text_extents(ch).x_advance for ch in s) + tracking * (len(s) - 1)

def text(ctx, s, x, y, size, color, fam="Jost Light", align="left", tracking=0.0, alpha=1.0):
    font(ctx, fam); ctx.set_font_size(size)
    w = text_width(ctx, s, tracking)
    if align == "center": x -= w / 2
    elif align == "right": x -= w
    set_col(ctx, color, color[3] * alpha)
    if tracking == 0:
        ctx.move_to(x, y); ctx.show_text(s)
    else:
        for ch in s:
            ctx.move_to(x, y); ctx.show_text(ch)
            x += ctx.text_extents(ch).x_advance + tracking
    ctx.new_path()
    return w

def reveal_text(ctx, s, x, y, size, color, p, **kw):
    if p <= 0: return
    e = ease_out_cubic(p)
    ctx.save(); ctx.translate(0, (1 - e) * size * 0.4)
    kw["alpha"] = kw.get("alpha", 1.0) * e
    text(ctx, s, x, y, size, color, **kw)
    ctx.restore()

def eyebrow(ctx, s, x, y, p, color=None, size=17):
    """small tracked uppercase label with a short rule"""
    if p <= 0: return
    color = color or C["aqua2"]
    e = ease_out_cubic(p)
    set_col(ctx, color, e); ctx.rectangle(x, y - 6, 34 * e, 2); ctx.fill()
    text(ctx, s.upper(), x + 46, y, size, color, fam="Jost Medium", tracking=4.5, alpha=e)

def rrect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0); ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi); ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()

def vgrad(stops, x0=0, y0=0, x1=0, y1=H):
    g = cairo.LinearGradient(x0, y0, x1, y1)
    for o, c in stops: g.add_color_stop_rgba(o, *c)
    return g

def glow(ctx, x, y, r, c, a=1.0):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, c[0], c[1], c[2], a); g.add_color_stop_rgba(0.45, c[0], c[1], c[2], a * 0.35); g.add_color_stop_rgba(1, c[0], c[1], c[2], 0)
    ctx.set_source(g); ctx.new_path(); ctx.arc(x, y, r, 0, 2 * math.pi); ctx.fill()

def vignette(ctx, a=0.16):
    g = cairo.RadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 1.0)
    g.add_color_stop_rgba(0, 0.2, 0.18, 0.12, 0); g.add_color_stop_rgba(1, 0.2, 0.18, 0.12, a)
    ctx.set_source(g); ctx.paint()

def grain(ctx, frame, a=0.035):
    make_textures()
    arr, surf = _TEX["grain"][frame % 3]
    pat = cairo.SurfacePattern(surf); pat.set_extend(cairo.EXTEND_REPEAT)
    m = cairo.Matrix(); m.scale(0.5, 0.5); m.translate(hsh(frame, 9) * 300, hsh(frame, 10) * 300)
    pat.set_matrix(m); pat.set_filter(cairo.FILTER_NEAREST)
    ctx.save(); ctx.set_operator(cairo.OPERATOR_SOFT_LIGHT); ctx.set_source(pat); ctx.paint_with_alpha(a); ctx.restore()

def paper_bg(ctx, t, contour_alpha=0.9, reveal=1.0):
    ctx.set_source(vgrad([(0, C["white"]), (1, C["paper"])])); ctx.paint()
    contours(ctx, t, C["contour"], contour_alpha, reveal=reveal)

def taupe_bg(ctx, t, reveal=1.0):
    ctx.set_source(vgrad([(0, C["taupe"]), (1, C["taupe2"])])); ctx.paint()
    contours(ctx, t, C["white"], 0.28, reveal=reveal, width=1.4)

# ----------------------------------------------------------------------------- wordmark
def wordmark(ctx, cx, y, size, p, ring_p=None, tracking_k=0.34, sub=True, color=None):
    """MOSAIC with the gradient-ring O, letters rising in; p drives letters, ring_p the O ring draw"""
    color = color or C["navy"]
    ring_p = p if ring_p is None else ring_p
    font(ctx, "Jost Medium"); ctx.set_font_size(size)
    letters = "MOSAIC"; tr = size * tracking_k
    adv = [ctx.text_extents(ch).x_advance for ch in letters]
    total = sum(adv) + tr * (len(letters) - 1)
    x = cx - total / 2
    for i, ch in enumerate(letters):
        lp = seg(p, i * 0.09, i * 0.09 + 0.5)
        e = ease_out_cubic(lp)
        if ch == "O":
            ext = ctx.text_extents("O")
            ox = x + ext.x_bearing + ext.width / 2; oy = y + ext.y_bearing + ext.height / 2
            r = ext.width / 2 * 0.86
            rp = ease_in_out(ring_p)
            if rp > 0:
                g = cairo.LinearGradient(ox - r, oy + r, ox + r, oy - r)
                for k, c in enumerate(GRAD): g.add_color_stop_rgba(k / (len(GRAD) - 1), *c)
                ctx.set_source(g); ctx.set_line_width(size * 0.085); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                ctx.new_path(); ctx.arc(ox, oy, r, -math.pi * 0.75, -math.pi * 0.75 + 2 * math.pi * rp); ctx.stroke()
        elif lp > 0:
            ctx.save(); ctx.translate(0, (1 - e) * size * 0.35)
            set_col(ctx, color, e); font(ctx, "Jost Medium"); ctx.set_font_size(size)
            ctx.move_to(x, y); ctx.show_text(ch); ctx.restore()
        x += adv[i] + tr
    if sub:
        sp = seg(p, 0.55, 1.0)
        if sp > 0:
            text(ctx, "FOREST MANAGEMENT", cx, y + size * 0.36, size * 0.135, color, fam="Jost Medium", align="center", tracking=size * 0.07, alpha=ease_out_cubic(sp))

# ----------------------------------------------------------------------------- icons (line style, 1 unit = s px)
def icon(ctx, kind, x, y, s, col, lw=None):
    ctx.save(); ctx.translate(x, y); set_col(ctx, col); ctx.new_path()
    ctx.set_line_width(lw or max(1.5, s * 0.11)); ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    if kind == "tree":
        ctx.move_to(0, -s); ctx.line_to(-s * 0.55, -s * 0.25); ctx.line_to(-s * 0.25, -s * 0.25); ctx.line_to(-s * 0.7, s * 0.4); ctx.line_to(s * 0.7, s * 0.4)
        ctx.line_to(s * 0.25, -s * 0.25); ctx.line_to(s * 0.55, -s * 0.25); ctx.close_path(); ctx.stroke()
        ctx.move_to(0, s * 0.4); ctx.line_to(0, s * 0.9); ctx.stroke()
    elif kind == "bolt":
        ctx.move_to(s * 0.15, -s); ctx.line_to(-s * 0.5, s * 0.1); ctx.line_to(0, s * 0.1); ctx.line_to(-s * 0.15, s); ctx.line_to(s * 0.5, -s * 0.1); ctx.line_to(0, -s * 0.1); ctx.close_path(); ctx.stroke()
    elif kind == "drop":
        ctx.move_to(0, -s); ctx.curve_to(s * 0.9, s * 0.05, s * 0.75, s * 0.9, 0, s * 0.9); ctx.curve_to(-s * 0.75, s * 0.9, -s * 0.9, s * 0.05, 0, -s); ctx.stroke()
        ctx.move_to(-s * 0.35, s * 0.35); ctx.curve_to(-s * 0.35, s * 0.6, -s * 0.15, s * 0.65, 0, s * 0.62); ctx.stroke()
    elif kind == "tent":
        ctx.move_to(-s, s * 0.7); ctx.line_to(0, -s * 0.8); ctx.line_to(s, s * 0.7); ctx.close_path(); ctx.stroke()
        ctx.move_to(0, -s * 0.8); ctx.line_to(0, s * 0.7); ctx.stroke(); ctx.move_to(-s * 0.2, -s); ctx.line_to(s * 0.2, -s * 0.6); ctx.stroke()
    elif kind == "house":
        ctx.move_to(-s, 0); ctx.line_to(0, -s); ctx.line_to(s, 0); ctx.stroke()
        ctx.move_to(-s * 0.7, -s * 0.2); ctx.line_to(-s * 0.7, s * 0.9); ctx.line_to(s * 0.7, s * 0.9); ctx.line_to(s * 0.7, -s * 0.2); ctx.stroke()
        ctx.rectangle(-s * 0.2, s * 0.3, s * 0.4, s * 0.6); ctx.stroke()
    elif kind == "leaf":
        ctx.move_to(-s * 0.9, s * 0.8); ctx.curve_to(-s * 0.9, -s * 0.6, s * 0.2, -s, s, -s); ctx.curve_to(s, s * 0.2, s * 0.2, s * 0.9, -s * 0.9, s * 0.8); ctx.stroke()
        ctx.move_to(-s * 0.9, s * 0.8); ctx.line_to(s * 0.55, -s * 0.55); ctx.stroke()
    elif kind == "mill":
        ctx.move_to(-s, s * 0.9); ctx.line_to(-s, -s * 0.2); ctx.line_to(-s * 0.35, -s * 0.7); ctx.line_to(-s * 0.35, -s * 0.2); ctx.line_to(s * 0.3, -s * 0.7); ctx.line_to(s * 0.3, -s * 0.2); ctx.line_to(s, -s * 0.2); ctx.line_to(s, s * 0.9); ctx.close_path(); ctx.stroke()
        ctx.move_to(-s * 0.7, -s * 1.0); ctx.line_to(-s * 0.7, -s * 0.45); ctx.stroke()
    elif kind == "worker":
        ctx.arc(0, -s * 0.55, s * 0.3, 0, 2 * math.pi); ctx.stroke()
        ctx.move_to(-s * 0.7, s); ctx.curve_to(-s * 0.7, s * 0.1, s * 0.7, s * 0.1, s * 0.7, s); ctx.stroke()
        ctx.move_to(-s * 0.5, -s * 0.75); ctx.line_to(s * 0.5, -s * 0.75); ctx.stroke()
    elif kind == "town":
        ctx.move_to(-s, s); ctx.line_to(-s, -s * 0.1); ctx.line_to(-s * 0.55, -s * 0.5); ctx.line_to(-s * 0.1, -s * 0.1); ctx.line_to(-s * 0.1, s); ctx.stroke()
        ctx.move_to(s * 0.1, s); ctx.line_to(s * 0.1, -s * 0.6); ctx.line_to(s * 0.55, -s); ctx.line_to(s, -s * 0.6); ctx.line_to(s, s); ctx.stroke()
        ctx.move_to(-s * 1.2, s); ctx.line_to(s * 1.2, s); ctx.stroke()
    elif kind == "wave":
        for k in range(2):
            yy = -s * 0.35 + k * s * 0.6
            ctx.move_to(-s, yy); ctx.curve_to(-s * 0.5, yy - s * 0.5, -s * 0.2, yy + s * 0.5, 0, yy); ctx.curve_to(s * 0.3, yy - s * 0.5, s * 0.6, yy + s * 0.5, s, yy); ctx.stroke()
    elif kind == "thermo":
        ctx.move_to(-s * 0.25, -s); ctx.line_to(-s * 0.25, s * 0.2); ctx.arc(0, s * 0.45, s * 0.4, math.pi, 0); ctx.line_to(s * 0.25, -s); ctx.close_path(); ctx.stroke()
        ctx.arc(0, s * 0.45, s * 0.15, 0, 2 * math.pi); ctx.fill()
    elif kind == "check":
        ctx.arc(0, 0, s, 0, 2 * math.pi); ctx.stroke(); ctx.move_to(-s * 0.45, 0); ctx.line_to(-s * 0.1, s * 0.4); ctx.line_to(s * 0.5, -s * 0.4); ctx.stroke()
    elif kind == "log":
        ctx.move_to(-s, -s * 0.4); ctx.line_to(s * 0.6, -s * 0.4); ctx.arc(s * 0.6, 0, s * 0.4, -math.pi / 2, math.pi / 2); ctx.line_to(-s, s * 0.4); ctx.close_path(); ctx.stroke()
        ctx.arc(-s, 0, s * 0.4, 0, 2 * math.pi); ctx.stroke()
    ctx.restore()

# ----------------------------------------------------------------------------- procedural conifer (light version)
def conifer(ctx, x, base_y, height, growth, seed=0, sway_t=0.0, alpha=1.0, dark=None, light=None, tiers=13):
    if growth <= 0.001: return
    dark = dark or C["forest"]; light = light or C["green"]
    Hf = height; Hc = Hf * growth
    ctx.save(); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    tw = 1.4 + 0.011 * Hc
    set_col(ctx, hexc("#6b5a44"), alpha)
    ctx.move_to(x - tw, base_y); ctx.line_to(x + tw, base_y); ctx.line_to(x + tw * 0.25, base_y - Hc); ctx.line_to(x - tw * 0.25, base_y - Hc); ctx.close_path(); ctx.fill()
    Lmax = Hf * 0.30
    for k in range(tiers):
        frac = 0.10 + 0.86 * k / (tiers - 1); ty = base_y - frac * Hf
        if Hc < frac * Hf: break
        unfurl = clamp((Hc - frac * Hf) / (0.22 * Hf))
        L = Lmax * (1 - frac) ** 0.85 * ease_out_cubic(unfurl) * (0.9 + 0.2 * hsh(seed, k))
        if L < 3: continue
        col = lerpc(dark, light, frac ** 0.8)
        sway = math.radians(2.0) * math.sin(sway_t * 1.1 + seed * 0.7 + frac * 2) * frac
        for side in (-1, 1):
            a = math.radians(14 + 6 * hsh(seed, k, side)) + sway * side
            ex = x + side * L * math.cos(a); ey = ty + L * math.sin(a)
            cx_ = x + side * L * 0.5 * math.cos(a); cy_ = ty + L * 0.5 * math.sin(a) - L * 0.12
            set_col(ctx, lerpc(col, dark, 0.5), alpha * 0.5)
            ctx.move_to(x, ty - L * 0.30); ctx.line_to(ex, ey); ctx.line_to(x, ty + L * 0.34); ctx.close_path(); ctx.fill()
            set_col(ctx, col, alpha); ctx.set_line_width(1.6 + L * 0.045)
            ctx.move_to(x, ty); ctx.curve_to(cx_, cy_, cx_, cy_, ex, ey); ctx.stroke()
            m = int(L / 6); ctx.set_line_width(1.6)
            for j in range(1, m):
                s = j / m
                px = (1 - s) ** 2 * x + 2 * (1 - s) * s * cx_ + s * s * ex
                py = (1 - s) ** 2 * ty + 2 * (1 - s) * s * cy_ + s * s * ey
                bl = L * 0.42 * (1 - s) * (0.7 + 0.5 * hsh(seed, k, j + 7 * side))
                ba = a + math.radians(38) + sway * side
                dx = side * bl * math.cos(ba); dy = bl * math.sin(ba)
                ctx.move_to(px, py); ctx.line_to(px + dx, py + dy)
                ctx.move_to(px, py); ctx.line_to(px + dx * 0.8, py - dy * 0.35)
            ctx.stroke()
    ctx.restore()

# ----------------------------------------------------------------------------- voronoi land mosaic
_VOR = {}

def build_voronoi(key, cx, cy, R, n=12, seed=21, wob=(0.10, 0.06, 0.04)):
    if key in _VOR: return _VOR[key]
    rng = np.random.default_rng(seed)
    pts = []
    for j in range(n):
        for i in range(n):
            pts.append((cx - R + (i + 0.5) * 2 * R / n + rng.uniform(-0.3, 0.3) * 2 * R / n,
                        cy - R + (j + 0.5) * 2 * R / n + rng.uniform(-0.3, 0.3) * 2 * R / n))
    pts = np.array(pts)
    far = np.array([[cx - 5000, cy - 5000], [cx + 5000, cy - 5000], [cx - 5000, cy + 5000], [cx + 5000, cy + 5000]])
    vor = Voronoi(np.vstack([pts, far]))
    def rb(ang): return 0.86 + wob[0] * math.sin(3 * ang + 0.8) + wob[1] * math.sin(5 * ang + 2.1) + wob[2] * math.sin(7 * ang)
    cells = []
    for k, p in enumerate(pts):
        reg = vor.regions[vor.point_region[k]]
        if -1 in reg or not reg: continue
        r = math.hypot(p[0] - cx, p[1] - cy) / R
        if r > rb(math.atan2(p[1] - cy, p[0] - cx)): continue
        cells.append(dict(poly=vor.vertices[reg], c=p, r=r, phase=hsh(k, 6 + seed), protected=(hsh(k, 5 + seed) < 0.14), kind=k))
    blob = []
    for k in range(160):
        ang = 2 * math.pi * k / 160
        blob.append((cx + R * rb(ang) * 1.08 * math.cos(ang), cy + R * rb(ang) * 1.08 * math.sin(ang)))
    _VOR[key] = dict(cells=cells, center=(cx, cy, R), blob=blob)
    return _VOR[key]

def poly_path(ctx, poly):
    ctx.move_to(*poly[0])
    for q in poly[1:]: ctx.line_to(*q)
    ctx.close_path()

STAGES = [(0.10, C["earth"], "Harvested"), (0.30, C["lime"], "Newly planted"), (0.65, C["green"], "Growing"), (1.00, C["forest"], "Mature")]

def stage_color(a):
    cols = [s[1] for s in STAGES]
    for i, (end, col, _) in enumerate(STAGES):
        if a < end:
            return lerpc(col, cols[(i + 1) % len(cols)], clamp((a - (end - 0.045)) / 0.045))
    return cols[-1]

# ============================================================================= SCENES
# ----------------------------------------------------------------------------- 1. title (0-7)
def scene_title(ctx, t, T):
    paper_bg(ctx, T, 1.0, reveal=seg(t, 0.0, 2.2))
    wordmark(ctx, 960, 470, 150, seg(t, 0.5, 2.0), ring_p=seg(t, 1.2, 2.4))
    p = seg(t, 2.6, 3.6)
    if p > 0:
        e = ease_out_cubic(p)
        ctx.save(); ctx.translate(0, (1 - e) * 16)
        font(ctx, "Jost Light"); ctx.set_font_size(46)
        w1 = text_width(ctx, "Innovation and stewardship ")
        font(ctx, "Jost SemiBold"); w2 = text_width(ctx, "meet here.")
        x = 960 - (w1 + w2) / 2
        text(ctx, "Innovation and stewardship ", x, 660, 46, C["navy"], fam="Jost Light", alpha=e)
        text(ctx, "meet here.", x + w1, 660, 46, C["navy"], fam="Jost SemiBold", alpha=ease_out_cubic(seg(t, 3.0, 3.9)))
        ctx.restore()
    # thin gradient rule
    rp = ease_out_expo(seg(t, 3.4, 4.6))
    if rp > 0:
        g = cairo.LinearGradient(760, 0, 1160, 0)
        for k, c in enumerate(GRAD): g.add_color_stop_rgba(k / 3, *c)
        ctx.set_source(g); ctx.rectangle(960 - 200 * rp, 715, 400 * rp, 3); ctx.fill()
    reveal_text(ctx, "VANCOUVER ISLAND, BRITISH COLUMBIA", 960, 770, 16, C["grey"], seg(t, 4.0, 4.9), fam="Jost Medium", align="center", tracking=5)

# ----------------------------------------------------------------------------- 2. portfolio (7-17)
PILLARS = [("tree", "Sustainable forestry"), ("bolt", "Renewable energy"), ("drop", "Watershed services"),
           ("tent", "Recreation"), ("house", "Real estate"), ("leaf", "Carbon programs")]

def scene_portfolio(ctx, t, T):
    taupe_bg(ctx, T)
    cx, cy, R = 1290, 560, 150
    V = build_voronoi("port", cx, cy, R, n=8, seed=3, wob=(0.05, 0.03, 0.02))
    # land mosaic in the middle
    lp = max(1e-3, ease_out_back(seg(t, 0.3, 1.1), 1.4))
    ctx.save(); ctx.translate(cx, cy); ctx.scale(lp, lp); ctx.translate(-cx, -cy)
    glow(ctx, cx, cy + 10, R * 1.7, hexc("#000000"), 0.18)
    blob = V["blob"]; poly_path(ctx, blob); ctx.clip()
    for cell in V["cells"]:
        age = (cell["phase"] + T / 14.0) % 1.0
        col = C["aqua2"] if cell["protected"] else stage_color(age)
        poly_path(ctx, cell["poly"]); set_col(ctx, col); ctx.fill_preserve()
        set_col(ctx, C["white"], 0.9); ctx.set_line_width(3); ctx.stroke()
    ctx.restore()
    # pillars on a ring
    Rr = 330
    for i, (kind, label) in enumerate(PILLARS):
        ang = -math.pi / 2 + i * 2 * math.pi / 6
        px, py = cx + Rr * math.cos(ang), cy + Rr * math.sin(ang) * 0.86
        p = seg(t, 1.0 + i * 0.28, 1.6 + i * 0.28)
        if p <= 0: continue
        # connector
        lp2 = ease_out_cubic(seg(p, 0, 0.6))
        set_col(ctx, C["white"], 0.75); ctx.set_line_width(2)
        ctx.move_to(cx + (R + 12) * math.cos(ang), cy + (R + 12) * math.sin(ang) * 0.9)
        ctx.line_to(cx + ((R + 12) + (Rr - R - 12 - 46) * lp2) * math.cos(ang), cy + ((R + 12) + (Rr - R - 12 - 46) * lp2) * math.sin(ang) * 0.87); ctx.stroke()
        e = ease_out_back(seg(p, 0.35, 1.0), 2.0)
        if e <= 0: continue
        ctx.save(); ctx.translate(px, py); ctx.scale(e, e)
        set_col(ctx, C["white"]); ctx.arc(0, 0, 46, 0, 2 * math.pi); ctx.fill()
        set_col(ctx, gradc(i / 5)); ctx.set_line_width(3); ctx.arc(0, 0, 46, 0, 2 * math.pi); ctx.stroke()
        icon(ctx, kind, 0, 0, 20, C["navy"], lw=2.4)
        ctx.restore()
        side = "left" if math.cos(ang) < -0.1 else "right" if math.cos(ang) > 0.1 else "center"
        tx = px - 62 if side == "left" else px + 62 if side == "right" else px
        ty = py + 7 if side != "center" else (py - 66 if math.sin(ang) < 0 else py + 84)
        al = "right" if side == "left" else "left" if side == "right" else "center"
        text(ctx, label, tx, ty, 22, C["white"], fam="Jost Medium", align=al, alpha=ease_out_cubic(seg(p, 0.5, 1.0)))
    reveal_text(ctx, "Redefining the", 120, 300, 84, C["white"], seg(t, 0.3, 1.1), fam="Jost Light")
    reveal_text(ctx, "forest economy.", 120, 395, 84, C["white"], seg(t, 0.6, 1.4), fam="Jost Light")
    reveal_text(ctx, "A traditional forestry company becoming a modern,", 120, 480, 28, C["white"], seg(t, 1.4, 2.2), fam="Jost Light", alpha=0.92)
    reveal_text(ctx, "diversified land business — six ways one landscape", 120, 520, 28, C["white"], seg(t, 1.55, 2.35), fam="Jost Light", alpha=0.92)
    reveal_text(ctx, "serves the public good.", 120, 560, 28, C["white"], seg(t, 1.7, 2.5), fam="Jost Light", alpha=0.92)
    eyebrow(ctx, "A portfolio approach", 120, 690, seg(t, 3.2, 4.0), color=C["white"])

# ----------------------------------------------------------------------------- 3. Koksilah pilot (17-29)
RIVER = [(1900, 300), (1720, 380), (1560, 430), (1420, 520), (1310, 640), (1250, 780), (1180, 900), (1100, 1080)]
TRIBS = [[(1360, 250), (1400, 380), (1440, 500)], [(1700, 700), (1560, 640), (1440, 610), (1330, 640)], [(980, 700), (1100, 760), (1190, 770), (1250, 780)]]

def catmull(P, u):
    n = len(P) - 1; u = clamp(u) * n; i = min(int(u), n - 1); f = u - i
    p0 = P[max(i - 1, 0)]; p1 = P[i]; p2 = P[i + 1]; p3 = P[min(i + 2, n)]
    return [0.5 * ((2 * b) + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f + (-a + 3 * b - 3 * c + d) * f ** 3)
            for a, b, c, d in zip(p0, p1, p2, p3)]

def stroke_curve(ctx, P, draw=1.0, steps=120):
    ctx.move_to(*catmull(P, 0))
    for k in range(1, int(steps * draw) + 1): ctx.line_to(*catmull(P, k / steps))

def dist_to_river(x, y):
    d = 1e9
    for P in [RIVER] + TRIBS:
        for k in range(41):
            px, py = catmull(P, k / 40); d = min(d, math.hypot(x - px, y - py))
    return d

def scene_koksilah(ctx, t, T):
    paper_bg(ctx, T, 0.9)
    V = build_voronoi("kok", 1380, 620, 520, n=14, seed=8, wob=(0.06, 0.05, 0.03))
    if "kdist" not in V:
        V["kdist"] = {c["kind"]: dist_to_river(*c["c"]) for c in V["cells"]}
    ctx.save()
    # map area fade region (right)
    mp = ease_out_cubic(seg(t, 0.2, 1.2))
    poly_path(ctx, V["blob"]); ctx.clip()
    buffer_p = ease_in_out(seg(t, 3.2, 4.6))
    # harvest blocks: light green cells; those near water become retained (dark) as the buffer arrives
    for cell in V["cells"]:
        d = V["kdist"][cell["kind"]]
        p = seg(t, 0.3 + cell["r"] * 0.9, 0.9 + cell["r"] * 0.9)
        if p <= 0: continue
        near = d < 95
        setaside = cell["c"][0] > 1560 and cell["c"][1] > 560
        if setaside:
            col = C["forest"]; a = 0.9
        elif near:
            col = lerpc(C["lime"], C["green2"], buffer_p); a = 0.85
        else:
            col = lerpc(C["lime"], C["green"], 0.35 * cell["phase"]); a = 0.8
        ctx.save(); poly_path(ctx, cell["poly"]); set_col(ctx, col, a * ease_out_cubic(p)); ctx.fill_preserve()
        set_col(ctx, C["white"], 0.9); ctx.set_line_width(2.5); ctx.stroke()
        if setaside and seg(t, 5.2, 6.0) > 0:
            poly_path(ctx, cell["poly"]); ctx.clip(); set_col(ctx, C["white"], 0.35 * seg(t, 5.2, 6.0)); ctx.set_line_width(1.5)
            for dd in range(-1200, 1200, 16):
                ctx.move_to(cell["c"][0] + dd, cell["c"][1] - 400); ctx.line_to(cell["c"][0] + dd + 400, cell["c"][1] + 400)
            ctx.stroke()
        ctx.restore()
    # roads: dashed; some segments vanish (reduced footprint)
    rp = seg(t, 6.2, 7.6)
    ctx.set_line_width(2.5); ctx.set_dash([10, 8])
    roads = [[(900, 950), (1080, 860), (1250, 900), (1400, 980)], [(1200, 200), (1330, 330), (1500, 350), (1700, 240)], [(1500, 350), (1600, 520), (1750, 560)], [(1080, 860), (1000, 640), (1100, 470)]]
    for i, Rd in enumerate(roads):
        keep = i < 2
        a = 0.55 * ease_out_cubic(seg(t, 1.0, 1.8)) * (1 if keep else (1 - rp))
        if a <= 0: continue
        set_col(ctx, C["ink"], a); stroke_curve(ctx, Rd); ctx.stroke()
    ctx.set_dash([])
    # riparian buffer
    if buffer_p > 0:
        ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        for P in [RIVER] + TRIBS:
            set_col(ctx, C["aqua"], 0.28 * buffer_p); ctx.set_line_width(110 * buffer_p); stroke_curve(ctx, P); ctx.stroke()
    # river
    rd = ease_in_out(seg(t, 0.8, 2.6))
    ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for P, wdt in [(RIVER, 12)] + [(Tb, 6) for Tb in TRIBS]:
        set_col(ctx, C["aqua2"]); ctx.set_line_width(wdt); stroke_curve(ctx, P, rd); ctx.stroke()
        set_col(ctx, C["white"], 0.6); ctx.set_line_width(wdt * 0.25); ctx.set_dash([26, 30], -T * 60); stroke_curve(ctx, P, rd); ctx.stroke(); ctx.set_dash([])
    ctx.restore()
    # set-aside label
    sp = seg(t, 5.4, 6.2)
    if sp > 0:
        e = ease_out_back(sp)
        ctx.save(); ctx.translate(1690, 760); ctx.scale(e, e)
        set_col(ctx, C["white"], 0.95); rrect(ctx, -110, -46, 220, 92, 12); ctx.fill()
        set_col(ctx, C["forest"]); ctx.set_line_width(2); rrect(ctx, -110, -46, 220, 92, 12); ctx.stroke()
        text(ctx, "715 ha", 0, -2, 40, C["forest"], fam="Jost SemiBold", align="center")
        text(ctx, "OLDER FOREST SET ASIDE", 0, 28, 12, C["grey"], fam="Jost Medium", align="center", tracking=2.5)
        ctx.restore()
    # left column
    ctx.save(); ctx.set_source(vgrad([(0, C["white"]), (0.7, hexc("#ffffff", 0.92)), (1, hexc("#ffffff", 0))], 0, 0, 1000, 0)); ctx.rectangle(0, 0, 1000, H); ctx.fill(); ctx.restore()
    eyebrow(ctx, "Pilot project", 120, 230, seg(t, 0.3, 1.0))
    reveal_text(ctx, "A new approach in the", 120, 320, 66, C["navy"], seg(t, 0.5, 1.3), fam="Jost Light")
    reveal_text(ctx, "Koksilah Watershed.", 120, 398, 66, C["navy"], seg(t, 0.7, 1.5), fam="Jost Light")
    items = [("Longer forest growth periods", 2.4), ("Harvest designs that protect water quality", 3.4), ("Enhanced stream & wetland protection", 4.4),
             ("Reduced road footprints", 6.2), ("Multi-year monitoring of flow, temperature & habitat", 7.4)]
    for k, (s, at) in enumerate(items):
        p = seg(t, at, at + 0.7)
        if p <= 0: continue
        y = 470 + k * 56
        e = ease_out_back(p, 2.2)
        ctx.save(); ctx.translate(134, y - 9); ctx.scale(e, e); icon(ctx, "check", 0, 0, 11, gradc(k / 4), lw=2.2); ctx.restore()
        text(ctx, s, 166, y, 25, C["ink"], fam="Jost", alpha=ease_out_cubic(p))
    # monitoring gauges
    gp = seg(t, 7.8, 8.8)
    if gp > 0:
        for k, (kind, lab) in enumerate([("wave", "Streamflow"), ("thermo", "Temperature"), ("drop", "Water quality")]):
            x = 120 + k * 250; y = 830
            e = ease_out_cubic(seg(gp, k * 0.2, k * 0.2 + 0.6))
            if e <= 0: continue
            set_col(ctx, C["paper2"], e); rrect(ctx, x, y - 50, 230, 96, 12); ctx.fill()
            icon(ctx, kind, x + 32, y - 4, 13, C["aqua2"], lw=2.2)
            text(ctx, lab.upper(), x + 62, y - 12, 13, C["grey"], fam="Jost Medium", tracking=2.5, alpha=e)
            # sparkline
            set_col(ctx, C["aqua2"], e); ctx.set_line_width(2)
            for j in range(0, 150, 4):
                yy = y + 22 - 12 * math.sin(j * 0.09 + T * 1.6 + k * 2) - 5 * math.sin(j * 0.31 + T * 2.3)
                (ctx.move_to if j == 0 else ctx.line_to)(x + 62 + j, yy)
            ctx.stroke()
    reveal_text(ctx, "WITH COWICHAN TRIBES AND THE PROVINCE OF B.C.", 120, 990, 15, C["grey"], seg(t, 9.0, 9.9), fam="Jost Medium", tracking=4)

# ----------------------------------------------------------------------------- 4. one forest, many ages (29-39)
def scene_mosaic(ctx, t, T):
    paper_bg(ctx, T, 0.8)
    V = build_voronoi("ages", 1290, 585, 350)
    cx, cy, R = V["center"]
    ctx.save()
    glow(ctx, cx, cy + 40, R * 1.5, hexc("#000000"), 0.16 * ease_out_cubic(seg(t, 0.2, 1.2)))
    poly_path(ctx, V["blob"]); ctx.clip()
    for cell in V["cells"]:
        px, py = cell["c"]
        ap = 0.25 + cell["r"] * 1.4 + hsh(cell["kind"], 8) * 0.35
        p = seg(t, ap, ap + 0.6)
        if p <= 0: continue
        s = ease_out_back(p, 1.6); age = (cell["phase"] + t / 9.0) % 1.0
        col = C["aqua2"] if cell["protected"] else stage_color(age)
        ctx.save(); ctx.translate(px, py); ctx.scale(s, s); ctx.translate(-px, -py)
        poly_path(ctx, cell["poly"]); set_col(ctx, col); ctx.fill_preserve()
        set_col(ctx, C["white"]); ctx.set_line_width(5); ctx.set_line_join(cairo.LINE_JOIN_ROUND); ctx.stroke()
        if cell["protected"]:
            poly_path(ctx, cell["poly"]); ctx.clip(); set_col(ctx, C["white"], 0.4); ctx.set_line_width(1.5)
            for d in range(-700, 700, 14): ctx.move_to(px + d, py - 300); ctx.line_to(px + d + 300, py + 300)
            ctx.stroke()
        elif age > 0.10:
            gsz = 6 + 26 * clamp((age - 0.10) / 0.75)
            for m in range(3):
                ox = (hsh(cell["kind"], 30 + m) - 0.5) * 34; oy = (hsh(cell["kind"], 40 + m) - 0.5) * 24
                hh = gsz * (0.7 + 0.5 * hsh(cell["kind"], 50 + m))
                set_col(ctx, C["white"], 0.55)
                ctx.move_to(px + ox - hh * 0.36, py + oy + 6); ctx.line_to(px + ox, py + oy - hh); ctx.line_to(px + ox + hh * 0.36, py + oy + 6); ctx.close_path(); ctx.fill()
        else:
            set_col(ctx, hexc("#8a7a5a"), 0.9)
            for m in range(4):
                ctx.arc(px + (hsh(cell["kind"], 60 + m) - 0.5) * 40, py + (hsh(cell["kind"], 70 + m) - 0.5) * 30, 2.6, 0, 2 * math.pi); ctx.fill()
        ctx.restore()
    ctx.restore()
    eyebrow(ctx, "Why “Mosaic”", 120, 250, seg(t, 0.2, 0.9))
    reveal_text(ctx, "One forest.", 120, 350, 92, C["navy"], seg(t, 0.3, 1.1), fam="Jost Light")
    reveal_text(ctx, "Many ages.", 120, 450, 92, C["navy"], seg(t, 0.7, 1.5), fam="Jost SemiBold")
    reveal_text(ctx, "Small patches on their own clocks — so the", 120, 530, 30, C["ink"], seg(t, 1.5, 2.3), fam="Jost Light")
    reveal_text(ctx, "landscape is never all one age, and never all one use.", 120, 572, 30, C["ink"], seg(t, 1.7, 2.5), fam="Jost Light")
    items = [(s[1], s[2]) for s in STAGES] + [(C["aqua2"], "Protected")]
    for i, (col, name) in enumerate(items):
        p = seg(t, 2.6 + i * 0.16, 3.2 + i * 0.16)
        if p <= 0: continue
        e = ease_out_back(p); y = 690 + i * 48
        ctx.save(); ctx.translate(134, y); ctx.scale(e, e); set_col(ctx, col); rrect(ctx, -14, -14, 28, 28, 6); ctx.fill(); ctx.restore()
        text(ctx, name, 166, y + 8, 24, C["ink"], fam="Jost", alpha=0.9 * ease_out_cubic(p))

# ----------------------------------------------------------------------------- 5. B.C. mills first (39-49)
# Real coastline: Natural Earth 10m land polygons clipped to the Salish Sea (data/coast.json,
# data/vancouver_island.json). Mill towns are placed by lat/lon.
import json
_MAP = {}

def load_map():
    if _MAP: return _MAP
    _MAP["coast"] = json.load(open(os.path.join(HERE, "data", "coast.json")))
    _MAP["island"] = json.load(open(os.path.join(HERE, "data", "vancouver_island.json")))
    return _MAP

LON0, LAT0 = -128.42, 50.87            # NW corner of the island bbox -> screen (620, 60)
SX, SY = 375 * math.cos(math.radians(49.6)), 375   # px per degree (equirectangular at 49.6N)

def proj(lon, lat):
    return 620 + (lon - LON0) * SX, 60 + (LAT0 - lat) * SY

MILLS = [  # (town, lat, lon, mills) — counts from mosaicforests.com's Log Sales & Market Access map
    ("Campbell River", 50.0244, -125.2475, 4), ("Black Creek", 49.8480, -125.1170, 1), ("Merville", 49.7660, -125.0520, 1),
    ("Port Alberni", 49.2339, -124.8055, 3), ("Qualicum Beach", 49.3494, -124.4438, 1), ("Parksville", 49.3192, -124.3136, 2),
    ("Nanoose Bay", 49.2667, -124.1833, 2), ("Lantzville", 49.2483, -124.0736, 1), ("Nanaimo", 49.1659, -123.9401, 4),
    ("Ladysmith", 48.9975, -123.8206, 3), ("Chemainus", 48.9245, -123.7136, 2), ("Duncan", 48.7787, -123.7079, 2),
    ("Cobble Hill", 48.6640, -123.6110, 2), ("Sooke", 48.3745, -123.7358, 2),
]

def mill_layout():
    """screen positions + de-overlapped label positions (labels fan right of the east-coast dots)"""
    if "layout" in _MAP: return _MAP["layout"]
    items = []
    for name, lat, lon, cnt in MILLS:
        x, y = proj(lon, lat)
        left = name in ("Port Alberni", "Sooke")
        items.append(dict(name=name, x=x, y=y, cnt=cnt, left=left, lx=x + (-22 if left else 22), ly=y))
    # push overlapping labels apart (east side only), keep order by latitude
    east = sorted([it for it in items if not it["left"]], key=lambda d: d["y"])
    minsep = 27
    for i in range(1, len(east)):
        if east[i]["ly"] - east[i - 1]["ly"] < minsep: east[i]["ly"] = east[i - 1]["ly"] + minsep
    # re-centre the pushed cluster around its dots
    shift = sum(it["ly"] - it["y"] for it in east) / len(east)
    for it in east: it["ly"] -= shift; it["lx"] = it["x"] + 22 + abs(it["ly"] - it["y"]) * 1.2
    _MAP["layout"] = items
    return items

def scene_mills(ctx, t, T):
    M = load_map()
    ctx.set_source(vgrad([(0, C["water"]), (1, lerpc(C["water"], C["water2"], 0.5))])); ctx.paint()
    contours(ctx, T, C["white"], 0.30, width=1.2)
    mp = ease_out_cubic(seg(t, 0.2, 1.4))
    # surrounding coast (mainland, Gulf Islands, Olympic Peninsula)
    ctx.save(); ctx.translate(0, (1 - mp) * 30)
    for ring in M["coast"]:
        ctx.move_to(*proj(*ring[0]))
        for lon, lat in ring[1:]: ctx.line_to(*proj(lon, lat))
        ctx.close_path()
    set_col(ctx, lerpc(C["paper"], C["water"], 0.35), mp); ctx.fill_preserve()
    set_col(ctx, C["white"], 0.8 * mp); ctx.set_line_width(1.5); ctx.stroke()
    ctx.restore()
    # Vancouver Island
    ip = ease_out_cubic(seg(t, 0.4, 1.6))
    isl = M["island"]
    def island_path():
        ctx.move_to(*proj(*isl[0]))
        for lon, lat in isl[1:]: ctx.line_to(*proj(lon, lat))
        ctx.close_path()
    ctx.save(); ctx.translate(0, (1 - ip) * 24)
    glow(ctx, 1180, 560, 760, hexc("#2a5060"), 0.16 * ip)
    island_path(); set_col(ctx, C["paper"], ip); ctx.fill_preserve(); set_col(ctx, C["white"], ip); ctx.set_line_width(3); ctx.stroke()
    island_path(); ctx.clip(); contours(ctx, T, C["contour"], 0.9 * ip, width=1.1)
    rng_pts = [(hsh(i, 1), hsh(i, 2), hsh(i, 3), hsh(i, 4)) for i in range(160)]
    for (h1, h2, h3, h4) in rng_pts:
        lon = LON0 + h1 * 5.2; lat = LAT0 - h2 * 2.6
        x, y = proj(lon, lat); r = 8 + 16 * h3
        set_col(ctx, lerpc(C["lime"], C["green"], h4), 0.26 * ip); ctx.new_path(); ctx.arc(x, y, r, 0, 2 * math.pi); ctx.fill()
    ctx.restore()
    # mills
    for i, it in enumerate(mill_layout()):
        mx, my = it["x"], it["y"]
        p = seg(t, 1.8 + i * 0.22, 2.4 + i * 0.22)
        if p <= 0: continue
        sx, sy = mx - 70 + 30 * hsh(i, 5), my - 55 + 30 * hsh(i, 6)
        set_col(ctx, C["green"], 0.6 * ease_out_cubic(p)); ctx.set_line_width(2.5); ctx.set_dash([8, 10], -T * 50)
        ctx.move_to(sx, sy); ctx.line_to(mx, my); ctx.stroke(); ctx.set_dash([])
        e = ease_out_back(p, 2.5)
        glow(ctx, mx, my, 34, C["aqua2"], 0.35 * (0.6 + 0.4 * math.sin(T * 3 + i)))
        ctx.save(); ctx.translate(mx, my); ctx.scale(e, e)
        set_col(ctx, C["navy"]); ctx.new_path(); ctx.arc(0, 0, 11, 0, 2 * math.pi); ctx.fill()
        text(ctx, str(it["cnt"]), 0, 5, 14, C["white"], fam="Jost SemiBold", align="center")
        ctx.restore()
        a = ease_out_cubic(p)
        if abs(it["ly"] - my) > 3 or abs(it["lx"] - mx) > 26:
            set_col(ctx, C["navy"], 0.45 * a); ctx.set_line_width(1)
            ctx.move_to(mx + (12 if not it["left"] else -12), my); ctx.line_to(it["lx"] - 6, it["ly"]); ctx.stroke()
        text(ctx, it["name"], it["lx"], it["ly"] + 5, 15, C["ink"], fam="Jost Medium", align="right" if it["left"] else "left", alpha=a)
    # region labels
    lp = ease_out_cubic(seg(t, 1.2, 2.0))
    text(ctx, "VANCOUVER ISLAND", 1010, 470, 15, C["grey"], fam="Jost Medium", align="center", tracking=5, alpha=0.8 * lp)
    text(ctx, "STRAIT OF GEORGIA", 1480, 300, 13, C["aqua2"], fam="Jost Medium", align="center", tracking=4, alpha=0.9 * lp)
    text(ctx, "PACIFIC OCEAN", 760, 900, 13, C["aqua2"], fam="Jost Medium", align="center", tracking=4, alpha=0.9 * lp)
    # copy panel (left)
    ctx.save(); ctx.set_source(vgrad([(0, hexc("#ffffff", 0.94)), (0.75, hexc("#ffffff", 0.8)), (1, hexc("#ffffff", 0))], 0, 0, 760, 0)); ctx.rectangle(0, 0, 760, H); ctx.fill(); ctx.restore()
    eyebrow(ctx, "Log sales & market access", 120, 230, seg(t, 0.2, 0.9))
    reveal_text(ctx, "B.C. mills first.", 120, 330, 84, C["navy"], seg(t, 0.4, 1.2), fam="Jost Light")
    reveal_text(ctx, "Domestic manufacturers get every log first.", 120, 400, 28, C["ink"], seg(t, 1.2, 2.0), fam="Jost Light")
    reveal_text(ctx, "Only surplus declined at home goes to export.", 120, 440, 28, C["ink"], seg(t, 1.4, 2.2), fam="Jost Light")
    cp = seg(t, 2.2, 3.0)
    if cp > 0:
        n60 = int(round(ease_out_expo(seg(t, 2.4, 5.6)) * 60)); n30 = int(round(ease_out_expo(seg(t, 2.4, 5.2)) * 30))
        e = ease_out_cubic(cp)
        text(ctx, f"{n60}+", 120, 620, 128, C["navy"], fam="Jost Medium", alpha=e)
        text(ctx, "B.C. MILLS SUPPLIED", 120, 660, 16, C["grey"], fam="Jost Medium", tracking=4, alpha=e)
        text(ctx, f"{n30}", 460, 620, 128, C["aqua2"], fam="Jost Medium", alpha=e)
        text(ctx, "ON VANCOUVER ISLAND", 460, 660, 16, C["grey"], fam="Jost Medium", tracking=4, alpha=e)
    p2 = seg(t, 5.0, 5.8)
    if p2 > 0:
        e = ease_out_cubic(p2)
        set_col(ctx, C["paper2"], e); rrect(ctx, 120, 720, 600, 96, 14); ctx.fill()
        text(ctx, "100%", 146, 782, 54, gradc(0.55), fam="Jost SemiBold", alpha=e)
        text(ctx, "of logs sold internationally were", 320, 764, 22, C["ink"], fam="Jost", alpha=e)
        text(ctx, "first offered to domestic mills.", 320, 794, 22, C["ink"], fam="Jost", alpha=e)
    reveal_text(ctx, "TOP SUPPLIER TO LOCAL PULP MILLS", 120, 880, 15, C["grey"], seg(t, 6.2, 7.0), fam="Jost Medium", tracking=4)

# ----------------------------------------------------------------------------- 6. keeping B.C. working (49-55)
def scene_working(ctx, t, T):
    taupe_bg(ctx, T)
    reveal_text(ctx, "Keeping B.C. working.", 960, 250, 84, C["white"], seg(t, 0.2, 1.0), fam="Jost Light", align="center")
    reveal_text(ctx, "A stable, economically viable harvest is what keeps the coast's forest economy alive.", 960, 310, 26, C["white"], seg(t, 0.8, 1.6), fam="Jost Light", align="center", alpha=0.92)
    cards = [("mill", "Fibre flowing", "to B.C. mills"), ("worker", "Forestry workers", "and contractors"), ("town", "Strong coastal", "communities")]
    for k, (kind, l1, l2) in enumerate(cards):
        p = seg(t, 1.4 + k * 0.35, 2.2 + k * 0.35)
        if p <= 0: continue
        e = ease_out_back(p, 1.5); x = 400 + k * 560; y = 600
        ctx.save(); ctx.translate(x, y); ctx.scale(e, e)
        glow(ctx, 0, 30, 260, hexc("#000000"), 0.18)
        set_col(ctx, C["white"]); rrect(ctx, -210, -170, 420, 340, 22); ctx.fill()
        g = cairo.LinearGradient(-210, 0, 210, 0); g.add_color_stop_rgba(0, *gradc(k / 2 * 0.6)); g.add_color_stop_rgba(1, *gradc(k / 2 * 0.6 + 0.4))
        ctx.set_source(g); rrect(ctx, -210, -170, 420, 8, 4); ctx.fill()
        set_col(ctx, C["paper2"]); ctx.arc(0, -60, 58, 0, 2 * math.pi); ctx.fill()
        icon(ctx, kind, 0, -60, 26, C["navy"], lw=2.6)
        text(ctx, l1, 0, 62, 32, C["navy"], fam="Jost Medium", align="center")
        text(ctx, l2, 0, 104, 32, C["navy"], fam="Jost Light", align="center")
        ctx.restore()
    reveal_text(ctx, "PRIVATE MANAGED FORESTS HELP KEEP FIBRE, JOBS AND TAX REVENUE ON THE COAST", 960, 900, 15, C["white"], seg(t, 3.0, 3.9), fam="Jost Medium", align="center", tracking=4, alpha=0.9)

# ----------------------------------------------------------------------------- 7. outro (55-60)
def scene_outro(ctx, t, T):
    paper_bg(ctx, T, 1.0, reveal=seg(t, 0.0, 1.6))
    wordmark(ctx, 960, 470, 150, seg(t, 0.2, 1.5), ring_p=seg(t, 0.6, 1.8))
    p = seg(t, 1.5, 2.4)
    if p > 0:
        e = ease_out_cubic(p)
        font(ctx, "Jost Light"); ctx.set_font_size(46); w1 = text_width(ctx, "Innovation and stewardship ")
        font(ctx, "Jost SemiBold"); w2 = text_width(ctx, "meet here.")
        x = 960 - (w1 + w2) / 2
        text(ctx, "Innovation and stewardship ", x, 660, 46, C["navy"], fam="Jost Light", alpha=e)
        text(ctx, "meet here.", x + w1, 660, 46, C["navy"], fam="Jost SemiBold", alpha=e)
    reveal_text(ctx, "mosaicforests.com", 960, 760, 26, C["aqua2"], seg(t, 2.2, 3.0), fam="Jost Medium", align="center", tracking=3)
    fo = seg(t, 4.2, 5.0)
    if fo > 0:
        set_col(ctx, C["white"], ease_in_out(fo)); ctx.paint()

# ----------------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 7.0, scene_title),
    (7.0, 17.0, scene_portfolio),
    (17.0, 29.0, scene_koksilah),
    (29.0, 39.0, scene_mosaic),
    (39.0, 49.0, scene_mills),
    (49.0, 55.0, scene_working),
    (55.0, 60.0, scene_outro),
]
TRANS = 1.6

def render_scene(idx, T):
    s0, s1, fn = SCENES[idx]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    fn(cairo.Context(surf), T - s0, T)
    return surf

def mosaic_wipe(ctx, surfA, surfB, p, cell=64):
    ctx.set_source_surface(surfA, 0, 0); ctx.paint()
    nx, ny = W // cell + 1, H // cell + 1
    for j in range(ny):
        for i in range(nx):
            thr = ((i + j) / (nx + ny)) * 0.6 + hsh(i, j, 77) * 0.2
            s = seg(p, thr, thr + 0.2)
            if s <= 0: continue
            e = max(0.03, ease_out_cubic(s)); x, y = i * cell + cell / 2, j * cell + cell / 2
            ctx.save(); ctx.translate(x, y); ctx.scale(e, e); ctx.translate(-x, -y)
            ctx.rectangle(i * cell - 0.5, j * cell - 0.5, cell + 1, cell + 1); ctx.clip()
            ctx.set_source_surface(surfB, 0, 0); ctx.paint()
            fl = clamp(1 - s * 1.5)
            if fl > 0: set_col(ctx, gradc(hsh(i, j, 78)), fl * 0.85); ctx.paint()
            ctx.restore()

def render_frame(fi, scale=1.0):
    T = fi / FPS
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(W * scale), int(H * scale))
    ctx = cairo.Context(surf); ctx.scale(scale, scale)
    idx = max(i for i, (s0, s1, _) in enumerate(SCENES) if T >= s0)
    cut = SCENES[idx][0]; nxt = SCENES[idx + 1][0] if idx + 1 < len(SCENES) else None
    if idx > 0 and T < cut + TRANS / 2:
        mosaic_wipe(ctx, render_scene(idx - 1, T), render_scene(idx, T), (T - (cut - TRANS / 2)) / TRANS)
    elif nxt is not None and T >= nxt - TRANS / 2:
        mosaic_wipe(ctx, render_scene(idx, T), render_scene(idx + 1, T), (T - (nxt - TRANS / 2)) / TRANS)
    else:
        SCENES[idx][2](ctx, T - cut, T)
    vignette(ctx); grain(ctx, fi)
    surf.flush()
    return surf

# ----------------------------------------------------------------------------- encode
def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def encode_chunk(args):
    k, f0, f1, scale = args
    w, h = int(W * scale), int(H * scale)
    path = os.path.join(OUT, f"seg_{k:02d}.mp4")
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-r", str(FPS),
           "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        try:
            frame = render_frame(fi, scale)
        except Exception as e:  # surface the failing frame instead of an unpicklable cairo error
            import traceback; traceback.print_exc()
            raise RuntimeError(f"frame {fi} failed: {e!r}")
        proc.stdin.write(bytes(frame.get_data()))
        if k == 0 and fi % 30 == 0: print(f"  chunk0 frame {fi}/{f1}", flush=True)
    proc.stdin.close(); proc.wait()
    return path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", nargs="*", type=int)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", default=os.path.join(OUT, "video.mp4"))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.stills is not None:
        for fi in (a.stills or list(range(0, NFRAMES, 45))):
            p = os.path.join(OUT, f"still_{fi:04d}.png"); render_frame(fi, a.scale).write_to_png(p); print(p)
        return
    n = a.workers; bounds = [round(i * NFRAMES / n) for i in range(n + 1)]
    with Pool(n) as pool:
        segs = pool.map(encode_chunk, [(k, bounds[k], bounds[k + 1], a.scale) for k in range(n)])
    lst = os.path.join(OUT, "segs.txt")
    with open(lst, "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    subprocess.check_call([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", a.out])
    for s in segs: os.remove(s)
    os.remove(lst); print("wrote", a.out)

if __name__ == "__main__":
    main()
