"""Build the Pili Pili Tabletop Simulator save file.

    python build_save.py              # render art + install into your TTS Saves folder
    python build_save.py --skip-art   # reuse assets/, rebuild the save only
    python build_save.py --local      # host-only file:/// images, for fast art iteration
    python build_save.py --out DIR    # write somewhere else

Images are served from the repo by default, so everyone at the table sees them.
"""
import argparse
import json
import math
import os
import random
import hashlib
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Assets are served straight out of this repo, so a plain build produces a save
# everyone at the table can see. Anything committed to assets/ on main is live
# at this prefix within seconds of pushing. Use --local for file:/// paths
# (host-only, but instant - handy while iterating on the art).
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/jjds44444/pili-pili-tts/main/assets"

import art  # noqa: E402  (lives next to this script)


# Seats on Table_Poker, in world units, lifted verbatim from the workshop mod
# "The Gang [Scripted]" (3385562324) - a working 6-player game on this exact
# table. They run along the +z long side and wrap slightly round the two
# corners; the entire -z half (the dealer's cut-out) is free for the play area,
# and with only 6 seats there is no crowding near the corners either.
# 4th field: rotY for this seat's DISPLAY tiles (dibber/mat/tray/dealer) - not
# the HandTrigger itself, which stays at the reference mod's 180 for every seat
# regardless (that governs how a dealt hand fans out, not what a human reads).
# The middle four sit on a near-straight run of the table edge and share one
# facing; Red and Purple wrap around the corner and were inheriting that same
# 180 despite sitting at a visibly different angle - computed by facing each
# toward the true centre of the felt instead.
SEATS = [
    ("Red",    -34.07,  7.91, 286.2),
    ("Orange", -21.77, 14.48, 180.0),
    ("White",   -6.85, 14.42, 180.0),
    ("Green",    6.83, 14.45, 180.0),
    ("Blue",    21.04, 14.32, 180.0),
    ("Purple",  34.07,  7.91,  73.8),
]

# The real centre of the play area, where the snap-point ring for played
# cards sits.
PLAY_CENTRE = (0.0, -6.0)

# A far-away point used ONLY to pick each seat's "inward" direction. Using the
# real PLAY_CENTRE for this made every seat's controls point at one nearby
# spot, so objects from different seats converged and crowded each other near
# the middle the further out they sat. A distant reference point makes inward
# directions nearly parallel across seats instead, which is what actually
# gives every seat's own cluster of objects its own lane.
DIR_CENTRE = (0.0, -500.0)

# The dibber/tray used to sit inside the seat's own HandTrigger footprint
# (9.6 x 5.6, from the reference mod - see hand_zone()) - anything dropped
# there, including Pilis paid out by the script, could get swept into that
# player's private hand instead of staying on the table. These values were
# found by search, over the REAL stadium-shaped felt (not a rectangle - see
# felt_clamp below) and the tiles' real (now square, see custom_tile) sizes,
# for the smallest OUT_MAT/OUT_CTRL under which every tile still clears every
# hand zone, the true felt edge, and every other tile with a small margin.
# The mat sits this far out because the hand zone it must clear is a genuinely
# large, real 9.6 x 5.6 box - shrinking HAND_W/HAND_D below the reference
# mod's real value would let it sit closer, at the cost of a smaller, less
# reliable card-catching area.
# Re-searched with a thinner (but still real, 0.5-unit) required margin
# instead of maximum comfort - the previous pass optimised for headroom and
# ended up reading as "too far from the seat" in play, even though nothing
# was actually wrong with it.
OUT_MAT = 8.25        # trick mat, in front of the seat
OUT_CTRL = 4.5         # dibber and Pili tray, between the seat and the mat
SIDE_CTRL = 1.75       # and apart from each other

