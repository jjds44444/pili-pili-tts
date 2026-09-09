"""Top-down map of a built save, so the table can be checked without TTS.

    python layout_preview.py <PiliPili.json> [out.png]

Draws the table's felt, every seat, and each object at its real position and
footprint. Overlaps and things hanging off the felt are obvious here and
almost impossible to judge from a list of coordinates.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# Table_Circular's felt: a plain circle (see FELT_R in build_save.py - must
# match, or this stops being a meaningful check on it). Weaker evidence than
# the rectangle's own FELT_X/FELT_Z had (see the CAVEAT on FELT_R there) -
# this is inferred from where real hand zones sit, not independently
# measured, so treat "on felt" here as provisional too.
FELT_R = 21.51


def on_felt(x, z):
    return math.hypot(x, z) <= FELT_R
PX = 18                      # pixels per TTS unit
MARGIN = 30

FONT = r"C:\Windows\Fonts\arialbd.ttf"

STYLE = {
    "HandTrigger":      ((90, 150, 220), "seat"),
    "ScriptingTrigger": ((230, 170, 60), "zone"),
    "Custom_Tile":      ((235, 235, 235), "tile"),
    "DeckCustom":       ((220, 90, 80), "deck"),
    "Custom_Token":     ((150, 220, 150), "token"),
    "Custom_PDF":       ((210, 190, 150), "token"),
    "Infinite_Bag":     ((190, 140, 220), "bag"),
}


def corners(x, z, ex, ez, rot_y):
    """The 4 world-space corners of a footprint centred at (x, z), half-size
    (ex, ez), rotated rot_y degrees about Y. Seats here sit at arbitrary
    angles (0/60/120/...), not just 0/180 the way the rectangle table's did
    - an axis-aligned box would be wrong for a rotated footprint, so this
    (and the SAT overlap check below) replaced the old simpler axis-aligned
    version once rotation stopped being just "flipped or not"."""
    r = math.radians(rot_y)
    cos_r, sin_r = math.cos(r), math.sin(r)
    pts = []
    for lx, lz in ((-ex, -ez), (ex, -ez), (ex, ez), (-ex, ez)):
        pts.append((x + lx * cos_r + lz * sin_r, z - lx * sin_r + lz * cos_r))
    return pts


def _axes(poly):
    axes = []
    for i in range(len(poly)):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % len(poly)]
        ex, ez = x2 - x1, z2 - z1
        axes.append((-ez, ex))
    return axes


def polys_overlap(a, b):
    """Separating Axis Theorem for two convex polygons (here, always
    quadrilaterals) - the general case a same-angle axis-aligned box check
    can't handle once footprints can sit at any rotation."""
    for ax, az in _axes(a) + _axes(b):
        proj_a = [px * ax + pz * az for px, pz in a]
        proj_b = [px * ax + pz * az for px, pz in b]
        if max(proj_a) < min(proj_b) or max(proj_b) < min(proj_a):
            return False
    return True


def main(save_path, out_path):
    save = json.load(open(save_path, encoding="utf-8"))
    w = int(FELT_R * 2 * PX) + MARGIN * 2
    h = int(FELT_R * 2 * PX) + MARGIN * 2
    img = Image.new("RGB", (w, h), (26, 30, 26))
    d = ImageDraw.Draw(img, "RGBA")
    small = ImageFont.truetype(FONT, 11)
    tiny = ImageFont.truetype(FONT, 9)

    def to_px(x, z):
        return (MARGIN + (x + FELT_R) * PX, MARGIN + (z + FELT_R) * PX)

    d.ellipse([to_px(-FELT_R, -FELT_R), to_px(FELT_R, FELT_R)],
             fill=(38, 92, 46), outline=(70, 130, 76), width=2)
    cx, cz = to_px(0, 0)
    d.line([(cx, MARGIN), (cx, h - MARGIN)], fill=(255, 255, 255, 26))
    d.line([(MARGIN, cz), (w - MARGIN, cz)], fill=(255, 255, 255, 26))

    footprints = []
    hand_zones = []  # checked separately below: overlapping a hand zone is
                      # not a visual clash like two tiles overlapping, it is a
                      # correctness bug - anything dropped there (a dealt
                      # card, a paid-out Pili) can get swept into that
                      # player's private hand instead of staying on the table.
                      # This exact bug shipped once already because nothing
                      # checked it.
    for o in save["ObjectStates"]:
        name = o["Name"]
        if name not in STYLE:
            continue
        colour, kind = STYLE[name]
        t = o["Transform"]
        x, z, rot_y = t["posX"], t["posZ"], t.get("rotY", 0.0)
        sx, sz = t.get("scaleX", 1.0), t.get("scaleZ", 1.0)

        if kind == "seat":
            ex, ez = sx * 0.5, sz * 0.5
        elif kind == "zone":
            ex, ez = sx * 0.5, sz * 0.5
        elif kind == "tile":
            ex, ez = sx * 1.15, sz * 1.15      # tile art is roughly 2.3 units
        elif kind == "deck":
            ex, ez = 1.2, 1.7
        else:
            ex, ez = sx * 0.9, sz * 0.9

        poly = corners(x, z, ex, ez, rot_y)
        px = [to_px(cx_, cz_) for cx_, cz_ in poly]
        if kind == "seat":
            d.polygon(px, outline=colour + (170,), width=2)
            hand_zones.append((poly, o.get("FogColor", "?") + " hand"))
        elif kind == "zone":
            d.polygon(px, outline=colour + (200,), width=1)
        else:
            d.polygon(px, fill=colour + (200,), outline=(20, 20, 20), width=1)
            footprints.append((poly, o.get("Nickname") or name))

        label = o.get("FogColor") or o.get("Nickname") or ""
        if label:
            mx = sum(p[0] for p in px) / 4
            mz = sum(p[1] for p in px) / 4
            d.text((mx, mz), label[:14], font=tiny,
                   fill=(15, 15, 15) if kind not in ("seat", "zone") else colour,
                   anchor="mm")

    # flag overlaps between solid objects and anything off the felt
    problems = []
    for i in range(len(footprints)):
        a_poly, an = footprints[i]
        if not all(on_felt(cx_, cz_) for cx_, cz_ in a_poly):
            problems.append(f"off the felt: {an}")
        for j in range(i + 1, len(footprints)):
            b_poly, bn = footprints[j]
            if polys_overlap(a_poly, b_poly):
                problems.append(f"overlap: {an}  x  {bn}")
        for h_poly, hn in hand_zones:
            if polys_overlap(a_poly, h_poly):
                problems.append(f"IN A HAND ZONE: {an}  x  {hn}")

    d.text((MARGIN, 8), os.path.basename(save_path)
           + f"   {len(save['ObjectStates'])} objects", font=small,
           fill=(200, 200, 200))
    img.save(out_path)
    print(out_path)
    if problems:
        print(f"\n{len(problems)} layout problem(s):")
        for p in sorted(set(problems)):
            print("  " + p)
    else:
        print("no overlaps, nothing off the felt")
    return 1 if problems else 0


if __name__ == "__main__":
    out = sys.argv[2] if len(sys.argv) > 2 else "layout.png"
    sys.exit(main(sys.argv[1], out))
