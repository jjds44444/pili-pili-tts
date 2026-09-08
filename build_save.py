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


# Seats on Table_Custom (Custom Rectangle), in world units, lifted verbatim
# from "The Settlers of Catan" workshop mod (1010436537647666695) - a real
# 6-player game on this exact table, using this exact 3-per-long-side
# arrangement. Replaces Table_Poker: that table's stadium shape (straight
# sides, curved end-caps) drove most of the corner-facing, felt-boundary and
# crowding problems below - see git history for the old SEATS/felt_clamp/
# DIR_CENTRE machinery this replaced. This table is a plain rectangle with
# seats on the two long sides only (the short ends are free, same role the
# poker table's dealer cut-out used to play) - no corners, no curved caps, no
# per-seat rotation guesswork.
# 4th field: rotY, shared by DISPLAY tiles (dibber/mat/tray/dealer) *and* the
# HandTrigger - unlike the poker table, the reference mod uses a HandTrigger
# rotY matching each row's own facing (0 for the south row, 180 for the
# north), not one constant, so there is no split to track here.
SEATS = [
    ("Red",    -23.67, -34.43,   0.0),
    ("Orange",   0.00, -34.43,   0.0),
    ("White",   23.67, -34.26,   0.0),
    ("Green",   23.67,  34.45, 180.0),
    ("Blue",     0.00,  34.45, 180.0),
    ("Purple", -23.67,  34.43, 180.0),
]

# The real centre of the play area, where the snap-point ring for played
# cards sits. With seats on only the two long sides, "inward" is just
# straight toward z=0 for every seat - no distant reference point needed to
# keep seats' lanes from converging (the poker table's DIR_CENTRE hack, now
# gone - see seat_spot()).
PLAY_CENTRE = (0.0, 0.0)

# Exact HandTrigger size from "The Settlers of Catan" - real, not a guess.
# Every per-seat display tile (dibber/mat/tray) has to clear this footprint.
HAND_W, HAND_D = 15.3, 6.4

# OUT_MAT/OUT_CTRL/SIDE_CTRL found by the same kind of search the poker table
# used (see git history for that script) - over this table's real rectangular
# felt (see FELT_X/FELT_Z below) and the tiles' real square footprints (see
# custom_tile), for the smallest OUT_MAT/OUT_CTRL under which every tile
# clears every hand zone, the felt edge, and every other tile with a 0.5-unit
# margin. On this table the felt edge is the binding constraint, not the hand
# zone: HAND_D means each hand zone's near edge already sits well past the
# felt boundary (players' hands hover past the rail, into their lap), so
# clearing the felt automatically clears the hand zone too.
OUT_MAT = 16.3         # trick mat, in front of the seat, toward the centre
OUT_CTRL = 12.1        # dibber and Pili tray, between the seat and the mat
SIDE_CTRL = 1.7        # and apart from each other

# Shared piles and controls. With seats on only the north/south edges, the
# east/west flanks (|x| beyond the seats' own 23.67, out to the felt edge)
# are as free of hand zones and mats as the poker table's dealer cut-out
# used to be - without that cut-out being the only unrailed, exposed edge on
# the table (every edge here is a plain straight rail), so there is no
# repeat of the play-deck-drifting-off bug to guard against by placement
# alone. lockAtRest() in global.lua is kept regardless, as a second line of
# defence against any pile getting nudged.
POS_PLAY = (-30.0, 1.6, -8.0)
POS_ASIDE = (-30.0, 1.6, 8.0)
POS_MISSION = (30.0, 1.6, -8.0)
POS_DISCARD = (30.0, 1.6, 8.0)
POS_REVEAL = (0.0, 1.6, 0.0)
POS_BUTTON = (0.0, 1.3, 10.0)
POS_PILIS = (0.0, 1.6, -10.0)
# Missions toggle and rulebook sit together, further out on the same west
# flank than PLAY/ASIDE - off to one side of the table, out of the open
# middle, rather than parked on the centreline where they read as sat in the
# way of the play area.
POS_MTOGGLE = (-38.0, 1.3, 6.0)

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


