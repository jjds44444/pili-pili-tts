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
SEATS = [
    ("Red",    -34.07,  7.91),
    ("Orange", -21.77, 14.48),
    ("White",   -6.85, 14.42),
    ("Green",    6.83, 14.45),
    ("Blue",    21.04, 14.32),
    ("Purple",  34.07,  7.91),
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

OUT_MAT = 10.0        # trick mat, in front of the seat
OUT_CTRL = 3.0        # dibber and Pili tray, between the seat and the mat
SIDE_CTRL = 3.0        # and apart from each other

POS_PLAY = (-16.0, 1.6, -15.0)
POS_ASIDE = (-25.0, 1.6, -15.0)
POS_MISSION = (16.0, 1.6, -15.0)
POS_DISCARD = (25.0, 1.6, -15.0)
POS_REVEAL = (0.0, 1.6, -11.0)
POS_BUTTON = (0.0, 1.3, -16.5)
POS_PILIS = (0.0, 1.6, -5.0)

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


# Table_Poker's felt, estimated from real objects in "The Gang" workshop
# mods (see layout_preview.py). Corner seats can walk a per-seat offset
# outside this with a large enough SIDE_CTRL, so every computed spot is
# clamped back onto it with a small margin - cheap insurance since these
# bounds are themselves an estimate, not a value TTS exposes directly.
FELT_X, FELT_Z, FELT_MARGIN = 38.0, 19.0, 2.0


def seat_spot(x, z, out, side=0.0):
    inward, tangent = seat_frame(x, z)
    px = x + inward[0] * out + tangent[0] * side
    pz = z + inward[1] * out + tangent[1] * side
    lim_x, lim_z = FELT_X - FELT_MARGIN, FELT_Z - FELT_MARGIN
    return (max(-lim_x, min(lim_x, px)), max(-lim_z, min(lim_z, pz)))


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
            "scaleX": 11.0, "scaleY": 5.0, "scaleZ": 4.0,
        },
        "Nickname": "", "Description": "", "GMNotes": "",
        "FogColor": color,
        "Hands": False, "Tooltip": True,
        "LayoutGroupSortIndex": 0, "Value": 0,
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })
    return zone


def custom_tile(image_url, pos, rot_y, nickname, gm_notes, scale, locked=True):
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
        # Stackable tokens get a generated quantity face on the reverse, which
        # with no ImageSecondaryURL renders as a broken "2" side. Give the back
        # the same art and drop stacking - the panel counts Pilis anyway.
        "CustomImage": {
            "ImageURL": image_url, "ImageSecondaryURL": image_url,
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


RULES = """PILI PILI - how a round runs

Everything is on the table. The chilli button in the middle runs the round;
the dibber in front of you sets your bet.

Guess how many tricks you will win, then win exactly that many.

1. PRESS THE CHILLI
   The NEXT ROUND button scores the round just finished, sweeps every card back,
   reshuffles, flips a new Mission and deals what it prints. Leftovers go face
   down on the SET ASIDE spot - still in play for missions that draw a card.
   Press it once at the start to begin.

2. BET
   Starting with the DEALER (gold marker) and going round, set your bet on the
   dibber in front of you with - and +. Bets are open - everyone sees them.
   The bets must NOT total the number of cards dealt to each player, so there is
   always at least one loser. The last person to bet cannot choose the number
   that would make them match, and their dibber will refuse it.

3. PLAY TRICKS
   The dealer leads. Everyone plays one card to the middle. Highest number takes
   the trick - no suits, only the number. The Joker takes any value 0 to 56,
   declared as you play it.

   PUT THE TRICKS YOU WIN IN YOUR OWN PILE, on the mat in front of you. That is
   how the button works out what you scored, so keep them there until the round
   is scored.

4. NEXT ROUND
   Press the chilli again. It counts each pile, works out tricks won, compares it
   to your bet and drops a Pili in your tray for every trick you were out by.
   Exactly right costs nothing.

   Missions that change the scoring (Cool Down, First & Last, Cursed Cards,
   Shared Burn) are on you - just drag chillies in or out of your tray to match.

5. WINNING
   The moment somebody has 6 Pilis in their tray the game ends, and whoever has
   the FEWEST wins.

FIRST GAME? Ignore the Mission deck, deal 5 each and go straight to betting."""

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
    for colour, sx, sz in SEATS:
        objects.append(hand_zone(colour, sx, sz))
        rot_y = 180.0

        mx, mz = seat_spot(sx, sz, OUT_MAT)
        objects.append(custom_tile(urls["mat"], (mx, 1.2, mz), rot_y,
                                   f"{colour} tricks", f"PILI:MAT:{colour}",
                                   scale=1.9))
        objects.append(scripting_zone((mx, 2.2, mz), rot_y,
                                      f"PILI:TRICKS:{colour}",
                                      size=(4.4, 4.0, 4.0)))

        bx, bz = seat_spot(sx, sz, OUT_CTRL, SIDE_CTRL)
        objects.append(custom_tile(urls["dibber"], (bx, 1.2, bz), rot_y,
                                   f"{colour} bid", f"PILI:DIBBER:{colour}",
                                   scale=1.3))

        px, pz = seat_spot(sx, sz, OUT_CTRL, -SIDE_CTRL)
        objects.append(custom_tile(urls["tray"], (px, 1.2, pz), rot_y,
                                   f"{colour} pilis", f"PILI:TRAY:{colour}",
                                   scale=1.2))
        objects.append(scripting_zone((px, 2.2, pz), rot_y,
                                      f"PILI:PILIS:{colour}",
                                      size=(3.2, 4.0, 3.2)))

    objects.append(custom_tile(urls["button"], POS_BUTTON, 0.0,
                               "Next Round", "PILI:BUTTON", scale=2.0))
    # straight in front of the seat, in the gap the dibber and tray leave
    # offset to the side of the dealer's own dibber, level with it, so it
    # never competes with the mat sitting further out on the same line
    dx, dz = seat_spot(SEATS[0][1], SEATS[0][2], OUT_CTRL, SIDE_CTRL * 2.2)
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
    order = ", ".join('"%s"' % c for c, _, _ in SEATS)
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
                 "mat": "mat_tricks.png", "tray": "mat_pilis.png"}
        files = {k: os.path.join(art.ASSETS, v) for k, v in names.items()}
    else:
        print("rendering art ...")
        files = art.generate(missions)

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
            urls[key] = args.base_url.rstrip("/") + "/" + name
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
