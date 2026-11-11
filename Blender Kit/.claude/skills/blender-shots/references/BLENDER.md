# Blender shots: how to design, build and render one

Read this before you plan or write any Blender shot. There is no template library here on purpose. You write a short
scene script for the one shot the user wants, using `scripts/blender_kit.py`, and render it with
`scripts/render_blender.py`. The fourteen files in `examples/` show the craft (four hero shots, nine whole-format shots from the showreel, and a complete 20-second vertical Short in the toon-3D cartoon-trivia style). Read the closest one, then write your own.

## 1. What a Blender shot is good for

A built shot earns its place when it makes one idea land harder than a clip or a card could:

- **A title.** The video title, a chapter card, a name or a line that needs weight. Extruded, lit, one word in the accent colour.
- **A big number.** Money, subscribers, views, days, a distance. Count it up and land it on the spoken word.
- **Real photos with a date.** "On March 28..." over the actual photos, fanned out in depth, the date card landing on the beat.
- **A comparison.** Two things side by side in depth, one pushed forward: before/after, tool A vs tool B, then vs now.
- **A quote or a document.** A screenshot of the real page or tweet on a plane, push in, light the line being read.
- **A lower third or label.** A name and a role, a price, a date, rendered with transparency to sit over footage.
- **A logo moment.** The user's own logo or a tool's logo on a card, revealed with light.

Do not use it for every line, or as filler. One shot per big moment; 3 to 8 seconds each; its key event (the count landing,
the date slamming in, the last word arriving) on the exact second the user gave you (`kit.f(seconds)`).

## 2. How to design a shot

1. **Write down what the viewer must understand in 2 seconds.** One idea per shot: "$12,000 a month", "three photos, one
   day", "MY FIRST 10K". If you need two ideas, make two shots or cut one.
2. **Real material on planes beats invented graphics.** `kit.image_plane()` puts the real photo, logo, screenshot or
   document in the scene at its true aspect ratio. A 3D object should hold or frame something real, not replace it.
3. **Camera motion with intent.** Push in toward what matters, drift sideways to reveal depth, pull back to show scale.
   Keep it slow and eased (`ease="in_out"`); add `kit.shake(cam, 0.01-0.02)` for a hand-held feel. Never spin or fly
   through for its own sake.
4. **Depth and light over effects.** Put things at different distances, use `kit.depth_of_field()` so the subject is
   sharp and the rest falls off, add `kit.motes()` for air, light with a warm key and a cool rim (`kit.three_point()`).
   A dark stage with one lit subject reads as cinematic. Rainbow glows, lens flares and particle storms read as cheap.
5. **Readable text at 1080p.** Text is on screen long enough to read twice. Use `Montserrat-Bold` or `Anton-Regular` for
   anything small. Keep it inside the frame with a margin (about 100 px at the sides and 80 px at the bottom). Light
   text on dark. Check the spelling and every number against what the user gave you.