# Reported bug: the play deck kept drifting toward the table edge and falling
# off. z=-15/-16.5 sat deep in the dealer's cut-out, which real poker tables
# leave unrailed on at least one side - there is nothing there to stop a
# nudged deck sliding off the felt entirely. Trick mats reach no further than
# z=-4.1 at their worst (Red/Purple, see the search above), so there is 10+
# units of untouched, presumably-railed felt available; the shared piles now
# sit at z=-9/-11, well clear of both the mats and the exposed cut-out edge.
# lockAtRest() in global.lua is the second half of this fix.
POS_PLAY = (-16.0, 1.6, -9.0)
POS_ASIDE = (-25.0, 1.6, -9.0)
POS_MISSION = (16.0, 1.6, -9.0)
POS_DISCARD = (25.0, 1.6, -9.0)
POS_REVEAL = (0.0, 1.6, -9.0)
POS_BUTTON = (0.0, 1.3, -12.5)
POS_PILIS = (0.0, 1.6, -5.0)
# Was (16, -12.5): visibly clipped into the table/rail in play. POS_BUTTON
# sits at the same z=-12.5 but x=0 and is fine, which points at the rail
# curving inward more at higher |x| (consistent with the corner-cap
# inaccuracy noted above) rather than z=-12.5 itself being the problem.
# Moved to lower |x|, comfortably inside the straight-side, no-guesswork
# region rather than re-testing the same edge a second time.
POS_MTOGGLE = (9.0, 1.3, -9.0)

_used_guids = set()


def guid():
    while True:
        g = "%06x" % random.randrange(16 ** 6)
        if g not in _used_guids:
            _used_guids.add(g)
            return g


def transform(pos, rot=(0, 180, 0), scale=1.0):
    return {
        "posX": pos[0], "posY": pos[1], "posZ": pos[2],
        "rotX": rot[0], "rotY": rot[1], "rotZ": rot[2],
        "scaleX": scale, "scaleY": scale, "scaleZ": scale,
    }


BASE_FLAGS = {
    "ColorDiffuse": {"r": 1.0, "g": 1.0, "b": 1.0},
    "Locked": False, "Grid": True, "Snap": True, "IgnoreFoW": False,
    "MeasureMovement": False, "DragSelectable": True, "Autoraise": True,
    "Sticky": True, "Tooltip": True, "GridProjection": False,
    "HideWhenFaceDown": True, "Hands": True,
}


def custom_deck(face, back, w, h):
    return {
        "FaceURL": face, "BackURL": back,
        "NumWidth": w, "NumHeight": h,
        "BackIsHidden": True, "UniqueBack": False, "Type": 0,
    }


def card(deck_id, index, nickname, description, gm_notes, cd, pos, rot):
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "CardCustom",
        "Transform": transform(pos, rot),
        "Nickname": nickname, "Description": description, "GMNotes": gm_notes,
        "CardID": deck_id * 100 + index,
        "SidewaysCard": False,
        "CustomDeck": {str(deck_id): cd},
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def deck(deck_id, cards, nickname, gm_notes, cd, pos, rot=(0, 180, 180)):
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "DeckCustom",
        "Transform": transform(pos, rot),
        "Nickname": nickname, "Description": "", "GMNotes": gm_notes,
        "SidewaysCard": False,
        "DeckIDs": [c["CardID"] for c in cards],
        "CustomDeck": {str(deck_id): cd},
        "ContainedObjects": cards,
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def seat_frame(x, z):
    """A seat's inward direction (see DIR_CENTRE above) and its tangent."""
    dx, dz = DIR_CENTRE[0] - x, DIR_CENTRE[1] - z
    n = math.hypot(dx, dz) or 1.0
    inward = (dx / n, dz / n)
    tangent = (-inward[1], inward[0])
    return inward, tangent


