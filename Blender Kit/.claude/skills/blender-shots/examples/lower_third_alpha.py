"""Example: a lower third (name + role) on a transparent background, for laying over footage.

Use it when a real person is first seen or quoted. Run it from the Blender Kit folder (the one with CLAUDE.md), in the background. Render with --alpha (ProRes 4444 .mov with transparency):
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/lower_third_alpha.py --out shots/lower-third/lower-third.mov --alpha \
      --frames 150 --arg name="MARIA OKAFOR" --arg role="Park geologist, 1998-2014"
name / role: the two lines (check spelling and title against a real source). hold: seconds the card stays fully on.
The card comes in, holds, and goes out by itself inside the clip, so you can drop the .mov over footage as it is.
"""
import blender_kit as kit

a = kit.args()
name = a.get("name", "MARIA OKAFOR")
role = a.get("role", "Park geologist, 1998-2014")
end = a.frames
out_at = end - kit.f(0.6)                                   # start leaving 0.6 s before the end

# Flat graphics: exact colours (view="Standard"), no bloom, no grain; motion blur still smooths the slides.
kit.setup(view="Standard", bloom=0, motion_blur=0.4)
kit.screen_camera()

ACCENT, INK, PAPER = "#E0A040", "#FFFFFF", "#0E1116"
x0, y0 = 150, 850                                           # left edge and baseline area, in 1920x1080 pixels
card = kit.empty(kit.screen(x0, y0), "LowerThird")

# A dark panel that wipes open from the left, an accent bar that leads it, then the two lines slide in behind it.
title = kit.text(name, font="Montserrat-Bold", size=0.62, spacing=1.04, color=INK, align="LEFT",
                 loc=(0.45, -0.01, 0.28), name="Name")
sub = kit.text(role.upper(), font="Montserrat-Bold", size=0.3, spacing=1.18, color=ACCENT, align="LEFT",
               loc=(0.47, -0.01, -0.36), name="Role")
width = max(kit.measure(title)[0], kit.measure(sub)[0]) + 1.05     # the panel fits the longer line
panel = kit.rect(width, 1.55, material=kit.emission(PAPER, 1.0, "Panel"), anchor="left", loc=(0, 0.02, 0), name="Panel")
bar = kit.rect(0.12, 1.55, ACCENT, anchor="left", loc=(0, 0, 0), name="Bar")
for part in (panel, bar, title, sub):
    kit.parent(part, card)
kit.fade(panel, [(1, 0.0), (6, 0.88), (out_at + 6, 0.88), (out_at + 14, 0.0)])

kit.key(bar, "location", [(1, (-0.6, 0, 0)), (8, (0, 0, 0), "hold"), (out_at, (0, 0, 0)), (out_at + 10, (-0.6, 0, 0))], ease="expo")
kit.fade(bar, [(1, 0.0), (4, 1.0), (out_at + 8, 1.0), (out_at + 12, 0.0)])
kit.key(panel, "scale", [(3, (0.001, 1, 1)), (16, (1, 1, 1), "hold"), (out_at, (1, 1, 1)), (out_at + 12, (0.001, 1, 1))],
        ease="expo_in_out")

for line, delay in ((title, 12), (sub, 17)):
    lx, ly, lz = line.location
    kit.key(line, "location", [(delay, (lx - 0.5, ly, lz)), (delay + 14, (lx, ly, lz), "hold"), (out_at - 4, (lx, ly, lz)),
                               (out_at + 6, (lx - 0.3, ly, lz))], ease="expo")
    kit.fade(line, [(delay, 0.0), (delay + 8, 1.0), (out_at - 4, 1.0), (out_at + 4, 0.0)])
