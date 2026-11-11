"""blender_kit: small helpers for writing your own 3D shots in Blender (imported INSIDE Blender).

You write a scene script; render_blender.py runs it and does the rendering and encoding. A scene script only BUILDS:

    import blender_kit as kit
    a = kit.args()                          # frames, fps, width, height, alpha, out_dir, stills + your --arg values
    kit.setup()                             # clean scene, EEVEE, render policy (1 sample), colour, bloom
    kit.backdrop("#0B0E13", center="#1E2530")
    t = kit.text("1872", font="Anton-Regular", size=2.2, extrude=0.12, color="#E9C46A")
    cam = kit.camera((0, -14, 0.4), look_at=(0, 0, 0), lens=50)
    kit.key(cam, "location", [(1, (0, -14, 0.4)), (a.frames, (0, -11, 0.2))], ease="in_out")
    kit.three_point(target=t)
    kit.post(bloom=0.4, vignette=0.35, grain=0.03)

Conventions (keep to them and every helper lines up):
- Z is up. The camera sits at negative Y looking toward +Y. text() and image_plane() stand upright facing the camera.
- Rotations are in DEGREES. Lengths are metres. Frames are 1-based: frame 1 is the first frame of the shot.
- kit.f(seconds) turns a time in the shot into a frame number, so events can land on the spoken word.
- Colours are "#RRGGBB" strings (sRGB, as in any design tool) or (r, g, b) tuples in 0-1 sRGB.

Render policy: setup() applies the kit's _render_policy.apply(scene) (1 sample, 2 motion-blur steps) and the runner applies
it again just before rendering. Never set samples yourself. Make the shot look good with light, depth, motion and grading.
Works on Blender 4.2 and newer (tested on 5.2). Version differences (EEVEE id, compositor, action API) are handled here.
"""
import argparse
import importlib.util
import math
import os
import random
import sys
import threading
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))


def _start_parent_watchdog(poll=2.0, exit_fn=None):
    """Mac and Linux: exit Blender if the render_blender.py runner that started it is gone (killed, crashed, force-quit).
    Windows does this with a job object in the runner, so nothing starts there. The runner also starts a separate watcher
    process that stops Blender's process group; this thread is the second, independent safety net (it can only run while
    Blender lets Python threads run). Returns the thread, or None when it does not apply."""
    runner = os.environ.get("STUDIO_RUNNER_PID", "")
    if os.name == "nt" or not runner.isdigit():
        return None
    runner, first_parent = int(runner), os.getppid()
    leave = exit_fn or os._exit

    def gone():
        if os.getppid() != first_parent:                     # re-parented to launchd/init: the runner died
            return True
        try:
            os.kill(runner, 0)
        except PermissionError:
            return False
        except OSError:
            return True
        return False

    def watch():
        while True:
            time.sleep(poll)
            if gone():
                print("KIT watchdog: the render runner is gone; stopping Blender", flush=True)
                leave(1)
                return

    t = threading.Thread(target=watch, name="studio-parent-watchdog", daemon=True)
    t.start()
    return t


_start_parent_watchdog()
FONTS = os.path.normpath(os.path.join(HERE, "..", "fonts"))
V5 = bpy.app.version >= (5, 0, 0)

_state = {"args": None, "policy": None, "policy_config": None, "counters": [], "setup": False, "shakes": 0}
SEED = 20261104        # fixed: a render stopped and resumed in a second Blender process must match a single run


# --------------------------------------------------------------------------------------------- arguments and timing
class Args:
    """What the runner asked for. a.get("name") / a.all("name") read your own --arg name=value pairs."""

    def __init__(self, ns, extra):
        self.frames, self.fps, self.alpha, self.out_dir = ns.frames, ns.fps, ns.alpha, ns.out_dir
        self.width, self.height = (int(v) for v in ns.size.lower().split("x"))
        self.size = (self.width, self.height)
        self.stills = [int(s) for s in ns.stills.split(",") if s.strip()] if ns.stills else []
        self.range = tuple(int(v) for v in ns.range.split("-")) if ns.range else None     # runner only: render frames A-B
        self._extra = extra

    def get(self, name, default=None, cast=None):
        vals = self._extra.get(name)
        if not vals:
            return default
        return cast(vals[-1]) if cast else vals[-1]

    def all(self, name):
        return list(self._extra.get(name, []))

    def __repr__(self):
        return f"Args(frames={self.frames}, fps={self.fps}, size={self.size}, alpha={self.alpha}, extra={self._extra})"


