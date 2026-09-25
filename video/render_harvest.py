#!/usr/bin/env python3
"""
Mosaic — "Stump to road": an educational explainer on ground-based, cable and tethered
harvesting, piece-size economics, mobilisation cost and machine connectivity.
Reuses the brand system from render.py (palette, contours, Jost, wordmark, wipes, encoder).

    python render_harvest.py                 # -> out/harvest_video.mp4
    python render_harvest.py --stills 300 900 --scale 0.5
"""
import math
import os

import cairo
import render as R
from render import (C, W, H, GRAD, gradc, hexc, lerp, lerpc, clamp, seg, hsh, ease_out_cubic, ease_in_out, ease_out_expo,
                    ease_out_back, set_col, text, reveal_text, eyebrow, rrect, vgrad, glow, contours, paper_bg, taupe_bg,
                    conifer, wordmark, icon, font, text_width)

NAVY = C["navy"]

# ============================================================================= drawing helpers
def stroke_fill(ctx, fill, line=NAVY, lw=2.5, alpha=1.0):
    set_col(ctx, fill, alpha); ctx.fill_preserve(); set_col(ctx, line, alpha); ctx.set_line_width(lw); ctx.stroke()

def tracks(ctx, x, y, w, h, alpha=1.0, roll=0.0):
    """crawler undercarriage, bottom-centre at (x, y); roll shifts the roller dots so the track reads as moving"""
    rrect(ctx, x - w / 2, y - h, w, h, h / 2); stroke_fill(ctx, NAVY, alpha=alpha)
    set_col(ctx, C["paper"], 0.9 * alpha)
    ctx.save(); rrect(ctx, x - w / 2 + h * 0.3, y - h, w - h * 0.6, h, h / 2); ctx.clip()
    n = int(w / (h * 0.9)) + 1; step = (w - h) / max(1, n - 1)
    for i in range(n + 1):
        cx = x - w / 2 + h / 2 + ((i * step + roll) % ((n) * step)) - step * 0.5
        ctx.new_path(); ctx.arc(cx, y - h / 2, h * 0.22, 0, 2 * math.pi); ctx.fill()
    ctx.restore()

def wheel(ctx, x, y, r, alpha=1.0):
    ctx.new_path(); ctx.arc(x, y, r, 0, 2 * math.pi); stroke_fill(ctx, NAVY, alpha=alpha)
    set_col(ctx, C["paper"], alpha); ctx.new_path(); ctx.arc(x, y, r * 0.45, 0, 2 * math.pi); ctx.fill()

def cab(ctx, x, y, w, h, accent, alpha=1.0):
    rrect(ctx, x, y - h, w, h, 6); stroke_fill(ctx, C["paper"], alpha=alpha)
    rrect(ctx, x + w * 0.12, y - h * 0.9, w * 0.76, h * 0.5, 4); set_col(ctx, accent, 0.85 * alpha); ctx.fill()

def body(ctx, x, y, w, h, alpha=1.0):
    rrect(ctx, x, y - h, w, h, 5); stroke_fill(ctx, C["paper2"], alpha=alpha)

def boom(ctx, pts, lw=9, alpha=1.0):
    """articulated boom through pts"""
    ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.move_to(*pts[0])
    for p in pts[1:]: ctx.line_to(*p)
    set_col(ctx, NAVY, alpha); ctx.set_line_width(lw); ctx.stroke()
    ctx.move_to(*pts[0])
    for p in pts[1:]: ctx.line_to(*p)
    set_col(ctx, C["paper"], alpha); ctx.set_line_width(lw * 0.45); ctx.stroke()
    for p in pts: ctx.new_path(); ctx.arc(p[0], p[1], lw * 0.55, 0, 2 * math.pi); set_col(ctx, NAVY, alpha); ctx.fill()

def log(ctx, x, y, L, d, ang=0.0, alpha=1.0, col=None):
    """a log centred at (x, y), length L, diameter d, rotated ang"""
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang)
    rrect(ctx, -L / 2, -d / 2, L, d, d / 2); stroke_fill(ctx, col or C["earth"], lw=1.8, alpha=alpha)
    set_col(ctx, NAVY, 0.5 * alpha); ctx.new_path(); ctx.arc(-L / 2 + d / 2, 0, d * 0.22, 0, 2 * math.pi); ctx.fill()
    ctx.restore()

def cable(ctx, p0, p1, sag=0.0, lw=2.2, col=NAVY, alpha=1.0, dash=None):
    ctx.save()
    if dash: ctx.set_dash(dash[0], dash[1])
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 + sag
    ctx.move_to(*p0); ctx.curve_to(mx, my, mx, my, *p1)
    set_col(ctx, col, alpha); ctx.set_line_width(lw); ctx.stroke(); ctx.restore()

def stump(ctx, x, y, s=9, alpha=1.0):
    rrect(ctx, x - s / 2, y - s * 0.8, s, s * 0.8, 2); stroke_fill(ctx, hexc("#8a7a5a"), lw=1.5, alpha=alpha)

def label_tag(ctx, x, y, s, p, col=None, align="left"):
    """small rounded label with a pin"""
    if p <= 0: return
    col = col or C["aqua2"]; e = ease_out_back(p, 1.8)
    font(ctx, "Jost Medium"); ctx.set_font_size(15); w = text_width(ctx, s.upper(), 2.5) + 28
    ctx.save(); ctx.translate(x, y); ctx.scale(e, e)
    x0 = -w / 2 if align == "center" else (-w if align == "right" else 0)
    rrect(ctx, x0, -30, w, 30, 8); set_col(ctx, C["white"], 0.95); ctx.fill_preserve(); set_col(ctx, col); ctx.set_line_width(1.5); ctx.stroke()
    text(ctx, s.upper(), x0 + 14, -9, 15, col, fam="Jost Medium", tracking=2.5)
    ctx.restore()

# ----------------------------------------------------------------------------- machines (side view, facing left)
def feller_buncher(ctx, x, y, s=1.0, phase=0.0, alpha=1.0):
    tracks(ctx, x, y, 150 * s, 36 * s, alpha)
    body(ctx, x - 55 * s, y - 36 * s, 120 * s, 34 * s, alpha)
    cab(ctx, x - 20 * s, y - 70 * s, 62 * s, 46 * s, C["lime"], alpha)
    reach = 150 * s + 12 * s * math.sin(phase)
    hy = y - 20 * s - 25 * s * (0.5 + 0.5 * math.sin(phase * 1.3))
    j1 = (x - 40 * s, y - 92 * s); j2 = (x - 120 * s, y - 130 * s); j3 = (x - reach, hy)
    boom(ctx, [j1, j2, j3], 10 * s, alpha)
    # felling head: disc saw
    ctx.new_path(); ctx.arc(j3[0], j3[1] + 14 * s, 22 * s, 0, 2 * math.pi); stroke_fill(ctx, C["paper"], alpha=alpha)
    set_col(ctx, NAVY, alpha); ctx.set_line_width(2)
    for k in range(8):
        a = phase * 6 + k * math.pi / 4
        ctx.move_to(j3[0] + 14 * s * math.cos(a), j3[1] + 14 * s + 14 * s * math.sin(a)); ctx.line_to(j3[0] + 22 * s * math.cos(a), j3[1] + 14 * s + 22 * s * math.sin(a))
    ctx.stroke()
    rrect(ctx, j3[0] - 10 * s, j3[1] - 30 * s, 20 * s, 34 * s, 4); stroke_fill(ctx, C["paper2"], alpha=alpha)

def skidder(ctx, x, y, s=1.0, logs=0, alpha=1.0, bounce=0.0):
    y = y - 3 * bounce
    body(ctx, x - 70 * s, y - 34 * s, 70 * s, 26 * s, alpha)          # rear frame
    cab(ctx, x - 5 * s, y - 34 * s, 56 * s, 44 * s, C["lime"], alpha)
    body(ctx, x + 50 * s, y - 34 * s, 40 * s, 22 * s, alpha)          # engine hood (front, left-facing... front is left)
    boom(ctx, [(x - 60 * s, y - 40 * s), (x - 85 * s, y - 80 * s), (x - 110 * s, y - 40 * s)], 8 * s, alpha)   # grapple arch
    for wx in (x - 50 * s, x + 45 * s): wheel(ctx, wx, y - 22 * s, 24 * s, alpha)
    if logs:
        for i in range(logs):
            log(ctx, x - 110 * s - 70 * s + i * 6, y - 18 * s + i * 9 - 10 * s, 150 * s, 12 * s, 0.10, alpha)

