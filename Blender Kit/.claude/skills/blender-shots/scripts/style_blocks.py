"""Building blocks for recreating a channel's style in Blender (used by the blender-style skill).

Import it in a scene script next to blender_kit:   import blender_kit as kit; import style_blocks as sb
Every block here was proven in a finished video (a cartoon Short and a space documentary, examples/style_*.py) and
renders cleanly at the kit's 1 sample. Use what fits the style card, write the rest yourself.

  Timing      Cuts, load_words, word_time, smooth, lerp
  Materials   new_mat, node, ramp, principled, bump_noise, emit_mat, toon_mat, strata_mat, sand_mat, rock_mat,
              ballast_bed_mat, wood_mat, rail_mat, gas_giant_mat, ice_moon_mat, atmosphere_mat, smoke_card_mat, board_mat
  Objects     prim, mesh_obj, box_verts, BOX_F, outline, scatter_stones, canyon_wall, heightfield, smoke_plume, debris_ring
  Worlds      sky_world (gradient + painted clouds), space_world (stars + faint nebula)
  Characters  ToonCharacter (armature rig, shape-key face, poses), POSES, vo_envelope
  Whiteboard  Whiteboard (dark room, board, spot, marker strokes that draw on, handwriting that types on), circle_pts
  Shots       bake_shots (camera per shot, cut on word times), sun_per_shot, hide_sets (only the current shot's set renders)
  Finish      finish (haze from the mist pass, painterly Kuwahara, bloom, vignette, grain), font_path

Rules learned the hard way (all at 1 sample, EEVEE):
- Geometry-nodes output loses the object's material: scatter_stones adds a Set Material node.
- kit.light() adds a Track-To constraint; clear it before keying a sun's rotation (sun_per_shot does).
- Objects whose vertices are in world space sit at the origin: hide_sets sorts by bounding box, not origin.
- A moon between the sun and a planet casts a huge oblique "eclipse" shadow; turn its shadow off.
- EEVEE volumes are blocky noise at 1 sample: use smoke cards (smoke_card_mat / smoke_plume), never raise samples.
- Motion blur across hard cuts smears the first frame of the next shot: style shots render with motion_blur=0.
"""
import math
import os
import random
import struct
import wave

import bpy
import bmesh
import blender_kit as kit
from mathutils import Matrix, Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")
_n = [0]


def nm(s):
    _n[0] += 1
    return f"{s}{_n[0]}"


# ============================================================== timing
class Cuts:
    """Shot boundaries in seconds, e.g. Cuts([0, 2.13, 3.6, 4.33]). shot(t) -> index, u(t) -> 0..1 through the shot,
    first_frame(i) -> the first frame that belongs to shot i (use it for hard switches)."""

    def __init__(self, starts, frames=None, fps=None):
        a = kit.args()
        self.starts = list(starts)
        self.frames, self.fps = frames or a.frames, fps or a.fps
        self.end = self.frames / self.fps

    def __len__(self):
        return len(self.starts)

    def shot(self, t):
        i = 0
        for k, s in enumerate(self.starts):
            if t >= s - 1e-9:
                i = k
        return i

    def bounds(self, i):
        b = self.starts[i + 1] if i + 1 < len(self.starts) else self.end
        return self.starts[i], min(b, self.end)

    def u(self, t):
        i = self.shot(t)
        a, b = self.bounds(i)
        return (t - a) / max(1e-3, b - a)

    def t(self, frame):
        return (frame - 1) / self.fps

    def first_frame(self, i):
        for fr in range(1, self.frames + 1):
            if self.shot(self.t(fr)) == i:
                return fr
        return self.frames


