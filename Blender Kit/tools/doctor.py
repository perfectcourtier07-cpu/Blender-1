"""Check this computer for everything the Blender Kit needs. Read-only: it installs and changes nothing.

  python tools/doctor.py            -> a readable table
  python tools/doctor.py --json     -> the same as JSON (the skills read this)

Checks: OS, CPU threads, RAM, free disk, the graphics card, Python (3.9 or newer is enough here), FFmpeg/ffprobe and Blender
(4.2 or newer; tested on 5.2). Gives a plain "speed" rating (fast / OK / slow) from GPU, CPU threads and RAM, and reports the
version of each installed pack (Setup, Blender skill) under "packs".
On Windows it appends the registry PATH (and winget's folders) to its own PATH for this run, so a tool installed a minute ago is
found without restarting Claude Desktop. On a Mac it adds Homebrew's folders to PATH for this run (Claude Desktop often lacks them).
"""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from _studio_env import ensure_tool_path
except ImportError:                       # the helper file is missing: carry on without the PATH fix
    def ensure_tool_path():
        return []
ensure_tool_path()

REQUIRED = ("python", "ffmpeg", "ffprobe", "blender")
MIN_BLENDER = (4, 2)
WINGET = {"ffmpeg": "winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements",
          "blender": "winget install -e --id BlenderFoundation.Blender --accept-source-agreements --accept-package-agreements"}
BREW = {"ffmpeg": "brew install ffmpeg", "blender": "brew install --cask blender"}


def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def first_version(out):
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", out or "")
    return m.group(1) if m else None


def _version_key(path):
    """Sort Blender installs by the numbers in the app/folder name only ("Blender 4.10" beats "Blender 4.9"); digits in other
    folders ("Program Files (x86)", a user name) and in the file name do not count."""
    nums = []
    for part in re.split(r"[\\/]", path)[:-1]:
        if "blender" in part.lower():
            nums += [int(n) for n in re.findall(r"\d+", part)]
    return nums or [0]


def mac_blender_candidates():
    out = []
    for base in ("/Applications", os.path.expanduser("~/Applications")):
        for pat in ("Blender*.app", os.path.join("Blender*", "Blender*.app")):
            out += glob.glob(os.path.join(base, pat, "Contents", "MacOS", "Blender"))
    return out


def blender_path():
    """The Blender executable, or None. Used by the render runner too."""
    if sys.platform == "darwin":                      # the .app binary first: Homebrew's `blender` may be a small wrapper script
        apps = [c for c in mac_blender_candidates() if os.path.exists(c)]
        if apps:
            return sorted(apps, key=_version_key)[-1]
    p = shutil.which("blender")
    if p:
        return p
    cands = []
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            if root:
                cands += glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe"))
    elif sys.platform == "darwin":
        cands += mac_blender_candidates()
    else:
        cands += glob.glob("/snap/bin/blender") + glob.glob("/opt/blender*/blender")
    cands = [c for c in cands if os.path.exists(c)]
    return sorted(cands, key=_version_key)[-1] if cands else None


def blender_version(exe):
    out = run([exe, "--version"], 60)
    m = re.search(r"Blender\s+(\d+\.\d+(?:\.\d+)?)", out or "")
    return m.group(1) if m else None


def gpu():
    out = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if out and "failed" not in out.lower() and "not found" not in out.lower():
        name = out.splitlines()[0].strip()
        return name if name.upper().startswith("NVIDIA") else "NVIDIA " + name
    if sys.platform == "darwin":
        chip = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if chip.lower().startswith("apple"):
            return chip.splitlines()[0].strip()
        out = run(["system_profiler", "SPDisplaysDataType"], 30)
        names = [n.strip() for n in re.findall(r"Chipset Model: (.+)", out)]
        return "; ".join(names) if names else "unknown graphics"
    if os.name == "nt":
        out = run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name -join '; '"], 30)
        return out.splitlines()[-1].strip() if out else None
    return None


def gpu_vram_gb():
    out = run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
    try:
        return round(int(out.splitlines()[0].strip()) / 1024, 1)
    except (ValueError, IndexError):
        return None


RAM_OK_GB = 15     # Windows reports usable RAM a little under what is installed (a 16 GB PC reads about 15.6)


