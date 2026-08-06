#!/usr/bin/env python3
"""Generate the 944S boot splash image.

    python3 make-splash.py splash.png

SQUARE on purpose. Plymouth draws the same image on every output and the
theme scales it to FIT, so a square canvas lands well on both panels the car
has: centred at 720x720 on the 1920x720 bar, and filling the 480x480 round
gauge. A wide image would shrink to a sliver on the round one.

Run on the Mac (needs Pillow and the macOS DIN faces), then commit the PNG —
the Pi never runs this.
"""
import sys
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
BLACK = (0, 0, 0)
WHITE = (238, 238, 238)
RED = (213, 0, 28)          # Guards Red
GREY = (122, 122, 122)

TITLE_FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
LABEL_FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"


def tracked(draw, text, font, tracking):
    """Width of `text` drawn with extra letterspacing."""
    return sum(draw.textlength(c, font=font) for c in text) + tracking * (len(text) - 1)


def draw_tracked(draw, xy, text, font, tracking, fill):
    x, y = xy
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += draw.textlength(c, font=font) + tracking


def main(out):
    img = Image.new("RGB", (SIZE, SIZE), BLACK)
    d = ImageDraw.Draw(img)

    title = ImageFont.truetype(TITLE_FONT, 460)
    label = ImageFont.truetype(LABEL_FONT, 40)

    # "944S" — measured off its ink box, not the font metrics, so the optical
    # centre is right regardless of the face's ascender padding.
    box = d.textbbox((0, 0), "944S", font=title)
    tw, th = box[2] - box[0], box[3] - box[1]
    tx = (SIZE - tw) / 2 - box[0]
    ty = SIZE * 0.44 - th / 2 - box[1]
    d.text((tx, ty), "944S", font=title, fill=WHITE)

    # Hairline under the wordmark, the width of the wordmark.
    rule_y = ty + box[3] + 46
    d.rectangle([(SIZE - tw) / 2, rule_y, (SIZE + tw) / 2, rule_y + 5], fill=RED)

    cap, track = "CLIMATE CONTROL", 14
    cw = tracked(d, cap, label, track)
    draw_tracked(d, ((SIZE - cw) / 2, rule_y + 40), cap, label, track, GREY)

    img.save(out)
    print(f"wrote {out} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "splash.png")