def load_words(path):
    """words.json from voice_timing.py: [[word, start, end], ...]. Returns [] if the file is missing."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            return [tuple(w) for w in json.load(f)]
    except (OSError, ValueError, TypeError):
        return []


def word_time(words, word, nth=1, default=None):
    """start time of the nth occurrence of word (case and punctuation ignored)"""
    key = "".join(ch for ch in word.lower() if ch.isalnum())
    seen = 0
    for w, s, e in words:
        if "".join(ch for ch in w.lower() if ch.isalnum()) == key:
            seen += 1
            if seen == nth:
                return s
    return default


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(p, q, u):
    return tuple(pp + (qq - pp) * u for pp, qq in zip(p, q))


def ease_back(x, c=1.9):
    x = max(0.0, min(1.0, x))
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


# ============================================================== materials
def new_mat(name):
    mat = bpy.data.materials.new(nm(name))
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return mat, nt, nt.nodes.new("ShaderNodeOutputMaterial")


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def ramp(nt, stops, interp="LINEAR"):
    """stops: [(position, "#RRGGBB"), ...] (at least two)"""
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.interpolation = interp
    els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0][0], kit.rgb(stops[0][1])
    els[1].position, els[1].color = stops[-1][0], kit.rgb(stops[-1][1])
    for pos, col in stops[1:-1]:
        e = els.new(pos)
        e.color = kit.rgb(col)
    return r


def principled(nt, out, color_sock=None, color=None, rough=0.8, metal=0.0, normal=None):
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Roughness"].default_value, p.inputs["Metallic"].default_value = rough, metal
    if color_sock is not None:
        nt.links.new(color_sock, p.inputs["Base Color"])
    elif color:
        p.inputs["Base Color"].default_value = kit.rgb(color)
    if normal is not None:
        nt.links.new(normal, p.inputs["Normal"])
    nt.links.new(p.outputs[0], out.inputs[0])
    return p


def bump_noise(nt, scale, strength, vec=None, detail=4.0, height=None):
    """a Bump normal from a noise texture (or from a given height socket)"""
    if height is None:
        nz = node(nt, "ShaderNodeTexNoise", Scale=scale, Detail=detail)
        if vec is not None:
            nt.links.new(vec, nz.inputs["Vector"])
        height = nz.outputs["Fac"]
    b = node(nt, "ShaderNodeBump", Strength=strength)
    nt.links.new(height, b.inputs["Height"])
    return b.outputs["Normal"]


def _blend(mat):
    try:
        mat.blend_method = "BLEND"
    except Exception:
        pass
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"


def emit_mat(color, strength=1.0, name="Emit"):
    """flat, unlit colour (marker ink, glows, lamp glass, sun discs)"""
    mat, nt, out = new_mat(name)
    e = node(nt, "ShaderNodeEmission", Strength=strength)
    e.inputs["Color"].default_value = kit.rgb(color)
    nt.links.new(e.outputs[0], out.inputs[0])
    return mat


def toon_mat(color, name="Toon", strength=1.0, shade="#9EA6C8", soft=0.07):
    """cartoon shading: two tones (cool shade, lit) with a soft edge; receives shadows. With view="Standard",
    strength 1.0 gives the exact colour; under AgX use ~1.3."""
    mat, nt, out = new_mat(name)
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs["Color"], bw.inputs[0])
    rp = ramp(nt, [(0.0, shade), (0.06, shade), (0.06 + soft, "#FFFFFF"), (1.0, "#FFFFFF")])
    nt.links.new(bw.outputs[0], rp.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs[6].default_value = kit.rgb(color)
    nt.links.new(rp.outputs["Color"], mix.inputs[7])
    em = node(nt, "ShaderNodeEmission", Strength=strength)
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def strata_mat(name="Strata", bands=None, band_scale=0.13, warp=0.55):
    """layered rock (canyons, mesas, boulders): colour bands by world height, bent a little by noise, with vertical
    erosion streaks and bump. bands: [(pos, "#hex"), ...]"""
    bands = bands or [(0.0, "#7A2418"), (0.14, "#B2391C"), (0.30, "#D9582A"), (0.42, "#EE8A3E"), (0.52, "#F0B46A"),
                      (0.60, "#C9502A"), (0.78, "#9C2E1E"), (0.90, "#D46A33"), (1.0, "#7A2418")]
    mat, nt, out = new_mat(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    wn = node(nt, "ShaderNodeTexNoise", Scale=0.018, Detail=2.0)
    nt.links.new(geo.outputs["Position"], wn.inputs["Vector"])
    zz = node(nt, "ShaderNodeMath")
    zz.operation = "MULTIPLY_ADD"
    zz.inputs[1].default_value = band_scale
    nt.links.new(sep.outputs["Z"], zz.inputs[0])
    w2 = node(nt, "ShaderNodeMath")
    w2.operation = "MULTIPLY"
    w2.inputs[1].default_value = warp
    nt.links.new(wn.outputs["Fac"], w2.inputs[0])
    nt.links.new(w2.outputs[0], zz.inputs[2])
    fr = node(nt, "ShaderNodeMath")
    fr.operation = "FRACT"
    nt.links.new(zz.outputs[0], fr.inputs[0])
    band = ramp(nt, bands)
    nt.links.new(fr.outputs[0], band.inputs["Fac"])
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.35, 0.35, 0.03)
    nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])
    st = node(nt, "ShaderNodeTexNoise", Scale=2.2, Detail=6.0, Roughness=0.6)
    nt.links.new(mp.outputs[0], st.inputs["Vector"])
    mr = node(nt, "ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.35, 0.68
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.55, 1.08
    nt.links.new(st.outputs["Fac"], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(band.outputs["Color"], mix.inputs[6])
    nt.links.new(mr.outputs[0], mix.inputs[7])
    principled(nt, out, mix.outputs[2], rough=0.95, normal=bump_noise(nt, 0.9, 0.45, mp.outputs[0]))
    return mat


def sand_mat(name="Sand", colors=("#D98742", "#E9A45F", "#F2BC7C")):
    mat, nt, out = new_mat(name)
    nz = node(nt, "ShaderNodeTexNoise", Scale=0.08, Detail=5.0)
    rp = ramp(nt, [(0.3, colors[0]), (0.5, colors[1]), (0.7, colors[2])])
    nt.links.new(nz.outputs["Fac"], rp.inputs["Fac"])
    principled(nt, out, rp.outputs["Color"], rough=0.95, normal=bump_noise(nt, 6.0, 0.25))
    return mat


def rock_mat(name="Stones", palette=("#B0603A", "#867D75", "#CDB08C", "#764632", "#A3988A", "#BE7440")):
    """per-stone colours for scattered stones (Voronoi cells about one stone wide). Keep albedo moderate: under
    view="Standard" with a strong sun, light stones clip to white."""
    mat, nt, out = new_mat(name)
    vo = node(nt, "ShaderNodeTexVoronoi", Scale=6.0)
    sp = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vo.outputs["Color"], sp.inputs[0])
    n = len(palette)
    rp = ramp(nt, [(i / (n - 1), c) for i, c in enumerate(palette)], interp="CONSTANT")
    nt.links.new(sp.outputs[0], rp.inputs["Fac"])
    principled(nt, out, rp.outputs["Color"], rough=0.75, normal=bump_noise(nt, 30.0, 0.35))
    return mat


def ballast_bed_mat(name="Bed"):
    mat, nt, out = new_mat(name)
    vo = node(nt, "ShaderNodeTexVoronoi", Scale=14.0)
    rp = ramp(nt, [(0.0, "#5E4A3C"), (0.5, "#9A7C66"), (1.0, "#B9926E")])
    nt.links.new(vo.outputs["Distance"], rp.inputs["Fac"])
    principled(nt, out, rp.outputs["Color"], rough=0.9, normal=bump_noise(nt, 30.0, 0.5))
    return mat


def wood_mat(name="Wood", colors=("#4A3324", "#7B5A3E", "#9C7A57"), grain_axis="X"):
    """weathered wood; grain runs along grain_axis (X for sleepers/planks laid along X)"""
    mat, nt, out = new_mat(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = {"X": (0.4, 7.0, 7.0), "Y": (7.0, 0.4, 7.0), "Z": (7.0, 7.0, 0.4)}[grain_axis]
    nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])
    nz = node(nt, "ShaderNodeTexNoise", Scale=1.5, Detail=8.0)
    nt.links.new(mp.outputs[0], nz.inputs["Vector"])
    rp = ramp(nt, [(0.3, colors[0]), (0.5, colors[1]), (0.68, colors[2])])
    nt.links.new(nz.outputs["Fac"], rp.inputs["Fac"])
    principled(nt, out, rp.outputs["Color"], rough=0.85, normal=bump_noise(nt, 3.0, 0.35, mp.outputs[0]))
    return mat


def rail_mat(name="Rail", glow=False, rust="#6A3A22", steel="#80858D"):
    """steel with a worn bright top and rusty sides (by surface normal); glow=True adds an emission you can key
    (mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]) for a red-hot look"""
    mat, nt, out = new_mat(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    mr = node(nt, "ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.55, 0.9
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value, mix.inputs[7].default_value = kit.rgb(rust), kit.rgb(steel)
    nt.links.new(mr.outputs[0], mix.inputs["Factor"])
    p = principled(nt, out, mix.outputs[2], rough=0.62)
    nt.links.new(mr.outputs[0], p.inputs["Metallic"])
    rr = node(nt, "ShaderNodeMapRange")
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = 0.95, 0.5
    nt.links.new(mr.outputs[0], rr.inputs["Value"])
    nt.links.new(rr.outputs[0], p.inputs["Roughness"])
    p.inputs["Specular IOR Level"].default_value = 0.0          # rust sides would mirror the blue sky otherwise
    if glow:
        p.inputs["Emission Color"].default_value = kit.rgb("#FF5A1E")
        p.inputs["Emission Strength"].default_value = 0.0
    return mat


def gas_giant_mat(name="GasGiant", bands=None, cloud="#DDE8FA", cloud_amount=0.35):
    """banded planet (Neptune/Jupiter/Saturn looks): latitude bands warped by noise plus sparse bright cloud streaks.
    bands: [(pos, "#hex"), ...] from south to north. cloud_amount 0..1 (lower = fewer streaks)."""
    bands = bands or [(0.0, "#16307A"), (0.2, "#2A54B8"), (0.35, "#3E6FD0"), (0.48, "#2B58C0"), (0.6, "#4B7EDC"),
                      (0.75, "#2448A6"), (1.0, "#152C70")]
    mat, nt, out = new_mat(name)
    tco = nt.nodes.new("ShaderNodeTexCoord")
    sepz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tco.outputs["Object"], sepz.inputs[0])
    warp = node(nt, "ShaderNodeTexNoise", Scale=2.5, Detail=4.0)
    nt.links.new(tco.outputs["Object"], warp.inputs["Vector"])
    zz = node(nt, "ShaderNodeMath")
    zz.operation = "MULTIPLY_ADD"
    zz.inputs[1].default_value = 0.18
    nt.links.new(warp.outputs["Fac"], zz.inputs[0])
    nt.links.new(sepz.outputs["Z"], zz.inputs[2])
    br = ramp(nt, bands)
    mr = node(nt, "ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1.1, 1.1
    nt.links.new(zz.outputs[0], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], br.inputs["Fac"])
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.8, 0.8, 3.5)
    nt.links.new(tco.outputs["Object"], mp.inputs["Vector"])
    cl = node(nt, "ShaderNodeTexNoise", Scale=1.1, Detail=3.0, Roughness=0.5)
    nt.links.new(mp.outputs[0], cl.inputs["Vector"])
    cm = node(nt, "ShaderNodeMapRange")
    lo = 0.62 + 0.12 * (1 - cloud_amount)
    cm.inputs["From Min"].default_value, cm.inputs["From Max"].default_value = lo, lo + 0.22
    nt.links.new(cl.outputs["Fac"], cm.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[7].default_value = kit.rgb(cloud)
    nt.links.new(cm.outputs[0], mix.inputs["Factor"])
    nt.links.new(br.outputs["Color"], mix.inputs[6])
    principled(nt, out, mix.outputs[2], rough=0.55)
    return mat


def ice_moon_mat(name="IceMoon", scale=1.0, colors=("#8E7A78", "#C9ADA4", "#E8D7D0", "#F6EFEC"), streaks=True):
    """icy / rocky moon or ground: mottled colour, cell texture in the bump, optional dark wind streaks.
    scale: texture density (1 for a ~1 m radius sphere; ~0.06 for terrain in metres)"""
    mat, nt, out = new_mat(name)
    tco = nt.nodes.new("ShaderNodeTexCoord")
    vor = node(nt, "ShaderNodeTexVoronoi", Scale=9.0 * scale)
    try:
        vor.feature = "DISTANCE_TO_EDGE"
    except Exception:
        pass
    nt.links.new(tco.outputs["Object"], vor.inputs["Vector"])
    nz = node(nt, "ShaderNodeTexNoise", Scale=3.0 * scale, Detail=8.0)
    nt.links.new(tco.outputs["Object"], nz.inputs["Vector"])
    col = ramp(nt, [(0.3, colors[0]), (0.45, colors[1]), (0.6, colors[2]), (0.75, colors[3])])
    nt.links.new(nz.outputs["Fac"], col.inputs["Fac"])
    base = col.outputs["Color"]
    if streaks:
        sk = node(nt, "ShaderNodeTexNoise", Scale=6.0 * scale, Detail=3.0)
        mps = nt.nodes.new("ShaderNodeMapping")
        mps.inputs["Scale"].default_value = (1.0, 5.0, 1.0)
        nt.links.new(tco.outputs["Object"], mps.inputs["Vector"])
        nt.links.new(mps.outputs[0], sk.inputs["Vector"])
        sm = node(nt, "ShaderNodeMapRange")
        sm.inputs["From Min"].default_value, sm.inputs["From Max"].default_value = 0.66, 0.74
        sm.inputs["To Min"].default_value, sm.inputs["To Max"].default_value = 1.0, 0.45
        nt.links.new(sk.outputs["Fac"], sm.inputs["Value"])
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(base, mul.inputs[6])
        nt.links.new(sm.outputs[0], mul.inputs[7])
        base = mul.outputs[2]
    h = node(nt, "ShaderNodeMath")
    h.operation = "ADD"
    nt.links.new(vor.outputs["Distance"], h.inputs[0])
    nt.links.new(nz.outputs["Fac"], h.inputs[1])
    principled(nt, out, base, rough=0.85, normal=bump_noise(nt, 0, 0.45, height=h.outputs[0]))
    return mat


def atmosphere_mat(name="Atmo", color="#6FA2FF", strength=1.6, power=2.4):
    """thin glowing rim for a planet: put it on a sphere ~3.5% larger than the planet. Glows only on the sunlit side."""
    mat, nt, out = new_mat(name)
    lw = node(nt, "ShaderNodeLayerWeight", Blend=0.35)
    pw = node(nt, "ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = power
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    em = node(nt, "ShaderNodeEmission", Strength=strength)
    em.inputs["Color"].default_value = kit.rgb(color)
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs[0], bw.inputs[0])
    lit = node(nt, "ShaderNodeMapRange")
    lit.inputs["From Min"].default_value, lit.inputs["From Max"].default_value = 0.0, 0.15
    nt.links.new(bw.outputs[0], lit.inputs["Value"])
    fac = node(nt, "ShaderNodeMath")
    fac.operation = "MULTIPLY"
    nt.links.new(pw.outputs[0], fac.inputs[0])
    nt.links.new(lit.outputs[0], fac.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    add = nt.nodes.new("ShaderNodeAddShader")
    mixs = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fac.outputs[0], mixs.inputs[0])
    nt.links.new(tr.outputs[0], mixs.inputs[1])
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], mixs.inputs[2])
    nt.links.new(mixs.outputs[0], out.inputs[0])
    _blend(mat)
    return mat


def smoke_card_mat(name="Smoke", across="X", dark="#2A2421", light="#7A6D66", opacity=0.85, glow=0.55, speed=3.0):
    """soft smoke on a flat card (uses the card's UV): noisy alpha, soft edges across the card, faded at both ends,
    slowly churning. across: which UV axis runs across the plume ("X" for a vertical column card, "Y" for a
    horizontal trail card). Smooth at 1 sample, unlike EEVEE volumes."""
    end = kit.args().frames
    mat, nt, out = new_mat(name)
    tco = nt.nodes.new("ShaderNodeTexCoord")
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tco.outputs["UV"], sp.inputs[0])
    acr, alo = (sp.outputs["X"], sp.outputs["Y"]) if across == "X" else (sp.outputs["Y"], sp.outputs["X"])
    c = node(nt, "ShaderNodeMath")
    c.operation = "SUBTRACT"
    c.inputs[1].default_value = 0.5
    nt.links.new(acr, c.inputs[0])
    ab = node(nt, "ShaderNodeMath")
    ab.operation = "ABSOLUTE"
    nt.links.new(c.outputs[0], ab.inputs[0])
    edge = node(nt, "ShaderNodeMapRange")
    edge.interpolation_type = "SMOOTHSTEP"
    edge.inputs["From Min"].default_value, edge.inputs["From Max"].default_value = 0.5, 0.08
    nt.links.new(ab.outputs[0], edge.inputs["Value"])
    far = node(nt, "ShaderNodeMapRange")
    far.interpolation_type = "SMOOTHSTEP"
    far.inputs["From Min"].default_value, far.inputs["From Max"].default_value = 1.0, 0.6
    nt.links.new(alo, far.inputs["Value"])
    near = node(nt, "ShaderNodeMapRange")
    near.interpolation_type = "SMOOTHSTEP"
    near.inputs["From Min"].default_value, near.inputs["From Max"].default_value = 0.0, 0.1
    nt.links.new(alo, near.inputs["Value"])
    mpn = nt.nodes.new("ShaderNodeMapping")
    mpn.inputs["Scale"].default_value = (3.0, 6.0, 1.0) if across == "X" else (6.0, 3.0, 1.0)
    nt.links.new(tco.outputs["UV"], mpn.inputs["Vector"])
    nz = node(nt, "ShaderNodeTexNoise", Scale=1.6, Detail=8.0, Roughness=0.62)
    nz.noise_dimensions = "4D"
    nt.links.new(mpn.outputs[0], nz.inputs["Vector"])
    kit.key(nz.inputs["W"], "default_value", [(1, 0.0), (end, speed)], ease="linear")
    nm_ = node(nt, "ShaderNodeMapRange")
    nm_.inputs["From Min"].default_value, nm_.inputs["From Max"].default_value = 0.35, 0.7
    nt.links.new(nz.outputs["Fac"], nm_.inputs["Value"])
    acc = edge.outputs[0]
    for sock in (nm_.outputs[0], far.outputs[0], near.outputs[0]):
        m = node(nt, "ShaderNodeMath")
        m.operation = "MULTIPLY"
        nt.links.new(acc, m.inputs[0])
        nt.links.new(sock, m.inputs[1])
        acc = m.outputs[0]
    op = node(nt, "ShaderNodeMath")
    op.operation = "MULTIPLY"
    op.inputs[1].default_value = opacity
    nt.links.new(acc, op.inputs[0])
    shade = ramp(nt, [(0.3, dark), (0.8, light)])
    nt.links.new(nz.outputs["Fac"], shade.inputs["Fac"])
    em = node(nt, "ShaderNodeEmission", Strength=glow)
    nt.links.new(shade.outputs["Color"], em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(op.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs[0])
    _blend(mat)
    return mat


def board_mat(name="Whiteboard"):
    mat, nt, out = new_mat(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sm = node(nt, "ShaderNodeTexNoise", Scale=1.3, Detail=6.0)
    nt.links.new(geo.outputs["Position"], sm.inputs["Vector"])
    col = ramp(nt, [(0.3, "#DADDE0"), (0.55, "#EDEFF0"), (0.75, "#F4F5F5")])
    nt.links.new(sm.outputs["Fac"], col.inputs["Fac"])
    principled(nt, out, col.outputs["Color"], rough=0.25)
    return mat


# ============================================================== objects
def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def prim(kind, loc, scale=(1, 1, 1), rot=(0, 0, 0), mat=None, name="P", smooth_shade=True, **kw):
    """bpy primitive (cube, uv_sphere, ico_sphere, cylinder, cone, plane, circle, torus) with a material.
    cube: pass size=1.0 so scale = edge length. plane rotated (90,0,0) stands up facing -Y: its height is scale[1]."""
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(location=loc, **kw)
    ob = bpy.context.object
    ob.name = nm(name)
    ob.scale = scale
    ob.rotation_euler = kit.rot(*rot)
    if mat:
        ob.data.materials.append(mat)
    if smooth_shade:
        for p in ob.data.polygons:
            p.use_smooth = True
    return ob


def mesh_obj(name, verts, faces, mat=None, smooth_shade=False):
    me = bpy.data.meshes.new(nm(name))
    me.from_pydata(verts, [], faces)
    me.update()
    ob = link(bpy.data.objects.new(me.name, me))
    if mat:
        ob.data.materials.append(mat)
    if smooth_shade:
        for p in me.polygons:
            p.use_smooth = True
    return ob


BOX_F = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]


def box_verts(cx, cy, cz, sx, sy, sz, yaw=0.0):
    """8 corners of a box (use with BOX_F) - for joining hundreds of boxes into one mesh (sleepers, planks, bricks)"""
    c, s = math.cos(yaw), math.sin(yaw)
    out = []
    for dx in (-sx / 2, sx / 2):
        for dy in (-sy / 2, sy / 2):
            for dz in (-sz / 2, sz / 2):
                out.append((cx + dx * c - dy * s, cy + dx * s + dy * c, cz + dz))
    return out


_INK_SHELL = {}


def outline(ob, width=0.018, color="#151313"):
    """cartoon ink outline (inverted hull): a back-facing shell drawn just outside the object"""
    key = color
    if key not in _INK_SHELL:
        m = emit_mat(color, 1.0, "InkShell")
        m.use_backface_culling = True
        _INK_SHELL[key] = m
    mod = ob.modifiers.new("Outline", "SOLIDIFY")
    mod.thickness, mod.offset, mod.use_flip_normals, mod.use_rim = width, 1.0, True, False
    mod.material_offset = len(ob.data.materials)
    ob.data.materials.append(_INK_SHELL[key])
    return ob


def scatter_stones(name, profile, y0, y1, density, mat, size_min=(0.038, 0.032, 0.026), size_max=(0.075, 0.066, 0.055),
                   seed=3, subdivisions=1):
    """thousands of loose stones (gravel, ballast, rubble, pebbles) scattered over a strip.
    profile: cross-section [(x, z), ...] swept from y0 to y1. density: stones per square metre (100-400 near the
    camera, ~100 further away). mat: rock_mat(). Geometry nodes; renders fast."""
    v = [(x, y0, z) for x, z in profile] + [(x, y1, z) for x, z in profile]
    n = len(profile)
    f = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    ob = mesh_obj(name, v, f)
    ng = bpy.data.node_groups.new(nm("Scatter"), "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    dist = N.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = density
    dist.inputs["Seed"].default_value = seed
    L.new(gi.outputs[0], dist.inputs["Mesh"])
    ico = N.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Radius"].default_value, ico.inputs["Subdivisions"].default_value = 1.0, subdivisions
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(dist.outputs["Points"], inst.inputs["Points"])
    L.new(ico.outputs["Mesh"], inst.inputs["Instance"])
    rr = N.new("FunctionNodeRandomValue")
    rr.data_type = "FLOAT_VECTOR"
    rr.inputs[0].default_value, rr.inputs[1].default_value = (0, 0, 0), (6.28, 6.28, 6.28)
    rr.inputs["Seed"].default_value = seed + 1
    L.new(rr.outputs[0], inst.inputs["Rotation"])
    rs = N.new("FunctionNodeRandomValue")
    rs.data_type = "FLOAT_VECTOR"
    rs.inputs[0].default_value, rs.inputs[1].default_value = size_min, size_max
    rs.inputs["Seed"].default_value = seed + 2
    L.new(rs.outputs[0], inst.inputs["Scale"])
    real = N.new("GeometryNodeRealizeInstances")
    L.new(inst.outputs[0], real.inputs[0])
    sm = N.new("GeometryNodeSetShadeSmooth")
    L.new(real.outputs[0], sm.inputs[0])
    smat = N.new("GeometryNodeSetMaterial")                     # GN output drops the object's material otherwise
    smat.inputs["Material"].default_value = mat
    L.new(sm.outputs[0], smat.inputs[0])
    L.new(smat.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("Stones", "NODES")
    mod.node_group = ng
    ob.data.materials.append(mat)
    return ob


def canyon_wall(side, base, height, mat, y0=-80.0, y1=440.0, step=1.4, lean=0.12, seed=0.0):
    """a carved cliff running along Y: side -1 (left, at x=-base) or +1 (right). Relief from layered noise, ledges,
    an irregular top. Give it strata_mat()."""
    verts, faces = [], []
    nz = int(height / 1.2) + 2
    ny = int((y1 - y0) / step) + 1
    for j in range(ny):
        y = y0 + j * step
        top = height * (0.9 + 0.18 * noise.noise(Vector((y * 0.02, side * 7.0 + seed, 0.3))))
        for i in range(nz):
            z = top * i / (nz - 1)
            p = Vector((y * 0.045, z * 0.035, side * 3.1 + seed))
            d = 3.2 * noise.noise(p) + 1.1 * noise.noise(Vector((y * 0.21, z * 0.05, side + seed))) \
                + 0.35 * noise.noise(Vector((y * 0.9, z * 0.4, side + seed)))
            ledge = 0.6 * math.floor((z + 2.0 * noise.noise(Vector((y * 0.05, 1.0, side + seed)))) / 4.5)
            verts.append((side * (base + lean * z + ledge * 0.5 + d), y, z))
        if j:
            for i in range(nz - 1):
                p0 = (j - 1) * nz + i
                faces.append((p0, p0 + nz, p0 + nz + 1, p0 + 1) if side > 0 else (p0, p0 + 1, p0 + nz + 1, p0 + nz))
    return mesh_obj(f"Wall{side}", verts, faces, mat, smooth_shade=True)


def heightfield(name, center, size, res, height_fn, mat):
    """terrain grid: height_fn(x, y) -> z in metres (x, y relative to center). res 150-250 is plenty."""
    cx, cy, cz = center
    verts, faces = [], []
    for j in range(res):
        for i in range(res):
            x = (i / (res - 1) - 0.5) * size
            y = (j / (res - 1) - 0.5) * size
            verts.append((cx + x, cy + y, cz + height_fn(x, y)))
    for j in range(res - 1):
        for i in range(res - 1):
            a0 = j * res + i
            faces.append((a0, a0 + 1, a0 + res + 1, a0 + res))
    return mesh_obj(name, verts, faces, mat, smooth_shade=True)


def smoke_plume(base, height, radius, trail=0.0, col_mat=None, trail_mat=None, facing_yaw=0.0):
    """a smoke column (and optionally a wind-blown trail along +X from its top), as two soft cards facing -Y.
    Works for geysers, chimneys, volcano ash, train smoke seen side-on. Returns the card objects."""
    col_mat = col_mat or smoke_card_mat("SmokeColumn", "X")
    out = []
    b = Vector(base)
    col = prim("plane", tuple(b + Vector((0, 0, height / 2))), scale=(radius, height / 2 + radius, 1), rot=(90, 0, facing_yaw),
               mat=col_mat, name="SmokeCol", smooth_shade=False, size=2.0)
    out.append(col)
    if trail > 0:
        trail_mat = trail_mat or smoke_card_mat("SmokeTrail", "Y")
        tr = prim("plane", tuple(b + Vector((trail / 2 - radius, 0.5, height + radius * 0.6))), scale=(trail / 2, radius * 2.4, 1),
                  rot=(90, 0, facing_yaw), mat=trail_mat, name="SmokeTrail", smooth_shade=False, size=2.0)
        out.append(tr)
    for ob in out:
        ob.visible_shadow = False
    return out


def debris_ring(center, radius, count, mat, spread=0.45, thickness=0.12, size=(0.04, 0.16), seed=5):
    """loose pieces in a ring (planetary rings, a moon torn apart, an asteroid belt seen from afar).
    Returns [(object, angle, rest_scale)] so you can reveal pieces over time (key their scale)."""
    rng = random.Random(seed)
    cx, cy, cz = center
    out = []
    for _ in range(count):
        ang = rng.uniform(0, 2 * math.pi)
        rr = radius + rng.gauss(0, spread)
        s = rng.uniform(*size)
        ob = prim("ico_sphere", (cx + rr * math.cos(ang), cy + rr * math.sin(ang), cz + rng.gauss(0, thickness)),
                  scale=(s, s * rng.uniform(0.6, 1.3), s * 0.8), rot=(rng.uniform(0, 90), rng.uniform(0, 90), 0), mat=mat,
                  name="Debris", smooth_shade=False, radius=1.0, subdivisions=1)
        out.append((ob, ang, ob.scale.copy()))
    return out


# ============================================================== worlds
def sky_world(horizon="#A9CBF4", zenith="#1A4FD6", clouds=True, cloud_shade="#9DB0DA", cloud_cover=0.53, strength=0.46):
    """daylight sky: gradient by height plus painted clouds fixed in direction (they stay put as the camera turns)"""
    sc = bpy.context.scene
    w = sc.world
    wn, wl = w.node_tree.nodes, w.node_tree.links
    bg = next(n for n in wn if n.type == "BACKGROUND")
    tc = wn.new("ShaderNodeTexCoord")
    sep = wn.new("ShaderNodeSeparateXYZ")
    wl.new(tc.outputs["Generated"], sep.inputs[0])
    sky = wn.new("ShaderNodeValToRGB")
    sky.color_ramp.elements[0].position, sky.color_ramp.elements[0].color = 0.0, kit.rgb(horizon)
    sky.color_ramp.elements[1].position, sky.color_ramp.elements[1].color = 0.5, kit.rgb(zenith)
    wl.new(sep.outputs["Z"], sky.inputs["Fac"])
    col = sky.outputs["Color"]
    if clouds:
        mp = wn.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.6, 1.6, 5.0)
        wl.new(tc.outputs["Generated"], mp.inputs["Vector"])
        cn = wn.new("ShaderNodeTexNoise")
        cn.inputs["Scale"].default_value, cn.inputs["Detail"].default_value, cn.inputs["Roughness"].default_value = 2.4, 6.0, 0.55
        wl.new(mp.outputs[0], cn.inputs["Vector"])
        cm = wn.new("ShaderNodeMapRange")
        cm.inputs["From Min"].default_value, cm.inputs["From Max"].default_value = cloud_cover, cloud_cover + 0.11
        wl.new(cn.outputs["Fac"], cm.inputs["Value"])
        hz = wn.new("ShaderNodeMapRange")
        hz.inputs["From Min"].default_value, hz.inputs["From Max"].default_value = 0.02, 0.16
        wl.new(sep.outputs["Z"], hz.inputs["Value"])
        cmul = wn.new("ShaderNodeMath")
        cmul.operation = "MULTIPLY"
        wl.new(cm.outputs[0], cmul.inputs[0])
        wl.new(hz.outputs[0], cmul.inputs[1])
        cshade = wn.new("ShaderNodeMix")
        cshade.data_type = "RGBA"
        cshade.inputs[6].default_value, cshade.inputs[7].default_value = kit.rgb(cloud_shade), kit.rgb("#FFFFFF")
        wl.new(cn.outputs["Fac"], cshade.inputs["Factor"])
        cmix = wn.new("ShaderNodeMix")
        cmix.data_type = "RGBA"
        wl.new(cmul.outputs[0], cmix.inputs["Factor"])
        wl.new(col, cmix.inputs[6])
        wl.new(cshade.outputs[2], cmix.inputs[7])
        col = cmix.outputs[2]
    wl.new(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    return w


def space_world(star_scale=260.0, star_size=0.06, star_gain=14.0, nebula="#0F0804", nebula_amount=1.0):
    """black space: a star field (sharp points of varied brightness) and a faint warm nebula. star_gain 8-20."""
    sc = bpy.context.scene
    w = sc.world
    wn, wl = w.node_tree.nodes, w.node_tree.links
    bg = next(n for n in wn if n.type == "BACKGROUND")
    tc = wn.new("ShaderNodeTexCoord")
    vo = wn.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = star_scale
    wl.new(tc.outputs["Generated"], vo.inputs["Vector"])
    st = wn.new("ShaderNodeMapRange")
    st.inputs["From Min"].default_value, st.inputs["From Max"].default_value = star_size, 0.0
    wl.new(vo.outputs["Distance"], st.inputs["Value"])
    pw = wn.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 6.0
    wl.new(st.outputs[0], pw.inputs[0])
    sep = wn.new("ShaderNodeSeparateColor")
    wl.new(vo.outputs["Color"], sep.inputs[0])
    br = wn.new("ShaderNodeMath")
    br.operation = "MULTIPLY"
    wl.new(pw.outputs[0], br.inputs[0])
    wl.new(sep.outputs[0], br.inputs[1])
    sw = wn.new("ShaderNodeMath")
    sw.operation = "MULTIPLY"
    sw.inputs[1].default_value = star_gain
    wl.new(br.outputs[0], sw.inputs[0])
    neb = wn.new("ShaderNodeTexNoise")
    neb.inputs["Scale"].default_value, neb.inputs["Detail"].default_value = 1.6, 8.0
    wl.new(tc.outputs["Generated"], neb.inputs["Vector"])
    nr = wn.new("ShaderNodeValToRGB")
    c = kit.rgb(nebula)
    nr.color_ramp.elements[0].position, nr.color_ramp.elements[0].color = 0.5, (0, 0, 0, 1)
    nr.color_ramp.elements[1].position, nr.color_ramp.elements[1].color = 0.78, (c[0] * nebula_amount, c[1] * nebula_amount, c[2] * nebula_amount, 1)
    wl.new(neb.outputs["Fac"], nr.inputs["Fac"])
    add = wn.new("ShaderNodeMix")
    add.data_type, add.blend_type = "RGBA", "ADD"
    add.inputs["Factor"].default_value = 1.0
    wl.new(nr.outputs["Color"], add.inputs[6])
    wl.new(sw.outputs[0], add.inputs[7])
    wl.new(add.outputs[2], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    return w


# ============================================================== characters
CHAR_BONES = {   # name: (head, tail, parent)   a ~1.9 m cartoon person facing -Y, feet at z=0, big head
    "hips": ((0, 0, 0.62), (0, 0, 0.72), None),
    "spine": ((0, 0, 0.72), (0, 0, 1.22), "hips"),
    "head": ((0, 0, 1.22), (0, 0, 1.50), "spine"),
    "upperarm.L": ((0.25, 0, 1.13), (0.25, 0, 0.86), "spine"),
    "fore.L": ((0.25, 0, 0.86), (0.25, 0, 0.60), "upperarm.L"),
    "upperarm.R": ((-0.25, 0, 1.13), (-0.25, 0, 0.86), "spine"),
    "fore.R": ((-0.25, 0, 0.86), (-0.25, 0, 0.60), "upperarm.R"),
    "thigh.L": ((0.11, 0, 0.70), (0.11, 0, 0.38), "hips"),
    "shin.L": ((0.11, 0, 0.38), (0.11, 0, 0.07), "thigh.L"),
    "thigh.R": ((-0.11, 0, 0.70), (-0.11, 0, 0.38), "hips"),
    "shin.R": ((-0.11, 0, 0.38), (-0.11, 0, 0.07), "thigh.R"),
}
FACE_KEYS = ("blink", "wide", "squint", "up", "angry", "worried", "O", "shock", "grin")


def _pose_rest():
    return {b: (0.0, 0.0, 0.0) for b in CHAR_BONES}


def pose_stand(t):
    """idle: breathing arms. Returns (pose, root height offset). Degrees, bone-local XYZ: on legs and arms +X swings
    back and -X forward; on spine/head +X leans forward; Z on arms swings out (L negative, R positive)."""
    p = _pose_rest()
    br = math.sin(t * 2.2)
    p["upperarm.L"], p["upperarm.R"] = (2 * br, 0, -10), (-2 * br, 0, 10)
    p["fore.L"] = p["fore.R"] = (-12, 0, 0)
    p["spine"] = (2 + 1.5 * br, 0, 0)
    return p, 0.0


def pose_walk(t, period=0.62, stride=30):
    """walk cycle in place (move the character's location yourself, ~1.0-1.6 m/s)"""
    p = _pose_rest()
    ph = 2 * math.pi * t / period
    s = math.sin(ph)
    p["thigh.L"], p["thigh.R"] = (-stride * s, 0, -2), (stride * s, 0, 2)
    p["shin.L"] = (8 + 42 * max(0.0, math.sin(ph + 1.3)), 0, 0)
    p["shin.R"] = (8 + 42 * max(0.0, math.sin(ph + 1.3 + math.pi)), 0, 0)
    p["upperarm.L"], p["upperarm.R"] = (28 * s, 0, -9), (-28 * s, 0, 9)
    p["fore.L"], p["fore.R"] = (-28 - 10 * max(0, -s), 0, 0), (-28 - 10 * max(0, s), 0, 0)
    p["spine"] = (7, 4 * s, 0)
    p["head"] = (-5, -4 * s, 2 * math.sin(2 * ph))
    return p, 0.045 * abs(math.cos(ph)) - 0.02


def pose_work(t, period=0.42):
    """crouched, right arm working back and forth (sawing, scrubbing, hammering); lower root by the returned offset"""
    p = _pose_rest()
    st = math.sin(2 * math.pi * t / period)
    p["thigh.L"], p["thigh.R"] = (-78, 0, -8), (-70, 0, 10)
    p["shin.L"], p["shin.R"] = (112, 0, 0), (96, 0, 0)
    p["spine"] = (32 + 2 * st, 0, 0)
    p["head"] = (-32, 6, 4)
    p["upperarm.R"] = (-62 + 13 * st, 0, 12)
    p["fore.R"] = (-28 - 16 * st, 0, 0)
    p["upperarm.L"], p["fore.L"] = (-48, 0, -14), (-46, 0, 0)
    return p, -0.30 + 0.01 * st


def pose_shrug(t, u):
    """palms up "why?" shrug; u = 0..1 through the shot (it settles in the first third)"""
    p = _pose_rest()
    k = smooth(u * 3.0)
    p["upperarm.L"], p["upperarm.R"] = (-25 * k, 0, -52 * k - 8), (-25 * k, 0, 52 * k + 8)
    p["fore.L"], p["fore.R"] = (-120 * k, 0, 25 * k), (-120 * k, 0, -25 * k)
    p["spine"] = (-4 * k, 0, 0)
    p["head"] = (-6 * k, 0, 12 * k)
    return p, 0.03 * k


def pose_shock(t, k):
    """arms flung up, leaning back; k 0..1 (use ease_back for an overshoot), add a little hop to the root yourself"""
    p, z = pose_stand(t)
    p["upperarm.L"], p["upperarm.R"] = (-20 * k, 0, -10 - 140 * k), (-20 * k, 0, 10 + 140 * k)
    p["fore.L"], p["fore.R"] = (-10 - 30 * k, 0, -20 * k), (-10 - 30 * k, 0, 20 * k)
    p["spine"] = (-10 * k, 0, 0)
    p["thigh.L"], p["thigh.R"] = (-8 * k, 0, -10 * k), (-8 * k, 0, 10 * k)
    p["shin.L"], p["shin.R"] = (14 * k, 0, 0), (14 * k, 0, 0)
    return p, z


def pose_point(t, side="R"):
    """pointing arm straight forward-out (presenting, accusing)"""
    p, z = pose_stand(t)
    s = 1 if side == "L" else -1
    p[f"upperarm.{side}"] = (-80, 0, -25 * s)
    p[f"fore.{side}"] = (-5, 0, 0)
    return p, z


POSES = {"stand": pose_stand, "walk": pose_walk, "work": pose_work, "shrug": pose_shrug, "shock": pose_shock, "point": pose_point}


class ToonCharacter:
    """A rigged 3D cartoon person: armature (hips, spine, head, arms, forearms, thighs, shins) with rigid parts parented
    to bones, a 3D head with ink outline, and a face made of flat features shrink-wrapped onto the head, each with
    SHAPE KEYS: eyes blink/wide/squint, brows up/angry/worried, mouth O/shock/grin (the basis is a smirk).

        bob = sb.ToonCharacter("Bob", shirt="#F2EEE6", body="#3D6BB3", hat="cap", hat_color="#B5442C")
        for fr in range(1, END + 1):
            t = (fr - 1) / FPS
            pose, dz = sb.pose_walk(t)
            bob.set(fr, loc=(x, y, z + dz), yaw=0, pose=pose, face={"grin": 0.3})

    Build it before anything moves (it parents in the rest pose). Faces the camera when yaw points its -Y at it:
    yaw = degrees(atan2(cam_x - x, -(cam_y - y))). Colours are exact under kit.setup(view="Standard")."""

    def __init__(self, name="Toon", skin="#F7F1E6", shirt="#F2EEE6", body="#3D6BB3", scarf="#D63B2F", hair="#5A3A26",
                 hat="cap", hat_color="#B5442C", hat_band="#6E2418", limbs="#1D1A1A", gloves="#FFFFFF", buttons="#E8B33E",
                 overalls=True, strength=1.0):
        self.name = name
        T = lambda c, n: toon_mat(c, f"{name}{n}", strength=strength)
        M = dict(skin=T(skin, "Skin"), shirt=T(shirt, "Shirt"), body=T(body, "Body"), scarf=T(scarf, "Scarf"), hair=T(hair, "Hair"),
                 hat=T(hat_color, "Hat"), band=T(hat_band, "Band"), limb=toon_mat(limbs, f"{name}Limb", strength, shade=limbs),
                 glove=T(gloves, "Glove"), btn=T(buttons, "Btn"))
        ink = emit_mat("#151313", 1.0, f"{name}Ink")
        arm_data = bpy.data.armatures.new(nm(name + "Rig"))
        self.rig = link(bpy.data.objects.new(arm_data.name, arm_data))
        vl = bpy.context.view_layer
        vl.objects.active = self.rig
        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        self.rig.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        for bn, (h, t, par) in CHAR_BONES.items():
            eb = arm_data.edit_bones.new(bn)
            eb.head, eb.tail, eb.roll = h, t, 0.0
        for bn, (h, t, par) in CHAR_BONES.items():
            if par:
                arm_data.edit_bones[bn].parent = arm_data.edit_bones[par]
        bpy.ops.object.mode_set(mode="OBJECT")
        for pb in self.rig.pose.bones:
            pb.rotation_mode = "XYZ"
        vl.update()
        bp = self._bone_parent
        torso = prim("uv_sphere", (0, 0, 0.94), scale=(0.29, 0.22, 0.31), mat=M["body"], name=name + "Torso", segments=32, ring_count=16)
        chest = prim("uv_sphere", (0, 0.01, 1.08), scale=(0.25, 0.19, 0.17), mat=M["shirt"], name=name + "Chest", segments=32, ring_count=16)
        parts = [torso, chest, prim("cone", (0, -0.14, 1.19), rot=(160, 0, 0), mat=M["scarf"], name=name + "Scarf", radius1=0.13,
                                    radius2=0.0, depth=0.16, vertices=3)]
        if overalls:
            parts.append(prim("cube", (0, -0.185, 1.05), scale=(0.2, 0.03, 0.16), rot=(-8, 0, 0), mat=M["body"], name=name + "Bib",
                              smooth_shade=False, size=1.0))
            for sx in (-0.1, 0.1):
                parts.append(prim("cube", (sx, -0.13, 1.17), scale=(0.045, 0.03, 0.2), rot=(-25, 0, 0), mat=M["body"], name=name + "Strap",
                                  smooth_shade=False, size=1.0))
                parts.append(prim("uv_sphere", (sx * 0.85, -0.205, 1.11), scale=(0.022,) * 3, mat=M["btn"], name=name + "Btn", segments=12,
                                  ring_count=6))
        for p in parts:
            bp(p, "spine")
        outline(torso, 0.016)
        outline(chest, 0.016)
        for s, side in ((1, "L"), (-1, "R")):
            self._limb((0.25 * s, 0, 1.13), (0.25 * s, 0, 0.86), 0.03, M["limb"], f"upperarm.{side}")
            self._limb((0.25 * s, 0, 0.86), (0.25 * s, 0, 0.62), 0.03, M["limb"], f"fore.{side}")
            bp(prim("uv_sphere", (0.25 * s, 0, 0.86), scale=(0.032,) * 3, mat=M["limb"], name=name + "Elbow", segments=12, ring_count=6), f"fore.{side}")
            hand = prim("uv_sphere", (0.25 * s, 0, 0.57), scale=(0.075, 0.07, 0.08), mat=M["glove"], name=name + "Hand", segments=20, ring_count=10)
            bp(hand, f"fore.{side}")
            outline(hand, 0.012)
            self._limb((0.11 * s, 0, 0.70), (0.11 * s, 0, 0.38), 0.033, M["limb"], f"thigh.{side}")
            self._limb((0.11 * s, 0, 0.38), (0.11 * s, 0, 0.08), 0.033, M["limb"], f"shin.{side}")
            bp(prim("uv_sphere", (0.11 * s, 0, 0.38), scale=(0.035,) * 3, mat=M["limb"], name=name + "Knee", segments=12, ring_count=6), f"shin.{side}")
            bp(prim("uv_sphere", (0.11 * s, -0.05, 0.05), scale=(0.085, 0.14, 0.055), mat=M["limb"], name=name + "Shoe", segments=20,
                    ring_count=10), f"shin.{side}")
        # hand props: empties at each hand; parent a prop to them with hold()
        self.hands = {}
        for s, side in ((1, "L"), (-1, "R")):
            e = kit.empty((0.25 * s, 0, 0.57), f"{name}Hand{side}")
            bp(e, f"fore.{side}")
            self.hands[side] = e
        # head
        self.HC, self.HR = Vector((0, 0, 1.58)), 0.33
        self.head = kit.empty(tuple(self.HC), name + "Head")
        bp(self.head, "head")
        self.skull = self._head_child(prim("uv_sphere", tuple(self.HC), mat=M["skin"], name=name + "Skull", radius=self.HR, segments=48, ring_count=24))
        shell = self._head_child(prim("uv_sphere", tuple(self.HC), mat=_INK_SHELL.get("#151313") or outline_shell_mat(), name=name + "SkullInk",
                                      radius=self.HR + 0.017, segments=48, ring_count=24))
        for p in shell.data.polygons:
            p.flip()
        for sx in (-1, 1):
            self._head_child(prim("uv_sphere", (sx * 0.27, 0.07, 1.52), scale=(0.085, 0.12, 0.12), mat=M["hair"], name=name + "Hair",
                                  segments=16, ring_count=8))
        self.cap = None
        if hat:
            self.cap = kit.empty((0, 0, 1.78), name + "Hat")
            self.cap.parent = self.head
            self.cap.matrix_parent_inverse = self.head.matrix_world.inverted()
            self.cap_z = 1.86
            if hat == "cap":
                hp = [prim("uv_sphere", (0, 0.03, 1.74), scale=(0.355, 0.37, 0.24), mat=M["hat"], name=name + "CapDome", segments=32, ring_count=16),
                      prim("cylinder", (0, 0.0, 1.74), mat=M["band"], name=name + "CapBand", radius=0.345, depth=0.07, vertices=32),
                      prim("cylinder", (0, -0.31, 1.73), scale=(1.0, 0.75, 1.0), rot=(-8, 0, 0), mat=M["hat"], name=name + "CapBrim",
                           radius=0.24, depth=0.035, vertices=32),
                      prim("uv_sphere", (0, 0.03, 1.985), scale=(0.05, 0.05, 0.03), mat=M["band"], name=name + "CapButton", segments=12, ring_count=6)]
                self._half_dome(hp[0])
            elif hat == "bowler":
                hp = [prim("uv_sphere", (0, 0.0, 1.76), scale=(0.3, 0.3, 0.26), mat=M["hat"], name=name + "BowlerDome", segments=32, ring_count=16),
                      prim("cylinder", (0, 0.0, 1.75), mat=M["hat"], name=name + "BowlerBrim", radius=0.44, depth=0.03, vertices=32),
                      prim("cylinder", (0, 0.0, 1.79), mat=M["band"], name=name + "BowlerBand", radius=0.305, depth=0.05, vertices=32)]
                self._half_dome(hp[0])
            else:                                                                         # top hat
                hp = [prim("cylinder", (0, 0.0, 1.98), mat=M["hat"], name=name + "TopHat", radius=0.25, depth=0.42, vertices=32),
                      prim("cylinder", (0, 0.0, 1.78), mat=M["hat"], name=name + "TopBrim", radius=0.42, depth=0.03, vertices=32),
                      prim("cylinder", (0, 0.0, 1.83), mat=M["band"], name=name + "TopBand", radius=0.255, depth=0.06, vertices=32)]
            for p in hp:
                p.parent = self.cap
                p.matrix_parent_inverse = self.cap.matrix_world.inverted()
                outline(p, 0.014)
        # face features with shape keys
        self.front_y = self.HC.y - self.HR - 0.02
        glint = emit_mat("#FFFFFF", 1.6, name + "Glint")
        mouth_m = emit_mat("#3A1414", 1.0, name + "Mouth")
        self.eyes, self.glints, self.brows = [], [], []
        ex, ez = 0.042, 0.06
        for s in (-1, 1):
            self.eyes.append(self._feature("Eye", [("basis", _ell(ex, ez)), ("blink", _ell(ex * 1.15, 0.006, 0, -0.01)),
                                                   ("wide", _ell(ex * 1.25, ez * 1.35)), ("squint", _ell(ex * 1.05, ez * 0.45, 0, -0.012))],
                                           (s * 0.105, 0.035), ink))
            self.glints.append(self._feature("Glint", [("basis", _ell(0.012, 0.014, 0.012 * s, 0.022)), ("blink", _ell(0.0005, 0.0005, 0, -0.01)),
                                                       ("wide", _ell(0.015, 0.018, 0.014 * s, 0.035)), ("squint", _ell(0.0005, 0.0005, 0, -0.01))],
                                             (s * 0.105, 0.035), glint))
            self.brows.append(self._feature("Brow", [("basis", _brow(s, 0, 0)), ("up", _brow(s, 0.01, 0.0, 0.05)), ("angry", _brow(s, -0.035, 0.015)),
                                                     ("worried", _brow(s, 0.03, -0.012, 0.02))], (s * 0.11, 0.135), ink))
        self.mouth = self._feature("Mouth", [("basis", _ring(_mouth_smirk)), ("O", _ring(_mouth_open(0.034, 0.05, -0.02))),
                                             ("shock", _ring(_mouth_open(0.07, 0.085, -0.035))), ("grin", _ring(_mouth_grin))],
                                   (0.0, -0.13), mouth_m)

    # ---- construction helpers
    def _bone_parent(self, ob, bone):
        pb = self.rig.pose.bones[bone]
        ob.parent, ob.parent_type, ob.parent_bone = self.rig, "BONE", bone
        ob.matrix_parent_inverse = (self.rig.matrix_world @ pb.matrix @ Matrix.Translation((0, pb.bone.length, 0))).inverted()

    def _limb(self, p0, p1, r, mat, bone):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        ob = prim("cylinder", tuple((p0 + p1) / 2), mat=mat, name=self.name + "Limb", radius=r, depth=d.length, vertices=12)
        ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        self._bone_parent(ob, bone)

    def _head_child(self, ob):
        ob.parent = self.head
        ob.matrix_parent_inverse = self.head.matrix_world.inverted()
        return ob

    @staticmethod
    def _half_dome(ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.02], context="VERTS")
        bm.to_mesh(ob.data)
        bm.free()

    def _feature(self, kind, shapes, center, mat):
        cx, cz = center
        verts = [(cx + x, self.front_y, self.HC.z + cz + z) for x, z in shapes[0][1]]
        ob = mesh_obj(self.name + kind, verts, [tuple(range(len(verts)))], mat)
        ob.shape_key_add(name="Basis")
        for key_name, pts in shapes[1:]:
            k = ob.shape_key_add(name=key_name)
            for i, (x, z) in enumerate(pts):
                k.data[i].co = (cx + x, self.front_y, self.HC.z + cz + z)
        sw = ob.modifiers.new("Wrap", "SHRINKWRAP")
        sw.target, sw.wrap_method, sw.offset = self.skull, "NEAREST_SURFACEPOINT", 0.01
        self._head_child(ob)
        return ob

    # ---- use
    def hold(self, prop, side="R"):
        """parent a prop (built in the rest pose around the hand at x=-0.25 (R) / +0.25 (L), z=0.57) to a hand"""
        e = self.hands[side]
        prop.parent = e
        prop.matrix_parent_inverse = e.matrix_world.inverted()
        return prop

    def set(self, frame, loc, yaw=0.0, pose=None, face=None, hat_pop=0.0):
        """key everything for one frame: root location/yaw (degrees), bone pose (dict from POSES), face values
        (any of FACE_KEYS, 0..1), hat_pop (metres the hat jumps up). Call it for every frame you render."""
        r = self.rig
        r.location, r.rotation_euler = loc, (0, 0, math.radians(yaw))
        r.keyframe_insert("location", frame=frame)
        r.keyframe_insert("rotation_euler", frame=frame)
        for bn, (rx, ry, rz) in (pose or _pose_rest()).items():
            pb = r.pose.bones[bn]
            pb.rotation_euler = kit.rot(rx, ry, rz)
            pb.keyframe_insert("rotation_euler", frame=frame)
        f = {k: 0.0 for k in FACE_KEYS}
        f.update(face or {})
        for ob in self.eyes + self.glints:
            for kn in ("blink", "wide", "squint"):
                kb = ob.data.shape_keys.key_blocks[kn]
                kb.value = f[kn] if kn != "squint" else f[kn] * (1 - f["blink"])
                kb.keyframe_insert("value", frame=frame)
        for ob in self.brows:
            for kn in ("up", "angry", "worried"):
                kb = ob.data.shape_keys.key_blocks[kn]
                kb.value = f[kn]
                kb.keyframe_insert("value", frame=frame)
        for kn in ("O", "shock", "grin"):
            kb = self.mouth.data.shape_keys.key_blocks[kn]
            kb.value = f[kn]
            kb.keyframe_insert("value", frame=frame)
        if self.cap is not None:
            self.cap.location = (0, 0, self.cap_z + hat_pop)
            self.cap.rotation_euler = kit.rot(-25 * min(1.0, hat_pop / 0.32), 0, 0)
            self.cap.keyframe_insert("location", frame=frame)
            self.cap.keyframe_insert("rotation_euler", frame=frame)

    def hide(self, frame, hidden=True):
        """park the character far away for shots it is not in (cheaper than hiding every part)"""
        self.rig.location = (0, 0, -500) if hidden else self.rig.location
        self.rig.keyframe_insert("location", frame=frame)


def outline_shell_mat():
    m = emit_mat("#151313", 1.0, "InkShell")
    m.use_backface_culling = True
    _INK_SHELL["#151313"] = m
    return m


_PTS = 28


def _ring(fn):
    return [fn(2 * math.pi * i / _PTS) for i in range(_PTS)]


def _ell(rx, rz, ox=0.0, oz=0.0):
    return _ring(lambda th: (ox + rx * math.cos(th), oz + rz * math.sin(th)))


def _brow(s, dz_in, dz_out, lift=0.0):
    def fn(th):
        x = 0.068 * math.cos(th)
        t = (x / 0.068 + 1) / 2
        inner = t if s < 0 else 1 - t
        return x, lift + dz_in * inner + dz_out * (1 - inner) + 0.012 * math.sin(math.pi * t) + 0.016 * math.sin(th)
    return _ring(fn)


def _mouth_smirk(th):
    x = 0.07 * math.cos(th) + 0.012
    return x, 3.2 * (x - 0.01) ** 2 + 0.25 * x - 0.012 + 0.009 * math.sin(th)


def _mouth_open(rx, rz, oz=0.0):
    return lambda th: (rx * math.cos(th), oz + rz * math.sin(th))


def _mouth_grin(th):
    x = 0.085 * math.cos(th)
    return x, (0.008 if math.sin(th) > 0 else 0.055) * math.sin(th) + 4.0 * x * x - 0.01


def vo_envelope(path, frames=None, fps=None, gain=1.6):
    """voice loudness per frame {frame: 0..1} from a 16-bit WAV (for mouth flaps: face["O"] = env.get(frame, 0))"""
    a = kit.args()
    frames, fps = frames or a.frames, fps or a.fps
    env = {}
    try:
        with wave.open(path, "rb") as wf:
            sr, ch, n = wf.getframerate(), wf.getnchannels(), wf.getnframes()
            raw = wf.readframes(n)
        samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)[::ch]
        hop = sr // fps
        vals = []
        for fr in range(frames):
            seg = samples[fr * hop:(fr + 1) * hop]
            vals.append(math.sqrt(sum(x * x for x in seg) / max(1, len(seg))) if seg else 0.0)
        peak = max(vals + [1.0])
        for fr, v in enumerate(vals):
            env[fr + 1] = min(1.0, v / peak * gain)
    except Exception as e:
        print(f"KIT note: no voice envelope ({e})")
    return env