# The table is a plain rectangle with seats on the north/south long sides
# only, so every seat's "inward" direction is simply straight toward z=0 -
# unlike the old poker table (seats fanned round a curved edge), there is no
# convergence problem to work around with a distant reference point.
def seat_spot(x, z, out, side=0.0):
    inward = -1.0 if z > 0 else 1.0
    return felt_clamp(x + side, z + inward * out)


# Table_Custom's felt is a plain rectangle - measured at 7'4" x 4'4"
# (community measurement, see PR description / git history), which in TTS's
# inches-as-units convention is FELT_X x FELT_Z below. No stadium shape, no
# curved end-caps, no per-corner guesswork: unlike the old Table_Poker
# constants this replaced, a straight |x| <= / |z| <= check is exact here,
# not an approximation layout_preview.py has to wave through with false
# confidence.
FELT_X, FELT_Z, FELT_MARGIN = 44.0, 26.0, 2.0


def felt_clamp(x, z, margin=FELT_MARGIN):
    lim_x, lim_z = FELT_X - margin, FELT_Z - margin
    return max(-lim_x, min(lim_x, x)), max(-lim_z, min(lim_z, z))


def hand_zone(color, x, z, rot_y):
    """Hand zone at a seat. rot_y matches the seat's own facing (SEATS'
    4th field) - the reference mod uses a HandTrigger rotY that varies by
    row (0 south, 180 north) on this table, unlike the poker table's
    constant 180."""
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
        objects.append(hand_zone(colour, sx, sz, rot_y))

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

    # rot_y here is about which way "up" in the plaque's own artwork points in
    # the world - at rot_y=0 that's world +z (the same baked default the
    # south row's own tiles use), at rot_y=180 world -z, at rot_y=90 world +x.
    # These three objects aren't tied to a seat, so the row convention above
    # doesn't apply automatically - each needs it worked out from its own
    # position instead of inheriting 0.0 by default (the bug reported after
    # the last build: everything not tied to a seat came out facing away from
    # the table instead of into it).
    # POS_BUTTON sits on the centreline but closer to the north row (z=+10,
    # between centre and the north mats at ~+18) than the south - oriented to
    # match the north row's own rot_y=180 so it faces those nearest players.
    objects.append(custom_tile(urls["button"], POS_BUTTON, 180.0,
                               "Next Round", "PILI:BUTTON", scale=1.6,
                               aspect=aspects.get("button", 1.0)))
    # POS_MTOGGLE sits on the open west flank, off the felt's centreline
    # entirely - rot_y=90 points its "up" toward world +x, i.e. into the
    # table from that edge, rather than toward north/south where nobody
    # relevant is standing.
    objects.append(custom_tile(urls["mtoggle"], POS_MTOGGLE, 90.0,
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
    # in place as intended) on the old table - only its placement needs
    # redoing here. Sits right next to POS_MTOGGLE on the same west flank
    # (see the comment there) rather than on the centreline, where it read
    # as sat in the middle of the play area for no reason. rot_y=90 for the
    # same reason as POS_MTOGGLE just above - it faces into the table (world
    # +x) rather than toward north/south, which is meaningless out on this
    # flank.
    objects.append(rulebook_pdf(urls["rulebook"], (-38.0, 1.3, -6.0), rot_y=90.0))

    # snap points for played cards, ringed tightly around the middle
    snaps = []
    for i in range(len(SEATS)):
        th = math.radians(360.0 * i / len(SEATS))
        snaps.append({
            "Position": {"x": PLAY_CENTRE[0] + 6.0 * math.sin(th), "y": 1.02,
                         "z": PLAY_CENTRE[1] + 6.0 * math.cos(th)},
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
        "Table": "Table_Custom",
        "TableURL": urls["felt"],
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
                 "mtoggle": "mission_toggle.png", "felt": "felt.png"}
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
