"""Voice and word timings for a video.  words.json everywhere is  [["word", start_s, end_s], ...]  (seconds, 3 decimals).

  python voice_timing.py elevenlabs --text script.txt --out DIR [--voice VOICE_ID] [--model eleven_multilingual_v2]
                                    [--stability 0.5] [--similarity 0.85] [--style 0.25]
        ElevenLabs text to speech WITH timestamps. The key is read only from the environment variable ELEVENLABS_API_KEY
        (never typed in chat, never written anywhere). Writes DIR/vo.mp3, DIR/vo.wav (48 kHz mono) and DIR/words.json.
        Uses your ElevenLabs credits: the character count is printed. --voice is required; run `voices` to see yours.
  python voice_timing.py voices
        List your ElevenLabs voices:  id | name | labels
  python voice_timing.py align --audio FILE --out DIR [--model base.en] [--device cpu|auto|cuda]
        Your own recording: faster-whisper finds the word times. Writes DIR/vo.wav and DIR/words.json.
        Needs:  python -m pip install --user faster-whisper   (the first run downloads a small model)
        Runs on the CPU by default (int8); --device auto/cuda tries the GPU first and falls back to the CPU once if it fails.
  python voice_timing.py even --text script.txt --out DIR [--wpm 165]
        No audio: estimate word times for planning (longer words take longer, extra pause after , ; : . ? !).
  python voice_timing.py pace --dir DIR [--audio vo.wav] [--cut "3.58-4.12,4.86-5.44"] [--insert "0:1.6,2.25:0.5"] [--total SECONDS]
        Tighten pauses (--cut ranges, in seconds of the ORIGINAL audio) and/or add silences (--insert at:seconds, original time).
        Reads DIR/words.json, writes DIR/vo-paced.wav and DIR/words-paced.json with the times remapped. --total pads or trims
        the result to exactly that many seconds. Cut ranges that overlap a word give a warning.
  python voice_timing.py show --words FILE
        Print  index  start  end  word  so you can plan cuts and inserts.

The last stdout line is always one JSON line: {"ok": true, ...} or {"ok": false, "error": "..."}.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from _studio_env import ensure_tool_path, install_stop_handlers
    ensure_tool_path()
    install_stop_handlers()
except Exception:  # noqa: BLE001
    pass

API = "https://api.elevenlabs.io/v1"
SR = 48000
CHILDREN = []


class ToolError(Exception):
    pass


def utf8_stdio():
    """Windows pipes default to cp1252: never crash on other alphabets in the words we print."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001  (Python 3.9 has it for real files; a test's StringIO does not)
            pass


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def popen_kw():
    if os.name == "nt":
        return {"creationflags": 0x00004000}
    return {"preexec_fn": lambda: os.nice(5)}


def run(cmd, timeout=600):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kw())
    CHILDREN.append(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise ToolError("timed out: " + os.path.basename(str(cmd[0])))
    finally:
        if p in CHILDREN:
            CHILDREN.remove(p)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def stop_children():
    for p in list(CHILDREN):
        try:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


def need_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise ToolError("%s was not found. Run the Setup again (it installs ffmpeg), then restart Claude." % exe)


def ffmpeg(args, timeout=600):
    r = run(["ffmpeg", "-v", "error", "-y", "-threads", "4"] + args, timeout)
    if r.returncode != 0:
        raise ToolError("ffmpeg failed: " + (r.stderr or b"").decode("utf-8", "replace").strip()[-400:])


def audio_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], 60)
    try:
        return float((r.stdout or b"").decode().strip())
    except ValueError:
        raise ToolError("could not read the length of " + path)


