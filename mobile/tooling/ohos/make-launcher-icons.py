#!/usr/bin/env python3
"""Render HarmonyOS shortcut icons from Android's shortcut resources.

  python3 tooling/ohos/make-launcher-icons.py

Launcher app icons (default and alternates) are instead generated across all
platforms by `python3 app/tool/make_brand_mark.py`.
Shortcut layers are 1024 px: a full-bleed background and a transparent
foreground. Needs rsvg-convert and magick.
"""
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID_RES = ROOT / 'app/android/app/src/main/res'
ENTRY_RES = ROOT / 'app/ohos/entry/src/main/resources'
NS = '{http://schemas.android.com/apk/res/android}'
SIZE = 1024
# The shortcut guide's foreground: shown at 450 px on the 1024 px layer.
SHORTCUT_GLYPH = 450


def render(svg, out):
    """Keeps the PNGs small: the layers are flat colours and smooth gradients."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.png') as raw:
        subprocess.run(['rsvg-convert', '-w', str(SIZE), '-h', str(SIZE), '-o', raw.name], input=svg.encode(), check=True)
        subprocess.run(['magick', raw.name, '-strip', '-define', 'png:compression-level=9', str(out)], check=True)


def layered(path, background, foreground):
    path.write_text(json.dumps({'layered-image': {
        'background': f'$media:{background}', 'foreground': f'$media:{foreground}',
    }}, indent=2) + '\n')


def android_colour(res_dir, name):
    """`#FFRRGGBB` of a <color> in res_dir/entry_colors.xml, as `#RRGGBB`."""
    root = ET.parse(ANDROID_RES / res_dir / 'entry_colors.xml').getroot()
    return '#' + next(c.text for c in root.findall('color') if c.get('name') == name)[3:]


def shortcuts():
    """新对话 and 语音输入: Android's glyphs and colours (values, values-night)."""
    scale = SHORTCUT_GLYPH / 24
    inset = (SIZE - SHORTCUT_GLYPH) / 2
    for theme, res_dir in (('base', 'values'), ('dark', 'values-night')):
        media = ENTRY_RES / theme / 'media'
        fill = android_colour(res_dir, 'shortcut_icon_background')
        render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}"><rect width="{SIZE}" height="{SIZE}" fill="{fill}"/></svg>',
               media / 'shortcut_background.png')
        glyph = android_colour(res_dir, 'shortcut_icon_glyph')
        for name in ('new_chat', 'voice'):
            vector = ET.parse(ANDROID_RES / f'drawable/ic_shortcut_{name}_glyph.xml').getroot()
            data = vector.find('group/path').get(f'{NS}pathData')
            render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">'
                   f'<g transform="translate({inset} {inset}) scale({scale})"><path fill="{glyph}" d="{data}"/></g></svg>',
                   media / f'shortcut_{name}_foreground.png')
    for name in ('new_chat', 'voice'):
        layered(ENTRY_RES / f'base/media/shortcut_{name}.json', 'shortcut_background', f'shortcut_{name}_foreground')


if __name__ == '__main__':
    shortcuts()
