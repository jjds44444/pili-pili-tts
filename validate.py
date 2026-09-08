"""Sanity-check a generated PiliPili.json before loading it in Tabletop Simulator."""
import json
import os
import re
import sys
import urllib.request
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
check(f"{len(zones)} hand zones present", len(zones) >= 2)
check("hand zones have distinct colours", len({z["FogColor"] for z in zones}) == len(zones))

print("\ndecks")
expected = {"Numbered Cards": 56, "Missions": 36}
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
pdf_urls = set()
for o in save["ObjectStates"]:
    for cd in o.get("CustomDeck", {}).values():
        urls.add(cd["FaceURL"])
        urls.add(cd["BackURL"])
    if "CustomImage" in o:
        urls.add(o["CustomImage"]["ImageURL"])
    if "CustomPDF" in o:
        pdf_urls.add(o["CustomPDF"]["PDFUrl"])
    for c in o.get("ContainedObjects", []):
        if "CustomImage" in c:
            urls.add(c["CustomImage"]["ImageURL"])


def check_url(u, expect_prefixes):
    if u.startswith("file:///"):
        local = u[len("file:///"):]
        check(f"  {os.path.basename(local)} exists", os.path.isfile(local))
        return
    # A save that points at a 404 loads fine and shows a blank card (or, for
    # a PDF, an object that does nothing when clicked) - this is the failure
    # TTS will not tell you about, so actually fetch it. raw.githubusercontent
    # serves PDFs as application/octet-stream rather than application/pdf
    # (confirmed: real %PDF bytes, exact byte count, just an untagged content
    # type) - checked prefixes are a tuple so that quirk doesn't read as a
    # failure here.
    name = u.rsplit("/", 1)[-1]
    try:
        req = urllib.request.Request(u, method="HEAD",
                                     headers={"User-Agent": "pili-pili-validate"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get("Content-Type", "")
            check(f"  {name} reachable ({ctype})",
                  r.status == 200 and ctype.startswith(expect_prefixes),
                  f"HTTP {r.status}")
    except Exception as e:                                      # noqa: BLE001
        check(f"  {name} reachable", False, f"{type(e).__name__}: {e}")


for u in sorted(urls):
    check_url(u, "image/")
for u in sorted(pdf_urls):
    check_url(u, ("application/pdf", "application/octet-stream"))

print("\nrequired fields")
# TTS writes these on every object it serialises. Omitting one makes the save
# fail to load with a bare "Object reference not set to an instance of an
# object" and no indication of which object is at fault.
ALWAYS = ["Name", "Transform", "Nickname", "Description", "GMNotes",
          "ColorDiffuse", "Locked", "Grid", "Snap", "Tooltip",
          "LuaScript", "LuaScriptState", "XmlUI", "GUID"]
missing = {}
for o in save["ObjectStates"]:
    for k in ALWAYS:
        if k not in o:
            missing.setdefault(o["Name"], set()).add(k)
for name in sorted({o["Name"] for o in save["ObjectStates"]}):
    check(f"  {name} has every required field", name not in missing,
          ", ".join(sorted(missing.get(name, []))))

print("\nlua")
try:
    import lupa
    try:
        lupa.LuaRuntime().compile(save["LuaScript"])
        check("  table script compiles", True)
    except Exception as e:                                      # noqa: BLE001
        check("  table script compiles", False, str(e))
except ImportError:
    print("  skipped (pip install lupa to syntax-check the table script)")

print("\nin-world controls")
seats = [o["FogColor"] for o in save["ObjectStates"] if o["Name"] == "HandTrigger"]
notes = {}
for o in save["ObjectStates"]:
    n = o.get("GMNotes", "")
    if n.startswith("PILI:"):
        notes.setdefault(n, 0)
        notes[n] += 1

for seat in seats:
    for pre in ("PILI:DIBBER:", "PILI:TRICKS:", "PILI:PILIS:",
                "PILI:MAT:", "PILI:TRAY:"):
        check(f"  {pre}{seat}", notes.get(pre + seat) == 1)
for single in ("PILI:BUTTON", "PILI:DEALER", "PILI:BAG", "PILI:MTOGGLE"):
    check(f"  exactly one {single}", notes.get(single) == 1)

check("turn system enabled", save["Turns"]["Enable"] is True)
# order lives in the injected SEAT_ORDER, not the save's TurnOrder
injected = re.search(r"SEAT_ORDER\s*=\s*\{([^}]*)\}", save["LuaScript"])
check("SEAT_ORDER injected into the script", injected is not None)
if injected:
    order = re.findall(r'"([A-Za-z]+)"', injected.group(1))
    check("SEAT_ORDER covers every seat exactly once",
          sorted(order) == sorted(seats), f"{order}")
check("no leftover floating UI", save["XmlUI"].strip() == "")

print("\nscripting")
lua = save["LuaScript"]
# every click_function named in the script must actually exist in it
for fn in sorted(set(re.findall(r'click_function\s*=\s*"([A-Za-z_]+)"', lua))):
    check(f"  Lua defines {fn}()",
          re.search(r"function\s+" + fn + r"\s*\(", lua) is not None)
for fn in ("nextRound", "bidUp", "bidDown", "scoreRound", "passDealer"):
    check(f"  Lua defines {fn}()",
          re.search(r"function\s+" + fn + r"\s*\(", lua) is not None)

# tags the script looks for must match the tags the save actually writes
for tag in ("PILI:PLAY", "PILI:MISSION", "PILI:TOKEN"):
    check(f"  tag {tag} used by both", tag in lua and any(
        tag == o.get("GMNotes") or any(c.get("GMNotes") == tag
                                       for c in o.get("ContainedObjects", []))
        for o in save["ObjectStates"]))

print("\nmission deal counts")
miss = next(o for o in save["ObjectStates"] if o["Nickname"] == "Missions")
counts = []
for c in miss["ContainedObjects"]:
    m = re.search(r"\[deal (\d+)\]", c["Description"])
    counts.append(int(m.group(1)) if m else None)
check("every mission prints a deal count", all(counts))
print(f"  range {min(counts)}-{max(counts)}")
n_seats = len(seats)
check(f"max deal works for {n_seats} players",
      max(counts) * n_seats <= 56, f"needs {max(counts) * n_seats} of 56")

print()
if fail:
    print(f"{len(fail)} CHECK(S) FAILED")
    sys.exit(1)
print("all checks passed")
