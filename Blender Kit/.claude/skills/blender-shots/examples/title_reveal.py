"""Example: a 3D title. The words swing up one by one over a glossy floor, the accent word in gold, a light bar sweeps across
the metal, an optional small line fades in underneath, the camera pushes in slowly.

Use it for a video title, an intro, a chapter card, a name that needs weight.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/title_reveal.py --out shots/title/title.mp4 --frames 150 --stills 1,45,150 \
      --arg title="MY FIRST 10K" --arg gold=10K --arg sub="IN 90 DAYS" --arg start=0.4 --arg gap=0.35
title: the words (up to about five short words on one line; longer titles are shrunk to fit). gold: a word to render in the accent
metal (repeat --arg gold=... for several; matched whole, ignoring case). sub: optional small line under the title. accent: the
accent colour (#RRGGBB). start: second the first word lands. gap: seconds between words. size: letter size (1.5 default).

Run it from the Blender Kit folder (the one with CLAUDE.md), in the background.
"""
import blender_kit as kit

a = kit.args()
title = a.get("title", "MY FIRST 10K")
gold_words = {g.upper().strip("!?.,:;'\"") for g in a.all("gold")}
sub = a.get("sub", "")
accent = a.get("accent", "#E2B65C")
start = a.get("start", 0.4, float)
gap = a.get("gap", 0.35, float)
size = a.get("size", 1.5, float)
end = a.frames
FLOOR, FOOT = -1.9, -0.55                                     # the floor height and where the words' feet hang above it

kit.setup(world="#04060A")
kit.backdrop("#05070C", center="#141A26", distance=16)
kit.floor("#06080C", z=FLOOR, roughness=0.28)                 # glossy: the lit words reflect in it (rougher = softer hotspot)

# Two metals: light chrome for most words, the accent metal for the key word. Metal needs lights to read (see the top light).
chrome = kit.metal("#E8EBF0", roughness=0.24, name="Chrome")
gold = kit.metal(accent, roughness=0.22, name="Gold")

words = title.split() or ["TITLE"]
objs = [kit.text(w, font="Montserrat-Bold", size=size, extrude=0.16, bevel=0.025,
                 material=(gold if w.upper().strip("!?.,:;'\"") in gold_words else chrome), align="LEFT", name=f"Word{i}")
        for i, w in enumerate(words)]
gapx = 0.32 * size
total = sum(kit.measure(o)[0] for o in objs) + gapx * (len(objs) - 1)
fit = 7.8 * (a.width / a.height) / (16 / 9)                  # the line width that still fits at the end of the push-in (7.8 m on 16:9, narrower on a vertical Short)
if total > fit:                                               # a long title: shrink the letters so the line fits the frame
    k = fit / total
    for o in objs:
        o.data.size *= k
    gapx *= k
    total = sum(kit.measure(o)[0] for o in objs) + gapx * (len(objs) - 1)

# Each word hangs from its own pivot at its foot, lies flat pointing away from the camera, and swings up on its beat with a
# small overshoot. The pivots sit in one centred row.
x = -total / 2
last = 1
for i, o in enumerate(objs):
    wd, ht = kit.measure(o)
    piv = kit.empty((x, 0, FOOT), f"Pivot{i}")
    kit.parent(o, piv)
    o.location = (0, 0, ht / 2)                              # text is centred vertically on its origin: lift it onto the pivot
    t0 = kit.f(start + i * gap)
    kit.key(piv, "rotation_euler", [(max(1, t0 - 1), kit.rot(-92, 0, 0)), (t0 + 10, kit.rot(7, 0, 0)),
                                    (t0 + 15, kit.rot(-2, 0, 0)), (t0 + 19, kit.rot(0, 0, 0))], ease="out")
    x += wd + gapx
    last = t0

# A narrow white light bar sweeps left to right across the metal once the words are up.
sweep = kit.light("AREA", (-10, -3.5, 2.6), (0, 0, FOOT + 0.5), power=2200, color="#FFFFFF", size=0.5, name="Sweep")
kit.key(sweep, "location", [(1, (-10, -3.5, 2.6)), (last + 4, (-10, -3.5, 2.6), "hold"), (last + 40, (10, -3.5, 2.6))], ease="in_out")

# The small line under the title: arrives after the last word, rising a little as it fades in.
if sub:
    cap = kit.text(sub, font="Montserrat-Bold", size=0.3 * size, spacing=1.25, color="#D9DEE6", strength=1.5,
                   loc=(0, -0.3, FOOT - 0.55), name="Sub")
    cw = kit.measure(cap)[0]
    if cw > fit * 1.15:                                       # a long sub line shrinks to fit the frame too
        cap.data.size *= fit * 1.15 / cw
    kit.fade(cap, [(last + 10, 0.0), (last + 26, 1.0)])
    kit.key(cap, "location", [(last + 10, (0, -0.3, FOOT - 0.7)), (last + 26, (0, -0.3, FOOT - 0.55))], ease="out")

# Light: warm key and cool rim from three_point, plus a soft top light so the metal faces read, not brown.
mid = objs[len(objs) // 2]
kit.three_point(target=(0, 0, FOOT + 0.5), power=1.0, distance=9)
kit.light("AREA", (0, -4, 6.5), (0, 0, FOOT + 0.4), power=1500, color="#FFE7C4", size=7, name="Top")

# Depth: bokeh specks drifting slowly; shallow focus on the middle word.
dust = kit.motes(count=60, center=(0, -1.0, 0.2), spread=(16, 14, 7), size=0.028, strength=2)
kit.key(dust, "location", [(1, (0, -1.0, 0.0)), (end, (0.5, -1.0, 0.4))], ease="linear")

# Camera: a slow push in with a slight arc; it looks a touch below the words so the floor reflection stays in frame.
cam = kit.camera((-0.9, -14.0, 1.6), look_at=(0, 0, FOOT + 0.1), lens=45)
kit.key(cam, "location", [(1, (-0.9, -14.0, 1.6)), (end, (0.3, -12.0, 1.0))], ease="in_out")
kit.shake(cam, strength=0.012, speed=35)
kit.depth_of_field(cam, focus=mid, fstop=2.0)

kit.post(bloom=0.3, vignette=0.4, grain=0.03)
