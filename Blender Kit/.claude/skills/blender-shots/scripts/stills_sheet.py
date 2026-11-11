"""Contact sheet of still images (to look at several frames at once, or to compare ours against a reference).

  python stills_sheet.py OUT.png [--cols 3] [--width 640] [--labels] [--side-by-side REF.png] FILE_OR_GLOB...

  FILE_OR_GLOB   image files or patterns such as "shots/*/S12-still-*.png" (quote patterns; this tool expands them itself).
                 Sorted naturally (still-2 before still-10).
  --cols N       columns in the grid (default 3)
  --width PX     width of every tile (default 640); height follows the first image's shape, others are fitted inside
  --labels       write the file name (without extension) on each tile
  --side-by-side REF.png
                 put a reference sheet above the grid (scaled to the same width), with "REFERENCE" and "OURS" tags, to compare
Prints one JSON line last: {"ok": true, "out": ..., "images": N, "size": "WxH"}.
Needs Pillow:  python -m pip install --user pillow numpy
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.normpath(os.path.join(HERE, "..", "fonts"))

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    _msg = "Pillow is missing. Run:  python -m pip install --user pillow numpy"
    if "--help" not in sys.argv and "-h" not in sys.argv:
        print(_msg, file=sys.stderr)
        print(json.dumps({"ok": False, "error": _msg}))
        raise SystemExit(2)

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")


class ToolError(Exception):
    pass


def utf8_stdio():
    """Windows pipes default to cp1252: never crash on other alphabets in the words we print."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001  (Python 3.9 has it for real files; a test's StringIO does not)
            pass


def natural_key(s):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def expand(patterns):
    files = []
    for pat in patterns:
        hits = glob.glob(pat) if any(c in pat for c in "*?[") else ([pat] if os.path.exists(pat) else [])
        if not hits:
            raise ToolError("no files match: " + pat)
        for h in hits:
            if os.path.isdir(h):
                files += [os.path.join(h, f) for f in os.listdir(h) if f.lower().endswith(IMG_EXT)]
            elif h.lower().endswith(IMG_EXT):
                files.append(h)
    seen, out = set(), []
    for f in sorted(files, key=lambda p: natural_key(p)):
        k = os.path.normcase(os.path.abspath(f))
        if k not in seen:
            seen.add(k)
            out.append(f)
    if not out:
        raise ToolError("no image files found")
    return out


def get_font(size):
    for name in ("Montserrat-Bold.ttf", "Montserrat.ttf"):
        p = os.path.join(FONT_DIR, name)
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def tag(sheet, text, x, y, font):
    d = ImageDraw.Draw(sheet)
    bb = d.textbbox((0, 0), text, font=font)
    pw, ph = bb[2] - bb[0] + 14, bb[3] - bb[1] + 10
    d.rectangle([x, y, x + pw, y + ph], fill=(0, 0, 0))
    d.text((x + 7 - bb[0], y + 5 - bb[1]), text, font=font, fill=(255, 255, 255))


def build(files, cols, width, labels):
    ims = []
    for f in files:
        try:
            ims.append(Image.open(f).convert("RGB"))
        except OSError as e:
            raise ToolError("cannot open %s (%s)" % (f, e))
    cell_h = int(round(width * ims[0].height / ims[0].width))
    cols = max(1, min(cols, len(ims)))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * cell_h), (40, 40, 40))
    font = get_font(max(12, width // 28))
    for i, (im, f) in enumerate(zip(ims, files)):
        scale = min(width / im.width, cell_h / im.height)
        sz = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
        tile = im.resize(sz, Image.LANCZOS)
        x, y = (i % cols) * width, (i // cols) * cell_h
        sheet.paste(tile, (x + (width - sz[0]) // 2, y + (cell_h - sz[1]) // 2))
        if labels:
            tag(sheet, os.path.splitext(os.path.basename(f))[0], x + 6, y + cell_h - max(26, width // 18) - 6, font)
    return sheet


def main():
    ap = argparse.ArgumentParser(description="Contact sheet of still images.", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("out", help="output PNG")
    ap.add_argument("files", nargs="+", metavar="FILE_OR_GLOB")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--labels", action="store_true")
    ap.add_argument("--side-by-side", metavar="REF.png", default=None)
    utf8_stdio()
    a = ap.parse_args()
    files = expand(a.files)
    sheet = build(files, a.cols, a.width, a.labels)
    if a.side_by_side:
        if not os.path.isfile(a.side_by_side):
            raise ToolError("reference sheet not found: " + a.side_by_side)
        ref = Image.open(a.side_by_side).convert("RGB")
        ref = ref.resize((sheet.width, max(1, int(round(ref.height * sheet.width / ref.width)))), Image.LANCZOS)
        gap = 12
        combo = Image.new("RGB", (sheet.width, ref.height + gap + sheet.height), (14, 14, 14))
        combo.paste(ref, (0, 0))
        combo.paste(sheet, (0, ref.height + gap))
        font = get_font(max(14, sheet.width // 60))
        tag(combo, "REFERENCE", 8, 8, font)
        tag(combo, "OURS", 8, ref.height + gap + 8, font)
        sheet = combo
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out)
    return {"ok": True, "out": os.path.abspath(a.out), "images": len(files), "size": "%dx%d" % sheet.size}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except ToolError as e:
        print(str(e), file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(1)
