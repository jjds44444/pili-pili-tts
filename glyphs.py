"""Procedural tribal/linocut glyphs and hand-cut edge treatment.

The published cards are built from a small vocabulary of hand-inked marks —
stacked chevrons, dot rows, zigzag bands, hatching, concentric arcs, staring
eyes — assembled into silhouettes (masks, totems, figures, suns, chillies).
This module rebuilds that vocabulary compositionally so every card can carry a
distinct glyph, deterministically seeded by card number.

Two public entry points:
    glyph(size, seed, colour)   -> RGBA layer holding one glyph
    scatter(size, seed, colour) -> RGBA layer of background glyphs
    roughen(mask, amount)       -> wobble a mask's edges so nothing reads as
                                   machine-drawn
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# --------------------------------------------------------------------------- #
# hand-cut edges
# --------------------------------------------------------------------------- #

def roughen(mask, amount=2.6, scale=9, bite=0.72):
    """Wobble the edge of an 'L' mask.

    Blurs the mask into a soft ramp, then thresholds it against low-frequency
    noise instead of a flat 128. Where the noise is high the edge pulls in,
    where it is low the edge pushes out — the result is an irregular, cut-by-hand
    contour rather than a mathematically exact one.
    """
    if amount <= 0:
        return mask
    w, h = mask.size
    soft = mask.filter(ImageFilter.GaussianBlur(amount))

    small = np.random.default_rng(abs(hash((w, h, scale))) % 2 ** 32)
    noise = small.random((max(2, h // scale), max(2, w // scale))).astype(np.float32)
    noise_img = Image.fromarray((noise * 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(amount * 0.8))

    a = np.asarray(soft, dtype=np.float32)
    n = np.asarray(noise_img, dtype=np.float32)
    thresh = 128.0 + (n - 128.0) * bite
    return Image.fromarray(((a > thresh) * 255).astype(np.uint8), "L")


def outline(mask, width=3):
    """Ring just outside `mask`, for the heavy black keyline on every shape."""
    grown = mask.filter(ImageFilter.MaxFilter(width * 2 + 1))
    return Image.fromarray(
        (np.asarray(grown, dtype=np.int16) - np.asarray(mask, dtype=np.int16))
        .clip(0, 255).astype(np.uint8), "L")


# --------------------------------------------------------------------------- #
# interior marks - the ink vocabulary
# --------------------------------------------------------------------------- #

def _chevrons(d, box, rng, ink):
    x0, y0, x1, y1 = box
    rows = rng.randint(2, 4)
    hgt = (y1 - y0) / rows
    for r in range(rows):
        y = y0 + r * hgt
        w = max(2, int((x1 - x0) * 0.10))
        d.line([(x0, y + hgt * 0.75), ((x0 + x1) / 2, y + hgt * 0.15),
                (x1, y + hgt * 0.75)], fill=ink, width=w, joint="curve")


def _dots(d, box, rng, ink):
    x0, y0, x1, y1 = box
    cols = rng.randint(2, 4)
    rows = rng.randint(2, 4)
    r = max(2, int(min(x1 - x0, y1 - y0) * 0.07))
    for i in range(cols):
        for j in range(rows):
            cx = x0 + (i + 0.5) * (x1 - x0) / cols
            cy = y0 + (j + 0.5) * (y1 - y0) / rows
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ink)


def _zigzag(d, box, rng, ink):
    x0, y0, x1, y1 = box
    n = rng.randint(3, 6)
    step = (x1 - x0) / n
    pts = []
    for i in range(n + 1):
        pts.append((x0 + i * step, y0 if i % 2 else y1))
    d.line(pts, fill=ink, width=max(2, int((y1 - y0) * 0.16)), joint="curve")


def _hatch(d, box, rng, ink):
    x0, y0, x1, y1 = box
    n = rng.randint(3, 7)
    for i in range(n):
        x = x0 + (i + 0.5) * (x1 - x0) / n
        d.line([(x, y0), (x, y1)], fill=ink, width=max(2, int((x1 - x0) * 0.045)))


def _eye(d, box, rng, ink):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) * 0.42, (y1 - y0) * 0.30
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=ink,
              width=max(2, int(ry * 0.28)))
    d.ellipse([cx - ry * 0.5, cy - ry * 0.5, cx + ry * 0.5, cy + ry * 0.5], fill=ink)
    if rng.random() < 0.6:                      # lashes
        for k in range(8):
            a = math.pi * (0.1 + 0.8 * k / 7)
            d.line([(cx - rx * math.cos(a), cy - ry * 1.1 * math.sin(a)),
                    (cx - rx * 1.45 * math.cos(a), cy - ry * 1.75 * math.sin(a))],
                   fill=ink, width=max(2, int(ry * 0.18)))


def _arcs(d, box, rng, ink):
    x0, y0, x1, y1 = box
    n = rng.randint(2, 4)
    for i in range(n):
        f = (i + 1) / (n + 0.4)
        cx, cy = (x0 + x1) / 2, y1
        rx, ry = (x1 - x0) * 0.5 * f, (y1 - y0) * f
        d.arc([cx - rx, cy - ry, cx + rx, cy + ry], 180, 360, fill=ink,
              width=max(2, int((y1 - y0) * 0.09)))


def _teeth(d, box, rng, ink):
    x0, y0, x1, y1 = box
    n = rng.randint(3, 6)
    step = (x1 - x0) / n
    for i in range(n):
        d.polygon([(x0 + i * step, y0), (x0 + (i + 1) * step, y0),
                   (x0 + (i + 0.5) * step, y1)], fill=ink)


MARKS = [_chevrons, _dots, _zigzag, _hatch, _eye, _arcs, _teeth]


def ink_fill(d, box, rng, ink, marks=None):
    """Stack a couple of random marks down `box`."""
    x0, y0, x1, y1 = box
    n = marks or rng.randint(2, 3)
    band = (y1 - y0) / n
    for i in range(n):
        fn = rng.choice(MARKS)
        pad = (x1 - x0) * 0.10
        fn(d, (x0 + pad, y0 + i * band + band * 0.15,
               x1 - pad, y0 + (i + 1) * band - band * 0.15), rng, ink)


# --------------------------------------------------------------------------- #
# silhouettes
# --------------------------------------------------------------------------- #

def _sil_shield(d, s, rng):
    d.polygon([(s * .18, s * .12), (s * .82, s * .12), (s * .82, s * .58),
               (s * .5, s * .90), (s * .18, s * .58)], fill=255)
    return (s * .24, s * .20, s * .76, s * .62)


def _sil_totem(d, s, rng):
    y = s * .10
    while y < s * .86:
        h = s * rng.uniform(.13, .22)
        w = s * rng.uniform(.28, .42)
        d.rounded_rectangle([s * .5 - w, y, s * .5 + w, y + h], s * .03, fill=255)
        y += h + s * .025
    return (s * .22, s * .14, s * .78, s * .80)


def _sil_mask(d, s, rng):
    d.rounded_rectangle([s * .20, s * .10, s * .80, s * .86], s * .18, fill=255)
    d.polygon([(s * .20, s * .30), (s * .04, s * .40), (s * .20, s * .52)], fill=255)
    d.polygon([(s * .80, s * .30), (s * .96, s * .40), (s * .80, s * .52)], fill=255)
    return (s * .26, s * .20, s * .74, s * .78)


def _sil_figure(d, s, rng):
    d.ellipse([s * .35, s * .06, s * .65, s * .34], fill=255)
    d.rounded_rectangle([s * .38, s * .34, s * .62, s * .70], s * .05, fill=255)
    w = max(3, int(s * .07))
    d.line([(s * .38, s * .42), (s * .12, s * .30)], fill=255, width=w)
    d.line([(s * .62, s * .42), (s * .88, s * .30)], fill=255, width=w)
    d.line([(s * .44, s * .70), (s * .34, s * .94)], fill=255, width=w)
    d.line([(s * .56, s * .70), (s * .66, s * .94)], fill=255, width=w)
    return (s * .40, s * .38, s * .60, s * .68)


def _sil_sun(d, s, rng):
    n = rng.randint(8, 12)
    for i in range(n):
        a = 2 * math.pi * i / n
        d.polygon([(s * .5 + s * .30 * math.cos(a - .18),
                    s * .5 + s * .30 * math.sin(a - .18)),
                   (s * .5 + s * .30 * math.cos(a + .18),
                    s * .5 + s * .30 * math.sin(a + .18)),
                   (s * .5 + s * .48 * math.cos(a), s * .5 + s * .48 * math.sin(a))],
                  fill=255)
    d.ellipse([s * .22, s * .22, s * .78, s * .78], fill=255)
    return (s * .30, s * .30, s * .70, s * .70)


def _sil_drop(d, s, rng):
    d.ellipse([s * .24, s * .34, s * .76, s * .90], fill=255)
    d.polygon([(s * .5, s * .06), (s * .27, s * .55), (s * .73, s * .55)], fill=255)
    return (s * .30, s * .42, s * .70, s * .84)


def _sil_hand(d, s, rng):
    d.rounded_rectangle([s * .30, s * .40, s * .70, s * .90], s * .10, fill=255)
    for i in range(4):
        x = s * (.32 + i * .115)
        d.rounded_rectangle([x, s * .16, x + s * .085, s * .48], s * .04, fill=255)
    d.rounded_rectangle([s * .16, s * .46, s * .34, s * .60], s * .05, fill=255)
    return (s * .34, s * .52, s * .66, s * .84)


def _sil_chili(d, s, rng):
    """A pod: shoulder at the stem end, long taper to a point, gentle hook.

    Profile peaks around t=0.25 and runs about 1:4 width to length, which is
    what stops it reading as a leaf or a comma.
    """
    steps = 140
    for i in range(steps + 1):
        t = i / steps
        prof = ((t + .08) ** .25) * ((1 - t) ** .60)
        r = s * .181 * prof
        x = s * .52 + s * .13 * math.sin(t * 2.2) - s * .10 * t
        y = s * .08 + s * .85 * t
        if r > 0.5:
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return (s * .44, s * .18, s * .62, s * .55)


def chili_stem_xy(s):
    """Where _sil_chili starts, so a stem can be attached to it."""
    return s * .52, s * .08


def _sil_spiral(d, s, rng):
    w = max(3, int(s * .085))
    pts = []
    for i in range(90):
        t = i / 89
        a = t * math.pi * 3.4
        r = s * .06 + s * .36 * t
        pts.append((s * .5 + r * math.cos(a), s * .5 + r * math.sin(a)))
    d.line(pts, fill=255, width=w, joint="curve")
    return None


def _sil_fish(d, s, rng):
    d.ellipse([s * .18, s * .32, s * .74, s * .68], fill=255)
    d.polygon([(s * .70, s * .50), (s * .94, s * .28), (s * .94, s * .72)], fill=255)
    return (s * .28, s * .40, s * .62, s * .60)


SILHOUETTES = [_sil_shield, _sil_totem, _sil_mask, _sil_figure, _sil_sun,
               _sil_drop, _sil_hand, _sil_chili, _sil_spiral, _sil_fish]


# --------------------------------------------------------------------------- #
# mission pictograms - these depict an effect, so they take no interior ink
# --------------------------------------------------------------------------- #

def _arrowhead(d, tip, ang, size):
    x, y = tip
    a1, a2 = ang + 2.5, ang - 2.5
    d.polygon([(x, y),
               (x + size * math.cos(a1), y + size * math.sin(a1)),
               (x + size * math.cos(a2), y + size * math.sin(a2))], fill=255)


def _sil_arrows_ring(d, s, rng):
    """Four arrows chasing each other round a ring - cards being passed on."""
    w = max(4, int(s * .085))
    r = s * .34
    for i in range(4):
        a0 = math.pi / 2 * i + .16
        a1 = a0 + 1.16
        pts = []
        for k in range(20):
            a = a0 + (a1 - a0) * k / 19
            pts.append((s * .5 + r * math.cos(a), s * .5 + r * math.sin(a)))
        d.line(pts, fill=255, width=w, joint="curve")
        _arrowhead(d, pts[-1], a1 + math.pi / 2, s * .17)
    return None


def _sil_swap(d, s, rng):
    w = max(3, int(s * .075))
    d.line([(s * .22, s * .34), (s * .78, s * .34)], fill=255, width=w)
    _arrowhead(d, (s * .80, s * .34), 0.0, s * .11)
    d.line([(s * .78, s * .66), (s * .22, s * .66)], fill=255, width=w)
    _arrowhead(d, (s * .20, s * .66), math.pi, s * .11)
    return None


def _sil_updown(d, s, rng):
    w = max(3, int(s * .085))
    d.line([(s * .33, s * .82), (s * .33, s * .24)], fill=255, width=w)
    _arrowhead(d, (s * .33, s * .14), -math.pi / 2, s * .13)
    d.line([(s * .67, s * .18), (s * .67, s * .76)], fill=255, width=w)
    _arrowhead(d, (s * .67, s * .86), math.pi / 2, s * .13)
    return None


def _sil_clock(d, s, rng):
    w = max(3, int(s * .075))
    d.ellipse([s * .16, s * .22, s * .84, s * .90], outline=255, width=w)
    d.rounded_rectangle([s * .42, s * .06, s * .58, s * .20], s * .03, fill=255)
    d.line([(s * .50, s * .56), (s * .50, s * .34)], fill=255, width=w)
    d.line([(s * .50, s * .56), (s * .68, s * .62)], fill=255, width=w)
    return None


def _sil_ban(d, s, rng):
    w = max(4, int(s * .10))
    d.ellipse([s * .14, s * .14, s * .86, s * .86], outline=255, width=w)
    d.line([(s * .26, s * .74), (s * .74, s * .26)], fill=255, width=w)
    return None


def _sil_eyecard(d, s, rng):
    """A card with an eye punched out of it - 'your hand is visible'."""
    d.rounded_rectangle([s * .18, s * .12, s * .82, s * .88], s * .08, fill=255)
    d.ellipse([s * .26, s * .38, s * .74, s * .64], fill=0)
    d.ellipse([s * .44, s * .44, s * .56, s * .58], fill=255)
    return None


def _sil_forehead(d, s, rng):
    """A head with a card held against the brow."""
    d.ellipse([s * .28, s * .36, s * .72, s * .86], fill=255)
    d.rounded_rectangle([s * .20, s * .08, s * .80, s * .32], s * .04, fill=255)
    d.ellipse([s * .38, s * .52, s * .45, s * .60], fill=0)
    d.ellipse([s * .55, s * .52, s * .62, s * .60], fill=0)
    d.arc([s * .40, s * .60, s * .60, s * .76], 20, 160, fill=0,
          width=max(2, int(s * .035)))
    return None


NAMED = {
    "arrows": _sil_arrows_ring, "swap": _sil_swap, "updown": _sil_updown,
    "clock": _sil_clock, "ban": _sil_ban, "eye": _sil_eyecard,
    "forehead": _sil_forehead, "hand": _sil_hand, "chili": _sil_chili,
    "sun": _sil_sun, "mask": _sil_mask, "figure": _sil_figure,
    "totem": _sil_totem, "shield": _sil_shield,
}


def glyph(size, seed, colour=(255, 255, 255), ink=(0, 0, 0), rough=True,
          silhouette=None):
    """One tribal glyph as an RGBA layer of the given square size.

    `silhouette` forces a named shape from NAMED; otherwise one is picked from
    SILHOUETTES by seed.
    """
    rng = random.Random(seed)
    s = size
    body = Image.new("L", (s, s), 0)
    bd = ImageDraw.Draw(body)
    fn = NAMED[silhouette] if silhouette else rng.choice(SILHOUETTES)
    interior = fn(bd, s, rng)
    if rough:
        body = roughen(body, amount=max(1.0, s * 0.012))

    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    layer.paste(Image.new("RGBA", (s, s), colour + (255,)), (0, 0), body)

    if interior is not None and rng.random() < 0.92:
        marks = Image.new("L", (s, s), 0)
        ink_fill(ImageDraw.Draw(marks), interior, rng, 255)
        # keep the ink strictly inside the silhouette
        marks = Image.fromarray(
            (np.minimum(np.asarray(marks), np.asarray(body))).astype(np.uint8), "L")
        layer.paste(Image.new("RGBA", (s, s), ink + (255,)), (0, 0), marks)

    return layer


def scatter(size, seed, colour, count=26, glyph_px=None, alpha=255, rough=False):
    """Background field of small glyphs, as on the real cards.

    Roughening is off by default here: at background size it eats the detail
    and leaves unrecognisable blobs.
    """
    w, h = size
    rng = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gp = glyph_px or int(min(w, h) * 0.16)
    for i in range(count):
        g = glyph(gp, seed * 1000 + i, colour=colour, ink=colour, rough=rough)
        g = g.rotate(rng.uniform(-22, 22), resample=Image.BICUBIC)
        if alpha < 255:
            g.putalpha(g.getchannel("A").point(lambda v: int(v * alpha / 255)))
        x = rng.randint(int(-gp * .3), int(w - gp * .7))
        y = rng.randint(int(-gp * .3), int(h - gp * .7))
        layer.alpha_composite(g, (x, y))
    return layer
