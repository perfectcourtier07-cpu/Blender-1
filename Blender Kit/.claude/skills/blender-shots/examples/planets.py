"""Example: a space explainer. Earth-like planet turning, a moon on a faint orbit ring, a ringed planet far behind.

  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/planets.py --out shots/planets/planets.mp4 --frames 180 --stills 1,60,120,180
No text. Everything is procedural (shader nodes), no downloaded textures.
"""
import math
import bpy
import blender_kit as kit

a = kit.args()
end = a.frames
ACCENT = "#E0A040"

kit.setup(world="#010204", bloom=0.5)
kit.post(bloom=0.5, vignette=0.3, grain=0.03)

SUN_POS = (-9.0, -6.0, 3.5)                     # sun comes from the left, slightly in front: a clear day/night terminator
_l = math.sqrt(sum(c * c for c in SUN_POS))
SUN_DIR = tuple(c / _l for c in SUN_POS)


# ------------------------------------------------------------------ helpers (own node materials)
def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


def ramp(nt, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    els = r.color_ramp.elements
    while len(els) > len(stops):
        els.remove(els[-1])
    while len(els) < len(stops):
        els.new(0.5)
    for el, (pos, col) in zip(els, stops):
        el.position = pos
        el.color = kit.rgb(col)
    return r


def sphere(name, radius, loc=(0, 0, 0), seg=96):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=seg // 2, radius=radius, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.shade_smooth()
    return ob


def earth_material():
    m, nt, out = new_mat("Earth")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.7
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.58
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    # a second, finer noise adds coastline wobble
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 7.0
    fine.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], fine.inputs["Vector"])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = 0.0
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "ADD"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = 0.5
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.16
    nt.links.new(fine.outputs["Fac"], sub.inputs[0])
    nt.links.new(sub.outputs[0], mul.inputs[0])
    nt.links.new(noise.outputs["Fac"], mix.inputs[0])
    nt.links.new(mul.outputs[0], mix.inputs[1])
    height = mix.outputs[0]
    col = ramp(nt, [(0.00, "#04163A"), (0.44, "#0A3C80"), (0.50, "#1E6FA8"), (0.515, "#C9B67A"),
                    (0.54, "#4C8A3A"), (0.66, "#2F6A2C"), (0.80, "#6B5B3A"), (1.00, "#B8B0A0")])
    nt.links.new(height, col.inputs["Fac"])
    # polar ice
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ab = nt.nodes.new("ShaderNodeMath")
    ab.operation = "ABSOLUTE"
    nt.links.new(sep.outputs["Z"], ab.inputs[0])
    cap = nt.nodes.new("ShaderNodeMapRange")
    cap.inputs["From Min"].default_value, cap.inputs["From Max"].default_value = 1.95, 2.12
    cap.interpolation_type = "SMOOTHSTEP"
    nt.links.new(ab.outputs[0], cap.inputs["Value"])
    ice = nt.nodes.new("ShaderNodeMix")
    ice.data_type = "RGBA"
    ice.inputs[7].default_value = kit.rgb("#E8EEF4")
    nt.links.new(cap.outputs[0], ice.inputs[0])
    nt.links.new(col.outputs["Color"], ice.inputs[6])
    # roughness: shiny sea, dull land
    rough = ramp(nt, [(0.0, "#404040"), (0.50, "#404040"), (0.52, "#E0E0E0"), (1.0, "#E0E0E0")])
    nt.links.new(height, rough.inputs["Fac"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.05
    land = nt.nodes.new("ShaderNodeMath")          # bump only on land
    land.operation = "MAXIMUM"
    land.inputs[1].default_value = 0.5
    nt.links.new(height, land.inputs[0])
    nt.links.new(land.outputs[0], bump.inputs["Height"])
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(ice.outputs[2], p.inputs["Base Color"])
    nt.links.new(rough.outputs["Color"], p.inputs["Roughness"])
    nt.links.new(bump.outputs[0], p.inputs["Normal"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


def cloud_material():
    m, nt, out = new_mat("Clouds")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.6
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    r = nt.nodes.new("ShaderNodeMapRange")
    r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = 0.52, 0.72
    r.interpolation_type = "SMOOTHSTEP"
    nt.links.new(noise.outputs["Fac"], r.inputs["Value"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    p = nt.nodes.new("ShaderNodeBsdfDiffuse")
    p.inputs["Color"].default_value = kit.rgb("#F2F6FA")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(r.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(p.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    blend(m)
    return m


def blend(m):
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    else:
        m.blend_method = "BLEND"
    try:
        m.use_backface_culling = True
    except Exception:
        pass
    try:
        m.use_transparency_overlap = False
    except Exception:
        pass


def atmosphere_material():
    m, nt, out = new_mat("Atmosphere")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.25
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 2.2
    nt.links.new(lw.outputs["Fresnel"], pw.inputs[0])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = SUN_DIR
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    lit = nt.nodes.new("ShaderNodeMapRange")           # glow strongest on the lit side, faint on the night side
    lit.inputs["From Min"].default_value, lit.inputs["From Max"].default_value = -0.6, 0.6
    lit.inputs["To Min"].default_value, lit.inputs["To Max"].default_value = 0.12, 1.0
    nt.links.new(dot.outputs["Value"], lit.inputs["Value"])
    fac = nt.nodes.new("ShaderNodeMath")
    fac.operation = "MULTIPLY"
    nt.links.new(pw.outputs[0], fac.inputs[0])
    nt.links.new(lit.outputs[0], fac.inputs[1])
    clamp = nt.nodes.new("ShaderNodeMath")
    clamp.operation = "MULTIPLY"
    clamp.use_clamp = True
    clamp.inputs[1].default_value = 1.6
    nt.links.new(fac.outputs[0], clamp.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = kit.rgb("#5AA8FF")
    em.inputs["Strength"].default_value = 2.2
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(clamp.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    blend(m)
    return m


def moon_material():
    m, nt, out = new_mat("Moon")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 4.0
    n1.inputs["Detail"].default_value = 10.0
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")          # crater-ish pits
    vor.inputs["Scale"].default_value = 9.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    col = ramp(nt, [(0.25, "#4A4A4C"), (0.75, "#A9A7A2")])
    nt.links.new(n1.outputs["Fac"], col.inputs["Fac"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.01
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Roughness"].default_value = 0.95
    nt.links.new(col.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(bump.outputs[0], p.inputs["Normal"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


def saturn_body_material():
    m, nt, out = new_mat("GasGiant")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    n.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    wob = nt.nodes.new("ShaderNodeMath")
    wob.operation = "MULTIPLY_ADD"
    wob.inputs[1].default_value = 0.18
    nt.links.new(n.outputs["Fac"], wob.inputs[0])
    wob.inputs[2].default_value = 0.0
    z = nt.nodes.new("ShaderNodeMath")
    z.operation = "MULTIPLY"
    z.inputs[1].default_value = 7.0
    nt.links.new(sep.outputs["Z"], z.inputs[0])
    zz = nt.nodes.new("ShaderNodeMath")
    zz.operation = "ADD"
    nt.links.new(z.outputs[0], zz.inputs[0])
    nt.links.new(wob.outputs[0], zz.inputs[1])
    s = nt.nodes.new("ShaderNodeMath")
    s.operation = "SINE"
    nt.links.new(zz.outputs[0], s.inputs[0])
    r = nt.nodes.new("ShaderNodeMath")
    r.operation = "MULTIPLY_ADD"
    r.inputs[1].default_value, r.inputs[2].default_value = 0.5, 0.5
    nt.links.new(s.outputs[0], r.inputs[0])
    col = ramp(nt, [(0.0, "#7A6038"), (0.5, "#C9A66B"), (1.0, "#E9D3A2")])
    nt.links.new(r.outputs[0], col.inputs["Fac"])
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Roughness"].default_value = 0.7
    nt.links.new(col.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


def ring_material():
    m, nt, out = new_mat("PlanetRing")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs["X"], comb.inputs["X"])
    nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    nt.links.new(comb.outputs[0], ln.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 9.0
    nt.links.new(ln.outputs["Value"], mul.inputs[0])
    s = nt.nodes.new("ShaderNodeMath")
    s.operation = "SINE"
    nt.links.new(mul.outputs[0], s.inputs[0])
    s2 = nt.nodes.new("ShaderNodeMath")
    s2.operation = "MULTIPLY_ADD"
    s2.inputs[1].default_value, s2.inputs[2].default_value = 0.5, 0.5
    nt.links.new(s.outputs[0], s2.inputs[0])
    col = ramp(nt, [(0.0, "#3A2E1E"), (0.45, "#9C8660"), (1.0, "#E3CF9E")])
    nt.links.new(s2.outputs[0], col.inputs["Fac"])
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Roughness"].default_value = 0.85
    nt.links.new(col.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    return m


# ------------------------------------------------------------------ scene
kit.backdrop("#010204", distance=140)                      # near-black wall far behind everything

# Earth: tilted axis (parent) + spin (child), clouds and atmosphere ride the same spin
R = 2.2
tilt = kit.empty((0, 0, 0), "EarthTilt")
tilt.rotation_euler = kit.rot(18, 0, 12)
earth = sphere("Earth", R)
kit.assign(earth, earth_material())
kit.parent(earth, tilt)
clouds = sphere("Clouds", R * 1.012, seg=64)
kit.assign(clouds, cloud_material())
kit.parent(clouds, tilt)
atmo = sphere("Atmosphere", R * 1.07, seg=64)
kit.assign(atmo, atmosphere_material())
kit.key(earth, "rotation_euler", [(1, kit.rot(0, 0, 0)), (end, kit.rot(0, 0, 36))], ease="linear")
kit.key(clouds, "rotation_euler", [(1, kit.rot(0, 0, 0)), (end, kit.rot(0, 0, 46))], ease="linear")

# Moon: one full orbit over the shot, on a faint tilted ring in the accent colour
ORB = 4.4
orbit = kit.empty((0, 0, 0), "OrbitPlane")
orbit.rotation_euler = kit.rot(28, 0, 10)                    # tilted so the camera sees an ellipse, not an edge-on line
pivot = kit.empty((0, 0, 0), "MoonPivot")
kit.parent(pivot, orbit)
moon = sphere("Moon", 0.42, loc=(ORB, 0, 0), seg=64)
kit.assign(moon, moon_material())
kit.parent(moon, pivot)
kit.key(pivot, "rotation_euler", [(1, kit.rot(0, 0, 0)), (end + 1, kit.rot(0, 0, 360))], ease="linear")
bpy.ops.mesh.primitive_torus_add(major_radius=ORB, minor_radius=0.011, major_segments=180, minor_segments=6)
ring = bpy.context.active_object
ring.name = "OrbitRing"
kit.assign(ring, kit.emission(ACCENT, 1.1, "OrbitRing"))
kit.parent(ring, orbit)

# Ringed planet far in the background (upper right), lit by the same sun
sat_tilt = kit.empty((12.5, 46.0, 7.0), "SatTilt")
sat_tilt.scale = (0.7, 0.7, 0.7)
sat_tilt.rotation_euler = kit.rot(28, 0, 18)
sat = sphere("Saturn", 3.0, seg=64)
kit.assign(sat, saturn_body_material())
kit.parent(sat, sat_tilt)
bpy.ops.mesh.primitive_torus_add(major_radius=5.2, minor_radius=1.7, major_segments=96, minor_segments=24)
sring = bpy.context.active_object
sring.name = "SaturnRing"
sring.scale = (1, 1, 0.012)
kit.assign(sring, ring_material())
kit.parent(sring, sat_tilt)
kit.key(sat_tilt, "rotation_euler", [(1, kit.rot(28, 0, 18)), (end, kit.rot(28, 0, 22))], ease="linear")

# Stars: many tiny low-strength motes, far behind
kit.motes(count=150, center=(0, 90, 6), spread=(110, 10, 62), size=0.085, color="#DCE6FF", strength=1.6, seed=11)

# Light: warm sun from the left, a very dim cool fill from the right so the night side is not a flat black hole
sun = kit.light("SUN", SUN_POS, (0, 0, 0), power=4.2, color="#FFE3BC", size=1.0, name="Sun")
kit.light("SUN", (10, -6, -1), (0, 0, 0), power=0.06, color="#6C8CFF", name="SpaceFill")

# Camera: slow eased lateral drift with a touch of push
cam = kit.camera((-2.0, -16.0, 1.2), (0, 0, 0), lens=42)
kit.key(cam, "location", [(1, (-2.0, -16.0, 1.2)), (end, (2.0, -14.6, 1.6))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (0.6, 0, 0.2)), (end, (-0.4, 0, 0.0))], ease="in_out")
kit.shake(cam, 0.01, 40.0)
