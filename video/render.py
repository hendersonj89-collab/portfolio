#!/usr/bin/env python3
"""
Mosaic Forest Management — 60s motion-graphics spot.
Rendered entirely in code: numpy + scipy + pycairo, encoded with ffmpeg.

    python render.py                 # full 1080p30 render -> out/video.mp4
    python render.py --stills 0 90   # dump PNG stills for given frame numbers
    python render.py --scale 0.5     # quick low-res render
"""
import argparse
import math
import os
import subprocess
import sys
from multiprocessing import Pool

import cairo
import numpy as np
from scipy.spatial import Voronoi

W, H = 1920, 1080
FPS = 30
DUR = 60.0
NFRAMES = int(DUR * FPS)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ----------------------------------------------------------------------------- palette
def hexc(s, a=1.0):
    s = s.lstrip("#")
    return (int(s[0:2], 16) / 255, int(s[2:4], 16) / 255, int(s[4:6], 16) / 255, a)

C = dict(
    bg0=hexc("#050f0c"), bg1=hexc("#0b2b21"), bg2=hexc("#0f3a2c"),
    g0=hexc("#154b34"), g1=hexc("#1f7a4d"), g2=hexc("#3cae6a"), g3=hexc("#8fdc9a"), g4=hexc("#cdf2c4"),
    lime=hexc("#c9e46a"), earth=hexc("#7c5a3a"), earth2=hexc("#4a3524"),
    teal=hexc("#3fb7bd"), teal2=hexc("#1d6f7a"), sky=hexc("#7fd3ff"),
    gold=hexc("#f0c66a"), amber=hexc("#e9955a"),
    cream=hexc("#f4f1e8"), mute=hexc("#b9c7bf"),
)

def lerp(a, b, t):
    return a + (b - a) * t

def lerpc(c1, c2, t):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))

def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

# ----------------------------------------------------------------------------- easing
def ease_out_cubic(t):
    t = clamp(t); return 1 - (1 - t) ** 3

def ease_in_out(t):
    t = clamp(t); return t * t * (3 - 2 * t)

def ease_out_expo(t):
    t = clamp(t); return 1 if t >= 1 else 1 - 2 ** (-10 * t)

def ease_out_back(t, s=1.7):
    t = clamp(t); t -= 1
    return 1 + t * t * ((s + 1) * t + s)

def ease_out_elastic(t):
    t = clamp(t)
    if t in (0, 1): return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1

def seg(t, t0, t1):
    """0..1 progress of t across [t0, t1]"""
    return clamp((t - t0) / (t1 - t0)) if t1 > t0 else float(t >= t0)

def hsh(i, j=0, k=0):
    """deterministic hash -> [0,1)"""
    n = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791)
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0

# ----------------------------------------------------------------------------- textures
_TEX = {}

def _value_noise(size, cells, rng):
    g = rng.random((cells, cells))
    g = np.concatenate([g, g[:1]], 0); g = np.concatenate([g, g[:, :1]], 1)
    xs = np.linspace(0, cells, size, endpoint=False)
    i0 = np.floor(xs).astype(int); f = xs - i0; f = f * f * (3 - 2 * f)
    a = g[np.ix_(i0, i0)]; b = g[np.ix_(i0, i0 + 1)]; c = g[np.ix_(i0 + 1, i0)]; d = g[np.ix_(i0 + 1, i0 + 1)]
    fx = f[None, :]; fy = f[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy

def make_textures():
    if _TEX: return
    rng = np.random.default_rng(7)
    size = 512
    fbm = np.zeros((size, size))
    for o, amp in [(4, 1.0), (8, 0.5), (16, 0.25), (32, 0.125)]:
        fbm += _value_noise(size, o, rng) * amp
    fbm = (fbm - fbm.min()) / (fbm.max() - fbm.min())
    fbm = np.clip((fbm - 0.35) * 1.6, 0, 1) ** 1.5
    a = (fbm * 255).astype(np.uint8)
    arr = np.dstack([a, a, a, a]).copy()  # premultiplied white fog
    _TEX["fog_arr"] = arr
    _TEX["fog"] = cairo.ImageSurface.create_for_data(memoryview(arr), cairo.FORMAT_ARGB32, size, size, size * 4)
    # grain
    gr = []
    for k in range(3):
        n = rng.random((270, 480))
        v = (n * 255).astype(np.uint8)
        garr = np.dstack([v, v, v, np.full_like(v, 255)]).copy()
        gr.append((garr, cairo.ImageSurface.create_for_data(memoryview(garr), cairo.FORMAT_ARGB32, 480, 270, 480 * 4)))
    _TEX["grain"] = gr

# ----------------------------------------------------------------------------- cairo helpers
def set_col(ctx, c, a=None):
    ctx.set_source_rgba(c[0], c[1], c[2], c[3] if a is None else a)

def font(ctx, fam="Inter Display", bold=True):
    ctx.select_font_face(fam, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)

def text_width(ctx, s, tracking=0.0):
    if tracking == 0:
        return ctx.text_extents(s).x_advance
    return sum(ctx.text_extents(ch).x_advance for ch in s) + tracking * (len(s) - 1)

def text(ctx, s, x, y, size, color, fam="Inter Display", bold=True, align="left", tracking=0.0, alpha=1.0):
    font(ctx, fam, bold); ctx.set_font_size(size)
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
    return w

def reveal_text(ctx, s, x, y, size, color, p, **kw):
    """text rising in with a soft wipe"""
    if p <= 0: return
    e = ease_out_cubic(p)
    ctx.save()
    ctx.translate(0, (1 - e) * size * 0.45)
    kw["alpha"] = kw.get("alpha", 1.0) * e
    text(ctx, s, x, y, size, color, **kw)
    ctx.restore()

def rrect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()

def vgrad(ctx, stops, x0=0, y0=0, x1=0, y1=H):
    g = cairo.LinearGradient(x0, y0, x1, y1)
    for o, c in stops: g.add_color_stop_rgba(o, *c)
    return g

def glow(ctx, x, y, r, c, a=1.0):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, c[0], c[1], c[2], a)
    g.add_color_stop_rgba(0.4, c[0], c[1], c[2], a * 0.35)
    g.add_color_stop_rgba(1, c[0], c[1], c[2], 0)
    ctx.set_source(g); ctx.arc(x, y, r, 0, 2 * math.pi); ctx.fill()

def fog(ctx, t, alpha=0.18, speed=18.0, scale=3.5, seed=0):
    make_textures()
    ctx.save()
    pat = cairo.SurfacePattern(_TEX["fog"]); pat.set_extend(cairo.EXTEND_REPEAT)
    m = cairo.Matrix(); m.scale(1 / scale, 1 / scale); m.translate(-t * speed - seed * 200, -seed * 130 - t * 3)
    pat.set_matrix(m); pat.set_filter(cairo.FILTER_BILINEAR)
    ctx.set_source(pat); ctx.paint_with_alpha(alpha)
    ctx.restore()