def speed_rating(gpu_name, vram_gb, threads, ram):
    """A plain-language guess of how fast this computer renders Blender shots: fast, OK or slow. Rules of thumb, not benchmarks.
    EEVEE at 1 sample leans on the graphics card, then CPU threads, then RAM."""
    g = (gpu_name or "").lower()
    reasons, capable, strong = [], False, False
    apple = "apple" in g or bool(re.search(r"\bm[1-9]( (pro|max|ultra))?\b", g) and sys.platform == "darwin")
    if apple:
        capable = strong = True
    elif "nvidia" in g or "geforce" in g or "rtx" in g or "gtx" in g or "quadro" in g:
        weak = bool(re.search(r"\bmx\s?\d|\bgt\s?\d", g)) or (vram_gb is not None and vram_gb < 3.5)
        capable = not weak
        strong = capable and vram_gb is not None and vram_gb >= 5.5
        if weak:
            reasons.append("the graphics card is a weak one (small video memory or an entry-level MX/GT model)")
    elif re.search(r"radeon\s+(rx|pro)\b|\brx\s?\d{3,4}", g):
        capable = strong = True
    if not capable and not any("graphics card" in r for r in reasons):
        reasons.append("no dedicated graphics card found (integrated graphics render Blender shots slowly)")
    if threads is not None and threads < 8:
        reasons.append(f"only {threads} CPU threads (8 or more recommended)")
    note = None
    if ram is not None and ram < RAM_OK_GB:
        if apple and ram >= 7.5 and not reasons:
            note = f"{ram:g} GB RAM: fine on Apple silicon, but keep shots short and close other apps"
        else:
            reasons.append(f"only {ram:g} GB RAM (16 GB or more recommended)")
    if reasons:
        rating = "slow"
    elif strong and (threads or 0) >= 12 and (ram or 0) >= RAM_OK_GB:
        rating, reasons = "fast", ["capable graphics card, 12+ CPU threads and 16 GB+ RAM"]
    else:
        rating, reasons = "OK", ["no weak spot found, but not a high-end machine either"]
    out = {"rating": rating, "reasons": reasons + ([note] if note else [])}
    return out


