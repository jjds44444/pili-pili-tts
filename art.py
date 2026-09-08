"""Card art for the Pili Pili TTS mod.

Drawn to match the published cards' linocut/tribal look: flat colour bands by
value, a big centre numeral in white with a heavy black keyline and tribal ink
marks inside the digit shapes, indices in all four corners, and a field of
scattered glyphs in a darker tone of the card colour. Glyph vocabulary and the
hand-cut edge treatment live in glyphs.py.

Everything renders at SS x size and is downsampled, because the roughened edges
need the resolution to read cleanly.
"""
import json
import math
import os
import random
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import glyphs


def stable_hash(text):
    """A hash of `text` that is the same every run.

    Python randomises str hash() per-process (PEP 456), so seeding art off
    hash(title) made every mission/tile's glyph and background reshuffle on
    every rebuild - a rebuild with no real content change still produced a
    huge, meaningless diff. crc32 is stable and plenty for a seed.
    """
    return zlib.crc32(text.encode("utf-8"))

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

FONT_DIR = r"C:\Windows\Fonts"
FONT_BLACK = os.path.join(FONT_DIR, "seguibl.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "arialbd.ttf")
FONT_REG = os.path.join(FONT_DIR, "arial.ttf")

CARD_W, CARD_H = 400, 560
BID_W, BID_H = 300, 420
SS = 2                      # supersample factor

INK = (18, 16, 16)
PAPER = (252, 250, 246)
CHILI_RED = (222, 44, 38)
LEAF = (108, 178, 52)

# value bands, eyeballed from the published cards
BANDS = [
    (11, (44, 116, 206)),      # 1-11   blue
    (22, (26, 194, 216)),      # 12-22  cyan
    (33, (92, 198, 61)),       # 23-33  green
    (41, (246, 197, 30)),      # 34-41  yellow
    (55, (231, 50, 44)),       # 42-55  red
]


def font(path, size):
    return ImageFont.truetype(path, size)


def band_colour(value):
    for top, col in BANDS:
        if value <= top:
            return col
    return BANDS[-1][1]


def shade(col, f):
    return tuple(max(0, min(255, int(c * f))) for c in col)


def fit_font(path, text, max_w, max_h, probe=100):
    """Font sized so `text` fills the box - a lone '4' should read as big as
    a '44', which a fixed point size never gives you."""
    f = font(path, probe)
    bb = f.getbbox(text)
    tw, th = max(1, bb[2] - bb[0]), max(1, bb[3] - bb[1])
    return font(path, max(8, int(probe * min(max_w / tw, max_h / th))))


# light marks only - the heavy ones swallow a digit stroke
def _digit_marks(mask, stroke, seed):
    """Sparse ink inside a digit: sized to the stroke, never spanning it."""
    a = np.asarray(mask)
    out = Image.new("L", mask.size, 0)
    if not a.any():
        return out

    # Sample mark centres from the stroke's interior, not its edge: a mark
    # placed on the boundary gets clipped to a sliver and reads as dirt.
    # Blur-and-threshold is a cheap stand-in for a big erosion kernel.
    soft = mask.filter(ImageFilter.GaussianBlur(max(1.0, stroke * 0.24)))
    inner = np.asarray(soft) > 190
    ys, xs = np.nonzero(inner if inner.any() else a)
    if len(xs) == 0:
        return out
    rng = random.Random(seed)
    n = int(len(xs) / max(1.0, stroke * stroke) * 1.6)
    n = max(4, min(12, n))
    d = ImageDraw.Draw(out)
    s = stroke
    for _ in range(n):
        i = rng.randrange(len(xs))
        cx, cy = float(xs[i]), float(ys[i])
        kind = rng.choice(("dot", "dots", "chev", "hatch", "ring"))
        if kind == "dot":
            r = s * .15
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
        elif kind == "dots":
            r = s * .11
            for k in (-1, 0, 1):
                x = cx + k * s * .32
                d.ellipse([x - r, cy - r, x + r, cy + r], fill=255)
        elif kind == "chev":
            half, wdt = s * .32, max(1, int(s * .13))
            d.line([(cx - half, cy + half * .5), (cx, cy - half * .45),
                    (cx + half, cy + half * .5)], fill=255, width=wdt, joint="curve")
        elif kind == "hatch":
            wdt = max(1, int(s * .11))
            for k in (-1, 0, 1):
                x = cx + k * s * .26
                d.line([(x, cy - s * .34), (x, cy + s * .34)], fill=255, width=wdt)
        else:
            r, wdt = s * .20, max(1, int(s * .10))
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=wdt)
    return Image.fromarray(np.minimum(np.asarray(out), a).astype(np.uint8), "L")


