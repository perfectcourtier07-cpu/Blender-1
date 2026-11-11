"""Style example 2: a 30-second dark cinematic space documentary (the look of the big space-explainer channels), built only
from Blender and style_blocks. Our own topic and true facts (Neptune's moon Triton). Six shots cut on the voice:
  0-4.3    Neptune half-lit in black space, slow push; Triton beside it          planets: gas_giant_mat, ice_moon_mat, atmosphere_mat
  4.3-9.6  whiteboard in a dark room: the backwards-orbit diagram draws itself   sb.Whiteboard (strokes + handwriting on the voice)
  9.6-13.8 drifting through icy Kuiper Belt bodies                               displaced ico spheres
  13.8-16.4 Voyager 2 sweeping past Neptune                                      a model made of primitives
  16.4-23.35 Triton's surface, dark plumes, Neptune huge in the sky              sb.heightfield, sb.smoke_plume (cards, not volumes)
  23.35-30 Triton spirals in and is torn into a ring of debris, fade to black    sb.debris_ring revealed by angle
Each set is built at its own place, 2-3 km apart; sb.hide_sets renders only the current shot's set. Labels (TRITON,
KUIPER BELT) and the HUD text are added by assemble_video.py (style_space_doc.assemble.json): crisp 2D like the channel's.

  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/style_space_doc.py --out shots/space-demo/space-demo.mp4 --frames 900 --stills 60,268,361,460,601,841
"""
import math
import random

import bpy
import blender_kit as kit
import style_blocks as sb
from mathutils import Vector, noise

a = kit.args()
END, FPS = a.frames, a.fps
F = kit.f
random.seed(5)
sc = kit.setup(view="AgX", look="Medium High Contrast", bloom=0.0, motion_blur=0, world="#000000")
sb.space_world()
CUTS = sb.Cuts([0.0, 4.30, 9.60, 13.80, 16.40, 23.35])
A, WB, KB, TS = Vector((0, 0, 0)), Vector((2000, 0, 0)), Vector((0, 3000, 0)), Vector((0, -3000, 0))   # the four sets

M_NEP, M_ATMO, M_TRITON = sb.gas_giant_mat(), sb.atmosphere_mat(), sb.ice_moon_mat()

# ---------------------------------------------------------------- set A: Neptune, Triton, debris ring, Voyager 2
nep = sb.prim("uv_sphere", (0, 0, 0), rot=(0, 18, 0), mat=M_NEP, name="Neptune", radius=10.0, segments=128, ring_count=64)
sb.prim("uv_sphere", (0, 0, 0), mat=M_ATMO, name="Atmo", radius=10.35, segments=128, ring_count=64)
kit.key(nep, "rotation_euler", [(1, kit.rot(0, 18, 0)), (END, kit.rot(0, 18, 40))], ease="linear")
triton = sb.prim("uv_sphere", (-13, -12, 2.4), mat=M_TRITON, name="Triton", radius=1.25, segments=96, ring_count=48)
triton.visible_shadow = False                    # its eclipse shadow on Neptune reads as a black hole
RING_R = 15.5
debris = sb.debris_ring((0, 0, 0), RING_R, 520, sb.ice_moon_mat("DebrisMat", 3.0))

