"""Example: a cinematic diorama, the grainy miniature documentary look (the kind of shot channels like fern build whole films from).
A mountain carved from noise sits on dark water under one low warm light; haze hangs in the air; a climbing route draws itself up
the ridge to a camp and the summit, each with a small label; a shallow lens keeps only the ridge sharp; heavy grain and a vignette.
180 frames at 30 fps. Everything is procedural: no models, no textures.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/diorama.py --out shots/diorama/diorama.mp4 --frames 180 --stills 1,90,180
Change the names, heights and beats at the top. A different seed gives a different mountain.
"""
import math
import random

import bpy
import blender_kit as kit
from mathutils import Vector, noise

a = kit.args()
end = a.frames
TITLE, SUB = "NANGA PARBAT", "8,126 M  ·  THE KILLER MOUNTAIN"
CAMP, SUMMIT = "CAMP IV  ·  7,200 M", "SUMMIT  ·  8,126 M"
T_ROUTE, T_CAMP, T_SUMMIT, T_TITLE = 0.6, 2.2, 3.6, 4.3          # seconds: route starts drawing, camp label, summit label, title
SEED = 7
ACCENT, INK = "#E0A040", "#EDE7DC"

random.seed(SEED)
noise.seed_set(SEED)
kit.setup(world="#04060A", look="Medium High Contrast", motion_blur=0.3)

# ---------------------------------------------------------------- the mountain: a dense grid displaced by a ridge shape plus layered noise
bpy.ops.mesh.primitive_grid_add(x_subdivisions=180, y_subdivisions=180, size=16, location=(0, 0, 0))
mtn = bpy.context.object
mtn.name = "Mountain"
me = mtn.data


def height(x, y):
    # an elongated ridge running roughly SW-NE, with a main summit and a lower shoulder
    u = (x * 0.8 + y * 0.6) / 1.0
    v = (-x * 0.6 + y * 0.8) / 1.0
    ridge = math.exp(-(v * v) / (2 * 1.6 ** 2)) * math.exp(-(u * u) / (2 * 4.2 ** 2))
    summit = math.exp(-((x - 0.6) ** 2 + (y - 0.4) ** 2) / (2 * 1.3 ** 2))
    shoulder = 0.55 * math.exp(-((x + 2.6) ** 2 + (y + 1.9) ** 2) / (2 * 1.5 ** 2))
    base = 4.6 * ridge * (0.55 + 0.45 * summit) + 2.4 * summit + 2.0 * shoulder
    p = Vector((x * 0.42, y * 0.42, 0.37))
    n = (noise.noise(p) * 0.9 + noise.noise(p * 2.1 + Vector((3.1, 1.7, 0))) * 0.45
         + noise.noise(p * 4.3 + Vector((7.3, 2.9, 0))) * 0.22)
    h = base * (1.0 + 0.32 * n) + 0.35 * noise.noise(p * 1.3 + Vector((11, 5, 0)))
    return max(h - 0.75, -0.9)                                   # the outskirts sink under the water: an island


for vtx in me.vertices:
    x, y = vtx.co.x, vtx.co.y
    vtx.co.z = height(x, y)
for p in me.polygons:
    p.use_smooth = True
peak = max(me.vertices, key=lambda w: w.co.z).co.copy()

# rock by height: dark slate low, grey rock, snow on the top third
rock = bpy.data.materials.new("Rock")
rock.use_nodes = True
nt = rock.node_tree
pb = nt.nodes["Principled BSDF"]
geo = nt.nodes.new("ShaderNodeNewGeometry")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
ramp = nt.nodes.new("ShaderNodeValToRGB")
mapr = nt.nodes.new("ShaderNodeMapRange")
mapr.inputs["From Min"].default_value, mapr.inputs["From Max"].default_value = -0.5, peak.z
ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (0.05, 0.06, 0.075, 1)
ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.6, (0.2, 0.22, 0.26, 1)
e = ramp.color_ramp.elements.new(0.74)
e.color = (0.86, 0.87, 0.9, 1)
nt.links.new(geo.outputs["Position"], sep.inputs[0])
nt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], pb.inputs["Base Color"])
pb.inputs["Roughness"].default_value = 0.85
kit.assign(mtn, rock)

# dark water around the base, a hint of gloss so the light draws a line on it
water = kit.rect(120, 120, material=kit.metal("#0A0F18", roughness=0.18, name="Water"), loc=(0, 0, -0.1), rot=(0, 0, 0), name="Water")