def args():
    """Parse the arguments after '--' (render_blender.py passes them). Safe to call many times."""
    if _state["args"] is None:
        random.seed(SEED)                       # scene scripts that use random get the same numbers in every process
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
        p = argparse.ArgumentParser(prog="scene")
        p.add_argument("--frames", type=int, default=120)
        p.add_argument("--fps", type=int, default=30)
        p.add_argument("--size", default="1920x1080")
        p.add_argument("--alpha", action="store_true")
        p.add_argument("--out-dir", dest="out_dir", default=os.path.join(os.getcwd(), "kit-frames"))
        p.add_argument("--stills", default="")
        p.add_argument("--range", default="")
        p.add_argument("--arg", action="append", default=[], help="name=value, repeatable")
        ns, _ = p.parse_known_args(argv)
        extra = {}
        for item in ns.arg:
            k, _, v = item.partition("=")
            extra.setdefault(k.strip(), []).append(v)
        _state["args"] = Args(ns, extra)
    return _state["args"]


def f(seconds):
    """Frame number (1-based) at `seconds` into the shot. kit.f(1.5) at 30 fps -> 46."""
    return int(round(seconds * args().fps)) + 1


# --------------------------------------------------------------------------------------------- render policy
def _find_policy():
    """The kit's tools/_render_policy.py (found by walking up from this file or the working folder), else the copy here."""
    seen = []
    for start in (HERE, os.getcwd()):
        d = start
        for _ in range(8):
            seen.append(os.path.join(d, "tools", "_render_policy.py"))
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    seen.append(os.path.join(HERE, "_render_policy.py"))
    for path in seen:
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("_render_policy", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "apply"):
                mod.__kit_path__ = path
                return mod
    raise RuntimeError("render policy not found (tools/_render_policy.py)")


def apply_policy(scene=None):
    """Apply the render policy to the scene. setup() and the runner both call this; you never need to."""
    if _state["policy"] is None:
        _state["policy"] = _find_policy()
    return _state["policy"].apply(scene or bpy.context.scene, _state["policy_config"])


# --------------------------------------------------------------------------------------------- colour helpers
def rgb(c, alpha=1.0):
    """'#RRGGBB' or sRGB (r, g, b[, a]) -> linear RGBA tuple for Blender sockets."""
    if isinstance(c, str):
        h = c.lstrip("#")
        c = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c[:3])
    return lin + ((c[3] if len(c) > 3 else alpha),)


def _rad(rot):
    return tuple(math.radians(v) for v in rot)


def rot(x=0.0, y=0.0, z=0.0):
    """Degrees -> the radians tuple Blender stores, for keying rotation: kit.key(ob, "rotation_euler", [(1, kit.rot(90, 0, 10))])."""
    return _rad((x, y, z))


# --------------------------------------------------------------------------------------------- scene setup
def _eevee_id():
    ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"


def _nodes_on(idblock):
    try:
        if not idblock.use_nodes:
            idblock.use_nodes = True      # deprecated no-op on 5.x, needed on 4.x
    except AttributeError:
        pass
    return idblock.node_tree


def setup(frames=None, fps=None, size=None, alpha=None, view="AgX", look="Punchy", exposure=0.0, motion_blur=0.35,
          bloom=0.35, world="#06080B", policy_config=None):
    """Start a clean shot. Defaults come from kit.args(). Returns the scene.

    view: "AgX" (filmic, best for lit 3D) or "Standard" (exact colours: flat graphics, overlays).
    look: AgX look such as "Punchy", "Medium High Contrast" or None. bloom: 0 turns the glare off.
    motion_blur: shutter (0 = off). 0.35 is a natural film blur; at 1 sample very fast moves blur grainy, so ease them.
    world: the colour around everything (keep it dark; it also tints reflections).
    policy_config: ONLY for a user's own word-for-word request for another sample count (see _render_policy.py).
    """
    a = args()
    frames, fps = frames or a.frames, fps or a.fps
    w, h = size or a.size
    alpha = a.alpha if alpha is None else alpha
    _state["policy_config"] = policy_config
    _state["counters"].clear()
    _state["shakes"] = 0
    random.seed(SEED)

    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights, bpy.data.materials):
        for item in list(coll):
            if item.users == 0:
                coll.remove(item)

    sc = bpy.context.scene
    sc.render.engine = _eevee_id()
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.fps, sc.render.fps_base = fps, 1.0
    sc.frame_start, sc.frame_end = 1, frames
    sc.frame_set(1)
    sc.render.film_transparent = bool(alpha)
    sc.render.use_motion_blur = bool(motion_blur)
    if motion_blur:
        sc.render.motion_blur_shutter = float(motion_blur)
    sc.render.use_lock_interface = True          # text counters change data between frames
    ee = sc.eevee
    for attr, val in (("use_raytracing", False), ("use_shadows", True), ("use_gtao", False),
                      ("use_bloom", False), ("use_ssr", False)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)

    vs = sc.view_settings
    for v in ((view, "AgX", "Filmic", "Standard") if view != "Standard" else ("Standard",)):
        try:
            vs.view_transform = v
            break
        except TypeError:
            continue
    vs.exposure = exposure
    if look and vs.view_transform != "Standard":
        for name in (f"{vs.view_transform} - {look}", look, "None"):
            try:
                vs.look = name
                break
            except TypeError:
                continue

    wd = sc.world or bpy.data.worlds.new("World")
    sc.world = wd
    nt = _nodes_on(wd)
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        bg = nt.nodes.new("ShaderNodeBackground")
        out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
        nt.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs["Color"].default_value = rgb(world)
    bg.inputs["Strength"].default_value = 1.0

    apply_policy(sc)
    _state["setup"] = True
    if alpha:
        sc.render.use_compositing = False
    else:
        post(bloom=bloom)
    return sc


