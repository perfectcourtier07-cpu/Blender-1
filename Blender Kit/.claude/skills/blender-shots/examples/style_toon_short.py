"""Style example 1: a 10-second vertical cartoon Short, "paper-doll people in a painted 3D world" (the look of the big
cartoon-trivia Shorts channels), built only from Blender and style_blocks. Our own story and true facts:
"Old railroads left a tiny gap every thirty-nine feet. Why? Steel grows in the heat. Skip the gap, and one hot
afternoon bends the whole line."

What makes the style, and which block does it:
  - a rigged 3D cartoon worker with a shape-key face that reacts on the words      sb.ToonCharacter, POSES
  - rich set dressing: thousands of stones, sleepers, rails, carved strata cliffs  sb.scatter_stones, canyon_wall, strata_mat
  - bright sky with painted clouds, distance haze, painterly brush filter          sb.sky_world, sb.finish(haze, paint)
  - one hard cut per caption phrase, low wide camera angles                         sb.Cuts, sb.bake_shots (times from words.json)
  - captions one or two words at a time, voice and SFX                              assemble_video.py (style_toon_short.assemble.json)

Render (vertical, 300 frames = 10 s):
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/style_toon_short.py --out shots/toon-demo/toon-demo.mp4 --frames 300 --size 1080x1920 --stills 37,88,121,150,217,240,277
Optional: --arg vo=<path to the voice WAV> makes the mouth move with the voice on the "Why?" shot.
To make your own: copy this file to shots/<name>/<name>.py, change CUTS from your words.json, the SHOTS table, the
set dressing and the story beats in the bake loop.
"""
import math
import random

import bpy
import blender_kit as kit
import style_blocks as sb
from mathutils import Vector

a = kit.args()
END, FPS = a.frames, a.fps
F = kit.f
random.seed(11)
kit.setup(view="Standard", bloom=0.0, motion_blur=0, world="#7FA8E0")

# ---------------------------------------------------------------- timing: one shot per caption phrase (from words.json)
CUTS = sb.Cuts([0.0, 2.13, 3.60, 4.33, 6.08, 7.53, 8.40])
#              saw   walk  why   heat  drone  sun   kink
SUN_POS = (-40.0, 322.0, 170.0)

# ---------------------------------------------------------------- the world: sky, sand, canyon, track
sb.sky_world()
M_STRATA, M_SAND, M_WOOD, M_RAIL = sb.strata_mat(), sb.sand_mat(), sb.wood_mat(), sb.rail_mat()
M_IRON = kit.matte("#26262A", 0.5, "Iron")
Y0, Y1 = -60.0, 430.0
sb.mesh_obj("Ground", [(-900, -400, 0), (900, -400, 0), (900, 1400, 0), (-900, 1400, 0)], [(0, 1, 2, 3)], M_SAND)
BED = [(-2.8, -0.01), (-1.8, 0.24), (1.8, 0.24), (2.8, -0.01)]
bv, bf = [], []
for j, y in enumerate(range(int(Y0), int(Y1) + 1, 2)):
    bv += [(x, y, z) for x, z in BED]
    if j:
        bf += [((j - 1) * 4 + k, (j - 1) * 4 + k + 1, j * 4 + k + 1, j * 4 + k) for k in range(3)]
sb.mesh_obj("BallastBed", bv, bf, sb.ballast_bed_mat())
sb.canyon_wall(-1, 8.0, 36.0, M_STRATA)
sb.canyon_wall(1, 11.0, 42.0, M_STRATA)
for i in range(9):                                                                 # distant mesas
    x, y, wd, ht = random.uniform(-260, 260), random.uniform(560, 900), random.uniform(40, 120), random.uniform(18, 45)
    sb.mesh_obj("Mesa", sb.box_verts(x, y, ht / 2, wd, wd * 0.6, ht), sb.BOX_F, M_STRATA)
