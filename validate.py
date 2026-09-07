"""Sanity-check a generated PiliPili.json before loading it in Tabletop Simulator."""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1]
save = json.load(open(path, encoding="utf-8"))

fail = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (("  " + detail) if detail else ""))
    if not cond:
        fail.append(label)


print("top level")
for k in ["SaveName", "Table", "ObjectStates", "LuaScript", "XmlUI", "TabStates", "SnapPoints"]:
    check(f"has {k}", k in save)

guids = []


def walk(o):
    guids.append(o.get("GUID"))
    for c in o.get("ContainedObjects", []):
        walk(c)


for o in save["ObjectStates"]:
    walk(o)

print("\nobjects")
print(f"  {len(guids)} objects total")
check("all objects have a GUID", all(guids))
check("GUIDs unique", len(set(guids)) == len(guids),
      f"{len(guids) - len(set(guids))} duplicates")

zones = [o for o in save["ObjectStates"] if o["Name"] == "HandTrigger"]
check("8 hand zones", len(zones) == 8)
check("hand zones have distinct colours", len({z["FogColor"] for z in zones}) == len(zones))

print("\ndecks")
expected = {"Numbered Cards": 56, "Missions": 36, "Bet Markers (optional)": 14}
seen = {}
for o in save["ObjectStates"]:
    if o["Name"] != "DeckCustom":
        continue
    key, cd = next(iter(o["CustomDeck"].items()))
    did, w, h = int(key), cd["NumWidth"], cd["NumHeight"]
    cards = o["ContainedObjects"]
    seen[o["Nickname"]] = len(cards)
    print(f"  {o['Nickname']}: {len(cards)} cards on a {w}x{h} sheet "
          f"({os.path.basename(cd['FaceURL'])})")
    check("  DeckIDs match contained cards",
          o["DeckIDs"] == [c["CardID"] for c in cards])
    check("  card ids inside the sheet",
          all(did * 100 <= i < did * 100 + w * h for i in o["DeckIDs"]))
    check("  cards fit the sheet", len(cards) <= w * h)
    check("  every card carries the deck's GMNotes tag",
          {c["GMNotes"] for c in cards} == {o["GMNotes"]})
    check("  every card references the same CustomDeck id",
          all(list(c["CustomDeck"]) == [key] for c in cards))

for name, n in expected.items():
    check(f"{name} has {n} cards", seen.get(name) == n, f"got {seen.get(name)}")

print("\nimages")
urls = set()
for o in save["ObjectStates"]:
    for cd in o.get("CustomDeck", {}).values():
        urls.add(cd["FaceURL"])
        urls.add(cd["BackURL"])
    if "CustomImage" in o:
        urls.add(o["CustomImage"]["ImageURL"])
    for c in o.get("ContainedObjects", []):
        if "CustomImage" in c:
            urls.add(c["CustomImage"]["ImageURL"])
for u in sorted(urls):
    if u.startswith("file:///"):
        local = u[len("file:///"):]
        check(f"  {os.path.basename(local)} exists", os.path.isfile(local))
    else:
        print(f"  (remote) {u}")

print("\nscripting")
try:
    ET.fromstring("<root>" + save["XmlUI"] + "</root>")
    check("XmlUI is well-formed", True)
except ET.ParseError as e:
    check("XmlUI is well-formed", False, str(e))

lua = save["LuaScript"]
handlers = set(re.findall(r'onClick="([A-Za-z_]+)', save["XmlUI"]))
for h in sorted(handlers):
    check(f"  Lua defines {h}()", re.search(r"function\s+" + h + r"\s*\(", lua) is not None)

ui_ids = set(re.findall(r'id="([A-Za-z_0-9]+)"', save["XmlUI"]))
for ref in sorted(set(re.findall(r'UI\.set\w+\("([A-Za-z_]+)"', lua))):
    if "_" in ref:
        continue
    check(f"  UI id '{ref}' exists in XmlUI", ref in ui_ids)
for c in ["Red", "Orange", "Yellow", "Green", "Teal", "Blue", "Purple", "White"]:
    for pre in ["row_", "bid_", "pili_"]:
        check(f"  UI id '{pre}{c}' exists", pre + c in ui_ids)

print("\nmission deal counts")
miss = next(o for o in save["ObjectStates"] if o["Nickname"] == "Missions")
counts = []
for c in miss["ContainedObjects"]:
    m = re.search(r"\[deal (\d+)\]", c["Description"])
    counts.append(int(m.group(1)) if m else None)
check("every mission prints a deal count", all(counts))
print(f"  range {min(counts)}-{max(counts)}; 8 players would need "
      f"{max(counts) * 8} of 56 cards at the top end")
check("max deal works for 6 players", max(counts) * 6 <= 56)

print()
if fail:
    print(f"{len(fail)} CHECK(S) FAILED")
    sys.exit(1)
print("all checks passed")