def motes(ctx, t, n=45, color=None, seed=3):
    color = color or C["g4"]
    for i in range(n):
        h1, h2, h3, h4 = hsh(i, seed), hsh(i, seed + 1), hsh(i, seed + 2), hsh(i, seed + 3)
        x = (h1 * W + t * (8 + 14 * h3) + 40 * math.sin(t * 0.5 + h4 * 6)) % (W + 60) - 30
        y = (h2 * H - t * (6 + 10 * h4)) % (H + 60) - 30
        r = 1.2 + 2.5 * h3
        a = 0.25 + 0.45 * (0.5 + 0.5 * math.sin(t * (1 + h1) + h2 * 9))
        glow(ctx, x, y, r * 4, color, a * 0.5)
        set_col(ctx, color, a); ctx.arc(x, y, r, 0, 2 * math.pi); ctx.fill()

def vignette(ctx, a=0.62):
    g = cairo.RadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95)
    g.add_color_stop_rgba(0, 0, 0, 0, 0); g.add_color_stop_rgba(1, 0, 0, 0, a)
    ctx.set_source(g); ctx.paint()

def grain(ctx, frame, a=0.055):
    make_textures()
    arr, surf = _TEX["grain"][frame % 3]
    pat = cairo.SurfacePattern(surf); pat.set_extend(cairo.EXTEND_REPEAT)
    m = cairo.Matrix(); m.scale(0.5, 0.5); m.translate(hsh(frame, 9) * 300, hsh(frame, 10) * 300)
    pat.set_matrix(m); pat.set_filter(cairo.FILTER_NEAREST)
    ctx.save(); ctx.set_operator(cairo.OPERATOR_SOFT_LIGHT); ctx.set_source(pat); ctx.paint_with_alpha(a); ctx.restore()

def background(ctx, top, bottom, t, fog_a=0.14):
    ctx.set_source(vgrad(ctx, [(0, top), (1, bottom)])); ctx.paint()
    fog(ctx, t, fog_a, seed=0); fog(ctx, t, fog_a * 0.6, speed=-11, scale=5.0, seed=1)

# ----------------------------------------------------------------------------- procedural conifer
def conifer(ctx, x, base_y, height, growth, seed=0, sway_t=0.0, alpha=1.0, dark=None, light=None, tiers=14):
    """fractal conifer; growth in [0,1] grows trunk bottom-up, branches unfurl as the trunk passes them"""
    if growth <= 0.001: return
    dark = dark or C["g0"]; light = light or C["g2"]
    Hf = height; Hc = Hf * growth
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    # trunk (tapered polygon)
    tw = 1.5 + 0.011 * Hc
    set_col(ctx, lerpc(C["earth2"], C["bg0"], 0.35), alpha)
    ctx.move_to(x - tw, base_y); ctx.line_to(x + tw, base_y); ctx.line_to(x + tw * 0.25, base_y - Hc); ctx.line_to(x - tw * 0.25, base_y - Hc)
    ctx.close_path(); ctx.fill()
    Lmax = Hf * 0.30
    for k in range(tiers):
        frac = 0.10 + 0.86 * k / (tiers - 1)
        ty = base_y - frac * Hf
        if Hc < frac * Hf: break
        unfurl = clamp((Hc - frac * Hf) / (0.22 * Hf))
        L = Lmax * (1 - frac) ** 0.85 * ease_out_cubic(unfurl) * (0.9 + 0.2 * hsh(seed, k))
        if L < 3: continue
        col = lerpc(dark, light, frac ** 0.8)
        sway = math.radians(2.2) * math.sin(sway_t * 1.1 + seed * 0.7 + frac * 2) * frac
        for side in (-1, 1):
            a = math.radians(14 + 6 * hsh(seed, k, side)) + sway * side
            ex = x + side * L * math.cos(a); ey = ty + L * math.sin(a)
            cx_ = x + side * L * 0.5 * math.cos(a); cy_ = ty + L * 0.5 * math.sin(a) - L * 0.12
            # foliage body between branch and trunk
            set_col(ctx, lerpc(col, dark, 0.5), alpha * 0.55)
            ctx.move_to(x, ty - L * 0.30); ctx.line_to(ex, ey); ctx.line_to(x, ty + L * 0.34); ctx.close_path(); ctx.fill()
            set_col(ctx, col, alpha); ctx.set_line_width(1.6 + L * 0.045)
            ctx.move_to(x, ty); ctx.curve_to(cx_, cy_, cx_, cy_, ex, ey); ctx.stroke()
            # branchlets
            m = int(L / 6)
            ctx.set_line_width(1.7)
            for j in range(1, m):
                s = j / m
                # point along the quadratic-ish curve
                px = (1 - s) ** 2 * x + 2 * (1 - s) * s * cx_ + s * s * ex
                py = (1 - s) ** 2 * ty + 2 * (1 - s) * s * cy_ + s * s * ey
                bl = L * 0.42 * (1 - s) * (0.7 + 0.5 * hsh(seed, k, j + 7 * side))
                ba = a + math.radians(38) + sway * side
                dx = side * bl * math.cos(ba); dy = bl * math.sin(ba)
                ctx.move_to(px, py); ctx.line_to(px + dx, py + dy)
                ctx.move_to(px, py); ctx.line_to(px + dx * 0.8, py - dy * 0.35)
            ctx.stroke()
    # leader tip
    if Hc > 0.9 * Hf:
        set_col(ctx, light, alpha); ctx.set_line_width(2)
        ctx.move_to(x, base_y - Hc + 6); ctx.line_to(x, base_y - Hc - 6); ctx.stroke()
    ctx.restore()

def seedling(ctx, x, y, s, alpha=1.0):
    """small two-leaf seedling icon, s = scale (px height)"""
    if s <= 0: return
    ctx.save(); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    set_col(ctx, C["g2"], alpha); ctx.set_line_width(max(1.2, s * 0.08))
    ctx.move_to(x, y); ctx.line_to(x, y - s); ctx.stroke()
    set_col(ctx, C["g3"], alpha)
    for side in (-1, 1):
        ctx.move_to(x, y - s * 0.55)
        ctx.curve_to(x + side * s * 0.6, y - s * 0.8, x + side * s * 0.55, y - s * 1.2, x, y - s * 0.95)
        ctx.fill()
    ctx.restore()

# ----------------------------------------------------------------------------- mosaic tree mark
def tree_mask(u, v):
    if abs(u) < 0.075 and v < 0.14: return True
    for vb, va, w in ((0.08, 0.50, 0.95), (0.36, 0.78, 0.72), (0.62, 1.0, 0.48)):
        if vb <= v <= va and abs(u) <= w * (1 - (v - vb) / (va - vb)): return True
    return False