for i in range(70):                                                                # fallen boulders at the cliff feet
    side = -1 if i % 2 else 1
    by = random.choice((random.uniform(-10, 40), random.uniform(215, 265), random.uniform(160, 330)))
    r = random.uniform(0.35, 1.6)
    bo = sb.prim("ico_sphere", (side * random.uniform(5.2, 8.5 if side < 0 else 10.5), by, r * 0.35), scale=(r, r * random.uniform(0.8, 1.3), r * 0.7),
                 rot=(0, 0, random.uniform(0, 360)), mat=M_STRATA, name="Boulder", radius=1.0, subdivisions=2)
    dm = bo.modifiers.new("Rough", "DISPLACE")
    dm.texture, dm.strength = bpy.data.textures.new(sb.nm("BoulderTex"), "VORONOI"), 0.35
STONES = sb.rock_mat()
PROFILE = [(-2.6, 0.03), (-1.75, 0.24), (1.75, 0.24), (2.6, 0.03)]
sb.scatter_stones("StonesNear", PROFILE, -8.0, 34.0, 380.0, STONES)              # dense where the camera is close
sb.scatter_stones("StonesKink", PROFILE, 221.0, 262.0, 380.0, STONES)
sb.scatter_stones("StonesMid", PROFILE, 34.0, 120.0, 120.0, STONES)
sb.scatter_stones("StonesFar", PROFILE, 170.0, 221.0, 120.0, STONES)

# sleepers: one mesh, except the stretch that kinks (separate objects so they can follow the rails)
KINK = (231.0, 258.0)
sv, sf, kink_sleepers = [], [], []
for i in range(int((Y1 - Y0) / 0.62)):
    y = Y0 + 0.62 * i
    jit, yaw = random.uniform(-0.04, 0.04), math.radians(random.uniform(-1.5, 1.5))
    if KINK[0] - 1 < y < KINK[1] + 1:
        ob = sb.mesh_obj("Sleeper", sb.box_verts(0, 0, 0, 2.6, 0.24, 0.15), sb.BOX_F, M_WOOD)
        ob.location, ob.rotation_euler = (jit, y, 0.285), (0, 0, yaw)
        kink_sleepers.append((ob, y, jit, yaw))
        continue
    base = len(sv)
    sv += sb.box_verts(jit, y, 0.285, 2.6, 0.24, 0.15, yaw)
    sf += [tuple(base + q for q in face) for face in sb.BOX_F]
sb.mesh_obj("Sleepers", sv, sf, M_WOOD)

# rails: real profile; 39-ft lengths with an (exaggerated) expansion gap up to y=170, one continuous length after
RAIL_PROF = [(-0.075, 0.0), (0.075, 0.0), (0.075, 0.018), (0.016, 0.03), (0.016, 0.12), (0.036, 0.13), (0.036, 0.17),
             (-0.036, 0.17), (-0.036, 0.13), (-0.016, 0.12), (-0.016, 0.03), (-0.075, 0.018)]
RAIL_L, GAP, RAIL_Z, GAUGE = 11.89, 0.10, 0.36, 0.72


def rail_mesh(length, step, mat):
    n, rings = len(RAIL_PROF), max(1, int(length / step))
    v, f = [], []
    for j in range(rings + 1):
        v += [(x, length * j / rings, z) for x, z in RAIL_PROF]
        if j:
            f += [((j - 1) * n + i, (j - 1) * n + (i + 1) % n, j * n + (i + 1) % n, j * n + i) for i in range(n)]
    f += [tuple(reversed(range(n))), tuple(rings * n + i for i in range(n))]
    return sb.mesh_obj("Rail", v, f, mat)


hot_rails = []
y = -5 * RAIL_L
while y + RAIL_L <= 170.0:
    for side in (-1, 1):
        hot = 11.0 < y < 12.5                                                      # the length that glows in the heat shot
        ob = rail_mesh(RAIL_L - GAP, 4.0, sb.rail_mat("HotRail", glow=True) if hot else M_RAIL)
        ob.location = (side * GAUGE, y, RAIL_Z)
        if hot:
            hot_rails.append(ob)
        for s2 in (-1, 1):                                                         # fishplates at the joint
            sb.mesh_obj("Fish", sb.box_verts(side * GAUGE + s2 * 0.032, y + RAIL_L - GAP / 2, RAIL_Z + 0.075, 0.018, 0.6, 0.08), sb.BOX_F, M_IRON)
    y += RAIL_L
