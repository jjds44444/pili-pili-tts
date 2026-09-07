"""Build the Pili Pili Tabletop Simulator save file.

    python build_save.py                 # render art + install into your TTS Saves folder
    python build_save.py --out .         # write everything here instead
    python build_save.py --base-url URL  # point the images at a web host (for multiplayer)

Local file:/// image paths only load for the person hosting the table. If you want
other people to see the cards, upload the contents of the assets folder somewhere
public (Steam Cloud, imgur, a GitHub raw URL) and rerun with --base-url.
"""
import argparse
import json
import os
import random
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import art  # noqa: E402  (lives next to this script)

COLORS = ["Red", "Orange", "Yellow", "Green", "Teal", "Blue", "Purple", "White"]
COLOR_HEX = {
    "Red": "#e04a3c", "Orange": "#e08a2c", "Yellow": "#d8cc44", "Green": "#4fb35a",
    "Teal": "#3fb6a8", "Blue": "#4a86e8", "Purple": "#9a63d0", "White": "#e8e4dc",
}

POS_PLAY = (-7.0, 1.6, 0.0)
POS_MISSION = (7.0, 1.6, 0.0)
POS_REVEAL = (7.0, 1.6, -5.5)
POS_DISCARD = (11.5, 1.6, 0.0)
POS_BIDS = (-11.5, 1.6, 0.0)
POS_PILIS = (-7.0, 1.6, 6.0)
SEAT_RADIUS = 16.0

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


def hand_zone(color, index, total):
    import math
    theta = math.radians(360.0 * index / total)
    pos = (-SEAT_RADIUS * math.sin(theta), 2.0, -SEAT_RADIUS * math.cos(theta))
    z = dict(BASE_FLAGS)
    z.update({
        "GUID": guid(), "Name": "HandTrigger",
        "Transform": {
            "posX": pos[0], "posY": pos[1], "posZ": pos[2],
            "rotX": 0.0, "rotY": 360.0 * index / total, "rotZ": 0.0,
            "scaleX": 12.0, "scaleY": 5.0, "scaleZ": 4.0,
        },
        "Nickname": "", "Description": "", "GMNotes": "",
        "FogColor": color,
        "Hands": False, "Tooltip": True,
    })
    return z


def pili_bag(image_url):
    token = dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Custom_Token",
        "Transform": transform((POS_PILIS[0], POS_PILIS[1] + 1, POS_PILIS[2]), (0, 0, 0), 0.55),
        "Nickname": "Pili", "Description": "One trick off your bet = one Pili.",
        "GMNotes": "PILI:TOKEN",
        "CustomImage": {
            "ImageURL": image_url, "ImageSecondaryURL": "",
            "ImageScalar": 1.0, "WidthScale": 0.0,
            "CustomToken": {
                "Thickness": 0.15, "MergeDistancePixels": 15.0,
                "StandUp": False, "Stackable": True,
            },
        },
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })
    return dict(BASE_FLAGS, **{
        "GUID": guid(), "Name": "Infinite_Bag",
        "Transform": transform(POS_PILIS, (0, 0, 0), 1.4),
        "Nickname": "Pilis", "Description": "Drag out a Pili. 6 ends the game.",
        "GMNotes": "", "MaterialIndex": -1, "MeshIndex": -1,
        "Hands": False,
        "ContainedObjects": [token],
        "LuaScript": "", "LuaScriptState": "", "XmlUI": "",
    })


def build_ui():
    rows = []
    for c in COLORS:
        rows.append(f"""
      <HorizontalLayout id="row_{c}" preferredHeight="26" spacing="3" active="false">
        <Text preferredWidth="62" fontSize="13" fontStyle="Bold" color="{COLOR_HEX[c]}"
              alignment="MiddleLeft">{c}</Text>
        <Button preferredWidth="24" onClick="bidDown({c})">-</Button>
        <Text id="bid_{c}" preferredWidth="42" alignment="MiddleCenter" color="#e8c45c">-</Text>
        <Button preferredWidth="24" onClick="bidUp({c})">+</Button>
        <Text preferredWidth="10" color="#6a5a55" alignment="MiddleCenter">|</Text>
        <Button preferredWidth="24" onClick="piliDown({c})">-</Button>
        <Text id="pili_{c}" preferredWidth="42" alignment="MiddleCenter" color="#f0a090">0</Text>
        <Button preferredWidth="24" onClick="piliUp({c})">+</Button>
      </HorizontalLayout>""")

    return f"""<Defaults>
  <Button color="#8c1414" textColor="#f7f0e4" fontSize="14" fontStyle="Bold"/>
  <Text color="#e6ded2" fontSize="13"/>
</Defaults>

<Panel id="piliMain" rectAlignment="UpperLeft" offsetXY="14 -14"
       width="320" height="440" color="#160f0ef2"
       outlineSize="2 2" outline="#e8c45c">
  <VerticalLayout padding="12 12 10 12" spacing="5">

    <Text fontSize="22" fontStyle="Bold" color="#e8c45c"
          alignment="MiddleCenter" preferredHeight="30">PILI PILI</Text>

    <HorizontalLayout preferredHeight="32" spacing="6">
      <Button onClick="uiDrawMission">Mission</Button>
      <Button onClick="uiDeal">Deal</Button>
      <Button onClick="uiReveal">Reveal Bets</Button>
    </HorizontalLayout>

    <Text id="status" preferredHeight="34" fontSize="12" color="#c8bcae"
          alignment="MiddleCenter">Draw a mission to begin.</Text>

    <HorizontalLayout preferredHeight="20" spacing="3">
      <Text preferredWidth="62" fontSize="11" color="#8a7a72" alignment="MiddleLeft">SEAT</Text>
      <Text preferredWidth="90" fontSize="11" color="#8a7a72" alignment="MiddleCenter">BET</Text>
      <Text preferredWidth="10"/>
      <Text preferredWidth="90" fontSize="11" color="#8a7a72" alignment="MiddleCenter">PILIS</Text>
    </HorizontalLayout>
{''.join(rows)}

    <Text id="dealtInfo" preferredHeight="20" fontSize="11" color="#8a7a72"
          alignment="MiddleCenter">no hand dealt</Text>

    <HorizontalLayout preferredHeight="30" spacing="6">
      <Button onClick="uiEndRound" color="#3a2a28">End Round</Button>
      <Button onClick="uiNewGame" color="#3a2a28">New Game</Button>
    </HorizontalLayout>

  </VerticalLayout>
</Panel>
"""