# --------------------------------------------------------------------------------------------- animation
EASES = {   # name -> (interpolation, easing) for the segment that STARTS at a key
    "linear": ("LINEAR", "AUTO"), "smooth": ("BEZIER", "AUTO"), "in_out": ("SINE", "EASE_IN_OUT"),
    "out": ("CUBIC", "EASE_OUT"), "in": ("CUBIC", "EASE_IN"), "expo": ("EXPO", "EASE_OUT"),
    "expo_in_out": ("EXPO", "EASE_IN_OUT"), "back": ("BACK", "EASE_OUT"), "bounce": ("BOUNCE", "EASE_OUT"),
    "hold": ("CONSTANT", "AUTO"),
}


def _fcurves(idblock):
    ad = idblock.animation_data
    if not ad or not ad.action:
        return []
    act, slot = ad.action, getattr(ad, "action_slot", None)
    if slot is not None and getattr(act, "layers", None):         # 4.4+ layered actions (5.x has no act.fcurves)
        found = []
        for layer in act.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag:
                    found.extend(bag.fcurves)
        if found or not hasattr(act, "fcurves"):
            return found
    return list(act.fcurves)


def key(target, path, keys, ease="smooth", index=-1):
    """Keyframe target.path. keys = [(frame, value), ...] or (frame, value, ease) to change the ease of one segment.

    target: an object, camera data, light data, a node socket, anything with keyframe_insert.
    ease: linear | smooth | in_out | out | in | expo | expo_in_out | back (overshoot) | bounce | hold.
    index: one channel of a vector, e.g. key(cam, "location", [(1, -14), (90, -11)], index=1) moves only Y.
    """
    eases = {}
    for k in keys:
        frame, value = k[0], k[1]
        if index >= 0:
            getattr(target, path)[index] = value
        else:
            setattr(target, path, value)
        target.keyframe_insert(path, frame=frame, index=index)
        eases[round(frame)] = k[2] if len(k) > 2 else ease
    full = target.path_from_id(path)
    for fc in _fcurves(target.id_data):
        if fc.data_path != full or (index >= 0 and fc.array_index != index):
            continue
        for kp in fc.keyframe_points:
            name = eases.get(round(kp.co[0]))
            if name:
                kp.interpolation, kp.easing = EASES[name]
                if name == "back":
                    kp.back = 1.4
        fc.update()


def shake(obj, strength=0.03, speed=30.0, path="location"):
    """Gentle hand-held drift on top of existing keys (adds noise to every channel of obj.path). Key obj first."""
    full = obj.path_from_id(path)
    for fc in _fcurves(obj.id_data):
        if fc.data_path == full:
            m = fc.modifiers.new("NOISE")
            _state["shakes"] += 1               # own seeded generator: the same drift in every Blender process
            m.strength, m.scale, m.phase = strength, speed, random.Random(SEED + _state["shakes"]).uniform(0, 100)


def _ease(name, t):
    t = max(0.0, min(1.0, t))
    return {"linear": t, "in": t ** 3, "out": 1 - (1 - t) ** 3, "in_out": 0.5 - 0.5 * math.cos(math.pi * t),
            "expo": 1.0 if t >= 1 else 1 - 2 ** (-10 * t)}.get(name, 1 - (1 - t) ** 3)


def number_count(text_obj, start, end, frame_a, frame_b, fmt="{:,.0f}", ease="out"):
    """Count text_obj's digits from start to end between two frames. fmt: "${:,.0f}", "{:.1f}%", or a function(value)."""
    _state["counters"].append(dict(obj=text_obj.name, a=start, b=end, fa=frame_a, fb=frame_b, fmt=fmt, ease=ease))
    if _count_handler not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(_count_handler)
    _count_handler(bpy.context.scene)


