"""Example: size comparison. Six things at true relative scale on one dark floor, smallest to biggest:
human 1.8 m, giraffe 5.5 m, T. rex 12 m, blue whale 30 m, Statue of Liberty 93 m, Eiffel Tower 330 m.
The camera starts close on the human and dollies right / pulls back; each label fades in when the camera reaches its object;
the last second is a wide shot where the tiny human is still marked by an accent ring.

  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/size_compare.py --out shots/size_compare/size_compare.mp4 --frames 180

Labels are flat decals on the floor in front of each object (name in white, height in the accent colour), scaled with the object.
"""
import math

import bmesh
import bpy
from mathutils import Vector

import blender_kit as kit

a = kit.args()
END = a.frames
ACCENT = "#E0A040"
E = math.radians(26)                    # camera elevation above the floor, constant: floor labels are stretched to match it
SINE, COSE = math.sin(E), math.cos(E)
K = 1.0 / SINE                          # label stretch along the floor so the text looks upright to the camera
HF = 0.5786                             # frame height / camera distance for a 35 mm lens on 16:9 (1920x1080)

kit.setup(world="#0A0D12", motion_blur=0.2)


# ------------------------------------------------------------------------------------------------ floor with a soft glow
def glow(fl, center, radius, c_in, c_out):
    mat = fl.data.materials[0]
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    co = nt.nodes.new("ShaderNodeTexCoord")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (center[0], center[1], 0.0)
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.interpolation_type = "SMOOTHSTEP"
    rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = 0.0, radius
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value, mix.inputs[7].default_value = kit.rgb(c_in), kit.rgb(c_out)
    nt.links.new(co.outputs["Object"], sub.inputs[0])
    nt.links.new(sub.outputs[0], ln.inputs[0])
    nt.links.new(ln.outputs["Value"], rng.inputs["Value"])
    nt.links.new(rng.outputs[0], mix.inputs[0])
    nt.links.new(mix.outputs[2], p.inputs["Base Color"])


floor = kit.floor("#0C0F14", z=0.0, size=16000, roughness=0.6)
glow(floor, (150, 0), 1000, "#171C26", "#05070A")


# ------------------------------------------------------------------------------------------------ shape helpers
def _fin(ob, grp, mat, loc, scl, rot):
    ob.location, ob.scale = loc, scl
    ob.rotation_euler = tuple(math.radians(v) for v in rot)
    kit.assign(ob, mat)
    kit.parent(ob, grp)
    return ob