# ---------------------------------------------------------------- the route: a curve climbing the ridge, drawn on the beat
waypoints = [(-6.4, -5.2), (-4.6, -3.6), (-3.2, -2.9), (-2.0, -1.4), (-0.9, -0.6), (0.1, 0.1), (peak.x, peak.y)]
cu = bpy.data.curves.new("Route", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.07
cu.bevel_resolution = 4
cu.use_fill_caps = True
sp = cu.splines.new("NURBS")
sp.points.add(len(waypoints) - 1)
for pt, (x, y) in zip(sp.points, waypoints):
    pt.co = (x, y, height(x, y) + 0.08, 1.0)
sp.use_endpoint_u = True
sp.order_u = 3
route = bpy.data.objects.new("Route", cu)
bpy.context.scene.collection.objects.link(route)
kit.assign(route, kit.emission(ACCENT, 4.0, "RouteGlow"))
for t, frac in ((T_ROUTE, 0.0), (T_CAMP, 0.62), (T_SUMMIT, 1.0)):
    cu.bevel_factor_end = frac
    cu.keyframe_insert("bevel_factor_end", frame=kit.f(t))

# camp and summit markers with small labels that stand up facing the camera
cam_yaw = -35
TEXT_YAW = -125                     # text faces the camera: camera azimuth (145) minus 270


def marker(name, x, y, label, t):
    z = height(x, y)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.09, location=(x, y, z + 0.12), segments=16, ring_count=8)
    dot = bpy.context.object
    dot.name = name
    kit.assign(dot, kit.emission(INK, 5.0, name + "Glow"))
    f0 = kit.f(t)
    kit.key(dot, "scale", [(f0 - 3, (0.001,) * 3), (f0 + 4, (1.5,) * 3, "back"), (f0 + 10, (1.0,) * 3)], ease="out")
    stem = kit.rect(0.02, 1.2, material=kit.emission(INK, 1.5, name + "Stem"), loc=(x, y, z + 0.75), rot=(90, 0, TEXT_YAW), name=name + "_stem")
    lab = kit.text(label, font="Montserrat-Bold", size=0.46, spacing=1.25, color=INK, strength=1.7, align="LEFT",
                   loc=(x - 0.1, y + 0.15, z + 1.5), rot=(90, 0, TEXT_YAW), name=name + "_label")
    for o in (stem, lab):
        kit.fade(o, [(f0 + 2, 0.0), (f0 + 12, 1.0)])
    return dot


marker("Camp", -0.9, -0.6, CAMP, T_CAMP)
marker("Summit", peak.x, peak.y, SUMMIT, T_SUMMIT)

# the title, low in the frame, serif for the name and a small caps line under it
tfr = kit.f(T_TITLE)
title = kit.empty((7.2, 9.6, 0.4), "Title")             # far-left of frame, on the water, clear of the mountain
t1 = kit.text(TITLE, font="Gelasio-Variable", size=1.35, color=INK, strength=1.6, align="LEFT", loc=(0, 0, 0.9), rot=(90, 0, TEXT_YAW), name="T1")
t2 = kit.text(SUB, font="Montserrat-Bold", size=0.4, spacing=1.3, color=ACCENT, strength=1.6, align="LEFT", loc=(0.02, 0, 0.05), rot=(90, 0, TEXT_YAW), name="T2")
rule = kit.rect(5.5, 0.03, material=kit.emission(ACCENT, 2.0, "TitleRule"), loc=(0, 0, 0.6), rot=(90, 0, TEXT_YAW), anchor="left", name="TitleRule")
rule.location = (0, 0, 0.6)
for o in (t1, t2, rule):
    kit.parent(o, title)
    kit.fade(o, [(tfr, 0.0), (tfr + 14, 1.0)])
kit.key(rule, "scale", [(tfr, (0.001, 1, 1)), (tfr + 18, (1, 1, 1))], ease="expo")

# ---------------------------------------------------------------- light and air: one low warm sun from the side, a faint cool fill, haze, drifting specks
sun = kit.light("SUN", (-18, -5, 8), (0, 0, 2), power=5.0, color="#FFC98A", name="Sun")     # raking from front-left, the camera side
sun.data.angle = math.radians(3.5)
kit.light("AREA", (12, 10, 8), (0, 0, 2), power=1100, color="#7F9CD6", size=6, name="Fill")   # cool fill keeps the shadow side blue, not brown
# haze as a volume BOX around the scene, not a world volume: an infinite world volume swallows the sun's light in EEVEE
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 4.0))
haze = bpy.context.object
haze.name = "Haze"
haze.scale = (46, 46, 12)
hm = bpy.data.materials.new("Haze")
hm.use_nodes = True
hn = hm.node_tree.nodes
for n in list(hn):
    hn.remove(n)
h_out = hn.new("ShaderNodeOutputMaterial")
h_vol = hn.new("ShaderNodeVolumeScatter")
h_vol.inputs["Density"].default_value = 0.0028        # a breath of haze, not fog
h_vol.inputs["Color"].default_value = (0.45, 0.58, 0.85, 1)
hm.node_tree.links.new(h_vol.outputs[0], h_out.inputs["Volume"])
haze.data.materials.append(hm)
haze.visible_shadow = False
dust = kit.motes(count=120, center=(0, 0, 3.5), spread=(18, 18, 6), size=0.02, color="#FFE7C2", strength=1.2, seed=SEED)
kit.key(dust, "location", [(1, (0, 0, 3.3)), (end, (0.6, -0.4, 3.8))], ease="linear")
for lt in bpy.data.lights:
    if hasattr(lt, "use_shadow_jitter"):
        lt.use_shadow_jitter = False

# ---------------------------------------------------------------- camera: a long lens, low and far, orbiting slowly, focus on the summit (the miniature look)
az0, az1 = math.radians(cam_yaw + 180 - 10), math.radians(cam_yaw + 180 + 10)
dist, el = 58.0, math.radians(19)


def cam_pos(az):
    return (dist * math.cos(el) * math.cos(az), dist * math.cos(el) * math.sin(az), dist * math.sin(el) + 0.8)


cam = kit.camera(cam_pos(az0), look_at=(-0.5, -0.8, 2.2), lens=85)
kit.key(cam, "location", [(1, cam_pos(az0)), (end, cam_pos(az1))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (-0.8, -1.2, 2.0)), (end, (-0.2, -0.5, 2.6))], ease="in_out")
kit.shake(cam, strength=0.02, speed=25)
kit.depth_of_field(cam, focus=bpy.data.objects["Summit"], fstop=3.2)       # focus on the summit marker: an object, not a point

kit.post(bloom=0.35, vignette=0.55, grain=0.07)