M_WHITE, M_FOIL, M_DARK = kit.matte("#D8D8D2", 0.5, "VgrWhite"), kit.metal("#C99A3E", 0.35, "Foil"), kit.matte("#1C1C1E", 0.6, "VgrDark")
vgr = kit.empty((0, 0, -600), "Voyager")
for p in [sb.prim("cone", (0, 0, 0.45), mat=M_WHITE, name="Dish", radius1=1.85, radius2=0.25, depth=0.55, vertices=48),
          sb.prim("cylinder", (0, 0, -0.15), mat=M_FOIL, name="Bus", radius=0.9, depth=0.45, vertices=10, smooth_shade=False),
          sb.prim("cylinder", (0, 0, 1.0), mat=M_DARK, name="Feed", radius=0.08, depth=0.7, vertices=12),
          sb.prim("cylinder", (2.2, 0, -0.2), rot=(0, 90, 0), mat=M_DARK, name="RTGBoom", radius=0.04, depth=2.8, vertices=8),
          sb.prim("cylinder", (-2.0, 0, -0.1), rot=(0, 90, 0), mat=M_DARK, name="SciBoom", radius=0.05, depth=2.4, vertices=8),
          sb.prim("cube", (-3.2, 0, -0.1), scale=(0.5, 0.45, 0.4), mat=M_DARK, name="Platform", smooth_shade=False, size=1.0),
          sb.prim("cylinder", (0.0, 3.5, -0.2), rot=(90, 0, 0), mat=M_DARK, name="MagBoom", radius=0.015, depth=6.6, vertices=6)] + \
         [sb.prim("cylinder", (2.8 + 0.42 * k, 0, -0.2), rot=(0, 90, 0), mat=M_DARK, name="RTG", radius=0.2, depth=0.38, vertices=12) for k in range(3)]:
    kit.parent(p, vgr)

# ---------------------------------------------------------------- set KB: Kuiper Belt bodies
mat_i, nt_i, out_i = sb.new_mat("Ice")
nz = sb.node(nt_i, "ShaderNodeTexNoise", Scale=4.0, Detail=8.0)
col = sb.ramp(nt_i, [(0.35, "#4D4A4C"), (0.5, "#8B9198"), (0.65, "#B9C2CB")])
nt_i.links.new(nz.outputs["Fac"], col.inputs["Fac"])
sb.principled(nt_i, out_i, col.outputs["Color"], rough=0.7, normal=sb.bump_noise(nt_i, 0, 0.6, height=nz.outputs["Fac"]))
for i in range(260):
    p = KB + Vector((random.uniform(-60, 60), random.uniform(-10, 160), random.uniform(-18, 18)))
    s = random.uniform(0.15, 1.6) * (1.0 if random.random() > 0.08 else 2.5)
    ob = sb.prim("ico_sphere", tuple(p), scale=(s, s * random.uniform(0.6, 1.2), s * random.uniform(0.6, 1.0)),
                 rot=(random.uniform(0, 180),) * 3, mat=mat_i, name="KBO", radius=1.0, subdivisions=3)
    d = ob.modifiers.new("Rough", "DISPLACE")
    d.texture, d.strength = bpy.data.textures.new(sb.nm("KBOtex"), "CLOUDS"), 0.4
    ob.visible_shadow = s > 2.0                  # small rocks would speckle the big ones with shadows
sb.prim("uv_sphere", tuple(KB + Vector((6, 70, -2))), mat=M_TRITON, name="KBTriton", radius=4.0, segments=96, ring_count=48)

# ---------------------------------------------------------------- set TS: Triton's surface with plumes, Neptune in the sky
def ground_h(x, y):
    p = Vector((x * 0.018, y * 0.018, 0.0))
    h = 16.0 * noise.noise(Vector((x * 0.005, y * 0.005, 0.2))) + 3.5 * noise.noise(p * 1.4) + 2.5 * abs(noise.noise(p * 0.5)) + 0.6 * noise.noise(p * 6.0)
    return h - 2.2 * math.exp(-((x - 40) ** 2 + (y - 260) ** 2) / 9000.0)