cont_rails = []
for side in (-1, 1):
    ob = rail_mesh(Y1 - y, 0.4, M_RAIL)
    ob.location = (side * GAUGE, y, RAIL_Z)
    cont_rails.append(ob)


def kink_dx(yy, amount):
    """the sun kink: an S-shaped sideways shift between KINK[0] and KINK[1]; returns (offset, slope)"""
    u = (yy - KINK[0]) / (KINK[1] - KINK[0])
    if u <= 0 or u >= 1:
        return 0.0, 0.0
    d = math.sin(2 * math.pi * u) * math.sin(math.pi * u)
    du = 2 * math.pi * math.cos(2 * math.pi * u) * math.sin(math.pi * u) + math.pi * math.sin(2 * math.pi * u) * math.cos(math.pi * u)
    return amount * d, amount * du / (KINK[1] - KINK[0])


for ob in cont_rails:                                                              # shape key "Kink" on the continuous rails
    ob.shape_key_add(name="Basis")
    sk = ob.shape_key_add(name="Kink")
    for i, vv in enumerate(ob.data.vertices):
        sk.data[i].co = (vv.co.x + kink_dx(ob.location.y + vv.co.y, 1.15)[0], vv.co.y, vv.co.z)

# telegraph poles, cacti
for py in range(-40, 430, 34):
    sb.prim("cylinder", (-4.6, py, 3.6), mat=M_WOOD, name="Pole", radius=0.09, depth=7.2, vertices=10)
    sb.prim("cube", (-4.6, py, 6.8), scale=(0.9, 0.08, 0.08), mat=M_WOOD, name="Arm", smooth_shade=False, size=1.0)
M_CACTUS = sb.toon_mat("#4F8A3C", "Cactus", shade="#7F8FA8")
for cx, cy in ((-3.6, 6.0), (3.4, 15.0), (-3.9, 27.0), (3.8, 226.0), (-3.4, 240.0), (3.6, 30.0), (-5.5, 12.5)):
    s = random.uniform(0.7, 1.1)
    for p in (sb.prim("cylinder", (cx, cy, 0.9 * s), mat=M_CACTUS, name="Cac", radius=0.16 * s, depth=1.8 * s, vertices=12),
              sb.prim("cylinder", (cx + 0.32 * s, cy, 1.05 * s), mat=M_CACTUS, name="CacArm", radius=0.1 * s, depth=0.7 * s, vertices=10),
              sb.prim("cylinder", (cx + 0.18 * s, cy, 0.78 * s), rot=(0, 90, 0), mat=M_CACTUS, name="CacJoin", radius=0.09 * s, depth=0.36 * s, vertices=10)):
        sb.outline(p, 0.02)