def mosaic_tree(ctx, t, cx, base_y, height, cell=22, gap=4, t_start=0.3, span=2.0, alpha=1.0, half_w=None):
    half_w = half_w or height * 0.54
    step = cell + gap
    nx = int(half_w * 2 / step) + 1; ny = int(height / step) + 1
    for j in range(ny):
        for i in range(nx):
            px = cx - half_w + i * step + step / 2; py = base_y - j * step - step / 2
            u = (px - cx) / half_w; v = (base_y - py) / height
            if not tree_mask(u, v): continue
            h = hsh(i, j, 11)
            ap = t_start + v * span + h * 0.35
            p = seg(t, ap, ap + 0.55)
            if p <= 0: continue
            s = ease_out_back(p, 2.0) * (1 + 0.025 * math.sin(t * 2 + h * 12))
            rot = (1 - ease_out_cubic(p)) * math.pi / 2
            if v < 0.14 and abs(u) < 0.075:
                col = lerpc(C["earth"], C["earth2"], h * 0.5)
            else:
                col = lerpc(C["g1"], C["g3"], v ** 1.1)
                col = lerpc(col, C["g4"], (h - 0.5) * 0.18)
            flash = clamp(1 - p * 1.6)
            col = lerpc(col, C["cream"], flash * 0.8)
            ctx.save(); ctx.translate(px, py); ctx.rotate(rot); ctx.scale(s, s)
            set_col(ctx, col, alpha)
            rrect(ctx, -cell / 2, -cell / 2, cell, cell, cell * 0.18); ctx.fill()
            ctx.restore()

# ----------------------------------------------------------------------------- scene 1: title
def scene_title(ctx, t, T):
    background(ctx, C["bg0"], C["bg1"], T)
    # dawn glow behind tree
    ga = ease_in_out(seg(t, 0.6, 3.0))
    glow(ctx, 960, 330, 620, C["g1"], 0.55 * ga)
    glow(ctx, 960, 300, 260, C["gold"], 0.22 * ga)
    motes(ctx, T, 40)
    mosaic_tree(ctx, t, 960, 640, 520, t_start=0.35, span=1.9)
    # ground line light
    lp = ease_out_expo(seg(t, 1.2, 2.4))
    g = cairo.LinearGradient(960 - 520 * lp, 0, 960 + 520 * lp, 0)
    g.add_color_stop_rgba(0, *C["g3"][:3], 0); g.add_color_stop_rgba(0.5, *C["g3"][:3], 0.8); g.add_color_stop_rgba(1, *C["g3"][:3], 0)
    ctx.set_source(g); ctx.rectangle(960 - 520 * lp, 656, 1040 * lp, 2); ctx.fill()
    # title
    reveal_text(ctx, "MOSAIC", 960, 790, 112, C["cream"], seg(t, 2.4, 3.3), fam="Inter Display ExtraBold", align="center", tracking=14)
    reveal_text(ctx, "FOREST MANAGEMENT", 960, 838, 26, C["g3"], seg(t, 2.9, 3.8), fam="Inter Medium", bold=False, align="center", tracking=9)
    # tagline with cursor line
    p = seg(t, 4.3, 5.4)
    reveal_text(ctx, "Every tree has a plan.", 960, 940, 40, C["cream"], p, fam="Inter Display Light", bold=False, align="center", alpha=0.85)

# ----------------------------------------------------------------------------- scene 2: the mosaic map
_VOR = {}

def build_voronoi():
    if _VOR: return _VOR
    rng = np.random.default_rng(21)
    cx, cy, R = 1290, 585, 350
    pts = []
    n = 12
    for j in range(n):
        for i in range(n):
            x = cx - R + (i + 0.5) * 2 * R / n + rng.uniform(-0.3, 0.3) * 2 * R / n
            y = cy - R + (j + 0.5) * 2 * R / n + rng.uniform(-0.3, 0.3) * 2 * R / n
            pts.append((x, y))
    pts = np.array(pts)
    far = np.array([[cx - 5000, cy - 5000], [cx + 5000, cy - 5000], [cx - 5000, cy + 5000], [cx + 5000, cy + 5000]])
    vor = Voronoi(np.vstack([pts, far]))
    cells = []
    for k, p in enumerate(pts):
        reg = vor.regions[vor.point_region[k]]
        if -1 in reg or not reg: continue
        poly = vor.vertices[reg]
        r = math.hypot(p[0] - cx, p[1] - cy) / R
        # organic blob boundary: cells whose seed is inside
        ang = math.atan2(p[1] - cy, p[0] - cx)
        rb = 0.86 + 0.10 * math.sin(3 * ang + 0.8) + 0.06 * math.sin(5 * ang + 2.1) + 0.04 * math.sin(7 * ang)
        if r > rb: continue
        h = hsh(k, 5)
        cells.append(dict(poly=poly, c=p, r=r, phase=hsh(k, 6), protected=(h < 0.14), kind=k))
    blob = []
    for k in range(160):
        ang = 2 * math.pi * k / 160
        rb = 0.86 + 0.10 * math.sin(3 * ang + 0.8) + 0.06 * math.sin(5 * ang + 2.1) + 0.04 * math.sin(7 * ang)
        blob.append((cx + R * rb * 1.08 * math.cos(ang), cy + R * rb * 1.08 * math.sin(ang)))
    _VOR["cells"] = cells; _VOR["center"] = (cx, cy, R); _VOR["blob"] = blob
    return _VOR

STAGES = [  # (end of stage, color, name)
    (0.10, C["earth"], "Harvested"),
    (0.30, C["lime"], "Newly planted"),
    (0.65, C["g2"], "Growing"),
    (1.00, C["g0"], "Mature"),
]

def stage_color(a):
    """a in [0,1) cyclic age; smooth blend between stage colors"""
    prev_end = 0.0; cols = [s[1] for s in STAGES]
    for i, (end, col, _) in enumerate(STAGES):
        if a < end:
            nxt = cols[(i + 1) % len(cols)]
            f = clamp((a - (end - 0.045)) / 0.045)
            return lerpc(col, nxt, f)
        prev_end = end
    return cols[-1]

