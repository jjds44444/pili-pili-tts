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

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import glyphs

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
    (11, (46, 108, 199)),      # 1-11   blue
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
                                        colour=shade(base, 0.82),
                                        count=30, glyph_px=int(w * 0.155)))

    big = font(FONT_BLACK, int(h * (0.42 if value < 10 else 0.34)))
    inked_text(card, (w // 2, int(h * 0.50)), str(value), big,
               key_width=max(4, int(w * 0.014)), marks_seed=value * 977,
               rough=w * 0.004)

    small = font(FONT_BLACK, int(h * 0.085))
    pad_x, pad_y = int(w * 0.085), int(h * 0.062)
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
    card.alpha_composite(glyphs.scatter((w, h), seed=abs(hash(title)) % 9991,
                                        colour=(235, 231, 223), count=26,
                                        glyph_px=int(w * 0.15)))

    accent = CHILI_RED if expert else (34, 32, 32)
    d = ImageDraw.Draw(card)

    d.text((w // 2, int(h * 0.055)), "EXPERT MISSION" if expert else "MISSION",
           font=font(FONT_BOLD, int(h * 0.035)), fill=accent, anchor="mm")

    # pictogram: solid ink so it reads on the pale card
    s = int(w * 0.38)
    pic = glyphs.glyph(s, seed=abs(hash(title)) % 99991, colour=INK, ink=PAPER,
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


def bid_card(n):
    w, h = BID_W * SS, BID_H * SS
    card = Image.new("RGBA", (w, h), (32, 30, 38, 255))
    card.alpha_composite(glyphs.scatter((w, h), seed=500 + n, colour=(56, 52, 64),
                                        count=20, glyph_px=int(w * 0.18)))
    d = ImageDraw.Draw(card)
    d.text((w // 2, int(h * 0.13)), "I BID", font=font(FONT_BOLD, int(h * 0.085)),
           fill=(232, 196, 92), anchor="mm")
    inked_text(card, (w // 2, int(h * 0.53)), str(n), font(FONT_BLACK, int(h * 0.42)),
               key_width=max(3, int(w * 0.014)), rough=w * 0.004)
    d = ImageDraw.Draw(card)
    d.text((w // 2, int(h * 0.90)), "TRICKS" if n != 1 else "TRICK",
           font=font(FONT_BOLD, int(h * 0.06)), fill=(170, 162, 182), anchor="mm")
    return card.resize((BID_W, BID_H), Image.LANCZOS).convert("RGB")


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

    say("bet markers")
    bids = [bid_card(n) for n in range(0, 14)]
    out["bid_face"] = build_sheet(bids, 7, 2, BID_W, BID_H,
                                  os.path.join(ASSETS, "bid_faces.png"))

    say("backs and token")
    p = os.path.join(ASSETS, "play_back.png")
    back(CARD_W, CARD_H, "PILI PILI", (232, 196, 92), "1 - 55").save(p, "PNG", optimize=True)
    out["play_back"] = p

    p = os.path.join(ASSETS, "mission_back.png")
    back(CARD_W, CARD_H, "MISSION", (120, 190, 230)).save(p, "PNG", optimize=True)
    out["mission_back"] = p

    p = os.path.join(ASSETS, "bid_back.png")
    back(BID_W, BID_H, "BID", (200, 170, 240)).save(p, "PNG", optimize=True)
    out["bid_back"] = p

    p = os.path.join(ASSETS, "pili_token.png")
    pili_token().save(p, "PNG", optimize=True)
    out["pili"] = p

    return out


if __name__ == "__main__":
    with open(os.path.join(HERE, "missions.json"), encoding="utf-8") as fh:
        ms = json.load(fh)["missions"]
    for k, v in generate(ms).items():
        print(f"{k:14s} {v}")