def to_wav(src, dst):
    ffmpeg(["-i", src, "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst])


def save_words(words, path):
    clean = [[w, round(float(s), 3), round(float(e), 3)] for w, s, e in words]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=1, ensure_ascii=False)
    return clean


def load_words(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [[str(w), float(s), float(e)] for w, s, e in data]
    except (OSError, ValueError) as e:
        raise ToolError("cannot read words file %s (%s)" % (path, e))


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read().strip()
    except OSError as e:
        raise ToolError("cannot read %s (%s)" % (path, e))
    if not text:
        raise ToolError("the text file is empty: " + path)
    return text


# ---------------------------------------------------------------- ElevenLabs

def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise ToolError(
            "ELEVENLABS_API_KEY is not set, so I cannot reach ElevenLabs. Never paste the key into the chat. "
            "WINDOWS: open PowerShell once and run  setx ELEVENLABS_API_KEY \"your-key-here\"  then fully quit Claude Desktop "
            "(right-click its tray icon, Quit) and open it again. "
            "MAC: add the line  export ELEVENLABS_API_KEY=\"your-key-here\"  to ~/.zprofile, and ALSO run  launchctl setenv "
            "ELEVENLABS_API_KEY \"your-key-here\"  because Claude Desktop started from the Dock does not read ~/.zprofile; then quit "
            "Claude Desktop (Cmd+Q) and reopen it. After that, ask again.")
    return key


def http(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            body = ""
        hint = ""
        if e.code in (401, 403):
            hint = " (the key was refused: check ELEVENLABS_API_KEY and that your plan allows this voice)"
        elif e.code == 429:
            hint = " (too many requests or out of credits)"
        raise ToolError("ElevenLabs answered HTTP %s%s %s" % (e.code, hint, body))
    except urllib.error.URLError as e:
        raise ToolError("could not reach ElevenLabs: %s" % e.reason)


def words_from_alignment(al):
    chars = al["characters"]
    starts = al["character_start_times_seconds"]
    ends = al["character_end_times_seconds"]
    words, cur, t0, last = [], "", 0.0, 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append([cur, t0, last])
                cur = ""
            continue
        if not cur:
            t0 = s
        cur += ch
        last = e
    if cur:
        words.append([cur, t0, last])
    return words


def cmd_elevenlabs(a):
    need_ffmpeg()
    text = read_text(a.text)
    if not a.voice:
        raise ToolError("--voice is required. Run  python voice_timing.py voices  to list your voice ids.")
    key = api_key()
    os.makedirs(a.out, exist_ok=True)
    log("sending %d characters to ElevenLabs (this uses your credits)" % len(text))
    body = {"text": text, "model_id": a.model,
            "voice_settings": {"stability": a.stability, "similarity_boost": a.similarity, "style": a.style, "use_speaker_boost": False}}
    req = urllib.request.Request("%s/text-to-speech/%s/with-timestamps?output_format=mp3_44100_128" % (API, a.voice),
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"}, method="POST")
    d = json.loads(http(req, 180).decode("utf-8"))
    if "audio_base64" not in d:
        raise ToolError("ElevenLabs returned no audio: " + json.dumps(d)[:200])
    mp3 = os.path.join(a.out, "vo.mp3")
    with open(mp3, "wb") as f:
        f.write(base64.b64decode(d["audio_base64"]))
    al = d.get("alignment") or d.get("normalized_alignment")
    if not al:
        raise ToolError("ElevenLabs returned no word timings (try the eleven_multilingual_v2 model)")
    to_wav(mp3, os.path.join(a.out, "vo.wav"))
    words = save_words(words_from_alignment(al), os.path.join(a.out, "words.json"))
    dur = audio_duration(os.path.join(a.out, "vo.wav"))
    return {"ok": True, "out": a.out, "audio": os.path.join(a.out, "vo.wav"), "mp3": mp3,
            "words": os.path.join(a.out, "words.json"), "word_count": len(words), "characters": len(text), "duration_s": round(dur, 3)}


def cmd_voices(a):
    req = urllib.request.Request(API + "/voices", headers={"xi-api-key": api_key()})
    d = json.loads(http(req, 60).decode("utf-8"))
    rows = []
    for v in d.get("voices", []):
        labels = ", ".join("%s=%s" % (k, val) for k, val in sorted((v.get("labels") or {}).items()))
        rows.append("%s | %s | %s" % (v.get("voice_id"), v.get("name"), labels))
        print(rows[-1])
    return {"ok": True, "voices": len(rows)}


# ---------------------------------------------------------------- align (your own recording)

def same_file(x, y):
    """True when both paths are one file (or would be): never overwrite a user's recording."""
    try:
        if os.path.exists(x) and os.path.exists(y):
            return os.path.samefile(x, y)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(x)) == os.path.normcase(os.path.abspath(y))


def cmd_align(a):
    need_ffmpeg()
    if not os.path.isfile(a.audio):
        raise ToolError("audio file not found: " + a.audio)
    if same_file(a.audio, os.path.join(a.out, "vo.wav")):
        raise ToolError("the recording %s is the same file as the vo.wav that align writes into --out, which would overwrite it. "
                        "Use a different --out folder." % a.audio)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ToolError("faster-whisper is not installed. The kit's Setup can install it:  python -m pip install --user faster-whisper "
                        "(the first run downloads a small model)")
    os.makedirs(a.out, exist_ok=True)
    wav = os.path.join(a.out, "vo.wav")
    to_wav(a.audio, wav)
    log("finding word times with faster-whisper (%s, %s) ..." % (a.model, a.device))

    def transcribe(device):
        model = WhisperModel(a.model, device=device, compute_type="int8" if device == "cpu" else "float16")
        segments, _info = model.transcribe(wav, word_timestamps=True)
        found = []
        for seg in segments:                             # the generator runs lazily: GPU library errors can appear here
            for w in (seg.words or []):
                t = (w.word or "").strip()
                if t:
                    found.append([t, w.start, w.end])
        return found

    if a.device == "cpu":
        words = transcribe("cpu")
    else:
        try:
            words = transcribe("cuda" if a.device == "cuda" else "auto")
        except Exception as e:  # noqa: BLE001  (missing CUDA libraries are common: fall back once)
            log("NOTE: GPU transcription failed (%s: %s); retrying once on the CPU" % (type(e).__name__, str(e)[:120]))
            words = transcribe("cpu")
    if not words:
        raise ToolError("no words were found in the recording")
    clean = save_words(words, os.path.join(a.out, "words.json"))
    return {"ok": True, "out": a.out, "audio": wav, "words": os.path.join(a.out, "words.json"), "word_count": len(clean),
            "duration_s": round(audio_duration(wav), 3)}


# ---------------------------------------------------------------- even (planning estimate)

PAUSE_AFTER = {",": 0.18, ";": 0.28, ":": 0.28, ".": 0.45, "?": 0.45, "!": 0.45, "…": 0.4, "—": 0.2}


def cmd_even(a):
    text = read_text(a.text)
    tokens = text.split()
    if not tokens:
        raise ToolError("no words in the text")
    weights = [max(2, len(re.sub(r"\W", "", t))) for t in tokens]
    pauses = [PAUSE_AFTER.get(t.rstrip("\"')]}")[-1:], 0.0) for t in tokens]
    speaking = len(tokens) * 60.0 / a.wpm                # total time for the words alone at this pace
    per_weight = speaking / float(sum(weights))
    t, words = 0.0, []
    for tok, wgt, pause in zip(tokens, weights, pauses):
        dur = wgt * per_weight
        words.append([tok, t, t + dur])
        t += dur + pause
    os.makedirs(a.out, exist_ok=True)
    clean = save_words(words, os.path.join(a.out, "words.json"))
    total = clean[-1][2]
    print("estimated length: %.1f s for %d words at %d wpm" % (total, len(clean), a.wpm))
    return {"ok": True, "out": a.out, "words": os.path.join(a.out, "words.json"), "word_count": len(clean), "duration_s": round(total, 3)}


# ---------------------------------------------------------------- pace (cut pauses / add silences)

def parse_cuts(spec):
    cuts = []
    for part in [p.strip() for p in (spec or "").split(",") if p.strip()]:
        m = re.match(r"^([0-9.]+)\s*-\s*([0-9.]+)$", part)
        if not m or float(m.group(2)) <= float(m.group(1)):
            raise ToolError("bad --cut range %r: use start-end in seconds, like 3.58-4.12" % part)
        cuts.append((float(m.group(1)), float(m.group(2))))
    cuts.sort()
    merged = []
    for a, b in cuts:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def parse_inserts(spec):
    ins = []
    for part in [p.strip() for p in (spec or "").split(",") if p.strip()]:
        m = re.match(r"^([0-9.]+)\s*:\s*([0-9.]+)$", part)
        if not m or float(m.group(2)) <= 0:
            raise ToolError("bad --insert %r: use at:seconds, like 2.25:0.5" % part)
        ins.append((float(m.group(1)), float(m.group(2))))
    ins.sort()
    return ins


def remap_start(t, cuts, ins):
    removed = sum(min(max(t - a, 0.0), b - a) for a, b in cuts)
    return t - removed + sum(sec for at, sec in ins if t >= at - 1e-9)


def remap_end(t, cuts, ins):
    removed = sum(min(max(t - a, 0.0), b - a) for a, b in cuts)
    return t - removed + sum(sec for at, sec in ins if t > at + 1e-9)


def build_segments(dur, cuts, ins):
    """Pieces of the original audio to keep and silences to add, in order: [("a", start, end) | ("s", seconds)]."""
    pts = sorted(set([0.0, dur] + [x for c in cuts for x in c if 0 <= x <= dur] + [at for at, _ in ins if 0 <= at <= dur]))
    segs = []
    for a, b in zip(pts, pts[1:]):
        for at, sec in ins:
            if abs(at - a) < 1e-9:
                segs.append(("s", sec))
        if not any(ca <= a + 1e-9 and b <= cb + 1e-9 for ca, cb in cuts):
            segs.append(("a", a, b))
    for at, sec in ins:
        if at >= dur - 1e-9:
            segs.append(("s", sec))
    return segs


def cmd_pace(a):
    need_ffmpeg()
    d = os.path.abspath(a.dir)
    words = load_words(os.path.join(d, "words.json"))
    audio = a.audio
    if audio:
        audio = audio if os.path.isabs(audio) or os.path.exists(audio) else os.path.join(d, audio)
    else:
        for cand in ("vo.wav", "vo.mp3"):
            if os.path.exists(os.path.join(d, cand)):
                audio = os.path.join(d, cand)
                break
    if not audio or not os.path.exists(audio):
        raise ToolError("audio not found (looked for vo.wav / vo.mp3 in %s; pass --audio)" % d)
    cuts, ins = parse_cuts(a.cut), parse_inserts(a.insert)
    dur = audio_duration(audio)
    warnings = []
    for ca, cb in cuts:
        for w, s, e in words:
            if min(e, cb) - max(s, ca) > 0.005:
                warnings.append("cut %.2f-%.2f overlaps the word %r (%.2f-%.2f)" % (ca, cb, w, s, e))
    for wmsg in warnings:
        log("WARNING: " + wmsg)

    segs = build_segments(dur, cuts, ins)
    chains, labels = [], []
    for i, sg in enumerate(segs):
        if sg[0] == "a":
            _, s, e = sg
            ln = e - s
            f = "[0:a]atrim=%.6f:%.6f,asetpts=PTS-STARTPTS,aresample=%d,aformat=channel_layouts=mono" % (s, e, SR)
            if ln > 0.03:
                if s > 1e-6:
                    f += ",afade=t=in:d=0.012"
                if e < dur - 1e-6:
                    f += ",afade=t=out:st=%.6f:d=0.012" % (ln - 0.012)
            chains.append(f + "[p%d]" % i)
        else:
            chains.append("anullsrc=r=%d:cl=mono,atrim=0:%.6f,asetpts=PTS-STARTPTS[p%d]" % (SR, sg[1], i))
        labels.append("[p%d]" % i)
    tail = ""
    if a.total:
        tail = ",apad=whole_dur=%.6f,atrim=0:%.6f" % (a.total, a.total)
    flt = ";".join(chains) + ";" + "".join(labels) + "concat=n=%d:v=0:a=1%s[o]" % (len(labels), tail)
    out_wav = os.path.join(d, "vo-paced.wav")
    ffmpeg(["-i", audio, "-filter_complex", flt, "-map", "[o]", "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", out_wav])

    paced = [[w, remap_start(s, cuts, ins), remap_end(e, cuts, ins)] for w, s, e in words]
    if a.total:
        paced = [[w, min(s, a.total), min(e, a.total)] for w, s, e in paced]
    save_words(paced, os.path.join(d, "words-paced.json"))
    new_len = audio_duration(out_wav)
    return {"ok": True, "audio": out_wav, "words": os.path.join(d, "words-paced.json"), "original_s": round(dur, 3),
            "duration_s": round(new_len, 3), "cuts": len(cuts), "inserts": len(ins), "warnings": warnings}


def cmd_show(a):
    words = load_words(a.words)
    for i, (w, s, e) in enumerate(words):
        print("%4d  %7.3f  %7.3f  %s" % (i, s, e, w))
    return {"ok": True, "word_count": len(words), "duration_s": round(words[-1][2], 3) if words else 0.0}


def main():
    ap = argparse.ArgumentParser(description="Voice and word timings for a video.", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("elevenlabs", help="ElevenLabs voice with word timings")
    p.add_argument("--text", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--voice", default=None)
    p.add_argument("--model", default="eleven_multilingual_v2")
    p.add_argument("--stability", type=float, default=0.5)
    p.add_argument("--similarity", type=float, default=0.85)
    p.add_argument("--style", type=float, default=0.25)
    p.set_defaults(fn=cmd_elevenlabs)
    p = sub.add_parser("voices", help="list your ElevenLabs voices")
    p.set_defaults(fn=cmd_voices)
    p = sub.add_parser("align", help="word times for your own recording (faster-whisper)")
    p.add_argument("--audio", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default="base.en")
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cpu", help="cpu (default, always works), auto or cuda; a failed GPU run retries on the CPU")
    p.set_defaults(fn=cmd_align)
    p = sub.add_parser("even", help="estimate word times from the text only")
    p.add_argument("--text", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--wpm", type=int, default=165)
    p.set_defaults(fn=cmd_even)
    p = sub.add_parser("pace", help="cut pauses / add silences, remap the word times")
    p.add_argument("--dir", required=True)
    p.add_argument("--audio", default=None)
    p.add_argument("--cut", default="")
    p.add_argument("--insert", default="")
    p.add_argument("--total", type=float, default=None)
    p.set_defaults(fn=cmd_pace)
    p = sub.add_parser("show", help="print index/start/end/word")
    p.add_argument("--words", required=True)
    p.set_defaults(fn=cmd_show)
    utf8_stdio()
    a = ap.parse_args()
    if not a.cmd:
        ap.print_help(sys.stderr)
        raise ToolError("choose a subcommand: elevenlabs, voices, align, even, pace or show")
    return a.fn(a)


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
    except Exception as e:  # noqa: BLE001
        stop_children()
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(1)