# a locomotive far down the line with its headlight on and smoke rising
M_LOCO, M_RED, M_GOLD = kit.matte("#1E3B2E", 0.45, "LocoGreen"), kit.matte("#8E1F1A", 0.5, "LocoRed"), kit.metal("#D9A441", 0.3, "Brass")
loco = kit.empty((0, 150, 0), "Loco")
parts = [sb.prim("cylinder", (0, -0.5, 2.25), rot=(90, 0, 0), mat=M_LOCO, name="Boiler", radius=0.95, depth=6.0, vertices=32),
         sb.prim("cylinder", (0, -3.6, 2.25), rot=(90, 0, 0), mat=M_IRON, name="Smokebox", radius=1.0, depth=0.5, vertices=32),
         sb.prim("cylinder", (0, -2.7, 3.7), mat=M_IRON, name="Stack", radius=0.32, depth=1.6, vertices=16),
         sb.prim("cone", (0, -2.7, 4.75), mat=M_IRON, name="StackTop", radius1=0.34, radius2=0.62, depth=0.6, vertices=16),
         sb.prim("cylinder", (0, 0.6, 3.35), mat=M_GOLD, name="Dome", radius=0.38, depth=0.6, vertices=16),
         sb.prim("cube", (0, 3.1, 2.6), scale=(2.5, 2.2, 2.6), mat=M_RED, name="Cab", smooth_shade=False, size=1.0),
         sb.prim("cube", (0, 3.1, 4.05), scale=(2.8, 2.6, 0.18), mat=M_IRON, name="CabRoof", smooth_shade=False, size=1.0),
         sb.prim("cube", (0, 0, 0.95), scale=(2.3, 9.0, 0.5), mat=M_IRON, name="Frame", smooth_shade=False, size=1.0),
         sb.prim("cube", (0, -4.6, 0.55), scale=(2.4, 1.0, 0.9), rot=(-35, 0, 0), mat=M_RED, name="Cowcatcher", smooth_shade=False, size=1.0),
         sb.prim("cylinder", (0, -4.02, 3.2), rot=(90, 0, 0), mat=sb.emit_mat("#FFE6A0", 14.0, "LampGlass"), name="Lamp", radius=0.2, depth=0.05, vertices=20)]
parts += [sb.prim("cylinder", (sx, wy, 0.85), rot=(0, 90, 0), mat=M_RED, name="Wheel", radius=0.78, depth=0.16, vertices=24)
          for wy in (-1.6, 0.2, 2.0) for sx in (-1.05, 1.05)]
for p in parts:
    kit.parent(p, loco)
hl = kit.light("POINT", (0, 0, 0), (0, 0, 0), power=3000, color="#FFD58A", size=0.3, name="Headlight")
kit.parent(hl, loco)
hl.location = (0, -4.4, 3.2)
kit.key(loco, "location", [(1, (0, 150, 0)), (F(3.6), (0, 128, 0))], ease="linear")
M_SMOKE = sb.toon_mat("#3A3634", "Smoke", shade="#2A2A30")
for i in range(22):                                                                # puffs: rise from the stack, drift, grow
    pf = sb.prim("ico_sphere", (0, 150, 5), mat=M_SMOKE, name="Puff", radius=1.0, subdivisions=2)
    d = pf.modifiers.new("Lumpy", "DISPLACE")
    d.texture, d.strength = bpy.data.textures.new(sb.nm("PuffTex"), "CLOUDS"), 0.35
    kl, ks = [], []
    for fr in range(1, F(3.7), 6):
        t = (fr - 1) / FPS
        u = (i / 22 + t / 2.2) % 1.0
        kl.append((fr, (math.sin(i * 1.7) * 0.6 * u, 150 - 22 * min(1, t / 3.6) - 2.7 + 9.0 * u, 5.0 + 9.0 * u + 1.5 * u * u), "linear"))
        ks.append((fr, (0.35 + 1.9 * u,) * 3, "linear"))
    kit.key(pf, "location", kl, ease="linear")
    kit.key(pf, "scale", ks, ease="linear")

# a big sun disc for the two heat shots
sun_disc = sb.prim("uv_sphere", SUN_POS, mat=sb.emit_mat("#FFD27A", 30.0, "SunDisc"), name="SunDisc", radius=17.0, segments=32, ring_count=16)

# ---------------------------------------------------------------- the worker: rig + shape-key face, with a saw
bob = sb.ToonCharacter("Worker", body="#3D6BB3", hat="cap", hat_color="#B5442C")
saw = kit.empty((-0.25, 0, 0.57), "Saw")
for p in (sb.prim("cube", (-0.25, -0.03, 0.33), scale=(0.008, 0.11, 0.42), mat=kit.metal("#C9CED6", 0.3, "Blade"), name="Blade", smooth_shade=False, size=1.0),
          sb.outline(sb.prim("cube", (-0.25, -0.01, 0.58), scale=(0.04, 0.13, 0.12), mat=M_WOOD, name="SawHandle", smooth_shade=False, size=1.0), 0.01)):
    p.parent = saw
    p.matrix_parent_inverse = saw.matrix_world.inverted()
