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


# Seats on Table_Circular, in world units. Radius and HandTrigger size are
# real, averaged from the 8 HandTriggers of "Auto replace Imgur links with
# mirror site" (a real, working Table_Circular mod) - not a guess. That mod
# seats 8; these 6 are evenly redistributed round the SAME real radius rather
# than borrowed wholesale from a 6-seat mod, because none turned up in a
# search of installed Workshop mods. That's a smaller leap than guessing the
# table's geometry outright: the seat-facing formula below reproduces all 8
# of that mod's real positions exactly (see git history for the check this
# was verified against), so it's the placement formula that's proven, not
# just one seat count's worth of coordinates.
#
# Replaces Table_Custom (the rectangle): two dead short ends and a wide-open
# middle read as "big and soulless" in practice. A true circle has no
# straight-vs-curved split to get wrong either (unlike the old poker table)
# - every seat's own radius vector already is the correct "inward" direction,
# no distant reference point or per-corner exception required.
#
# CAVEAT, carried over from the rectangle's own FELT_X/FELT_Z note but
# weaker here: the rectangle's 44 x 26 had an independent community
# measurement (7'4" x 4'4") to cross-check against. There is no equivalent
# independent measurement for Table_Circular - FELT_R below is inferred
# from where real hand zones sit, not measured separately. Treat it as
# provisional until an in-game ruler check confirms or corrects it.
#
# 4th field: rotY (phi), shared by the DISPLAY tiles and the HandTrigger,
# same convention as the rectangle - it's the seat's own facing angle, and
# doubles as the angle used to compute x/z below (see seat_spot()).
FELT_R, FELT_MARGIN = 21.51, 2.0


def _seat_xz(phi_deg):
    phi = math.radians(phi_deg)
    return -FELT_R * math.sin(phi), -FELT_R * math.cos(phi)


SEATS = [(colour, *_seat_xz(phi), phi) for colour, phi in [
    ("Red", 0.0), ("Orange", 60.0), ("White", 120.0),
    ("Green", 180.0), ("Blue", 240.0), ("Purple", 300.0),
]]

# The real centre of the play area, where the snap-point ring for played
# cards sits - dead centre on a true circle, no other candidate point makes
# sense here.
PLAY_CENTRE = (0.0, 0.0)

# Real HandTrigger size, same reference mod as FELT_R above.
HAND_W, HAND_D = 11.7, 6.8

# No more trick mat or Pili tray (see the dump-zone note in build()) - just
# the dibber (bid) and one open dump zone per seat, so there is one fewer
# footprint to clear than the rectangle ever needed, and both sit closer to
# the seat's own edge of the felt than the rectangle's equivalents did.
#
# Found with an actual rotated-footprint search (real_search.py, not kept in
# the repo - a one-off script reusing layout_preview.py's corners()/
# polys_overlap() against these seats' real angles), not the simpler
# axis-aligned approximation the rectangle table could get away with. That
# approximation was tried first here and gave numbers (OUT_CTRL ~10) that
# looked fine under it but produced real overlaps once actually built and
# checked with a proper rotated-rectangle test - seats packed 60 degrees
# apart, at this radius, are close enough that an unrotated approximation of
# a rotated footprint is genuinely wrong, not just imprecise. Re-run that
# kind of search (not the axis-aligned kind) over layout_preview.py's own
# corners()/polys_overlap() if any of SEATS, HAND_W/HAND_D, or these scales
# change. Reported after a real load: still not close enough to the edge -
# re-run with a smaller required margin (1.5, was 2.0) and it turns out
# OUT_CTRL and DUMP_HALF trade directly against each other at this radius
# (a smaller, still-real search found the exact tradeoff curve: shrinking
# DUMP_HALF by roughly 1 unit buys roughly 1.5 units of extra closeness to
# the rim) - these values move the dump zone about 0.8 units closer to the
# rim than the previous pass, trading some of its size for that.
OUT_CTRL = 6.0      # dibber, and the dump zone's own "forward" distance
SIDE_DUMP = 3.8     # dump zone, sideways from the dibber
DUMP_HALF = 2.5     # dump zone half-size (must match the scripting_zone size below)