# Table_Poker's felt, estimated from real objects in "The Gang" workshop mods
# (see layout_preview.py). It is a STADIUM shape - straight sides, semicircular
# ends - not a rectangle: Red and Purple sit in the curved end-caps (|x| well
# past FELT_X - FELT_Z). Clamping to a rectangular bounding box, which an
# earlier version of this file did, allows points in that box's CORNERS that
# are outside the real oval table entirely - confirmed by their trick mats
# visibly clipping off the felt in play. FELT_MARGIN is how far inside the
# true edge every clamped point must stay.
FELT_X, FELT_Z, FELT_MARGIN = 38.0, 19.0, 2.0


def felt_clamp(x, z, margin=FELT_MARGIN):
    """Pull (x, z) back onto the stadium-shaped felt, `margin` inside its edge."""
    straight = FELT_X - FELT_Z          # |x| below this: bounded by a flat side
    lim_z = FELT_Z - margin
    if abs(x) <= straight:
        return x, max(-lim_z, min(lim_z, z))
    # in one of the rounded end-caps: clamp radially around its centre
    cx = math.copysign(straight, x)
    dx, dz = x - cx, z
    r = math.hypot(dx, dz)
    lim_r = FELT_Z - margin
    if r <= lim_r or r == 0:
        return x, z
    return cx + dx / r * lim_r, dz / r * lim_r


def seat_spot(x, z, out, side=0.0):
    inward, tangent = seat_frame(x, z)
    px = x + inward[0] * out + tangent[0] * side
    pz = z + inward[1] * out + tangent[1] * side
    return felt_clamp(px, pz)


# Exact HandTrigger size from "The Gang [Scripted]" (3385562324) - real,
# proven to catch a dealt hand on this table, not a guess like the 11x4 this
# replaced. Every per-seat display tile (dibber/mat/tray) has to clear this
# footprint - see the OUT_MAT/OUT_CTRL/SIDE_CTRL comment above.
HAND_W, HAND_D = 9.6, 5.6


def hand_zone(color, x, z):
    """Hand zone at a seat. rotY 180 throughout, matching the reference mod -
    every seat on this table looks across it the same way."""
    rot_y = 180.0
    zone = dict(BASE_FLAGS)
    zone.update({
        "GUID": guid(), "Name": "HandTrigger",
        "Transform": {
            "posX": x, "posY": 2.0, "posZ": z,
            "rotX": 0.0, "rotY": rot_y, "rotZ": 0.0,
            "scaleX": HAND_W, "scaleY": 5.0, "scaleZ": HAND_D,
        },
        "Nickname": "", "Description": "", "GMNotes": "",
        "FogColor": color,
        "Hands": False, "Tooltip": True,
        "LayoutGroupSortIndex": 0, "Value": 0,
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })
    return zone