bob.hold(saw, "R")
ENV = sb.vo_envelope(a.get("vo", "")) if a.get("vo", "") else {}

# ---------------------------------------------------------------- camera, light, shots
cam = kit.camera((0, -10, 1), look_at=(0, 0, 1), lens=20)
cam.data.clip_end = 2500
aim = kit.aim(cam)
dof = kit.depth_of_field(cam, focus=5.0, fstop=2.2)
#        camera from / to,                       aim from / to,                                 lens, focus (m)
SHOTS = [dict(cam=((-0.2, -0.75, 1.0), (-0.22, -0.45, 0.96)), aim=((-2.1, 8.0, 0.55), (-2.1, 8.0, 0.5)), lens=18, focus=2.3),
         dict(cam=((-0.9, 8.55, 0.62), (-0.9, 8.85, 0.64)), aim=((-1.6, 16.0, 1.25), (-1.6, 16.0, 1.2)), lens=28, focus=4.0),
         dict(cam=((-1.5, 9.85, 1.66), (-1.52, 10.05, 1.68)), aim=((-1.85, 12.1, 1.72), (-1.85, 12.1, 1.74)), lens=30, focus=2.2),
         dict(cam=((-0.33, 21.9, 0.78), (-0.34, 22.2, 0.8)), aim=((-0.8, 30.0, 0.75), (-0.8, 30.0, 0.85)), lens=19, focus=1.75),
         dict(cam=((2.6, 168.0, 23.0), (1.6, 182.0, 18.5)), aim=((0.0, 268.0, 0.0), (0.0, 280.0, 0.0)), lens=26, focus=80.0),
         dict(cam=((0.5, 204.0, 0.9), (0.5, 204.6, 1.0)), aim=((-14.0, 238.0, 48.0), (-13.0, 238.0, 52.0)), lens=17, focus=30.0),
         dict(cam=((0.2, 226.6, 1.25), (0.15, 226.95, 1.28)), aim=((-2.46, 237.5, 1.1), (-2.46, 237.5, 1.0)), lens=21, focus=3.5)]
for s in SHOTS:
    s["fstop"] = 2.2
sb.bake_shots(cam, aim, dof, CUTS, SHOTS, ease_mix=1.0)
sun = kit.light("SUN", (0, 0, 10), (0, 0, 0), power=2.2, color="#FFF1DC", name="Sun")
sun.data.angle = math.radians(1.2)
if hasattr(sun.data, "use_shadow_jitter"):
    sun.data.use_shadow_jitter = False
to = lambda src, dst: tuple(d - s for s, d in zip(src, dst))                      # direction the light travels
sb.sun_per_shot(sun, CUTS, [to((10, -45, 75), (0, 0, 0)), to((10, -35, 85), (0, 0, 0)), to((10, -30, 80), (0, 0, 0)),
                            to(SUN_POS, (-0.6, 24.0, 0.5)), to((-40, 150, 60), (0, 0, 0)), to(SUN_POS, (0.5, 204.0, 1.0)),
                            to((10, 185, 75), (0, 0, 0))], powers=[2.2, 2.2, 2.2, 1.8, 2.2, 1.8, 2.2])

