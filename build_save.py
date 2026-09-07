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


POS_PLAY = (-6.2, 1.6, -2.8)
POS_ASIDE = (-6.2, 1.6, 2.8)
POS_MISSION = (6.2, 1.6, 2.8)
POS_REVEAL = (6.2, 1.6, -2.8)
POS_DISCARD = (0.0, 1.6, -3.4)
POS_BUTTON = (0.0, 1.3, 3.4)
POS_PILIS = (-11.0, 1.6, -5.0)

# how far out from the middle each per-seat object sits, as a fraction of the
# seat's own position, plus a sideways nudge so dibber and Pilis don't overlap
F_DIBBER, F_TRICKS = 0.82, 0.55
SIDE_OFFSET = 2.9

# Table_Poker's playing surface, roughly, in TTS units.
TABLE_A, TABLE_B = 17.0, 9.5

# Where each seat sits on that oval, as fractions of (TABLE_A, TABLE_B),
# and which colour is in it. THIS ORDER MUST MATCH THE TABLE'S OWN SEATS -
# TTS assigns colours to a built-in table's seats itself, and a zone only
# works if it is parked at the seat of the colour it is tinted with. Sit in
# each colour and check the nameplates, then reorder this list to match.
SEATS = [
    ("White",  0.00,  1.00),   # bottom centre
    ("Red",    0.58,  1.00),   # bottom right
    ("Orange", 1.00,  0.00),   # right end
    ("Yellow", 0.58, -1.00),   # top right
    ("Green",  0.00, -1.00),   # top centre
    ("Teal",  -0.58, -1.00),   # top left
    ("Blue",  -1.00,  0.00),   # left end
    ("Purple", -0.58, 1.00),   # bottom left
]

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


def hand_zone(color, fx, fz):
    """Hand zone at (fx, fz) as a fraction of the table's half-width/depth.

    Table_Poker is an oval, so an evenly-spaced circle of zones does not land
    on its seats - they run along the two long sides plus one at each end.
    """
    x, z = fx * TABLE_A, fz * TABLE_B
    rot_y = math.degrees(math.atan2(-x, -z)) % 360.0   # face the middle
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


def seat_frame(fx, fz):
    """Seat position plus its inward-facing rotation and sideways axis."""
    x, z = fx * TABLE_A, fz * TABLE_B
    rot_y = math.degrees(math.atan2(-x, -z)) % 360.0
    n = math.hypot(x, z) or 1.0
    inward = (-x / n, -z / n)
    right = (-inward[1], inward[0])
    return (x, z), rot_y, right


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
        "Transform": transform(pos, (0, 0, 0), 0.9),
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
    for colour, fx, fz in SEATS:
        objects.append(hand_zone(colour, fx, fz))
        (sx, sz), rot_y, right = seat_frame(fx, fz)

        dx, dz = sx * F_DIBBER, sz * F_DIBBER
        objects.append(custom_tile(
            urls["dibber"],
            (dx + right[0] * SIDE_OFFSET, 1.3, dz + right[1] * SIDE_OFFSET),
            rot_y, f"{colour} bid", f"PILI:DIBBER:{colour}", scale=1.1))

        objects.append(custom_tile(
            urls["mat"], (sx * F_TRICKS, 1.2, sz * F_TRICKS), rot_y,
            f"{colour} tricks", f"PILI:MAT:{colour}", scale=1.7))
        objects.append(scripting_zone(
            (sx * F_TRICKS, 2.0, sz * F_TRICKS), rot_y,
            f"PILI:TRICKS:{colour}", size=(3.8, 3.0, 3.4)))

        objects.append(custom_tile(
            urls["tray"],
            (dx - right[0] * SIDE_OFFSET, 1.2, dz - right[1] * SIDE_OFFSET),
            rot_y, f"{colour} pilis", f"PILI:TRAY:{colour}", scale=1.2))
        objects.append(scripting_zone(
            (dx - right[0] * SIDE_OFFSET, 2.0, dz - right[1] * SIDE_OFFSET),
            rot_y, f"PILI:PILIS:{colour}", size=(3.2, 3.0, 3.2)))

    objects.append(custom_tile(urls["button"], POS_BUTTON, 0.0,
                               "Next Round", "PILI:BUTTON", scale=2.0))
    first_seat = seat_frame(SEATS[0][1], SEATS[0][2])[0]
    objects.append(dealer_marker(
        urls["dealer"], (first_seat[0] * 0.90, 1.6, first_seat[1] * 0.90)))

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
            "Position": {"x": -2.4 * math.sin(th), "y": 1.02, "z": -2.4 * math.cos(th)},
            "Rotation": {"x": 0.0, "y": 360.0 * i / len(SEATS), "z": 0.0},
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
    lua = ("-- generated by build_save.py from SEATS; do not edit\n"
           "SEAT_ORDER = {%s}\n\n" % order) + lua

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
