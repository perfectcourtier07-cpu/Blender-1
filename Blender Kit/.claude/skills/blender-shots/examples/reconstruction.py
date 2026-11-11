"""Example: a 3D reconstruction, the clean isometric documentary look. A grey airplane cabin cut open from above, rows of
seats, red and blue mannequins, one row lit with a callout ("ROW 13 · 34,000 FT"); the cabin lights drop out on the beat, the
camera dollies slowly down the aisle. 180 frames at 30 fps. No downloaded models: everything is primitives.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/reconstruction.py --out shots/reconstruction/reconstruction.mp4 --frames 180 --stills 1,75,150
Change ROW, the callout lines, the mannequin seats and the beats at the top for another story.
"""
import math

import bpy
import blender_kit as kit

a = kit.args()
end = a.frames
ROW = 13                      # the row the story is about
ROWS, PITCH, SEAT_W = 26, 0.82, 0.5
LINE1, LINE2 = f"ROW {ROW}", "34,000 FT  ·  174 PASSENGERS"
T_LIGHT, T_CALLOUT, T_POWER = 1.2, 2.4, 4.0      # seconds: the row lights up, the callout lands, the cabin power drops out
GREY, SEAT, RED, BLUE, ACCENT = "#C9CDD3", "#9AA0A8", "#D63B3B", "#2F6FD6", "#E0A040"

kit.setup(world="#05070A", look="Medium High Contrast", motion_blur=0.25)


def row_y(r):
    return (r - 1) * PITCH


def box(name, size, loc, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0], size[1], size[2])                   # primitive_cube_add size=1 is a 1 m cube: scale = edge length
    ob.rotation_euler = kit.rot(*rot)
    return kit.assign(ob, mat)


# ---------------------------------------------------------------- the cabin: floor, two low walls with windows, no ceiling (cutaway)
grey = kit.matte(GREY, 0.75, "CabinGrey")
dark = kit.matte("#3C4149", 0.6, "CabinDark")
L = ROWS * PITCH + 2.0
box("Floor", (3.8, L, 0.1), (0, L / 2 - 1.0, -0.05), grey)
for side in (-1, 1):
    box(f"Wall{side}", (0.12, L, 1.5), (side * 1.9, L / 2 - 1.0, 0.75), grey)
    for r in range(ROWS):
        box(f"Win{side}{r}", (0.14, 0.34, 0.26), (side * 1.9, row_y(r + 1) + 0.1, 0.95), dark)
box("Aisle", (0.56, L, 0.02), (0, L / 2 - 1.0, 0.01), kit.matte("#B0B5BC", 0.8, "AisleStrip"))

# ---------------------------------------------------------------- seats: 3 + 3 per row, a lighter material on the story row
seat_mat = kit.matte(SEAT, 0.6, "Seat")
seat_hot = kit.matte("#D9DDE3", 0.5, "SeatHot")
xs = [-1.45, -0.95, -0.45, 0.45, 0.95, 1.45]
for r in range(1, ROWS + 1):
    m = seat_hot if r == ROW else seat_mat
    for i, x in enumerate(xs):
        y = row_y(r)
        box(f"S{r}_{i}", (SEAT_W - 0.06, 0.5, 0.42), (x, y, 0.21), m)                       # cushion
        box(f"B{r}_{i}", (SEAT_W - 0.06, 0.1, 0.62), (x, y + 0.22, 0.73), m, rot=(-8, 0, 0))   # backrest, leaning back


# ---------------------------------------------------------------- mannequins: a capsule body and a sphere head, seated
def mannequin(name, x, y, mat, scale=1.0):
    root = kit.empty((x, y - 0.05, 0.42), name)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.16 * scale, depth=0.5 * scale, location=(0, 0, 0.25 * scale), vertices=24)
    body = bpy.context.object
    body.name = name + "_body"
    kit.assign(body, mat)
    kit.parent(body, root)
    body.location = (0, 0, 0.25 * scale)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.14 * scale, location=(0, 0, 0.66 * scale), segments=24, ring_count=12)
    head = bpy.context.object
    head.name = name + "_head"
    kit.assign(head, mat)
    kit.parent(head, root)
    head.location = (0, 0, 0.66 * scale)
    for ob in (body, head):
        for p in ob.data.polygons:
            p.use_smooth = True
    return root