RULES = """PILI PILI - how a round runs

Guess how many tricks you will win, then win exactly that many.

1. REVEAL A MISSION
   Press [Mission]. The card that turns over sets the round's special rule and
   prints, bottom-left, how many numbered cards each player gets.

2. DEAL
   Press [Deal]. Leftover cards stay face down beside the deck, out of play.

3. BET
   Starting with the dealer, everyone bets how many tricks they will take.
   Use the -/+ next to your colour, then press [Reveal Bets].
   The bets must NOT add up to the number of cards dealt to each player -
   there always has to be at least one loser. If the last bidder would make the
   totals match, they must pick a different number. The panel flags it if they don't.

4. PLAY TRICKS
   The dealer leads. Everyone plays one card. Highest number takes the trick
   and leads the next one. There are no suits - only the number matters.
   The Joker takes any value from 0 to 56, chosen as you play it.

5. PILIS
   Take 1 Pili for every trick you are away from your bet. Exactly right = none.
   Bet 1 and win 3? That is 2 Pilis. Use the -/+ in the panel, or drag physical
   chillies out of the Pili bag.

6. NEXT ROUND
   Press [End Round] to sweep the cards back and reshuffle, then draw a new mission.
   The moment someone hits 6 Pilis the game stops and the FEWEST Pilis wins.

FIRST GAME? Skip the missions entirely, deal 5 cards each, and go straight to betting."""

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

    # seats
    for i, c in enumerate(COLORS):
        objects.append(hand_zone(c, i, len(COLORS)))

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

    # optional physical bet markers
    cd_bid = custom_deck(urls["bid_face"], urls["bid_back"], 7, 2)
    bid_cards = [card(3, i, str(i), "Optional physical bet marker.", "PILI:BID",
                      cd_bid, POS_BIDS, (0, 180, 180)) for i in range(14)]
    objects.append(deck(3, bid_cards, "Bet Markers (optional)", "PILI:BID",
                        cd_bid, POS_BIDS))

    objects.append(pili_bag(urls["pili"]))

    # snap points for played cards, ringed around the middle
    import math
    snaps = []
    for i in range(len(COLORS)):
        th = math.radians(360.0 * i / len(COLORS))
        snaps.append({
            "Position": {"x": -4.2 * math.sin(th), "y": 1.02, "z": -4.2 * math.cos(th)},
            "Rotation": {"x": 0.0, "y": 360.0 * i / len(COLORS), "z": 0.0},
            "Tags": [],
        })
    snaps.append({"Position": {"x": POS_REVEAL[0], "y": 1.02, "z": POS_REVEAL[2]},
                  "Rotation": {"x": 0.0, "y": 0.0, "z": 0.0}, "Tags": []})

    with open(os.path.join(HERE, "global.lua"), encoding="utf-8") as fh:
        lua = fh.read()

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
        "Turns": {"Enable": False, "Type": 0, "TurnOrder": [], "Reverse": False,
                  "SkipEmpty": False, "DisableInteractions": False,
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
        "XmlUI": build_ui(),
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
    ap.add_argument("--base-url", help="host images at this URL prefix instead of local files")
    ap.add_argument("--skip-art", action="store_true", help="reuse the assets already rendered")
    args = ap.parse_args()

    with open(os.path.join(HERE, "missions.json"), encoding="utf-8") as fh:
        missions = json.load(fh)["missions"]
    if len(missions) != 36:
        print(f"note: missions.json holds {len(missions)} cards, not 36")

    if args.skip_art:
        names = {"play_face": "play_faces.png", "mission_face": "mission_faces.png",
                 "bid_face": "bid_faces.png", "play_back": "play_back.png",
                 "mission_back": "mission_back.png", "bid_back": "bid_back.png",
                 "pili": "pili_token.png"}
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
    print("images:   ", asset_dir)
    if not args.base_url:
        print("\nLocal images only load for the host. For multiplayer, upload the")
        print("assets folder somewhere public and rerun with --base-url <prefix>.")


if __name__ == "__main__":
    main()