def excavator(ctx, x, y, s=1.0, accent=None, tool="grapple", boom_pts=None, alpha=1.0, phase=0.0, draw_boom=True, roll=0.0):
    accent = accent or C["aqua"]
    tracks(ctx, x, y, 130 * s, 34 * s, alpha, roll)
    body(ctx, x - 60 * s, y - 34 * s, 110 * s, 30 * s, alpha)
    cab(ctx, x - 40 * s, y - 64 * s, 52 * s, 40 * s, accent, alpha)
    if not draw_boom: return None
    pts = boom_pts or [(x - 10 * s, y - 80 * s), (x - 90 * s, y - 150 * s), (x - 160 * s, y - 60 * s + 10 * s * math.sin(phase))]
    boom(ctx, pts, 9 * s, alpha)
    ex, ey = pts[-1]
    if tool == "grapple":
        set_col(ctx, NAVY, alpha); ctx.set_line_width(3 * s); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for sd in (-1, 1):
            ctx.move_to(ex, ey); ctx.curve_to(ex + sd * 22 * s, ey + 10 * s, ex + sd * 20 * s, ey + 30 * s, ex + sd * 6 * s, ey + 36 * s); ctx.stroke()
    elif tool == "head":
        rrect(ctx, ex - 14 * s, ey - 6 * s, 28 * s, 44 * s, 5); stroke_fill(ctx, C["paper2"], alpha=alpha)
    return pts

def log_truck(ctx, x, y, s=1.0, logs=0, alpha=1.0):
    # tractor (front left)
    cab(ctx, x - 150 * s, y - 24 * s, 60 * s, 52 * s, C["aqua"], alpha)
    body(ctx, x - 90 * s, y - 24 * s, 200 * s, 14 * s, alpha)
    for wx in (x - 128 * s, x - 60 * s, x - 30 * s, x + 70 * s, x + 100 * s): wheel(ctx, wx, y - 14 * s, 14 * s, alpha)
    for bx in (x - 70 * s, x + 90 * s):   # bunks / stakes
        set_col(ctx, NAVY, alpha); ctx.set_line_width(3 * s); ctx.move_to(bx, y - 38 * s); ctx.line_to(bx, y - 100 * s); ctx.stroke()
    for i in range(logs):
        row, col = divmod(i, 4)
        log(ctx, x + 10 * s, y - 46 * s - row * 13 * s - (col % 2) * 4, 200 * s, 12 * s, 0, alpha, lerpc(C["earth"], C["paper"], 0.1 * col))

def yarder(ctx, x, y, s=1.0, alpha=1.0):
    """tower yarder, returns the sheave point at the top of the mast"""
    tracks(ctx, x, y, 150 * s, 38 * s, alpha)
    body(ctx, x - 70 * s, y - 38 * s, 140 * s, 44 * s, alpha)
    cab(ctx, x + 10 * s, y - 82 * s, 56 * s, 42 * s, C["aqua"], alpha)
    # drums
    for dx in (-45, -15):
        ctx.new_path(); ctx.arc(x + dx * s, y - 60 * s, 14 * s, 0, 2 * math.pi); stroke_fill(ctx, C["paper"], alpha=alpha)
    # mast
    top = (x - 30 * s, y - 330 * s)
    rrect(ctx, x - 38 * s, top[1], 16 * s, 330 * s - 82 * s, 4); stroke_fill(ctx, C["paper"], alpha=alpha)
    ctx.new_path(); ctx.arc(top[0], top[1], 10 * s, 0, 2 * math.pi); stroke_fill(ctx, C["paper"], alpha=alpha)
    # guylines back to anchors
    for gx in (x + 160 * s, x + 260 * s):
        cable(ctx, top, (gx, y), sag=6, lw=1.6, alpha=0.8 * alpha)
        stump(ctx, gx, y, 10 * s, alpha)
    return top

def carriage(ctx, x, y, s=1.0, drop=0.0, logs=(), alpha=1.0):
    rrect(ctx, x - 16 * s, y - 8 * s, 32 * s, 22 * s, 4); stroke_fill(ctx, C["paper"], alpha=alpha)
    set_col(ctx, NAVY, alpha); ctx.set_line_width(2); ctx.move_to(x, y + 14 * s); ctx.line_to(x, y + 14 * s + drop); ctx.stroke()
    for (L, d, ang, ox, oy) in logs:
        log(ctx, x + ox, y + 14 * s + drop + oy, L, d, ang, alpha)

def lowbed(ctx, x, y, s=1.0, alpha=1.0, machine=True):
    cab(ctx, x - 200 * s, y - 24 * s, 60 * s, 52 * s, C["aqua"], alpha)
    body(ctx, x - 140 * s, y - 24 * s, 40 * s, 14 * s, alpha)
    # low deck
    ctx.move_to(x - 100 * s, y - 24 * s); ctx.line_to(x - 80 * s, y - 10 * s); ctx.line_to(x + 120 * s, y - 10 * s); ctx.line_to(x + 140 * s, y - 24 * s)
    ctx.line_to(x + 200 * s, y - 24 * s); ctx.line_to(x + 200 * s, y - 14 * s); ctx.line_to(x + 140 * s, y - 14 * s); ctx.line_to(x + 118 * s, y); ctx.line_to(x - 82 * s, y); ctx.line_to(x - 100 * s, y - 14 * s); ctx.close_path()
    stroke_fill(ctx, C["paper2"], alpha=alpha)
    for wx in (x - 178 * s, x - 120 * s, x + 160 * s, x + 185 * s): wheel(ctx, wx, y - 12 * s, 12 * s, alpha)
    if machine:
        ctx.save(); ctx.translate(x + 20 * s, y - 10 * s); ctx.scale(0.7 * s, 0.7 * s); yarder_folded(ctx, 0, 0, alpha); ctx.restore()

def yarder_folded(ctx, x, y, alpha=1.0):
    tracks(ctx, x, y, 150, 38, alpha); body(ctx, x - 70, y - 38, 140, 44, alpha); cab(ctx, x + 10, y - 82, 56, 42, C["aqua"], alpha)
    rrect(ctx, x - 150, y - 100, 220, 16, 4); stroke_fill(ctx, C["paper"], alpha=alpha)   # mast laid down

# ----------------------------------------------------------------------------- terrain
def terrain(ctx, gy, x0=-20, x1=W + 20, top=None, alpha=1.0, step=16):
    """fill below the ground function gy(x); returns nothing"""
    ctx.move_to(x0, gy(x0))
    for x in range(int(x0), int(x1) + step, step): ctx.line_to(x, gy(x))
    ctx.line_to(x1, H + 20); ctx.line_to(x0, H + 20); ctx.close_path()
    ctx.set_source(vgrad([(0, top or hexc("#e9e4d6")), (1, hexc("#cfc7b3"))], 0, 500, 0, H)); ctx.fill_preserve()
    set_col(ctx, NAVY, 0.55 * alpha); ctx.set_line_width(2.5); ctx.stroke()
    # subtle strata
    ctx.save()
    ctx.move_to(x0, gy(x0))
    for x in range(int(x0), int(x1) + step, step): ctx.line_to(x, gy(x))
    ctx.line_to(x1, H + 20); ctx.line_to(x0, H + 20); ctx.close_path(); ctx.clip()
    set_col(ctx, C["white"], 0.35); ctx.set_line_width(1.2)
    for k in range(1, 7):
        ctx.move_to(x0, gy(x0) + 40 * k)
        for x in range(int(x0), int(x1) + step, step): ctx.line_to(x, gy(x) + 40 * k + 6 * math.sin(x * 0.01 + k))
        ctx.stroke()
    ctx.restore()

def road(ctx, gy, x0, x1, alpha=1.0):
    ctx.move_to(x0, gy(x0) - 6); ctx.line_to(x1, gy(x1) - 6); ctx.line_to(x1, gy(x1) + 10); ctx.line_to(x0, gy(x0) + 10); ctx.close_path()
    set_col(ctx, C["taupe"], alpha); ctx.fill()
    set_col(ctx, C["white"], 0.7 * alpha); ctx.set_line_width(1.5); ctx.set_dash([14, 12]); ctx.move_to(x0, gy(x0) + 2); ctx.line_to(x1, gy(x1) + 2); ctx.stroke(); ctx.set_dash([])