def scene_mosaic(ctx, t, T):
    background(ctx, C["bg1"], C["bg0"], T, fog_a=0.10)
    motes(ctx, T, 30, seed=5)
    V = build_voronoi(); cx, cy, R = V["center"]
    # blob shadow / base
    ctx.save()
    sh = ease_out_cubic(seg(t, 0.2, 1.2))
    glow(ctx, cx, cy + 40, R * 1.5, hexc("#000000"), 0.5 * sh)
    blob = V["blob"]; ctx.move_to(*blob[0])
    for q in blob[1:]: ctx.line_to(*q)
    ctx.close_path(); ctx.clip()
    for cell in V["cells"]:
        px, py = cell["c"]
        ap = 0.25 + cell["r"] * 1.4 + hsh(cell["kind"], 8) * 0.35
        p = seg(t, ap, ap + 0.6)
        if p <= 0: continue
        s = ease_out_back(p, 1.6)
        age = (cell["phase"] + t / 9.0) % 1.0
        if cell["protected"]:
            col = C["teal2"]
        else:
            col = stage_color(age)
        col = lerpc(col, C["cream"], clamp(1 - p * 2) * 0.7)
        ctx.save(); ctx.translate(px, py); ctx.scale(s, s); ctx.translate(-px, -py)
        poly = cell["poly"]
        ctx.move_to(*poly[0])
        for q in poly[1:]: ctx.line_to(*q)
        ctx.close_path()
        set_col(ctx, col); ctx.fill_preserve()
        set_col(ctx, C["bg0"], 0.9); ctx.set_line_width(5); ctx.set_line_join(cairo.LINE_JOIN_ROUND); ctx.stroke()
        # inside detail: mini conifers scaling with age, hatch for protected
        if cell["protected"]:
            ctx.move_to(*poly[0])
            for q in poly[1:]: ctx.line_to(*q)
            ctx.close_path(); ctx.clip()
            set_col(ctx, C["teal"], 0.45); ctx.set_line_width(1.5)
            for d in range(-700, 700, 14):
                ctx.move_to(px + d, py - 300); ctx.line_to(px + d + 300, py + 300)
            ctx.stroke()
        else:
            if age > 0.10:
                gsz = 6 + 26 * clamp((age - 0.10) / 0.75)
                for m in range(3):
                    ox = (hsh(cell["kind"], 30 + m) - 0.5) * 34; oy = (hsh(cell["kind"], 40 + m) - 0.5) * 24
                    hh = gsz * (0.7 + 0.5 * hsh(cell["kind"], 50 + m))
                    set_col(ctx, lerpc(C["g1"], C["bg0"], 0.35), 0.9)
                    ctx.move_to(px + ox - hh * 0.36, py + oy + 6); ctx.line_to(px + ox, py + oy - hh); ctx.line_to(px + ox + hh * 0.36, py + oy + 6); ctx.close_path(); ctx.fill()
            else:
                # fresh cut: stumps
                set_col(ctx, C["earth2"], 0.9)
                for m in range(4):
                    ox = (hsh(cell["kind"], 60 + m) - 0.5) * 40; oy = (hsh(cell["kind"], 70 + m) - 0.5) * 30
                    ctx.arc(px + ox, py + oy, 2.6, 0, 2 * math.pi); ctx.fill()
        ctx.restore()
    ctx.restore()
    # headline
    reveal_text(ctx, "One forest.", 120, 330, 96, C["cream"], seg(t, 0.3, 1.1), fam="Inter Display ExtraBold")
    reveal_text(ctx, "Many ages.", 120, 440, 96, C["g3"], seg(t, 0.7, 1.5), fam="Inter Display ExtraBold")
    reveal_text(ctx, "Small patches on their own clocks,", 120, 530, 32, C["cream"], seg(t, 1.5, 2.3), fam="Inter Light", bold=False, alpha=0.85)
    reveal_text(ctx, "so the whole forest is never all one age.", 120, 575, 32, C["cream"], seg(t, 1.7, 2.5), fam="Inter Light", bold=False, alpha=0.85)
    # legend
    items = [(s[1], s[2]) for s in STAGES] + [(C["teal2"], "Protected")]
    for i, (col, name) in enumerate(items):
        p = seg(t, 2.6 + i * 0.16, 3.2 + i * 0.16)
        if p <= 0: continue
        e = ease_out_back(p)
        y = 700 + i * 48
        ctx.save(); ctx.translate(120 + 14, y); ctx.scale(e, e)
        set_col(ctx, col); rrect(ctx, -14, -14, 28, 28, 6); ctx.fill()
        ctx.restore()
        text(ctx, name, 162, y + 8, 24, C["cream"], fam="Inter Medium", bold=False, alpha=0.9 * ease_out_cubic(p))
    # small caption on right
    reveal_text(ctx, "ONE MANAGED LANDSCAPE  •  DECADES OF PLANNING", cx, cy + R + 95, 16, C["mute"], seg(t, 3.4, 4.2), fam="Inter Medium", bold=False, align="center", tracking=4, alpha=0.8)

# ----------------------------------------------------------------------------- scene 3: plant
def hills(ctx, t, y0=840):
    for layer, (amp, freq, col, off) in enumerate([(60, 0.0032, lerpc(C["bg2"], C["bg0"], 0.2), 0), (44, 0.0048, lerpc(C["g0"], C["bg0"], 0.45), 40), (30, 0.007, lerpc(C["g0"], C["bg0"], 0.25), 78)]):
        ctx.move_to(-10, H + 10)
        for x in range(-10, W + 40, 24):
            y = y0 + off + amp * math.sin(x * freq + layer * 1.7) + amp * 0.5 * math.sin(x * freq * 2.3 + 0.5)
            ctx.line_to(x, y)
        ctx.line_to(W + 10, H + 10); ctx.close_path()
        set_col(ctx, col); ctx.fill()