def _count_handler(scene, *_):
    for c in _state["counters"]:
        ob = bpy.data.objects.get(c["obj"])
        if ob is None:
            continue
        fr = round(scene.frame_current + scene.frame_subframe)    # same digits for every motion-blur step of a frame
        t = (fr - c["fa"]) / max(1, c["fb"] - c["fa"])
        v = c["a"] + (c["b"] - c["a"]) * _ease(c["ease"], t)
        ob.data.body = c["fmt"](v) if callable(c["fmt"]) else c["fmt"].format(v)


# --------------------------------------------------------------------------------------------- materials
def _material(name):
    """New material: Output <- Mix(KitAlpha: Transparent, surface). Returns (mat, nodes, surface_input_socket)."""
    mat = bpy.data.materials.new(name)
    nt = _nodes_on(mat)
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.name = mix.label = "KitAlpha"
    mix.inputs[0].default_value = 1.0
    nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat, nt, mix.inputs[2]


def emission(color="#FFFFFF", strength=1.0, name="Emission"):
    """Unlit colour. Exact on screen with view="Standard"; strength above 1 glows (with bloom)."""
    mat, nt, surf = _material(name)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = rgb(color)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], surf)
    return mat


def _principled(name, color, metallic, roughness, **extra):
    mat, nt, surf = _material(name)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = rgb(color)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = roughness
    for sock, val in extra.items():
        sock = sock.replace("_", " ")
        if sock in p.inputs:
            p.inputs[sock].default_value = val
    nt.links.new(p.outputs[0], surf)
    return mat


def matte(color="#CCCCCC", roughness=0.5, name="Matte"):
    """Lit, non-metal surface (paper, paint, card)."""
    return _principled(name, color, 0.0, roughness)


def metal(color="#D8B46A", roughness=0.28, name="Metal"):
    """Lit metal. Needs lights (or a bright backdrop) to reflect, else it reads black."""
    return _principled(name, color, 1.0, roughness)


def glass(color="#DDEEFF", roughness=0.08, name="Glass"):
    """Glass-ish: clear, glossy and slightly see-through. EEVEE without ray tracing fakes refraction; fine for accents."""
    mat = _principled(name, color, 0.0, roughness, Transmission_Weight=1.0, IOR=1.45, Alpha=0.55)
    _blended(mat)
    return mat


def assign(obj, mat):
    """Replace obj's materials with mat."""
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def _blended(mat):
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"     # smooth fades at 1 sample (DITHERED would stipple)
    else:
        mat.blend_method = "BLEND"


def fade(obj, keys, ease="smooth"):
    """Fade an object made by the kit: keys = [(frame, alpha 0-1), ...]. Also fades its children (photo borders)."""
    for ob in [obj] + list(obj.children_recursive):
        for slot in ob.material_slots:
            mat = slot.material
            node = mat and mat.node_tree and mat.node_tree.nodes.get("KitAlpha")
            if node:
                _blended(mat)
                key(node.inputs[0], "default_value", keys, ease)


# --------------------------------------------------------------------------------------------- objects
def _link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _quad(name, w, h, anchor="center"):
    x0 = {"left": 0.0, "right": -w, "center": -w / 2}[anchor]
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, -h / 2, 0), (x0 + w, -h / 2, 0), (x0 + w, h / 2, 0), (x0, h / 2, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for loop, co in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = co
    return _link(bpy.data.objects.new(name, me))


def empty(loc=(0, 0, 0), name="Empty"):
    """An invisible handle: parent things to it and move the group."""
    ob = bpy.data.objects.new(name, None)
    ob.location = loc
    return _link(ob)


def parent(child, par):
    """Parent child to par. child's location/rotation become RELATIVE to par, so build a group around (0, 0, 0)
    and move, scale or fade the parent. Example: card = kit.empty((x, y, z)); kit.parent(kit.rect(...), card)."""
    child.parent = par
    return child


def measure(obj):
    """(width, height) of an object in metres as it stands now, e.g. to size a panel to its text."""
    bpy.context.view_layer.update()
    d = obj.dimensions
    return d.x, (d.y if obj.type in ("FONT", "CURVE") or abs(d.y) > abs(d.z) else d.z)


def rect(w, h, color="#FFFFFF", loc=(0, 0, 0), rot=(90, 0, 0), material=None, anchor="center", name="Rect"):
    """Flat rectangle (bars, cards, rules). anchor="left" puts the origin on the left edge, so scale.x grows it rightward."""
    ob = _quad(name, w, h, anchor)
    ob.location, ob.rotation_euler = loc, _rad(rot)
    return assign(ob, material or emission(color, name=name))


def _font(font):
    path = font if os.path.isfile(font) else os.path.join(FONTS, font if font.lower().endswith((".ttf", ".otf")) else font + ".ttf")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"font not found: {font} (fonts here: {', '.join(sorted(os.listdir(FONTS)))})")
    return bpy.data.fonts.load(path, check_existing=True)


