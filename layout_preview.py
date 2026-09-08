"""Top-down map of a built save, so the table can be checked without TTS.

    python layout_preview.py <PiliPili.json> [out.png]

Draws the poker table's felt, every seat, and each object at its real position
and footprint. Overlaps and things hanging off the felt are obvious here and
almost impossible to judge from a list of coordinates.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# Table_Poker's felt, from the extent of the objects in "The Gang" mods
FELT_X, FELT_Z = 38.0, 19.0
PX = 18                      # pixels per TTS unit
MARGIN = 30

FONT = r"C:\Windows\Fonts\arialbd.ttf"

STYLE = {
    "HandTrigger":      ((90, 150, 220), "seat"),
    "ScriptingTrigger": ((230, 170, 60), "zone"),
    "Custom_Tile":      ((235, 235, 235), "tile"),
    "DeckCustom":       ((220, 90, 80), "deck"),
    "Custom_Token":     ((150, 220, 150), "token"),
    "Infinite_Bag":     ((190, 140, 220), "bag"),
}


def main(save_path, out_path):
    save = json.load(open(save_path, encoding="utf-8"))
    w = int(FELT_X * 2 * PX) + MARGIN * 2
    h = int(FELT_Z * 2 * PX) + MARGIN * 2
    img = Image.new("RGB", (w, h), (26, 30, 26))
    d = ImageDraw.Draw(img, "RGBA")
    small = ImageFont.truetype(FONT, 11)
    tiny = ImageFont.truetype(FONT, 9)

    def to_px(x, z):
        return (MARGIN + (x + FELT_X) * PX, MARGIN + (z + FELT_Z) * PX)

    d.rounded_rectangle([to_px(-FELT_X, -FELT_Z), to_px(FELT_X, FELT_Z)],
                        FELT_Z * PX, fill=(38, 92, 46), outline=(70, 130, 76), width=2)
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
        x, z = t["posX"], t["posZ"]
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

        p0, p1 = to_px(x - ex, z - ez), to_px(x + ex, z + ez)
        if kind == "seat":
            d.rectangle([p0, p1], outline=colour + (170,), width=2)
            hand_zones.append((x - ex, z - ez, x + ex, z + ez,
                               o.get("FogColor", "?") + " hand"))
        elif kind == "zone":
            d.rectangle([p0, p1], outline=colour + (200,), width=1)
        else:
            d.rectangle([p0, p1], fill=colour + (200,), outline=(20, 20, 20), width=1)
            footprints.append((x - ex, z - ez, x + ex, z + ez,
                               o.get("Nickname") or name))

        label = o.get("FogColor") or o.get("Nickname") or ""
        if label:
            d.text(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), label[:14],
                   font=tiny, fill=(15, 15, 15) if kind not in ("seat", "zone")
                   else colour, anchor="mm")

    # flag overlaps between solid objects and anything off the felt
    problems = []
    for i in range(len(footprints)):
        ax0, az0, ax1, az1, an = footprints[i]
        if (abs(ax0) > FELT_X or abs(ax1) > FELT_X
                or abs(az0) > FELT_Z or abs(az1) > FELT_Z):
            problems.append(f"off the felt: {an}")
        for j in range(i + 1, len(footprints)):
            bx0, bz0, bx1, bz1, bn = footprints[j]
            if ax0 < bx1 and bx0 < ax1 and az0 < bz1 and bz0 < az1:
                problems.append(f"overlap: {an}  x  {bn}")
        for hx0, hz0, hx1, hz1, hn in hand_zones:
            if ax0 < hx1 and hx0 < ax1 and az0 < hz1 and hz0 < az1:
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