def scene_plant(ctx, t, T):
    # dawn sky
    ctx.set_source(vgrad(ctx, [(0, C["bg0"]), (0.55, C["bg2"]), (0.86, hexc("#3f6a4a")), (1, hexc("#7d6a3c"))])); ctx.paint()
    glow(ctx, 1500, 860, 700, C["gold"], 0.35 * ease_in_out(seg(t, 0.2, 2.5)))
    fog(ctx, T, 0.12); motes(ctx, T, 35, seed=8, color=C["gold"])
    hills(ctx, t)
    # trees in rows (back row small, front row big)
    rows = [(905, 0.7, 9, 0.0), (955, 1.0, 7, 0.5), (1015, 1.45, 5, 1.0)]
    for ri, (by, sc, n, delay) in enumerate(rows):
        for i in range(n):
            x = 200 + (W - 400) * (i + 0.5) / n + (hsh(ri, i) - 0.5) * 120
            x += 150 if ri == 2 else 0
            if ri == 2 and x > 1500: continue
            start = 0.6 + delay + i * 0.22 + hsh(ri, i, 3) * 0.3
            g = ease_out_cubic(seg(t, start, start + 6.0))
            # seedling first, then conifer
            if g < 0.08:
                seedling(ctx, x, by, 30 * sc * ease_out_back(seg(g, 0, 0.05)))
            else:
                conifer(ctx, x, by, 300 * sc, clamp((g - 0.05) / 0.95), seed=ri * 17 + i, sway_t=T,
                        dark=lerpc(C["g0"], C["bg0"], 0.3 * (2 - ri)), light=lerpc(C["g2"], C["bg1"], 0.25 * (2 - ri)))
    # foreground seedling pop line
    for i in range(30):
        x = 40 + i * 66; p = seg(t, 1.2 + i * 0.07, 1.6 + i * 0.07)
        if p > 0: seedling(ctx, x, 1055, 22 * ease_out_back(p) * (1 + 0.3 * hsh(i, 2)))
    # panel text
    ctx.save()
    ctx.set_source(vgrad(ctx, [(0, hexc("#050f0c", 0.85)), (1, hexc("#050f0c", 0))], 0, 0, 0, 780)); ctx.rectangle(0, 0, W, 780); ctx.fill()
    ctx.restore()
    reveal_text(ctx, "Plant.", 120, 300, 130, C["cream"], seg(t, 0.3, 1.2), fam="Inter Display ExtraBold")
    reveal_text(ctx, "Every harvested hectare is replanted —", 120, 380, 34, C["cream"], seg(t, 1.0, 1.9), fam="Inter Light", bold=False, alpha=0.9)
    reveal_text(ctx, "native species, grown from local seed.", 120, 426, 34, C["g3"], seg(t, 1.2, 2.1), fam="Inter Light", bold=False, alpha=0.95)
    # counter: seedlings on screen equivalent -> 'trees per tree' chip
    p = seg(t, 2.6, 3.4)
    if p > 0:
        e = ease_out_back(p)
        ctx.save(); ctx.translate(120, 480); ctx.scale(e, 1)
        set_col(ctx, C["g3"], 0.12); rrect(ctx, 0, 0, 640, 120, 26); ctx.fill()
        set_col(ctx, C["g3"], 0.6); ctx.set_line_width(1.5); rrect(ctx, 0, 0, 640, 120, 26); ctx.stroke()
        n = int(round(ease_out_expo(seg(t, 2.8, 5.5)) * 100))
        text(ctx, f"{n}%", 30, 84, 76, C["g4"], fam="Inter Display ExtraBold")
        text(ctx, "OF HARVESTED AREA REPLANTED", 250, 54, 19, C["cream"], fam="Inter Medium", bold=False, tracking=3)
        text(ctx, "USUALLY WITHIN TWO SEASONS", 250, 84, 19, C["mute"], fam="Inter Medium", bold=False, tracking=3, alpha=0.8)
        ctx.restore()

# ----------------------------------------------------------------------------- scene 4: grow (cycle ring)
PHASES = [(0.00, 0.08, "Plant", C["lime"]), (0.08, 0.50, "Grow", C["g2"]), (0.50, 0.72, "Thin", C["teal"]),
          (0.72, 0.86, "Harvest", C["amber"]), (0.86, 1.00, "Replant", C["g3"])]

def scene_grow(ctx, t, T):
    background(ctx, C["bg0"], C["bg2"], T, fog_a=0.10)
    motes(ctx, T, 30, seed=13)
    cx, cy, r = 1270, 570, 300
    prog = ease_in_out(seg(t, 0.9, 1.2)) * 0 + clamp((t - 1.0) / 8.8)
    ring_in = ease_out_cubic(seg(t, 0.2, 1.2))
    glow(ctx, cx, cy, r * 1.6, C["g1"], 0.35 * ring_in)
    # ticks (years)
    ctx.save(); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for k in range(60):
        a = -math.pi / 2 + 2 * math.pi * k / 60
        pk = seg(ring_in, k / 60 * 0.8, k / 60 * 0.8 + 0.2)
        if pk <= 0: continue
        r0 = r + 34; r1 = r + (48 if k % 10 == 0 else 40)
        set_col(ctx, C["cream"], (0.55 if k % 10 == 0 else 0.22) * pk)
        ctx.set_line_width(2); ctx.move_to(cx + r0 * math.cos(a), cy + r0 * math.sin(a)); ctx.line_to(cx + r1 * math.cos(a), cy + r1 * math.sin(a)); ctx.stroke()
    ctx.restore()
    # base ring segments
    gap = 0.012
    ctx.set_line_width(26)
    for (a0, a1, name, col) in PHASES:
        s0 = -math.pi / 2 + 2 * math.pi * (a0 + gap) ; s1 = -math.pi / 2 + 2 * math.pi * (a1 - gap)
        s1 = s0 + (s1 - s0) * ring_in
        set_col(ctx, col, 0.18); ctx.arc(cx, cy, r, s0, s1); ctx.stroke()
        # filled
        fe = clamp((prog - a0) / (a1 - a0))
        if fe > 0:
            f1 = s0 + (s1 - s0) * fe
            set_col(ctx, col, 0.95); ctx.arc(cx, cy, r, s0, f1); ctx.stroke()
        # label
        am = -math.pi / 2 + 2 * math.pi * (a0 + a1) / 2
        lx, ly = cx + (r + 82) * math.cos(am), cy + (r + 82) * math.sin(am)
        active = a0 <= prog < a1
        lp = seg(ring_in, 0.5, 1.0)
        text(ctx, name.upper(), lx, ly + 7, 19 if not active else 22, col if active else C["mute"],
             fam="Inter SemiBold" if active else "Inter Medium", bold=False, align="center", tracking=3, alpha=lp * (1 if active else 0.75))
    # pointer
    pa = -math.pi / 2 + 2 * math.pi * prog
    px, py = cx + r * math.cos(pa), cy + r * math.sin(pa)
    glow(ctx, px, py, 60, C["cream"], 0.6 * ring_in)
    set_col(ctx, C["cream"], ring_in); ctx.arc(px, py, 11, 0, 2 * math.pi); ctx.fill()
    # inner scene: tree cycle
    ctx.save()
    ctx.arc(cx, cy, r - 22, 0, 2 * math.pi); ctx.clip()
    set_col(ctx, C["bg0"], 0.35 * ring_in); ctx.paint()
    ground = cy + 150
    set_col(ctx, lerpc(C["earth2"], C["bg0"], 0.4), ring_in); ctx.rectangle(cx - r, ground, 2 * r, r); ctx.fill()
    if prog < 0.72:
        g = clamp(prog / 0.72)
        conifer(ctx, cx, ground, 285, g ** 0.9, seed=99, sway_t=T)
        for sd, ox, sc in ((3, -105, 0.62), (4, 108, 0.66)):
            thin = clamp((prog - 0.50) / 0.10)
            conifer(ctx, cx + ox, ground + 10, 285 * sc, g ** 0.9, seed=sd, sway_t=T, alpha=1 - thin)
    elif prog < 0.86:
        f = clamp((prog - 0.72) / 0.14)
        conifer(ctx, cx, ground, 285, 1.0, seed=99, sway_t=T, alpha=1 - ease_in_out(f))
        set_col(ctx, C["earth2"]); rrect(ctx, cx - 8, ground - 12 * f, 16, 12 * f, 3); ctx.fill()
        # logs
        for m in range(3):
            lp = seg(f, 0.4 + m * 0.15, 0.7 + m * 0.15)
            if lp > 0:
                set_col(ctx, C["earth"], lp); rrect(ctx, cx - 120 + m * 60, ground - 14 + (1 - ease_out_back(lp)) * -40, 46, 14, 7); ctx.fill()
    else:
        f = clamp((prog - 0.86) / 0.14)
        set_col(ctx, C["earth2"]); rrect(ctx, cx - 8, ground - 12, 16, 12, 3); ctx.fill()
        for m, ox in enumerate((-70, 0, 70)):
            sp = seg(f, m * 0.2, m * 0.2 + 0.6)
            seedling(ctx, cx + ox, ground, 40 * ease_out_back(sp))
    ctx.restore()
    # ring outline
    set_col(ctx, C["cream"], 0.12 * ring_in); ctx.set_line_width(1.5); ctx.arc(cx, cy, r - 22, 0, 2 * math.pi); ctx.stroke()
    # left column
    reveal_text(ctx, "Grow.", 120, 300, 130, C["cream"], seg(t, 0.3, 1.2), fam="Inter Display ExtraBold")
    reveal_text(ctx, "A rotation planned decades ahead,", 120, 380, 34, C["cream"], seg(t, 1.0, 1.9), fam="Inter Light", bold=False, alpha=0.9)
    reveal_text(ctx, "one patch at a time.", 120, 426, 34, C["g3"], seg(t, 1.2, 2.1), fam="Inter Light", bold=False, alpha=0.95)
    yp = seg(t, 1.6, 2.4)
    if yp > 0:
        year = int(round(prog * 60))
        text(ctx, "YEAR", 122, 560, 18, C["mute"], fam="Inter Medium", bold=False, tracking=5, alpha=yp)
        text(ctx, f"{year:02d}", 116, 720, 190, C["cream"], fam="Inter Display Black", alpha=yp)
        for (a0, a1, name, col) in PHASES:
            if a0 <= prog < a1 or (prog >= 1 and a1 == 1):
                ph = clamp((prog - a0) / 0.06)
                text(ctx, name.upper(), 124, 790, 30, col, fam="Inter SemiBold", bold=False, tracking=8, alpha=yp * ease_out_cubic(ph))

