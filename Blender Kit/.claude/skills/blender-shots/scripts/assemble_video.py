"""Finish a shot: burn in captions, labels and HUD text, mix voice + synthesized music + sound effects, write the final MP4.

  python assemble_video.py spec.json [--check] [--overwrite]

Paths in the spec are relative to the spec file's folder. Every key is optional except "video" and "out":

  {"video": "shot.mp4", "out": "shot-final.mp4",
   "voice": "vo-paced.wav", "voice_gain": 0.95,
   "captions": {"style": "pop",                      # "pop" (pops in big, settles) or "none"
                "words": "words-paced.json",          # [["word", start, end], ...]  -> automatic captions
                "max_words": 2,                       # words per caption; a caption also breaks after . , ! ? ; :
                "groups": [[0.0, "Old"], [0.31, "railroads"]],   # OR explicit captions: [start_seconds, "text"]; each holds until the next
                "font": "Montserrat-Bold", "size": 84, "y": 0.66, "stroke": 9, "upper": false},
   "labels": [{"t0": 2.35, "t1": 4.15, "text": "TRITON", "x": 250, "y": 590, "size": 64, "color": "#5FD3F3",
               "font": "Anton-Regular", "spacing": 10, "align": "center"}],       # fades in and out, drifts up 8 px
   "hud": [{"t0": 13.95, "t1": 16.3, "lines": ["VOYAGER 2", "DATE: 1989-08-25"], "x": 90, "y": 80, "size": 30,
            "font": "ShareTechMono-Regular", "brackets": true, "type_on": 0.6}],   # lines type on; thin corner brackets
   "music": {"preset": "drone", "gain": 0.16, "swell": [23.4, 28.0]},            # "none", "drone", "pulse"
   "sfx": [{"t": 27.3, "kind": "hit", "gain": 0.45}, {"t": 8.44, "kind": "groan", "gain": 0.22},
           {"t": 0.12, "kind": "saw", "gain": 0.1, "count": 5, "every": 0.42}, {"t": 4.4, "kind": "sizzle", "gain": 0.05, "dur": 1.6},
           {"t": 2.0, "kind": "whoosh", "gain": 0.12}, {"t": 3.0, "kind": "click", "gain": 0.1}],
   "fade_out": 0.8}                                  # seconds: picture to black and sound to silence at the very end

x / y of labels and HUD are pixels of the video, or fractions of the width / height when 1.0 or less. Fonts are looked up in the
skill's fonts folder (../fonts) by name; a missing font falls back to Montserrat-Bold with a note. All sound is synthesized with
numpy (no sound files, no rights issues). Any video size works (vertical or horizontal). Output: H.264 yuv420p (CRF 17, slow) +
AAC 192k, the same length as the input video. --check validates EVERYTHING a real run needs (files exist, colours, sfx kinds, music
preset, numbers, fonts) and prints the plan without rendering. Colours: #RRGGBB or white, black, red, orange, yellow, green, cyan, blue,
purple, magenta, pink, gray. An existing "out" file is refused unless --overwrite is passed (use it only when re-running the same
piece); an input file (video, voice, words) is never overwritten. The encode goes to a temporary file next to "out" that replaces it
only on success, so a failed run leaves no half-written file.
Frames stream through Pillow (decode pipe, draw, encode pipe), so memory stays flat. Needs Pillow and numpy:
  python -m pip install --user pillow numpy
Prints one JSON line last: {"ok": true, "out": ..., "duration_s": ..., "size": ..., "fps": ..., "frames": ...}.
"""
import argparse
import bisect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from _studio_env import ensure_tool_path, install_stop_handlers
    ensure_tool_path()
    install_stop_handlers()
except Exception:  # noqa: BLE001
    pass

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    _msg = "Pillow and numpy are required. Run:  python -m pip install --user pillow numpy"
    if "--help" not in sys.argv and "-h" not in sys.argv:
        print(_msg, file=sys.stderr)
        print(json.dumps({"ok": False, "error": _msg}))
        raise SystemExit(2)
    np = None

SR = 48000
THREADS = "4"
FONT_DIR = os.path.normpath(os.path.join(HERE, "..", "fonts"))
CHILDREN = []
NOTES = []


class ToolError(Exception):
    pass