def text(body, font="Montserrat-Bold", size=1.0, extrude=0.0, bevel=0.0, color="#FFFFFF", align="CENTER",
         material=None, loc=(0, 0, 0), rot=(90, 0, 0), spacing=1.0, strength=1.0, name="Text"):
    """3D (extrude > 0) or flat text, standing up facing the camera.

    font: Montserrat-Bold | Anton-Regular | Gelasio-Variable (regular serif) | Montserrat, or a .ttf path.
          Montserrat.ttf is a variable font that Blender loads at its THIN weight: hairline, only for big display text.
          For small text (roles, captions, labels) use Montserrat-Bold, ideally in capitals with spacing=1.15.
    size: cap height is about 0.7 * size metres. align: LEFT | CENTER | RIGHT (origin at that edge).
    Default material: flat text = emission (crisp colour); 3D text = lit matte in `color`.
    strength: brightness of flat text. Under view="AgX" white at 1.0 reads light grey; 1.4-1.8 reads white.
    """
    cu = bpy.data.curves.new(name, "FONT")
    cu.body, cu.font, cu.size = body, _font(font), size
    cu.extrude, cu.bevel_depth, cu.bevel_resolution = extrude, bevel, 3
    cu.align_x, cu.align_y, cu.space_character = align.upper(), "CENTER", spacing
    ob = _link(bpy.data.objects.new(name, cu))
    ob.location, ob.rotation_euler = loc, _rad(rot)
    return assign(ob, material or (emission(color, strength, name) if extrude == 0 and bevel == 0 else matte(color, 0.35, name)))


def image_plane(path, width=4.0, loc=(0, 0, 0), rot=(90, 0, 0), lit=False, strength=1.0, border=0.0,
                border_color="#F1EDE4", name=None):
    """A real photo on a plane with the photo's own aspect ratio. Returns the plane (height = obj["height"]).

    lit=False: emission, the photo looks exactly like itself. lit=True: it takes the scene's light and shadow.
    border: white print border in metres (0.08 is a classic print); the border is parented to the photo.
    """
    path = os.path.abspath(path)
    img = bpy.data.images.load(path, check_existing=True)
    iw, ih = img.size
    if not iw or not ih:
        raise ValueError(f"could not read image: {path}")
    h = width * ih / iw
    name = name or os.path.splitext(os.path.basename(path))[0]
    ob = _quad(name, width, h)
    ob.location, ob.rotation_euler = loc, _rad(rot)
    ob["height"] = h
    mat, nt, surf = _material(name)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image, tex.interpolation, tex.extension = img, "Cubic", "EXTEND"
    if lit:
        p = nt.nodes.new("ShaderNodeBsdfPrincipled")
        p.inputs["Roughness"].default_value = 0.55
        nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
        nt.links.new(p.outputs[0], surf)
    else:
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = strength
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], surf)
    assign(ob, mat)
    if border > 0:
        b = _quad(name + ".border", width + 2 * border, h + 2 * border)
        assign(b, matte(border_color, 0.6, name + ".border"))
        b.parent = ob
        b.location = (0, 0, -0.004)        # just behind the photo (local -Z faces away from the camera)
    return ob


def backdrop(color="#0B0E13", center=None, image=None, distance=12.0, size=90.0, lit=False, name="Backdrop"):
    """A wall behind everything, facing the camera at y=distance. center: a lighter colour in the middle (soft spotlight
    falloff). image: a photo instead (blur or darken it yourself first if it competes with the subject). lit=True takes
    light and shadow (use it when objects should throw shadows onto it)."""
    if image:
        ob = image_plane(image, width=size * 0.4, loc=(0, distance, 0), lit=lit, name=name)
        return ob
    ob = _quad(name, size, size * 0.6)
    ob.location, ob.rotation_euler = (0, distance, 0), _rad((90, 0, 0))
    mat, nt, surf = _material(name)
    edge = rgb(color)
    mid = rgb(center) if center else edge
    co = nt.nodes.new("ShaderNodeTexCoord")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = 0.0, 0.22
    rng.interpolation_type = "SMOOTHSTEP"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value, mix.inputs[7].default_value = mid, edge
    nt.links.new(co.outputs["UV"], sub.inputs[0])
    nt.links.new(sub.outputs[0], ln.inputs[0])
    nt.links.new(ln.outputs["Value"], rng.inputs["Value"])
    nt.links.new(rng.outputs[0], mix.inputs[0])
    if lit:
        shader = nt.nodes.new("ShaderNodeBsdfPrincipled")
        shader.inputs["Roughness"].default_value = 0.85
        nt.links.new(mix.outputs[2], shader.inputs["Base Color"])
    else:
        shader = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(mix.outputs[2], shader.inputs["Color"])
    nt.links.new(shader.outputs[0], surf)
    return assign(ob, mat)