# ----------------------------------------------------------------------------- scene 5: protect (carbon)
def leaf_icon(ctx, x, y, s, col, a=1.0):
    set_col(ctx, col, a)
    ctx.move_to(x - s, y + s * 0.6); ctx.curve_to(x - s, y - s * 0.9, x + s * 0.5, y - s, x + s, y - s)
    ctx.curve_to(x + s, y + 0.5 * s, x - 0.1 * s, y + s, x - s, y + s * 0.6); ctx.fill()
    ctx.set_line_width(max(1, s * 0.12)); ctx.move_to(x - s, y + s * 0.6); ctx.line_to(x + s * 0.7, y - s * 0.7); ctx.stroke()

def drop_icon(ctx, x, y, s, col, a=1.0):
    set_col(ctx, col, a)
    ctx.move_to(x, y - s); ctx.curve_to(x + s * 0.9, y + s * 0.1, x + s * 0.8, y + s, x, y + s)
    ctx.curve_to(x - s * 0.8, y + s, x - s * 0.9, y + s * 0.1, x, y - s); ctx.fill()

def bird_icon(ctx, x, y, s, col, a=1.0):
    set_col(ctx, col, a); ctx.set_line_width(max(1.5, s * 0.16)); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.move_to(x - s, y); ctx.curve_to(x - s * 0.5, y - s * 0.9, x - s * 0.2, y - s * 0.9, x, y - s * 0.1)
    ctx.curve_to(x + s * 0.2, y - s * 0.9, x + s * 0.5, y - s * 0.9, x + s, y); ctx.stroke()

def river(ctx, t, y0=905):
    ctx.save()
    ctx.move_to(-10, H + 10)
    for x in range(-10, W + 40, 16):
        ctx.line_to(x, y0 + 26 * math.sin(x * 0.006 + t * 0.9) + 10 * math.sin(x * 0.017 - t * 1.4))
    ctx.line_to(W + 10, H + 10); ctx.close_path()
    ctx.set_source(vgrad(ctx, [(0, C["teal2"]), (1, lerpc(C["teal2"], C["bg0"], 0.7))], 0, y0 - 30, 0, H)); ctx.fill()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_width(2.5)
    for k in range(3):
        set_col(ctx, C["sky"], 0.35 - k * 0.08)
        ctx.set_dash([60 + 30 * k, 90 + 40 * k], -t * (120 + 40 * k))
        yy = y0 + 40 + k * 38
        ctx.move_to(-10, yy)
        for x in range(-10, W + 40, 16):
            ctx.line_to(x, yy + 14 * math.sin(x * 0.007 + t * 1.1 + k))
        ctx.stroke()
    ctx.restore()