sb.heightfield("TritonGround", tuple(TS), 900.0, 220, ground_h, sb.ice_moon_mat("GroundMat", 0.06))
sky_nep = sb.prim("uv_sphere", tuple(TS + Vector((-900, 3800, 900))), rot=(20, 30, 0), mat=M_NEP, name="SkyNeptune", radius=1100, segments=128, ring_count=64)
sky_atmo = sb.prim("uv_sphere", tuple(TS + Vector((-900, 3800, 900))), mat=M_ATMO, name="SkyAtmo", radius=1138, segments=128, ring_count=64)
COL, TRAIL = sb.smoke_card_mat("PlumeColumn", "X"), sb.smoke_card_mat("PlumeTrail", "Y")
for off, height, r, trail in (((-60, 330, 0), 105.0, 7.0, 330.0), ((130, 560, 0), 130.0, 8.0, 380.0), ((-230, 640, 0), 90.0, 6.0, 260.0)):
    sb.smoke_plume(TS + Vector(off), height, r, trail, COL, TRAIL)

# ---------------------------------------------------------------- set WB: the whiteboard diagram, timed on the words
wb = sb.Whiteboard(origin=tuple(WB))
wb.text("Triton's orbit", -1.6, 0.92, 0.19, "black", 4.35, 4.9)
wb.stroke(sb.circle_pts(0.0, -0.05, 0.36, 0.36, n=48), "blue", 4.4, 4.95, width=0.013)
for k in range(5):                                                                 # light hatching inside the planet
    yy = -0.3 + k * 0.12
    half = math.sqrt(max(0.0, 0.33 ** 2 - (yy + 0.05) ** 2))
    wb.stroke([(-half, yy), (half, yy + 0.02)], "lblue", 4.7 + 0.05 * k, 4.95 + 0.05 * k, width=0.006)
wb.text("Neptune", 0.0, -0.62, 0.13, "blue", 4.9, 5.3, align="CENTER")
orbit = sb.circle_pts(0.0, -0.05, 1.45, 0.78, a0=math.radians(100), a1=math.radians(100 - 330), n=96)   # clockwise = backwards
wb.arrow(orbit, "red", 4.9, 5.85)
tri = orbit[30]
wb.stroke(sb.circle_pts(tri[0], tri[1], 0.09, 0.09, n=24), "black", 4.6, 4.85)
wb.text("Triton", tri[0] - 0.05, tri[1] + 0.13, 0.12, "black", 4.75, 5.05, align="RIGHT")
wb.text("BACKWARDS", 1.0, 0.72, 0.2, "red", 5.2, 5.7, tilt=-4)
wb.arrow(sb.circle_pts(0.0, -0.05, 0.55, 0.55, a0=math.radians(-60), a1=math.radians(60), n=24), "black", 5.95, 6.6, head=0.1, width=0.01)
wb.text("planet's spin", 0.62, 0.28, 0.11, "black", 6.3, 6.85)
wb.text("no other big moon does this", 0.0, -1.08, 0.13, "blue", 7.45, 8.7, align="CENTER")
wb.stroke([(-1.0, -1.13), (1.0, -1.11)], "blue", 8.5, 8.9, width=0.008)

# ---------------------------------------------------------------- camera, light
cam = kit.camera((0, -50, 0), look_at=(0, 0, 0), lens=50)
cam.data.clip_end = 12000
aim = kit.aim(cam)
dof = kit.depth_of_field(cam, focus=40.0, fstop=8.0)
W = lambda v: tuple(WB + Vector(v))
K = lambda v: tuple(KB + Vector(v))
T = lambda v: tuple(TS + Vector(v))
SHOTS = [dict(cam=((-12, -32, 3.0), (-11.2, -29.5, 2.8)), aim=((-6.0, 0, 0.0), (-6.2, 0, 0.1)), lens=52, fstop=16, focus=20),
         dict(cam=(W((-0.95, -3.45, 1.68)), W((-0.75, -3.1, 1.68))), aim=(W((0.1, 0.86, 1.7)), W((0.12, 0.86, 1.66))), lens=30, fstop=5.6, focus=4.2),
         dict(cam=(K((3, -6, 1)), K((1, 18, -1))), aim=(K((8, 70, -1)), K((6, 70, -2))), lens=35, fstop=4.0, focus=60),
         dict(cam=((-21.0, -52.0, 2.6), (-20.2, -51.0, 2.9)), aim=((-14.2, -40, 1.5), (-14.6, -40, 1.6)), lens=30, fstop=11, focus=13),
         dict(cam=(T((0, -40, 14)), T((0, 20, 13))), aim=(T((-30, 420, 50)), T((-30, 420, 56))), lens=30, fstop=64, focus=400),
         dict(cam=((6, -58, 16), (4, -50, 12)), aim=((-1, 0, -1), (-1, 0, 0)), lens=32, fstop=16, focus=50)]