6. **One accent colour.** Pick one (a warm amber like `#E0A040` works on most channels, or the user's brand colour) and use
   it for bars, rules and one highlighted word. Everything else is near-white on near-black.

## 3. The workflow

1. Plan the shot in one sentence: the idea, the second it lands on, the real material it uses.
2. Write the scene script into `shots/<name>/<name>.py`. Start from the closest example's structure. Take text, paths and
   timings as `--arg` values so you can re-render without editing code.
3. Render stills first and look at them:
   `python .claude/skills/blender-shots/scripts/render_blender.py shots/<name>/<name>.py --out shots/<name>/<name>.mp4 --frames 150 --stills 1,72,150 --arg title="MY FIRST 10K"`
   This writes `<name>-still-0001.png` and so on next to the output and takes seconds. Open them and check the frame,
   the text, the edges and the key moment.
4. Fix and render the stills again until the shot is right. Usually two or three passes. Show the user before the full render.
5. Render the clip: the same command without `--stills`, in the background. Overlays (lower thirds, labels over footage)
   use `--alpha` and a `.mov` output: ProRes 4444 with transparency.
6. Tell the user the file and how to place it (SKILL.md section 4).
7. If they watch it with their voice and the event misses the word, change `--arg land=...` (or the frame numbers) and render again.

The runner prints one JSON line: `{"ok": true, "out": "...", "frames": 150, "seconds": 82.1, "stills": [], "policy": "...",
"notes": []}`. On failure, `ok` is false and `error`, `log` and `tail` say what went wrong in your script. `notes` lists
any finishing step this Blender version skipped and any setting the kit forced back (engine, resolution). A full render
also returns `estimate_minutes` (and `frames_reused` after a `--time-ok` re-run).

**Weak PCs and laptops:** keep scenes modest. Use fewer than about 150 motes, photos under about 6000 px wide, and no
more than a handful of lights. 1080p at 30 fps, 4 to 6 seconds, is the normal size. A 150-frame shot takes roughly 1
to 2 minutes on a mid-range PC. The runner caps Blender at 6 threads and ffmpeg at 4; pass `--threads 2` if the computer is
busy (a game, a call). Render stills before every full render; it saves the most time. If the time gate stops a shot, that is
the runner protecting a slow computer: simplify the shot first.

## 4. Hard rules

- **Render policy: 1 sample, 2 motion-blur steps.** `kit.setup()` applies the kit's `tools/_render_policy.py` (the copy
  in `scripts/` is only a fallback) and the runner applies it again just before rendering. Never set samples yourself,
  and never raise them because a frame looks noisy or "could look better". Only the user can ask for a different count,
  for one job, in their own words. Make shots look good with light, depth, motion and grading. The story is in `RENDER-RULES.md`.
- **Always render through `scripts/render_blender.py`. Never call `blender` yourself**, not for a test, not for a "quick"
  render, not with your own script. Your own scene scripts go through the runner like the examples do, and every guard
  below applies to them.
- **EEVEE at the runner's size, forced.** The runner renders every shot with EEVEE at its `--size` (1920x1080 by default) at
  100 percent, never larger. If your script switches to Cycles or Workbench, or sets a bigger resolution or a percentage over
  100, the kit puts it back and prints a `KIT note` line (it shows up in `notes`). Do not fight it. Cycles is far too slow here.
- **30 second cap per shot.** `--frames` above 30 seconds of footage (900 frames at 30 fps) is refused. Split the shot into
  shorter ones; 3 to 8 seconds is normal. Only the user may ask for a longer shot, in their own words, and then you pass
  `--long-ok`.
- **15 minute gate.** A full render is one Blender run. After its first 3 frames the runner measures the time per frame and
  projects the total. If it is above 15 minutes (`--max-minutes`) it stops Blender and returns `ok: false` with
  `estimate_minutes`. Make the shot cheaper (fewer frames, fewer motes and lights, smaller photos), or tell the user the
  estimate and ask whether to wait. Only if the user says yes, run the same command again with `--time-ok`; the frames
  already rendered are reused, and the time-out grows to fit the estimate. Never pass `--time-ok` or raise `--max-minutes`
  on your own.
- **One Blender render at a time**, in the background, at below-normal priority. The runner enforces this with a lock
  file. If it says another render is running, wait (`--wait 600`). Do not start a second one another way, and do not run
  two renders in parallel to "save time": it makes both slower.
- Long renders print a `PROGRESS` line about once a minute (frames done and a rough time left). If a render is clearly
  going to take much longer than promised, stop it and tell the user instead of waiting.
- If you stop the runner, Blender stops with it. Never open Blender's window for a render.
- Test renders go into `shots/<name>/` (or a temp folder), never into the skill folder.

## 5. The kit at a glance

