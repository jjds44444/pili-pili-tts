# Pili Pili — Tabletop Simulator mod

An unofficial fan implementation of **Pili Pili** (Ben, Martin & JB / ATM Gaming) for
Tabletop Simulator. All artwork is drawn from scratch by `art.py` — no publisher art,
photos, or rulebook text are reproduced.

## Install

```bash
python build_save.py
```

That renders the card sheets and drops `PiliPili.json` plus a `PiliPili_assets/`
folder into your Tabletop Simulator **Saves** directory. Launch TTS →
*Games → Save & Load → Pili Pili*.

Needs Python 3 and Pillow (`pip install pillow`).

### Playing with other people

Local `file:///` image paths only resolve on the machine hosting the table — everyone
else sees blank cards. Upload the contents of `PiliPili_assets/` somewhere public
(Steam Cloud, imgur, a GitHub raw URL) and rebuild pointing at it:

```bash
python build_save.py --base-url https://example.com/pilipili
```

Other flags: `--out DIR` to write somewhere else, `--skip-art` to reuse rendered sheets.

## What's on the table

| Object | |
|---|---|
| Numbered Cards | 55 cards, 1–55, plus the Joker. Colour-graded cool→hot so relative strength reads at a glance. |
| Missions | 36 cards. The number bottom-left is how many cards to deal each player. |
| Pilis | Infinite bag of chilli tokens, if you'd rather count penalties physically. |
| Bet Markers | Optional 0–13 cards, standing in for the rulebook's "Scoville scale" trick of laying out unused number cards. |

Eight seats are set up with hand zones and snap points; the panel only shows rows for
colours people are actually sitting in.

## The control panel

- **Mission** — discards the current mission, flips the next one, announces its deal count.
- **Deal** — deals that many cards to every seated player, shuffling first. If there
  aren't enough cards for the player count it deals the largest even amount it can and says so.
- **Reveal Bets** — each player sets a hidden bet with their row's `-`/`+` (shows `SET`
  to everyone else, whispers the value back to you). Reveal shows them all and
  **enforces the rule that the bets must not total the number of cards dealt** — if
  they do, it flags that the last bidder has to change.
- **Pilis** — `-`/`+` per seat. At 6 the game stops and it announces who has fewest.
- **End Round** — sweeps every numbered card back out of hands and off the table into
  one reshuffled deck.
- **New Game** — the same, plus the mission deck, and zeroes all Pilis.

Rules and credits are in the in-game notebook (`Ctrl+N`).

## Editing the missions

The rulebook (pp. 14–19) prints **17 effect types** but not the parameters of each of
the 36 physical cards — how many cards each deals, which way the arrows point, how
many cards get passed, which numbers are cursed. `missions.json` covers all 17 effects
with a plausible split of those parameters. If you have the physical deck and want it
exact, edit `missions.json` and rerun `build_save.py`.

Each entry:

```json
{"title": "Pass Left", "text": "AFTER BETTING\nPass 1 card to the player\non your LEFT.", "cards": 5, "expert": false}
```

`cards` prints bottom-left and drives the Deal button. `expert` gives the card the red
Expert frame. `\n` breaks lines on the card face.

## Files

| | |
|---|---|
| `build_save.py` | Builds the save. Start here. |
| `art.py` | Draws every card, back, and token. |
| `missions.json` | The 36 mission cards. |
| `global.lua` | Table script — dealing, betting, Pilis, cleanup. |
| `validate.py` | `python validate.py PiliPili.json` — structural check before loading. |

## Credits

Pili Pili is designed by Ben, Martin & JB and published by ATM Gaming
(<https://www.atmgaming.com>). This mod is unofficial and non-commercial. If you enjoy
it, buy the real game — it's a lovely little box.