def slope_marker(ctx, x, y, run, rise, p, label):
    """right-angle triangle with % label"""
    if p <= 0: return
    a = ease_out_cubic(p)
    set_col(ctx, C["aqua2"], a); ctx.set_line_width(2); ctx.set_dash([6, 6])
    ctx.move_to(x, y); ctx.line_to(x + run, y); ctx.line_to(x + run, y - rise); ctx.stroke(); ctx.set_dash([])
    ctx.move_to(x, y); ctx.line_to(x + run, y - rise); ctx.stroke()
    text(ctx, label, x + run + 14, y - rise / 2 + 6, 22, C["aqua2"], fam="Jost SemiBold", alpha=a)

def left_panel(ctx, w=760, h=H):
    ctx.save()
    if h < H:
        ctx.set_source(vgrad([(0, hexc("#ffffff", 1)), (0.8, hexc("#ffffff", 1)), (1, hexc("#ffffff", 0))], 0, 0, 0, h)); ctx.rectangle(0, 0, w, h); ctx.clip()
        ctx.push_group()
    ctx.set_source(vgrad([(0, hexc("#ffffff", 0.96)), (0.75, hexc("#ffffff", 0.85)), (1, hexc("#ffffff", 0))], 0, 0, w, 0)); ctx.rectangle(0, 0, w, h); ctx.fill()
    if h < H:
        ctx.pop_group_to_source(); ctx.mask(vgrad([(0, hexc("#000000", 1)), (0.8, hexc("#000000", 1)), (1, hexc("#000000", 0))], 0, 0, 0, h))
    ctx.restore()

def bullets(ctx, items, x, y0, t, dy=50, size=24, col=None):
    for k, (s, at) in enumerate(items):
        p = seg(t, at, at + 0.7)
        if p <= 0: continue
        y = y0 + k * dy; e = ease_out_back(p, 2.2)
        ctx.save(); ctx.translate(x + 12, y - 9); ctx.scale(e, e); icon(ctx, "check", 0, 0, 10, col or gradc(k / max(1, len(items) - 1)), lw=2.2); ctx.restore()
        text(ctx, s, x + 40, y, size, C["ink"], fam="Jost", alpha=ease_out_cubic(p))

# ============================================================================= SCENES
# ----------------------------------------------------------------------------- 1. title (0-8)
def s_title(ctx, t, T):
    paper_bg(ctx, T, 1.0, reveal=seg(t, 0.0, 2.2))
    wordmark(ctx, 960, 300, 96, seg(t, 0.3, 1.6), ring_p=seg(t, 0.8, 1.9))
    eyebrow(ctx, "Mosaic explains", 960 - 110, 440, seg(t, 1.6, 2.3))
    reveal_text(ctx, "Stump to road.", 960, 560, 110, NAVY, seg(t, 1.9, 2.8), fam="Jost Light", align="center")
    reveal_text(ctx, "How logs are harvested, what drives the cost, and how", 960, 640, 30, C["ink"], seg(t, 2.8, 3.7), fam="Jost Light", align="center")
    reveal_text(ctx, "connected machines help contractors succeed.", 960, 682, 30, C["ink"], seg(t, 3.0, 3.9), fam="Jost Light", align="center")
    rp = ease_out_expo(seg(t, 3.6, 4.8))
    if rp > 0:
        g = cairo.LinearGradient(760, 0, 1160, 0)
        for k, c in enumerate(GRAD): g.add_color_stop_rgba(k / 3, *c)
        ctx.set_source(g); ctx.rectangle(960 - 200 * rp, 740, 400 * rp, 3); ctx.fill()
    # three little machine glyphs
    for k, (kind, lab) in enumerate([("ground", "Ground"), ("cable", "Cable"), ("tether", "Tethered")]):
        p = seg(t, 4.4 + k * 0.3, 5.1 + k * 0.3)
        if p <= 0: continue
        x = 960 + (k - 1) * 260; e = ease_out_back(p)
        ctx.save(); ctx.translate(x, 850); ctx.scale(e * 0.42, e * 0.42)
        if kind == "ground": feller_buncher(ctx, 40, 30, 1.0, 0)
        elif kind == "cable": top = yarder(ctx, 60, 30, 0.6); cable(ctx, top, (-220, 60), sag=20)
        else: excavator(ctx, 60, 30, 0.8, C["green"], tool="head", boom_pts=[(50, -40), (-40, -110), (-140, -20)])
        ctx.restore()
        text(ctx, lab.upper(), x, 920, 15, C["grey"], fam="Jost Medium", align="center", tracking=4, alpha=ease_out_cubic(p))

# ----------------------------------------------------------------------------- 2. ground-based (8-30)
def g_ground(x): return 760 + 0.10 * (x - 1500) + 8 * math.sin(x * 0.006)

def s_ground(ctx, t, T):
    paper_bg(ctx, T, 0.7)
    terrain(ctx, g_ground)
    road(ctx, g_ground, 1480, W + 20)
    # trees: standing until the feller-buncher passes, then falling, then bunched
    fb_x = 1380 - 620 * clamp((t - 1.0) / 14.0)    # moves left over 14 s
    for i in range(16):
        tx = 720 + i * 40 + (hsh(i, 1) - 0.5) * 24; ty = g_ground(tx); hgt = 150 + 60 * hsh(i, 2)
        cut_t = 1.0 + (1380 - tx) / 620 * 14.0 + 0.3   # when the head reaches it
        p = seg(t, cut_t, cut_t + 0.9)
        if p >= 1:
            stump(ctx, tx, ty); continue
        ctx.save(); ctx.translate(tx, ty); ctx.rotate(-ease_in_out(p) * math.radians(80)); ctx.translate(-tx, -ty)
        conifer(ctx, tx, ty, hgt, 1.0, seed=i, sway_t=T, tiers=11)
        ctx.restore()
        if p > 0: stump(ctx, tx, ty)
    # bunches at the ground after felling (as logs lying on slope)
    for i in range(16):
        tx = 720 + i * 40 + (hsh(i, 1) - 0.5) * 24
        cut_t = 1.0 + (1380 - tx) / 620 * 14.0 + 1.2
        if t > cut_t and i % 3 == 0:
            done = seg(t, cut_t + 2.0 + (16 - i) * 0.5, cut_t + 2.5 + (16 - i) * 0.5)   # skidder collected it
            if done < 1: log(ctx, tx + 40, g_ground(tx + 40) - 8, 110, 12, math.atan(0.10), 1 - done)
    feller_buncher(ctx, fb_x, g_ground(fb_x) + 2, 1.0, phase=T * 5)
    # skidder shuttles between the cut and the landing
    cyc = (t - 3.0) % 6.0; loaded = cyc > 3.0
    if t > 3.0:
        u = ease_in_out(cyc / 3.0) if not loaded else ease_in_out((cyc - 3.0) / 3.0)
        sx = 1340 - 520 * u if not loaded else 820 + 520 * u
        ctx.save()
        if not loaded: ctx.translate(sx, 0); ctx.scale(-1, 1); ctx.translate(-sx, 0)   # face left when heading out
        skidder(ctx, sx, g_ground(sx) + 2, 0.9, logs=3 if loaded else 0, bounce=math.sin(T * 14))
        ctx.restore()
    # landing: processor + loader + truck, log deck grows
    excavator(ctx, 1560, g_ground(1560) + 2, 0.85, C["lime"], tool="head", phase=T * 3)
    ndeck = min(9, int(max(0, (t - 8) / 1.6)))
    for i in range(ndeck):
        row, col = divmod(i, 3)
        log(ctx, 1400 + col * 12, g_ground(1420) - 10 - row * 13, 110, 12, 0)
    log_truck(ctx, 1800, g_ground(1800) + 2, 0.75, logs=min(8, int(max(0, (t - 12) / 1.4))))
    # captions
    left_panel(ctx, 700, 700)
    eyebrow(ctx, "System 1 of 3", 120, 200, seg(t, 0.2, 0.9))
    reveal_text(ctx, "Ground-based.", 120, 300, 84, NAVY, seg(t, 0.4, 1.2), fam="Jost Light")
    reveal_text(ctx, "Machines drive to the tree.", 120, 360, 30, C["ink"], seg(t, 1.2, 2.0), fam="Jost Light")
    bullets(ctx, [("Gentle ground, under ~35% slope", 3.0), ("Feller-buncher cuts and bunches", 5.0), ("Skidder drags bunches to the road", 8.0),
                  ("Processor bucks, loader fills the truck", 12.0), ("Short cycles → lowest cost per m³", 16.0)], 120, 450, t)
    slope_marker(ctx, 760, g_ground(760) + 70, 200, 20, seg(t, 3.2, 4.0), "≈10–35%")
    label_tag(ctx, 1560, g_ground(1560) - 160, "Landing", seg(t, 12.2, 13.0), C["lime"], "center")
    label_tag(ctx, 1100, 400, "Feller-buncher", seg(t, 5.2, 6.0), C["lime"], "center")