```python
import blender_kit as kit
a = kit.args()            # a.frames, a.fps, a.width, a.height, a.alpha; a.get("name", default, type), a.all("photo") for --arg values
kit.setup()               # clean scene, EEVEE, policy, AgX colour, bloom. setup(view="Standard", bloom=0) for flat graphics
kit.f(1.8)                # frame number at 1.8 s into the shot (frames are 1-based)
```

| Area | Functions |
|---|---|
| Timing and motion | `f(sec)`, `key(target, path, [(frame, value[, ease])], ease, index)`, `shake(obj, strength, speed)`, `rot(x, y, z)` (degrees to radians, for keying rotation) |
| Eases | `linear`, `smooth`, `in_out`, `out`, `in`, `expo`, `expo_in_out`, `back` (overshoot), `bounce`, `hold` |
| Objects | `text(body, font, size, extrude, bevel, color, align, strength, spacing, material, loc, name)`, `number_count(text_obj, start, end, frame_a, frame_b, fmt, ease)`, `image_plane(path, width, loc, rot, lit, border)`, `rect(w, h, color, anchor)`, `backdrop(color, center, image, distance, lit)`, `floor(color, z)`, `motes(count, center=(x, y, z), spread=(x, y, z), size)`, `empty(loc)`, `parent(child, par)`, `measure(obj)` |
| Materials | `emission(color, strength)`, `matte(color, roughness)`, `metal(color, roughness)`, `glass(color)`, `assign(obj, mat)`, `fade(obj, [(frame, alpha)])` |
| Camera and light | `camera(loc, look_at, lens, ortho)`, `aim(cam)`, `screen_camera()` + `screen(x_px, y_px)`, `depth_of_field(cam, focus, fstop)` (returns `dof` for focus pulls), `light(kind, loc, target, power, color, size)`, `three_point(target)`, `rim(target)` |
| Finish | `post(bloom, vignette, grain)`. Good default: `post(bloom=0.3, vignette=0.4, grain=0.035)`. Leave it off for alpha overlays. |

Conventions: Z is up and the camera looks toward +Y from negative Y. `text()` and `image_plane()` stand upright facing
the camera. Rotations are given in degrees, lengths in metres, colours as `"#RRGGBB"`. `parent()` makes the child's
position relative to the parent, so build a group around (0, 0, 0) and then move, scale or fade the parent.

## 6. Things learned the hard way (1 sample, EEVEE)

- **Montserrat.ttf loads as Thin.** It is a variable font and Blender uses its thinnest weight. Thin strokes break up at
  1 sample. Use `Montserrat-Bold` for small text (capitals with `spacing=1.15` read cleanly), `Gelasio-Variable` for a
  serif line, and `Anton-Regular` for big numbers.
- **White text looks grey under AgX.** Flat text at `strength=1.0` reads light grey. Use `strength=1.4`-`1.8` for white,
  or `setup(view="Standard")` when the colours must be exact (overlays, brand colours).
- **Metal needs something to reflect.** On a dark stage, metal text turns brown or black unless it has a key light and a
  soft top light (see `number_build.py` and `title_reveal.py`).
