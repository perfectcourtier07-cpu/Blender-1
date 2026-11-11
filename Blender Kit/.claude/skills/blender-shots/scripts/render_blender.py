"""Render one Blender scene script (written with blender_kit) to one shot file you can drop into any video editor.

  python render_blender.py SCENE.py --out shots/NAME/NAME.mp4 [--frames 120] [--fps 30] [--size 1920x1080]
                           [--alpha] [--stills 1,60,120] [--arg name=value ...] [--threads N] [--wait SECONDS]
                           [--max-minutes 15] [--time-ok] [--long-ok]

  full frame : H.264 MP4, yuv420p, no audio, at --size and --fps.
  --alpha    : ProRes 4444 .mov with an alpha channel (yuva444p10le), for overlays. --out must end in .mov.
  --stills   : render only those frames, as PNGs next to --out (S12-still-0060.png). Look at them before the full render.
  --arg      : values for the scene script, read inside it with kit.args().get("name") / .all("name"). Repeatable.

Runs Blender in the background (-b --factory-startup) at below-normal priority with a modest thread count, one render at a
time on this computer, Blender capped at 6 threads and ffmpeg at 4 by default (--threads / --encode-threads; a lock file in the
temp folder; --wait N waits up to N seconds for another render to finish). If this script is stopped, Blender is stopped with it.
PNG frames go to a temp folder and are deleted after encoding. Prints one JSON line:
  {"ok": true, "out": "...", "frames": 120, "seconds": 41.2, "stills": [...]}
Samples come from the render policy (1 sample). This script never changes them.

Guards (they cover your own scene scripts too; always render through this runner, never call blender directly):
  engine and size : every shot is rendered with EEVEE at --size (1920x1080 unless you pass another), 100 percent. If the scene
                    script set Cycles, Workbench or a bigger resolution, the kit forces it back and prints a "KIT note" line
                    (returned in "notes").
  length cap      : --frames above 30 seconds of footage (30 x fps) is refused. Split the shot. Only the USER may ask for a
                    longer shot; then pass --long-ok.
  time gate       : a full render is one Blender run. After its first 3 frames the runner measures seconds per frame and projects
                    the total. If that is above --max-minutes (default 15) it stops Blender and returns ok:false with
                    "estimate_minutes". Make the shot cheaper, or ask the user; if the user accepts the wait, run the same command
                    again with --time-ok. The finished frames are kept and reused. With --time-ok the time-out grows to fit the
                    estimate (1.5 x the estimate + 5 minutes, never below --timeout); if it still times out, the frames are kept.
  progress        : a PROGRESS line goes to stderr about once a minute during a long render.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _studio_env import ensure_tool_path, install_stop_handlers, keep_awake, start_reaper, stop_reaper
ensure_tool_path()                                    # Mac: Homebrew's folders are often missing from Claude Desktop's PATH
LOCK = os.path.join(tempfile.gettempdir(), "faceless-studio-blender.lock")   # same name as the Faceless Studio: one Blender at a time on this computer, whichever kit started it
BELOW_NORMAL = 0x00004000
PROBE = 3                      # frames rendered before the time estimate
WORK_PREFIX = "faceless-studio-shot-"
INTERRUPTED = [False]          # set by the signal handler: keep the frames, they can be reused


def find_blender(given=None):
    """--blender, $BLENDER, the kit's tools/doctor.py blender_path(), then the usual install places."""
    if given:
        return given
    if os.environ.get("BLENDER") and os.path.isfile(os.environ["BLENDER"]):
        return os.environ["BLENDER"]
    for start in (HERE, os.getcwd()):
        d = start
        for _ in range(8):
            doc = os.path.join(d, "tools", "doctor.py")
            if os.path.isfile(doc):
                sys.path.insert(0, os.path.dirname(doc))
                try:
                    from doctor import blender_path
                    p = blender_path()
                    if p:
                        return p
                except Exception:
                    pass
                finally:
                    sys.path.pop(0)
            if os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
    if sys.platform == "darwin":                      # the .app binary first: Homebrew's `blender` may be a small wrapper script
        hits = []
        for base in ("/Applications", os.path.expanduser("~/Applications")):
            for pat in ("Blender*.app", os.path.join("Blender*", "Blender*.app")):
                hits += glob.glob(os.path.join(base, pat, "Contents", "MacOS", "Blender"))
        if hits:
            return sorted(hits, key=version_key)[-1]
    p = shutil.which("blender")
    if p:
        return p
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")]
        hits = [h for r in roots if r for h in glob.glob(os.path.join(r, "Blender Foundation", "Blender*", "blender.exe"))]
    elif sys.platform == "darwin":
        hits = []
    else:
        hits = glob.glob("/snap/bin/blender") + glob.glob("/opt/blender*/blender")
    return sorted(hits, key=version_key)[-1] if hits else None