# ----------------------------------------------------------------------------- 3. cable yarding (30-55)
def g_cable(x): return 430 + (1150 - min(x, 1500)) * 0.42 * clamp((1500 - x) / 1300) ** 0.9 * (1 if x < 1500 else 0) + (0 if x < 1500 else 0)

def g_steep(x):
    # road bench on the right at y=430, steep slope descending to the left to ~y=990
    if x >= 1480: return 430
    u = (1480 - x) / 1300
    return 430 + 560 * min(1, u) ** 0.95 + 10 * math.sin(x * 0.01)

def s_cable(ctx, t, T):
    paper_bg(ctx, T, 0.7)
    terrain(ctx, g_steep)
    road(ctx, g_steep, 1480, W + 20)
    # standing trees on the slope (some yarded away over time)
    for i in range(18):
        tx = 150 + i * 70 + (hsh(i, 3) - 0.5) * 30; ty = g_steep(tx); hgt = 120 + 60 * hsh(i, 4)
        gone = seg(t, 6 + i * 1.0, 6.5 + i * 1.0) if i % 2 == 0 else 0
        if gone >= 1: stump(ctx, tx, ty); continue
        conifer(ctx, tx, ty, hgt, 1.0, seed=40 + i, sway_t=T, tiers=10, alpha=1 - gone)
    yp = ease_out_cubic(seg(t, 0.3, 1.2))
    top = yarder(ctx, 1600, g_steep(1600) + 2, 0.95, alpha=yp)
    tail = (140, g_steep(140) - 30)
    stump(ctx, 140, g_steep(140), 14, yp)
    # skyline
    sl = ease_in_out(seg(t, 1.0, 2.6))
    if sl > 0:
        end = (top[0] + (tail[0] - top[0]) * sl, top[1] + (tail[1] - top[1]) * sl)
        cable(ctx, top, end, sag=40 * sl, lw=2.4, alpha=yp)
        label_tag(ctx, 900, 330, "Skyline", seg(t, 2.4, 3.2), C["aqua2"], "center")
        label_tag(ctx, 140, g_steep(140) - 60, "Tailhold anchor", seg(t, 2.6, 3.4), C["aqua2"], "left")
    # carriage cycle: out empty (3s), hook (1s), in loaded (3.5s), unhook (0.5s) = 8 s
    if t > 3.0:
        cyc = (t - 3.0) % 8.0
        if cyc < 3.0: u = 1 - ease_in_out(cyc / 3.0); drop = 0; logs = ()
        elif cyc < 4.0: u = 0; drop = 90 * ease_in_out((cyc - 3.0) / 1.0); logs = ()
        elif cyc < 7.5: u = ease_in_out((cyc - 4.0) / 3.5); drop = 90 - 60 * u; logs = [(110, 12, 0.5, -10, 10), (110, 11, 0.6, 14, 16), (100, 10, 0.45, 2, 28)]
        else: u = 1; drop = 0; logs = ()
        # position along the sagging skyline
        cx = top[0] + (tail[0] - top[0]) * (1 - u) if False else tail[0] + (top[0] - tail[0]) * u
        s0 = (1 - u); cy = (1 - s0) ** 2 * top[1] + 2 * (1 - s0) * s0 * ((top[1] + tail[1]) / 2 + 40) + s0 ** 2 * tail[1]
        carriage(ctx, cx, cy, 1.0, drop, logs)
        # main line back to the yarder
        cable(ctx, (cx, cy), (top[0] + 6, top[1] + 8), sag=14, lw=1.4, alpha=0.7)
    # landing deck grows
    ndeck = min(8, int(max(0, (t - 10) / 2.5)))
    for i in range(ndeck):
        row, col = divmod(i, 3)
        log(ctx, 1380 + col * 10, 430 - 10 - row * 13, 100, 12, 0)
    # crew figures near the tail (chokers)
    if t > 3:
        for k in range(2):
            px = 260 + k * 50 + 6 * math.sin(T * 2 + k); py = g_steep(px)
            set_col(ctx, C["amber"]); ctx.new_path(); ctx.arc(px, py - 34, 6, 0, 2 * math.pi); ctx.fill()
            set_col(ctx, NAVY); ctx.set_line_width(3); ctx.move_to(px, py - 28); ctx.line_to(px, py - 10); ctx.move_to(px, py - 10); ctx.line_to(px - 6, py); ctx.move_to(px, py - 10); ctx.line_to(px + 6, py); ctx.stroke()
        label_tag(ctx, 285, g_steep(285) - 60, "Rigging crew", seg(t, 8.0, 8.8), C["amber"], "center")
    left_panel(ctx, 720, 700)
    eyebrow(ctx, "System 2 of 3", 120, 200, seg(t, 0.2, 0.9))
    reveal_text(ctx, "Cable yarding.", 120, 300, 84, NAVY, seg(t, 0.4, 1.2), fam="Jost Light")
    reveal_text(ctx, "The tree comes to the machine.", 120, 360, 30, C["ink"], seg(t, 1.2, 2.0), fam="Jost Light")
    bullets(ctx, [("Steep ground, roughly 35–60%+", 3.5), ("Yarder stays on the road", 5.5), ("Skyline + carriage pull each turn uphill", 8.5),
                  ("Bigger crew: operator, chokers, chaser", 12.0), ("Longer cycles → higher cost per m³", 16.0)], 120, 450, t)
    slope_marker(ctx, 420, g_steep(420) + 40, 160, 100, seg(t, 3.7, 4.5), "≈45%")

# ----------------------------------------------------------------------------- 4. tethered (55-75)
def rotp(px, py, cx, cy, a):
    """rotate (px, py) about (cx, cy) by a (cairo convention: positive = clockwise on screen)"""
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)

def harvest_head(ctx, x, y, ang, s=1.0, alpha=1.0):
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang)
    rrect(ctx, -13 * s, -26 * s, 26 * s, 52 * s, 5); stroke_fill(ctx, C["paper2"], alpha=alpha)
    set_col(ctx, NAVY, alpha); ctx.set_line_width(2)
    for k in (-1, 1): ctx.move_to(-13 * s, k * 12 * s); ctx.line_to(13 * s, k * 12 * s)
    ctx.stroke(); ctx.restore()

def winch_dozer(ctx, x, y, alpha=1.0):
    """small tracked winch-assist unit: blade dug in on the right, winch drum on the slope side; returns drum point"""
    tracks(ctx, x, y, 120, 32, alpha)
    body(ctx, x - 52, y - 32, 100, 26, alpha)
    cab(ctx, x - 26, y - 58, 44, 34, C["aqua"], alpha)
    boom(ctx, [(x + 40, y - 40), (x + 82, y - 30)], 7, alpha)
    ctx.move_to(x + 78, y - 44); ctx.line_to(x + 96, y - 40); ctx.line_to(x + 92, y + 4); ctx.line_to(x + 76, y + 2); ctx.close_path(); stroke_fill(ctx, C["paper2"], alpha=alpha)
    d = (x - 62, y - 44)
    ctx.new_path(); ctx.arc(d[0], d[1], 13, 0, 2 * math.pi); stroke_fill(ctx, C["paper"], alpha=alpha)
    ctx.new_path(); ctx.arc(d[0], d[1], 5, 0, 2 * math.pi); set_col(ctx, NAVY, alpha); ctx.fill()
    return d