def floor(color="#0D1014", z=-1.5, size=80.0, roughness=0.35, name="Floor"):
    """A lit floor plane at height z: grounds objects with contact shadows and soft highlights."""
    return rect(size, size, loc=(0, 0, z), rot=(0, 0, 0), material=matte(color, roughness, name), name=name)


def motes(count=80, center=(0, 0, 0), spread=(14, 10, 7), size=0.012, color="#FFE7C2", strength=3.0, seed=7):
    """Tiny glowing specks scattered in depth. With depth of field they become soft bokeh: cheap depth and air.
    Returns their parent empty (animate it for a slow drift)."""
    rnd = random.Random(seed)
    root = empty(center, "Motes")
    me = bpy.data.meshes.new("Mote")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=size)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(emission(color, strength, "Mote"))
    for i in range(count):
        ob = _link(bpy.data.objects.new(f"Mote.{i:03d}", me))
        ob.location = tuple(rnd.uniform(-s / 2, s / 2) for s in spread)
        ob.scale = (rnd.uniform(0.5, 1.6),) * 3
        ob.parent = root
    return root


# --------------------------------------------------------------------------------------------- camera and light
def camera(loc=(0, -12, 0), look_at=(0, 0, 0), lens=40.0, ortho=None, name="Camera"):
    """Camera aimed at a target (an empty you can animate: kit.aim(cam)). ortho=width in metres for a flat 2D camera.
    Becomes the scene camera. Animate it with kit.key(cam, "location", ...) and kit.key(kit.aim(cam), "location", ...)."""
    cam = _link(bpy.data.objects.new(name, bpy.data.cameras.new(name)))
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_start, cam.data.clip_end = 0.05, 500
    if ortho:
        cam.data.type, cam.data.ortho_scale = "ORTHO", ortho
    target = empty(look_at if not hasattr(look_at, "location") else look_at.location, name + ".aim")
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    bpy.context.scene.camera = cam
    return cam


def aim(cam):
    """The empty the camera looks at."""
    return cam.constraints[0].target


def screen_camera(name="ScreenCam"):
    """Flat orthographic camera for overlays and 2D graphics. Pair it with kit.screen(x, y) for pixel positions."""
    cam = camera((0, -10, 0), (0, 0, 0), ortho=19.2, name=name)
    return cam


def screen(x, y, depth=0.0):
    """World position of a pixel on a 1920x1080 reference frame (0,0 = top left) for screen_camera(). Scales with size."""
    w, h = args().size
    return ((x / 1920 - 0.5) * 19.2, depth, (0.5 - y / 1080) * 19.2 * h / w)


def light(kind="AREA", loc=(4, -6, 5), target=(0, 0, 0), power=500.0, color="#FFFFFF", size=3.0, name="Light"):
    """One light aimed at target (a point or an object). kind: AREA | SPOT | POINT | SUN. power: watts (sun: strength)."""
    data = bpy.data.lights.new(name, kind)
    data.energy, data.color = power, rgb(color)[:3]
    if kind == "AREA":
        data.size = size
    elif kind in ("POINT", "SPOT"):
        data.shadow_soft_size = size * 0.1
    if kind == "SPOT":
        data.spot_size, data.spot_blend = math.radians(45), 0.6
    ob = _link(bpy.data.objects.new(name, data))
    ob.location = loc
    con = ob.constraints.new("TRACK_TO")
    con.track_axis, con.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    con.target = target if hasattr(target, "location") else empty(target, name + ".aim")
    return ob


def three_point(target=(0, 0, 0), power=1.0, warm="#FFD9B0", cool="#B5CCFF", distance=8.0):
    """Key (warm, front left, high), fill (cool, front right, low) and rim (behind, high). Returns {key, fill, rim}."""
    tl = target.location if hasattr(target, "location") else target
    d = distance
    tx, ty, tz = tl
    return {
        "key": light("AREA", (tx - 0.6 * d, ty - 0.8 * d, tz + 0.6 * d), target, 900 * power, warm, 4.0, "Key"),
        "fill": light("AREA", (tx + 0.8 * d, ty - 0.6 * d, tz + 0.1 * d), target, 250 * power, cool, 6.0, "Fill"),
        "rim": rim(target, cool, 1200 * power, distance=d),
    }