# Shared piles and controls, in the open middle a circular table gives for
# free (unlike the rectangle, which had to earn this space back from two
# dead short ends). Kept close to the centre and to each other on request
# rather than spread out to fill the available radius - "just try it and
# see" on the exact numbers; layout_preview.py is the actual check.
# Two mirrored rows across the centre, requested explicitly: cards on one
# side, tokens and controls on the other. BOTH decks sit opposite BOTH bags
# (an earlier pass only mirrored the play deck and left the mission deck off
# to one side, which is what "the decks should be opposite the bags" was
# about). Discard sits beside its own deck, aside beside the mission deck.
POS_REVEAL = (0.0, 1.6, 0.0)
POS_PLAY = (-3.2, 1.6, 6.5)        # mirrors POS_PILIS
POS_MISSION = (3.2, 1.6, 6.5)      # mirrors POS_TRICKBAG
POS_DISCARD = (-8.0, 1.6, 3.0)     # face up - see gather()'s rotation in global.lua
POS_ASIDE = (8.0, 1.6, 3.0)
POS_PILIS = (-3.2, 1.6, -6.5)      # Pili token supply bag
POS_TRICKBAG = (3.2, 1.6, -6.5)    # trick token supply bag
# Next Round/Reset side by side, in front of the bags. NOT stacked: stacking
# them puts one further in toward the middle, and the whole point of keeping
# them out here is that the centre of the table is where cards get played.
# Side by side spends tangential space instead of radial, so the pair stays
# one band's worth of depth no matter how many controls end up here.
POS_BUTTON = (-2.0, 1.3, -4.2)
POS_NEWGAME = (2.0, 1.3, -4.2)
POS_MTOGGLE = (7.0, 1.3, 5.2)      # by the mission deck, since that is what it toggles

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


# Every seat's own radius vector already is the correct "inward" direction on
# a true circle - unlike either previous table, there's no per-seat exception
# and no distant reference point needed to stop directions converging.
# `phi_deg` is the seat's own rotY (SEATS' 4th field): inward = (sin phi,
# cos phi), tangent = (cos phi, -sin phi), which is what reproduces the
# reference mod's real 8 seat positions exactly (see the SEATS comment).
def seat_spot(x, z, phi_deg, out, side=0.0):
    phi = math.radians(phi_deg)
    inward = (math.sin(phi), math.cos(phi))
    tangent = (math.cos(phi), -math.sin(phi))
    px = x + inward[0] * out + tangent[0] * side
    pz = z + inward[1] * out + tangent[1] * side
    return felt_clamp(px, pz)


def felt_clamp(x, z, margin=FELT_MARGIN):
    """Pull (x, z) back inside the circular felt, `margin` inside its edge."""
    r = math.hypot(x, z)
    lim = FELT_R - margin
    if r <= lim or r == 0:
        return x, z
    return x / r * lim, z / r * lim


def face_centre(x, z):
    """rotY that points a plaque's baked "up" from (x, z) toward the table
    centre - the general form of SEATS' own rotation (reproduces every
    SEATS rotY exactly, given that seat's own x/z), for objects that aren't
    tied to a seat and so have no rotY of their own to inherit."""
    if x == 0 and z == 0:
        return 0.0
    return math.degrees(math.atan2(-x, -z)) % 360.0


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