def fb_head(ctx, x, y, ang, s=1.0, spin=0.0, alpha=1.0):
    """feller-buncher head: accumulator frame with a disc saw at its foot; pivot at the grip point"""
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang)
    rrect(ctx, -11 * s, -34 * s, 22 * s, 46 * s, 5); stroke_fill(ctx, C["paper2"], alpha=alpha)
    set_col(ctx, NAVY, alpha); ctx.set_line_width(2.5 * s)
    for k in (-1, 1): ctx.move_to(k * 11 * s, -26 * s); ctx.line_to(k * 24 * s, -18 * s); ctx.line_to(k * 20 * s, -4 * s)   # arms
    ctx.stroke()
    ctx.new_path(); ctx.arc(0, 16 * s, 19 * s, 0, 2 * math.pi); stroke_fill(ctx, C["paper"], lw=2, alpha=alpha)
    set_col(ctx, NAVY, alpha); ctx.set_line_width(1.8)
    for k in range(6):
        aa = spin + k * math.pi / 3
        ctx.move_to(11 * s * math.cos(aa), 16 * s + 11 * s * math.sin(aa)); ctx.line_to(19 * s * math.cos(aa), 16 * s + 19 * s * math.sin(aa))
    ctx.stroke(); ctx.restore()

SLOPE_A = math.atan(0.43)                 # ground angle of g_steep on the working face (≈23°)
LAY_A = -(math.pi / 2 + SLOPE_A)          # a stem laid downhill along the slope
T_TREES = [1300 - k * 100 for k in range(6)]   # buncher works these down the slope, in order
T_START = 1.6
T_CYC = [4.2] + [2.7] * 5                 # first cycle deliberately slow so it reads
T_ST = [T_START + sum(T_CYC[:k]) for k in range(len(T_CYC))]
PH = (0.30, 0.15, 0.14, 0.30, 0.11)       # travel, grip, cut, lay, release (fractions of a cycle)
S_TRIPS = [8.4, 14.6, 20.8]               # skidder trips: tree 0, 1, 2 — always ≥2 trees behind the buncher
S_DESC, S_GRAB, S_CLIMB, S_DROP = 2.6, 0.6, 2.6, 0.6
S_ROAD = 1585

def tree_state(j, t):
    """-> (phase, progress) for tree j: stand | grip | cut | lay | release | done"""
    c = t - T_ST[j]; L = T_CYC[j]
    if c < 0: return "stand", 0.0
    names = ("stand", "grip", "cut", "lay", "release"); e0 = 0.0
    for name, f in zip(names, PH):
        e1 = e0 + L * f
        if c < e1: return name, (c - e0) / (e1 - e0)
        e0 = e1
    return "done", 1.0

