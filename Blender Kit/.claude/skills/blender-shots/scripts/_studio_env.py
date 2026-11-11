"""Small helpers shared by the Blender Kit scripts (an identical copy sits next to each pack's scripts).

ensure_tool_path()      On a Mac, Claude Desktop is a normal app: its PATH usually lacks Homebrew (/opt/homebrew/bin on Apple
                        Silicon, /usr/local/bin on Intel), so ffmpeg, yt-dlp, deno, node and blender "disappear" even though they
                        are installed. This adds the usual folders to the END of this process's PATH (so anything the user put
                        first still wins) and every program started from here inherits it. On Windows the shell Claude Desktop
                        started does not see programs installed (winget) after it started, until the app restarts; this reads the
                        user and machine PATH from the registry and appends the folders that are missing, so a new ffmpeg or
                        Python works at once. It does nothing on Linux.
install_stop_handlers() Turn SIGTERM / SIGHUP / SIGBREAK into SystemExit so a script's cleanup (stop children, release locks, save
                        the ledger) runs. A SIGHUP that was already ignored (nohup) stays ignored.
start_reaper(pid)       Mac/Linux: a tiny separate watcher process that stops a child's whole process group if THIS process
                        disappears (SIGKILL, crash, app force-quit). Windows uses a job object instead. stop_reaper(r, child)
                        only stops the watcher once the child is confirmed dead.
keep_awake()            Mac: `caffeinate -i -w <this pid>`, so the Mac does not go to sleep by itself while a long job runs. It ends
                        with this process and changes no setting.
Every function is safe to call many times.
"""
import glob
import os
import re
import shutil
import signal
import subprocess
import sys


def mac_tool_dirs():
    if sys.platform != "darwin":
        return []
    home = os.path.expanduser("~")
    dirs = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/usr/local/sbin",
            os.path.join(home, ".deno", "bin"), os.path.join(home, ".local", "bin")]
    py = glob.glob(os.path.join(home, "Library", "Python", "3.*", "bin"))
    dirs += sorted(py, key=lambda d: [int(n) for n in re.findall(r"\d+", d.split("Python")[-1])], reverse=True)   # 3.12 before 3.9
    return [d for d in dirs if os.path.isdir(d)]


WIN_USER_ENV = r"Environment"
WIN_MACHINE_ENV = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _registry_path(winreg, hive, sub):
    try:
        with winreg.OpenKey(hive, sub) as key:
            value, _kind = winreg.QueryValueEx(key, "Path")
    except Exception:  # noqa: BLE001  (missing key or value, no access: that PATH simply adds nothing)
        return []
    return [p for p in value.split(";")] if isinstance(value, str) else []


def windows_tool_dirs():
    """Windows: every entry of the user and machine PATH from the registry (%VAR% expanded), then winget's Links folder, Node.js
    and Deno's usual folders. Only folders that exist. Every failure is silent."""
    if sys.platform != "win32":
        return []
    raw = []
    try:
        import winreg                                    # only on Windows; imported here so Mac and Linux never touch it
        raw += _registry_path(winreg, winreg.HKEY_CURRENT_USER, WIN_USER_ENV)
        raw += _registry_path(winreg, winreg.HKEY_LOCAL_MACHINE, WIN_MACHINE_ENV)
    except Exception:  # noqa: BLE001
        pass
    env = os.environ
    for base, rest in (("LOCALAPPDATA", r"Microsoft\WinGet\Links"), ("ProgramFiles", "nodejs"), ("USERPROFILE", os.path.join(".deno", "bin"))):
        if env.get(base):
            raw.append(os.path.join(env[base], rest))
    out = []
    for p in raw:
        try:
            p = os.path.expandvars(p.strip().strip('"'))
            if p and "%" not in p and os.path.isdir(p):
                out.append(p)
        except Exception:  # noqa: BLE001
            continue
    return out


def _same_dir(a, b):
    return os.path.normcase(a.strip().rstrip("/" + os.sep)) == os.path.normcase(b.strip().rstrip("/" + os.sep))


def ensure_tool_path():
    have = os.environ.get("PATH", "").split(os.pathsep)
    if sys.platform == "win32":
        add = []
        for d in windows_tool_dirs():
            if not any(_same_dir(d, h) for h in have + add if h):
                add.append(d)
    else:
        add = [d for d in mac_tool_dirs() if d not in have]
    if add:
        os.environ["PATH"] = os.pathsep.join([p for p in have if p] + add)
    return add


def install_stop_handlers(on_signal=None):
    """SIGTERM, SIGHUP (and SIGBREAK on Windows) raise SystemExit(1) after calling on_signal(signum). Returns the names set."""
    def handler(signum, frame):
        if on_signal:
            on_signal(signum)
        raise SystemExit(1)
    done = []
    for name in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            if name == "SIGHUP" and signal.getsignal(sig) == signal.SIG_IGN:      # started with nohup: keep ignoring it
                continue
            signal.signal(sig, handler)
            done.append(name)
        except (OSError, ValueError):
            pass
    return done


REAPER = ("import os, signal, sys, time" + chr(10) +
          "rp, pg = int(sys.argv[1]), int(sys.argv[2])" + chr(10) +
          "def alive(pid):" + chr(10) +
          "    try:" + chr(10) +
          "        os.kill(pid, 0)" + chr(10) +
          "    except PermissionError:" + chr(10) +
          "        return True" + chr(10) +
          "    except OSError:" + chr(10) +
          "        return False" + chr(10) +
          "    return True" + chr(10) +
          "while alive(rp):" + chr(10) +
          "    time.sleep(1)" + chr(10) +
          "for sig in (signal.SIGTERM, signal.SIGKILL):" + chr(10) +
          "    try:" + chr(10) +
          "        os.killpg(pg, sig)" + chr(10) +
          "    except OSError:" + chr(10) +
          "        break" + chr(10) +
          "    time.sleep(5)" + chr(10))


def start_reaper(child_pid):
    """Start the watcher for a child that leads its own process group (Popen start_new_session=True). Returns the watcher
    process, or None on Windows. The watcher has its own session, so killing this process does not reach it."""
    if os.name == "nt":
        return None
    try:
        return subprocess.Popen([sys.executable, "-I", "-c", REAPER, str(os.getpid()), str(child_pid)], start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def stop_reaper(reaper, child=None):
    """Stop the watcher, but only once `child` (a Popen) is confirmed dead: if it is still running, the watcher stays and
    stops it when this process exits."""
    if reaper is None:
        return
    if child is not None and child.poll() is None:
        return
    try:
        reaper.terminate()
        reaper.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


_AWAKE = [None]


def keep_awake():
    """Mac only: ask macOS not to idle-sleep while this process runs (`caffeinate -i -w pid`). Returns the process or None."""
    if sys.platform != "darwin":
        return None
    if _AWAKE[0] is not None and _AWAKE[0].poll() is None:
        return _AWAKE[0]
    exe = shutil.which("caffeinate") or ("/usr/bin/caffeinate" if os.path.exists("/usr/bin/caffeinate") else None)
    if not exe:
        return None
    try:
        _AWAKE[0] = subprocess.Popen([exe, "-i", "-w", str(os.getpid())], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        _AWAKE[0] = None
    return _AWAKE[0]