sb.bake_shots(cam, aim, dof, CUTS, SHOTS)
sun = kit.light("SUN", (0, 0, 10), (0, 0, 0), power=4.0, color="#FFF4E8", name="Sun")
sun.data.angle = math.radians(0.5)
if hasattr(sun.data, "use_shadow_jitter"):
    sun.data.use_shadow_jitter = False
# light comes from the camera's front-left in every space shot: planets read half-lit, not as black discs
sb.sun_per_shot(sun, CUTS, [(0.9, 0.3, -0.15), (0, 0, -1), (0.9, 0.35, -0.2), (0.8, 0.45, -0.3), (0.92, 0.25, -0.18), (0.85, 0.4, -0.25)],
                powers=[4.0, 0.0, 4.0, 4.0, 3.6, 4.0])

# ---------------------------------------------------------------- the story: Triton, Voyager, the break-up
for fr in range(1, END + 1):
    t = CUTS.t(fr)
    si, u = CUTS.shot(t), CUTS.u(t)
    if si == 0:
        tl, ts = sb.lerp((-13.6, -12.6, 2.3), (-12.3, -11.8, 2.6), u), 1.25
    elif si == 5:                                                                  # spirals in, then breaks up
        ang = math.radians(240 + 70 * u)
        r = 26 - (26 - RING_R) * sb.smooth((t - 23.4) / 3.4)
        tl = (r * math.cos(ang), r * math.sin(ang), 0.4 * (1 - u))
        ts = 1.1 * (1 - sb.smooth((t - 26.6) / 1.6)) + 0.001
    else:
        tl, ts = (0, 0, -500), 0.001
    triton.location, triton.scale = tl, (ts,) * 3
    triton.keyframe_insert("location", frame=fr)
    triton.keyframe_insert("scale", frame=fr)
    if si == 3:
        vgr.location = sb.lerp((-16.0, -40.5, 1.0), (-12.6, -40.5, 1.9), u)
        vgr.rotation_euler = kit.rot(62 + 8 * u, 0, 130 + 14 * u)
    else:
        vgr.location = (0, 0, -600)
    vgr.keyframe_insert("location", frame=fr)
    vgr.keyframe_insert("rotation_euler", frame=fr)
brk = 26.6
brk_ang = math.radians(240 + 70 * ((brk - CUTS.starts[5]) / (CUTS.end - CUTS.starts[5])))
for ob, ang, s0 in debris:                                                         # pieces appear outward from the break-up point
    dang = abs((ang - brk_ang + math.pi) % (2 * math.pi) - math.pi)
    f_on = F(min(brk + 1.8 * dang / math.pi, 29.9))
    kit.key(ob, "scale", [(1, (0.001,) * 3), (f_on, (0.001,) * 3), (min(END, f_on + 12), tuple(s0))], ease="out")

# ---------------------------------------------------------------- only the current shot's set renders
sb.hide_sets(CUTS, {"A": A, "WB": WB, "KB": KB, "TS": TS}, ["A", "WB", "KB", "A", "TS", "A"], keep=(aim, sun),
             force={sky_nep: "TS", sky_atmo: "TS"})

sb.finish(bloom=0.35, vignette=0.55, grain=0.045)
kit.key(sc.view_settings, "exposure", [(1, 0.0), (F(29.2), 0.0), (END, -7.0)], ease="in")       # fade to black
