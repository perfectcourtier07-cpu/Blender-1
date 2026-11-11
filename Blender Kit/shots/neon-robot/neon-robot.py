"""Neon robot: a 3D robot flies over a night city in a neon style. 5 seconds, full frame.

The robot (chrome and gunmetal, glowing cyan visor and chest core, magenta trim, flickering foot thrusters) flies along +Y
about 150 m above a procedural city: ~330 towers with lit windows, neon signs in magenta, cyan and violet, glowing streets,
purple haze toward a magenta horizon. The camera flies with it and swings from behind-left round to its front-left side.

  python .claude/skills/blender-shots/scripts/render_blender.py shots/neon-robot/neon-robot.py --out shots/neon-robot/neon-robot.mp4 --frames 150 --stills 1,72,150

--arg speed=25 (metres per second), --arg height=150 (flight height in metres), --arg seed=11 (a different city).
"""
import math
import random

import bmesh
import bpy

import blender_kit as kit

a = kit.args()
SPEED = a.get("speed", 25.0, float)
HEIGHT = a.get("height", 150.0, float)
SEED = a.get("seed", 11, int)
end = a.frames
travel = SPEED * end / a.fps

PINK, CYAN, VIOLET, AMBER = "#FF2BD6", "#21E6FF", "#9B5CFF", "#FF9A3C"
FOG = "#2A1442"

kit.setup(world=FOG, bloom=0.5, motion_blur=0.3)