def custom_tile(image_url, pos, rot_y, nickname, gm_notes, scale, locked=True,
                aspect=1.0):
    """A CustomTile Type 3 (Rectangle). TTS renders scaleX/scaleZ as literal,
    independent width/depth - it does NOT infer them from the image. Passing
    the same value for both, as an earlier version of this file did, squashes
    every non-square plaque (the dibber, the button, the trick mat were all
    wide rectangles) onto a square footprint: text and buttons sized for the
    real canvas end up compressed into a squarer shape than they were drawn
    for, which is what made them look oversized and cramped. `aspect` is
    height/width of the source image; scaleZ is derived from it so the tile's
    footprint actually matches what was drawn.
    """
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_Tile",
        "Transform": {
            "posX": pos[0], "posY": pos[1], "posZ": pos[2],
            "rotX": 0.0, "rotY": rot_y, "rotZ": 0.0,
            "scaleX": scale, "scaleY": 1.0, "scaleZ": scale * aspect,
        },
        "Nickname": nickname, "Description": "", "GMNotes": gm_notes,
        "Locked": locked, "Hands": False, "Grid": False, "Snap": False,
        "CustomImage": {
            "ImageURL": image_url, "ImageSecondaryURL": image_url,
            "ImageScalar": 1.0, "WidthScale": 0.0,
            "CustomTile": {"Type": 3, "Thickness": 0.2,
                           "Stackable": False, "Stretch": True},
        },
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def scripting_zone(pos, rot_y, gm_notes, size=(3.4, 3.0, 3.4)):
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "ScriptingTrigger",
        "Transform": {
            "posX": pos[0], "posY": pos[1], "posZ": pos[2],
            "rotX": 0.0, "rotY": rot_y, "rotZ": 0.0,
            "scaleX": size[0], "scaleY": size[1], "scaleZ": size[2],
        },
        "Nickname": "", "Description": "", "GMNotes": gm_notes,
        "Locked": True, "Hands": False, "Grid": False, "Snap": False,
        "Tooltip": False,
        # TTS reads these on every zone; omitting them makes the whole save
        # fail to load with "Object reference not set to an instance of an
        # object", with no clue which object caused it.
        "LayoutGroupSortIndex": 0, "Value": 0,
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def rulebook_pdf(pdf_url, pos, rot_y=0.0):
    """The real rulebook, propped up like a book - schema verified against 51
    real Custom_PDF objects across 28 workshop mods (field names, nesting,
    and the 45-degree lean are all copied from working examples, not
    guessed)."""
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_PDF",
        "Transform": {
            "posX": pos[0], "posY": pos[1], "posZ": pos[2],
            "rotX": 45.0, "rotY": rot_y, "rotZ": 0.0,
            "scaleX": 2.2, "scaleY": 1.0, "scaleZ": 2.2,
        },
        "Nickname": "Pili Pili Rulebook", "Description":
            "The official rulebook, published by ATM Gaming. Click to open, "
            "then flip through with the arrows.",
        "GMNotes": "", "Locked": True, "Hands": False,
        "CustomPDF": {"PDFUrl": pdf_url, "PDFPassword": "",
                      "PDFPage": 0, "PDFPageOffset": 0},
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def dealer_marker(image_url, pos):
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_Token",
        "Transform": transform(pos, (0, 0, 0), 0.7),
        "Nickname": "Dealer", "Description":
            "Bets start here and this seat leads the first trick. Passes left each round.",
        "GMNotes": "PILI:DEALER", "Hands": False,
        "CustomImage": {
            "ImageURL": image_url, "ImageSecondaryURL": image_url,
            "ImageScalar": 1.0, "WidthScale": 0.0,
            "CustomToken": {"Thickness": 0.2, "MergeDistancePixels": 15.0,
                            "StandUp": False, "Stackable": False},
        },
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def pili_bag(image_url):
    token = dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_Token",
        "Transform": transform((POS_PILIS[0], POS_PILIS[1] + 1, POS_PILIS[2]), (0, 0, 0), 0.55),
        "Nickname": "Pili", "Description": "One trick off your bet = one Pili.",
        "GMNotes": "PILI:TOKEN",
        # Every Custom_Token in ~450 checked across 28 real workshop mods leaves
        # ImageSecondaryURL empty, Stackable or not - TTS mirrors the front onto
        # the back by itself when it is empty and Stackable is false. An earlier
        # attempt here explicitly set the same URL on both sides on the theory
        # that Stackable alone caused a blank back; that was an unverified guess
        # and the actual reported symptom (blank back) suggests it was wrong.
        "CustomImage": {
            "ImageURL": image_url, "ImageSecondaryURL": "",
            "ImageScalar": 1.0, "WidthScale": 0.0,
            "CustomToken": {
                "Thickness": 0.15, "MergeDistancePixels": 15.0,
                "StandUp": False, "Stackable": False,
            },
        },
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Infinite_Bag",
        "Transform": transform(POS_PILIS, (0, 0, 0), 1.4),
        "Nickname": "Pilis", "Description": "Drag out a Pili. 6 ends the game.",
        "GMNotes": "PILI:BAG", "MaterialIndex": -1, "MeshIndex": -1,
        "Hands": False,
        "ContainedObjects": [token],
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