def rim(target=(0, 0, 0), color="#B5CCFF", power=1200.0, distance=8.0, side=1):
    """Back light that draws a bright edge around the subject (side=1 right, -1 left)."""
    tl = target.location if hasattr(target, "location") else target
    loc = (tl[0] + side * 0.5 * distance, tl[1] + 0.7 * distance, tl[2] + 0.5 * distance)
    return light("AREA", loc, target, power, color, 3.0, "Rim")


def depth_of_field(cam, focus=None, fstop=2.8):
    """Turn on depth of field. focus: an object to stay sharp, or a distance in metres. Returns cam.data.dof, so a
    focus pull is kit.key(dof, "focus_distance", [...]) and an aperture change kit.key(dof, "aperture_fstop", [...])."""
    dof = cam.data.dof
    dof.use_dof, dof.aperture_fstop = True, fstop
    ee = bpy.context.scene.eevee
    if hasattr(ee, "bokeh_max_size"):
        ee.bokeh_max_size = max(ee.bokeh_max_size, 160.0)      # blur radius cap in pixels (not samples)
    if hasattr(focus, "location"):
        dof.focus_object = focus
    elif focus is not None:
        dof.focus_distance = float(focus)
    return dof


# --------------------------------------------------------------------------------------------- compositor finish
class _Comp:
    """Tiny adapter over the two compositor APIs (4.x scene.node_tree / 5.x scene.compositing_node_group)."""

    def __init__(self, sc):
        if hasattr(sc, "compositing_node_group"):
            ng = bpy.data.node_groups.new("Kit Finish", "CompositorNodeTree")
            ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            sc.compositing_node_group = ng
            self.tree, self.out = ng, ng.nodes.new("NodeGroupOutput").inputs[0]
        else:
            sc.use_nodes = True
            self.tree = sc.node_tree
            self.tree.nodes.clear()
            self.out = self.tree.nodes.new("CompositorNodeComposite").inputs["Image"]
        sc.render.use_compositing = True
        self.image = self.tree.nodes.new("CompositorNodeRLayers").outputs["Image"]

    def node(self, kind):
        return self.tree.nodes.new(kind)

    def link(self, a, b):
        self.tree.links.new(a, b)

    def mix(self, blend, fac, a, b):
        """Blend a and b (a colour/float socket each). fac: float or a socket. Returns the output socket."""
        if V5:
            m = self.node("ShaderNodeMix")
            m.data_type, m.blend_type, m.clamp_result = "RGBA", blend, False
            ins, out = (m.inputs[0], m.inputs[6], m.inputs[7]), m.outputs[2]
        else:
            m = self.node("CompositorNodeMixRGB")
            m.blend_type = blend
            ins, out = (m.inputs[0], m.inputs[1], m.inputs[2]), m.outputs[0]
        for sock, val in zip(ins, (fac, a, b)):
            if hasattr(val, "is_linked") or hasattr(val, "links"):
                self.link(val, sock)
            else:
                sock.default_value = val
        return out

    def bloom(self, amount):
        g = self.node("CompositorNodeGlare")
        if V5:
            g.inputs["Type"].default_value, g.inputs["Quality"].default_value = "Bloom", "Medium"
            g.inputs["Threshold"].default_value = 0.9
            g.inputs["Strength"].default_value = amount
            g.inputs["Size"].default_value = 0.7
        else:
            try:
                g.glare_type = "BLOOM"
            except TypeError:
                g.glare_type = "FOG_GLOW"
            g.quality, g.threshold, g.mix, g.size = "MEDIUM", 0.9, amount - 1.0, 8
        self.link(self.image, g.inputs["Image"])
        self.image = g.outputs["Image"]

    def vignette(self, amount):
        if V5:
            co = self.node("CompositorNodeImageCoordinates")
            self.link(self.image, co.inputs[0])
            sub = self.node("ShaderNodeVectorMath")
            sub.operation = "SUBTRACT"
            sub.inputs[1].default_value = (0.5, 0.5, 0.0)
            self.link(co.outputs["Normalized"], sub.inputs[0])
            ln = self.node("ShaderNodeVectorMath")
            ln.operation = "LENGTH"
            self.link(sub.outputs[0], ln.inputs[0])
            ramp = self.node("ShaderNodeMapRange")
            ramp.interpolation_type = "SMOOTHSTEP"
            self.link(ln.outputs["Value"], ramp.inputs["Value"])
            ramp.inputs["From Min"].default_value, ramp.inputs["From Max"].default_value = 0.72, 0.28
            mask = ramp.outputs[0]                                    # 1 in the middle, 0 in the corners
        else:
            e = self.node("CompositorNodeEllipseMask")
            e.width, e.height = 0.95, 0.95
            bl = self.node("CompositorNodeBlur")
            bl.filter_type, bl.use_relative, bl.factor_x, bl.factor_y = "FAST_GAUSS", True, 22, 22
            self.link(e.outputs["Mask"], bl.inputs["Image"])
            mask = bl.outputs["Image"]
        self.image = self.mix("MULTIPLY", amount, self.image, mask)

    def grain(self, amount):
        if V5:
            co = self.node("CompositorNodeImageCoordinates")
            self.link(self.image, co.inputs[0])
            t = self.node("CompositorNodeSceneTime")
            n = self.node("ShaderNodeTexWhiteNoise")
            n.noise_dimensions = "4D"
            self.link(co.outputs["Pixel"], n.inputs["Vector"])
            self.link(t.outputs["Frame"], n.inputs["W"])
            noise = n.outputs["Value"]
        else:
            tex = bpy.data.textures.get("KitGrain") or bpy.data.textures.new("KitGrain", "NOISE")
            n = self.node("CompositorNodeTexture")
            n.texture = tex
            noise = n.outputs["Value"]
        self.image = self.mix("OVERLAY", amount, self.image, noise)

    def finish(self):
        self.link(self.image, self.out)