# ------------------------------------------------------------------------------------------------ shader helpers
def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def fogged(nt, out, surface_socket, dist=260.0, amount=1.0):
    """Mix the surface toward the fog colour with distance from the camera (cheap fake haze, no volumes)."""
    cam = nt.nodes.new("ShaderNodeCameraData")
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = -dist
    nt.links.new(cam.outputs["View Distance"], div.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath"); ex.operation = "EXPONENT"
    nt.links.new(div.outputs[0], ex.inputs[0])
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    nt.links.new(ex.outputs[0], inv.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = amount
    mul.use_clamp = True
    nt.links.new(inv.outputs[0], mul.inputs[0])
    fog = nt.nodes.new("ShaderNodeEmission")
    fog.inputs["Color"].default_value = kit.rgb(FOG)
    fog.inputs["Strength"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(surface_socket, mix.inputs[1])
    nt.links.new(fog.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])


def math_node(nt, op, a_, b_=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a_, b_)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def neon_mat(name, color, strength=6.0, fog=True):
    m, nt, out = new_mat(name)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = kit.rgb(color)
    em.inputs["Strength"].default_value = strength
    if fog:
        fogged(nt, out, em.outputs[0], dist=420.0, amount=0.85)
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def building_mat():
    """Dark towers with a window grid in world space; random windows lit warm or cool. Roofs stay dark."""
    m, nt, out = new_mat("Building")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], nsep.inputs[0])
    x, y, z = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    u = math_node(nt, "DIVIDE", math_node(nt, "ADD", x, y), 2.0)
    v = math_node(nt, "DIVIDE", z, 3.3)
    fu, fv = math_node(nt, "FRACT", u), math_node(nt, "FRACT", v)
    win = math_node(nt, "MULTIPLY",
                    math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", fu, 0.22), math_node(nt, "LESS_THAN", fu, 0.78)),
                    math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", fv, 0.3), math_node(nt, "LESS_THAN", fv, 0.78)))
    side = math_node(nt, "LESS_THAN", math_node(nt, "ABSOLUTE", nsep.outputs[2]), 0.5)
    cell = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(math_node(nt, "FLOOR", u), cell.inputs[0])
    nt.links.new(math_node(nt, "FLOOR", v), cell.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise"); noise.noise_dimensions = "3D"
    nt.links.new(cell.outputs[0], noise.inputs["Vector"])
    lit = math_node(nt, "GREATER_THAN", noise.outputs["Value"], 0.68)
    mask = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", win, side), lit)
    # window colour: warm or cool, picked by a second noise channel
    sepc = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(noise.outputs["Color"], sepc.inputs[0])
    pick = nt.nodes.new("ShaderNodeMix"); pick.data_type = "RGBA"
    nt.links.new(math_node(nt, "GREATER_THAN", sepc.outputs[0], 0.55), pick.inputs[0])
    pick.inputs[6].default_value = kit.rgb("#FF9E4A")
    pick.inputs[7].default_value = kit.rgb("#3FD8FF")
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = kit.rgb("#0B0D16")
    p.inputs["Roughness"].default_value = 0.45
    p.inputs["Metallic"].default_value = 0.3
    nt.links.new(pick.outputs[2], p.inputs["Emission Color"])
    nt.links.new(math_node(nt, "MULTIPLY", mask, 2.2), p.inputs["Emission Strength"])
    fogged(nt, out, p.outputs[0], dist=280.0)
    return m


def ground_mat():
    m, nt, out = new_mat("Ground")
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = kit.rgb("#06070C")
    p.inputs["Roughness"].default_value = 0.35
    fogged(nt, out, p.outputs[0], dist=220.0)
    return m


def principled(name, color, metallic, roughness):
    m, nt, out = new_mat(name)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = kit.rgb(color)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = roughness
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


# ------------------------------------------------------------------------------------------------ sky
wd = bpy.context.scene.world
nt = wd.node_tree
bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
tc = nt.nodes.new("ShaderNodeTexCoord")
sxyz = nt.nodes.new("ShaderNodeSeparateXYZ")
nt.links.new(tc.outputs["Generated"], sxyz.inputs[0])
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, kit.rgb(FOG)
glow = ramp.color_ramp.elements.new(0.02)
glow.color = kit.rgb("#5A1A6E")
ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.35, kit.rgb("#05040C")
mid = ramp.color_ramp.elements.new(0.12)
mid.color = kit.rgb("#2A1442")
nt.links.new(sxyz.outputs[2], ramp.inputs[0])
nt.links.new(ramp.outputs[0], bg.inputs["Color"])


# ------------------------------------------------------------------------------------------------ mesh helpers
def add_box(bm, cx, cy, z0, w, d, h):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for vert in r["verts"]:
        vert.co.x = cx + vert.co.x * w
        vert.co.y = cy + vert.co.y * d
        vert.co.z = z0 + (vert.co.z + 0.5) * h


def mesh_obj(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ------------------------------------------------------------------------------------------------ city
rnd = random.Random(SEED)
city, signs = bmesh.new(), {c: bmesh.new() for c in (PINK, CYAN, VIOLET)}
STEP = 30.0
y0, y1 = -420.0, travel + 900.0
ix = range(-13, 14)
iy = range(int(y0 // STEP), int(y1 // STEP) + 1)
for i in ix:
    for j in iy:
        cx = i * STEP + rnd.uniform(-3, 3)
        cy = j * STEP + rnd.uniform(-3, 3)
        w, d = rnd.uniform(13, 22), rnd.uniform(13, 22)
        near = abs(cx) < 22
        h = rnd.uniform(15, 45) if near else rnd.uniform(18, 70)
        if abs(cx) > 80 and rnd.random() < 0.15:
            h = rnd.uniform(90, 115)                         # a few taller towers off to the sides
        add_box(city, cx, cy, 0, w, d, h)
        if rnd.random() < 0.35:                              # a setback on top for a varied skyline
            add_box(city, cx, cy, h, w * 0.6, d * 0.6, h * rnd.uniform(0.12, 0.25))
        if rnd.random() < 0.45:                              # a vertical neon sign on one face
            col = rnd.choice((PINK, CYAN, VIOLET))
            sh = rnd.uniform(8, 20)
            sz = rnd.uniform(h * 0.35, max(h * 0.4, h - sh / 2 - 2))
            face = rnd.choice(("-x", "+x", "-y"))
            if face == "-x":
                add_box(signs[col], cx - w / 2 - 0.4, cy + rnd.uniform(-d / 4, d / 4), sz - sh / 2, 0.4, 2.2, sh)
            elif face == "+x":
                add_box(signs[col], cx + w / 2 + 0.4, cy + rnd.uniform(-d / 4, d / 4), sz - sh / 2, 0.4, 2.2, sh)
            else:
                add_box(signs[col], cx + rnd.uniform(-w / 4, w / 4), cy - d / 2 - 0.4, sz - sh / 2, 2.2, 0.4, sh)
        if rnd.random() < 0.25:                              # a horizontal neon band near the roof
            col = rnd.choice((PINK, CYAN, VIOLET))
            add_box(signs[col], cx, cy, h - 2.5, w + 0.6, d + 0.6, 0.6)
mesh_obj("City", city, building_mat())
for col, bm in signs.items():
    mesh_obj("Neon" + col, bm, neon_mat("Neon" + col, col, 7.0))

# streets: glowing lines along the gaps (traffic along Y in amber, cross streets in cyan)
streets_y, streets_x = bmesh.new(), bmesh.new()
for i in list(ix) + [ix[-1] + 1]:
    add_box(streets_y, (i - 0.5) * STEP, (y0 + y1) / 2, 0.05, 1.6, y1 - y0, 0.1)
for j in iy:
    add_box(streets_x, 0, (j - 0.5) * STEP, 0.05, len(ix) * STEP, 1.2, 0.1)
mesh_obj("StreetsY", streets_y, neon_mat("StreetY", AMBER, 5.0))
mesh_obj("StreetsX", streets_x, neon_mat("StreetX", CYAN, 2.5))
ground = bmesh.new()
add_box(ground, 0, (y0 + y1) / 2, -0.5, 2000, 2400, 0.5)
mesh_obj("Ground", ground, ground_mat())


# ------------------------------------------------------------------------------------------------ robot
GUN = principled("Gunmetal", "#2A303D", 1.0, 0.32)
CHROME = principled("Chrome", "#C9D2E0", 1.0, 0.22)
VISOR = neon_mat("Visor", CYAN, 9.0, fog=False)
CORE = neon_mat("Core", CYAN, 12.0, fog=False)
TRIM = neon_mat("Trim", PINK, 6.0, fog=False)
FLAME_OUT = neon_mat("FlameOut", "#FF6A2B", 8.0, fog=False)
FLAME_IN = neon_mat("FlameIn", "#CFF6FF", 14.0, fog=False)


def part(name, kind, size, loc, mat, par, rot=(0, 0, 0), bevel=0.04):
    bm = bmesh.new()
    if kind == "box":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    elif kind == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=14, radius=1.0)
        bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    elif kind == "cyl":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=size[0], radius2=size[1], depth=size[2])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = kind != "box"
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if kind == "box" and bevel:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width, mod.segments = bevel, 3
        ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    ob.parent = par
    ob.location = loc
    ob.rotation_euler = kit.rot(*rot)
    return ob


rig = kit.empty((0, 0, HEIGHT), "Rig")                       # moves along the flight path; camera and robot lights ride on it
kit.key(rig, "location", [(1, (0, 0, HEIGHT)), (end, (0, travel, HEIGHT))], ease="linear")

robot = kit.empty((0, 0, 0), "Robot")
robot.parent = rig
body = kit.empty((0, 0, 0), "Body")                          # the robot's own pose: leaning into the flight
body.parent = robot
body.rotation_euler = kit.rot(-38, 0, 0)

# torso, chest core, pelvis
part("Torso", "box", (0.95, 0.6, 0.9), (0, 0, 1.45), CHROME, body, bevel=0.08)
part("Belly", "box", (0.7, 0.5, 0.25), (0, 0, 0.95), GUN, body)
part("Pelvis", "box", (0.75, 0.5, 0.3), (0, 0, 0.72), CHROME, body)
part("CoreRing", "cyl", (0.2, 0.2, 0.08), (0, 0.31, 1.52), GUN, body, rot=(90, 0, 0))
part("Core", "cyl", (0.13, 0.13, 0.1), (0, 0.33, 1.52), CORE, body, rot=(90, 0, 0))
part("ChestTrimL", "box", (0.05, 0.03, 0.55), (-0.38, 0.31, 1.45), TRIM, body, bevel=0)
part("ChestTrimR", "box", (0.05, 0.03, 0.55), (0.38, 0.31, 1.45), TRIM, body, bevel=0)
part("Pack", "box", (0.7, 0.3, 0.7), (0, -0.42, 1.5), GUN, body)
for sx in (-1, 1):
    part(f"PackJet{sx}", "cyl", (0.12, 0.16, 0.3), (sx * 0.22, -0.48, 1.05), GUN, body)
    part(f"PackFlame{sx}", "cyl", (0.12, 0.0, 0.7), (sx * 0.22, -0.48, 0.6), FLAME_OUT, body, rot=(180, 0, 0))
# neck and head
part("Neck", "cyl", (0.13, 0.13, 0.2), (0, 0, 1.98), GUN, body)
head = part("Head", "box", (0.55, 0.5, 0.45), (0, 0, 2.28), CHROME, body, bevel=0.1)
part("Visor", "box", (0.46, 0.06, 0.12), (0, 0.26, 2.3), VISOR, body, bevel=0.02)
part("EarL", "cyl", (0.09, 0.09, 0.1), (-0.3, 0, 2.28), GUN, body, rot=(0, 90, 0))
part("EarR", "cyl", (0.09, 0.09, 0.1), (0.3, 0, 2.28), GUN, body, rot=(0, 90, 0))
part("Antenna", "cyl", (0.015, 0.015, 0.35), (0.18, -0.05, 2.65), GUN, body)
part("AntennaTip", "sphere", (0.05, 0.05, 0.05), (0.18, -0.05, 2.84), TRIM, body)

# arms: swept back along the body for flight
for sx in (-1, 1):
    sh = kit.empty((sx * 0.62, 0, 1.78), f"Shoulder{sx}")
    sh.parent = body
    sh.rotation_euler = kit.rot(-28, sx * -8, 0)
    part(f"ShoulderBall{sx}", "sphere", (0.22, 0.22, 0.22), (0, 0, 0), GUN, sh)
    part(f"UpperArm{sx}", "box", (0.22, 0.24, 0.5), (sx * 0.04, 0, -0.32), CHROME, sh)
    part(f"Elbow{sx}", "sphere", (0.13, 0.13, 0.13), (sx * 0.04, 0, -0.62), GUN, sh)
    part(f"Forearm{sx}", "box", (0.24, 0.26, 0.5), (sx * 0.04, 0, -0.92), GUN, sh)
    part(f"ArmTrim{sx}", "box", (0.02, 0.04, 0.38), (sx * 0.165, 0.09, -0.92), TRIM, sh, bevel=0)
    part(f"Hand{sx}", "sphere", (0.15, 0.13, 0.15), (sx * 0.04, 0, -1.25), CHROME, sh)

# legs: straight down and a little back, thrusters under the boots
flames = []
for sx in (-1, 1):
    hip = kit.empty((sx * 0.22, 0, 0.6), f"Hip{sx}")
    hip.parent = body
    hip.rotation_euler = kit.rot(-6 if sx < 0 else 4, 0, 0)
    part(f"Thigh{sx}", "box", (0.28, 0.3, 0.5), (0, 0, -0.32), GUN, hip)
    part(f"Knee{sx}", "sphere", (0.15, 0.15, 0.15), (0, 0.02, -0.62), CHROME, hip)
    part(f"Shin{sx}", "box", (0.3, 0.32, 0.55), (0, 0, -0.95), CHROME, hip)
    part(f"LegTrim{sx}", "box", (0.02, 0.04, 0.42), (sx * 0.16, 0.1, -0.95), TRIM, hip, bevel=0)
    part(f"Boot{sx}", "box", (0.34, 0.42, 0.22), (0, 0.04, -1.33), GUN, hip)
    part(f"Nozzle{sx}", "cyl", (0.12, 0.16, 0.14), (0, 0, -1.5), GUN, hip)
    fo = part(f"Flame{sx}", "cyl", (0.14, 0.0, 1.0), (0, 0, -2.07), FLAME_OUT, hip, rot=(180, 0, 0))
    fi = part(f"FlameCore{sx}", "cyl", (0.07, 0.0, 0.55), (0, 0, -1.85), FLAME_IN, hip, rot=(180, 0, 0))
    flames += [fo, fi]

# flight life: a gentle bob and bank, flickering flames
bob, roll = [], []
for fr in range(1, end + 1, 10):
    t = fr / a.fps
    bob.append((fr, (0, 0, 0.35 * math.sin(t * 2.4))))
    roll.append((fr, kit.rot(4 * math.sin(t * 1.7), 6 * math.sin(t * 1.3 + 0.5), 0)))
kit.key(robot, "location", bob, ease="smooth")
kit.key(robot, "rotation_euler", roll, ease="smooth")
fl = random.Random(3)
for ob in flames:
    kit.key(ob, "scale", [(fr, (1, 1, fl.uniform(0.75, 1.15))) for fr in range(1, end + 1, 2)], ease="linear")

# lights riding with the robot: magenta and cyan rims from behind, a soft cool key from the camera side
for name, loc, col, pw in (("RimPink", (-3.5, -3.0, 3.0), PINK, 900), ("RimCyan", (3.5, -2.0, 2.5), CYAN, 900),
                           ("Key", (-5.0, 2.0, 3.0), "#D8E4FF", 900), ("Under", (0, 1.0, -3.0), "#FF7A3C", 250)):
    lt = kit.light("AREA", loc, robot, power=pw, color=col, size=1.5, name=name)
    lt.parent = rig
    if hasattr(lt.data, "use_shadow_jitter"):
        lt.data.use_shadow_jitter = False
# a faint cold moonlight over the city
sun = kit.light("SUN", (50, -50, 200), (0, 100, 0), power=0.4, color="#8DA2FF", name="Moon")
sun.data.angle = math.radians(2)

# ------------------------------------------------------------------------------------------------ camera
cam = kit.camera((-6.5, -7.0, 2.4), look_at=(0, 0, 0), lens=32)
aim = kit.aim(cam)
cam.parent = rig
aim.parent = rig
aim.location = (0, 1.0, 0.2)
kit.key(cam, "location", [(1, (-6.5, -7.0, 2.4)), (end, (-6.5, 4.5, 1.6))], ease="in_out")
kit.shake(cam, strength=0.03, speed=25)

kit.post(bloom=0.55, vignette=0.4, grain=0.03)
