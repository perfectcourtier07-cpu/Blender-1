---
name: blender-shots
description: Build 3D shots in Blender for a YouTube video and hand back a video file. 3D titles, big numbers counting up, real photos fanned in depth with a date card, lower thirds with transparency, comparisons, logos and quotes on a dark stage. Use when the user asks for a Blender shot, a 3D title, an intro, a number animation, a "cinematic" card, or anything rendered in 3D, and for changing or re-rendering a shot made here.
---

# Blender shots

You write a short Blender scene script for the one shot the user wants, render stills, fix, render the clip, and tell them the file to drop into their editor. There is no template library: the examples show the craft, the kit gives you the parts, you build the shot.

The kit rules in `CLAUDE.md` apply (render policy, runner only, one render at a time, no spending, cleanup). Start a session with `python tools/doctor.py` if you haven't run it yet; if Blender or FFmpeg is missing, offer the Blender setup.

**Files** (`.claude/skills/blender-shots/`):
- `scripts/render_blender.py` + `scripts/blender_kit.py` (+ `_render_policy.py`): the runner and the scene helpers.
- `references/BLENDER.md`: how to design a shot, the kit at a glance, the hard rules, lessons learned at 1 sample. **Read it before the first shot of a session.**
- `references/RENDER-RULES.md`: why renders use 1 sample. Read it when the user asks about quality, noise or samples.
- `references/PROMPTS.md`: the prompts users are given. Shows the kinds of requests to expect.
- `examples/`: fourteen worked scenes. `short_toon3d.py` is a whole 20-second vertical Short (`--size 1080x1920 --frames 600`) in the paper-people-in-a-3D-world style of the big cartoon-trivia channels: five cel-shaded sets in one file (striped canyon, train cab, trestle over a canyon, curving track, station street), flat cut-out characters turned to face the camera, hard cuts, one bold outlined caption at a time; the model for any "make me a Short like that channel" ask. `cartoon.py` is the flat 2D cartoon (cut-out characters with round heads and dot eyes, thick outlines, a sky-and-hills background, a talking character with mouth flaps and blinks, kinetic captions popping in word by word, all exact flat colours under the 2D screen camera: 1 m = 100 px, outlines are the same shape in black a hair behind). The two 3D looks people ask for most: `diorama.py` (the grainy cinematic miniature look of the big documentary channels: a procedural mountain on dark water, one low warm sun, a breath of haze, a route drawing itself to labelled camps, a serif title, heavy grain and a long shallow lens) and `reconstruction.py` (the clean isometric 3D documentary look: a grey cutaway cabin, red and blue mannequins, one lit row with a callout, cabin power dropping out on the beat; change the row, the lines, the seats and the beats at the top). Hero shots: `title_reveal.py`, `number_build.py`, `photo_stack_date.py`, `lower_third_alpha.py`. Whole-format shots from the showreel people saw: `size_compare.py` (objects to scale with labels), `planets.py` (procedural planets, moon on an orbit), `physics.py` (a baked rigid-body sim), `data_bars.py` (columns rising with counting numbers), `map_route.py` (a route drawing itself on a stylised map), `phone.py` (a product mockup). Learn from them and adapt; don't paste them as templates. The showreel ones take no `--arg` values yet: change the lists at the top of the file for the user's data.
- `fonts/`: the fonts `blender_kit` loads (Montserrat-Bold, Anton-Regular, Gelasio-Variable, all free licences).

