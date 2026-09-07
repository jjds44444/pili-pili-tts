"""Original card art for the Pili Pili TTS mod.

Everything here is drawn from scratch with Pillow - no publisher assets are used.
Produces the deck sheets TTS expects (one grid image per deck) plus backs and a
chili token.
"""
import colorsys
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

FONT_DIR = r"C:\Windows\Fonts"
FONT_BLACK = os.path.join(FONT_DIR, "seguibl.ttf")   # Segoe UI Black
FONT_BOLD = os.path.join(FONT_DIR, "arialbd.ttf")
FONT_REG = os.path.join(FONT_DIR, "arial.ttf")

CARD_W, CARD_H = 400, 560
BID_W, BID_H = 300, 420

CREAM = (247, 240, 228)
INK = (28, 22, 20)
DEEP = (26, 18, 16)
CHILI_RED = (198, 34, 30)
CHILI_DARK = (140, 20, 20)
LEAF = (76, 140, 58)


def font(path, size):
    return ImageFont.truetype(path, size)


def heat_colors(t):
    """t in 0..1 -> (light, dark) background pair going blue -> green -> red."""
    hue = 0.62 * (1.0 - t) ** 1.15
    sat = 0.62 + 0.33 * t
    light = colorsys.hsv_to_rgb(hue, sat * 0.88, 0.93)
    dark = colorsys.hsv_to_rgb(hue, min(1.0, sat * 1.05), 0.55)
    to255 = lambda c: tuple(int(round(x * 255)) for x in c)
    return to255(light), to255(dark)


def vertical_gradient(size, top, bottom):
    w, h = size
    grad = Image.new("RGB", (1, h))
    px = grad.load()
    for y in range(h):
        f = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3))
    return grad.resize((w, h), Image.BILINEAR)


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, fill=255)
    return m


def draw_chili(img, cx, cy, size, body=CHILI_RED, shine=True, rot=-18, underside=True):
    """A tapered curved pod with a stem, drawn on its own layer then rotated."""
    pad = int(size * 1.5)
    layer = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ox, oy = pad // 2, pad // 2

    curve = 0.26
    thick = 0.30
    steps = 120

    def spine(t):
        return (ox + size * curve * math.sin(t * 2.0),
                oy - size * 0.44 + size * 0.94 * t,
                size * thick * (1.0 - t) ** 0.55)

    for i in range(steps + 1):
        x, y, r = spine(i / steps)
        if r < 0.6:
            continue
        d.ellipse([x - r, y - r, x + r, y + r], fill=body + (255,))

    if underside:
        dark = tuple(max(0, int(c * 0.7)) for c in body)
        for i in range(steps + 1):
            x, y, r = spine(i / steps)
            r *= 0.5
            if r < 0.6:
                continue
            x += size * 0.075
            y += size * 0.05
            d.ellipse([x - r, y - r, x + r, y + r], fill=dark + (150,))

    if shine:
        for i in range(steps + 1):
            t = i / steps
            if t > 0.70:
                continue
            x, y, r = spine(t)
            x -= size * 0.10
            y -= size * 0.03
            r = size * 0.062 * (1.0 - t) ** 0.5
            if r < 0.6:
                continue
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 130))

    # stem
    sx, sy = ox, oy - size * 0.44
    d.line([(sx, sy + size * 0.06), (sx - size * 0.15, sy - size * 0.30)],
           fill=LEAF + (255,), width=max(3, int(size * 0.085)))
    d.ellipse([sx - size * 0.13, sy - size * 0.085, sx + size * 0.13, sy + size * 0.085],
              fill=LEAF + (255,))

    layer = layer.rotate(rot, resample=Image.BICUBIC, center=(ox, oy))
    img.paste(layer, (int(cx - ox), int(cy - oy)), layer)


def text_outlined(d, xy, text, fnt, fill, outline, width=5, anchor="mm"):
    x, y = xy
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy > width * width:
                continue
            d.text((x + dx, y + dy), text, font=fnt, fill=outline, anchor=anchor)
    d.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


# --------------------------------------------------------------------------- #
# card faces
# --------------------------------------------------------------------------- #

