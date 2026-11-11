"""Example: a product mockup. A stylised phone (rounded dark slab, glowing screen with simple UI blocks) rises, turns on a
slow turntable while a light bar sweeps across its edges; a price tag and a feature line fade in beside it. 180 frames at 30 fps.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/phone.py --out shots/phone/phone.mp4 --frames 180 --stills 1,90,180
"""
import math

import bpy
import blender_kit as kit

a = kit.args()
end = a.frames
ACCENT, INK = "#E0A040", "#F2EEE6"

kit.setup(world="#05070A")
kit.backdrop("#06080C", center="#141A24", distance=10)
kit.floor("#07090D", z=-2.6, roughness=0.22)

rig = kit.empty((0, 0, -0.2), "PhoneRig")
rig.scale = (0.34, 0.34, 0.34)                                 # the phone takes about half the frame height

# Body: a cube scaled to phone proportions with a bevel modifier, glossy near-black.
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
body = bpy.context.object
body.name = "Body"
body.scale = (3.1, 0.28, 6.5)                                   # a bezel around the 2.8 x 6.0 screen
bev = body.modifiers.new("Bevel", "BEVEL")
bev.width, bev.segments = 0.16, 6
bev.use_clamp_overlap = True
kit.assign(body, kit.matte("#444A56", roughness=0.4, name="Shell"))     # matte: a dark world gives metal nothing to reflect
kit.parent(body, rig)

# Screen: a flat emissive panel just in front of the body, with a few UI blocks (a header bar, an accent card, two lines).
screen = kit.rect(2.8, 6.0, material=kit.emission("#0D1420", 1.2, "Screen"), loc=(0, -0.145, 0), name="Screen")
kit.parent(screen, rig)
ui = [((0, -0.15, 2.5), (2.4, 0.5), "#1C2A40", 1.4), ((0, -0.15, 1.2), (2.4, 1.3), ACCENT, 2.2),
      ((0, -0.15, -0.2), (2.4, 0.35), "#2A3448", 1.4), ((0, -0.15, -0.9), (1.7, 0.35), "#2A3448", 1.4),
      ((0, -0.15, -2.2), (2.0, 0.6), "#F2EEE6", 2.0)]
for i, (loc, (w, h), col, s) in enumerate(ui):
    r = kit.rect(w, h, material=kit.emission(col, s, f"UI{i}"), loc=loc, name=f"UI{i}")
    kit.parent(r, rig)
price = kit.text("$29", font="Anton-Regular", size=0.5, color="#0B0E13", strength=1.0, loc=(0, -0.16, -2.25), name="PriceOnScreen")
kit.parent(price, rig)

# Motion: the phone rises into frame and turns 300 degrees over the shot, with a lean.
kit.key(rig, "location", [(1, (0, 0, -3.2)), (kit.f(0.9), (0, 0, -0.2), "back"), (end, (0, 0, 0.0))], ease="out")
kit.key(rig, "rotation_euler", [(1, kit.rot(10, 0, -55)), (end, kit.rot(4, 0, 28))], ease="in_out")   # screen faces the camera most of the way

# Side copy: a feature line and a price, fading in once the phone has settled.
tag = kit.text("YOUR APP · DEMO", font="Montserrat-Bold", size=0.26, spacing=1.25, color=ACCENT, strength=1.6, align="LEFT",
               loc=(2.3, 0, 1.0), name="Tag")
line1 = kit.text("Any product, any angle,", font="Montserrat-Bold", size=0.38, color=INK, strength=1.5, align="LEFT", loc=(2.3, 0, 0.4), name="L1")
line2 = kit.text("built from a sentence.", font="Montserrat-Bold", size=0.38, color=INK, strength=1.5, align="LEFT", loc=(2.3, 0, -0.15), name="L2")
for i, o in enumerate((tag, line1, line2)):
    f0 = kit.f(1.4 + 0.25 * i)
    kit.fade(o, [(f0, 0.0), (f0 + 12, 1.0)])
    x = o.location.x
    kit.key(o, "location", [(f0, (x + 0.4, 0, o.location.z)), (f0 + 12, (x, 0, o.location.z))], ease="out")

# Light: key + rim, a sweeping bar for the edge highlight, a soft top light.
kit.three_point(target=rig, power=1.0, distance=8)
kit.light("AREA", (0, -3, 6), rig, power=600, color="#FFE7C4", size=5, name="Top")
sweep = kit.light("AREA", (-7, -4, 1), rig, power=1500, color="#FFFFFF", size=0.4, name="Sweep")
kit.key(sweep, "location", [(1, (-7, -4, 1)), (kit.f(1.0), (-7, -4, 1), "hold"), (end, (7, -4, 2))], ease="in_out")

kit.motes(count=50, center=(0, 2, 0), spread=(12, 8, 7), size=0.025, strength=2)

cam = kit.camera((-1.0, -16.5, 0.6), look_at=(2.0, 0, 0.0), lens=50)
kit.key(cam, "location", [(1, (-1.0, -16.5, 0.6)), (end, (-0.4, -15.0, 0.3))], ease="in_out")
kit.shake(cam, strength=0.01, speed=30)
kit.depth_of_field(cam, focus=body, fstop=2.2)

kit.post(bloom=0.35, vignette=0.4, grain=0.03)