def scene_protect(ctx, t, T):
    background(ctx, C["bg0"], C["bg2"], T, fog_a=0.12)
    motes(ctx, T, 30, seed=17)
    tx, ty, th = 1380, 870, 560
    grow = ease_out_cubic(seg(t, 0.1, 1.6))
    # particles: CO2 -> leaves
    N = 150
    arrived = 0
    canopy = []
    for i in range(N):
        s = 0.5 + i * 0.052; d = 2.0 + hsh(i, 21) * 1.4
        p = (t - s) / d
        if p < 0: continue
        h = 0.18 + 0.75 * hsh(i, 22)
        tw = 0.30 * th * (1 - h) * 0.95
        gx = tx + (hsh(i, 23) * 2 - 1) * tw; gy = ty - h * th
        canopy.append((gx, gy, i))
        if p >= 1:
            arrived += 1; continue
        # start on left or top
        if hsh(i, 24) < 0.7:
            sx, sy = -40, 120 + hsh(i, 25) * 760
        else:
            sx, sy = hsh(i, 25) * 1100, -40
        mx, my = (sx + gx) / 2, (sy + gy) / 2
        nx_, ny_ = -(gy - sy), (gx - sx); ln = math.hypot(nx_, ny_) or 1
        off = (hsh(i, 26) - 0.5) * 520
        cx_, cy_ = mx + nx_ / ln * off, my + ny_ / ln * off
        e = ease_in_out(p)
        x = (1 - e) ** 2 * sx + 2 * (1 - e) * e * cx_ + e * e * gx
        y = (1 - e) ** 2 * sy + 2 * (1 - e) * e * cy_ + e * e * gy
        fade = clamp(p * 6) * clamp((1 - p) * 4)
        rad = 13 * (1 - 0.5 * clamp((p - 0.85) / 0.15))
        set_col(ctx, C["mute"], 0.10 * fade); ctx.arc(x, y, rad, 0, 2 * math.pi); ctx.fill()
        set_col(ctx, C["sky"], 0.7 * fade); ctx.set_line_width(1.3); ctx.arc(x, y, rad, 0, 2 * math.pi); ctx.stroke()
        text(ctx, "CO₂", x, y + 4, 11, C["cream"], fam="Inter SemiBold", bold=False, align="center", alpha=0.9 * fade)
    # tree with canopy glow that intensifies as carbon arrives
    glow(ctx, tx, ty - th * 0.5, th * 0.8, C["g2"], 0.25 + 0.35 * arrived / N)
    hills(ctx, t, y0=860)
    conifer(ctx, tx, ty, th, grow, seed=5, sway_t=T, tiers=16)
    # stuck leaves
    for gx, gy, i in canopy:
        s = 0.5 + i * 0.052; d = 2.0 + hsh(i, 21) * 1.4
        p = (t - s) / d
        if p < 1: continue
        pop = ease_out_back(seg(p, 1.0, 1.25), 2.5)
        pulse = 0.75 + 0.25 * math.sin(T * 2.5 + i)
        glow(ctx, gx, gy, 14 * pop, C["g3"], 0.35 * pulse)
        set_col(ctx, lerpc(C["g3"], C["g4"], hsh(i, 27)), 0.95); ctx.arc(gx, gy, 4.2 * pop, 0, 2 * math.pi); ctx.fill()
    river(ctx, T)
    # left column
    ctx.save()
    ctx.set_source(vgrad(ctx, [(0, hexc("#050f0c", 0.7)), (1, hexc("#050f0c", 0))], 0, 0, 900, 0)); ctx.rectangle(0, 0, 900, 880); ctx.fill()
    ctx.restore()
    reveal_text(ctx, "Protect.", 120, 300, 130, C["cream"], seg(t, 0.3, 1.2), fam="Inter Display ExtraBold")
    reveal_text(ctx, "Working forests that keep working", 120, 380, 34, C["cream"], seg(t, 1.0, 1.9), fam="Inter Light", bold=False, alpha=0.9)
    reveal_text(ctx, "for the climate, the water and the wild.", 120, 426, 34, C["g3"], seg(t, 1.2, 2.1), fam="Inter Light", bold=False, alpha=0.95)
    items = [(leaf_icon, C["g3"], "Carbon", "captured in every growing tree"),
             (drop_icon, C["sky"], "Water", "streams buffered by standing forest"),
             (bird_icon, C["gold"], "Habitat", "old growth and wildlife areas conserved")]
    for k, (icon, col, title, sub) in enumerate(items):
        p = seg(t, 2.4 + k * 0.45, 3.1 + k * 0.45)
        if p <= 0: continue
        e = ease_out_back(p); y = 520 + k * 104
        ctx.save(); ctx.translate(150, y); ctx.scale(e, e)
        set_col(ctx, col, 0.15); ctx.arc(0, 0, 34, 0, 2 * math.pi); ctx.fill()
        set_col(ctx, col, 0.7); ctx.set_line_width(1.5); ctx.arc(0, 0, 34, 0, 2 * math.pi); ctx.stroke()
        icon(ctx, 0, 0, 15, col)
        ctx.restore()
        text(ctx, title, 210, y - 2, 30, C["cream"], fam="Inter SemiBold", bold=False, alpha=ease_out_cubic(p))
        text(ctx, sub, 210, y + 30, 21, C["mute"], fam="Inter Regular", bold=False, alpha=0.85 * ease_out_cubic(p))

# ----------------------------------------------------------------------------- scene 6: share
TRAIL = [(-60, 820), (300, 900), (520, 560), (760, 520), (1000, 760), (1250, 700), (1500, 330), (1980, 260)]

def trail_point(u):
    """catmull-rom through TRAIL, u in [0,1]"""
    P = TRAIL; n = len(P) - 1
    u = clamp(u) * n; i = min(int(u), n - 1); f = u - i
    p0 = P[max(i - 1, 0)]; p1 = P[i]; p2 = P[i + 1]; p3 = P[min(i + 2, n)]
    out = []
    for k in range(2):
        a, b, c, d = p0[k], p1[k], p2[k], p3[k]
        out.append(0.5 * ((2 * b) + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f + (-a + 3 * b - 3 * c + d) * f ** 3))
    return out

def scene_share(ctx, t, T):
    background(ctx, C["bg1"], C["bg0"], T, fog_a=0.10)
    motes(ctx, T, 30, seed=23)
    # background forest silhouettes
    for i in range(22):
        x = i * 95 + (hsh(i, 31) - 0.5) * 60; sc = 0.45 + 0.4 * hsh(i, 32)
        conifer(ctx, x, 880 + 30 * hsh(i, 33), 240 * sc, 1.0, seed=200 + i, sway_t=T, alpha=0.5,
                dark=lerpc(C["g0"], C["bg0"], 0.6), light=lerpc(C["g1"], C["bg0"], 0.5), tiers=10)
    hills(ctx, t, y0=880)
    # trail
    draw = ease_in_out(seg(t, 0.4, 3.6))
    ctx.save(); ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    steps = 260
    ctx.move_to(*trail_point(0))
    for k in range(1, int(steps * draw) + 1):
        ctx.line_to(*trail_point(k / steps))
    set_col(ctx, C["cream"], 0.12); ctx.set_line_width(18); ctx.stroke_preserve()
    set_col(ctx, C["cream"], 0.85); ctx.set_line_width(5); ctx.set_dash([18, 16], -T * 40); ctx.stroke()
    ctx.restore()
    # markers
    marks = [(0.16, "Campsites", "tent"), (0.40, "Trails", "hiker"), (0.62, "Viewpoints", "view"), (0.85, "Partnerships", "people")]
    for (u, label, kind) in marks:
        p = seg(draw, u, u + 0.08)
        if p <= 0: continue
        e = ease_out_back(p, 2.2); x, y = trail_point(u); y -= 70
        ctx.save(); ctx.translate(x, y); ctx.scale(e, e)
        glow(ctx, 0, 0, 90, C["g3"], 0.35)
        set_col(ctx, C["g1"]); ctx.arc(0, 0, 38, 0, 2 * math.pi); ctx.fill()
        set_col(ctx, C["g4"]); ctx.set_line_width(2.5); ctx.arc(0, 0, 38, 0, 2 * math.pi); ctx.stroke()
        # stem
        ctx.move_to(0, 38); ctx.line_to(0, 62); ctx.stroke()
        set_col(ctx, C["cream"]); ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_width(3)
        if kind == "tent":
            ctx.move_to(-20, 14); ctx.line_to(0, -16); ctx.line_to(20, 14); ctx.close_path(); ctx.stroke()
            ctx.move_to(0, -16); ctx.line_to(0, 14); ctx.stroke()
        elif kind == "hiker":
            ctx.arc(2, -16, 5, 0, 2 * math.pi); ctx.fill()
            ctx.move_to(2, -9); ctx.line_to(-2, 4); ctx.line_to(-9, 16); ctx.move_to(-2, 4); ctx.line_to(8, 12); ctx.line_to(6, 18)
            ctx.move_to(0, -4); ctx.line_to(12, 2); ctx.move_to(0, -4); ctx.line_to(-12, 0); ctx.line_to(-14, 16); ctx.stroke()
        elif kind == "view":
            ctx.arc(-9, 2, 8, 0, 2 * math.pi); ctx.stroke(); ctx.arc(9, 2, 8, 0, 2 * math.pi); ctx.stroke()
            ctx.move_to(-5, -8); ctx.line_to(-5, -14); ctx.line_to(5, -14); ctx.line_to(5, -8); ctx.stroke()
        else:
            for ox, sc in ((-14, 0.8), (14, 0.8), (0, 1.0)):
                ctx.arc(ox, -10 * sc, 5 * sc, 0, 2 * math.pi); ctx.fill()
                rrect(ctx, ox - 8 * sc, -2 * sc, 16 * sc, 18 * sc, 6 * sc); ctx.fill()
        ctx.restore()
        text(ctx, label, x, y + 100, 22, C["cream"], fam="Inter SemiBold", bold=False, align="center", alpha=ease_out_cubic(p))
    ctx.save()
    ctx.set_source(vgrad(ctx, [(0, hexc("#050f0c", 0.8)), (1, hexc("#050f0c", 0))], 0, 0, 0, 420)); ctx.rectangle(0, 0, W, 420); ctx.fill()
    ctx.restore()
    reveal_text(ctx, "Share.", 120, 200, 110, C["cream"], seg(t, 0.3, 1.2), fam="Inter Display ExtraBold")
    reveal_text(ctx, "Open trails, campsites and partnerships with communities and First Nations.", 120, 262, 30, C["cream"], seg(t, 0.9, 1.8), fam="Inter Light", bold=False, alpha=0.9)