# ---------------------------------------------------------------- the story, frame by frame
BLINKS = [0.95, 2.95, 7.0, 9.6]
for fr in range(1, END + 1):
    t = CUTS.t(fr)
    si, u = CUTS.shot(t), CUTS.u(t)
    face, hat_pop = {}, 0.0
    if si == 0:                                     # "Old railroads left a tiny gap": crouched, sawing the rail, smug
        pose, dz = sb.pose_work(t)
        loc, yaw = (-1.35, 1.3, 0.22), 50.0
        face = {"squint": 0.35, "angry": 0.45, "grin": 0.25 * sb.smooth((t - 1.2) / 0.3)}
    elif si == 1:                                   # "every thirty-nine feet": walks toward us past a joint
        pose, dz = sb.pose_walk(t)
        loc, yaw = (-1.85, 13.6 - 1.0 * (t - CUTS.starts[1]), 0.22), 4.0
        face = {"grin": 0.15}
    elif si == 2:                                   # "Why?": shrug, brows up, mouth follows the voice
        pose, dz = sb.pose_shrug(t, u)
        loc, yaw = (-1.85, 12.1, 0.22), 9.0
        face = {"up": sb.smooth(u * 3), "wide": 0.4 * sb.smooth(u * 3), "O": ENV.get(fr, 0.6 * sb.smooth(u * 4))}
    elif si in (3, 4, 5):                           # heat, drone and sun shots: he is off screen
        pose, dz = sb.pose_stand(t)
        loc, yaw = (-9.0, 0.0, -20.0), 0.0
    else:                                           # "bends the whole line": the track kinks, he jumps, hat flies
        tk = t - 8.47
        k = sb.ease_back(tk / 0.22) if tk > 0 else 0.0
        pose, dz = sb.pose_shock(t, max(0.0, min(1.2, k)))
        loc, yaw = (-1.7, 229.8, 0.22), 32.0
        dz += 0.16 * math.sin(math.pi * min(1, max(0, tk / 0.35))) if tk > 0 else 0.0
        pose["head"] = (pose["head"][0], 0.0 if tk > 0.05 else 34.0, pose["head"][2])   # looking at the track, then at us
        face = {"wide": min(1, k), "up": min(1, k), "shock": min(1, k), "worried": 0.4 * (1 - min(1, k))}
        hat_pop = 0.32 * math.sin(math.pi * min(1, max(0, tk / 0.45))) if tk > 0 else 0.0
    for bt in BLINKS:
        if abs(t - bt) < 0.08 and face.get("shock", 0) < 0.1:
            face["blink"] = 1.0 - abs(t - bt) / 0.08
    bob.set(fr, (loc[0], loc[1], loc[2] + dz), yaw, pose, face, hat_pop)
    saw.scale = (1, 1, 1) if si == 0 else (0.001,) * 3
    saw.keyframe_insert("scale", frame=fr)
    sun_disc.scale = (1, 1, 1) if si in (3, 5) else (0.001,) * 3
    sun_disc.keyframe_insert("scale", frame=fr)

# "Steel grows in the heat": the rail glows, then lengthens to close its gap on "grows"
for ob in hot_rails:
    em = ob.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    kit.key(em, "default_value", [(1, 0.0), (F(4.33), 0.0), (F(5.0), 2.2), (F(6.0), 3.5)], ease="in_out")
    kit.key(ob, "scale", [(1, (1, 1, 1)), (F(4.87), (1, 1, 1)), (F(5.25), (1, RAIL_L / (RAIL_L - GAP), 1))], ease="out")
# "bends": rails by shape key, the sleepers in that stretch follow
k0, k1 = F(8.45), F(8.9)
for ob in cont_rails:
    kit.key(ob.data.shape_keys.key_blocks["Kink"], "value", [(1, 0.0), (k0, 0.0), (k1, 1.0)], ease="back")
for fr in range(k0 - 1, k1 + 8):
    v = sb.ease_back((fr - k0) / (k1 - k0)) if fr >= k0 else 0.0
    for ob, yy, jit, yaw in kink_sleepers:
        dx, slope = kink_dx(yy, 1.15 * v)
        ob.location, ob.rotation_euler = (jit + dx, yy, 0.285), (0, 0, yaw + math.atan(slope))
        ob.keyframe_insert("location", frame=fr)
        ob.keyframe_insert("rotation_euler", frame=fr)

sb.finish(bloom=0.45, vignette=0.18, grain=0.015, haze=0.62, paint=6)
