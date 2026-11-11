"""Example: a 3D data story. Five metal columns rise on a dark glossy floor, left to right, 0.6 s apart; each has a year label
on the floor in front of it and a number that counts up above it and lands when the column finishes. The tallest column
(2026) is the accent colour and its number glows a touch. A thin "SUBSCRIBERS" line sits above the bars; the camera arcs slowly.

  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/data_bars.py --out shots/data_bars/data_bars.mp4 --frames 180

Column heights are square-root scaled (12,400 to 1,100,000 is 89x; a linear scale would make 2022 a sliver).
"""
import math

import bpy

import blender_kit as kit

a = kit.args()
END = a.frames
ACCENT = "#E0A040"
YEARS = ["2022", "2023", "2024", "2025", "2026"]
VALUES = [12400, 38900, 97000, 240000, 1100000]
XS = [-5.4, -2.7, 0.0, 2.7, 5.4]
HMAX = 5.0
HS = [HMAX * math.sqrt(v / VALUES[-1]) for v in VALUES]
BW = 1.6                                   # column width and depth
T0, BEAT, RISE = 0.5, 0.6, 0.9             # first column starts at 0.5 s, 0.6 s apart, each rises for 0.9 s
E = math.radians(20)                       # camera elevation: constant, floor labels are stretched to match it
K = 1.0 / math.sin(E)

kit.setup(world="#06080B", motion_blur=0.25)

# ---------------------------------------------------------------------------------------------- floor: dark, glossy, faint mirror
floor = kit.floor("#07090C", z=0.0, size=300, roughness=0.4)
mat = floor.data.materials[0]
nt = mat.node_tree
p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
co = nt.nodes.new("ShaderNodeTexCoord")
ln = nt.nodes.new("ShaderNodeVectorMath")
ln.operation = "LENGTH"
rng = nt.nodes.new("ShaderNodeMapRange")
rng.interpolation_type = "SMOOTHSTEP"
rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = 0.0, 22.0
mix = nt.nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.inputs[6].default_value, mix.inputs[7].default_value = kit.rgb("#1A202B"), kit.rgb("#050608")
nt.links.new(co.outputs["Object"], ln.inputs[0])
nt.links.new(ln.outputs["Value"], rng.inputs["Value"])
nt.links.new(rng.outputs[0], mix.inputs[0])
nt.links.new(mix.outputs[2], p.inputs["Base Color"])
kit.fade(floor, [(1, 0.8), (2, 0.8)])        # 80 percent opaque: the mirrored columns below show through as a reflection