def box(grp, mat, size, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    return _fin(bpy.context.active_object, grp, mat, loc, size, rot)


def ball(grp, mat, radii, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=32, ring_count=16)
    ob = bpy.context.active_object
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    if isinstance(radii, (int, float)):
        radii = (radii,) * 3
    return _fin(ob, grp, mat, loc, radii, rot)


def limb(grp, mat, p0, p1, r0, r1=None, verts=20):
    """A cylinder or cone between two points (local to grp)."""
    r1 = r0 if r1 is None else r1
    v0, v1 = Vector(p0), Vector(p1)
    d = v1 - v0
    bpy.ops.mesh.primitive_cone_add(radius1=r0, radius2=r1, depth=d.length, vertices=verts)
    ob = bpy.context.active_object
    ob.location = (v0 + v1) / 2
    ob.rotation_euler = Vector((0, 0, 1)).rotation_difference(d).to_euler()
    kit.assign(ob, mat)
    kit.parent(ob, grp)
    return ob


def loft(name, rings, sub=1, tri=False, cap_top=True):
    """Square-section frustum stack. rings = [(z, width_x, width_y), ...] bottom to top."""
    n = 4 * sub
    verts, faces = [], []
    for z, wx, wy in rings:
        corners = [(-wx / 2, -wy / 2), (wx / 2, -wy / 2), (wx / 2, wy / 2), (-wx / 2, wy / 2)]
        for i in range(4):
            p, q = corners[i], corners[(i + 1) % 4]
            for j in range(sub):
                t = j / sub
                verts.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, z))
    for r in range(len(rings) - 1):
        for i in range(n):
            a0, b0 = r * n + i, r * n + (i + 1) % n
            c0, d0 = (r + 1) * n + (i + 1) % n, (r + 1) * n + i
            if tri:
                faces += [(a0, b0, c0), (a0, c0, d0)]
            else:
                faces.append((a0, b0, c0, d0))
    if cap_top:
        faces.append(tuple((len(rings) - 1) * n + i for i in range(n)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ------------------------------------------------------------------------------------------------ the six objects
def build_human(x):
    g = kit.empty((x, 0, 0), "Human")
    m = kit.matte(ACCENT, 0.5, "Human")
    for sx in (-1, 1):
        limb(g, m, (sx * 0.1, 0, 0.0), (sx * 0.1, 0, 0.85), 0.085)
        limb(g, m, (sx * 0.27, 0, 1.42), (sx * 0.3, 0, 0.78), 0.05)
    box(g, m, (0.4, 0.22, 0.64), (0, 0, 1.17))
    limb(g, m, (0, 0, 1.45), (0, 0, 1.58), 0.05)
    ball(g, m, 0.125, (0, 0, 1.675))
    return g


def build_giraffe(x):
    g = kit.empty((x, 0, 0), "Giraffe")
    m = kit.matte("#A3ABB8", 0.6, "Giraffe")
    for lx in (-0.85, 0.85):
        for ly in (-0.22, 0.22):
            limb(g, m, (lx, ly, 0.0), (lx, ly, 2.6), 0.1, 0.12)
    ball(g, m, (1.25, 0.45, 0.55), (0, 0, 2.95))
    limb(g, m, (1.0, 0, 3.3), (1.9, 0, 5.1), 0.27, 0.16)
    ball(g, m, (0.38, 0.17, 0.17), (2.15, 0, 5.15))
    for sy in (-0.07, 0.07):
        limb(g, m, (1.95, sy, 5.28), (1.95, sy, 5.5), 0.045, 0.03)
    limb(g, m, (-1.2, 0, 3.25), (-1.45, 0, 2.1), 0.06, 0.03)
    return g


def build_trex(x):
    g = kit.empty((x, 0, 0), "TRex")
    m = kit.matte("#8E98A8", 0.6, "TRex")
    ball(g, m, (3.0, 1.25, 1.7), (0, 0, 3.5))
    for sy in (-0.95, 0.95):
        ball(g, m, (0.9, 0.55, 1.45), (0.2, sy, 2.0))
        limb(g, m, (0.45, sy, 1.7), (0.95, sy, 0.15), 0.42, 0.28)
        box(g, m, (1.2, 0.5, 0.26), (1.5, sy, 0.13))
        limb(g, m, (2.6, sy * 0.7, 3.9), (3.3, sy * 0.7, 3.25), 0.13, 0.08)
    limb(g, m, (-0.4, 0, 3.7), (-5.9, 0, 2.55), 1.1, 0.08)
    limb(g, m, (1.0, 0, 3.9), (4.2, 0, 5.3), 0.9, 0.55)
    ball(g, m, (1.2, 0.62, 0.68), (4.95, 0, 5.5))
    ball(g, m, (0.95, 0.45, 0.2), (5.0, 0, 5.0))
    return g


def build_whale(x):
    g = kit.empty((x, 0, 0), "Whale")
    m = kit.matte("#6F8CAB", 0.55, "Whale")
    ball(g, m, (12.0, 2.9, 2.7), (2.6, 0, 2.7))
    limb(g, m, (-4.5, 0, 2.7), (-14.8, 0, 2.7), 1.85, 0.5, verts=24)
    box(g, m, (0.6, 7.2, 0.35), (-15.1, 0, 2.7), rot=(0, 0, 0))
    limb(g, m, (5.0, -2.2, 1.8), (2.6, -4.4, 1.3), 0.55, 0.2)
    limb(g, m, (5.0, 2.2, 1.8), (2.6, 4.4, 1.3), 0.55, 0.2)
    return g


def build_liberty(x):
    g = kit.empty((x, 0, 0), "Liberty")
    m = kit.matte("#8FB0A6", 0.6, "Liberty")
    ped = loft("Pedestal", [(0, 30, 30), (18, 23, 23), (18, 25, 25), (40, 19, 19), (40, 21, 21), (47, 17, 17)])
    kit.assign(ped, m)
    kit.parent(ped, g)
    robe = loft("Robe", [(47, 12, 9), (58, 10.5, 8), (70, 8.5, 6), (77, 7, 5)])
    kit.assign(robe, m)
    kit.parent(robe, g)
    limb(g, m, (0, 0, 77), (0, 0, 80), 1.5, 1.2)
    ball(g, m, 2.6, (0, 0, 81))
    for ang in (-66, -44, -22, 0, 22, 44, 66):
        s, c = math.sin(math.radians(ang)), math.cos(math.radians(ang))
        p0 = (2.3 * s, 0, 81.6 + 2.3 * c)
        limb(g, m, p0, (p0[0] + 3.2 * s, 0, p0[2] + 3.2 * c), 0.35, 0.05, verts=8)
    limb(g, m, (3.3, 0, 75), (5.4, 0, 89.5), 1.05, 0.8)
    limb(g, m, (5.4, 0, 89.0), (5.4, 0, 91.4), 1.6, 0.9)
    flame = ball(g, kit.emission(ACCENT, 3.0, "Torch"), (1.1, 1.1, 1.6), (5.4, 0, 91.4))
    limb(g, m, (-3.5, 0, 72), (-5.2, -1.5, 66.5), 1.0, 0.8)
    box(g, m, (3.4, 0.9, 5.0), (-5.6, -1.9, 66.0), rot=(0, 0, 18))
    return g


def build_eiffel(x):
    g = kit.empty((x, 0, 0), "Eiffel")
    m = kit.matte("#A9A294", 0.6, "Eiffel")
    prof = [(0, 125), (57, 62), (115, 34), (190, 19), (276, 11), (300, 6), (330, 1.4)]
    rings = []
    for (z0, w0), (z1, w1) in zip(prof, prof[1:]):
        n = max(2, int(round((z1 - z0) / 14)))
        for j in range(n):
            t = j / n
            rings.append((z0 + (z1 - z0) * t, w0 + (w1 - w0) * t, w0 + (w1 - w0) * t))
    rings.append((330, 1.4, 1.4))
    lat = loft("Lattice", rings, sub=4, tri=True, cap_top=False)
    mod = lat.modifiers.new("Wire", "WIREFRAME")
    mod.thickness, mod.use_even_offset, mod.use_replace, mod.use_boundary = 1.7, True, True, True
    kit.assign(lat, m)
    kit.parent(lat, g)
    for z, w, h in ((57, 66, 4.0), (115, 37, 3.5), (276, 14, 3.0)):
        box(g, m, (w, w, h), (0, 0, z))
    return g


# x positions along the floor (free: only the sizes are true), local label data
OBJECTS = [
    # name, height text, builder, x, floor depth (half), name size, label fade-in start frame
    ("HUMAN", "1.8 m", build_human, 0.0, 0.3, 0.18, 6),
    ("GIRAFFE", "5.5 m", build_giraffe, 7.0, 0.6, 0.6, 22),
    ("T. REX", "12 m", build_trex, 28.0, 1.8, 0.6, 49),
    ("BLUE WHALE", "30 m", build_whale, 82.0, 3.6, 2.2, 76),
    ("STATUE OF LIBERTY", "93 m", build_liberty, 160.0, 15.0, 11.5, 103),
    ("EIFFEL TOWER", "330 m", build_eiffel, 290.0, 62.5, 31.0, 128),
]
STOPS = [   # frame, aim x, frame height in metres at the aim, ring radius around the human, foot position in frame
    (1, 0.0, 3.6, 0.8, 0.42),
    (31, 7.4, 11.0, 1.3, 0.42),
    (58, 28.0, 12.0, 1.7, 0.44),
    (85, 82.0, 26.0, 2.4, 0.54),
    (112, 160.0, 190.0, 6.0, 0.42),
    (142, 290.0, 600.0, 11.0, 0.42),
    (END, 160.0, 700.0, 13.5, 0.42),
]
STOP_D = [s[2] / HF for s in STOPS]

for name, height, builder, x, depth, sn, f_in in OBJECTS:
    builder(x)
    sh = sn * 1.5
    z0 = 0.1 * sn
    grp = kit.empty((x, 0, z0), "Label." + name)
    y1 = -(depth + 0.7 * sn * K)
    y2 = y1 - K * (0.7 * sn + 0.5 * sh)
    t1 = kit.text(name, "Montserrat-Bold", size=sn, color="#EEF1F5", strength=1.8, rot=(0, 0, 0), spacing=1.15,
                  loc=(0, y1, 0), name="Name." + name)
    t2 = kit.text(height, "Anton-Regular", size=sh, color=ACCENT, strength=1.6, rot=(0, 0, 0),
                  loc=(0, y2, 0), name="Height." + name)
    for t in (t1, t2):
        t.scale = (1.0, K, 1.0)
        kit.parent(t, grp)
        kit.fade(t, [(f_in, 0.0), (f_in + 16, 1.0)])

# a ring on the floor around the human: it keeps the tiny reference findable in the wide shot
ring_me = bpy.data.meshes.new("Ring")
rv, rf = [], []
for i in range(72):
    ang = 2 * math.pi * i / 72
    rv += [(0.8 * math.cos(ang), 0.8 * math.sin(ang), 0), (math.cos(ang), math.sin(ang), 0)]
for i in range(72):
    j = (i + 1) % 72
    rf.append((2 * i, 2 * i + 1, 2 * j + 1, 2 * j))
ring_me.from_pydata(rv, [], rf)
ring_me.update()
ring = bpy.data.objects.new("Ring", ring_me)
bpy.context.scene.collection.objects.link(ring)
ring.location = (0, 0, 0.012)
kit.assign(ring, kit.emission(ACCENT, 2.2, "Ring"))


# ------------------------------------------------------------------------------------------------ lights (three suns, true to scale)
kit.light("SUN", (-60, -90, 75), (0, 0, 0), power=4.6, color="#FFD9B0", name="Key")
kit.light("SUN", (90, -60, 30), (0, 0, 0), power=1.1, color="#B5CCFF", name="Fill")
kit.light("SUN", (40, 90, 60), (0, 0, 0), power=1.3, color="#CFE0FF", name="Rim")


# ------------------------------------------------------------------------------------------------ camera, dust, ring: one path
def smooth01(t):
    return t * t * (3 - 2 * t)


def state(fr):
    i = 0
    while i < len(STOPS) - 2 and fr > STOPS[i + 1][0]:
        i += 1
    s0, s1 = STOPS[i], STOPS[i + 1]
    t = min(1.0, max(0.0, (fr - s0[0]) / (s1[0] - s0[0])))
    u = 0.15 * t + 0.85 * smooth01(t)
    H = s0[2] * (s1[2] / s0[2]) ** u
    ax = s0[1] + (s1[1] - s0[1]) * u
    r = s0[3] * (s1[3] / s0[3]) ** u
    fb = s0[4] + (s1[4] - s0[4]) * u
    return ax, H, r, fb


cam = kit.camera((0, -6, 2), look_at=(0, 0, 0.7), lens=35)
cam.data.clip_end = 9000
dof = kit.depth_of_field(cam, focus=5.5, fstop=4.0)
dust = kit.motes(count=120, center=(0, 0, 0), spread=(10, 8, 4.5), size=0.01, strength=1.5)
for m_ in dust.children:
    m_.visible_shadow = False

frames = sorted(set(list(range(1, END + 1, 2)) + [END]))
k_cam, k_aim, k_foc, k_clip, k_dl, k_ds, k_ring = [], [], [], [], [], [], []
for fr in frames:
    ax, H, r, fb = state(fr)
    d = H / HF
    az = (0.5 - fb) * H / COSE
    phi = math.radians(-15.0 + 29.0 * (fr - 1) / (END - 1))
    k_cam.append((fr, (ax + d * math.sin(phi) * COSE, -d * math.cos(phi) * COSE, az + d * SINE)))
    k_aim.append((fr, (ax, 0, az)))
    k_foc.append((fr, d))
    k_clip.append((fr, 0.1 * d))
    s = d / 6.0
    k_dl.append((fr, (ax * 0.88, 0, 0.4 * d)))
    k_ds.append((fr, (s, s, s)))
    k_ring.append((fr, (r, r, 1.0)))
kit.key(cam, "location", k_cam, ease="linear")
kit.key(kit.aim(cam), "location", k_aim, ease="linear")
kit.key(dof, "focus_distance", k_foc, ease="linear")
kit.key(cam.data, "clip_start", k_clip, ease="linear")
kit.key(dust, "location", k_dl, ease="linear")
kit.key(dust, "scale", k_ds, ease="linear")
kit.key(ring, "scale", k_ring, ease="linear")

kit.post(bloom=0.28, vignette=0.45, grain=0.03)
