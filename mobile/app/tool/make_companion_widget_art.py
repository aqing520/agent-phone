#!/usr/bin/env python3
"""Render Agent Phone's neutral Android and HarmonyOS companion status art."""
from pathlib import Path

from PIL import Image, ImageDraw

APP = Path(__file__).resolve().parents[1]
OUTPUTS = (
    APP / "android/app/src/main/res/drawable-nodpi",
    APP / "ohos/entry/src/main/resources/base/media",
)


def render(state):
    image = Image.new("RGBA", (240, 240))
    draw = ImageDraw.Draw(image)
    ink = "#263a65"
    draw.rounded_rectangle((30, 65, 210, 217), radius=50, fill="#7289ed", outline=ink, width=7)
    draw.line((120, 41, 120, 65), fill=ink, width=8)
    draw.ellipse((109, 22, 131, 44), fill="#f7bd63", outline=ink, width=4)
    draw.rounded_rectangle((48, 85, 192, 181), radius=32, fill="#edf3ff")
    for x in (83, 157):
        if state == "sleeping":
            draw.arc((x-12, 111, x+12, 130), 0, 180, fill=ink, width=5)
        elif state == "happy":
            draw.arc((x-12, 110, x+12, 130), 180, 360, fill=ink, width=5)
        else:
            draw.rounded_rectangle((x-5, 111, x+5, 130), radius=5, fill=ink)
    if state == "happy":
        draw.arc((99, 132, 141, 157), 0, 180, fill=ink, width=5)
    elif state == "sleeping":
        draw.ellipse((115, 143, 125, 153), outline=ink, width=3)
    else:
        draw.rounded_rectangle((109, 143, 131, 148), radius=2, fill=ink)
    return image


if __name__ == "__main__":
    for state in ("idle", "happy", "sleeping"):
        image = render(state)
        for output in OUTPUTS:
            image.save(output / f"companion_widget_{state}.png")