def inked_numeral(layer, centre, text, fnt, key_width, rough, seed,
                  fill=(255, 255, 255), key=INK, tracking=0.07):
    """The big centre number: digits set individually so they get their own
    ink and a little breathing room, then one shared keyline."""
    w, h = layer.size
    cx, cy = centre
    advances = [fnt.getlength(ch) for ch in text]
    gap = tracking * (sum(advances) / len(advances))
    total = sum(advances) + gap * (len(text) - 1)

    per_digit = []
    x = cx - total / 2.0
    for ch, adv in zip(text, advances):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text((x + adv / 2.0, cy), ch, font=fnt, fill=255, anchor="mm")
        if rough:
            m = glyphs.roughen(m, amount=rough)
        per_digit.append(m)
        x += adv + gap

    whole = per_digit[0]
    for m in per_digit[1:]:
        whole = Image.fromarray(
            np.maximum(np.asarray(whole), np.asarray(m)).astype(np.uint8), "L")

    ring = glyphs.outline(whole, key_width)
    layer.paste(Image.new("RGBA", (w, h), key + (255,)), (0, 0), ring)
    layer.paste(Image.new("RGBA", (w, h), fill + (255,)), (0, 0), whole)

    stroke = max(4.0, fnt.size * 0.21)
    for i, m in enumerate(per_digit):
        marks = _digit_marks(m, stroke, seed * 31 + i)
        layer.paste(Image.new("RGBA", (w, h), key + (255,)), (0, 0), marks)


def inked_text(layer, xy, text, fnt, anchor="mm", fill=(255, 255, 255),
               key=INK, key_width=4, marks_seed=None, rough=2.2):
    """Text as a hand-cut shape: roughened, heavy keyline, optional ink marks
    inside the letterforms - the treatment on the real cards' numerals."""
    w, h = layer.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255, anchor=anchor)
    if rough:
        mask = glyphs.roughen(mask, amount=rough)

    ring = glyphs.outline(mask, key_width)
    layer.paste(Image.new("RGBA", (w, h), key + (255,)), (0, 0), ring)
    layer.paste(Image.new("RGBA", (w, h), fill + (255,)), (0, 0), mask)

    if marks_seed is not None:
        bbox = mask.getbbox()
        if bbox:
            marks = Image.new("L", (w, h), 0)
            rng = random.Random(marks_seed)
            glyphs.ink_fill(ImageDraw.Draw(marks), bbox, rng, 255, marks=4)
            marks = Image.fromarray(
                np.minimum(np.asarray(marks), np.asarray(mask)).astype(np.uint8), "L")
            layer.paste(Image.new("RGBA", (w, h), key + (255,)), (0, 0), marks)


# --------------------------------------------------------------------------- #
# faces
# --------------------------------------------------------------------------- #