RULES = """PILI PILI - full rules

Two lines from the rulebook that say what the game is:
"In Pili Pili, you have to guess how many tricks you'll win... and try to
stick to that guess!" "A trick refers to the cards played during a round and
collected by the player who played the highest-value card!"

Everything else you need is on the table: the chilli button in the middle
runs each round, a dibber in front of every seat holds that player's bet,
and a mat catches the tricks you win.

MISSIONS start OFF. The rulebook's own advice for a first game is to skip
them and deal 5 cards straight to betting - flip the MISSIONS tile by the
mission deck whenever you want them on.

1. DEAL - press the chilli
   Missions OFF: 5 cards each.
   Missions ON: a Mission card flips first, setting the round's twist and
   how many cards to deal (printed bottom-left). Leftovers go face down on
   SET ASIDE - still in play for the one Mission that draws an extra card.

2. BET
   "Starting with the dealer, each player bets on how many tricks they
   think they will win" - use your own dibber's - and +. Bets are open
   on purpose, so you can see what everyone else is planning.

   "The total number of bets must not equal the number of cards dealt to
   each player" - there is always at least one loser. Bet last and your
   number would make the totals match? Your dibber refuses it; pick another.

3. PLAY
   The dealer leads the very first card, since nobody has won a trick yet
   to lead from. After that, "the player who plays the highest-value card
   wins the trick and leads the next one." No suits - only the number
   counts. The Joker "takes any value... between 0 and 56," chosen as you
   play it.

   Stack every trick you win on your own mat, face down, and leave it -
   the chilli button counts it at the end of the round.

4. SCORE - press the chilli again
   "Each player receives 1 Pili as a penalty for every trick they missed
   their bet by." Exactly right costs nothing. A few Missions change this
   (Cool Down, First & Last, Cursed Cards, Shared Burn) - the button can't
   see those, so just drag chillies into or out of your own tray to match
   what the card says.

5. WINNING
   "As soon as a player reaches 6 Pilis, the game ends. The player with
   the fewest Pilis is declared the winner." """

CREDITS = """Pili Pili is designed by Ben, Martin & JB and published by ATM Gaming.
This is an unofficial fan-made Tabletop Simulator implementation - buy the real
thing if you enjoy it: www.atmgaming.com

All artwork in this mod was drawn from scratch (see art.py); no publisher art or
text is reproduced here.

The 36 mission cards follow the 17 effect types printed in the official rulebook,
but the rulebook does not list each card's parameters - how many cards it deals,
which direction the arrows point, which numbers are cursed. Those splits are a
reconstruction. Edit missions.json and rerun build_save.py to correct them."""