def number_card(value):
    t = (value - 1) / 54.0
    light, dark = heat_colors(t)
    card = vertical_gradient((CARD_W, CARD_H), light, dark).convert("RGBA")
    d = ImageDraw.Draw(card)

    # inner frame
    d.rounded_rectangle([14, 14, CARD_W - 15, CARD_H - 15], 22,
                        outline=(255, 255, 255, 90), width=3)

    big = font(FONT_BLACK, 250 if value < 10 else 200)
    text_outlined(d, (CARD_W // 2, CARD_H // 2 - 18), str(value), big,
                  (255, 255, 255), (0, 0, 0), width=7)

    small = font(FONT_BLACK, 50)
    text_outlined(d, (50, 54), str(value), small, (255, 255, 255), (0, 0, 0), width=3)
    corner = Image.new("RGBA", (140, 100), (0, 0, 0, 0))
    cd = ImageDraw.Draw(corner)
    text_outlined(cd, (70, 50), str(value), small, (255, 255, 255), (0, 0, 0), width=3)
    corner = corner.rotate(180)
    card.paste(corner, (CARD_W - 140 - 8, CARD_H - 100 - 8), corner)

    # heat pips (Scoville-ish read of the card's strength)
    pips = max(1, min(5, math.ceil(value / 11)))
    step = 40
    start = CARD_W // 2 - (pips - 1) * step // 2
    for i in range(pips):
        draw_chili(card, start + i * step, CARD_H - 96, 42,
                   body=(255, 255, 255), shine=False, underside=False)

    return card.convert("RGB")


def joker_card():
    card = vertical_gradient((CARD_W, CARD_H), (58, 44, 40), (18, 12, 12)).convert("RGBA")
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([14, 14, CARD_W - 15, CARD_H - 15], 22,
                        outline=(232, 196, 92), width=4)
    draw_chili(card, CARD_W // 2, CARD_H // 2 - 40, 250, body=(226, 62, 46))
    d = ImageDraw.Draw(card)
    d.text((CARD_W // 2, CARD_H - 128), "JOKER", font=font(FONT_BLACK, 62),
           fill=(232, 196, 92), anchor="mm")
    d.text((CARD_W // 2, CARD_H - 74), "declare any value 0-56", font=font(FONT_REG, 26),
           fill=(226, 214, 200), anchor="mm")
    return card.convert("RGB")


def mission_card(title, body, cards, expert=False):
    header = (150, 26, 22) if not expert else (30, 30, 34)
    card = Image.new("RGBA", (CARD_W, CARD_H), CREAM + (255,))
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, CARD_W, 150], fill=header)
    d.rectangle([0, 150, CARD_W, 158], fill=(232, 196, 92))

    d.text((CARD_W // 2, 40), "EXPERT MISSION" if expert else "MISSION",
           font=font(FONT_BOLD, 26), fill=(240, 200, 190), anchor="mm")

    size = 52
    fnt = font(FONT_BLACK, size)
    while d.textlength(title.upper(), font=fnt) > CARD_W - 48 and size > 26:
        size -= 2
        fnt = font(FONT_BLACK, size)
    d.text((CARD_W // 2, 100), title.upper(), font=fnt, fill=CREAM, anchor="mm")

    lines = body.split("\n")
    bs = 32
    bf = font(FONT_REG, bs)
    while max(d.textlength(l, font=bf) for l in lines) > CARD_W - 56 and bs > 17:
        bs -= 1
        bf = font(FONT_REG, bs)
    y = 285 - (len(lines) - 1) * (bs + 11) // 2
    for line in lines:
        d.text((CARD_W // 2, y), line, font=bf, fill=INK, anchor="mm")
        y += bs + 11

    # deal count, bottom-left as on the printed cards
    d.ellipse([26, CARD_H - 122, 138, CARD_H - 10], fill=CHILI_RED)
    d.text((82, CARD_H - 68), str(cards), font=font(FONT_BLACK, 68),
           fill=CREAM, anchor="mm")
    d.text((82, CARD_H - 134), "CARDS EACH", font=font(FONT_BOLD, 20),
           fill=(120, 106, 96), anchor="mm")

    draw_chili(card, CARD_W - 74, CARD_H - 72, 96)

    if expert:
        # red card symbol in the header marks an Expert mission
        d.rounded_rectangle([CARD_W - 66, 14, CARD_W - 18, 78], 7,
                            fill=CHILI_RED, outline=(240, 200, 190), width=2)
        d.text((CARD_W - 42, 46), "!", font=font(FONT_BLACK, 38), fill=CREAM, anchor="mm")
        d.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=CHILI_RED, width=8)

    return card.convert("RGB")


def bid_card(n):
    card = vertical_gradient((BID_W, BID_H), (54, 50, 66), (22, 20, 30)).convert("RGBA")
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([10, 10, BID_W - 11, BID_H - 11], 18,
                        outline=(232, 196, 92), width=3)
    d.text((BID_W // 2, 60), "I BID", font=font(FONT_BOLD, 34),
           fill=(232, 196, 92), anchor="mm")
    text_outlined(d, (BID_W // 2, BID_H // 2 + 20), str(n), font(FONT_BLACK, 190),
                  (255, 255, 255), (0, 0, 0), width=5)
    d.text((BID_W // 2, BID_H - 40), "TRICKS" if n != 1 else "TRICK",
           font=font(FONT_BOLD, 26), fill=(180, 172, 190), anchor="mm")
    return card.convert("RGB")


def back(w, h, label, tint=(140, 22, 20), sub=None):
    card = vertical_gradient((w, h), tuple(min(255, int(c * 1.5)) for c in tint),
                             tuple(int(c * 0.55) for c in tint)).convert("RGBA")
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([int(w * 0.035), int(h * 0.025), w - int(w * 0.035), h - int(h * 0.025)],
                        int(w * 0.05), outline=(232, 196, 92), width=max(3, w // 110))
    draw_chili(card, w // 2, int(h * 0.44), int(h * 0.42), body=(240, 226, 206))
    d = ImageDraw.Draw(card)
    d.text((w // 2, int(h * 0.80)), label, font=font(FONT_BLACK, int(h * 0.085)),
           fill=(240, 226, 206), anchor="mm")
    if sub:
        d.text((w // 2, int(h * 0.885)), sub, font=font(FONT_BOLD, int(h * 0.042)),
               fill=(232, 196, 92), anchor="mm")
    return card.convert("RGB")


def pili_token():
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, size - 8, size - 8], fill=(250, 244, 232, 255),
              outline=(140, 20, 20, 255), width=14)
    draw_chili(img, size // 2, size // 2, int(size * 0.62))
    return img


# --------------------------------------------------------------------------- #
# sheets
# --------------------------------------------------------------------------- #

def build_sheet(images, cols, rows, cw, ch, path):
    sheet = Image.new("RGB", (cols * cw, rows * ch), (12, 10, 10))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % cols) * cw, (i // cols) * ch))
    sheet.save(path, "PNG", optimize=True)
    return path


def generate(missions):
    os.makedirs(ASSETS, exist_ok=True)
    out = {}

    play = [number_card(v) for v in range(1, 56)] + [joker_card()]
    out["play_face"] = build_sheet(play, 8, 7, CARD_W, CARD_H,
                                   os.path.join(ASSETS, "play_faces.png"))

    miss = [mission_card(m["title"], m["text"], m["cards"], m.get("expert", False))
            for m in missions]
    out["mission_face"] = build_sheet(miss, 6, 6, CARD_W, CARD_H,
                                      os.path.join(ASSETS, "mission_faces.png"))

    bids = [bid_card(n) for n in range(0, 14)]
    out["bid_face"] = build_sheet(bids, 7, 2, BID_W, BID_H,
                                  os.path.join(ASSETS, "bid_faces.png"))

    p = os.path.join(ASSETS, "play_back.png")
    back(CARD_W, CARD_H, "PILI PILI", (150, 26, 22), "1 - 55").save(p, "PNG", optimize=True)
    out["play_back"] = p

    p = os.path.join(ASSETS, "mission_back.png")
    back(CARD_W, CARD_H, "MISSION", (40, 60, 120)).save(p, "PNG", optimize=True)
    out["mission_back"] = p

    p = os.path.join(ASSETS, "bid_back.png")
    back(BID_W, BID_H, "BID", (56, 46, 88)).save(p, "PNG", optimize=True)
    out["bid_back"] = p

    p = os.path.join(ASSETS, "pili_token.png")
    pili_token().save(p, "PNG", optimize=True)
    out["pili"] = p

    return out


if __name__ == "__main__":
    import json
    with open(os.path.join(HERE, "missions.json"), encoding="utf-8") as fh:
        ms = json.load(fh)["missions"]
    for k, v in generate(ms).items():
        print(f"{k:14s} {v}")
