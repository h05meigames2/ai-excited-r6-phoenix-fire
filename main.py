#!/usr/bin/env python3
"""ai-excited-01 round 6: "The Phoenix That Set Its Own Painting on Fire"

A single deterministic image, drawn procedurally with the Python standard
library only (no PIL, no network, no assets, no clock, no unseeded
randomness). Running it writes one PNG to /output/entry.png.

Scene: a phoenix bursts OUT of its own gilded baroque painting - wings
smashing through the left and right of the frame, tail ribbons streaming
across the bottom edge, gold shards and embers flying, the painted dusk
sky still visible behind it.
"""

import math
import os
import random
import struct
import zlib

W = 768
H = 768
OUT = "/output/entry.png"
SEED = 20261116


# ---------------------------------------------------------------- raster --
class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, color, alpha=255):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        i = (y * self.w + x) * 3
        if alpha >= 255:
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]
        elif alpha > 0:
            inv = 255 - alpha
            self.px[i] = (color[0] * alpha + self.px[i] * inv) // 255
            self.px[i + 1] = (color[1] * alpha + self.px[i + 1] * inv) // 255
            self.px[i + 2] = (color[2] * alpha + self.px[i + 2] * inv) // 255

    def rect(self, x0, y0, x1, y1, color, alpha=255):
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w, x1)
        y1 = min(self.h, y1)
        for y in range(y0, y1):
            base = (y * self.w + x0) * 3
            if alpha >= 255:
                for x in range(x0, x1):
                    i = base + (x - x0) * 3
                    self.px[i] = color[0]
                    self.px[i + 1] = color[1]
                    self.px[i + 2] = color[2]
            else:
                for x in range(x0, x1):
                    self.set(x, y, color, alpha)

    def vgrad(self, x0, y0, x1, y1, top, bottom):
        """Vertical gradient rectangle."""
        for y in range(max(0, y0), min(self.h, y1)):
            t = (y - y0) / max(1, (y1 - y0 - 1))
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            self.rect(x0, y, x1, y + 1, c)

    def hgrad(self, x0, y0, x1, y1, left, right):
        for x in range(max(0, x0), min(self.w, x1)):
            t = (x - x0) / max(1, (x1 - x0 - 1))
            c = tuple(int(left[i] + (right[i] - left[i]) * t) for i in range(3))
            self.rect(x, y0, x + 1, y1, c)

    def ellipse(self, cx, cy, rx, ry, color, alpha=255):
        rx = int(rx)
        ry = int(ry)
        for y in range(max(0, cy - ry), min(self.h, cy + ry + 1)):
            dy = (y - cy) / ry
            if abs(dy) > 1:
                continue
            dx = rx * math.sqrt(1 - dy * dy)
            self.rect(int(cx - dx), y, int(cx + dx) + 1, y + 1, color, alpha)

    def circle(self, cx, cy, r, color, alpha=255):
        self.ellipse(cx, cy, r, r, color, alpha)

    def polygon(self, pts, color, alpha=255):
        """Even-odd scanline fill. pts: list of (x, y)."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(self.h - 1, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if y1p == y2p:
                    continue
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    t = (y - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.rect(int(xs[k]), y, int(xs[k + 1]) + 1, y + 1, color, alpha)

    def thick_line(self, x0, y0, x1, y1, width, color, alpha=255):
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            self.circle(x0, y0, width // 2, color, alpha)
            return
        nx = -dy / length * width / 2
        ny = dx / length * width / 2
        self.polygon(
            [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
             (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)],
            color, alpha)
        self.circle(x0, y0, width // 2, color, alpha)
        self.circle(x1, y1, width // 2, color, alpha)

    def ring(self, cx, cy, r, width, color, alpha=255):
        for k in range(width):
            rr = r - k
            for a in range(0, 360, 1):
                rad = math.radians(a)
                self.set(int(cx + rr * math.cos(rad)), int(cy + rr * math.sin(rad)),
                         color, alpha)

    def glow(self, cx, cy, radius, color, peak_alpha):
        """Soft radial glow: concentric ellipses, alpha fading outward."""
        steps = 26
        for s in range(steps, 0, -1):
            t = s / steps
            a = int(peak_alpha * (1 - t) * (1 - t))
            if a <= 0:
                continue
            self.ellipse(cx, cy, int(radius * t), int(radius * t), color, a)


def lerp(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def cubic_bezier(p0, p1, p2, p3, steps=28):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0]
             + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0])
        y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1]
             + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1])
        pts.append((x, y))
    return pts


def quad_bezier(p0, p1, p2, steps=24):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def ribbon(c, spine, widths, color, alpha=255):
    """A tapered ribbon along a spine of points with per-point widths."""
    left = []
    right = []
    n = len(spine)
    for i, (x, y) in enumerate(spine):
        if i == 0:
            dx, dy = spine[1][0] - x, spine[1][1] - y
        elif i == n - 1:
            dx, dy = x - spine[i - 1][0], y - spine[i - 1][1]
        else:
            dx, dy = spine[i + 1][0] - spine[i - 1][0], spine[i + 1][1] - spine[i - 1][1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        w = widths[i] / 2.0
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    c.polygon(left + right[::-1], color, alpha)


# ---------------------------------------------------------------- colors --
WALL_TOP = (10, 26, 34)
WALL_BOT = (14, 42, 51)
GOLD_DARK = (107, 74, 0)
GOLD = (212, 160, 23)
GOLD_LIGHT = (246, 211, 101)
GOLD_DEEP = (146, 100, 8)
SKY_TOP = (20, 26, 77)
SKY_MID = (74, 42, 109)
SKY_LOW = (179, 64, 42)
SKY_BOT = (232, 118, 42)
MTN = (43, 24, 66)
FLAME_RED = (214, 42, 30)
FLAME_ORANGE = (240, 106, 30)
FLAME_GOLD = (255, 201, 60)
FLAME_YELLOW = (255, 226, 120)
EMBER = (255, 150, 40)


# ---------------------------------------------------------------- scene ---
def draw_wall(c):
    c.vgrad(0, 0, W, H, WALL_TOP, WALL_BOT)
    # faint wall panels
    c.rect(0, 0, W, 6, (6, 18, 24))
    c.rect(0, H - 6, W, H, (6, 18, 24))


def draw_frame(c):
    # outer gold band with bevel: dark edge, bright face, inner shadow
    c.rect(56, 56, 712, 712, GOLD_DARK)
    c.rect(60, 60, 708, 708, GOLD)
    c.hgrad(60, 60, 708, 708, GOLD_LIGHT, GOLD)
    c.vgrad(60, 60, 708, 708, (232, 190, 60), (170, 118, 10))
    # groove lines
    c.rect(60, 60, 708, 66, GOLD_LIGHT)
    c.rect(60, 60, 66, 708, GOLD_LIGHT)
    c.rect(60, 702, 708, 708, GOLD_DEEP)
    c.rect(702, 60, 708, 708, GOLD_DEEP)
    c.rect(96, 96, 672, 104, GOLD_DEEP)
    c.rect(96, 96, 104, 672, GOLD_DEEP)
    c.rect(96, 664, 672, 672, GOLD_LIGHT)
    c.rect(664, 96, 672, 672, GOLD_LIGHT)
    # corner rosettes
    for (cx, cy) in [(80, 80), (688, 80), (80, 688), (688, 688)]:
        c.circle(cx, cy, 15, GOLD_DEEP)
        c.circle(cx, cy, 11, GOLD)
        c.circle(cx, cy, 6, GOLD_LIGHT)
        c.circle(cx, cy, 2, GOLD_DEEP)


def draw_painting(c, rng):
    # dusk sky inside the frame
    for y in range(104, 664):
        t = (y - 104) / 560.0
        if t < 0.45:
            col = lerp(SKY_TOP, SKY_MID, t / 0.45)
        elif t < 0.8:
            col = lerp(SKY_MID, SKY_LOW, (t - 0.45) / 0.35)
        else:
            col = lerp(SKY_LOW, SKY_BOT, (t - 0.8) / 0.2)
        c.rect(104, y, 664, y + 1, col)
    # stars (upper sky only)
    for _ in range(70):
        x = rng.randint(112, 656)
        y = rng.randint(112, 330)
        r = rng.choice([1, 1, 1, 2])
        a = rng.randint(120, 235)
        c.circle(x, y, r, (255, 244, 214), a)
    # crescent moon, upper left
    c.circle(178, 168, 30, (255, 238, 190))
    c.circle(190, 160, 26, SKY_TOP)
    # distant mountains
    c.polygon([(104, 664), (104, 560), (190, 500), (280, 566), (360, 512),
               (450, 570), (540, 506), (620, 562), (664, 530), (664, 664)],
              MTN)
    c.polygon([(104, 664), (104, 620), (230, 580), (330, 624), (470, 584),
               (580, 626), (664, 596), (664, 664)], (30, 16, 50))
    # warm glow behind the phoenix
    c.glow(384, 380, 250, (255, 120, 30), 46)
    c.glow(384, 380, 150, (255, 190, 80), 60)


def feather(c, base, tip, width, color, curve=0.0, alpha=255):
    """One tapered feather from base toward tip, bowed by `curve`."""
    mx = (base[0] + tip[0]) / 2 - curve
    my = (base[1] + tip[1]) / 2
    spine = quad_bezier(base, (mx, my), tip, 20)
    widths = [width * (1 - i / (len(spine) - 1)) ** 0.7 + 1
              for i in range(len(spine))]
    ribbon(c, spine, widths, color, alpha)
    # central shaft highlight
    c.thick_line(int(base[0]), int(base[1]), int(tip[0]), int(tip[1]),
                 2, lerp(color, (255, 255, 255), 0.35), 110)


def draw_wing(c, mirror):
    """One spread wing. mirror=-1 left, +1 right."""
    sx = 352 if mirror < 0 else 416
    sy = 352
    # top primary feather smashes almost to the frame's outer edge
    tips = [(64, 224), (104, 284), (146, 328), (192, 362), (236, 386)]
    if mirror > 0:
        tips = [(768 - x, y + (6 if i % 2 else -4)) for i, (x, y) in enumerate(tips)]
    cols = [FLAME_RED, FLAME_ORANGE, FLAME_RED, FLAME_GOLD, FLAME_ORANGE]
    # under-layer: broad wing membrane so gaps read as one wing
    fan = [(sx, sy)]
    for (tx, ty) in tips:
        fan.append((tx, ty))
    fan.append((sx + 40 * mirror, sy + 70))
    c.polygon(fan, (178, 32, 22), 235)
    # individual feathers fanning out, bases spread along a small arc so
    # they separate instead of merging into one flat triangle
    for idx, ((tx, ty), col) in enumerate(zip(tips, cols)):
        bx = sx + (idx - 2) * 7 * mirror
        by = sy + abs(idx - 2) * 5
        feather(c, (bx, by), (tx, ty), 36, col, curve=26 * mirror)
        # dark separation line between neighbouring feathers
        if idx < len(tips) - 1:
            nx, ny = tips[idx + 1]
            c.thick_line(int((tx + nx) / 2), int((ty + ny) / 2),
                         int(sx + idx * 4 * mirror), int(sy + 26),
                         2, (140, 22, 16), 120)
    # second row, shorter, brighter
    tips2 = [(150, 300), (185, 340), (225, 372), (262, 392)]
    if mirror > 0:
        tips2 = [(768 - x, y) for (x, y) in tips2]
    for (tx, ty) in tips2:
        feather(c, (sx + 6 * mirror, sy + 18), (tx, ty), 26, FLAME_GOLD,
                curve=18 * mirror)
    # shoulder coverts
    c.ellipse(sx + 8 * mirror, sy + 22, 46, 34, FLAME_ORANGE)
    c.ellipse(sx + 8 * mirror, sy + 22, 30, 22, FLAME_GOLD)


def draw_tail(c):
    ends = [(288, 712), (330, 740), (384, 750), (438, 738), (480, 714)]
    cols = [FLAME_RED, FLAME_ORANGE, FLAME_GOLD, FLAME_ORANGE, FLAME_RED]
    for (ex, ey), col in zip(ends, cols):
        # S-curved ribbon: two control points bow it sideways
        spine = cubic_bezier((384, 470),
                             (384 + (ex - 384) * 0.15, 560),
                             (384 + (ex - 384) * 0.85, 640),
                             (ex, ey), 30)
        widths = [30 * (1 - i / (len(spine) - 1)) ** 0.6 + 2
                  for i in range(len(spine))]
        ribbon(c, spine, widths, col)
        # rounded flame tip, not an arrowhead
        c.ellipse(ex, ey - 4, 7, 10, FLAME_YELLOW)
    # thin bright streamers between ribbons
    for ex in (312, 358, 410, 456):
        spine = cubic_bezier((384, 480),
                             (384 + (ex - 384) * 0.2, 580),
                             (384 + (ex - 384) * 0.7, 660),
                             (ex, 736), 24)
        ribbon(c, spine, [7] * len(spine), FLAME_YELLOW, 200)


def draw_body_head(c):
    # body: flame teardrop, chest toward viewer
    c.ellipse(384, 402, 62, 80, FLAME_ORANGE)
    c.ellipse(384, 416, 48, 62, FLAME_RED)
    c.ellipse(384, 428, 34, 44, FLAME_GOLD)
    c.ellipse(372, 396, 18, 26, FLAME_YELLOW, 200)
    # neck
    c.polygon([(362, 340), (406, 340), (398, 300), (370, 300)], FLAME_ORANGE)
    # head
    c.ellipse(384, 268, 36, 32, FLAME_ORANGE)
    c.ellipse(384, 272, 26, 22, FLAME_GOLD)
    # crest: three broad flame feathers sweeping up-left
    for (tx, ty), col in [((312, 192), FLAME_RED), ((350, 176), FLAME_ORANGE),
                          ((390, 172), FLAME_GOLD)]:
        feather(c, (384, 244), (tx, ty), 26, col, curve=-16)
    # beak, pointing up-right (head turned, calling out)
    c.polygon([(400, 250), (446, 254), (406, 276)], (255, 214, 90))
    c.polygon([(400, 250), (446, 254), (426, 262)], (214, 150, 20))
    # eye: bright, determined
    c.circle(398, 258, 7, (255, 255, 255))
    c.circle(399, 258, 4, (20, 8, 4))
    c.circle(401, 256, 2, (255, 255, 255))
    # cheek flame tuft
    c.polygon([(352, 282), (336, 296), (354, 292)], FLAME_RED)


def draw_break(c, rng):
    # short, sparse cracks from each wing-impact point on the frame:
    # a small dark chip plus 3 short lines fanning outward
    for (ix, iy, angs) in [
            (100, 306, (2.6, 3.1, 3.6)),   # left frame, fanning left
            (668, 310, (-0.5, 0.0, 0.5)),  # right frame, fanning right
    ]:
        c.circle(ix, iy, 3, (52, 28, 4))
        for ang in angs:
            ln = rng.randint(10, 18)
            x1 = ix + int(ln * math.cos(ang))
            y1 = iy + int(ln * math.sin(ang))
            c.thick_line(ix, iy, x1, y1, 2, (52, 28, 4))
    # gold shards flying outward
    shard_spots = [(82, 268, -1), (74, 356, -1), (690, 272, 1), (696, 352, 1),
                   (330, 716, 0), (452, 712, 0)]
    for (sx, sy, d) in shard_spots:
        w = rng.randint(10, 18)
        h = rng.randint(6, 10)
        ang = rng.uniform(0, 3.14)
        pts = []
        for k in range(4):
            a = ang + k * 1.57
            r = w if k % 2 == 0 else h
            pts.append((sx + r * math.cos(a), sy + r * math.sin(a)))
        c.polygon(pts, GOLD_LIGHT if d else GOLD)
        # motion streak behind each shard
        c.thick_line(sx - d * 26, sy + 10, sx - d * 6, sy + 2, 2,
                     (255, 220, 130), 150)


def draw_embers(c, rng):
    for _ in range(46):
        ang = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(120, 330)
        x = int(384 + dist * math.cos(ang) * 1.15)
        y = int(390 + dist * math.sin(ang) * 0.95)
        if not (0 <= x < W and 0 <= y < H):
            continue
        r = rng.choice([1, 2, 2, 3, 3, 4])
        col = rng.choice([FLAME_YELLOW, EMBER, FLAME_ORANGE, (255, 90, 30)])
        c.circle(x, y, r + 2, col, 60)
        c.circle(x, y, r, col, 230)
    # a few bright sparks near the wingtips
    for (x, y) in [(96, 238), (676, 244), (300, 724), (470, 720)]:
        c.circle(x, y, 5, FLAME_YELLOW, 90)
        c.circle(x, y, 2, (255, 255, 220))


def vignette(c):
    cx, cy = W / 2, H / 2
    maxd = math.hypot(cx, cy)
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - cx, y - cy) / maxd
            if d > 0.62:
                f = 1 - 0.30 * ((d - 0.62) / 0.38) ** 2
                i = (y * W + x) * 3
                c.px[i] = int(c.px[i] * f)
                c.px[i + 1] = int(c.px[i + 1] * f)
                c.px[i + 2] = int(c.px[i + 2] * f)


def render():
    rng = random.Random(SEED)
    c = Canvas(W, H)
    draw_wall(c)
    draw_frame(c)
    draw_painting(c, rng)
    draw_tail(c)
    draw_wing(c, -1)
    draw_wing(c, +1)
    draw_body_head(c)
    draw_break(c, rng)
    draw_embers(c, rng)
    vignette(c)
    return c


# ---------------------------------------------------------------- png -----
def write_png(path, canvas):
    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return out

    raw = bytearray()
    stride = canvas.w * 3
    for y in range(canvas.h):
        raw.append(0)  # filter: none
        raw += canvas.px[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    canvas = render()
    n = write_png(OUT, canvas)
    print(f"wrote {OUT} ({canvas.w}x{canvas.h}, {n} bytes)")


if __name__ == "__main__":
    main()