def utf8_stdio():
    """Windows pipes default to cp1252: never crash on other alphabets in text we print."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001  (Python 3.9 has it for real files; a test's StringIO does not)
            pass


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def note(msg):
    if msg not in NOTES:
        NOTES.append(msg)
        log("NOTE: " + msg)


def popen_kw():
    if os.name == "nt":
        return {"creationflags": 0x00004000}
    return {"preexec_fn": lambda: os.nice(5)}


def stop_children():
    for p in list(CHILDREN):
        try:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


def run_quick(cmd, timeout=60):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kw())
    CHILDREN.append(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise ToolError("timed out: " + os.path.basename(cmd[0]))
    finally:
        if p in CHILDREN:
            CHILDREN.remove(p)
    return p.returncode, out, err


# ---------------------------------------------------------------- video info

def probe_video(path):
    code, out, err = run_quick(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,duration:stream_side_data=rotation:format=duration",
                                "-of", "json", path])
    if code != 0:
        raise ToolError("ffprobe could not read " + path + ": " + err.decode("utf-8", "replace").strip()[-300:])
    d = json.loads(out or b"{}")
    if not d.get("streams"):
        raise ToolError("no video stream in " + path)
    s = d["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    for sd in s.get("side_data_list") or []:
        if "rotation" in sd and abs(int(float(sd["rotation"]))) % 180 == 90:
            w, h = h, w
    fps_str = "30/1"
    for key in ("avg_frame_rate", "r_frame_rate"):
        v = str(s.get(key, "0/1"))
        try:
            a, b = v.split("/")
            if float(b) and float(a) / float(b) > 0:
                fps_str = v
                break
        except ValueError:
            continue
    a, b = fps_str.split("/")
    fps = float(a) / float(b)
    dur = None
    for v in (s.get("duration"), (d.get("format") or {}).get("duration")):
        try:
            dur = float(v)
            break
        except (TypeError, ValueError):
            continue
    if not dur:
        raise ToolError("could not read the video length")
    frames = None
    try:
        frames = int(s.get("nb_frames"))
    except (TypeError, ValueError):
        pass
    if not frames or abs(frames / fps - dur) > 0.5:
        frames = int(round(dur * fps))
    return {"w": w, "h": h, "fps": fps, "fps_str": fps_str, "frames": frames, "dur": dur}


# ---------------------------------------------------------------- fonts

_FONT_CACHE = {}
_FONT_PATHS = {}
MONO_SYSTEM = ["C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf",
               "/Library/Fonts/Courier New.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def font_path(name):
    """Resolve a font name to a file: the skill's fonts folder first, then (for mono names) a system monospace, then Montserrat-Bold."""
    key = name or "Montserrat-Bold"
    if key in _FONT_PATHS:
        return _FONT_PATHS[key]
    found = None
    if os.path.isabs(key) and os.path.isfile(key):
        found = key
    else:
        stem = re.sub(r"\.(ttf|otf|ttc)$", "", key, flags=re.I)
        try:
            files = os.listdir(FONT_DIR)
        except OSError:
            files = []
        for f in files:
            if f.lower() in (stem.lower() + ".ttf", stem.lower() + ".otf"):
                found = os.path.join(FONT_DIR, f)
                break
        if not found:
            for f in sorted(files):
                if f.lower().endswith((".ttf", ".otf")) and f.lower().startswith(stem.lower()):
                    found = os.path.join(FONT_DIR, f)
                    break
    if not found and re.search(r"mono|consol|courier|menlo|code", key, re.I):
        for cand in MONO_SYSTEM:
            if os.path.isfile(cand):
                found = cand
                note("font %s is not in the fonts folder; using the system monospace font %s" % (key, os.path.basename(cand)))
                break
    if not found:
        fallback = os.path.join(FONT_DIR, "Montserrat-Bold.ttf")
        if key != "Montserrat-Bold":
            note("font %s was not found in %s; using Montserrat-Bold" % (key, FONT_DIR))
        found = fallback if os.path.isfile(fallback) else None
    _FONT_PATHS[key] = found
    return found


def get_font(name, size):
    size = max(6, int(size))
    path = font_path(name)
    k = (path, size)
    if k not in _FONT_CACHE:
        try:
            _FONT_CACHE[k] = ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except OSError:
            _FONT_CACHE[k] = ImageFont.load_default()
    return _FONT_CACHE[k]


NAMED_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (230, 50, 50), "orange": (255, 140, 0), "yellow": (250, 220, 40),
                "green": (60, 200, 90), "cyan": (95, 211, 243), "blue": (50, 110, 240), "purple": (150, 80, 220),
                "magenta": (230, 60, 200), "pink": (255, 130, 180), "gray": (160, 160, 160), "grey": (160, 160, 160)}


def parse_color(c, default=(255, 255, 255)):
    if c is None:
        return default
    if isinstance(c, (list, tuple)):
        try:
            if len(c) >= 3 and all(0 <= int(v) <= 255 for v in c[:3]):
                return tuple(int(v) for v in c[:3])
        except (TypeError, ValueError):
            pass
        raise ToolError("bad color %r (three numbers 0-255)" % (c,))
    if str(c).strip().lower() in NAMED_COLORS:
        return NAMED_COLORS[str(c).strip().lower()]
    m = re.match(r"^#?([0-9a-fA-F]{6})$", str(c).strip())
    if not m:
        raise ToolError("bad color %r (use #RRGGBB or a name: %s)" % (c, ", ".join(sorted(NAMED_COLORS))))
    v = m.group(1)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def px(v, total):
    """Pixels, or a fraction of `total` when the number is 1.0 or less."""
    v = float(v)
    return v * total if 0 < v <= 1.0 else v