# ----------------------------------------------------------------------------- scene 7: outro
def scene_outro(ctx, t, T):
    background(ctx, C["bg0"], C["bg1"], T, fog_a=0.12)
    glow(ctx, 960, 470, 520, C["g1"], 0.45 * ease_in_out(seg(t, 0.0, 1.2)))
    motes(ctx, T, 40)
    mosaic_tree(ctx, t + 0.4, 960, 560, 300, cell=14, gap=3, t_start=0.0, span=1.0)
    reveal_text(ctx, "MOSAIC", 960, 690, 92, C["cream"], seg(t, 0.9, 1.7), fam="Inter Display ExtraBold", align="center", tracking=12)
    reveal_text(ctx, "FOREST MANAGEMENT", 960, 732, 22, C["g3"], seg(t, 1.2, 2.0), fam="Inter Medium", bold=False, align="center", tracking=8)
    reveal_text(ctx, "Plant.  Grow.  Protect.  Share.", 960, 830, 34, C["cream"], seg(t, 1.6, 2.5), fam="Inter Display Light", bold=False, align="center", alpha=0.8)
    reveal_text(ctx, "mosaicforests.com", 960, 900, 26, C["g4"], seg(t, 2.0, 2.8), fam="Inter Medium", bold=False, align="center", tracking=3)
    # fade to black
    fo = seg(t, 4.0 - 0.9, 4.0)
    if fo > 0:
        set_col(ctx, C["bg0"], ease_in_out(fo)); ctx.paint()

# ----------------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 8.0, scene_title),
    (8.0, 19.0, scene_mosaic),
    (19.0, 30.0, scene_plant),
    (30.0, 41.0, scene_grow),
    (41.0, 51.0, scene_protect),
    (51.0, 56.0, scene_share),
    (56.0, 60.0, scene_outro),
]
TRANS = 0.8  # mosaic wipe duration around each cut

def render_scene(idx, T, surf_cache):
    s0, s1, fn = SCENES[idx]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    fn(ctx, T - s0, T)
    return surf

def mosaic_wipe(ctx, surfA, surfB, p, cell=64):
    """A -> B via tiles flipping in a diagonal sweep with an accent flash"""
    ctx.set_source_surface(surfA, 0, 0); ctx.paint()
    nx, ny = W // cell + 1, H // cell + 1
    for j in range(ny):
        for i in range(nx):
            thr = ((i + j) / (nx + ny)) * 0.62 + hsh(i, j, 77) * 0.25
            s = seg(p, thr, thr + 0.13)
            if s <= 0: continue
            e = ease_out_cubic(s)
            x, y = i * cell + cell / 2, j * cell + cell / 2
            ctx.save()
            ctx.translate(x, y); ctx.scale(e, e); ctx.translate(-x, -y)
            ctx.rectangle(i * cell - 0.5, j * cell - 0.5, cell + 1, cell + 1); ctx.clip()
            ctx.set_source_surface(surfB, 0, 0); ctx.paint()
            fl = clamp(1 - s * 1.5)
            if fl > 0:
                set_col(ctx, C["g3"], fl * 0.85); ctx.paint()
            ctx.restore()

def render_frame(fi, scale=1.0):
    T = fi / FPS
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(W * scale), int(H * scale))
    ctx = cairo.Context(surf)
    ctx.scale(scale, scale)
    idx = max(i for i, (s0, s1, _) in enumerate(SCENES) if T >= s0)
    cut = SCENES[idx][0]
    nxt = SCENES[idx + 1][0] if idx + 1 < len(SCENES) else None
    if idx > 0 and T < cut + TRANS / 2:
        # finishing a wipe into this scene
        A = render_scene(idx - 1, T, None); B = render_scene(idx, T, None)
        mosaic_wipe(ctx, A, B, (T - (cut - TRANS / 2)) / TRANS)
    elif nxt is not None and T >= nxt - TRANS / 2:
        A = render_scene(idx, T, None); B = render_scene(idx + 1, T, None)
        mosaic_wipe(ctx, A, B, (T - (nxt - TRANS / 2)) / TRANS)
    else:
        SCENES[idx][2](ctx, T - cut, T)
    vignette(ctx)
    grain(ctx, fi)
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
        surf = render_frame(fi, scale)
        proc.stdin.write(bytes(surf.get_data()))
        if k == 0 and fi % 30 == 0:
            print(f"  chunk0 frame {fi}/{f1}", flush=True)
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
        frames = a.stills or list(range(0, NFRAMES, 45))
        for fi in frames:
            p = os.path.join(OUT, f"still_{fi:04d}.png")
            render_frame(fi, a.scale).write_to_png(p); print(p)
        return
    n = a.workers
    bounds = [round(i * NFRAMES / n) for i in range(n + 1)]
    jobs = [(k, bounds[k], bounds[k + 1], a.scale) for k in range(n)]
    with Pool(n) as pool:
        segs = pool.map(encode_chunk, jobs)
    lst = os.path.join(OUT, "segs.txt")
    with open(lst, "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    subprocess.check_call([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", a.out])
    for s in segs: os.remove(s)
    os.remove(lst)
    print("wrote", a.out)

if __name__ == "__main__":
    main()