# ============================================================== whiteboard
def circle_pts(cx, cy, rx, ry, a0=0.0, a1=2 * math.pi, n=64):
    """points along an ellipse arc, angles in radians (a1 < a0 draws clockwise)"""
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


class Whiteboard:
    """A whiteboard in a dark room under a warm spot light, with marker strokes that draw themselves and handwriting
    that types on, timed in seconds. Board coordinates: u right, v up, metres from the board centre.

        wb = sb.Whiteboard(origin=(2000, 0, 0))
        wb.stroke(sb.circle_pts(0, 0, 0.36, 0.36), "blue", 4.4, 4.95)
        wb.text("Neptune", 0, -0.6, 0.13, "blue", 4.9, 5.3, align="CENTER")
        wb.arrow(points, "red", 4.9, 5.85)
        camera: about 3.5 m in front, a little left, lens 30, slow push in

    Ink is flat (emission) so strokes read as marker, not tubes."""

    INKS = {"black": "#1B1C20", "red": "#B42A22", "blue": "#2154B0", "lblue": "#86ABDF", "green": "#2E8B57", "orange": "#D9822B"}

    def __init__(self, origin=(2000, 0, 0), width=4.2, height=2.5, center_z=1.75, spot_power=360, room=True, seed=7):
        self.o = Vector(origin)
        self.W, self.H, self.Z = width, height, center_z
        self.rng = random.Random(seed)
        self.inks = {k: emit_mat(v, 0.9 if k != "black" else 1.0, "Ink" + k) for k, v in self.INKS.items()}
        self.types = []
        o = self.o
        dark = kit.matte("#1A1B1E", 0.9, "Room")
        metal = kit.metal("#9DA3AA", 0.35, "BoardFrame")
        if room:
            for loc, sc_ in (((0, 1.0, 1.5), (14, 0.2, 7)), ((0, -3, -0.1), (14, 12, 0.2)), ((0, -3, 4.6), (14, 12, 0.2)),
                             ((-6.5, -3, 2), (0.2, 12, 6)), ((6.5, -3, 2), (0.2, 12, 6)), ((0, -9, 2), (14, 0.2, 6))):
                prim("cube", tuple(o + Vector(loc)), scale=sc_, mat=dark, name="RoomWall", smooth_shade=False, size=1.0)
        self.board = prim("cube", tuple(o + Vector((0, 0.86, center_z))), scale=(width, 0.03, height), mat=board_mat(), name="Board",
                          smooth_shade=False, size=1.0)
        for dx, dz, sx, sz in ((0, height / 2, width + 0.08, 0.05), (0, -height / 2, width + 0.08, 0.05), (width / 2, 0, 0.05, height),
                               (-width / 2, 0, 0.05, height)):
            prim("cube", tuple(o + Vector((dx, 0.84, center_z + dz))), scale=(sx, 0.06, sz), mat=metal, name="BoardFrame", smooth_shade=False, size=1.0)
        prim("cube", tuple(o + Vector((0, 0.78, center_z - height / 2 - 0.05))), scale=(width * 0.9, 0.12, 0.03), mat=metal, name="Tray",
             smooth_shade=False, size=1.0)
        self.spot = kit.light("SPOT", tuple(o + Vector((0.4, -2.6, 4.2))), tuple(o + Vector((0.2, 0.85, center_z))), power=spot_power,
                              color="#FFF4E6", size=2.0, name="BoardSpot")
        self.spot.data.spot_size, self.spot.data.spot_blend = math.radians(62), 0.85
        self.fill = kit.light("AREA", tuple(o + Vector((-3, -5, 2.5))), tuple(o + Vector((0, 0.85, center_z))), power=25, color="#9FB4D8",
                              size=3.0, name="RoomFill")
        self.y = o.y + 0.86 - 0.016
        hand = font_path("hand")
        self.hand_font = bpy.data.fonts.load(hand) if hand else None
        bpy.app.handlers.frame_change_pre.append(self._typewriter)

    def p(self, u, v):
        return Vector((self.o.x + u, self.y, self.Z + v))

    def stroke(self, points, ink, t0, t1, width=0.011, wobble=0.004):
        """a marker line through [(u, v), ...] that draws itself from t0 to t1 (seconds)"""
        cu = bpy.data.curves.new(nm("Stroke"), "CURVE")
        cu.dimensions, cu.bevel_depth, cu.bevel_resolution = "3D", width, 2
        cu.bevel_factor_mapping_end = "SPLINE"
        spl = cu.splines.new("POLY")
        spl.points.add(len(points) - 1)
        for i, (u, v) in enumerate(points):
            q = self.p(u + self.rng.uniform(-wobble, wobble), v + self.rng.uniform(-wobble, wobble))
            spl.points[i].co = (q.x, q.y, q.z, 1.0)
        ob = link(bpy.data.objects.new(cu.name, cu))
        ob.data.materials.append(self.inks[ink])
        kit.key(cu, "bevel_factor_end", [(1, 0.0), (kit.f(t0), 0.0), (kit.f(t1), 1.0)], ease="in_out")
        return ob

    def arrow(self, points, ink, t0, t1, head=0.14, width=0.012):
        """a stroke with an arrowhead at its end; the head draws right after the line"""
        self.stroke(points, ink, t0, t1, width)
        end, pre = points[-1], points[max(0, len(points) - 4)]
        dx, dy = end[0] - pre[0], end[1] - pre[1]
        ln = math.hypot(dx, dy) or 1.0
        dx, dy = dx / ln, dy / ln
        for sgn in (1, -1):
            tip = (end[0] - head * dx + sgn * head * 0.57 * -dy, end[1] - head * dy + sgn * head * 0.57 * dx)
            self.stroke([end, tip], ink, t1, t1 + 0.15, width)

    def text(self, body, u, v, size, ink, t0, t1, align="LEFT", tilt=0.0):
        """handwriting that types on from t0 to t1; tilt in degrees"""
        cu = bpy.data.curves.new(nm("Hand"), "FONT")
        cu.body = ""
        if self.hand_font:
            cu.font = self.hand_font
        cu.size, cu.align_x, cu.extrude = size, align, 0.0005
        ob = link(bpy.data.objects.new(cu.name, cu))
        ob.location = self.p(u, v)
        ob.rotation_euler = kit.rot(90, tilt, 0)
        ob.data.materials.append(self.inks[ink])
        self.types.append((cu, body, kit.f(t0), kit.f(t1)))
        return ob

    def _typewriter(self, scene, *_):
        fr = scene.frame_current
        for cu, body, f0, f1 in self.types:
            n = 0 if fr < f0 else len(body) if fr >= f1 else int(len(body) * (fr - f0) / max(1, f1 - f0))
            if cu.body != body[:n]:
                cu.body = body[:n]