def build(missions, urls, out_dir, aspects=None):
    aspects = aspects or {}
    objects = []

    # Seats. Everything except the hand zone is parked here and then moved into
    # place by layoutTable() at load, measured off the hand zones - so the hand
    # zone is the single source of truth for where a seat is, and correcting
    # SEATS re-lays the whole table automatically.
    for colour, sx, sz, rot_y in SEATS:
        objects.append(hand_zone(colour, sx, sz))

        mx, mz = seat_spot(sx, sz, OUT_MAT)
        objects.append(custom_tile(urls["mat"], (mx, 1.2, mz), rot_y,
                                   f"{colour} tricks", f"PILI:MAT:{colour}",
                                   scale=1.4, aspect=aspects.get("mat", 1.0)))
        objects.append(scripting_zone((mx, 2.2, mz), rot_y,
                                      f"PILI:TRICKS:{colour}",
                                      size=(4.4, 4.0, 4.0)))

        bx, bz = seat_spot(sx, sz, OUT_CTRL, SIDE_CTRL)
        objects.append(custom_tile(urls["dibber"], (bx, 1.2, bz), rot_y,
                                   f"{colour} bid", f"PILI:DIBBER:{colour}",
                                   scale=1.1, aspect=aspects.get("dibber", 1.0)))

        px, pz = seat_spot(sx, sz, OUT_CTRL, -SIDE_CTRL)
        objects.append(custom_tile(urls["tray"], (px, 1.2, pz), rot_y,
                                   f"{colour} pilis", f"PILI:TRAY:{colour}",
                                   scale=1.2))
        objects.append(scripting_zone((px, 2.2, pz), rot_y,
                                      f"PILI:PILIS:{colour}",
                                      size=(3.2, 4.0, 3.2)))

    objects.append(custom_tile(urls["button"], POS_BUTTON, 0.0,
                               "Next Round", "PILI:BUTTON", scale=1.6,
                               aspect=aspects.get("button", 1.0)))
    objects.append(custom_tile(urls["mtoggle"], POS_MTOGGLE, 0.0,
                               "Missions toggle", "PILI:MTOGGLE", scale=1.1,
                               aspect=aspects.get("mtoggle", 1.0)))
    # straight in front of the seat, in the gap the dibber and tray leave
    # Extrapolated past the first seat's dibber, away from its tray - the
    # same formula passDealer() uses in global.lua to reposition the marker
    # every round after this one, so the very first frame matches what every
    # later round will look like rather than starting from a different spot.
    d0x, d0z = seat_spot(SEATS[0][1], SEATS[0][2], OUT_CTRL, SIDE_CTRL)
    t0x, t0z = seat_spot(SEATS[0][1], SEATS[0][2], OUT_CTRL, -SIDE_CTRL)
    dx, dz = d0x + (d0x - t0x) * 0.6, d0z + (d0z - t0z) * 0.6
    objects.append(dealer_marker(urls["dealer"], (dx, 1.6, dz)))

    # play deck: 1-55 plus the Joker
    cd_play = custom_deck(urls["play_face"], urls["play_back"], 8, 7)
    play_cards = []
    for i in range(56):
        if i < 55:
            nick, desc = str(i + 1), ""
        else:
            nick, desc = "Joker", "Choose any value from 0 to 56 as you play it."
        play_cards.append(card(1, i, nick, desc, "PILI:PLAY", cd_play,
                               POS_PLAY, (0, 180, 180)))
    objects.append(deck(1, play_cards, "Numbered Cards", "PILI:PLAY", cd_play, POS_PLAY))

    # mission deck
    cd_miss = custom_deck(urls["mission_face"], urls["mission_back"], 6, 6)
    miss_cards = []
    for i, m in enumerate(missions):
        desc = m["text"].replace("\n", " ") + f"  [deal {m['cards']}]"
        if m.get("expert"):
            desc = "EXPERT. " + desc
        miss_cards.append(card(2, i, m["title"], desc, "PILI:MISSION", cd_miss,
                               POS_MISSION, (0, 180, 180)))
    objects.append(deck(2, miss_cards, "Missions", "PILI:MISSION", cd_miss, POS_MISSION))

    objects.append(pili_bag(urls["pili"]))
    # The PDF viewer itself is confirmed working (opens, flips pages, locked
    # in place as intended) - the only remaining problem was placement. Its
    # first home (x=-32) clipped the rail in the curved end-cap; its second
    # (z=-15) was still reported as tucked out of the way, and sat in the
    # same deep z=-12.5/-15 band where POS_MTOGGLE separately clipped too.
    # Moved onto the z=-9 row instead, next to Numbered Cards - the one band
    # of the dealer's cut-out with several objects confirmed clearly visible
    # and trouble-free across every screenshot so far.
    objects.append(rulebook_pdf(urls["rulebook"], (-9.0, 1.3, -9.0), rot_y=0.0))

    # snap points for played cards, ringed tightly around the middle
    snaps = []
    for i in range(len(SEATS)):
        th = math.radians(360.0 * i / len(SEATS))
        snaps.append({
            "Position": {"x": PLAY_CENTRE[0] + 5.0 * math.sin(th), "y": 1.02,
                         "z": PLAY_CENTRE[1] + 5.0 * math.cos(th)},
            "Rotation": {"x": 0.0, "y": 180.0, "z": 0.0},
            "Tags": [],
        })
    for spot in (POS_REVEAL, POS_ASIDE):
        snaps.append({"Position": {"x": spot[0], "y": 1.02, "z": spot[2]},
                      "Rotation": {"x": 0.0, "y": 0.0, "z": 0.0}, "Tags": []})

    with open(os.path.join(HERE, "global.lua"), encoding="utf-8") as fh:
        lua = fh.read()
    # the seating order is defined once, here, and injected rather than
    # duplicated in the Lua where it could drift out of sync
    order = ", ".join('"%s"' % c for c, _, _, _ in SEATS)
    header = ["-- generated by build_save.py; do not edit, change the Python",
              "SEAT_ORDER = {%s}" % order]
    for name, p in (("POS_PLAY", POS_PLAY), ("POS_ASIDE", POS_ASIDE),
                    ("POS_MISSION", POS_MISSION), ("POS_REVEAL", POS_REVEAL),
                    ("POS_DISCARD", POS_DISCARD)):
        header.append("%s = {%.2f, %.2f, %.2f}" % (name, p[0], p[1], p[2]))
    lua = "\n".join(header) + "\n\n" + lua

    save = {
        "SaveName": "Pili Pili",
        "EpochTime": int(time.time()),
        "Date": time.strftime("%d/%m/%Y %H:%M:%S"),
        "VersionNumber": "",
        "GameMode": "Pili Pili",
        "GameType": "Card Game",
        "GameComplexity": "Light",
        "Tags": ["Card Game", "Trick Taking", "Party"],
        "Gravity": 0.5,
        "PlayArea": 0.5,
        "Table": "Table_Poker",
        "Sky": "Sky_Museum",
        "Note": "Unofficial fan implementation of Pili Pili by ATM Gaming.",
        "TabStates": {
            "0": {"title": "Rules", "body": RULES, "color": "Grey",
                  "visibleColor": {"r": 0.5, "g": 0.5, "b": 0.5}, "id": 0},
            "1": {"title": "Credits", "body": CREDITS, "color": "Grey",
                  "visibleColor": {"r": 0.5, "g": 0.5, "b": 0.5}, "id": 1},
        },
        # Turns on, but left on TTS's automatic seat ordering: no workshop mod
        # in the wild writes a custom TurnOrder here, so the encoding is not
        # worth guessing at. The script drives order from SEAT_ORDER instead
        # and just sets turn_color to the dealer.
        "Turns": {"Enable": True, "Type": 0, "TurnOrder": [], "Reverse": False,
                  "SkipEmpty": True, "DisableInteractions": False,
                  "PassTurns": True, "TurnColor": ""},
        "Hands": {"Enable": True, "DisableUnused": False, "Hiding": "Default"},
        "ComponentTags": {"labels": []},
        "Grid": {"Type": 0, "Lines": False, "Color": {"r": 0, "g": 0, "b": 0},
                 "Opacity": 0.75, "ThickLines": False, "Snapping": False,
                 "Offset": False, "BothSnapping": False, "xSize": 2, "ySize": 2,
                 "PosOffset": {"x": 0, "y": 1, "z": 0}},
        "Lighting": {"LightIntensity": 0.54, "LightColor": {"r": 1, "g": 0.9804, "b": 0.8902},
                     "AmbientIntensity": 1.3, "AmbientType": 0,
                     "AmbientSkyColor": {"r": 0.5, "g": 0.5, "b": 0.5},
                     "AmbientEquatorColor": {"r": 0.5, "g": 0.5, "b": 0.5},
                     "AmbientGroundColor": {"r": 0.5, "g": 0.5, "b": 0.5},
                     "ReflectionIntensity": 1.0, "LutIndex": 0, "LutContribution": 1.0},
        "SnapPoints": snaps,
        "DecalPallet": [],
        "LuaScript": lua,
        "LuaScriptState": "",
        "XmlUI": "",          # everything lives on the table now
        "ObjectStates": objects,
    }

    path = os.path.join(out_dir, "PiliPili.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(save, fh, indent=2)
    return path


def tts_saves_dir():
    home = os.path.expanduser("~")
    for base in (os.path.join(home, "Documents"), os.path.join(home, "OneDrive", "Documents")):
        d = os.path.join(base, "My Games", "Tabletop Simulator", "Saves")
        if os.path.isdir(d):
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the save + assets here instead of the TTS Saves folder")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help="URL prefix the images are served from")
    ap.add_argument("--local", action="store_true",
                    help="point at local file:/// copies instead (host sees them, nobody else)")
    ap.add_argument("--skip-art", action="store_true", help="reuse the assets already rendered")
    args = ap.parse_args()
    if args.local:
        args.base_url = None

    with open(os.path.join(HERE, "missions.json"), encoding="utf-8") as fh:
        missions = json.load(fh)["missions"]
    if len(missions) != 36:
        print(f"note: missions.json holds {len(missions)} cards, not 36")

    if args.skip_art:
        names = {"play_face": "play_faces.png", "mission_face": "mission_faces.png",
                 "play_back": "play_back.png", "mission_back": "mission_back.png",
                 "pili": "pili_token.png", "dibber": "dibber.png",
                 "button": "round_button.png", "dealer": "dealer.png",
                 "mat": "mat_tricks.png", "tray": "mat_pilis.png",
                 "mtoggle": "mission_toggle.png"}
        files = {k: os.path.join(art.ASSETS, v) for k, v in names.items()}
    else:
        print("rendering art ...")
        files = art.generate(missions)

    # Static file, not generated by art.py - just sits in assets/ and gets
    # copied/hosted the same way as everything else below.
    files["rulebook"] = os.path.join(art.ASSETS, "ATM_GAMING_pilipili_RULES.pdf")

    out_dir = args.out or tts_saves_dir()
    if out_dir is None:
        out_dir = HERE
        print("could not find your Tabletop Simulator Saves folder - writing here instead")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    asset_dir = os.path.join(out_dir, "PiliPili_assets")
    os.makedirs(asset_dir, exist_ok=True)
    urls = {}
    for key, src in files.items():
        name = os.path.basename(src)
        dst = os.path.join(asset_dir, name)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copyfile(src, dst)
        if args.base_url:
            # TTS caches a downloaded image/PDF by URL and has no reason to
            # suspect the same URL now points at different bytes - several
            # fixes this session edited a file without the fix visibly
            # taking effect, and a stale client-side cache is a real,
            # previously-unhandled explanation for that. A content-hash
            # query string makes the URL itself change whenever the file's
            # bytes do, forcing a fresh download; an unchanged file keeps
            # the same URL, so nothing gets needlessly re-fetched.
            with open(src, "rb") as fh:
                digest = hashlib.md5(fh.read()).hexdigest()[:10]
            urls[key] = f"{args.base_url.rstrip('/')}/{name}?v={digest}"
        else:
            urls[key] = "file:///" + dst.replace("\\", "/")

    from PIL import Image as _Image
    aspects = {}
    for key in ("mat", "dibber", "button", "mtoggle"):
        with _Image.open(files[key]) as im:
            aspects[key] = im.height / im.width

    path = build(missions, urls, out_dir, aspects)
    print("save file:", path)
    if args.base_url:
        print("images:    served from", args.base_url)
        print("\nEveryone at the table will see the cards. If you changed the art,")
        print("commit and push assets/ or the others still get the old images.")
    else:
        print("images:   ", asset_dir)
        print("\nLocal images load for you only - everyone else sees blank cards.")
        print("Drop --local to point at the published assets.")


if __name__ == "__main__":
    main()