def s_tether(ctx, t, T):
    paper_bg(ctx, T, 0.7)
    terrain(ctx, g_steep)
    road(ctx, g_steep, 1480, W + 20)
    ax = 1852; ay = g_steep(ax) + 2; drum_h = (ax - 64, ay - 58)     # buncher anchor (excavator, bucket dug in)
    dz = 1738; dy_ = g_steep(dz) + 2; drum_s = (dz - 62, dy_ - 44)    # skidder anchor (winch dozer)
    # ---- buncher position: parks just uphill of each tree
    k = max([i for i in range(len(T_TREES)) if t >= T_ST[i]], default=-1)
    if k < 0:
        hx = 1420.0; phase, pp = "idle", 0.0
    else:
        phase, pp = tree_state(k, t)
        goal = T_TREES[k] + 110; prev = 1420.0 if k == 0 else T_TREES[k - 1] + 110
        hx = prev + (goal - prev) * ease_in_out(pp) if phase == "stand" else goal
        if phase == "stand": phase = "travel"
        if phase == "done": phase = "release"; pp = 1.0
    hy = g_steep(hx) + 2
    tilt = -math.atan2(g_steep(hx - 40) - g_steep(hx + 40), 80)   # counter-clockwise → downhill (left) end sits lower
    # ---- skidder trips (first, so bunches know whether they have been picked up)
    sk = None; picked = set()
    for j, s0 in enumerate(S_TRIPS):
        if t < s0: break
        goal = T_TREES[j] + 95; c = t - s0
        if c < S_DESC: sx = S_ROAD + (goal - S_ROAD) * ease_in_out(c / S_DESC); loaded = False; st = "desc"
        elif c < S_DESC + S_GRAB: sx = goal; loaded = (c - S_DESC) / S_GRAB > 0.5; st = "grab"
        elif c < S_DESC + S_GRAB + S_CLIMB: sx = goal + (S_ROAD - goal) * ease_in_out((c - S_DESC - S_GRAB) / S_CLIMB); loaded = True; st = "climb"
        elif c < S_DESC + S_GRAB + S_CLIMB + S_DROP: sx = S_ROAD; loaded = False; st = "drop"
        else: sx = S_ROAD; loaded = False; st = "wait"
        sk = (sx, loaded, st, j, c)
        if c >= S_DESC + S_GRAB * 0.5: picked.add(j)
    # ---- untouched trees further down the slope
    for i in range(6):
        tx = 190 + i * 66 + (hsh(i, 5) - 0.5) * 30; conifer(ctx, tx, g_steep(tx), 120 + 60 * hsh(i, 6), 1.0, seed=60 + i, sway_t=T, tiers=10)
    # ---- worked trees: laid bunches first (a little nearer the viewer, beside the trail), then standing ones
    states = [(j, tx, g_steep(tx), 140 + 40 * hsh(j, 7)) + tree_state(j, t) for j, tx in enumerate(T_TREES)]
    for j, tx, ty, hgt, ph, p in states:
        if ph in ("stand", "grip", "cut"): continue
        stump(ctx, tx, ty, 11)
        if ph in ("release", "done") and j in picked: continue
        ang = LAY_A * ease_in_out(p) if ph == "lay" else LAY_A
        ox, oy = (0, 0) if ph == "lay" else (-10, 8)
        ctx.save(); ctx.translate(tx + ox, ty + oy); ctx.rotate(ang); ctx.translate(-tx - ox, -ty - oy)
        conifer(ctx, tx + ox, ty + oy, hgt, 1.0, seed=70 + j, sway_t=0, tiers=10); ctx.restore()
    for j, tx, ty, hgt, ph, p in states:
        if ph not in ("stand", "grip", "cut"): continue
        conifer(ctx, tx, ty, hgt, 1.0, seed=70 + j, sway_t=T if ph == "stand" else 0, tiers=10)
        if ph == "cut":   # saw at the base: kerf + sparks
            set_col(ctx, C["amber"], 0.9); ctx.set_line_width(3)
            for m in range(5):
                aa = -0.3 - m * 0.5 + p * 2; ctx.move_to(tx - 4, ty - 6); ctx.line_to(tx - 4 + 18 * math.cos(aa), ty - 6 + 18 * math.sin(aa))
            ctx.stroke()
    # ---- roadside deck (delivered tree-lengths)
    delivered = sum(1 for s0 in S_TRIPS if t >= s0 + S_DESC + S_GRAB + S_CLIMB + S_DROP * 0.6)
    for i in range(delivered * 2):
        row, col = divmod(i, 2)
        log(ctx, 1530 + col * 8, 430 - 9 - row * 12, 118, 11, 0)
    # ---- buncher tether first (so the dozer draws over it), then anchors
    ap = ease_out_cubic(seg(t, 0.3, 1.2)); hp = ease_out_cubic(seg(t, 0.6, 1.4))
    if hp > 0:
        att = rotp(hx + 50, hy - 14, hx, hy, tilt)   # low on the uphill end of the undercarriage
        cable(ctx, drum_h, att, sag=10, lw=2.6, col=C["green2"], alpha=hp)
    excavator(ctx, ax, ay, 0.95, C["green"], draw_boom=False, alpha=ap)
    boom(ctx, [(ax + 10, ay - 76), (ax + 70, ay - 138), (ax + 98, ay - 6)], 9, ap)
    rrect(ctx, ax + 82, ay - 14, 34, 24, 4); stroke_fill(ctx, C["paper2"], alpha=ap)
    ctx.new_path(); ctx.arc(drum_h[0], drum_h[1], 15, 0, 2 * math.pi); stroke_fill(ctx, C["paper"], alpha=ap)
    ctx.new_path(); ctx.arc(drum_h[0], drum_h[1], 6, 0, 2 * math.pi); set_col(ctx, NAVY, ap); ctx.fill()
    label_tag(ctx, ax - 60, ay - 170, "Anchor + winch", seg(t, 1.2, 2.0), C["green2"], "center")
    dp = ease_out_cubic(seg(t, 7.2, 8.0))
    if dp > 0:
        winch_dozer(ctx, dz, dy_, dp)
        label_tag(ctx, dz - 10, dy_ - 105, "Skidder anchor", seg(t, 7.6, 8.4), C["aqua2"], "center")
    # ---- skidder: faces uphill; backs down, grapples the bunch, drives up dragging the whole trees butt-first
    if sk:
        sx, loaded, st, j, c = sk; sy = g_steep(sx) + 2
        stilt = -math.atan2(g_steep(sx - 40) - g_steep(sx + 40), 80) if sx < 1470 else 0.0
        att = rotp(sx + 70, sy - 16, sx, sy, stilt)
        cable(ctx, drum_s, att, sag=8, lw=2.4, col=C["aqua2"])
        if loaded:   # butts in the grapple, stems trailing on the ground behind
            fx, fy = rotp(sx - 92, sy - 40, sx, sy, stilt)
            for i in range(2):
                txl = fx - 150 - i * 8; tyl = g_steep(txl) - 4 - i * 6
                ang = math.atan2(txl - fx, -(tyl - fy))     # rotation that points the sprite's 'up' from butt to tail
                ctx.save(); ctx.translate(fx + i * 4, fy - i * 6); ctx.rotate(ang)
                conifer(ctx, 0, 0, 150 + 20 * i, 1.0, seed=70 + j + i, sway_t=0, tiers=10); ctx.restore()
        ctx.save(); ctx.translate(sx, sy); ctx.rotate(stilt); ctx.translate(-sx, -sy)
        bounce = math.sin(T * 16) * (1 if st in ("desc", "climb") else 0)
        skidder(ctx, sx, sy, 0.85, logs=0, bounce=bounce)
        ctx.restore()
        label_tag(ctx, sx, sy - 118, "Same skidder, on its own line", seg(t, 9.8, 10.6) * (1 - seg(t, 13.4, 14.2)), C["aqua2"], "center")
    # ---- feller-buncher: base rotated to the slope, boom/head placed in world space so the head meets the tree
    if hp > 0:
        bob = math.sin(T * 18) * (1.2 if phase == "travel" else 0)
        ctx.save(); ctx.translate(hx, hy + bob); ctx.rotate(tilt); ctx.translate(-hx, -hy - bob)
        excavator(ctx, hx, hy + bob, 0.85, C["green"], draw_boom=False, alpha=hp, roll=-hx * 0.8)
        ctx.restore()
        root = rotp(hx - 8, hy - 62 + bob, hx, hy, tilt)
        carry_tip = rotp(hx - 96, hy - 40, hx, hy, tilt)
        head_ang = tilt; spin = 0.0
        if phase == "idle":
            tip = carry_tip
        elif phase == "travel":
            tip = carry_tip
        else:
            tx = T_TREES[k]; ty = g_steep(tx)
            grip_tip = (tx + 2, ty - 30)
            if phase == "grip":
                e = ease_in_out(pp); tip = (carry_tip[0] + (grip_tip[0] - carry_tip[0]) * e, carry_tip[1] + (grip_tip[1] - carry_tip[1]) * e); head_ang = tilt * (1 - e)
            elif phase == "cut":
                tip = grip_tip; head_ang = 0.0; spin = T * 40
            elif phase == "lay":
                ang = LAY_A * ease_in_out(pp); tip = rotp(grip_tip[0], grip_tip[1], tx, ty, ang); head_ang = ang
            else:   # release: head lifts back to carry
                laid = rotp(grip_tip[0], grip_tip[1], tx, ty, LAY_A); e = ease_in_out(pp)
                tip = (laid[0] + (carry_tip[0] - laid[0]) * e, laid[1] + (carry_tip[1] - laid[1]) * e); head_ang = LAY_A * (1 - e) + tilt * e
        mx, my = (root[0] + tip[0]) / 2, (root[1] + tip[1]) / 2
        dx, dy = tip[0] - root[0], tip[1] - root[1]; ln = math.hypot(dx, dy) or 1
        elbow = (mx + dy / ln * 55, my - dx / ln * 55)
        if elbow[1] > my: elbow = (mx - dy / ln * 55, my + dx / ln * 55)
        boom(ctx, [root, elbow, tip], 8, hp)
        fb_head(ctx, tip[0], tip[1], head_ang, 0.85, spin, hp)
        label_tag(ctx, hx, hy - 150, "Tethered feller-buncher", seg(t, 3.0, 3.8) * (1 - seg(t, 7.0, 7.8)), C["green2"], "center")
    left_panel(ctx, 720, 700)
    eyebrow(ctx, "System 3 of 3", 120, 200, seg(t, 0.2, 0.9))
    reveal_text(ctx, "Tethered.", 120, 300, 84, NAVY, seg(t, 0.4, 1.2), fam="Jost Light")
    reveal_text(ctx, "A winch line gives the machine traction and stability.", 120, 360, 30, C["ink"], seg(t, 1.2, 2.0), fam="Jost Light")
    bullets(ctx, [("Anchor on the road keeps the winch line tight", 2.5), ("Feller-buncher cuts each tree and lays it in a bunch", 5.5), ("Tethered skidder drags the bunch up to the road", 10.5),
                  ("Bucked and loaded at roadside, as before", 15.5), ("Safer than hand falling; more machines to own and move", 20.0)], 120, 450, t)
    slope_marker(ctx, 420, g_steep(420) + 40, 160, 100, seg(t, 3.2, 4.0), "≈40–60%")