# ============================================================== shots
def bake_shots(cam, aim, dof, cuts, shots, ease_mix=0.6):
    """camera per shot, keyed every frame so cuts are hard. shots[i] = dict(cam=(from, to), aim=(from, to), lens=,
    fstop=, focus=) with positions as (x, y, z). ease_mix 0..1: how eased the move is (0 = constant speed)."""
    for fr in range(1, cuts.frames + 1):
        t = cuts.t(fr)
        i = cuts.shot(t)
        u = cuts.u(t)
        s = shots[i]
        e = smooth(u) * ease_mix + u * (1 - ease_mix)
        cam.location = lerp(*s["cam"], e)
        aim.location = lerp(*s["aim"], e)
        cam.data.lens = s.get("lens", 35)
        cam.keyframe_insert("location", frame=fr)
        aim.keyframe_insert("location", frame=fr)
        cam.data.keyframe_insert("lens", frame=fr)
        if dof is not None:
            dof.aperture_fstop, dof.focus_distance = s.get("fstop", 8.0), s.get("focus", 10.0)
            dof.keyframe_insert("aperture_fstop", frame=fr)
            dof.keyframe_insert("focus_distance", frame=fr)


def sun_per_shot(sun, cuts, dirs, powers=None):
    """one SUN light re-aimed for each shot (a film cheat: light every shot well). dirs[i] = the direction the light
    TRAVELS, e.g. (0.9, 0.3, -0.15) = coming from the camera's front-left when the camera looks along +Y."""
    sun.constraints.clear()
    for i in range(len(cuts)):
        fr = cuts.first_frame(i)
        sun.rotation_euler = Vector(dirs[i]).normalized().to_track_quat("-Z", "Y").to_euler()
        sun.keyframe_insert("rotation_euler", frame=fr)
        if powers:
            sun.data.energy = powers[i]
            sun.data.keyframe_insert("energy", frame=fr)
    for fc in kit._fcurves(sun) + kit._fcurves(sun.data):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def hide_sets(cuts, centers, shot_sets, keep=(), force=None):
    """Only the current shot's set renders. centers = {"canyon": (x, y, z), "space": (...), ...} (build each set far
    from the others, 1-3 km apart); shot_sets[i] = the set name of shot i. Objects are sorted to the nearest centre by
    their bounding box (vertices placed in world space still count), force = {obj: set} overrides, keep = objects
    never hidden (camera, aim, sun). Saves render time and stops one set's shadows falling on another."""
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    cen = {k: Vector(v) for k, v in centers.items()}
    force = force or {}
    groups = {k: [] for k in cen}
    for ob in list(sc.objects):
        if ob.type == "CAMERA" or ob in keep:
            continue
        if ob in force:
            groups[force[ob]].append(ob)
            continue
        if ob.type in ("MESH", "CURVE", "FONT") and ob.parent is None and ob.type != "FONT":
            pos = sum((ob.matrix_world @ Vector(c) for c in ob.bound_box), Vector()) / 8
        else:
            pos = ob.matrix_world.translation
        groups[min(cen, key=lambda k: (pos - cen[k]).length)].append(ob)
    firsts = [cuts.first_frame(i) for i in range(len(cuts))]
    for key, obs in groups.items():
        for ob in obs:
            for i, fr in enumerate(firsts):
                ob.hide_render = shot_sets[i] != key
                ob.keyframe_insert("hide_render", frame=fr)
    return groups


