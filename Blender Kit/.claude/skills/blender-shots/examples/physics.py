"""Example: satisfying physics. A 55-cube pyramid on a dark floor, a heavy metal sphere rolls in at ~1 s and knocks it over.

  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/physics.py --out shots/physics/physics.mp4 --frames 180 --stills 1,60,120,180
The rigid-body simulation is baked inside this script (frames 1-180) so stills at any frame and clips agree. No text.
"""
import math
import random
import time
import bpy
import bmesh
import blender_kit as kit

a = kit.args()
end = a.frames
ACCENT = "#E0A040"
S = 0.6                       # cube edge (m)
LAYERS = 5                    # 25 + 16 + 9 + 4 + 1 = 55 cubes
R = 0.7                       # sphere radius
SPEED = 0.30                  # sphere travel per frame while driven (m/frame = 9 m/s)
HIT = 30                      # frame the sphere is released (it reaches the pyramid right after)

kit.setup(world="#1C2430", bloom=0.3)
kit.post(bloom=0.3, vignette=0.4, grain=0.03)
kit.backdrop("#07090D", center="#1A212C", distance=14)

# ------------------------------------------------------------------ floor (passive box so collision is solid)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.25))
fl = bpy.context.active_object
fl.name = "Floor"
fl.scale = (60, 60, 0.5)
kit.assign(fl, kit.matte("#1A1F28", 0.75, "Floor"))

# ------------------------------------------------------------------ cubes (shared mesh, shared materials)
me = bpy.data.meshes.new("CubeMesh")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=S)
bm.to_mesh(me)
bm.free()
palette = [kit.matte(c, 0.7, f"Cube{i}") for i, c in enumerate(("#56626C", "#8B7C6B", "#3F5B57"))]
accent_mat = kit.matte(ACCENT, 0.55, "CubeAccent")

rnd = random.Random(5)
cubes = []
for k in range(LAYERS):
    n = LAYERS - k
    z = S / 2 + k * (S + 0.002)
    for i in range(n):
        for j in range(n):
            x = (i - (n - 1) / 2) * (S + 0.002)
            y = (j - (n - 1) / 2) * (S + 0.002)
            ob = bpy.data.objects.new(f"Cube.{len(cubes):03d}", me)
            bpy.context.scene.collection.objects.link(ob)
            ob.location = (x, y, z)
            cubes.append(ob)
accents = set(rnd.sample(range(len(cubes)), 6))
me.materials.append(palette[0])
for idx, ob in enumerate(cubes):                       # per-object material link (shared mesh)
    ob.material_slots[0].link = "OBJECT"
    ob.material_slots[0].material = accent_mat if idx in accents else palette[rnd.randrange(3)]
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width, bev.segments = 0.018, 2

# ------------------------------------------------------------------ sphere
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=R, location=(0, 0, 0))
ball = bpy.context.active_object
ball.name = "Ball"
bpy.ops.object.shade_smooth()
kit.assign(ball, kit.metal("#B4BAC4", 0.42, "Steel"))
reach = (LAYERS * (S + 0.002)) / 2 + R                 # sphere centre x when it first touches the base layer
x_hit = -reach - 0.15
x0 = x_hit - SPEED * (HIT - 1)
ball.location = (x0, 0, R)
ball.rotation_euler = (0, 0, 0)
kit.key(ball, "location", [(1, (x0, 0, R)), (HIT, (x_hit, 0, R))], ease="linear")
kit.key(ball, "rotation_euler", [(1, (0, 0, 0)), (HIT, (0, (x_hit - x0) / R, 0))], ease="linear")

# ------------------------------------------------------------------ rigid body world
sc = bpy.context.scene
if sc.rigidbody_world is None:
    bpy.ops.rigidbody.world_add()
rbw = sc.rigidbody_world
rbw.substeps_per_frame = 10
rbw.solver_iterations = 25
rbw.point_cache.frame_start, rbw.point_cache.frame_end = 1, end


def add_rb(objs, kind):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.rigidbody.objects_add(type=kind)


add_rb([fl], "PASSIVE")
add_rb(cubes, "ACTIVE")
add_rb([ball], "ACTIVE")
fl.rigid_body.collision_shape = "BOX"
fl.rigid_body.friction = 0.7
for o in cubes:
    rb = o.rigid_body
    rb.collision_shape, rb.mass, rb.friction, rb.restitution = "BOX", 2.0, 0.7, 0.05
    rb.use_margin, rb.collision_margin = True, 0.001
    rb.linear_damping, rb.angular_damping = 0.08, 0.15
rb = ball.rigid_body
rb.collision_shape, rb.mass, rb.friction, rb.restitution = "SPHERE", 120.0, 0.4, 0.05
rb.use_margin, rb.collision_margin = True, 0.001
rb.linear_damping, rb.angular_damping = 0.0, 0.02
rb.kinematic = True                                       # driven by the location keys until HIT, then dynamic
ball.keyframe_insert("rigid_body.kinematic", frame=1)
rb.kinematic = False
ball.keyframe_insert("rigid_body.kinematic", frame=HIT)
for fc in kit._fcurves(ball):
    if fc.data_path == "rigid_body.kinematic":
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
        fc.update()

# ------------------------------------------------------------------ light and camera
kit.three_point(target=(0, 0, 1.2), power=2.2, distance=9)
kit.light("AREA", (0, -4, 8), (0, 0, 0.5), power=650, color="#FFFFFF", size=2.5, name="Top")   # a smaller light: crisper shadows, less grain at 1 sample
cam = kit.camera((0.8, -12.5, 1.0), (0.8, 0, 1.2), lens=42)
kit.key(cam, "location", [(1, (0.8, -12.5, 1.0)), (end, (0.6, -10.6, 1.2))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (0.8, 0, 1.2)), (end, (1.2, 0, 0.9))], ease="in_out")
dof = kit.depth_of_field(cam, 12.5, 2.0)
kit.key(dof, "focus_distance", [(1, 12.5), (end, 10.7)], ease="in_out")
kit.shake(cam, 0.008, 45.0)

# ------------------------------------------------------------------ bake (inside the script, so every render sees the same sim)
t0 = time.time()
sc.frame_set(1)
try:
    with bpy.context.temp_override(scene=sc, point_cache=rbw.point_cache):
        bpy.ops.ptcache.bake_all(bake=True)
except Exception as e:
    print("KIT note: bake with override failed:", e)
    bpy.ops.ptcache.bake_all(bake=True)
print(f"KIT bake seconds {time.time() - t0:.1f}  baked={rbw.point_cache.is_baked}")
sc.frame_set(1)