def custom_tile(image_url, pos, rot_y, nickname, gm_notes, scale, locked=True):
    """A CustomTile Type 3 (Rectangle).

    **scaleX and scaleZ must be equal.** TTS works out the tile's rendered
    shape from the source image's own aspect ratio; scaleX/scaleZ are a
    uniform size multiplier on top of that, NOT independent width/depth.
    Verified against real workshop tiles that ship non-square art - e.g. a
    Type 3 tile with a 1520x478 image (3.18:1) at scaleX = scaleZ = 1.5, and
    Type 0 tiles at 1600x700 and 3355x2040, all with equal scales. Across
    451 real tiles checked, every single one has scaleX == scaleZ.

    An earlier version of this file believed the opposite ("TTS renders
    scaleX/scaleZ literally and does not infer them from the image") and set
    scaleZ = scale * image aspect - which applies the aspect a SECOND time on
    top of the one TTS already applies, squashing the tile flat. That is what
    the reported squishing actually was, and chasing it as an image problem
    (or a caching problem) wasted a lot of time. Want a rectangular tile?
    Draw a rectangular image and leave the scale uniform.
    """
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_Tile",
        "Transform": {
            "posX": pos[0], "posY": pos[1], "posZ": pos[2],
            "rotX": 0.0, "rotY": rot_y, "rotZ": 0.0,
            "scaleX": scale, "scaleY": 1.0, "scaleZ": scale,
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
    """The real rulebook, lying flat on the felt.

    Schema verified against 51 real Custom_PDF objects across 28 workshop
    mods. It used to lean at rotX=45, copied from working examples - but only
    half-copied: **every** real leaning PDF (7 of them) also sits at
    posY 4.0-4.46, well clear of the table, while the flat ones (20+) sit at
    posY 0.96-1.7. Ours took the 45-degree lean and kept a flat object's
    height, so the lower half of the page was underneath the table surface
    and got clipped - the page turned fine and popped out fine, it was just
    sunken. Flat at a flat object's height can't have that problem at all,
    and on a table this small a full-size book propped up at head height
    would dominate the middle anyway. All 51 use scaleX == scaleZ.
    """
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_PDF",
        "Transform": {
            "posX": pos[0], "posY": pos[1], "posZ": pos[2],
            "rotX": 0.0, "rotY": rot_y, "rotZ": 0.0,
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


def token_bag(image_url, pos, bag_notes, bag_nick, bag_desc,
             token_notes, token_nick, token_desc, scale=1.4):
    """An Infinite_Bag holding one prototype Custom_Token, the pattern both
    the Pili and trick-token supplies use. Every Custom_Token in ~450 checked
    across 28 real workshop mods leaves ImageSecondaryURL empty, Stackable or
    not - TTS mirrors the front onto the back by itself when it is empty and
    Stackable is false. An earlier attempt here explicitly set the same URL
    on both sides on the theory that Stackable alone caused a blank back;
    that was an unverified guess and the actual reported symptom (blank
    back) suggests it was wrong."""
    token = dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_Token",
        "Transform": transform((pos[0], pos[1] + 1, pos[2]), (0, 0, 0), 0.55),
        "Nickname": token_nick, "Description": token_desc,
        "GMNotes": token_notes,
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
        "Transform": transform(pos, (0, 0, 0), scale),
        "Nickname": bag_nick, "Description": bag_desc,
        "GMNotes": bag_notes, "MaterialIndex": -1, "MeshIndex": -1,
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


def build(missions, urls, out_dir):
    objects = []

    # Seats. Everything except the hand zone is parked here and then moved into
    # place by layoutTable() at load, measured off the hand zones - so the hand
    # zone is the single source of truth for where a seat is, and correcting
    # SEATS re-lays the whole table automatically.
    #
    # No trick mat, no Pili tray - see the module docstring-equivalent note
    # in CLAUDE.md ("Trick and Pili storage"). Cards from a resolved trick go
    # to the shared discard; the trick's winner drags one trick-token from
    # PILI:TRICKBAG onto their own dump zone, exactly as Pilis already work
    # (givePilis() in global.lua). One dump zone per seat holds both token
    # kinds - players sort out whose is whose, and clear the trick-tokens
    # back to the supply themselves at reset (or gather() does it - see
    # global.lua). That is one fewer footprint than the rectangle needed,
    # which is what let both remaining pieces sit closer to the seat's own
    # edge of the felt than the rectangle's dibber/tray ever did.
    for colour, sx, sz, rot_y in SEATS:
        objects.append(hand_zone(colour, sx, sz, rot_y))

        bx, bz = seat_spot(sx, sz, rot_y, OUT_CTRL)
        objects.append(custom_tile(urls["dibber"], (bx, 1.2, bz), rot_y,
                                   f"{colour} bid", f"PILI:DIBBER:{colour}",
                                   scale=1.1))

        # Reported bug: the tile and its zone used to share one GMNotes tag
        # ("there's only one functional zone, a second tag has no purpose" -
        # true, but one() (tagged(tag, true)[1]) doesn't guarantee which of
        # the two same-tagged objects it hands back. It returned the plain
        # Custom_Tile at the table, which has no getObjects() - "Attempting
        # to call getObjects() on an object that does not support
        # getObjects()", crashing sweepAndDeal(). The tile now carries its
        # own separate, script-unused tag (PILI:DUMPTILE) - back to the old
        # mat/tray-vs-tricks/pilis split this replaced, for exactly the
        # reason that split existed.
        dx, dz = seat_spot(sx, sz, rot_y, OUT_CTRL, SIDE_DUMP)
        objects.append(custom_tile(urls["dump"], (dx, 1.2, dz), rot_y,
                                   f"{colour} dump", f"PILI:DUMPTILE:{colour}",
                                   scale=2.0))
        objects.append(scripting_zone((dx, 2.2, dz), rot_y,
                                      f"PILI:DUMP:{colour}",
                                      size=(DUMP_HALF * 2, 4.0, DUMP_HALF * 2)))

    # Next Round and New Game aren't tied to a seat, so - same lesson as the
    # rectangle table's first pass, which shipped everything at a lazy
    # rot_y=0.0 and had it all facing away from the table - their facing has
    # to be worked out from their own position, not inherited. face_centre()
    # generalises SEATS' own rotation formula (rotY such that a tile's baked
    # "up" points at the table centre) to any position, seat or not. They
    # share ONE rotation (their cluster's own midpoint, not each one's own
    # slightly different angle) so the pair reads as one matched control
    # rather than two tiles tilted at a visible angle to each other - and so
    # neither one's footprint reaches further towards the other than its
    # plain half-width, which an off-axis rotation would otherwise do.
    ctrl_rot = face_centre((POS_BUTTON[0] + POS_NEWGAME[0]) / 2,
                           (POS_BUTTON[2] + POS_NEWGAME[2]) / 2)
    # A tile's SHORT side follows the scale, its long side extends with the
    # image's aspect (see custom_tile()), so a 900x280 nameplate at the old
    # square-tile scale of 1.28 came out ~3.2x too wide - "they're now
    # massive". This is sized off the long side instead: ~3.3 units wide.
    CTRL_SCALE = 0.45
    objects.append(custom_tile(urls["button"], POS_BUTTON, ctrl_rot,
                               "Next Round", "PILI:BUTTON", scale=CTRL_SCALE))
    objects.append(custom_tile(urls["newgame"], POS_NEWGAME, ctrl_rot,
                               "Reset", "PILI:NEWGAME", scale=CTRL_SCALE))
    objects.append(custom_tile(urls["mtoggle"], POS_MTOGGLE,
                               face_centre(POS_MTOGGLE[0], POS_MTOGGLE[2]),
                               "Missions toggle", "PILI:MTOGGLE", scale=1.1))
    # straight in front of the seat, toward the dump zone
    # Extrapolated past the first seat's dibber, away from its dump zone -
    # the same formula passDealer() uses in global.lua to reposition the
    # marker every round after this one, so the very first frame matches
    # what every later round will look like rather than starting from a
    # different spot.
    d0x, d0z = seat_spot(SEATS[0][1], SEATS[0][2], SEATS[0][3], OUT_CTRL)
    p0x, p0z = seat_spot(SEATS[0][1], SEATS[0][2], SEATS[0][3], OUT_CTRL, SIDE_DUMP)
    dx, dz = d0x + (d0x - p0x) * 0.6, d0z + (d0z - p0z) * 0.6
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

    objects.append(token_bag(
        urls["pili"], POS_PILIS, "PILI:BAG", "Pilis",
        "Drag out a Pili when you owe one. Hand-tracked - agree between "
        "yourselves when someone's had enough, then hit Reset.",
        "PILI:TOKEN", "Pili", "One trick off your bet = one Pili."))
    objects.append(token_bag(
        urls["trick"], POS_TRICKBAG, "PILI:TRICKBAG", "Trick tokens",
        "Won a trick? Drag one into your own dump zone. Cleared away "
        "automatically at the next deal.",
        "PILI:TRICKTOKEN", "Trick", "One of these = one trick won this round."))
    # Reported after a real load: too far forward (toward the centre) -
    # moved out toward the felt edge as asked. Hand-picking a gap between
    # two dump zones by angle alone kept clipping something else nearby
    # (the dealer marker, which sits close to Red but not centred on it -
    # see passDealer() - then a HandTrigger, much wider than any dump zone,
    # then a second HandTrigger) each time a new spot looked clear by eye.
    # This one instead comes from an actual search over every real
    # footprint already in the build (find_rulebook_spot.py, not kept in
    # the repo - reuses layout_preview.py's own corners()/polys_overlap())
    # for the largest radius that clears everything, same "trust the real
    # check, not the 2D picture" lesson as the rest of this table's layout.
    # face_centre() still works out which way is "into the table" from
    # wherever it actually sits.
    RULEBOOK_POS = (-7.89, 1.3, -17.72)   # flat, see rulebook_pdf()
    objects.append(rulebook_pdf(urls["rulebook"], RULEBOOK_POS,
                                rot_y=face_centre(RULEBOOK_POS[0], RULEBOOK_POS[2])))

    # No snap points anywhere near the middle. There used to be a ring of six
    # around PLAY_CENTRE for played cards, plus one dead centre at
    # POS_REVEAL - which is exactly where people actually throw cards, so all
    # it did was drag them into fixed slots. Snap points here are entirely
    # ours to choose (nothing about the table forces them), so the middle is
    # simply left free. The two kept below are both well off-centre and only
    # help tidy the piles the script itself uses.
    snaps = []
    for spot in (POS_ASIDE, POS_DISCARD):
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
        # Table_Circular is a built-in table, not a Custom one - confirmed
        # against the one real Table_Circular mod installed locally, it has
        # no "TableURL" key at all. Unlike Table_Custom, there is no way to
        # put our own felt art on it; this is TTS's own stock circular
        # table surface, whatever that looks like. art.felt() is kept
        # (harmless, and useful again if a Custom table ever comes back)
        # but nothing here references its output any more.
        "Table": "Table_Circular",
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
                 "pili": "pili_token.png", "trick": "trick_token.png",
                 "dibber": "dibber.png", "dump": "dump_area.png",
                 "button": "round_button.png", "newgame": "new_game_button.png",
                 "dealer": "dealer.png",
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

    path = build(missions, urls, out_dir)
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