# ----------------------------------------------------------------------------- 5. piece size economics (75-100)
def s_piece(ctx, t, T):
    taupe_bg(ctx, T)
    # left: two turns under a carriage
    reveal_text(ctx, "Every turn costs the same.", 120, 200, 72, C["white"], seg(t, 0.3, 1.1), fam="Jost Light")
    reveal_text(ctx, "Whether the carriage carries three big logs or eight small ones, the yarder, the crew", 120, 258, 26, C["white"], seg(t, 1.0, 1.8), fam="Jost Light", alpha=0.92)
    reveal_text(ctx, "and the clock cost the same — but the cubic metres per turn are very different.", 120, 296, 26, C["white"], seg(t, 1.2, 2.0), fam="Jost Light", alpha=0.92)
    for k, (title, logs, vol) in enumerate([("Large pieces", [(150, 22)] * 3, "3 × 1.0 m³  =  3.0 m³"), ("Small pieces", [(120, 11)] * 8, "8 × 0.25 m³  =  2.0 m³")]):
        p = seg(t, 2.4 + k * 1.2, 3.2 + k * 1.2)
        if p <= 0: continue
        e = ease_out_cubic(p); x = 300 + k * 420; y = 420
        ctx.save(); ctx.translate(0, (1 - e) * 20)
        set_col(ctx, C["white"], 0.96 * e); rrect(ctx, x - 170, y - 40, 340, 400, 20); ctx.fill()
        text(ctx, title, x, y, 26, NAVY, fam="Jost Medium", align="center", alpha=e)
        cable(ctx, (x - 170, y + 40), (x + 170, y + 40), sag=6, lw=2, alpha=e)
        carriage(ctx, x, y + 44, 0.9, 40)
        for i, (L, d) in enumerate(logs):
            lp = seg(t, 3.0 + k * 1.2 + i * 0.12, 3.5 + k * 1.2 + i * 0.12)
            if lp <= 0: continue
            ang = 1.15; ox = (i - (len(logs) - 1) / 2) * (d + 6); oy = 100 + 90
            log(ctx, x + ox * 0.5, y + oy + (1 - ease_out_cubic(lp)) * -30, L, d, ang, ease_out_cubic(lp))
        text(ctx, vol, x, y + 330, 22, C["aqua2"], fam="Jost SemiBold", align="center", alpha=e)
        ctx.restore()
    # right: cost curve. cost per m3 ∝ 1 / (m3 per turn)
    cp = seg(t, 5.0, 6.0)
    if cp > 0:
        e = ease_out_cubic(cp); x0, y0, w, h = 1160, 900, 620, 480
        set_col(ctx, C["white"], 0.96 * e); rrect(ctx, x0 - 70, y0 - h - 110, w + 130, h + 190, 20); ctx.fill()
        text(ctx, "COST PER CUBIC METRE  vs  PIECE SIZE", x0, y0 - h - 60, 15, C["grey"], fam="Jost Medium", tracking=3, alpha=e)
        set_col(ctx, C["mute"], e); ctx.set_line_width(1.5); ctx.move_to(x0, y0 - h); ctx.line_to(x0, y0); ctx.line_to(x0 + w, y0); ctx.stroke()
        text(ctx, "piece size (m³)  →", x0 + w, y0 + 34, 15, C["grey"], fam="Jost Medium", align="right", alpha=e)
        ctx.save(); ctx.translate(x0 - 22, y0 - h / 2); ctx.rotate(-math.pi / 2); text(ctx, "cost / m³  →", 0, 0, 15, C["grey"], fam="Jost Medium", align="center", alpha=e); ctx.restore()
        def curve(u):   # u: 0 (0.1 m3) .. 1 (1.2 m3)
            m3 = 0.1 + 1.1 * u; c = 1 / m3 / (1 / 0.1)   # normalised
            return x0 + w * u, y0 - h * (0.06 + 0.9 * (c ** 0.55))
        draw = ease_in_out(seg(t, 5.6, 8.0))
        set_col(ctx, C["aqua2"], e); ctx.set_line_width(4); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for k in range(int(80 * draw) + 1):
            px, py = curve(1 - k / 80)
            (ctx.move_to if k == 0 else ctx.line_to)(px, py)
        ctx.stroke()
        for u, lab in ((0.82, "1.0"), (0.36, "0.5"), (0.14, "0.25")):
            px, _ = curve(u); text(ctx, lab, px, y0 + 24, 14, C["grey"], fam="Jost", align="center", alpha=e)
        # slider marker sweeping from large to small
        mu = 1 - 0.85 * ease_in_out(seg(t, 8.5, 16.0))
        if t > 8.0:
            px, py = curve(mu); m3 = 0.1 + 1.1 * mu; ratio = (1.2 / m3)
            set_col(ctx, C["aqua2"], 0.25); ctx.new_path(); ctx.arc(px, py, 22, 0, 2 * math.pi); ctx.fill()
            set_col(ctx, NAVY); ctx.new_path(); ctx.arc(px, py, 8, 0, 2 * math.pi); ctx.fill()
            set_col(ctx, C["mute"], 0.7); ctx.set_line_width(1); ctx.set_dash([4, 4]); ctx.move_to(px, py); ctx.line_to(px, y0); ctx.stroke(); ctx.set_dash([])
            text(ctx, f"{m3:.2f} m³ pieces", x0 + w, y0 - h + 10, 22, NAVY, fam="Jost Medium", align="right")
            text(ctx, f"≈ {ratio:.1f}× the cost per m³", x0 + w, y0 - h + 44, 26, C["amber"] if ratio > 2 else C["aqua2"], fam="Jost SemiBold", align="right")
    reveal_text(ctx, "ILLUSTRATIVE — SMALLER PIECES MEAN FEWER CUBIC METRES PER TURN, SO EACH CUBIC METRE CARRIES MORE OF THE COST", 960, 1010, 14, C["white"], seg(t, 9.0, 9.8), fam="Jost Medium", align="center", tracking=3, alpha=0.85)

# ----------------------------------------------------------------------------- 6. mobilisation (100-120)
ROAD = [(-40, 640), (260, 600), (560, 700), (900, 620), (1240, 700), (1560, 560), (1960, 500)]
BLOCKS = [("A", 420, 470, 120), ("B", 900, 480, 70), ("C", 1230, 850, 70), ("D", 1620, 720, 70)]

def s_mob(ctx, t, T):
    paper_bg(ctx, T, 1.0)
    # top-down map: blocks and road
    for k, (name, bx, by, r) in enumerate(BLOCKS):
        p = seg(t, 0.3 + k * 0.2, 0.9 + k * 0.2)
        if p <= 0: continue
        e = ease_out_back(p)
        ctx.save(); ctx.translate(bx, by); ctx.scale(e, e)
        ctx.new_path()
        for i in range(24):
            a = i / 24 * 2 * math.pi; rr = r * (1 + 0.12 * math.sin(3 * a + k) + 0.06 * math.sin(7 * a))
            (ctx.move_to if i == 0 else ctx.line_to)(rr * math.cos(a), rr * math.sin(a))
        ctx.close_path(); stroke_fill(ctx, lerpc(C["lime"], C["green"], 0.3), C["green2"], 2)
        text(ctx, f"Block {name}", 0, 6, 18, NAVY, fam="Jost SemiBold", align="center")
        ctx.restore()
    set_col(ctx, C["taupe"]); ctx.set_line_width(10); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    R.stroke_curve(ctx, ROAD); ctx.stroke()
    set_col(ctx, C["white"], 0.8); ctx.set_line_width(1.5); ctx.set_dash([12, 10]); R.stroke_curve(ctx, ROAD); ctx.stroke(); ctx.set_dash([])
    # lowbed travelling along the road between blocks, pausing at each
    u = 0.12 + 0.78 * ease_in_out(seg(t, 2.0, 12.0))
    lx, ly = R.catmull(ROAD, u); nx_, ny_ = R.catmull(ROAD, min(1, u + 0.01))
    ang = math.atan2(ny_ - ly, nx_ - lx)
    ctx.save(); ctx.translate(lx, ly - 10); ctx.rotate(ang); ctx.scale(0.5, 0.5); ctx.scale(-1, 1); lowbed(ctx, 0, 0, 1.0); ctx.restore()
    label_tag(ctx, lx, ly - 60, "Lowbed move", seg(t, 2.5, 3.3), C["amber"], "center")
    # calendar strips
    cp = seg(t, 4.0, 5.0)
    if cp > 0:
        e = ease_out_cubic(cp)
        set_col(ctx, C["white"], 0.96 * e); rrect(ctx, 90, 120, 1740, 230, 20); ctx.fill()
        text(ctx, "20 PRODUCING DAYS — TWO WAYS", 120, 160, 15, C["grey"], fam="Jost Medium", tracking=3, alpha=e)
        rows = [("One large block", [("g", 20), ("m", 2)]), ("Four small blocks", [("g", 5), ("m", 2), ("g", 5), ("m", 2), ("g", 5), ("m", 2), ("g", 5), ("m", 2)])]
        for r, (name, segs) in enumerate(rows):
            y = 205 + r * 66
            text(ctx, name, 120, y + 8, 22, NAVY, fam="Jost Medium", alpha=e)
            x = 400; day = 0
            for kind, n in segs:
                for i in range(n):
                    p = seg(t, 5.0 + day * 0.12 + r * 0.8, 5.3 + day * 0.12 + r * 0.8); day += 1
                    if p <= 0: continue
                    col = C["green"] if kind == "g" else C["amber"]
                    ctx.save(); ctx.translate(x + 15, y); ctx.scale(ease_out_back(p), ease_out_back(p))
                    rrect(ctx, -14, -14, 28, 28, 6); set_col(ctx, col); ctx.fill(); ctx.restore()
                    x += 34
            moves = sum(n for k, n in segs if k == "m")
            text(ctx, f"{moves} move days — no logs, costs still running", x + 20, y + 8, 18, C["amber"], fam="Jost Medium", alpha=ease_out_cubic(seg(t, 6.0 + r * 1.2, 6.8 + r * 1.2)))
    left_panel(ctx, 0)
    ctx.save(); ctx.set_source(vgrad([(0, hexc("#ffffff", 0)), (1, hexc("#ffffff", 0.95))], 0, 760, 0, 900)); ctx.rectangle(0, 760, W, H - 760); ctx.fill(); ctx.restore()
    reveal_text(ctx, "Moving costs money.", 120, 960, 72, NAVY, seg(t, 0.3, 1.1), fam="Jost Light")
    reveal_text(ctx, "A yarder travels by lowbed and a move can take days. Crew wages, equipment payments and insurance", 120, 1005, 24, C["ink"], seg(t, 1.0, 1.8), fam="Jost Light")
    reveal_text(ctx, "keep running while nothing is produced — and smaller blocks mean more moves.", 120, 1040, 24, C["ink"], seg(t, 1.2, 2.0), fam="Jost Light")

