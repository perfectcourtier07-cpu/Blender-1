"""Example: a 20-second vertical Short in the "paper people in a 3D world" style of the big cartoon-trivia channels: flat cut-out
characters (white round heads, dot eyes, eyebrows, stick limbs, thick outlines) standing in bright cel-shaded 3D sets (striped
red canyon walls, deep blue sky, sand, tracks with ballast, a trestle over a canyon), hard cuts every few seconds, low and dutch
camera angles, and one bold white caption word at a time. Five scenes in one file; the camera jumps between them.
The story is told in our own words (why a dead-straight railroad was a bad idea): no assets, text or audio from any channel.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/short_toon3d.py --out shots/short/short.mp4 --frames 600 --size 1080x1920 --stills 60,180,300,430,560
Change CAPTIONS and SCENES at the top, recolour the characters, swap the sets. Everything is primitives plus three shader tricks:
cel shading (Shader to RGB -> colour ramp), strata stripes (fract of Z -> colour ramp) and inverted-hull outlines on the 3D props.
"""
import math
import random

import bpy
import blender_kit as kit
from mathutils import Vector

a = kit.args()
end = a.frames
FPS = a.fps
random.seed(3)
# ---------------------------------------------------------------- story and timing
CAPTIONS = [(0.2, "A perfectly"), (1.3, "straight railroad"), (3.0, "sounds ideal."), (4.4, "But the crews"), (6.0, "kept nodding"),
            (7.2, "off."), (8.6, "Nothing to see."), (10.2, "Nothing to hear."), (12.2, "So engineers"), (13.6, "added curves"),
            (15.0, "and rail joints."), (16.6, "The clickety-clack"), (18.4, "kept them awake.")]
SCENES = [(0.0, 4.4), (4.4, 8.6), (8.6, 12.2), (12.2, 16.8), (16.8, 20.0)]      # canyon straight, cab, trestle, curve, station
INK = "#141414"
SAND, BALLAST, WOOD, RAIL = "#E6B46A", "#9A8C7C", "#7A4E2A", "#9AA0A8"
STRATA = ("#B8451F", "#E27A3A", "#C9582A", "#EE9B52", "#A33C1A")
WHITE, SHIRT_TEAL, SHIRT_GOLD, SHIRT_RED, SHIRT_BLUE = "#F7F4EE", "#2FA38B", "#E0A23A", "#C9372F", "#3F6FB5"

kit.setup(view="Standard", bloom=0, motion_blur=0.2, world="#2C5DBF")
sc = bpy.context.scene