- **Soft shadows speckle at 1 sample.** Area lights jitter their shadows across samples; with one sample that reads as grain on floors and seat edges. Set `light.use_shadow_jitter = False` on every light (see `reconstruction.py`) and keep area lights small (size 2-3) for clean, slightly harder shadows.
- **Haze: never a world volume.** A Volume Scatter on the World swallows the sun in EEVEE (everything goes black or foggy). Put the haze in a big cube with a volume material around the scene instead (`diorama.py`), density 0.002-0.005, `visible_shadow = False`.
- **Text facing an angled camera.** Upright text faces -Y by default; for a camera at azimuth A (degrees, from +X), set the text's Z rotation to A - 270 (camera at 225 -> -45; at 145 -> -125). `depth_of_field(focus=...)` takes an object or a distance, not a point.
- **Flat 2D in Blender.** `kit.screen_camera()` + `kit.setup(view="Standard", bloom=0, motion_blur=0)` gives exact flat colours; 1 m = 100 px on the 1920 frame; nearer = smaller Y. Outlines: the same disc or rect in black, a hair bigger and 0.01 further back. Build characters around an empty and parent EVERY part, outline copies included, or the strays float at the world origin (`cartoon.py`). Mouth flaps and blinks are scale keys.
- **A whole Short in one file.** Build each scene as its own set 70 m apart on X, key the camera and its aim with the next scene's first key one frame after the previous scene's last key (that is the cut), and turn flat characters toward each scene's camera (`short_toon3d.py`). Captions that must sit over 3D: parent them to the camera 1.2 m in front of the lens at letter size 0.08, or the ground swallows them. Stripe textures on scaled boxes: read world position (Geometry node), not Object coordinates. Cel shading: Diffuse -> Shader to RGB -> constant colour ramp; outlines: a flipped Solidify shell in a black material with backface culling on.
- **Fast moves blur grainy.** Motion blur at 1 sample gets noisy on very fast moves. Ease entrances (`expo`, `out`) so the
  fast part lasts only a few frames, or turn blur off with `setup(motion_blur=0)` for that shot.
- **Counting text and motion blur.** `number_count` gives every blur step of a frame the same digits, so numbers do not
  ghost. Do not replace it with your own handler that reads `frame_current` alone.
- **Fades use blended transparency.** Every kit material can fade. Give each fading object its own material (the kit
  does this by default) or they fade together.
- **Depth of field is a post-process.** Strong blur is capped at a pixel size. Very near motes give the nicest bokeh.
- **Version differences** (the EEVEE engine id `BLENDER_EEVEE_NEXT` on 4.2-4.x and `BLENDER_EEVEE` on 5.x, the compositor
  API, the action API) are handled in the kit. If a finishing step is missing on some version, it is skipped and listed in
  `notes`. It never stops the render.

## 7. Style shots (multi-shot pieces in a channel's look)

The `blender-style` skill covers the workflow; `scripts/style_blocks.py` holds the blocks. What the two finished example pieces taught:
- **Plan the best version first.** List every technique the style needs (rigs, shape-key faces, scattered detail, real materials, haze, painterly finish, captions per word) before writing code. A first version built from primitives and keyframes alone looks cheap next to the reference.
- **Compare stills with the reference** (`stills_sheet.py --side-by-side`), shot by shot, before showing anyone.
- **One set per place.** Build each shot's set 1-3 km from the others and render only the current one (`sb.hide_sets`): faster frames, and no stray shadows (a second planet's shadow once put a black hole on Neptune).
- **Light every shot on purpose.** One sun re-aimed per shot (`sb.sun_per_shot`). Light from behind the subject turns planets and faces into black discs. `kit.light()` adds a Track-To constraint; clear it before keying a rotation.
- **No motion blur across hard cuts** (`motion_blur=0`): blur smears the first frame of the next shot.
- **Geometry nodes drop the object's material**: end the tree with Set Material (`sb.scatter_stones` does).
- **EEVEE volumes are blocky noise at 1 sample.** Smoke, plumes and steam are soft cards (`sb.smoke_card_mat`, `sb.smoke_plume`).
- **Standard view clips bright colours** under a strong sun: keep the sun around 2-2.5 and albedos moderate, or light stones turn white. Rusty or rough metal still mirrors a blue sky at grazing angles: set its Specular IOR Level to 0.
- **A moon between the sun and its planet casts a huge oblique shadow** that reads as a hole: turn the moon's shadow off.
- **Objects made from world-space vertices sit at the origin**: sort and place them by their bounding box.
- **`plane` rotated 90 degrees on X** stands up facing -Y; its height is its local Y scale.
- **Cartoon faces**: flat features with shape keys, shrink-wrapped onto the head (`sb.ToonCharacter`); a cap's full sphere hides the eyebrows, so cut domes to half domes.