def number_card(value):
    w, h = CARD_W * SS, CARD_H * SS
    base = band_colour(value)
    card = Image.new("RGBA", (w, h), base + (255,))

    card.alpha_composite(glyphs.scatter((w, h), seed=value * 31 + 7,
                                        colour=shade(base, 0.91),
                                        count=52, glyph_px=int(w * 0.105)))

    big = fit_font(FONT_BLACK, str(value), w * 0.68, h * 0.34)
    inked_numeral(card, (w // 2, int(h * 0.50)), str(value), big,
                  key_width=max(5, int(w * 0.020)), rough=w * 0.005,
                  seed=value * 977)

    small = font(FONT_BLACK, int(h * 0.095))
    pad_x, pad_y = int(w * 0.095), int(h * 0.070)
    corner = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    inked_text(corner, (pad_x, pad_y), str(value), small,
               key_width=max(2, int(w * 0.007)), rough=w * 0.002)
    inked_text(corner, (w - pad_x, pad_y), str(value), small,
               key_width=max(2, int(w * 0.007)), rough=w * 0.002)
    card.alpha_composite(corner)
    card.alpha_composite(corner.rotate(180))

    return card.resize((CARD_W, CARD_H), Image.LANCZOS).convert("RGB")


def joker_card():
    w, h = CARD_W * SS, CARD_H * SS
    card = Image.new("RGBA", (w, h), (16, 15, 15, 255))
    card.alpha_composite(glyphs.scatter((w, h), seed=4242, colour=(44, 41, 40),
                                        count=34, glyph_px=int(w * 0.15)))

    s = int(w * 0.62)
    pod = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    body = Image.new("L", (s, s), 0)
    glyphs._sil_chili(ImageDraw.Draw(body), s, random.Random(1))
    body = glyphs.roughen(body, amount=s * 0.01)
    pod.paste(Image.new("RGBA", (s, s), CHILI_RED + (255,)), (0, 0), body)
    stem = Image.new("L", (s, s), 0)
    sd = ImageDraw.Draw(stem)
    sd.line([(s * .52, s * .13), (s * .43, s * .01)], fill=255, width=int(s * .05))
    sd.ellipse([s * .45, s * .00, s * .59, s * .07], fill=255)
    pod.paste(Image.new("RGBA", (s, s), LEAF + (255,)), (0, 0), stem)
    card.alpha_composite(pod, ((w - s) // 2, int(h * 0.20)))

    d = ImageDraw.Draw(card)
    d.text((w // 2, int(h * 0.855)), "JOKER", font=font(FONT_BLACK, int(h * 0.085)),
           fill=PAPER, anchor="mm")
    d.text((w // 2, int(h * 0.925)), "any value 0 - 56",
           font=font(FONT_BOLD, int(h * 0.038)), fill=(196, 190, 182), anchor="mm")
    return card.resize((CARD_W, CARD_H), Image.LANCZOS).convert("RGB")


# which pictogram depicts which effect
MISSION_ICONS = {
    "Pass Left": "arrows", "Pass Right": "arrows", "Double Pass": "arrows",
    "Double Back": "arrows", "Hand Over": "arrows", "Hand Back": "arrows",
    "No Zero": "ban", "No One": "ban", "No Echo": "ban", "No Doubles": "ban",
    "One More": "hand", "Open Hand": "eye", "Forehead": "forehead",
    "Blind Round": "forehead", "All At Once": "sun", "Cool Down": "chili",
    "Upside Down": "updown", "High Or Low": "updown", "Trade Off": "swap",
    "Three Seconds": "clock", "Quickfire": "clock",
    "First & Last": "totem", "Cursed Cards": "mask", "Shared Burn": "figure",
}


def mission_card(title, body, cards, expert=False):
    w, h = CARD_W * SS, CARD_H * SS
    card = Image.new("RGBA", (w, h), PAPER + (255,))
    card.alpha_composite(glyphs.scatter((w, h), seed=stable_hash(title) % 9991,
                                        colour=(235, 231, 223), count=26,
                                        glyph_px=int(w * 0.15)))

    accent = CHILI_RED if expert else (34, 32, 32)
    d = ImageDraw.Draw(card)

    d.text((w // 2, int(h * 0.055)), "EXPERT MISSION" if expert else "MISSION",
           font=font(FONT_BOLD, int(h * 0.035)), fill=accent, anchor="mm")

    # pictogram: solid ink so it reads on the pale card
    s = int(w * 0.38)
    pic = glyphs.glyph(s, seed=stable_hash(title) % 99991, colour=INK, ink=PAPER,
                       silhouette=MISSION_ICONS.get(title))
    card.alpha_composite(pic, ((w - s) // 2, int(h * 0.105)))

    # lay the text out from the bottom up so the blocks cannot collide
    lines = body.split("\n")
    bs = int(h * 0.042)
    bf = font(FONT_REG, bs)
    while max(d.textlength(l, font=bf) for l in lines) > w * 0.84 and bs > int(h * 0.024):
        bs -= 1
        bf = font(FONT_REG, bs)
    gap = int(h * 0.013)
    block = len(lines) * bs + (len(lines) - 1) * gap
    body_bottom = int(h * 0.80)
    y = body_bottom - block + bs // 2

    size = int(h * 0.072)
    fnt = font(FONT_BLACK, size)
    while d.textlength(title.upper(), font=fnt) > w * 0.88 and size > int(h * 0.038):
        size -= 2
        fnt = font(FONT_BLACK, size)
    d.text((w // 2, y - bs // 2 - int(h * 0.032) - size // 2), title.upper(),
           font=fnt, fill=INK, anchor="mm")

    for line in lines:
        d.text((w // 2, y), line, font=bf, fill=(62, 58, 56), anchor="mm")
        y += bs + gap

    # deal count, dark box bottom-left as on the real cards
    box = int(w * 0.19)
    bx, by = int(w * 0.055), h - box - int(w * 0.05)
    d.rounded_rectangle([bx, by, bx + box, by + box], int(box * 0.16), fill=accent)
    d.text((bx + box // 2, by + box // 2), str(cards),
           font=font(FONT_BLACK, int(box * 0.60)), fill=PAPER, anchor="mm")

    if expert:
        d.rectangle([0, 0, w - 1, h - 1], outline=CHILI_RED, width=int(w * 0.022))

    return card.resize((CARD_W, CARD_H), Image.LANCZOS).convert("RGB")


def plaque(cw, ch, title, ground=(20, 18, 18), accent=(232, 196, 92),
           chilli=False, title_frac=0.30, title_y=0.5):
    """Dark tile used for the in-world control objects: dibbers, round button.

    `title=None` skips the baked title entirely - for a tile whose meaning is
    already carried by a runtime button overlay (the dibber's number row, for
    instance), baking a second, static label into the same central space just
    gives the two something to visually collide with. `title_y` moves the
    title off-centre (as a fraction of height) for tiles where a button DOES
    still need the centre - see mission_toggle, whose title used to sit right
    under its own on/off button.
    """
    w, h = cw * SS, ch * SS
    seed_text = title or "plaque"
    tile = Image.new("RGBA", (w, h), ground + (255,))
    tile.alpha_composite(glyphs.scatter((w, h), seed=stable_hash(seed_text) % 7777,
                                        colour=shade(ground, 2.4),
                                        count=26, glyph_px=int(min(w, h) * 0.30)))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle([int(w * .012), int(h * .022), w - int(w * .012), h - int(h * .022)],
                        int(min(w, h) * .09), outline=accent, width=max(3, int(min(w, h) * .022)))

    if chilli:
        s = int(h * 0.52)
        pod = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        b = Image.new("L", (s, s), 0)
        glyphs._sil_chili(ImageDraw.Draw(b), s, random.Random(2))
        b = glyphs.roughen(b, amount=s * 0.012)
        pod.paste(Image.new("RGBA", (s, s), CHILI_RED + (255,)), (0, 0), b)
        st = Image.new("L", (s, s), 0)
        ImageDraw.Draw(st).line([(s * .52, s * .13), (s * .43, s * .01)],
                                fill=255, width=max(2, int(s * .05)))
        pod.paste(Image.new("RGBA", (s, s), LEAF + (255,)), (0, 0), st)
        tile.alpha_composite(pod, (int(w * .07), (h - s) // 2))
        tx = int(w * .58)
    else:
        tx = w // 2

    if title:
        fnt = fit_font(FONT_BLACK, title, w * (0.62 if chilli else 0.80), h * title_frac)
        d.text((tx, int(h * title_y)), title, font=fnt, fill=PAPER, anchor="mm")
    return tile.resize((cw, ch), Image.LANCZOS).convert("RGB")


def dealer_token():
    s = 512
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ring = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ring).ellipse([6, 6, s - 6, s - 6], fill=255)
    body = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    body.paste(Image.new("RGBA", (s, s), (232, 196, 92, 255)), (0, 0), ring)
    body.alpha_composite(glyphs.scatter((s, s), seed=88, colour=(210, 172, 70),
                                        count=16, glyph_px=int(s * 0.20)))
    body.putalpha(ring)
    d = ImageDraw.Draw(body)
    d.ellipse([16, 16, s - 16, s - 16], outline=INK, width=12)
    d.text((s // 2, int(s * 0.42)), "DEALER", font=font(FONT_BLACK, int(s * 0.15)),
           fill=INK, anchor="mm")
    d.text((s // 2, int(s * 0.60)), "bets & leads", font=font(FONT_BOLD, int(s * 0.075)),
           fill=(90, 74, 40), anchor="mm")
    return body


def back(cw, ch, label, tint, sub=None):
    """Black back with the glyph field, a flaming mask and crossed chillies."""
    w, h = cw * SS, ch * SS
    card = Image.new("RGBA", (w, h), (16, 15, 15, 255))
    card.alpha_composite(glyphs.scatter((w, h), seed=77, colour=(46, 43, 42),
                                        count=40, glyph_px=int(w * 0.14)))

    s = int(w * 0.52)
    cx, cy = (w - s) // 2, int(h * 0.30)

    # flames licking up from behind the top of the mask
    fh = int(s * 0.72)
    flame = Image.new("RGBA", (s, fh), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flame)
    for col, spread, height in [((228, 62, 28), 0.50, 1.00),
                                ((244, 142, 26), 0.36, 0.78),
                                ((250, 206, 62), 0.20, 0.52)]:
        tongues = 5
        for t in range(tongues):
            f = (t - (tongues - 1) / 2) / max(1, (tongues - 1) / 2)   # -1..1
            base = s * 0.5 + f * s * spread * 0.9
            tip_h = fh * height * (1.0 - 0.45 * abs(f))
            bw = s * 0.13 * spread / 0.5
            fd.polygon([
                (base - bw, fh),
                (base - bw * 0.35, fh - tip_h * 0.55),
                (base + f * bw * 0.9, fh - tip_h),          # tip leans outward
                (base + bw * 0.35, fh - tip_h * 0.5),
                (base + bw, fh),
            ], fill=col + (255,))
    card.alpha_composite(flame, (cx, cy - fh + int(s * 0.22)))

    # crossed chillies
    for sign in (-1, 1):
        cs = int(s * 0.78)
        pod = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
        b = Image.new("L", (cs, cs), 0)
        glyphs._sil_chili(ImageDraw.Draw(b), cs, random.Random(2))
        b = glyphs.roughen(b, amount=cs * 0.01)
        pod.paste(Image.new("RGBA", (cs, cs), CHILI_RED + (255,)), (0, 0), b)
        st = Image.new("L", (cs, cs), 0)
        sd = ImageDraw.Draw(st)
        sd.line([(cs * .52, cs * .13), (cs * .43, cs * .01)], fill=255,
                width=int(cs * .05))
        pod.paste(Image.new("RGBA", (cs, cs), LEAF + (255,)), (0, 0), st)
        # crossed low and splayed outward, behind the chin of the mask
        pod = pod.rotate(sign * 128, resample=Image.BICUBIC, expand=False)
        card.alpha_composite(pod, (cx + int(sign * s * 0.30), cy + int(s * 0.46)))

    # mask
    m = Image.new("L", (s, s), 0)
    glyphs._sil_mask(ImageDraw.Draw(m), s, random.Random(3))
    m = glyphs.roughen(m, amount=s * 0.01)
    face = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    face.paste(Image.new("RGBA", (s, s), PAPER + (255,)), (0, 0), m)
    marks = Image.new("L", (s, s), 0)
    md = ImageDraw.Draw(marks)
    glyphs._eye(md, (s * .28, s * .30, s * .48, s * .46), random.Random(4), 255)
    glyphs._eye(md, (s * .52, s * .30, s * .72, s * .46), random.Random(6), 255)
    glyphs._teeth(md, (s * .30, s * .58, s * .70, s * .74), random.Random(7), 255)
    glyphs._chevrons(md, (s * .32, s * .14, s * .68, s * .26), random.Random(8), 255)
    marks = Image.fromarray(
        np.minimum(np.asarray(marks), np.asarray(m)).astype(np.uint8), "L")
    face.paste(Image.new("RGBA", (s, s), INK + (255,)), (0, 0), marks)
    card.alpha_composite(face, (cx, cy))

    d = ImageDraw.Draw(card)
    d.text((w // 2, int(h * 0.855)), label, font=font(FONT_BLACK, int(h * 0.088)),
           fill=PAPER, anchor="mm")
    if sub:
        d.text((w // 2, int(h * 0.925)), sub, font=font(FONT_BOLD, int(h * 0.042)),
               fill=tint, anchor="mm")
    return card.resize((cw, ch), Image.LANCZOS).convert("RGB")


def pili_token():
    s = 512 * 2
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, s - 8, s - 8], fill=(18, 16, 16, 255))
    img.alpha_composite(glyphs.scatter((s, s), seed=31, colour=(48, 44, 42),
                                       count=18, glyph_px=int(s * 0.16)))
    ring = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ring).ellipse([8, 8, s - 8, s - 8], fill=255)
    img.putalpha(ring)

    cs = int(s * 0.62)
    b = Image.new("L", (cs, cs), 0)
    glyphs._sil_chili(ImageDraw.Draw(b), cs, random.Random(2))
    b = glyphs.roughen(b, amount=cs * 0.01)
    pod = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    pod.paste(Image.new("RGBA", (cs, cs), CHILI_RED + (255,)), (0, 0), b)
    st = Image.new("L", (cs, cs), 0)
    ImageDraw.Draw(st).line([(cs * .50, cs * .22), (cs * .40, cs * .03)],
                            fill=255, width=int(cs * .06))
    pod.paste(Image.new("RGBA", (cs, cs), LEAF + (255,)), (0, 0), st)
    img.alpha_composite(pod, ((s - cs) // 2, (s - cs) // 2))
    return img.resize((512, 512), Image.LANCZOS)


# --------------------------------------------------------------------------- #
# sheets
# --------------------------------------------------------------------------- #

def build_sheet(images, cols, rows, cw, ch, path):
    sheet = Image.new("RGB", (cols * cw, rows * ch), (12, 10, 10))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % cols) * cw, (i // cols) * ch))
    sheet.save(path, "PNG", optimize=True)
    return path


def generate(missions, progress=True):
    os.makedirs(ASSETS, exist_ok=True)
    out = {}

    def say(msg):
        if progress:
            print("  " + msg, flush=True)

    say("55 numbered cards + Joker")
    play = [number_card(v) for v in range(1, 56)] + [joker_card()]
    out["play_face"] = build_sheet(play, 8, 7, CARD_W, CARD_H,
                                   os.path.join(ASSETS, "play_faces.png"))

    say(f"{len(missions)} mission cards")
    miss = [mission_card(m["title"], m["text"], m["cards"], m.get("expert", False))
            for m in missions]
    out["mission_face"] = build_sheet(miss, 6, 6, CARD_W, CARD_H,
                                      os.path.join(ASSETS, "mission_faces.png"))

    say("in-world controls")
    # Square canvases throughout, deliberately: TTS's Custom_Tile Rectangle
    # type does not infer scaleX/scaleZ from the image, and a real check
    # against 28 workshop mods found no correlation between a tile's scale
    # ratio and its source image's aspect ratio either - so there is no
    # evidence for what mapping (if any) TTS applies to a non-square canvas,
    # and two different guesses at it both still came back visibly squashed
    # in play. Square avoids the question entirely, which is what ~95% of
    # real Custom_Tiles do (635 of 666 checked).
    # No baked title: the runtime number row and big-pick display already say
    # what this tile is for, and a static "BID" fighting them for the same
    # central space read as garbled, half-covered text in play.
    p = os.path.join(ASSETS, "dibber.png")
    plaque(600, 600, None).save(p, "PNG", optimize=True)
    out["dibber"] = p

    p = os.path.join(ASSETS, "round_button.png")
    plaque(700, 700, "NEXT ROUND", ground=(28, 14, 12), accent=CHILI_RED,
           chilli=True, title_frac=0.15).save(p, "PNG", optimize=True)
    out["button"] = p

    p = os.path.join(ASSETS, "dealer.png")
    dealer_token().save(p, "PNG", optimize=True)
    out["dealer"] = p

    p = os.path.join(ASSETS, "mission_toggle.png")
    # Title pushed up near the top edge (title_y) rather than centred, so the
    # ON/OFF toggle button - which needs the centre - stops sitting directly
    # on top of it. Centred was what made "MISSIONS" unreadable in play.
    plaque(500, 500, "MISSIONS", ground=(26, 24, 20), accent=(232, 196, 92),
           title_frac=0.13, title_y=0.20).save(p, "PNG", optimize=True)
    out["mtoggle"] = p

    # mats are backdrops, so they stay quiet: dark, thin border, small type
    p = os.path.join(ASSETS, "mat_tricks.png")
    plaque(700, 700, "TRICKS WON", ground=(24, 23, 22), accent=(74, 70, 66),
           title_frac=0.075).save(p, "PNG", optimize=True)
    out["mat"] = p

    p = os.path.join(ASSETS, "mat_pilis.png")
    plaque(500, 500, "PILIS", ground=(30, 20, 19), accent=(96, 44, 40),
           title_frac=0.13).save(p, "PNG", optimize=True)
    out["tray"] = p

    say("backs and token")
    p = os.path.join(ASSETS, "play_back.png")
    back(CARD_W, CARD_H, "PILI PILI", (232, 196, 92), "1 - 55").save(p, "PNG", optimize=True)
    out["play_back"] = p

    p = os.path.join(ASSETS, "mission_back.png")
    back(CARD_W, CARD_H, "MISSION", (120, 190, 230)).save(p, "PNG", optimize=True)
    out["mission_back"] = p

    p = os.path.join(ASSETS, "pili_token.png")
    pili_token().save(p, "PNG", optimize=True)
    out["pili"] = p

    return out


if __name__ == "__main__":
    with open(os.path.join(HERE, "missions.json"), encoding="utf-8") as fh:
        ms = json.load(fh)["missions"]
    for k, v in generate(ms).items():
        print(f"{k:14s} {v}")
