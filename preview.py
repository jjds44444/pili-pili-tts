"""Render a contact sheet of the generated cards, for eyeballing the art."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import art  # noqa: E402

A = art.ASSETS
CW, CH = art.CARD_W, art.CARD_H


def cell(img, i, cols, cw=CW, ch=CH):
    return img.crop(((i % cols) * cw, (i // cols) * ch,
                     (i % cols) * cw + cw, (i // cols) * ch + ch))


def main(out):
    play = Image.open(os.path.join(A, "play_faces.png"))
    miss = Image.open(os.path.join(A, "mission_faces.png"))

    cols = 7
    sheet = Image.new("RGB", (CW * cols, CH * 3), (18, 14, 14))
    for j, i in enumerate([0, 10, 22, 33, 44, 54, 55]):
        sheet.paste(cell(play, i, 8), (j * CW, 0))
    for j, i in enumerate([0, 7, 9, 13, 15, 17, 18]):
        sheet.paste(cell(miss, i, 6), (j * CW, CH))
    for j, i in enumerate([19, 22, 24, 28, 31, 33, 35]):
        sheet.paste(cell(miss, i, 6), (j * CW, CH * 2))

    extras = Image.new("RGB", (CW * cols, CH), (18, 14, 14))
    extras.paste(Image.open(os.path.join(A, "play_back.png")), (0, 0))
    extras.paste(Image.open(os.path.join(A, "mission_back.png")), (CW, 0))
    tok = Image.open(os.path.join(A, "pili_token.png")).convert("RGB").resize((CH - 80, CH - 80))
    extras.paste(tok, (int(CW * 2.1), 40))
    for j, name in enumerate(("dibber.png", "round_button.png")):
        im = Image.open(os.path.join(A, name)).convert("RGB")
        im = im.resize((int(CW * 1.1), int(CW * 1.1 * im.height / im.width)))
        extras.paste(im, (int(CW * (3.1 + j * 1.3)), int(CH * 0.3)))
    dl = Image.open(os.path.join(A, "dealer.png")).convert("RGB").resize((CH - 200, CH - 200))
    extras.paste(dl, (int(CW * 5.8), 100))

    full = Image.new("RGB", (CW * cols, CH * 4), (18, 14, 14))
    full.paste(sheet, (0, 0))
    full.paste(extras, (0, CH * 3))
    full = full.resize((full.width // 3, full.height // 3), Image.LANCZOS)
    full.save(out, "PNG", optimize=True)
    print(out, full.size)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         os.path.join(os.path.dirname(A), "preview.png"))