def ram_gb():
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 2 ** 30, 1)
        if sys.platform == "darwin":
            return round(int(run(["sysctl", "-n", "hw.memsize"])) / 2 ** 30, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except Exception:  # noqa: BLE001
        return None


def os_name():
    if platform.system() == "Windows":
        build = int((platform.version().split(".") + ["0", "0", "0"])[2] or 0)
        return "Windows 11" if build >= 22000 else f"{platform.system()} {platform.release()}"
    if sys.platform == "darwin":
        arm = run(["sysctl", "-n", "hw.optional.arm64"]).strip() == "1"
        return f"macOS {platform.mac_ver()[0] or platform.release()}, {'Apple silicon' if arm else 'Intel'}"
    return f"{platform.system()} {platform.release()}"


PACK_VERSION_FILES = {"setup": ".claude/skills/blender-setup/VERSION", "blender-shots": ".claude/skills/blender-shots/VERSION",
                      "blender-style": ".claude/skills/blender-style/VERSION"}
# Optional Python packages for the style workflow (study a reference video, voice timings, captions/music/HUD).
# Not required for plain Blender shots. module name -> pip name
STYLE_PACKAGES = {"PIL": "pillow", "numpy": "numpy", "yt_dlp": "yt-dlp", "faster_whisper": "faster-whisper"}


def style_packages():
    import importlib.util
    have = {pip: importlib.util.find_spec(mod) is not None for mod, pip in STYLE_PACKAGES.items()}
    missing = [pip for pip, ok in have.items() if not ok]
    exe = f'"{sys.executable}"' if " " in sys.executable else sys.executable
    fix = None
    if missing:
        fix = f"{exe} -m pip install --user " + " ".join(missing)
        if sys.platform == "darwin":       # Homebrew Python refuses --user installs ("externally-managed-environment")
            fix += "   (if pip says externally-managed-environment, add --break-system-packages)"
    return {"have": have, "missing": missing, "fix": fix}


def pack_versions():
    root = os.path.dirname(HERE)
    out = {}
    for name, rel in PACK_VERSION_FILES.items():
        try:
            with open(os.path.join(root, *rel.split("/")), encoding="utf-8-sig") as f:
                out[name] = f.readline().strip() or None
        except OSError:
            out[name] = None
    return out


def python_candidates():
    """Other Pythons on this computer (newest first), for when the running one is too old or is the Microsoft Store stub."""
    names = ["python3.14", "python3.13", "python3.12", "python3.11", "python3", "python"]
    paths = [shutil.which(n) for n in names]
    if os.name == "nt":
        for base in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python"), os.environ.get("ProgramFiles", "")):
            if base:
                paths += glob.glob(os.path.join(base, "Python3*", "python.exe"))
        paths = [p for p in paths if p and "windowsapps" not in p.lower()]
    out, seen = [], set()
    for pth in paths:
        if not pth or os.path.realpath(pth) in seen:
            continue
        seen.add(os.path.realpath(pth))
        v = run([pth, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], 10).strip()
        if re.fullmatch(r"\d+\.\d+", v) and tuple(int(x) for x in v.split(".")) >= (3, 9):
            out.append({"path": pth, "version": v})
    return sorted(out, key=lambda c: [int(x) for x in c["version"].split(".")], reverse=True)


def main():
    res = {"os": os_name(), "machine": platform.machine(), "cpu_threads": os.cpu_count(), "ram_gb": ram_gb(),
           "free_disk_gb": round(shutil.disk_usage(os.getcwd()).free / 2 ** 30, 1), "gpu": gpu(), "tools": {}}
    t = res["tools"]
    t["python"] = {"version": platform.python_version(), "path": sys.executable, "ok": sys.version_info >= (3, 9)}
    for name in ("ffmpeg", "ffprobe"):
        p = shutil.which(name)
        t[name] = {"path": p, "version": first_version(run([p, "-version"])) if p else None, "ok": bool(p)}
    exe = blender_path()
    bv = blender_version(exe) if exe else None
    ok = bool(exe) and bool(bv) and tuple(int(x) for x in bv.split(".")[:2]) >= MIN_BLENDER
    t["blender"] = {"path": exe, "version": bv, "ok": ok}
    if exe and bv and not ok:
        t["blender"]["note"] = f"Blender {bv} is older than {MIN_BLENDER[0]}.{MIN_BLENDER[1]}; install the current release"
    if not t["python"]["ok"]:
        res["python_candidates"] = python_candidates()
        if res["python_candidates"]:
            res["recommended_python"] = res["python_candidates"][0]["path"]
    res["speed"] = speed_rating(res["gpu"], gpu_vram_gb(), res["cpu_threads"], res["ram_gb"])
    res["packs"] = pack_versions()
    res["style_tools"] = style_packages()
    res["missing"] = [n for n in REQUIRED if not t[n]["ok"]]
    fixes = {}
    for n in res["missing"]:
        if n == "python":
            fixes[n] = ("winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements"
                        if os.name == "nt" else "brew install python@3.12")
        elif n in ("ffmpeg", "ffprobe"):
            fixes["ffmpeg"] = WINGET["ffmpeg"] if os.name == "nt" else BREW["ffmpeg"]
        elif n == "blender":
            fixes[n] = WINGET["blender"] if os.name == "nt" else BREW["blender"] + "   (or download it from blender.org)"
    res["fixes"] = fixes
    res["ok"] = not res["missing"]

    if "--json" in sys.argv:
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1

    print(f"Computer : {res['os']}  |  {res['cpu_threads']} CPU threads  |  {res['ram_gb']} GB RAM  |  {res['free_disk_gb']} GB free  |  GPU: {res['gpu'] or 'unknown'}")
    print(f"Speed    : {res['speed']['rating']} ({'; '.join(res['speed']['reasons'])})")
    print("-" * 100)
    for name in REQUIRED:
        e = t[name]
        state = "OK     " if e["ok"] else "MISSING"
        extra = e.get("version") or ""
        where = e.get("path") or ""
        print(f"{name:9s} {state} {extra:12s} {where}")
        if e.get("note"):
            print(f"{'':9s}         note: {e['note']}")
    if res.get("recommended_python"):
        print(f"use this Python for the kit: {res['recommended_python']}")
    print("-" * 100)
    for name, cmd in fixes.items():
        print(f"fix {name}: {cmd}")
    stl = res["style_tools"]
    print("style    : " + ", ".join(f"{k} {'OK' if v else 'missing'}" for k, v in stl["have"].items())
          + "   (optional: only for recreating a channel's style)")
    if stl["fix"]:
        print(f"fix style (optional, ask first): {stl['fix']}")
    print("packs    : " + ", ".join(f"{k}={v or 'not installed'}" for k, v in res["packs"].items()))
    print("result   : " + ("everything the Blender Kit needs is here" if res["ok"] else "missing: " + ", ".join(res["missing"])))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