# ---------------------------------------------------------------------------------------------- columns
def column_mesh(h):
    me = bpy.data.meshes.new("Bar")
    x = BW / 2
    v = [(-x, -x, 0), (x, -x, 0), (x, x, 0), (-x, x, 0), (-x, -x, h), (x, -x, h), (x, x, h), (-x, x, h)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(v, [], f)
    me.update()
    return me


def mirror_material(color, h, strength):
    m, ntree, surf = kit._material("Mirror")
    c = ntree.nodes.new("ShaderNodeTexCoord")
    sep = ntree.nodes.new("ShaderNodeSeparateXYZ")
    r = ntree.nodes.new("ShaderNodeMapRange")
    r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = 0.0, h
    r.inputs["To Min"].default_value, r.inputs["To Max"].default_value = 1.0, 0.0
    mul = ntree.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    em = ntree.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = kit.rgb(color)
    ntree.links.new(c.outputs["Object"], sep.inputs[0])
    ntree.links.new(sep.outputs["Z"], r.inputs["Value"])
    ntree.links.new(r.outputs[0], mul.inputs[0])
    ntree.links.new(mul.outputs[0], em.inputs["Strength"])
    ntree.links.new(em.outputs[0], surf)
    return m


def add_obj(me, name, loc, mat_):
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    kit.assign(ob, mat_)
    bv = ob.modifiers.new("Bevel", "BEVEL")
    bv.width, bv.segments = 0.05, 2
    ob.scale = (1, 1, 0.001)
    return ob


steel = kit.matte("#D6CFBF", roughness=0.45, name="Steel")     # matte: lit faces read in a dark world (metal tops went black)
gold = kit.matte(ACCENT, roughness=0.4, name="GoldAccent")
SOUND = []
for i, (yr, val, x, h) in enumerate(zip(YEARS, VALUES, XS, HS)):
    f0 = kit.f(T0 + i * BEAT)
    f1 = kit.f(T0 + i * BEAT + RISE)
    top = i == len(YEARS) - 1
    me = column_mesh(h)
    bar = add_obj(me, f"Bar{yr}", (x, 0, 0), gold if top else steel)
    kit.key(bar, "scale", [(max(1, f0 - 1), 0.001), (f1, 1.0)], ease="out", index=2)
    kit.key(bar, "hide_render", [(1, True), (max(2, f0 - 1), False)], ease="hold")
    mir = add_obj(me, f"Mirror{yr}", (x, 0, 0), mirror_material("#E0A040" if top else "#B9AE95", h, 2.0))
    kit.key(mir, "scale", [(max(1, f0 - 1), -0.001), (f1, -1.0)], ease="out", index=2)
    kit.key(mir, "hide_render", [(1, True), (max(2, f0 - 1), False)], ease="hold")

    # the counting number rides on the top of the column and lands with it
    num = kit.text("0", font="Anton-Regular", size=0.64, color=ACCENT if top else "#F2F4F7",
                   strength=3.4 if top else 1.7, loc=(x, 0, 0.6), name=f"Num{yr}")
    kit.number_count(num, 0, val, f0, f1, fmt="{:,.0f}", ease="out")
    kit.key(num, "location", [(max(1, f0 - 1), (x, 0, 0.7)), (f1, (x, 0, h + 0.7))], ease="out")
    kit.fade(num, [(max(1, f0 - 1), 0.0), (f0 + 5, 1.0)])
    kit.key(num, "scale", [(f1, (1, 1, 1)), (f1 + 4, (1.1, 1.1, 1.1)), (f1 + 12, (1, 1, 1))], ease="out")

    # the year, painted on the floor in front of the column
    lab = kit.text(yr, font="Montserrat-Bold", size=0.55, color="#D9DEE6", strength=1.7, spacing=1.15, rot=(0, 0, 0),
                   loc=(x, -(BW / 2 + 0.2 + 0.5 * 0.7 * 0.55 * K), 0.01), name=f"Year{yr}")
    lab.scale = (1.0, K, 1.0)
    kit.fade(lab, [(max(1, f0 - 6), 0.0), (f0 + 6, 1.0)])

# ---------------------------------------------------------------------------------------------- the chart title: thin, with a rule
title = kit.text("SUBSCRIBERS", font="Montserrat-Bold", size=0.5, color="#EEF1F5", strength=1.7, spacing=1.2,
                 loc=(0, 0, 6.4), name="Title")
kit.fade(title, [(3, 0.0), (18, 1.0)])
kit.key(title, "location", [(3, (0, 0, 6.25)), (18, (0, 0, 6.4))], ease="out")
rule = kit.rect(5.4, 0.03, ACCENT, loc=(0, 0, 6.0), name="Rule")
kit.key(rule, "scale", [(8, (0.001, 1, 1)), (30, (1, 1, 1))], ease="expo")

# ---------------------------------------------------------------------------------------------- light
kit.three_point(target=(0, 0, 2.4), power=1.2, distance=10)
kit.light("AREA", (0, -1, 10), (0, 0, 2.4), power=1000, color="#FFE7C4", size=8, name="Top")
# a big soft panel overhead: never in frame, but the metal tops need something bright to reflect
kit.rect(60, 40, "#C8D2E6", loc=(0, 15, 14), rot=(180, 0, 0), material=kit.emission("#C8D2E6", 1.6, "Softbox"), name="Softbox")

# ---------------------------------------------------------------------------------------------- depth
dust = kit.motes(count=90, center=(0, -1, 3.5), spread=(18, 14, 10), size=0.02, strength=1.8)
for m_ in dust.children:
    m_.visible_shadow = False
kit.key(dust, "location", [(1, (0, -1, 3.2)), (END, (0.8, -1, 4.2))], ease="linear")

# ---------------------------------------------------------------------------------------------- camera: a slow arc and a small push in
cam = kit.camera((0, -25, 11), look_at=(0, 0, 2.6), lens=45)
dof = kit.depth_of_field(cam, focus=25.0, fstop=3.2)
frames = sorted(set(list(range(1, END + 1, 3)) + [END]))
kc, kd = [], []
for fr in frames:
    t = (fr - 1) / (END - 1)
    u = 0.5 - 0.5 * math.cos(math.pi * t)             # ease in and out
    phi = math.radians(-24 + 48 * u)
    d = 25.5 - 3.0 * u
    az = 2.1 + 0.2 * u
    kc.append((fr, (d * math.sin(phi) * math.cos(E), -d * math.cos(phi) * math.cos(E), az + d * math.sin(E))))
    kd.append((fr, d))
kit.key(cam, "location", kc, ease="linear")
kit.key(dof, "focus_distance", kd, ease="linear")
kit.key(kit.aim(cam), "location", [(1, (0, 0, 2.6)), (END, (0.2, 0, 2.8))], ease="in_out")

kit.post(bloom=0.3, vignette=0.45, grain=0.03)
