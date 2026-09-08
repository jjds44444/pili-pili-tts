# Pili Pili — Tabletop Simulator

An unofficial, fan-made Tabletop Simulator implementation of **Pili Pili**, the
trick-taking card game with variable missions by **Ben, Martin & JB**, published by
**[ATM Gaming](https://www.atmgaming.com)**.

Not affiliated with or endorsed by ATM Gaming. If you enjoy it, **buy the real game** —
it's a lovely little box, and this exists because the physical game is good.

![Cards](preview-cards.png)

## Install

```bash
pip install pillow numpy
python build_save.py
```

That renders the card art and writes `PiliPili.json` into your Tabletop Simulator
**Saves** folder. In TTS: **Games → Save & Load → Saves → Pili Pili**.

Card images are served from this repo, so everyone at the table sees them — no Steam
Cloud upload needed. Add `--local` to use local files instead (faster while iterating
on the art, but only you will see them).

| Flag | |
|---|---|
| `--skip-art` | Reuse `assets/`, just rebuild the save. Seconds instead of minutes. |
| `--local` | Local `file:///` images instead of the repo's hosted copies. Host-only, but instant. |
| `--out DIR` | Write somewhere other than the TTS Saves folder. |
| `--base-url URL` | Serve images from somewhere other than this repo. |

## Playing

Everything lives on the table — there's no floating menu. Sit down in a player colour;
a dibber, a trick mat and a Pili tray appear in front of your seat.

**Missions start OFF** — the rulebook's own advice for a first game. Flip the MISSIONS
tile by the mission deck to turn them on. Press the chilli **Next Round** button to
deal: with Missions off that's 5 cards each; with them on, a Mission card flips first
and sets the round's twist plus how many cards to deal.

Starting with the dealer (the gold marker), everyone bets openly on their own dibber
with `-`/`+`. The bets can't total the number of cards dealt, so there's always at
least one loser — the last to bet will find their dibber refuses the number that would
make it match.

Play tricks: highest card wins, no suits, the Joker takes any value from 0 to 56.
**Stack every trick you win on your own mat** — that's how the button knows what you
scored. Press **Next Round** again to score: it counts your mat, drops a Pili in your
tray for every trick you were off by, sweeps everything, and deals the next hand.

First to **6 Pilis** ends the game; fewest Pilis wins.

The full rulebook is on the table as a physical object near the mission deck — click
it to open, then flip through like any other TTS rulebook.

## Missions

The rulebook prints 17 mission **effect types** but not the parameters of each of the
36 physical cards — how many cards each deals, which way the arrows point, which
numbers are cursed. `missions.json` covers all 17 effects with a plausible split of
those parameters. If you have the physical deck and want it exact, edit that file and
rebuild.

## Artwork

Every card is drawn from scratch in code — no scans, photos or exports of the published
game. `glyphs.py` builds tribal glyphs compositionally from silhouettes and ink marks,
seeded per card, and roughens every contour so nothing reads as machine-drawn; `art.py`
lays out the cards. Styled after the published design, but not copied from it.

The one deliberate exception is the rulebook itself: `assets/ATM_GAMING_pilipili_RULES.pdf`
is ATM Gaming's actual published rulebook, included and hosted as-is (not redrawn) so the
in-game copy is the real thing rather than a paraphrase.

## Files

| | |
|---|---|
| `build_save.py` | Builds the TTS save. Start here. |
| `art.py` | Card layout, palette, typography. |
| `glyphs.py` | Glyph vocabulary and hand-cut edge treatment. |
| `missions.json` | The 36 mission cards. |
| `global.lua` | Table script — dealing, betting, Pilis, cleanup. |
| `validate.py` | `python validate.py PiliPili.json` — structural check before loading. |
| `preview.py` | Contact sheet of the rendered art. |

## Credits

Pili Pili is designed by **Ben, Martin & JB** and published by
**[ATM Gaming](https://www.atmgaming.com)**. All game design, rules and mission effects
are theirs. This repository contains only an independent digital implementation and
original artwork, shared for personal use.
