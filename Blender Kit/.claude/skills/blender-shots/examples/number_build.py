"""Example: a big figure counting up on a dark stage, camera pushing in, depth from bokeh specks.

Use it for the line where the number IS the story ("...a twelve-million-dollar settlement").
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/number_build.py --out shots/number/number.mp4 --frames 150 \
      --arg value=12000000 --arg prefix=$ --arg label="PAID OUT IN 2026" --arg land=2.4
value/prefix/suffix: the figure. label: one short line under it. land: second at which the count finishes (the spoken word).

Run it from the Blender Kit folder (the one with CLAUDE.md), in the background.
"""
import blender_kit as kit

a = kit.args()
value = a.get("value", 12000000, float)
prefix, suffix = a.get("prefix", "$"), a.get("suffix", "")
label = a.get("label", "PAID OUT IN 2026")
land = kit.f(a.get("land", 2.4, float))                 # the count lands on this frame
end = a.frames

kit.setup(world="#05070A")
kit.backdrop("#05070A", center="#1A2230", distance=14)

# The figure: extruded, bevelled, warm metal so the key light rolls across the edges as the camera moves (a dark world gives metal nothing to reflect, so the top light matters).
gold = kit.metal("#E2B65C", roughness=0.3, name="Gold")
num = kit.text(f"{prefix}{value:,.0f}{suffix}", font="Anton-Regular", size=2.0, extrude=0.14, bevel=0.025,
               material=gold, loc=(0, 0, 0.15), name="Figure")
kit.number_count(num, 0, value, kit.f(0.2), land, fmt=prefix + "{:,.0f}" + suffix, ease="out")
kit.key(num, "scale", [(1, (0.92,) * 3), (land, (1.0,) * 3, "back"), (end, (1.02,) * 3)], ease="out")

# A thin rule and the label arrive just after the count lands (they explain the number, they do not compete).
rule = kit.rect(0.001, 0.035, "#E2B65C", loc=(0, -0.3, -1.05), name="Rule")
kit.key(rule, "scale", [(land, (1, 1, 1)), (land + 12, (5200, 1, 1))], ease="expo")
cap = kit.text(label, font="Montserrat-Bold", size=0.34, spacing=1.25, color="#D9DEE6", strength=1.5,
               loc=(0, -0.3, -1.42), name="Label")
kit.fade(cap, [(land + 2, 0.0), (land + 16, 1.0)])
kit.key(cap, "location", [(land + 2, (0, -0.3, -1.52)), (land + 16, (0, -0.3, -1.42))], ease="out")

# Light: warm key, cool rim for the edge, and a soft top light so the faces of the digits read gold, not brown.
kit.three_point(target=num, power=1.1, distance=9)
kit.light("AREA", (0, -4, 6), num, power=700, color="#FFE7C4", size=6, name="Top")

# Depth: glowing specks in front of and behind the figure, drifting slowly; shallow focus on the figure.
dust = kit.motes(count=55, center=(0, -1.0, 0.4), spread=(14, 16, 7), size=0.03, strength=2)
kit.key(dust, "location", [(1, (0, -1.0, 0.2)), (end, (0.4, -1.0, 0.6))], ease="linear")

# Camera: a slow push in with a slight arc; the aim rises a touch so the label settles in frame.
cam = kit.camera((-1.6, -15.5, 1.1), look_at=(0, 0, 0), lens=55)
kit.key(cam, "location", [(1, (-1.6, -15.5, 1.1)), (end, (0.5, -12.6, 0.35))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (0, 0, 0.25)), (end, (0, 0, -0.1))], ease="in_out")
kit.shake(cam, strength=0.015, speed=40)
kit.depth_of_field(cam, focus=num, fstop=1.2)

kit.post(bloom=0.3, vignette=0.4, grain=0.035)