# ============================================================== finish
def finish(bloom=0.35, vignette=0.4, grain=0.03, haze=0.0, haze_color="#AFC3EA", haze_start=25.0, haze_depth=420.0, paint=0):
    """compositor finish. haze 0..1: distance fog from the mist pass (bright, airy outdoor scenes); paint: Kuwahara
    brush size in pixels (0 off, 4-7 for a painterly cartoon look). Replaces kit.post()."""
    sc = bpy.context.scene
    if kit.args().alpha:                       # transparent overlays: grading would tint the empty area (like kit.post)
        sc.render.use_compositing = False
        return
    if haze:
        bpy.context.view_layer.use_pass_mist = True
        ms = sc.world.mist_settings
        ms.start, ms.depth, ms.falloff = haze_start, haze_depth, "QUADRATIC"
    if hasattr(sc, "compositing_node_group") and sc.compositing_node_group:
        bpy.data.node_groups.remove(sc.compositing_node_group)
    c = kit._Comp(sc)
    rl = c.image.node
    if haze and rl.outputs.get("Mist") is not None:
        try:                                   # Blender 5.x composites with shader math nodes, 4.x with compositor ones
            mm = c.node("ShaderNodeMath" if kit.V5 else "CompositorNodeMath")
            mm.operation = "MULTIPLY"
            mm.inputs[1].default_value = haze
            c.link(rl.outputs["Mist"], mm.inputs[0])
            c.image = c.mix("MIX", mm.outputs[0], c.image, kit.rgb(haze_color))
        except Exception as ex:
            print(f"KIT note: haze skipped on Blender {bpy.app.version_string}: {ex}")
    if paint:
        try:
            kw = c.node("CompositorNodeKuwahara")
            for attr, val in (("variation", "ANISOTROPIC"), ("use_high_precision", False), ("size", int(paint))):
                try:
                    setattr(kw, attr, val)
                except Exception:
                    pass
            for nm_, val in (("Type", "Anisotropic"), ("Size", int(paint)), ("Uniformity", 4), ("Sharpness", 0.6), ("Eccentricity", 1.0)):
                if nm_ in kw.inputs:
                    try:
                        kw.inputs[nm_].default_value = val
                    except Exception:
                        pass
            c.link(c.image, kw.inputs["Image"])
            c.image = kw.outputs["Image"]
        except Exception as ex:
            print(f"KIT note: painterly filter skipped on Blender {bpy.app.version_string}: {ex}")
    for name, amount in (("bloom", bloom), ("vignette", vignette), ("grain", grain)):
        if amount:
            try:
                getattr(c, name)(amount)
            except Exception as ex:
                print(f"KIT note: {name} skipped: {ex}")
    c.finish()


def font_path(kind="caption"):
    """a font file for a role: caption (Montserrat-Bold), label (Anton / BebasNeue), mono (ShareTechMono, HUD text),
    serif (Gelasio), hand (handwriting: the system's Ink Free on Windows, Noteworthy/Chalkboard on a Mac; None if none
    is found, then Blender's default font is used)"""
    if kind == "hand":
        for p in (r"C:/Windows/Fonts/Inkfree.ttf", "/System/Library/Fonts/Noteworthy.ttc", "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
                  "/Library/Fonts/Chalkboard.ttc"):
            if os.path.exists(p):
                return p
        return None
    name = {"caption": "Montserrat-Bold.ttf", "label": "Anton-Regular.ttf", "condensed": "BebasNeue-Regular.ttf",
            "mono": "ShareTechMono-Regular.ttf", "serif": "Gelasio-Variable.ttf"}.get(kind, kind)
    p = os.path.join(FONTS, name)
    return p if os.path.exists(p) else None