# ----------------------------------------------------------------------------- 7. connectivity (120-142)
def s_connect(ctx, t, T):
    paper_bg(ctx, T, 0.7)
    terrain(ctx, lambda x: 820 + 0.12 * (x - 900) + 10 * math.sin(x * 0.005), x1=1250)
    # a few trees
    for i in range(7):
        tx = 120 + i * 130; conifer(ctx, tx, 820 + 0.12 * (tx - 900) + 10 * math.sin(tx * 0.005), 110 + 40 * hsh(i, 9), 1.0, seed=90 + i, sway_t=T, tiers=9, alpha=0.7)
    machines = [(600, lambda x, y: feller_buncher(ctx, x, y, 0.7, T * 4)), (880, lambda x, y: skidder(ctx, x, y, 0.65, logs=2)), (1130, lambda x, y: yarder(ctx, x, y, 0.6))]
    dash = (1360, 140)
    for k, (mx, draw) in enumerate(machines):
        my = 820 + 0.12 * (mx - 900) + 10 * math.sin(mx * 0.005) + 2
        draw(mx, my)
        p = seg(t, 1.0 + k * 0.6, 1.8 + k * 0.6)
        if p <= 0: continue
        # signal arcs
        for a in range(3):
            ap = seg((T * 1.2 + k * 0.3) % 1.0, a * 0.25, a * 0.25 + 0.5)
            set_col(ctx, C["aqua2"], 0.8 * (1 - ap) * ease_out_cubic(p)); ctx.set_line_width(3)
            ctx.new_path(); ctx.arc(mx, my - 150, 14 + a * 12 + ap * 6, -math.pi * 0.8, -math.pi * 0.2); ctx.stroke()
        # data line to the dashboard
        dp = ease_in_out(seg(t, 1.6 + k * 0.6, 2.8 + k * 0.6))
        ex, ey = mx + (dash[0] - mx) * dp, my - 160 + (dash[1] + 260 - (my - 160)) * dp
        cable(ctx, (mx, my - 160), (ex, ey), sag=-60 * dp, lw=1.6, col=C["aqua2"], alpha=0.7, dash=([6, 8], -T * 40))
    # dashboard card
    dp = seg(t, 2.6, 3.5)
    if dp > 0:
        e = ease_out_cubic(dp); x, y = dash[0], dash[1] + (1 - e) * 20
        glow(ctx, x + 230, y + 230, 380, hexc("#000000"), 0.12 * e)
        set_col(ctx, C["white"], 0.97 * e); rrect(ctx, x, y, 460, 500, 22); ctx.fill()
        set_col(ctx, NAVY, e); rrect(ctx, x, y, 460, 54, 22); ctx.fill(); ctx.rectangle(x, y + 30, 460, 24); ctx.fill()
        text(ctx, "MACHINE CONNECTIVITY  •  LIVE", x + 24, y + 34, 15, C["white"], fam="Jost Medium", tracking=3, alpha=e)
        ctx.new_path(); ctx.arc(x + 430, y + 27, 6, 0, 2 * math.pi); set_col(ctx, C["lime"], 0.6 + 0.4 * math.sin(T * 5)); ctx.fill()
        tiles = [("Production today", "m³", 412, 4.0), ("Machine hours", "h", 9.2, 4.4), ("Idle time", "%", 14, 4.8), ("Fuel used", "L", 286, 5.2), ("Turns / hour", "", 11, 5.6), ("Next move", "", None, 6.0)]
        for i, (lab, unit, val, at) in enumerate(tiles):
            p = seg(t, at, at + 0.7)
            if p <= 0: continue
            r, c = divmod(i, 2); tx, ty = x + 24 + c * 216, y + 80 + r * 138
            set_col(ctx, C["paper2"], ease_out_cubic(p)); rrect(ctx, tx, ty, 196, 118, 12); ctx.fill()
            text(ctx, lab.upper(), tx + 16, ty + 30, 12, C["grey"], fam="Jost Medium", tracking=2, alpha=ease_out_cubic(p))
            if val is None:
                text(ctx, "Planned", tx + 16, ty + 78, 30, C["green"], fam="Jost SemiBold", alpha=ease_out_cubic(p))
                text(ctx, "Block C → Block D, Thu", tx + 16, ty + 102, 14, C["ink"], fam="Jost", alpha=ease_out_cubic(p))
            else:
                v = val * ease_out_expo(seg(t, at, at + 2.2))
                s = f"{v:.1f}" if isinstance(val, float) else f"{int(round(v))}"
                text(ctx, s, tx + 16, ty + 82, 40, NAVY, fam="Jost Medium", alpha=ease_out_cubic(p))
                text(ctx, unit, tx + 22 + text_width(ctx, s), ty + 82, 18, C["grey"], fam="Jost", alpha=ease_out_cubic(p))
                # mini sparkline
                set_col(ctx, C["aqua2"], 0.8 * ease_out_cubic(p)); ctx.set_line_width(2)
                for j in range(0, 60, 4):
                    yy = ty + 100 - 8 * math.sin(j * 0.15 + T * 1.3 + i) - 4 * math.sin(j * 0.5 + i)
                    (ctx.move_to if j == 0 else ctx.line_to)(tx + 120 + j, yy)
                ctx.stroke()
    left_panel(ctx, 700, 780)
    eyebrow(ctx, "Technology", 120, 200, seg(t, 0.2, 0.9))
    reveal_text(ctx, "Connected machines.", 120, 300, 76, NAVY, seg(t, 0.4, 1.2), fam="Jost Light")
    reveal_text(ctx, "Live data from every machine, shared with the contractor.", 120, 360, 28, C["ink"], seg(t, 1.2, 2.0), fam="Jost Light")
    bullets(ctx, [("Plan blocks and moves together — fewer move days", 7.0), ("See idle time and fix it: waiting on trucks, on the yarder", 9.0),
                  ("Match the right machine to the right ground", 11.0), ("Pay contractors on accurate, shared numbers", 13.0),
                  ("Maintenance alerts before a breakdown stops the crew", 15.0), ("Location and check-ins for lone-worker safety", 17.0)], 120, 450, t, dy=52, size=23)

# ----------------------------------------------------------------------------- 8. outro (142-150)
def s_outro(ctx, t, T):
    paper_bg(ctx, T, 1.0, reveal=seg(t, 0.0, 1.6))
    reveal_text(ctx, "Better data. Better decisions.", 960, 380, 64, NAVY, seg(t, 0.3, 1.2), fam="Jost Light", align="center")
    reveal_text(ctx, "Stronger contractors.", 960, 460, 64, NAVY, seg(t, 0.6, 1.5), fam="Jost SemiBold", align="center")
    wordmark(ctx, 960, 660, 120, seg(t, 1.4, 2.6), ring_p=seg(t, 1.8, 3.0))
    reveal_text(ctx, "mosaicforests.com", 960, 790, 26, C["aqua2"], seg(t, 3.0, 3.8), fam="Jost Medium", align="center", tracking=3)
    fo = seg(T, R.DUR - 1.2, R.DUR - 0.2)
    if fo > 0: set_col(ctx, C["white"], ease_in_out(fo)); ctx.paint()

# ============================================================================= timeline
SCENES = [
    (0.0, 11.0, s_title, 1.0),
    (11.0, 33.0, s_ground, 1.0),
    (33.0, 58.0, s_cable, 1.0),
    (58.0, 86.0, s_tether, 1.0),
    (86.0, 111.0, s_piece, 1.0),
    (111.0, 131.0, s_mob, 1.0),
    (131.0, 153.0, s_connect, 1.0),
    (153.0, 161.0, s_outro, 1.0),
]
DUR = 161.0

def install():
    R.SCENES = SCENES; R.DUR = DUR; R.NFRAMES = int(DUR * R.FPS); R.TRANS = 1.8

install()

if __name__ == "__main__":
    import sys
    if "--out" not in sys.argv and "--stills" not in sys.argv:
        sys.argv += ["--out", os.path.join(R.OUT, "harvest_video.mp4")]
    R.main()
