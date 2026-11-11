"""Prove Blender works from the command line: render one 640x360 frame of a lit gold "BLENDER KIT" title with the render policy applied.

  python tools/blender_check.py            (finds Blender the same way tools/doctor.py does)
Writes renders/blender-check.png and prints the Blender version and the sample count used. Takes a few seconds to a minute.
Inside Blender this same file builds the scene (it is run as: blender -b --factory-startup -P tools/blender_check.py -- OUT.png).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if "bpy" not in sys.modules and "--" not in sys.argv:          # ---- outside Blender: launch it
    sys.path.insert(0, HERE)
    from doctor import blender_path
    exe = blender_path()
    if not exe:
        sys.exit("Blender not found. Run the Blender setup first (or install it from blender.org).")
    out = os.path.join(os.path.dirname(HERE), "renders", "blender-check.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    kw = {"creationflags": 0x4000} if os.name == "nt" else {"preexec_fn": lambda: os.nice(10), "start_new_session": True}
    p = subprocess.Popen([exe, "-b", "--factory-startup", "-P", os.path.abspath(__file__), "--", out], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, errors="replace", **kw)
    try:
        so, se = p.communicate(timeout=600)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as e:
        try:                                                    # stop Blender and anything it started, then confirm it is gone
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(p.pid, 9)
        except OSError:
            pass
        p.kill()
        p.wait(timeout=30)
        sys.exit("Blender did not finish within 10 minutes and was stopped." if isinstance(e, subprocess.TimeoutExpired)
                 else "Stopped.")
    ok = p.returncode == 0 and os.path.exists(out)
    tail = "\n".join(l for l in (so + se).splitlines() if "CHECK" in l or "Error" in l)
    print(tail or (so + se)[-800:])
    if not ok and sys.platform == "darwin":
        print("On a Mac, if macOS blocked Blender: open the Blender app once from Applications (double-click; if it says it can't be "
              "checked, open System Settings > Privacy & Security and click Open Anyway), close it, and run this again.")
    sys.exit(0 if ok else 1)

import bpy  # noqa: E402  (inside Blender)
sys.path.insert(0, HERE)
import _render_policy  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
sc = bpy.context.scene
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 640, 360, 100
n = _render_policy.apply(sc)
bpy.ops.object.text_add(location=(0, 0, 0))
t = bpy.context.object
t.data.body = "BLENDER KIT"
t.data.align_x = "CENTER"
t.data.extrude = 0.06
t.rotation_euler = (1.5708, 0, 0)
mat = bpy.data.materials.new("Title")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.95, 0.75, 0.3, 1)
t.data.materials.append(mat)
bpy.ops.object.light_add(type="AREA", location=(2, -4, 3))
bpy.context.object.data.energy = 600
bpy.ops.object.camera_add(location=(0, -17, 0.35), rotation=(1.5708, 0, 0))
sc.camera = bpy.context.object
sc.world = sc.world or bpy.data.worlds.new("W")
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print(f"CHECK blender {bpy.app.version_string} engine {sc.render.engine} samples {n} -> {out}")