# ---------------------------------------------------------------- audio synthesis (numpy only)

RNG = None


def rng():
    global RNG
    if RNG is None:
        RNG = np.random.default_rng(4)
    return RNG


def env(n, a, r):
    e = np.ones(n)
    ai, ri = min(int(a * SR), n // 2), min(int(r * SR), n // 2)
    if ai > 0:
        e[:ai] = np.linspace(0, 1, ai)
    if ri > 0:
        e[-ri:] *= np.linspace(1, 0, ri)
    return e


def bandnoise(dur, lo, hi):
    n = max(2, int(dur * SR))
    x = rng().standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    y = np.fft.irfft(X, n)
    return y / (np.abs(y).max() + 1e-9)


def lowpass(x, fc):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[f > fc] = 0
    return np.fft.irfft(X, len(x))


def norm(x):
    return x / (np.abs(x).max() + 1e-9)


def sfx_hit(**_):
    n = int(2.5 * SR)
    tt = np.arange(n) / SR
    s = np.sin(2 * np.pi * (48 - 14 * tt) * tt) * np.exp(-tt * 2.2) + 0.4 * lowpass(rng().standard_normal(n), 300) * np.exp(-tt * 3)
    return norm(s)


def sfx_groan(**_):
    t = np.arange(int(0.9 * SR)) / SR
    g = np.sin(2 * np.pi * (220 * t - 70 * t * t)) * np.exp(-t * 3.0) + 0.5 * bandnoise(0.9, 60, 400) * np.exp(-t * 4)
    return norm(g)


def sfx_saw(**_):
    """One back-and-forth saw stroke pair (two strokes 0.21 s apart)."""
    n = int(0.17 * SR)
    out = np.zeros(int(0.21 * SR) + n)
    out[:n] += bandnoise(0.17, 2500, 7000) * env(n, 0.02, 0.08)
    out[int(0.21 * SR):] += 0.8 * bandnoise(0.17, 1800, 5000) * env(n, 0.02, 0.08)
    return out


def sfx_sizzle(dur=1.6, **_):
    dur = max(0.2, float(dur))
    n = int(dur * SR)
    return bandnoise(dur, 4000, 11000) * env(n, dur * 0.25, dur * 0.31) * (0.6 + 0.4 * np.sin(np.linspace(0, 25 * dur, n)))


def sfx_whoosh(dur=0.7, **_):
    dur = max(0.2, float(dur))
    n = int(dur * SR)
    x = np.linspace(0, 1, n)
    low, mid, high = bandnoise(dur, 150, 1200), bandnoise(dur, 900, 4000), bandnoise(dur, 3000, 9000)
    w_low = np.clip(1 - x * 2.2, 0, 1)
    w_mid = np.clip(1 - np.abs(x - 0.45) * 3.0, 0, 1)
    w_high = np.clip((x - 0.35) * 2.2, 0, 1)
    shape = np.sin(np.pi * np.clip(x * 1.15, 0, 1)) ** 2
    return norm((low * w_low + mid * w_mid + high * w_high * 0.7) * shape)


def sfx_click(**_):
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return norm(bandnoise(0.03, 1500, 9000) * np.exp(-t * 180) + 0.5 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 220))


SFX = {"hit": (sfx_hit, 0.45), "groan": (sfx_groan, 0.22), "saw": (sfx_saw, 0.10), "sizzle": (sfx_sizzle, 0.05),
       "whoosh": (sfx_whoosh, 0.12), "click": (sfx_click, 0.10)}


def music_bed(preset, n, music):
    """Returns the bed (before gain) as float array of n samples, peak about 1."""
    if preset in (None, "none", ""):
        return None
    t = np.arange(n) / SR
    D = n / SR
    fin, fout = min(2.0, D * 0.2), min(1.2, D * 0.12)
    if preset == "drone":
        drone = sum(a * np.sin(2 * np.pi * f * t + p) for f, a, p in ((55.0, 1.0, 0), (82.4, 0.6, 1), (110.0, 0.35, 2), (164.8, 0.18, 3)))
        drone = drone * (0.75 + 0.25 * np.sin(2 * np.pi * t / 7.5))
        blk = lowpass(rng().standard_normal(int(SR * 20)), 500)                 # periodic block: tiles without a seam
        wind = np.tile(blk / np.abs(blk).max(), int(np.ceil(n / len(blk))))[:n]
        bed = drone / np.abs(drone).max() * 0.6 + wind * 0.25 * (0.6 + 0.4 * np.sin(2 * np.pi * t / 11))
        bed = bed * np.clip(t / max(fin, 1e-3), 0, 1) * np.clip((D - t) / max(fout, 1e-3), 0, 1)
        sw = (music or {}).get("swell")
        if sw and len(sw) == 2 and sw[1] > sw[0]:
            ramp = min(3.5, (sw[1] - sw[0]) * 0.75)
            swell = np.clip((t - sw[0]) / ramp, 0, 1) * np.clip((sw[1] - t) / 0.6, 0, 1)
            bed = bed * (1 + 0.8 * swell)
        return bed
    if preset == "pulse":
        beat = 60.0 / 90.0
        kt = np.arange(int(0.4 * SR)) / SR
        thump = np.sin(2 * np.pi * np.cumsum(45 + 55 * np.exp(-kt * 28)) / SR) * np.exp(-kt * 9)
        bed = np.zeros(n)
        b = 0.0
        k = 0
        while b < D:
            i = int(b * SR)
            amp = 1.0 if k % 4 == 0 else 0.75
            seg = thump[:max(0, n - i)]
            bed[i:i + len(seg)] += amp * seg
            b += beat
            k += 1
        ph = np.mod(t, beat)
        gate = 0.5 + 0.5 * np.exp(-ph * 4)
        pad = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((110.0, 1.0), (130.8, 0.8), (164.8, 0.7))) * gate
        bed = norm(bed) * 0.8 + norm(pad) * 0.35
        return bed * np.clip(t / max(fin, 1e-3), 0, 1) * np.clip((D - t) / max(fout, 1e-3), 0, 1)
    raise ToolError("unknown music preset %r (use none, drone or pulse)" % preset)