red, blue = kit.matte(RED, 0.5, "Red"), kit.matte(BLUE, 0.5, "Blue")
# the story row: a family of four (two adults, two children) on the right side
for x, mat, sc in ((0.45, RED, 1.0), (0.95, BLUE, 1.0), (1.45, BLUE, 0.75), (-0.45, RED, 0.75)):
    mannequin(f"P{ROW}_{x}", x, row_y(ROW), red if mat == RED else blue, sc)
# other passengers, sparse, alternating colours
for r, x in ((3, -1.45), (4, 0.95), (6, -0.95), (7, 1.45), (9, -0.45), (10, 0.45), (11, -1.45), (15, 0.95), (16, -0.95),
             (18, 1.45), (19, -0.45), (21, 0.45), (23, -1.45), (24, 0.95)):
    mannequin(f"P{r}_{x}", x, row_y(r), blue if (r + int(x * 10)) % 2 else red)

# ---------------------------------------------------------------- the story row: a glowing floor ring and a leader + callout
yR = row_y(ROW)
ring_mat = bpy.data.materials.new("RingGlow")
ring_mat.use_nodes = True
rn = ring_mat.node_tree.nodes
for n in list(rn):
    rn.remove(n)
out_n = rn.new("ShaderNodeOutputMaterial")
em_n = rn.new("ShaderNodeEmission")
em_n.inputs["Color"].default_value = kit.rgb(ACCENT)
em_n.inputs["Strength"].default_value = 0.0
ring_mat.node_tree.links.new(em_n.outputs[0], out_n.inputs[0])
bpy.ops.mesh.primitive_torus_add(major_radius=1.25, minor_radius=0.03, location=(0.5, yR + 0.05, 0.02), major_segments=64, minor_segments=8)
ring = bpy.context.object
ring.name = "RowRing"
ring.scale = (1.5, 0.75, 1.0)
kit.assign(ring, ring_mat)
sock = em_n.inputs["Strength"]
for t, v in ((T_LIGHT - 0.05, 0.0), (T_LIGHT + 0.25, 6.0), (T_LIGHT + 0.6, 3.5), (end / 30, 3.5)):
    sock.default_value = v
    sock.keyframe_insert("default_value", frame=kit.f(t))

# callout: two lines standing upright, turned to face the isometric camera, with a thin leader down to the row
cam_yaw = -45
call = kit.empty((2.9, yR + 0.6, 1.55), "Callout")
l1 = kit.text(LINE1, font="Montserrat-Bold", size=0.42, spacing=1.12, color="#F4F4F6", strength=1.7, align="LEFT",
              loc=(0, 0, 0.32), rot=(90, 0, cam_yaw), name="Line1")
l2 = kit.text(LINE2, font="Montserrat-Bold", size=0.2, spacing=1.2, color=ACCENT, strength=1.6, align="LEFT",
              loc=(0, 0, 0.02), rot=(90, 0, cam_yaw), name="Line2")
leader = kit.rect(0.02, 1.3, material=kit.emission(ACCENT, 2.5, "Leader"), loc=(0, 0, -0.68), rot=(0, 0, 0), name="Leader")
leader.rotation_euler = kit.rot(90, 0, cam_yaw)
for part in (l1, l2, leader):
    kit.parent(part, call)
fc = kit.f(T_CALLOUT)
for part in (l1, l2):
    kit.fade(part, [(fc, 0.0), (fc + 12, 1.0)])