**Plain commands:** one command per call from the Blender Kit folder, exactly as written here: no `cd ... &&`, no chains, no pipes. **Long jobs** (every clip render) run in the background or with no timeout, one at a time, and you wait for them; a timeout kills a render half-way. Stills are short.
- Style work (recreating a channel's look from a reference video): the `blender-style` skill (`../blender-style/SKILL.md`) drives it, using `scripts/style_blocks.py` (proven building blocks: rigged cartoon characters with shape-key faces, scattered stones, canyons, planets, smoke, a whiteboard that draws itself, per-shot sets and light, painterly finish), `examples/style_toon_short.py` and `examples/style_space_doc.py` (+ their `.assemble.json`), and the tools `scripts/style_study.py`, `voice_timing.py`, `assemble_video.py`, `stills_sheet.py`. Fonts also include `BebasNeue-Regular` (condensed labels) and `ShareTechMono-Regular` (HUD text).

## 1. Get the brief (one short exchange)
Ask only for what is missing, in one message:
- **What the shot is for:** a title, a number, photos with a date, a lower third, a comparison, a quote, a logo. One idea per shot.
- **The exact text and numbers.** Copy them from the user's message; never retype from memory. Spell-check against what they gave.
- **Files** (photos, logos, screenshots): the full paths. Use them at their real aspect ratio; don't invent images.
- **Length:** 5 seconds unless they say otherwise (3 to 8 is the range; the runner caps at 30).
- **The key moment:** when the number lands, the date slams in, the last word arrives. Default 2.4 s. If they want it on a spoken word, ask for the second where that word is said in their voiceover (they can read it off their editor's timeline).
- **Full frame or overlay:** full frame is an `.mp4` they cut to; an overlay (lower third, label) is a `.mov` with transparency they lay over footage.
- **Look:** dark stage by default, one accent colour (warm amber `#E0A040` works on most channels). If they have brand colours, use them.
If they just say "make me a title that says X", that is enough: use the defaults and show stills.

## 2. Name it and write it
- One folder per shot: `shots/<short-name>/` (letters, digits, dashes). The scene script is `shots/<short-name>/<short-name>.py`.
- Start from the closest example's structure and write your own scene with `blender_kit` (BLENDER.md section 5). Take text, numbers, paths and timings as `--arg` values so the user can ask for a change without you rewriting code.
- Keep it modest: 1920x1080 at 30 fps (pass `--size 1080x1920` for a vertical Short, and re-check the stills: the examples are laid out for 16:9), under about 150 motes, a handful of lights, photos under about 6000 px wide. On a computer doctor rates "slow", shorter and simpler.

## 3. Stills, then the clip
1. Stills first, always:
   `python .claude/skills/blender-shots/scripts/render_blender.py shots/<name>/<name>.py --out shots/<name>/<name>.mp4 --frames 150 --stills 1,72,150 --arg title="..."`
   Pick stills at the start, at the key moment and at the end. Open each PNG with the file-reading tool and check: the text (every letter and digit), the frame (nothing cut off, margins), the key moment landing on its frame, the light (metal not black, white not grey), the depth.
2. Fix and render stills again. Two or three passes are normal. Then show the user the stills (give the paths) and ask if it's right before the full render, unless they said "just render it".
3. Render the clip: the same command without `--stills`, in the background, and wait for it. The runner prints one JSON line: `ok`, `out`, `frames`, `seconds`, `notes`. On `ok: false` read `error` and `tail`: it is a mistake in your script, a time gate, or a lock.
4. Overlays: add `--alpha` and give `--out` a `.mov` name (ProRes 4444 with transparency). No bloom or grain on overlays (`kit.setup(view="Standard", bloom=0)`).

## 4. Hand it back
Tell the user in a few lines: the file path, its length, what you checked by eye (the stills) and what only by machine (the frame count), and how to use it:
- a full-frame `.mp4`: drag it onto the timeline like any clip (CapCut, Premiere, DaVinci, Final Cut);
- an overlay `.mov`: put it on the track above the footage. Premiere, DaVinci Resolve and Final Cut read its transparency; in CapCut, test one short overlay first (alpha support there varies by version).
A change request ("make the gold word bigger", "land it at 3.1 s") is a `--arg` change or a small edit to the scene, stills again, then one render. Overwrite the same file unless they want to keep both versions (`<name>-v2.mp4`).

## 5. Rules that don't move
- **1 sample, 2 motion-blur steps.** Applied by `kit.setup()` and again by the runner. Never raise them for noise or "quality"; fix the scene instead (RENDER-RULES.md). Only the user can ask for another count, for one job, in their own words; then put their words in the scene's policy config as `_render_policy.py` describes.
- **Render only through `scripts/render_blender.py`.** Never call `blender` yourself, not for a test, not with your own script. The runner forces EEVEE at the requested `--size` (1920x1080 by default), caps a shot at 30 s (`--long-ok` only when the user asked for a longer shot), stops a render projected over 15 minutes (`--time-ok` only after the user accepted the wait), keeps one render at a time on this computer (`--wait 600` if another is running), runs Blender in the background at below-normal priority and never opens its window.
- **One clip render per finished shot.** Don't re-render a clip that didn't change. A stopped or failed render keeps its finished frames; the same command reuses them.
- **Real material only.** Real photos, real numbers, the user's own words. No invented logos, fake screenshots or "illustrations" presented as real.
- **Cleanup and stopping.** To stop a render, stop the runner process you started (it stops its own Blender); never stop Blender by name (`taskkill /IM blender.exe`, `pkill blender`): that would also close a Blender the user has open. When a render ends or you stop it, make sure Blender exited. Delete only stills you replaced in this job; everything else of the user's stays.
- **Honesty.** Say what you looked at and what you didn't. If the shot can't be built the way they asked (too long, a file missing, a font without a glyph), say so and offer the nearest thing.