def version_key(path):
    """Sort Blender installs by the numbers in the app/folder name only ("Blender 4.10.app" beats "Blender 4.9.app"); digits in
    other folders ("Program Files (x86)", a user name) and in the file name do not count."""
    nums = []
    for part in re.split(r"[\\/]", path)[:-1]:
        if "blender" in part.lower():
            nums += [int(n) for n in re.findall(r"\d+", part)]
    return nums or [0]


# ------------------------------------------------------------------------------------------- lock and processes
def pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259                                         # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True                                  # it exists, it just belongs to someone else
    except OSError:
        return False


def proc_start(pid):
    """When the process started (a number or text), to tell it apart from a later process that reuses the same pid."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.OpenProcess.restype = wintypes.HANDLE
            h = k.OpenProcess(0x1000, False, pid)
            if not h:
                return None
            c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
            ok = k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
            k.CloseHandle(h)
            return ((c.dwHighDateTime << 32) | c.dwLowDateTime) if ok else None
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


def same_process(pid, start):
    """True if pid is alive and (when we know its start time) is still the same process."""
    if not pid_alive(pid):
        return False
    return start is None or proc_start(pid) in (None, start)


def read_lock():
    for _ in range(6):                     # the file may be mid-write for a moment
        try:
            with open(LOCK) as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            time.sleep(0.3)
    return {}


def write_lock(info):
    tmp = LOCK + f".{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(info, f)
    for _ in range(10):
        try:
            os.replace(tmp, LOCK)
            return
        except OSError:
            time.sleep(0.1)


def lock_alive(info):
    return same_process(int(info.get("pid", 0) or 0), info.get("start")) or \
        same_process(int(info.get("blender", 0) or 0), info.get("bstart"))


def take_lock(wait, scene):
    deadline = time.monotonic() + wait
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "start": proc_start(os.getpid()), "scene": scene,
                                     "started": time.time()}).encode())
            os.close(fd)
            return None
        except FileExistsError:
            info = read_lock()
            if info is None:
                continue
            if not lock_alive(info):
                try:
                    os.remove(LOCK)                                      # stale lock from a crashed run
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                return (f"another Blender render is running (pid {info.get('pid')}, Blender pid {info.get('blender')}, "
                        f"{info.get('scene')}). Wait for it or pass --wait 600. Do not start a second render.")
            time.sleep(2)


def set_lock_child(pid):
    """Record the running Blender/ffmpeg pid in the lock, so a leftover child still counts as 'a render is running'."""
    info = read_lock()
    if not info or info.get("pid") != os.getpid():
        return
    info["blender"], info["bstart"] = pid, (proc_start(pid) if pid else None)
    write_lock(info)


def release_lock():
    info = read_lock()
    if info and info.get("pid") == os.getpid():
        try:
            os.remove(LOCK)
        except OSError:
            pass


# Windows: a job object that kills Blender/ffmpeg when this script dies for any reason (even a forced kill).
_JOB = [None]


def _job():
    if _JOB[0] is None and os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class EXT(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        try:
            k = ctypes.windll.kernel32
            k.CreateJobObjectW.restype = wintypes.HANDLE
            k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            job = k.CreateJobObjectW(None, None)
            info = EXT()
            info.Basic.LimitFlags = 0x2000                       # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if job and k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                _JOB[0] = job
            else:
                _JOB[0] = False
        except Exception:  # noqa: BLE001
            _JOB[0] = False
    return _JOB[0]


def _stop_tree(p):
    """Stop the process and everything it started, and confirm it exited. A second SIGTERM/SIGHUP/Ctrl+C while this runs is
    ignored until it is finished, so the SIGKILL escalation below can never be skipped."""
    saved = {}
    if threading.current_thread() is threading.main_thread():
        for name in ("SIGTERM", "SIGHUP", "SIGINT", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                saved[sig] = signal.signal(sig, signal.SIG_IGN)
            except (OSError, ValueError):
                pass
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(p.pid, signal.SIGTERM)         # the group holds Blender (or ffmpeg) and anything it started
            except OSError:
                pass
        try:
            p.wait(timeout=15 if os.name != "nt" else 30)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                try:
                    os.killpg(p.pid, signal.SIGKILL)     # it ignored the polite stop: stop the whole group for good
                except OSError:
                    pass
            p.kill()
            p.wait(timeout=30)
    finally:
        for sig, old in saved.items():
            try:
                signal.signal(sig, old)
            except (OSError, ValueError):
                pass


def run_low(cmd, timeout, log, poll=None, poll_every=1.0):
    """Run at below-normal priority; on timeout stop the whole process tree and confirm it exited.
    poll(seconds_running) is called about every second. It may return "stop" (stop the process; the result is "stopped")
    or a number (a new total time limit in seconds). Returns the exit code, None on timeout, or "stopped"."""
    kw = {"stdout": log, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kw["creationflags"] = BELOW_NORMAL
    else:
        kw["start_new_session"] = True
        kw["preexec_fn"] = lambda: os.nice(10)
    p = subprocess.Popen(cmd, **kw)
    if os.name == "nt":
        job = _job()
        if job:
            import ctypes
            ctypes.windll.kernel32.AssignProcessToJobObject(job, int(p._handle))
    set_lock_child(p.pid)
    reaper = start_reaper(p.pid)
    t_start, limit = time.monotonic(), timeout           # monotonic: a Mac sleeping or a clock change cannot fake a timeout
    try:
        while True:
            left = t_start + limit - time.monotonic()
            if left <= 0:
                _stop_tree(p)
                return None
            try:
                return p.wait(timeout=min(poll_every, left))
            except subprocess.TimeoutExpired:
                r = poll(time.monotonic() - t_start) if poll else None
                if r == "stop":
                    _stop_tree(p)
                    return "stopped"
                if r:
                    limit = r
    except BaseException:
        _stop_tree(p)
        raise
    finally:
        stop_reaper(reaper, p)                           # only once the child is confirmed dead; otherwise it stays on watch
        set_lock_child(None)


class LogTail:
    """Reads the lines a running Blender has written to its log so far."""

    def __init__(self, path):
        self.path, self.pos, self.carry = path, 0, ""

    def lines(self):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except OSError:
            return []
        self.pos += len(data)
        parts = (self.carry + data.decode("utf-8", "replace")).split("\n")
        self.carry = parts.pop()
        return parts


# ------------------------------------------------------------------------------------------- encoding
def encode(frames_dir, out, fps, n, alpha, threads, log):
    tags = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    src = ["ffmpeg", "-v", "error", "-y", "-threads", str(threads), "-framerate", str(fps), "-start_number", "1",
           "-i", os.path.join(frames_dir, "f_%04d.png"), "-frames:v", str(n), "-an"]
    if alpha:
        cmd = src + ["-c:v", "prores_ks", "-threads", str(threads), "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                     "-vendor", "apl0", "-vf", "scale=out_color_matrix=bt709"] + tags + [out]
    else:
        cmd = src + ["-c:v", "libx264", "-threads", str(threads), "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(fps),
                     "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-movflags", "+faststart"] + tags + [out]
    return run_low(cmd, 1800, log)


def count_frames(path):
    """Frames in the encoded file (None if ffprobe is missing or fails)."""
    if not shutil.which("ffprobe"):
        return None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=300)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def valid_png(path):
    """A finished PNG ends with the IEND chunk; a frame cut off when Blender was stopped does not."""
    try:
        with open(path, "rb") as f:
            f.seek(-12, os.SEEK_END)
            return f.read(12)[4:8] == b"IEND"
    except OSError:
        return False


def frame_no(path):
    m = re.match(r"f_(\d+)\.png$", os.path.basename(path))
    return int(m.group(1)) if m else None


def work_dir(out):
    """A fixed folder per output file, so frames from a stopped render can be reused by the re-run."""
    h = hashlib.sha1(os.path.abspath(out).lower().encode()).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), WORK_PREFIX + h)


def cleanup_old_work(days=2):
    """Remove kept frame folders that nobody came back for."""
    for d in glob.glob(os.path.join(tempfile.gettempdir(), WORK_PREFIX + "*")):
        try:
            if time.time() - os.path.getmtime(os.path.join(d, "meta.json")) > days * 86400:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def arg_files(items):
    """Size and modified time of every --arg value that is an existing file: changing a photo must not reuse old frames."""
    sig = []
    for item in items:
        v = item.split("=", 1)[-1]
        if os.path.isfile(v):
            st = os.stat(v)
            sig.append([item, st.st_size, st.st_mtime_ns])
    return sig


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene")
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--alpha", action="store_true")
    ap.add_argument("--stills", default="")
    ap.add_argument("--arg", action="append", default=[])
    ap.add_argument("--threads", type=int, default=6, help="Blender render threads (default 6, keeps the PC usable)")
    ap.add_argument("--encode-threads", type=int, default=4, help="ffmpeg threads (default 4)")
    ap.add_argument("--wait", type=float, default=0, help="seconds to wait for another render to finish")
    ap.add_argument("--timeout", type=float, default=3600, help="stop Blender after this many seconds (grows with --time-ok)")
    ap.add_argument("--max-minutes", type=float, default=15, help="stop if the projected render time is longer (default 15)")
    ap.add_argument("--time-ok", action="store_true", help="the USER accepted a render longer than --max-minutes")
    ap.add_argument("--long-ok", action="store_true", help="the USER asked for a shot longer than 30 seconds")
    ap.add_argument("--blender")
    a = ap.parse_args()
    t0 = time.monotonic()

    def done(ok, **kw):
        print(json.dumps({"ok": ok, **kw}))
        sys.exit(0 if ok else 1)

    scene, out = os.path.abspath(a.scene), os.path.abspath(a.out)
    try:
        stills = sorted({int(s) for s in a.stills.split(",") if s.strip()})
    except ValueError:
        done(False, error=f"--stills must be frame numbers like 1,60,120, got {a.stills}")
    try:
        w, h = (int(v) for v in a.size.lower().split("x"))
    except ValueError:
        done(False, error=f"--size must look like 1920x1080, got {a.size}")
    if not os.path.isfile(scene):
        done(False, error=f"scene script not found: {scene}")
    if w < 2 or h < 2 or w % 2 or h % 2:
        done(False, error="width and height must be even numbers")
    if a.fps < 1:
        done(False, error="--fps must be at least 1")
    if a.frames < 1:
        done(False, error="--frames must be at least 1")
    if a.alpha and not out.lower().endswith(".mov"):
        done(False, error="--alpha writes ProRes 4444: give --out a .mov name")
    if not a.alpha and not out.lower().endswith(".mp4"):
        done(False, error="a full-frame shot is H.264: give --out an .mp4 name (or use --alpha with .mov)")
    if a.frames > 30 * a.fps and not a.long_ok:
        done(False, error=f"{a.frames} frames at {a.fps} fps is {a.frames / a.fps:.0f} seconds. Shots are capped at 30 seconds "
                          f"({30 * a.fps} frames): split this into shorter shots (3 to 6 seconds is normal) or ask the user. "
                          f"Only if the USER asked for a longer shot, pass --long-ok.", max_frames=30 * a.fps)
    if any(s < 1 or s > a.frames for s in stills):
        done(False, error=f"--stills must be between 1 and --frames ({a.frames})")
    exe = find_blender(a.blender)
    if not exe:
        done(False, error="Blender not found. Run the Blender setup (tools/doctor.py) or pass --blender PATH.")
    if not stills and not shutil.which("ffmpeg"):
        done(False, error="ffmpeg not found on PATH")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    def on_signal(signum):
        INTERRUPTED[0] = True                # keep the frames: a re-run reuses them
    install_stop_handlers(on_signal)         # run_low stops Blender, the finally below releases the lock; nohup's ignored SIGHUP stays ignored
    os.environ["STUDIO_RUNNER_PID"] = str(os.getpid())      # blender_kit's own watchdog (Mac/Linux) reads this
    keep_awake()                             # Mac: no idle sleep while this render runs (ends with this process; no setting changes)

    err = take_lock(a.wait, os.path.basename(scene))
    if err:
        done(False, error=err)
    keep_work = False
    meta, seen_notes, policy, calls = {}, [], [""], [0]
    tmp = None
    try:
        cleanup_old_work()
        if stills:
            tmp = tempfile.mkdtemp(prefix="blender-shot-")
        else:
            tmp = work_dir(out)
            meta_now = {"scene": file_hash(scene), "frames": a.frames, "fps": a.fps, "size": [w, h], "alpha": a.alpha,
                        "args": a.arg, "argfiles": arg_files(a.arg), "exe": exe,
                        "kit": [file_hash(os.path.join(HERE, n)) for n in ("blender_kit.py", "_render_policy.py")
                                if os.path.isfile(os.path.join(HERE, n))]}
            old = read_json(os.path.join(tmp, "meta.json"))
            if not old or {k: old.get(k) for k in meta_now} != meta_now:
                shutil.rmtree(tmp, ignore_errors=True)       # different scene or settings: nothing here can be reused
                old = None
            os.makedirs(tmp, exist_ok=True)
            meta = {**meta_now, "spf": (old or {}).get("spf")}
            write_json(os.path.join(tmp, "meta.json"), meta)
            for p in glob.glob(os.path.join(tmp, "f_*.png")):    # drop a frame cut off when an earlier run was stopped
                if frame_no(p) is None or not valid_png(p):
                    os.remove(p)

        def blender(rng=None, poll=None, timeout=None):
            """One Blender run (frames rng = (first, last), or the stills). Returns (code, log text, log path)."""
            calls[0] += 1
            log_path = os.path.join(tmp, f"blender-{calls[0]}.log")
            prelude = f"import sys; sys.path.insert(0, {HERE!r})"
            cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "1", "-t", str(a.threads),
                   "--python-expr", prelude, "-P", scene, "--python-expr", "import blender_kit; blender_kit._render()",
                   "--", "--frames", str(a.frames), "--fps", str(a.fps), "--size", f"{w}x{h}", "--out-dir", tmp]
            cmd += (["--alpha"] if a.alpha else []) + (["--stills", ",".join(map(str, stills))] if stills else [])
            if rng:
                cmd += ["--range", f"{rng[0]}-{rng[1]}"]
            for item in a.arg:
                cmd += ["--arg", item]
            tail = LogTail(log_path)
            with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                code = run_low(cmd, timeout or a.timeout, log, (lambda el: poll(el, tail)) if poll else None)
            with open(log_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            policy[0] = policy[0] or next((l for l in text.splitlines() if l.startswith("KIT render")), "")
            for l in text.splitlines():
                if l.startswith("KIT note") and l not in seen_notes:
                    seen_notes.append(l)
            return code, text, log_path

        def fail(msg, text="", log_path=None, **extra):
            if log_path:
                keep = os.path.splitext(out)[0] + "-blender.log"
                shutil.copy(log_path, keep)
                extra["log"] = keep
                extra["tail"] = [l for l in text.splitlines() if l.strip()][-25:]
            done(False, error=msg, notes=seen_notes, **extra)

        def present():
            return {n for n in (frame_no(p) for p in glob.glob(os.path.join(tmp, "f_*.png"))) if n}

        def first_missing():
            have, n = present(), 1
            while n in have:
                n += 1
            return n

        base = os.path.splitext(out)[0]
        if stills:
            code, text, lp = blender()
            if code is None:
                fail(f"Blender timed out after {a.timeout:.0f}s and was stopped", text, lp)
            if code != 0 or "KIT done" not in text:
                fail(f"Blender exited with code {code}", text, lp)
            made = []
            for s in stills:
                src = os.path.join(tmp, f"still_{s:04d}.png")
                if not os.path.isfile(src):
                    fail(f"still {s} was not written", text, lp)
                dst = f"{base}-still-{s:04d}.png"
                shutil.move(src, dst)
                made.append(dst)
            done(True, out=None, frames=0, seconds=round(time.monotonic() - t0, 1), stills=made, policy=policy[0], notes=seen_notes)

        def gate_fail(spf, kept):
            est = spf * a.frames / 60
            return fail(f"Projected render time is about {est:.0f} minutes ({spf:.1f} s per frame x {a.frames} frames), "
                        f"above the {a.max_minutes:g} minute limit. Blender was stopped. Make the shot cheaper: fewer frames, "
                        f"fewer motes and lights, smaller photos (under about 6000 px), or a lower --size only if the user agrees. "
                        f"Or ask the user whether they accept the wait; if they say yes, run the same command again with --time-ok. "
                        f"The {kept} frames already rendered are kept and will be reused.",
                        estimate_minutes=round(est, 1), seconds_per_frame=round(spf, 2), frames_kept=kept, max_minutes=a.max_minutes)

        start = first_missing()
        reused = start - 1
        if reused:
            print(f"PROGRESS reusing {reused} frames already rendered", file=sys.stderr, flush=True)
        text, lp = "", None
        spf = meta.get("spf")
        estimate = spf * a.frames / 60 if spf else None
        gate = not a.time_ok and a.frames > PROBE
        if gate and spf and estimate > a.max_minutes and start <= a.frames:
            keep_work = True
            gate_fail(spf, reused)

        if start <= a.frames:
            st = {"times": [], "decided": bool(spf), "prog": time.monotonic(), "n0": start - 1}
            limit0 = a.timeout if not spf else max(a.timeout, 1.5 * spf * (a.frames - start + 1) + 300)

            def poll(el, tail):
                st["times"] += [float(m.group(1)) for m in (re.fullmatch(r"KIT frame \d+ ([\d.]+)", l.strip())
                                                            for l in tail.lines()) if m]   # the kit's own timing lines only
                want = min(PROBE, a.frames - st["n0"])
                ret = None
                if not st["decided"] and len(st["times"]) >= want:
                    st["decided"] = True
                    use = st["times"][1:] if len(st["times"]) > 1 else st["times"]    # frame 1 also pays for loading
                    meta["spf"] = sum(use) / len(use)
                    write_json(os.path.join(tmp, "meta.json"), meta)
                    est = meta["spf"] * a.frames / 60
                    print(f"PROGRESS estimate {meta['spf']:.1f} s per frame, about {est:.1f} min for {a.frames} frames "
                          f"(limit {a.max_minutes:g} min{', accepted by the user' if a.time_ok else ''})",
                          file=sys.stderr, flush=True)
                    if gate and est > a.max_minutes and len(st["times"]) < a.frames - st["n0"]:
                        st["stopped"] = True
                        return "stop"
                    ret = max(a.timeout, 1.5 * meta["spf"] * (a.frames - st["n0"]) + 300)
                if time.monotonic() - st["prog"] >= 60:
                    st["prog"] = time.monotonic()
                    n = len(present())
                    new = n - st["n0"]
                    eta = f", about {el / 60 / new * (a.frames - n):.0f} min left" if new > 0 and n < a.frames else ""
                    print(f"PROGRESS blender {n}/{a.frames} frames, {el / 60:.0f} min so far{eta}", file=sys.stderr, flush=True)
                return ret

            code, text, lp = blender((start, a.frames), poll, limit0)
            if code == "stopped":
                keep_work = True
                for p in glob.glob(os.path.join(tmp, "f_*.png")):        # the frame Blender was drawing is cut off
                    if not valid_png(p):
                        os.remove(p)
                gate_fail(meta["spf"], first_missing() - 1)
            if code is None:
                keep_work = True
                fail(f"Blender timed out and was stopped ({len(present())} of {a.frames} frames done). The finished frames are "
                     f"kept: run the same command again to continue, or ask the user (a render this long needs --time-ok).",
                     text, lp, frames_kept=len(present()))
            if code != 0 or "KIT done" not in text:
                keep_work = True                      # a crash keeps the finished frames: the same command reuses them
                for p_ in glob.glob(os.path.join(tmp, "f_*.png")):
                    if not valid_png(p_):
                        os.remove(p_)
                fail(f"Blender exited with code {code}. The {len(present())} finished frames are kept: fix the cause and run the "
                     f"same command again to continue.", text, lp, frames_kept=len(present()))
            estimate = meta["spf"] * a.frames / 60 if meta.get("spf") else estimate
        got = present()
        if got != set(range(1, a.frames + 1)):
            fail(f"expected frames 1..{a.frames}, Blender wrote {len(got)}", text, lp)
        flog = os.path.join(tmp, "ffmpeg.log")
        with open(flog, "w") as log:
            code = encode(tmp, out, a.fps, a.frames, a.alpha, a.encode_threads, log)
        if code != 0 or not os.path.isfile(out):
            with open(flog) as f:
                fail(f"ffmpeg failed (code {code})", f.read(), flog)
        n_out = count_frames(out)
        if n_out is not None and n_out != a.frames:
            fail(f"the encoded file has {n_out} frames, expected {a.frames}")
        extra = {"estimate_minutes": round(estimate, 1)} if estimate else {}
        if reused:
            extra["frames_reused"] = reused
        done(True, out=out, frames=a.frames, seconds=round(time.monotonic() - t0, 1), stills=[], policy=policy[0],
             notes=seen_notes, **extra)
    finally:
        if tmp and not (keep_work or (INTERRUPTED[0] and not stills)):
            shutil.rmtree(tmp, ignore_errors=True)
        release_lock()


if __name__ == "__main__":
    main()