# sky: deep blue at the top, pale at the horizon (a screen-space gradient on the world)
w = sc.world
wn = w.node_tree.nodes
wl = w.node_tree.links
bg = wn["Background"]
tc = wn.new("ShaderNodeTexCoord")
sep = wn.new("ShaderNodeSeparateXYZ")
ramp = wn.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.35, (0.63, 0.86, 0.96, 1)
ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.95, (0.12, 0.30, 0.72, 1)
wl.new(tc.outputs["Window"], sep.inputs[0])
wl.new(sep.outputs["Y"], ramp.inputs["Fac"])
wl.new(ramp.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 1.0


# ---------------------------------------------------------------- materials
def _steps(nt, dif_out):
    """Diffuse -> Shader to RGB -> 2-step ramp (shade / lit); returns the ramp colour output"""
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.color_ramp.interpolation = "CONSTANT"
    rp.color_ramp.elements[0].position, rp.color_ramp.elements[0].color = 0.0, (0.62, 0.62, 0.66, 1)
    rp.color_ramp.elements[1].position, rp.color_ramp.elements[1].color = 0.42, (1, 1, 1, 1)
    nt.links.new(dif_out, s2r.inputs[0])
    nt.links.new(s2r.outputs["Color"], rp.inputs["Fac"])
    return rp.outputs["Color"]


def toon(color, name="Toon"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    dif.inputs["Color"].default_value = (1, 1, 1, 1)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs[6].default_value = kit.rgb(color)
    nt.links.new(_steps(nt, dif.outputs[0]), mix.inputs[7])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def strata(name="Strata", scale=0.45):
    """red canyon rock: horizontal colour bands from fract(Z), lit in two cel steps"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tcn = nt.nodes.new("ShaderNodeNewGeometry")          # world position: bands follow real height, not the box's unit coords
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = scale
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.08
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    frac = nt.nodes.new("ShaderNodeMath")
    frac.operation = "FRACT"
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.color_ramp.interpolation = "CONSTANT"
    cols = [kit.rgb(c) for c in STRATA]
    rp.color_ramp.elements[0].color = cols[0]
    rp.color_ramp.elements[1].position, rp.color_ramp.elements[1].color = 0.22, cols[1]
    for pos, c in ((0.45, cols[2]), (0.62, cols[3]), (0.85, cols[4])):
        e = rp.color_ramp.elements.new(pos)
        e.color = c
    nt.links.new(tcn.outputs["Position"], sp.inputs[0])
    nt.links.new(tcn.outputs["Position"], noise.inputs["Vector"])
    nt.links.new(sp.outputs["Z"], mul.inputs[0])
    nt.links.new(mul.outputs[0], add.inputs[0])
    nt.links.new(noise.outputs["Fac"], add.inputs[1])
    nt.links.new(add.outputs[0], frac.inputs[0])
    nt.links.new(frac.outputs[0], rp.inputs["Fac"])
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(rp.outputs["Color"], mix.inputs[6])
    nt.links.new(_steps(nt, dif.outputs[0]), mix.inputs[7])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


INK_SHELL = kit.emission(INK, 1.0, "InkShell")
INK_SHELL.use_backface_culling = True
INK_FLAT = kit.emission(INK, 1.0, "InkFlat")
_c = [0]


def nm(s):
    _c[0] += 1
    return f"{s}{_c[0]}"


def outline(ob, width=0.04):
    mod = ob.modifiers.new("Outline", "SOLIDIFY")
    mod.thickness, mod.offset, mod.use_flip_normals, mod.use_rim = width, 1.0, True, False
    mod.material_offset = 1
    ob.data.materials.append(INK_SHELL)
    return ob


def box(size, loc, mat, name="Box", rot=(0, 0, 0), line=True):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    ob = bpy.context.object
    ob.name = nm(name)
    ob.scale = size
    ob.rotation_euler = kit.rot(*rot)
    kit.assign(ob, mat)
    return outline(ob) if line else ob


def cyl(r, h, loc, mat, name="Cyl", rot=(0, 0, 0), line=True, verts=24):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=verts)
    ob = bpy.context.object
    ob.name = nm(name)
    ob.rotation_euler = kit.rot(*rot)
    kit.assign(ob, mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return outline(ob) if line else ob


def ball(r, loc, mat, name="Ball", line=True, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=32, ring_count=16)
    ob = bpy.context.object
    ob.name = nm(name)
    ob.scale = scale
    kit.assign(ob, mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return outline(ob) if line else ob


def flat_disc(rx, rz, loc, mat, name="FDisc"):
    """a filled circle standing upright, facing -Y (the camera side before the character is turned)"""
    bpy.ops.mesh.primitive_circle_add(vertices=40, radius=1.0, fill_type="NGON", location=loc)
    ob = bpy.context.object
    ob.name = nm(name)
    ob.rotation_euler = kit.rot(90, 0, 0)
    ob.scale = (rx, rz, 1)
    return kit.assign(ob, mat)


def flat_rect(wd, ht, loc, mat, name="FRect", tilt=0.0):
    ob = kit.rect(wd, ht, material=mat, loc=loc, name=nm(name))
    ob.rotation_euler = kit.rot(90, tilt, 0)
    return ob


def group(parts, root):
    for p in parts:
        kit.parent(p, root)


M_SAND, M_BALLAST, M_WOOD, M_RAIL = toon(SAND, "Sand"), toon(BALLAST, "Ballast"), toon(WOOD, "Wood"), toon(RAIL, "Rail")
M_BLACK, M_WHITE3D, M_ROCK = toon("#2A2A2E", "Black"), toon(WHITE, "White3D"), strata("Rock")


# ---------------------------------------------------------------- set pieces
def ground(cx, cy=0, size=260):
    return box((size, size, 0.4), (cx, cy, -0.2), M_SAND, "Ground", line=False)


def canyon_walls(cx, y0, y1, gap=11.0, height=26.0, lean=4.0):
    """two striped rock walls either side of the track, leaning out a little, plus some tall blocks behind for a skyline"""
    L = y1 - y0
    for side in (-1, 1):
        box((8, L, height), (cx + side * (gap + 4), (y0 + y1) / 2, height / 2), M_ROCK, "Wall", rot=(0, side * lean, 0), line=False)
        for i in range(4):
            yy = y0 + L * (0.15 + 0.22 * i)
            hh = height * random.uniform(0.6, 1.25)
            box((random.uniform(4, 9), random.uniform(6, 12), hh), (cx + side * (gap + 9 + random.uniform(0, 4)), yy, hh / 2), M_ROCK, "Butte", line=False)


def clouds(cx, y, z, n=3):
    for i in range(n):
        x = cx + random.uniform(-30, 30)
        s = random.uniform(2.5, 4.5)
        for dx, dz, r in ((0, 0, 1.0), (-1.1, -0.2, 0.75), (1.1, -0.2, 0.8), (0.2, -0.55, 0.7)):
            ball(r * s, (x + dx * s, y + random.uniform(-3, 3), z + dz * s + random.uniform(-2, 2)), M_WHITE3D, "Cloud", line=False, scale=(1, 0.6, 0.7))


def track(cx, y0, y1, curve=0.0, joints=False, dz=0.0, stones=120):
    parts = []
    n = int((y1 - y0) / 1.2)

    def xy(t):
        return cx + curve * t * t, y0 + t * (y1 - y0)

    def yaw(t):
        return math.degrees(math.atan2(2 * curve * t, (y1 - y0)))

    for i in range(n):
        t = i / max(1, n - 1)
        x, y = xy(t)
        parts.append(box((2.9, 0.42, 0.22), (x, y, dz + 0.11), M_WOOD, "Sleeper", rot=(0, 0, yaw(t)), line=False))
        if i % 2 == 0:
            parts.append(box((3.9, 1.3, 0.14), (x, y, dz + 0.02), M_BALLAST, "Ballast", rot=(0, 0, yaw(t)), line=False))
    seg = 6.0 if joints else 12.0
    m = int((y1 - y0) / seg)
    for j in range(m):
        ya, yb = y0 + j * seg, y0 + (j + 1) * seg - (0.22 if joints else 0.0)
        t = ((ya + yb) / 2 - y0) / (y1 - y0)
        x, _ = xy(t)
        yw = yaw(t)
        for side in (-0.78, 0.78):
            parts.append(box((0.16, yb - ya, 0.2), (x + side * math.cos(math.radians(yw)), (ya + yb) / 2, dz + 0.32), M_RAIL, "Rail", rot=(0, 0, yw), line=False))
            if joints:
                parts.append(box((0.3, 0.5, 0.26), (x + side * math.cos(math.radians(yw)), yb + 0.1, dz + 0.32), M_BLACK, "Fishplate", rot=(0, 0, yw), line=False))
    for _ in range(stones):                                      # loose stones along the near part of the track
        t = random.uniform(0, 0.35)
        x, y = xy(t)
        parts.append(box((random.uniform(0.12, 0.3),) * 3, (x + random.uniform(-2.3, 2.3), y, dz + 0.08), M_BALLAST, "Stone", rot=(0, 0, random.uniform(0, 90)), line=False))
    return parts


def train(loc, color="#B6322C"):
    root = kit.empty(loc, nm("Train"))
    m_body = toon(color, nm("TrainBody"))
    parts = [box((2.3, 5.4, 1.7), (0, 0, 1.35), m_body, "Loco"), box((2.5, 2.0, 2.5), (0, -1.9, 2.0), m_body, "Cab"),
             box((2.2, 1.7, 1.2), (0, -1.9, 3.7), M_BLACK, "Roof"), cyl(0.4, 1.4, (0, 1.6, 2.8), M_BLACK, "Stack"),
             cyl(0.58, 0.7, (0, 1.6, 3.6), M_BLACK, "StackTop"), box((2.4, 0.8, 0.7), (0, 2.9, 0.55), M_BLACK, "Cowcatcher", rot=(35, 0, 0)),
             cyl(0.5, 0.2, (0, 2.75, 2.1), toon("#FFE08A", nm("Lamp")), "Lamp", rot=(90, 0, 0))]
    for yy in (-1.7, 0.0, 1.7):
        for sx in (-1.2, 1.2):
            parts.append(cyl(0.58, 0.26, (sx, yy, 0.58), M_BLACK, "Wheel", rot=(0, 90, 0)))
    group(parts, root)
    return root


def character(loc, cam_pos, shirt=SHIRT_TEAL, hat="cap", face="awake", scale=1.0, mood="neutral"):
    """flat paper cut-out standing in the 3D world, turned to face the camera. Returns (root, head)"""
    dx, dy = cam_pos[0] - loc[0], cam_pos[1] - loc[1]
    yaw = math.degrees(math.atan2(dx, -dy))                      # its -Y face points at the camera
    root = kit.empty(loc, nm("Char"))
    root.rotation_euler = kit.rot(0, 0, yaw)
    root.scale = (scale,) * 3
    m_shirt = kit.emission(shirt, 1.0, nm("Shirt"))
    m_shirt_dark = kit.emission("#1B1B1B", 1.0, nm("Vest"))
    parts = []
    # legs, shoes
    for sx in (-0.17, 0.17):
        parts.append(flat_rect(0.1, 1.0, (sx, 0.0, 0.5), INK_FLAT, "Leg"))
        parts.append(flat_disc(0.2, 0.09, (sx + (0.05 if sx > 0 else -0.05), -0.02, 0.06), INK_FLAT, "Shoe"))
    # body (outline then fill), vest line, arms, hands
    parts.append(flat_disc(0.52, 0.72, (0, 0.03, 1.5), INK_FLAT, "BodyInk"))
    parts.append(flat_disc(0.46, 0.66, (0, 0.0, 1.5), m_shirt, "Body"))
    parts.append(flat_rect(0.06, 1.1, (0, -0.01, 1.5), m_shirt_dark, "Buttons"))
    for sx, tilt in ((-0.62, 12), (0.62, -12)):
        parts.append(flat_rect(0.1, 0.95, (sx, -0.02, 1.35), INK_FLAT, "Arm", tilt=tilt))
        parts.append(flat_disc(0.12, 0.12, (sx + (0.1 if sx > 0 else -0.1), -0.03, 0.9), kit.emission(WHITE, 1.0, nm("Hand")), "Hand"))
        parts.append(flat_disc(0.15, 0.15, (sx + (0.1 if sx > 0 else -0.1), -0.02, 0.9), INK_FLAT, "HandInk"))
    # head
    head = kit.empty((0, 0, 2.55), nm("Head"))
    hp = [flat_disc(0.62, 0.62, (0, 0.03, 0), INK_FLAT, "SkullInk"), flat_disc(0.56, 0.56, (0, 0.0, 0), kit.emission(WHITE, 1.0, nm("Skull")), "Skull")]
    if face == "awake":
        for sx in (-0.19, 0.19):
            hp.append(flat_disc(0.07, 0.1, (sx, -0.02, 0.08), INK_FLAT, "Eye"))
        brow = {"neutral": 0, "angry": -1, "worried": 1}[mood]
        for sx in (-0.19, 0.19):
            hp.append(flat_rect(0.2, 0.05, (sx, -0.02, 0.27), INK_FLAT, "Brow", tilt=(-14 if sx < 0 else 14) * brow))
        hp.append(flat_rect(0.22, 0.04, (0, -0.02, -0.22), INK_FLAT, "Mouth"))
    else:
        for sx in (-0.19, 0.19):
            hp.append(flat_rect(0.18, 0.045, (sx, -0.02, 0.06), INK_FLAT, "EyeShut"))
        hp.append(flat_disc(0.07, 0.09, (0, -0.02, -0.22), INK_FLAT, "MouthO"))
    if hat == "cap":
        hp += [flat_disc(0.6, 0.3, (0, -0.01, 0.5), INK_FLAT, "CapInk"), flat_disc(0.56, 0.26, (0, -0.02, 0.5), kit.emission("#3E66B8", 1.0, nm("Cap")), "Cap"),
               flat_rect(1.2, 0.09, (0.08, -0.03, 0.36), INK_FLAT, "Brim")]
    elif hat == "bowler":
        hp += [flat_disc(0.5, 0.42, (0, -0.01, 0.6), INK_FLAT, "Bowler"), flat_rect(1.45, 0.09, (0, -0.02, 0.4), INK_FLAT, "BowlerBrim")]
    elif hat == "top":
        hp += [flat_rect(0.78, 0.7, (0, -0.01, 0.78), INK_FLAT, "TopHat"), flat_rect(1.35, 0.09, (0, -0.02, 0.44), INK_FLAT, "TopBrim")]
    group(hp, head)
    group(parts + [head], root)
    return root, head


# camera set-ups per scene (from, to, aim from, aim to); characters are turned toward "from"
X = [0, 70, 140, 210, 280]
SHOTS = [
    ((3.4, -10, 1.6), (2.2, -7.5, 1.9), (0.5, 40, 3.0), (0.3, 30, 2.6)),
    ((X[1] + 2.4, -4.6, 2.5), (X[1] + 1.8, -3.6, 2.3), (X[1] - 0.9, 0.2, 2.4), (X[1] - 1.0, 0.1, 2.6)),
    ((X[2] - 6.0, -9.0, 17.5), (X[2] - 4.5, -7.0, 16.8), (X[2] + 0.5, 3.0, 15.4), (X[2] + 0.3, 5.0, 15.6)),
    ((X[3] + 4.2, -17, 0.9), (X[3] + 2.8, -13, 1.1), (X[3] + 1.5, 10, 1.8), (X[3] + 0.5, 2, 1.6)),
    ((X[4] + 0.6, -7.8, 2.6), (X[4] + 0.2, -6.4, 2.4), (X[4], 1.0, 2.1), (X[4], 1.0, 2.2)),
]

# ---------------------------------------------------------------- SCENE 1: the canyon straight, a train coming, the narrator at the side
ground(X[0])
canyon_walls(X[0], -20, 220)
clouds(X[0], 160, 34)
track(X[0], -14, 220)
t1 = train((X[0], 110, 0))
kit.key(t1, "location", [(1, (X[0], 110, 0)), (kit.f(SCENES[0][1]), (X[0], 20, 0))], ease="linear")
n1, n1h = character((X[0] - 3.2, -1.5, 0), SHOTS[0][0], shirt=SHIRT_TEAL, hat="cap", mood="neutral")
for f in range(1, kit.f(SCENES[0][1]) + 1, 3):                                                  # a small talk bob
    t = (f - 1) / FPS
    n1h.rotation_euler = kit.rot(0, 3 * math.sin(t * 6), 0)
    n1h.keyframe_insert("rotation_euler", frame=f)

# ---------------------------------------------------------------- SCENE 2: the cab, the engineer nodding off, the straight through the window
ground(X[1])
box((5.0, 0.3, 4.2), (X[1], 2.3, 2.1), toon("#8F3A33", "CabWall"), "CabWall")
box((2.4, 0.1, 1.5), (X[1] + 0.7, 2.1, 2.7), kit.emission("#9FD8F0", 1.0, "WindowSky"), "Window", line=False)
canyon_walls(X[1] + 0.7, 6, 120, gap=9, height=22)
track(X[1] + 0.7, 2.6, 120, dz=-0.6, stones=0)
box((5.0, 3.8, 0.3), (X[1], 0.4, 0.15), toon("#5A3B25", "CabFloor"), "CabFloor", line=False)
box((1.3, 1.0, 0.9), (X[1] - 1.2, 0.0, 0.45), M_BLACK, "Seat")
cyl(0.07, 1.4, (X[1] + 1.0, 0.7, 1.0), M_BLACK, "Lever", rot=(25, 0, 0))
cyl(0.35, 0.1, (X[1] + 1.0, 0.1, 1.75), M_BLACK, "LeverKnob", rot=(90, 0, 0))
eng, eng_head = character((X[1] - 1.2, -0.1, 0.9), SHOTS[1][0], shirt=SHIRT_BLUE, hat="cap", face="asleep", scale=0.85)
f2a, f2b = kit.f(SCENES[1][0]), kit.f(SCENES[1][1])
for f in range(f2a, f2b + 1, 2):                                                                  # droop, jerk, droop
    t = (f - f2a) / FPS
    eng_head.rotation_euler = kit.rot(34 * max(0.0, math.sin(t * 1.7)) ** 2, 0, 0)
    eng_head.keyframe_insert("rotation_euler", frame=f)
for i in range(3):                                                                               # Z Z Z floating up
    z = kit.text("Z", font="Montserrat-Bold", size=0.3 + 0.1 * i, extrude=0.03, material=toon("#F4F4F4", nm("Zmat")),
                 loc=(X[1] - 0.5 + 0.3 * i, -0.6, 3.0), rot=(90, 0, -15), name=f"Z{i}")
    outline(z, 0.02)
    f0 = f2a + kit.f(0.6 + 0.9 * i) - 1
    kit.key(z, "location", [(f0, (X[1] - 0.5 + 0.3 * i, -0.6, 2.9)), (f0 + 40, (X[1] - 0.1 + 0.4 * i, -0.6, 3.9 + 0.3 * i))], ease="out")
    kit.fade(z, [(f0, 0.0), (f0 + 6, 1.0), (f0 + 30, 1.0), (f0 + 40, 0.0)])

# ---------------------------------------------------------------- SCENE 3: a trestle over a canyon, two surveyors, dutch angle
Z3 = 15.0
box((300, 300, 0.6), (X[2], 0, -24.3), toon("#2F5CB0", "River"), "River", line=False)       # the canyon floor far below
for side in (-1, 1):                                                                             # the canyon rims either side
    box((60, 300, 24), (X[2] + side * 42, 0, 12 - 24), M_ROCK, "Rim", line=False)
    box((60, 300, 0.5), (X[2] + side * 42, 0, 0.0), M_SAND, "RimTop", line=False)
for yy in range(-30, 90, 6):                                                                    # trestle: posts and crossed braces
    for sx in (-1.3, 1.3):
        box((0.35, 0.35, Z3 + 24), (X[2] + sx, yy, (Z3 - 24) / 2), M_WOOD, "Post", line=False)
    for zz in range(-20, int(Z3), 6):
        box((2.9, 0.22, 0.22), (X[2], yy, zz), M_WOOD, "BraceA", rot=(0, 0, 0), line=False)
        box((0.22, 0.22, 7.2), (X[2], yy, zz + 3), M_WOOD, "BraceX", rot=(0, 42, 0), line=False)
        box((0.22, 0.22, 7.2), (X[2], yy, zz + 3), M_WOOD, "BraceX2", rot=(0, -42, 0), line=False)
box((3.6, 130, 0.5), (X[2], 30, Z3 - 0.25), M_WOOD, "Deck", line=False)
track(X[2], -34, 96, dz=Z3, stones=0)
s1, s1h = character((X[2] - 1.6, 2.2, Z3 + 0.3), SHOTS[2][0], shirt=SHIRT_GOLD, hat="bowler", mood="angry")
s2, s2h = character((X[2] + 1.5, 1.0, Z3 + 0.3), SHOTS[2][0], shirt=SHIRT_TEAL, hat="cap", mood="worried", scale=0.95)
plan = flat_rect(1.5, 1.0, (X[2] + 0.1, 0.0, Z3 + 1.7), kit.emission("#F2EDE0", 1.0, "Plan"), "Plan", tilt=-8)
plan.rotation_euler = kit.rot(90, -8, math.degrees(math.atan2(SHOTS[2][0][0] - X[2], -(SHOTS[2][0][1] - 0.0))))
f3a, f3b = kit.f(SCENES[2][0]), kit.f(SCENES[2][1])
for f in range(f3a, f3b + 1, 3):                                                                  # the angry one shakes his head
    t = (f - f3a) / FPS
    s1h.rotation_euler = kit.rot(0, 0, 10 * math.sin(t * 5.5))
    s1h.keyframe_insert("rotation_euler", frame=f)
clouds(X[2], 120, 30, n=4)

# ---------------------------------------------------------------- SCENE 4: the fix, a curving track with joints, low angle, train bobbing past
ground(X[3])
canyon_walls(X[3] + 5, -20, 200, gap=14)
clouds(X[3], 150, 32)
track(X[3], -20, 130, curve=16.0, joints=True)
t4 = train((X[3], 60, 0), color="#2E6FB7")
f4a, f4b = kit.f(SCENES[3][0]), kit.f(SCENES[3][1])
kit.key(t4, "location", [(f4a, (X[3] + 16.0 * (56 / 150) ** 2, 36, 0)), (f4b, (X[3] + 16.0 * (4 / 150) ** 2, -16, 0))], ease="linear")
kit.key(t4, "rotation_euler", [(f4a, kit.rot(0, 0, -16)), (f4b, kit.rot(0, 0, -2))], ease="linear")
for f in range(f4a, f4b + 1, 4):                                                                  # clickety bob on each joint
    k = (f - f4a) // 4
    t4.location.z = 0.0 if k % 2 == 0 else 0.08
    t4.keyframe_insert("location", index=2, frame=f)

# ---------------------------------------------------------------- SCENE 5: the station street, the narrator wraps up
ground(X[4])
for i, (wd, ht, col) in enumerate(((5.5, 7.5, "#C96A3B"), (6.5, 9.5, "#4F7FBF"), (5.5, 8.5, "#D9A441"), (6.5, 7.5, "#8E5BA6"))):
    x = X[4] - 9.5 + i * 6.4
    box((wd, 4, ht), (x, 9, ht / 2), toon(col, nm("Facade")), "Facade")
    box((wd + 0.6, 1.7, 0.28), (x, 6.9, 3.5), M_WOOD, "Awning")
    for wx in (-1.3, 1.3):
        box((1.2, 0.1, 1.5), (x + wx, 6.95, 5.4), kit.emission("#1F2A3A", 1.0, nm("Glass")), "Win", line=False)
    box((wd * 0.9, 0.1, 0.9), (x, 6.9, ht - 0.7), kit.emission("#F2EDE0", 1.0, nm("Sign")), "Sign", line=False)
for px in (-7, 7):
    cyl(0.12, 4.2, (X[4] + px, 3.5, 2.1), M_BLACK, "LampPost")
    ball(0.45, (X[4] + px, 3.5, 4.4), toon("#FFE08A", nm("LampGlow")), "LampHead")
nar, nar_head = character((X[4], 1.0, 0), SHOTS[4][0], shirt=SHIRT_RED, hat="top", mood="neutral", scale=1.05)
f5a, f5b = kit.f(SCENES[4][0]), kit.f(SCENES[4][1])
for f in range(f5a, f5b + 1, 3):
    t = (f - f5a) / FPS
    nar_head.rotation_euler = kit.rot(3 * math.sin(t * 6), 0, 2.5 * math.sin(t * 3))
    nar_head.keyframe_insert("rotation_euler", frame=f)

# ---------------------------------------------------------------- camera: five set-ups with hard cuts (keys one frame apart)
cam = kit.camera(SHOTS[0][0], look_at=SHOTS[0][2], lens=30)
aim = kit.aim(cam)
for i, (ca, cb, aa, ab) in enumerate(SHOTS):
    fa = kit.f(SCENES[i][0]) + (1 if i else 0)
    fb = kit.f(SCENES[i][1])
    kit.key(cam, "location", [(fa, ca), (fb, cb)], ease="in_out")
    kit.key(aim, "location", [(fa, aa), (fb, ab)], ease="in_out")
kit.shake(cam, strength=0.012, speed=20)

# light: one hard sun for the cel steps, no soft-shadow jitter
sun = kit.light("SUN", (30, -40, 60), (0, 0, 0), power=4.0, color="#FFF6E8", name="Sun")
sun.data.angle = math.radians(2.0)
for lt in bpy.data.lights:
    if hasattr(lt, "use_shadow_jitter"):
        lt.use_shadow_jitter = False

# ---------------------------------------------------------------- captions: parented to the camera, right in front of the lens so nothing hides them
cap_root = kit.empty((0, 0, 0), "Captions")
cap_root.parent = cam
cap_root.location, cap_root.rotation_euler = (0, -0.36, -1.25), (0, 0, 0)
for i, (t, txt) in enumerate(CAPTIONS):
    f0 = kit.f(t)
    f1 = kit.f(CAPTIONS[i + 1][0]) if i + 1 < len(CAPTIONS) else end + 1
    grp = kit.empty((0, 0, 0), f"Cap{i}")
    grp.parent = cap_root
    grp.location = (0, 0, 0)
    for dx, dz in ((-0.006, 0), (0.006, 0), (0, -0.006), (0, 0.006), (-0.0045, -0.0045), (0.0045, 0.0045), (-0.0045, 0.0045), (0.0045, -0.0045), (0.004, -0.008)):
        o = kit.text(txt, font="Montserrat-Bold", size=0.082, color=INK, strength=1.0, loc=(dx, dz, -0.003), rot=(0, 0, 0), name=f"CapInk{i}")
        o.parent = grp
    wtxt = kit.text(txt, font="Montserrat-Bold", size=0.082, color=WHITE, strength=1.0, loc=(0, 0, 0), rot=(0, 0, 0), name=f"CapText{i}")
    wtxt.parent = grp
    kit.key(grp, "scale", [(f0 - 1, (0.001,) * 3), (f0, (0.001,) * 3), (f0 + 4, (1.1,) * 3), (f0 + 8, (1.0,) * 3), (f1 - 1, (1.0,) * 3), (f1, (0.001,) * 3)], ease="out")

kit.post(bloom=0, vignette=0.12, grain=0.018)
