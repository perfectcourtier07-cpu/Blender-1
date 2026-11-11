# Why every render here uses 1 sample

Short version: the kit renders every Blender shot at **1 sample** with **2 motion-blur steps**. That is a decision, not a draft setting. Claude never changes it on its own. The look comes from lighting, depth, camera motion and the finishing pass, not from samples.

## What happened before

The templates that this kit grew out of started at the usual Blender defaults: 32 render samples for studio scenes, 48 for desk scenes, 6 motion-blur steps. Every shot went through the whole pipeline at those settings, and renders were the slowest part of every edit. When the owner finally put the high-sample and low-sample versions of the same clips side by side, he could not see a difference worth waiting for. On October 17, 2026 he made it a standing rule: 1 sample, 2 blur steps, for every channel. Nobody raises it without being asked; in this kit, you are the one who can ask.

Measured on the same scene, same PC (a 7-second, 210-frame 1080p clip; times include Blender start-up, scene build, rendering and encoding):

| Settings (samples / blur steps) | Seconds |
|---|---:|
| 32 / 6 (the old default) | 218.6 |
| 8 / 2 | 135.0 |
| 6 / 2 | 113.9 |

A second scene went from 77 seconds at 8 samples to 71 seconds at 1 sample. So the saving is real but it is not magic: a shot still takes a minute or two on a mid-range PC because most of the time goes to building frames, loading fonts and encoding. What the rule buys is **predictability**: no shot ever takes ten times longer because somebody "turned up the quality".

## Why 1 sample looks fine here

EEVEE is a real-time engine. With one sample it renders a clean image as long as the scene gives it something to work with:

- **light:** a warm key light, a cool rim, and a soft top light; dark worlds with one lit subject read as cinematic;
- **depth:** objects at different distances, shallow depth of field, a few floating specks for bokeh;
- **motion:** slow, eased camera moves; fast moves get grainy, so the fast part of an entrance lasts only a few frames;
- **finish:** a little bloom, a vignette and film grain hide the rest.

Things that do look bad at 1 sample, and the fix: very thin fonts (use the bold faces in `fonts/`), pure white text under the AgX view (use a higher emission strength), metal in an empty black world (add a top light so it has something to reflect).

## What this means in practice

- Claude will not say "let me bump the samples to clean that up". If a still looks noisy, the fix is in the scene: light, font, speed, blur.
- If you really want a higher count for one job, say so in your own words ("render this one at 8 samples"). Claude records your request in the shot's settings and uses it for that job only. Expect a slower render and, most of the time, the same-looking clip.
- Never ask Claude to "test which sample count looks best". That is exactly the loop that wasted days before this rule existed.

The rule is enforced in code (`tools/_render_policy.py`, with a fallback copy in the skill's `scripts/`), applied in `blender_kit.setup()` and again by the render runner, so a scene script cannot quietly change it.