def read_audio(path, n):
    """Decode any audio file to mono float at SR, padded or trimmed to n samples."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-threads", THREADS, "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kw())
    CHILDREN.append(p)
    try:
        raw, err = p.communicate(timeout=300)
    finally:
        if p in CHILDREN:
            CHILDREN.remove(p)
    if p.returncode != 0:
        raise ToolError("could not read the voice file: " + err.decode("utf-8", "replace").strip()[-300:])
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    out = np.zeros(n)
    out[:min(n, len(x))] = x[:n]
    return out


def build_audio(spec, base, n, D):
    """Mix voice + music + sfx -> float mono array of n samples (peak limited to about 0.92)."""
    mix = np.zeros(n)
    used = False
    if spec.get("voice"):
        vp = os.path.join(base, spec["voice"])
        if not os.path.isfile(vp):
            raise ToolError("voice file not found: " + vp)
        mix += read_audio(vp, n) * float(spec.get("voice_gain", 0.95))
        used = True
    music = spec.get("music") or {}
    if music and music.get("preset") not in (None, "none", ""):
        preset = music.get("preset")
        bed = music_bed(preset, n, music)
        mix += bed * float(music.get("gain", 0.16 if preset == "drone" else 0.2))
        used = True
    for i, s in enumerate(spec.get("sfx") or []):
        kind = s.get("kind")
        if kind not in SFX:
            raise ToolError("sfx %d: unknown kind %r (use %s)" % (i, kind, ", ".join(sorted(SFX))))
        fn, dg = SFX[kind]
        gain = float(s.get("gain", dg))
        count, every = max(1, int(s.get("count", 1))), float(s.get("every", 0.4))
        for k in range(count):
            t0 = float(s["t"]) + k * every
            if t0 < 0 or t0 >= D:
                continue
            sig = fn(dur=s.get("dur", 1.6 if kind == "sizzle" else 0.7))
            j = int(t0 * SR)
            seg = sig[:n - j]
            mix[j:j + len(seg)] += gain * seg
            used = True
    peak = float(np.abs(mix).max()) if used else 0.0
    if peak > 0:
        mix = mix / max(1.0, peak / 0.92)
    fo = float(spec.get("fade_out") or 0)
    if fo > 0:
        m = min(n, int(fo * SR))
        mix[n - m:] *= np.linspace(1, 0, m)
    return mix


def write_wav(path, x):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


# ---------------------------------------------------------------- overlays

def fade(t, t0, t1, d=0.35):
    if t < t0 or t > t1:
        return 0.0
    return max(0.0, min(1.0, (t - t0) / d, (t1 - t) / d))


def draw_spaced(d, xy, text, font, fill, spacing, align="left"):
    if spacing:
        widths = [d.textlength(ch, font=font) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
    else:
        total = d.textlength(text, font=font)
    x, y = xy
    if align == "center":
        x -= total / 2
    elif align == "right":
        x -= total
    if not spacing:
        d.text((x, y), text, font=font, fill=fill)
        return
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill)
        x += w + spacing


def auto_groups(words, max_words):
    """[(start, text, last_word_end)] from [[word, start, end], ...]."""
    groups, cur = [], []

    def flush():
        if cur:
            groups.append((cur[0][1], " ".join(w for w, _, _ in cur), cur[-1][2]))
            cur.clear()
    for w, s, e in words:
        cur.append((w, s, e))
        if len(cur) >= max_words or re.search(r"[.,!?;:\u2026][\"')\]]*$", w):
            flush()
    flush()
    return groups


def caption_track(cfg, base, D):
    """Sorted list of (start, end, text) or empty."""
    if not cfg or cfg.get("style", "pop") == "none":
        return []
    upper = bool(cfg.get("upper"))
    items = []
    if cfg.get("groups"):
        g = sorted(((float(t), str(x)) for t, x in cfg["groups"]), key=lambda z: z[0])
        for i, (t, x) in enumerate(g):
            end = g[i + 1][0] if i + 1 < len(g) else D
            items.append((t, end, x))
    elif cfg.get("words"):
        wp = os.path.join(base, cfg["words"])
        try:
            with open(wp, "r", encoding="utf-8") as f:
                words = [[str(w), float(s), float(e)] for w, s, e in json.load(f)]
        except (OSError, ValueError) as e:
            raise ToolError("cannot read captions words file %s (%s)" % (wp, e))
        g = auto_groups(words, max(1, int(cfg.get("max_words", 2))))
        for i, (t, x, last_end) in enumerate(g):
            nxt = g[i + 1][0] if i + 1 < len(g) else D
            items.append((t, min(nxt, last_end + 1.2, D), x))
    if upper:
        items = [(a, b, x.upper()) for a, b, x in items]
    return items


class Overlay:
    def __init__(self, spec, base, vi, D):
        self.W, self.H = vi["w"], vi["h"]
        self.D = D
        self.fade_out = float(spec.get("fade_out") or 0)
        cap = spec.get("captions") or {}
        self.cap_cfg = cap
        self.caps = caption_track(cap, base, D)
        self.cap_starts = [c[0] for c in self.caps]
        short = min(self.W, self.H)
        self.cap_font = cap.get("font", "Montserrat-Bold")
        self.cap_size = float(cap.get("size", round(short * 0.078)))
        self.cap_stroke = int(cap.get("stroke", max(2, round(self.cap_size * 0.107))))
        self.cap_y = px(cap.get("y", 0.66), self.H)
        self.cap_x = px(cap.get("x", 0.5), self.W)
        self.labels = spec.get("labels") or []
        self.hud = spec.get("hud") or []
        for i, lb in enumerate(self.labels):
            for k in ("t0", "t1", "text"):
                if k not in lb:
                    raise ToolError("labels[%d] needs %s" % (i, k))
        for i, h in enumerate(self.hud):
            for k in ("t0", "t1", "lines"):
                if k not in h:
                    raise ToolError("hud[%d] needs %s" % (i, k))
        for lb in self.labels:                           # resolve fonts now so notes show up before the render
            get_font(lb.get("font", "Anton-Regular"), lb.get("size", 64))
        for h in self.hud:
            get_font(h.get("font", "ShareTechMono-Regular"), h.get("size", 30))
        if self.caps:
            get_font(self.cap_font, self.cap_size)

    def active(self, t):
        for lb in self.labels:
            if lb["t0"] <= t <= lb["t1"]:
                return True
        for h in self.hud:
            if h["t0"] <= t <= h["t1"]:
                return True
        return False

    def caption_at(self, t):
        i = bisect.bisect_right(self.cap_starts, t + 1e-6) - 1
        if i >= 0 and t < self.caps[i][1] - 1e-6:
            return self.caps[i]
        return None

    def draw_caption(self, im, t):
        c = self.caption_at(t)
        if not c:
            return
        t0, _, txt = c
        k = min(1.0, (t - t0) / 0.12)
        size = self.cap_size * (1.22 - 0.22 * (1 - (1 - k) ** 3))               # pops in big, settles
        d = ImageDraw.Draw(im)
        sw = self.cap_stroke
        f = get_font(self.cap_font, size)
        bb = d.textbbox((0, 0), txt, font=f, stroke_width=sw)
        maxw = self.W * 0.92
        if bb[2] - bb[0] > maxw:                                                  # long caption: shrink to fit the frame
            f = get_font(self.cap_font, size * maxw / (bb[2] - bb[0]))
            bb = d.textbbox((0, 0), txt, font=f, stroke_width=sw)
        x = self.cap_x - (bb[2] - bb[0]) / 2 - bb[0]
        y = self.cap_y - (bb[3] - bb[1]) / 2 - bb[1]
        off = (max(1, round(sw * 0.45)), max(2, round(sw * 0.8)))                # soft drop shadow
        d.text((x + off[0], y + off[1]), txt, font=f, fill=(0, 0, 0), stroke_width=sw, stroke_fill=(0, 0, 0))
        d.text((x, y), txt, font=f, fill=(255, 255, 255), stroke_width=sw, stroke_fill=(16, 16, 16))

    def draw_layers(self, im, t):
        over = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        short = min(self.W, self.H)
        for lb in self.labels:
            a = fade(t, lb["t0"], lb["t1"], float(lb.get("fade", 0.35)))
            if a <= 0:
                continue
            col = parse_color(lb.get("color"), (240, 240, 236))
            f = get_font(lb.get("font", "Anton-Regular"), lb.get("size", 64))
            x, y = px(lb.get("x", 0.5), self.W), px(lb.get("y", 0.5), self.H)
            draw_spaced(d, (x, y + 8 * (1 - a)), str(lb["text"]), f, col + (int(float(lb.get("alpha", 235)) * a),),
                        float(lb.get("spacing", 0)), lb.get("align", "center"))
        for h in self.hud:
            a = fade(t, h["t0"], h["t1"], 0.25)
            if a <= 0:
                continue
            size = h.get("size", 30)
            f = get_font(h.get("font", "ShareTechMono-Regular"), size)
            col = parse_color(h.get("color"), (220, 226, 230))
            x, y = px(h.get("x", 90), self.W), px(h.get("y", 80), self.H)
            lh = float(h.get("line_height", round(float(size) * 1.33)))
            type_on = max(1e-3, float(h.get("type_on", 0.6)))
            stagger = float(h.get("stagger", 0))
            for i, ln in enumerate(h["lines"]):
                prog = min(1.0, max(0.0, (t - h["t0"] - i * stagger) / type_on))
                shown = str(ln)[:int(len(str(ln)) * prog)]
                if shown:
                    d.text((x, y + i * lh), shown, font=f, fill=col + (int(200 * a),))
            if h.get("brackets"):
                ix, iy, arm = short * 0.055, short * 0.046, short * 0.037
                for cx, cy, sx, sy in ((ix, iy, 1, 1), (self.W - ix, iy, -1, 1), (ix, self.H - iy, 1, -1), (self.W - ix, self.H - iy, -1, -1)):
                    d.line([(cx, cy + sy * arm), (cx, cy), (cx + sx * arm, cy)], fill=col + (int(150 * a),), width=max(1, round(short / 540)))
        bb = over.getbbox()
        if not bb:
            return im
        region = Image.alpha_composite(im.crop(bb).convert("RGBA"), over.crop(bb)).convert("RGB")
        im.paste(region, bb[:2])
        return im

    def frame(self, im, t):
        if self.caps:
            self.draw_caption(im, t)
        if (self.labels or self.hud) and self.active(t):
            im = self.draw_layers(im, t)
        if self.fade_out > 0 and t > self.D - self.fade_out:
            f = max(0.0, (self.D - t) / self.fade_out)
            im = Image.blend(Image.new("RGB", im.size, (0, 0, 0)), im, f)
        return im


# ---------------------------------------------------------------- main

MUSIC_PRESETS = ("none", "drone", "pulse")


def validate_spec(spec, base):
    """Everything a real run would fail on, collected so one --check shows all of it. Returns a list of problems (empty = fine)."""
    errs = []

    def num(v, where, lo=None, hi=None):
        try:
            f = float(v)
            if f != f or f in (float("inf"), float("-inf")):
                raise ValueError
        except (TypeError, ValueError):
            errs.append("%s must be a number (got %r)" % (where, v))
            return None
        if lo is not None and f < lo:
            errs.append("%s must be at least %s (got %s)" % (where, lo, v))
        if hi is not None and f > hi:
            errs.append("%s must be at most %s (got %s)" % (where, hi, v))
        return f

    def need_file(rel, where):
        if not isinstance(rel, str) or not os.path.isfile(os.path.join(base, rel)):
            errs.append("%s file not found: %s" % (where, os.path.join(base, rel) if isinstance(rel, str) else rel))
            return False
        return True

    def color(v, where):
        try:
            parse_color(v)
        except ToolError as e:
            errs.append("%s: %s" % (where, e))

    def font(name, where):
        if name is not None:
            if not isinstance(name, str):
                errs.append("%s font must be a name" % where)
            else:
                font_path(name)                                            # a missing font is a note + fallback, shown by --check

    need_file(spec.get("video"), "video")
    if spec.get("voice"):
        need_file(spec["voice"], "voice")
    if "voice_gain" in spec:
        num(spec["voice_gain"], "voice_gain", 0, 4)
    if spec.get("fade_out") is not None:
        num(spec["fade_out"], "fade_out", 0, 30)

    cap = spec.get("captions")
    if cap is not None and not isinstance(cap, dict):
        errs.append("captions must be an object")
    elif cap:
        if cap.get("style", "pop") not in ("pop", "none"):
            errs.append('captions.style must be "pop" or "none"')
        if cap.get("style", "pop") != "none":
            if cap.get("groups"):
                if not isinstance(cap["groups"], list) or not all(isinstance(g, (list, tuple)) and len(g) == 2 for g in cap["groups"]):
                    errs.append('captions.groups must look like [[0.0, "Old"], [0.31, "railroads"]]')
                else:
                    for i, g in enumerate(cap["groups"]):
                        num(g[0], "captions.groups[%d] time" % i, 0)
            elif cap.get("words"):
                if need_file(cap["words"], "captions.words"):
                    try:
                        with open(os.path.join(base, cap["words"]), "r", encoding="utf-8") as f:
                            for w, st, en in json.load(f):
                                float(st), float(en)
                    except (OSError, ValueError, TypeError):
                        errs.append('captions.words must be a words.json file: [["word", start, end], ...]')
        for k, lo in (("size", 4), ("stroke", 0), ("max_words", 1), ("y", 0), ("x", 0)):
            if cap.get(k) is not None:
                num(cap[k], "captions." + k, lo)
        font(cap.get("font"), "captions")

    for name, req in (("labels", ("t0", "t1", "text")), ("hud", ("t0", "t1", "lines"))):
        items = spec.get(name)
        if items is None:
            continue
        if not isinstance(items, list):
            errs.append("%s must be a list" % name)
            continue
        for i, it in enumerate(items):
            w = "%s[%d]" % (name, i)
            if not isinstance(it, dict):
                errs.append(w + " must be an object")
                continue
            for k in req:
                if k not in it:
                    errs.append("%s needs %s" % (w, k))
            t0 = num(it["t0"], w + ".t0", 0) if "t0" in it else None
            t1 = num(it["t1"], w + ".t1", 0) if "t1" in it else None
            if t0 is not None and t1 is not None and t1 <= t0:
                errs.append("%s: t1 must be after t0" % w)
            if name == "hud" and "lines" in it and (not isinstance(it["lines"], list) or not it["lines"]):
                errs.append(w + ".lines must be a non-empty list of text lines")
            for k in ("x", "y", "size", "spacing", "alpha", "type_on", "stagger", "fade", "line_height"):
                if it.get(k) is not None:
                    num(it[k], "%s.%s" % (w, k), 0)
            if it.get("color") is not None:
                color(it["color"], w + ".color")
            if it.get("align") not in (None, "left", "center", "right"):
                errs.append(w + '.align must be "left", "center" or "right"')
            font(it.get("font", "Anton-Regular" if name == "labels" else "ShareTechMono-Regular"), w)

    music = spec.get("music")
    if music is not None:
        if not isinstance(music, dict):
            errs.append("music must be an object")
        else:
            if music.get("preset", "none") not in MUSIC_PRESETS:
                errs.append("music.preset must be one of %s (got %r)" % (", ".join(MUSIC_PRESETS), music.get("preset")))
            if music.get("gain") is not None:
                num(music["gain"], "music.gain", 0, 4)
            sw = music.get("swell")
            if sw is not None:
                if not isinstance(sw, (list, tuple)) or len(sw) != 2:
                    errs.append("music.swell must be two times: [start, end]")
                else:
                    a, b = num(sw[0], "music.swell start", 0), num(sw[1], "music.swell end", 0)
                    if a is not None and b is not None and b <= a:
                        errs.append("music.swell end must be after its start")

    sfx = spec.get("sfx")
    if sfx is not None:
        if not isinstance(sfx, list):
            errs.append("sfx must be a list")
        else:
            for i, s_ in enumerate(sfx):
                w = "sfx[%d]" % i
                if not isinstance(s_, dict):
                    errs.append(w + " must be an object")
                    continue
                if s_.get("kind") not in SFX:
                    errs.append("%s.kind must be one of %s (got %r)" % (w, ", ".join(sorted(SFX)), s_.get("kind")))
                if "t" not in s_:
                    errs.append(w + " needs t (seconds)")
                else:
                    num(s_["t"], w + ".t", 0)
                for k, lo in (("gain", 0), ("count", 1), ("every", 0), ("dur", 0.05)):
                    if s_.get(k) is not None:
                        num(s_[k], "%s.%s" % (w, k), lo)
    return errs


def same_file(x, y):
    try:
        if os.path.exists(x) and os.path.exists(y):
            return os.path.samefile(x, y)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(x)) == os.path.normcase(os.path.abspath(y))


def load_spec(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            spec = json.load(f)
    except OSError as e:
        raise ToolError("cannot read the spec: %s" % e)
    except ValueError as e:
        raise ToolError("the spec is not valid JSON: %s" % e)
    for k in ("video", "out"):
        if not spec.get(k):
            raise ToolError('the spec needs "%s"' % k)
    cap = spec.get("captions")
    if cap and cap.get("style", "pop") not in ("pop", "none"):
        raise ToolError('captions.style must be "pop" or "none"')
    return spec


def main():
    ap = argparse.ArgumentParser(description="Burn captions/labels/HUD into a shot and mix voice, music and sfx.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("spec", help="spec.json (see the examples in --help)")
    ap.add_argument("--check", action="store_true", help="validate everything and print the plan, render nothing")
    ap.add_argument("--overwrite", action="store_true", help="replace an existing output file (only when re-running the same piece)")
    a = ap.parse_args()
    utf8_stdio()
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise ToolError("%s was not found. Run the Setup again (it installs ffmpeg), then restart Claude." % exe)
    spec_path = os.path.abspath(a.spec)
    base = os.path.dirname(spec_path)
    spec = load_spec(spec_path)
    video = os.path.join(base, spec["video"])
    out = os.path.join(base, spec["out"])
    problems = validate_spec(spec, base)
    if problems:
        raise ToolError("the spec has %d problem%s: %s" % (len(problems), "" if len(problems) == 1 else "s", "; ".join(problems)))
    inputs = [video]
    if spec.get("voice"):
        inputs.append(os.path.join(base, spec["voice"]))
    cap_cfg = spec.get("captions") or {}
    if cap_cfg.get("words") and not cap_cfg.get("groups"):
        inputs.append(os.path.join(base, cap_cfg["words"]))
    for inp in inputs:
        if same_file(inp, out):
            raise ToolError('"out" would overwrite an input file (%s). Choose a different "out" name.' % inp)
    if os.path.exists(out) and not a.overwrite:
        raise ToolError("the output file already exists: %s. Pick a new name, or pass --overwrite when you are re-running the same piece." % out)
    vi = probe_video(video)
    W, H = vi["w"] - vi["w"] % 2, vi["h"] - vi["h"] % 2
    vi["w"], vi["h"] = W, H
    N, fps = vi["frames"], vi["fps"]
    D = N / fps
    n_audio = int(round(D * SR))
    overlay = Overlay(spec, base, vi, D)
    plan = {"size": "%dx%d" % (W, H), "fps": round(fps, 3), "frames": N, "duration_s": round(D, 3),
            "captions": len(overlay.caps), "labels": len(overlay.labels), "hud": len(overlay.hud),
            "sfx": len(spec.get("sfx") or []), "music": (spec.get("music") or {}).get("preset", "none"),
            "voice": bool(spec.get("voice"))}
    if a.check:
        return {"ok": True, "check": True, "plan": plan, "notes": NOTES}
    t_start = time.time()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="assemble-")
    stem, ext = os.path.splitext(out)
    part = "%s.partial-%d%s" % (stem, os.getpid(), ext)             # encoded here, moved onto "out" only when it worked
    dec = enc = None
    errs = []
    try:
        audio = build_audio(spec, base, n_audio, D)
        mixwav = os.path.join(tmp, "mix.wav")
        write_wav(mixwav, audio)
        del audio
        has_audio = True
        derr = open(os.path.join(tmp, "dec.log"), "wb")
        eerr = open(os.path.join(tmp, "enc.log"), "wb")
        errs = [derr, eerr]
        dec = subprocess.Popen(["ffmpeg", "-v", "error", "-threads", THREADS, "-i", video, "-frames:v", str(N),
                                "-vf", "crop=%d:%d" % (W, H), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               stdout=subprocess.PIPE, stderr=derr, **popen_kw())
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                                "-framerate", vi["fps_str"], "-i", "-", "-i", mixwav, "-map", "0:v", "-map", "1:a",
                                "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-threads", THREADS,
                                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", "-movflags", "+faststart", part],
                               stdin=subprocess.PIPE, stderr=eerr, **popen_kw())
        CHILDREN.extend([dec, enc])
        size = W * H * 3
        written = 0
        for fr in range(N):
            raw = dec.stdout.read(size)
            if len(raw) < size:
                break
            im = overlay.frame(Image.frombytes("RGB", (W, H), raw), fr / fps)
            enc.stdin.write(im.tobytes())
            written += 1
            if fr % 150 == 149:
                log("frame %d / %d" % (fr + 1, N))
        enc.stdin.close()
        dec.stdout.close()
        enc.wait(timeout=600)
        dec.wait(timeout=60)
        if written == 0:
            raise ToolError("no frames could be decoded from " + video)
        if enc.returncode != 0:
            with open(os.path.join(tmp, "enc.log"), "rb") as f:
                raise ToolError("the encoder failed: " + f.read().decode("utf-8", "replace").strip()[-400:])
        if written != N:
            note("the video had %d frames, expected %d" % (written, N))
        os.replace(part, out)
    finally:
        for p in (dec, enc):
            if p is not None and p.poll() is None:
                p.kill()
                try:
                    p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
        for p in (dec, enc):
            if p in CHILDREN:
                CHILDREN.remove(p)
        for f in errs:
            try:
                f.close()
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(part):                                       # a failed or interrupted run leaves no half-written file
            for _ in range(5):
                try:
                    os.remove(part)
                    break
                except OSError:
                    time.sleep(0.3)

    code, o, _ = run_quick(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", out])
    info = json.loads(o or b"{}")
    kinds = [s.get("codec_type") for s in info.get("streams", [])]
    return {"ok": True, "out": out, "duration_s": round(float((info.get("format") or {}).get("duration", D)), 3), "size": plan["size"],
            "fps": plan["fps"], "frames": N, "audio": "audio" in kinds, "notes": NOTES, "seconds": round(time.time() - t_start, 1)}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except ToolError as e:
        stop_children()
        print(str(e), file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    except SystemExit:
        stop_children()
        raise
    except KeyboardInterrupt:
        stop_children()
        print(json.dumps({"ok": False, "error": "interrupted"}))
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        stop_children()
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(1)
