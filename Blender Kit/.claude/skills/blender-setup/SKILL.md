---
name: blender-setup
description: Set up or repair the Blender Kit on this computer. It checks and installs Blender, FFmpeg and (only if missing) Python, proves Blender renders from the command line, and installs the Blender skill pack. Use when the user says "set up", "run the Blender setup", "install what I need", "continue setup", "install the Blender skill from", or when a tool is missing or broken.
---

# Blender setup

Goal: in one pass, the user's computer can render Blender shots from Claude and turn them into video files. Keep the user's effort to a few "yes" clicks. Install only what is missing.

## 0. No Python yet?
Try `python --version`, `python3 --version` and `py -3 --version`. On Windows, `python` may just open the Microsoft Store; that is not a working Python. If none of them prints 3.9 or higher, install Python first (ask once): Windows `winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements`, Mac `brew install python@3.12`. **On Windows do not ask for a restart yet.** The new Python is at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (then `%ProgramFiles%\Python312\python.exe`); check the file exists and use that full path as `<python>` for the rest of setup (the full path is not pre-approved, so each command asks once; after the restart at the end, plain `py -3` or `python` is, so switch to that). Only if you can't find it there, ask the user to fully quit and reopen Claude Desktop in this folder and say "continue setup".

## 1. Look before installing
Run `python tools/doctor.py` (Mac: `python3 tools/doctor.py`; Windows alternative `py -3`, or the full path from step 0; use whichever works from now on). On Windows doctor adds the registry PATH to its own PATH, so it finds tools installed after Claude Desktop started. Show the user its short table, plus one line on what each missing tool is for:

| Tool | What it's for |
|---|---|
| Blender | building and rendering the 3D shots |
| FFmpeg | turning the rendered frames into an MP4 (and ProRes overlays) |
| Python | running the kit's scripts (3.9 or newer is enough) |

## 2. Install what's missing (ask once)
List the exact commands for this OS and ask once for permission to run them all. Doctor prints them as `fix ...:` lines.

**Windows (winget).** Add `--accept-source-agreements --accept-package-agreements` to every command:
```
winget install -e --id Gyan.FFmpeg
winget install -e --id BlenderFoundation.Blender
```
Blender is about 350 MB; FFmpeg about 150 MB. Install, then run doctor again: it finds the new tools through the registry PATH without a restart. If the user prefers, they can install Blender themselves from blender.org (Download, Windows installer) and say "continue setup"; doctor finds it in `C:\Program Files\Blender Foundation\`.

**macOS (Homebrew).** If `brew` is missing, tell the user to open Terminal, paste the one-line installer from brew.sh and press Return (it asks for their Mac password; they type it, you never do), then fully quit and reopen Claude Desktop in this folder and say "continue setup". Then, asking once:
```
brew install ffmpeg
brew install --cask blender        # Apple silicon; on an Intel Mac use Blender 4.5 LTS from blender.org instead (no Intel build after 4.5)
```
First Blender launch on a Mac: macOS may block it. The user opens Blender once from Applications; if macOS says it can't verify it, they open System Settings > Privacy & Security and click "Open Anyway". Their click, not yours. Then they close Blender and you continue. The kit's scripts add `/opt/homebrew/bin` and `/usr/local/bin` to PATH on their own.

**Linux:** the distro's ffmpeg package, plus Blender from blender.org or snap.

**Rules for installing:** no admin/sudo unless the package manager asks; no security-setting changes; never ask for or type a password; if something fails, show the error and the official download page, and carry on with the rest.

## 3. Prove it works
- **Blender:** `python tools/blender_check.py` renders one frame to `renders/blender-check.png` with the render policy applied (1 sample). Look at the image: a gold "BLENDER KIT" title on black. It also prints the Blender version.
- **FFmpeg:** make a 2-second test clip, then check it. Two separate commands, one per call:
  - `ffmpeg -f lavfi -i testsrc=duration=2:size=1280x720:rate=30 -pix_fmt yuv420p renders/ffmpeg-check.mp4`
  - `ffprobe renders/ffmpeg-check.mp4`

## 4. Finish
- Delete the test files you just made in `renders/` (you created them in this setup; leave any other file there alone).
- Tell the user, in a few lines: what was installed, what was already there, anything that failed and how to fix it, and **how fast this computer is** from doctor's `speed` line ("fast", "OK" or "slow" and the reason in one sentence). If it is slow, say renders will take longer here and shots will be kept short (3 to 5 seconds) and simple; it still works.
- **Windows: one restart.** Ask the user to fully quit Claude Desktop (right-click its tray icon, Quit) and open it again in this folder, so every new chat sees the new tools. This is the only restart.
- Tell them the next step: download **Blender-Kit-2-Blender-Skill.zip**, leave it where it is, and say "Install the Blender skill from <path to the zip>". Never ask them to unzip, merge or replace folders.

## Installing the Blender skill
When the user says "Install the Blender skill from <path>": run `python tools/install_pack.py "<path to zip or unzipped folder>"`. It only adds the pack's files, keeps `CLAUDE.md`, the Setup tools and `shots/` untouched, and backs up anything it replaces to `.kit/backups/`. Then run `python tools/doctor.py` and read back the `packs` line (both should show a version). Tell the user the skill is in, and that `PROMPTS.md` in this folder has prompts to start from. Their first shot: "Make a 5-second 3D title that says ... Show me stills first."

## Style tools (optional, for copying a channel's look)
Only when the user wants to recreate a channel's style (the `blender-style` skill), or asks for them. Doctor's `style` line shows four free Python packages: **pillow** and **numpy** (drawing captions, labels and sound), **yt-dlp** (downloading one reference video from a link) and **faster-whisper** (finding when each word is said in their voiceover; the first run downloads a ~150 MB speech model). Ask once, then run the `fix style` command doctor prints, with the same Python the kit uses (for example `python -m pip install --user pillow numpy yt-dlp faster-whisper`; on a Mac `python3 -m pip ...`). Run doctor again and read back the `style` line. If yt-dlp can't be installed, the user can still give a downloaded video file instead of a link.

## Updating the kit itself
Only when the user says "Update the kit from <path>" (a new Setup zip, or the folder it unzipped into): run `python tools/install_pack.py "<path>" --upgrade-kit`. A Setup pack is refused without that flag. The flag replaces the kit's own files (`CLAUDE.md`, `START-HERE.md`, `tools/*`, this skill, `.claude/settings.json`), each old one copied to `.kit/backups/<time>/` first, and never touches `shots/` or `.kit/`. Afterwards run `python tools/doctor.py`, tell the user the Setup version it shows, and ask them to quit and reopen Claude Desktop once so the new rules load.