def post(bloom=0.35, vignette=0.0, grain=0.0):
    """Finish the picture in the compositor: bloom on bright parts, darker corners, light film grain. Cheap at 1080p.
    Calling it again replaces the previous finish. Skip it on alpha overlays (it would grade the transparent area).
    Good defaults: post(bloom=0.35, vignette=0.35, grain=0.03)."""
    sc = bpy.context.scene
    if hasattr(sc, "compositing_node_group") and sc.compositing_node_group:
        bpy.data.node_groups.remove(sc.compositing_node_group)
    if not (bloom or vignette or grain):
        sc.render.use_compositing = False
        return
    c = _Comp(sc)
    for name, amount in (("bloom", bloom), ("vignette", vignette), ("grain", grain)):
        if amount:
            try:
                getattr(c, name)(amount)
            except Exception as e:              # a node missing on this Blender version must never stop the shot
                print(f"KIT note: {name} skipped on Blender {bpy.app.version_string}: {e}")
    c.finish()


# --------------------------------------------------------------------------------------------- render (runner only)
def _render():
    """Called by render_blender.py after your scene script. Re-applies the policy, then writes PNG frames to out_dir.

    This is also the guard: whatever the scene script did, the shot is rendered with EEVEE at the runner's --size
    (100 percent), with the render policy re-applied. Each override is printed as a "KIT note" line."""
    a, sc = args(), bpy.context.scene
    if not _state["setup"]:
        raise RuntimeError("the scene script never called kit.setup()")
    if sc.camera is None:
        raise RuntimeError("the scene has no camera: call kit.camera(...) or kit.screen_camera()")
    r = sc.render
    eevee = _eevee_id()
    if r.engine != eevee:
        print(f"KIT note: the scene script set the render engine to {r.engine}; forced back to EEVEE ({eevee}). "
              f"Cycles and Workbench are not allowed in this kit.")
        r.engine = eevee
    if (r.resolution_x, r.resolution_y, r.resolution_percentage) != (a.width, a.height, 100):
        print(f"KIT note: the scene script set the resolution to {r.resolution_x}x{r.resolution_y} at "
              f"{r.resolution_percentage}%; forced to {a.width}x{a.height} at 100% (the runner's --size).")
        r.resolution_x, r.resolution_y, r.resolution_percentage = a.width, a.height, 100
    n = apply_policy(sc)
    sc.frame_start, sc.frame_end = 1, a.frames
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA" if a.alpha else "RGB"
    r.image_settings.color_depth = "16" if a.alpha else "8"
    r.image_settings.compression = 15
    os.makedirs(a.out_dir, exist_ok=True)
    print(f"KIT render policy={getattr(_state['policy'], 'POLICY', '?')} samples={n} "
          f"engine={r.engine} size={r.resolution_x}x{r.resolution_y} file={_state['policy'].__kit_path__}")
    if a.stills:
        for fr in a.stills:
            sc.frame_set(fr)
            r.filepath = os.path.join(a.out_dir, f"still_{fr:04d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        if a.range:                                  # the runner renders the first frames, then the rest
            sc.frame_start, sc.frame_end = max(1, a.range[0]), min(a.frames, a.range[1])
        r.filepath = os.path.join(a.out_dir, "f_####")
        clock = {"t": time.time()}

        def _pre(*_):
            clock["t"] = time.time()

        def _post(scene, *_):
            print(f"KIT frame {scene.frame_current} {time.time() - clock['t']:.3f}", flush=True)

        bpy.app.handlers.render_pre.append(_pre)
        bpy.app.handlers.render_post.append(_post)
        bpy.ops.render.render(animation=True)
    print("KIT done")