kit.fade(leader, [(fc - 4, 0.0), (fc + 6, 1.0)])
kit.key(call, "location", [(fc, (2.9, yR + 0.6, 1.35)), (fc + 14, (2.9, yR + 0.6, 1.55))], ease="out")

# ---------------------------------------------------------------- light: one big soft key from the open top (the "cutaway sun"), a cool fill,
# a warm spot on the story row, and the cabin strip lights that drop out on the power beat
kit.light("AREA", (-6, yR - 10, 12), (0, yR, 0.4), power=4500, color="#FFF1E0", size=2.0, name="Key")   # a smaller light: crisp shadows, less grain at 1 sample
kit.light("AREA", (7, yR + 6, 9), (0, yR, 0.4), power=1500, color="#9FB8FF", size=2.5, name="Fill")
spot = kit.light("SPOT", (0.6, yR - 0.4, 5.5), (0.6, yR, 0.4), power=900, color="#FFD9A8", size=4, name="RowSpot")
spot.data.spot_size = math.radians(28)
spot.data.spot_blend = 0.5
spot.data.energy = 0.0
for t, v in ((T_LIGHT - 0.05, 0.0), (T_LIGHT + 0.3, 900.0), (end / 30, 900.0)):
    spot.data.energy = v
    spot.data.keyframe_insert("energy", frame=kit.f(t))
strip_mat = bpy.data.materials.new("StripLight")
strip_mat.use_nodes = True
sn = strip_mat.node_tree.nodes
for n in list(sn):
    sn.remove(n)
s_out = sn.new("ShaderNodeOutputMaterial")
s_em = sn.new("ShaderNodeEmission")
s_em.inputs["Color"].default_value = (1.0, 0.96, 0.9, 1.0)
strip_mat.node_tree.links.new(s_em.outputs[0], s_out.inputs[0])
for side in (-1, 1):
    box(f"Strip{side}", (0.08, L - 1.0, 0.03), (side * 1.1, L / 2 - 1.0, 1.42), strip_mat)
ssock = s_em.inputs["Strength"]
for t, v in ((0, 2.2), (T_POWER - 0.05, 2.2), (T_POWER + 0.08, 0.15), (T_POWER + 0.2, 1.2), (T_POWER + 0.3, 0.05), (end / 30, 0.05)):
    ssock.default_value = v
    ssock.keyframe_insert("default_value", frame=kit.f(t))
# the key dims with the power so the whole cabin goes moody; the story row stays lit by its spot
key = bpy.data.objects["Key"]
for t, v in ((0, 4500.0), (T_POWER - 0.05, 4500.0), (T_POWER + 0.35, 1600.0), (end / 30, 1600.0)):
    key.data.energy = v
    key.data.keyframe_insert("energy", frame=kit.f(t))

# ---------------------------------------------------------------- camera: isometric, high 3/4 from the left, dollying from row 8 to row 13
dist = 16.0
el = math.radians(36)
az = math.radians(225)                                        # front-left of the cabin, where the callout text faces (its yaw is -45)
ox, oy, oz = dist * math.cos(el) * math.cos(az), dist * math.cos(el) * math.sin(az), dist * math.sin(el)
y0, y1 = row_y(ROW - 5), row_y(ROW) + 0.2
cam = kit.camera((ox, y0 + oy, oz), look_at=(0.3, y0, 0.3), lens=50, ortho=19.0)
kit.key(cam, "location", [(1, (ox, y0 + oy, oz)), (end, (ox, y1 + oy, oz))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (0.3, y0, 0.3)), (end, (0.3, y1, 0.3))], ease="in_out")

# 1 sample: jittered soft shadows speckle, so turn the jitter off on every light (clean, slightly harder shadows)
for lt in bpy.data.lights:
    if hasattr(lt, "use_shadow_jitter"):
        lt.use_shadow_jitter = False

kit.post(bloom=0.25, vignette=0.35, grain=0.025)
