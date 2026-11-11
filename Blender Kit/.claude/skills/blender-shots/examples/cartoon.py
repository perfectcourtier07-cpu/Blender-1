"""Example: a flat 2D cartoon, the viral "stick-cartoon history" look, in Blender only. Cut-out characters (round heads, dot
eyes, thick outlines) on a flat sky-and-hills background, a talking soldier with a machine gun, an emu that bobs and struts,
big kinetic captions popping in word by word, a little camera push. 180 frames at 30 fps. No drawing, no images: every shape
is a flat disc, rectangle or triangle with exact colours (view="Standard"), outlines are the same shape in black behind it.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/cartoon.py --out shots/cartoon/cartoon.mp4 --frames 180 --stills 1,90,160
Change the captions and beats at the top; the characters are small functions you can re-pose or recolour.
"""
import math

import bpy
import blender_kit as kit

a = kit.args()
end = a.frames
CAPTIONS = [("AUSTRALIA", 0.5, "#FFFFFF"), ("SENT SOLDIERS", 1.5, "#FFFFFF"), ("WITH MACHINE GUNS", 2.6, "#FFFFFF"),
            ("TO FIGHT BIRDS.", 3.8, "#FFFFFF"), ("THE BIRDS WON.", 5.0, "#FF4D4D")]
TALK = (0.5, 4.6)                           # seconds the soldier's mouth flaps
INK = "#1B1B1B"
SKIN, KHAKI, CAP, BROWN = "#F3C9A0", "#8E8F5E", "#6C6E46", "#5B4636"
SKY, SKY_LOW, HILL, HILL2, GROUND, SUN, WHITE = "#9FD9F2", "#DDF2FA", "#86CC72", "#5FA84C", "#6DB357", "#FFD95A", "#FFFFFF"

kit.setup(view="Standard", bloom=0, motion_blur=0, world="#9FD9F2")
cam = kit.screen_camera()
kit.key(cam.data, "ortho_scale", [(1, 19.2), (end, 18.0)], ease="in_out")        # a slow push in (1 m = 100 px at 19.2)

# ---------------------------------------------------------------- flat shape helpers (everything stands in the XZ plane, facing the camera)
_n = [0]


def nm(s):
    _n[0] += 1
    return f"{s}{_n[0]}"


def disc(rx, rz, loc, color, name="Disc"):
    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=1.0, fill_type="NGON", location=loc)
    ob = bpy.context.object
    ob.name = nm(name)
    ob.rotation_euler = kit.rot(90, 0, 0)
    ob.scale = (rx, rz, 1)
    return kit.assign(ob, kit.emission(color, 1.0, ob.name))


def box(w, h, loc, color, name="Box", rot_z=0.0):
    ob = kit.rect(w, h, material=kit.emission(color, 1.0, nm(name)), loc=loc, name=nm(name))
    ob.rotation_euler = kit.rot(90, rot_z, 0)          # rot about the view axis = the kit's Y after standing up
    return ob


def tri(pts, loc, color, name="Tri"):
    me = bpy.data.meshes.new(nm(name))
    me.from_pydata([(x, 0, z) for x, z in pts], [], [(0, 1, 2)])
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return kit.assign(ob, kit.emission(color, 1.0, ob.name))


def outlined_disc(rx, rz, loc, color, line=0.06, name="ODisc"):
    """a black disc a hair bigger and a hair behind, then the coloured disc; returns [ink, fill] so BOTH get parented"""
    ink = disc(rx + line, rz + line, (loc[0], loc[1] + 0.01, loc[2]), INK, name + "Ink")
    return [ink, disc(rx, rz, loc, color, name)]


def outlined_box(w, h, loc, color, line=0.06, name="OBox", rot_z=0.0):
    ink = box(w + 2 * line, h + 2 * line, (loc[0], loc[1] + 0.01, loc[2]), INK, name + "Ink", rot_z)
    return [ink, box(w, h, loc, color, name, rot_z)]


def group(parts, root):
    for p in parts:
        kit.parent(p, root)


# ---------------------------------------------------------------- background: sky, sun, clouds, hills, ground (far = larger y)
box(19.2, 10.8, (0, 3.0, 0), SKY, "Sky")
box(19.2, 3.6, (0, 2.9, -2.2), SKY_LOW, "Horizon")
disc(1.1, 1.1, (6.8, 2.8, 3.4), "#FFE9A3", "SunGlow")
outlined_disc(0.8, 0.8, (6.8, 2.7, 3.4), SUN, name="Sun")
for cx, cz, s in ((-6.5, 3.4, 1.0), (-2.0, 4.0, 0.7), (3.2, 3.6, 0.85)):
    for dx, dz, r in ((0, 0, 0.55), (-0.6, -0.1, 0.42), (0.6, -0.1, 0.45), (0.1, -0.28, 0.4)):
        disc(r * s, r * s * 0.85, (cx + dx * s, 2.6, cz + dz * s), WHITE, "Cloud")
outlined_disc(7.5, 2.3, (-4.0, 2.4, -4.3), HILL2, name="HillBack")
outlined_disc(6.5, 1.9, (5.0, 2.3, -4.4), HILL, name="HillFront")
box(19.2, 2.6, (0, 2.2, -4.9), GROUND, "Ground")
box(19.2, 0.07, (0, 2.19, -3.62), INK, "GroundLine")

# ---------------------------------------------------------------- the soldier (left), built around a root empty at his feet
sol = kit.empty((-4.2, 0.0, -3.6), "Soldier")
parts = []
parts += [*outlined_box(0.26, 1.0, (-0.3, 0.3, 0.5), KHAKI, name="LegL"), *outlined_box(0.26, 1.0, (0.3, 0.3, 0.5), KHAKI, name="LegR")]
parts += [*outlined_box(0.5, 0.16, (-0.32, 0.25, 0.08), INK, name="BootL"), *outlined_box(0.5, 0.16, (0.32, 0.25, 0.08), INK, name="BootR")]
parts += [*outlined_box(1.0, 1.25, (0, 0.2, 1.55), KHAKI, name="Torso")]
parts += [box(0.08, 1.1, (0, 0.15, 1.5), "#5E5F3A", "Seam")]
armL = kit.empty((-0.55, 0.1, 2.05), "ArmL")                     # shoulder pivot, left arm hangs
parts_l = [*outlined_box(0.24, 0.85, (0, 0, -0.42), KHAKI, name="ArmL"), *outlined_disc(0.15, 0.15, (0, 0, -0.9), SKIN, name="HandL")]
group(parts_l, armL)
armR = kit.empty((0.55, 0.1, 2.05), "ArmR")                      # right arm holds the gun grip
parts_r = [*outlined_box(0.24, 0.8, (0, 0, -0.4), KHAKI, name="ArmR"), *outlined_disc(0.15, 0.15, (0, 0, -0.85), SKIN, name="HandR")]
group(parts_r, armR)
head = kit.empty((0, 0.1, 2.75), "Head")
hp = [*outlined_disc(0.56, 0.56, (0, 0, 0), SKIN, name="Face")]
hp += [*outlined_box(0.95, 0.34, (0, -0.02, 0.42), CAP, name="Cap"), *outlined_box(1.2, 0.1, (0.1, -0.03, 0.26), CAP, name="Brim")]
eyeL, eyeR = disc(0.07, 0.07, (-0.2, -0.05, 0.1), INK, "EyeL"), disc(0.07, 0.07, (0.2, -0.05, 0.1), INK, "EyeR")
hp += [eyeL, eyeR]
hp += [disc(0.3, 0.08, (0, -0.05, -0.12), BROWN, "Moustache")]
mouth = disc(0.13, 0.07, (0, -0.06, -0.3), INK, "Mouth")
hp += [mouth]
group(hp, head)
group(parts + [armL, armR, head], sol)
# the machine gun on a tripod, in front of him
gun = kit.empty((-2.6, -0.3, -3.6), "Gun")
gp = [*outlined_box(1.9, 0.16, (0.35, 0, 1.35), "#3A3A3A", name="Barrel"), *outlined_box(0.5, 0.42, (-0.5, 0, 1.3), "#3A3A3A", name="Body"),
      *outlined_box(0.12, 1.3, (-0.25, 0.05, 0.65), "#3A3A3A", name="Leg", rot_z=-18), *outlined_box(0.12, 1.3, (0.05, 0.05, 0.65), "#3A3A3A", name="Leg", rot_z=18),
      *outlined_disc(0.12, 0.12, (0.0, -0.02, 1.33), "#2A2A2A", name="Hub")]
group(gp, gun)

# ---------------------------------------------------------------- the emu (right): body, neck, head, beak, legs
emu = kit.empty((4.6, 0.0, -3.6), "Emu")
legs = [*outlined_box(0.16, 1.4, (-0.3, 0.2, 0.7), "#8A6A4A", name="ELegL"), *outlined_box(0.16, 1.4, (0.3, 0.2, 0.7), "#8A6A4A", name="ELegR")]
feet = [tri([(-0.35, 0), (0.35, 0), (0, 0.22)], (-0.3, 0.15, 0.0), INK, "FootL"), tri([(-0.35, 0), (0.35, 0), (0, 0.22)], (0.3, 0.15, 0.0), INK, "FootR")]
body = [*outlined_disc(1.2, 0.85, (0, 0.1, 1.9), BROWN, name="EBody"), disc(0.7, 0.4, (-0.1, 0.05, 1.75), "#6E5742", "EBelly")]
neck = kit.empty((-0.6, 0.05, 2.5), "Neck")
np_ = [*outlined_box(0.26, 1.7, (0, 0, 0.8), BROWN, name="ENeck")]
headE = kit.empty((0, 0, 1.75), "EHead")
ehp = [*outlined_disc(0.42, 0.3, (0, 0, 0), BROWN, name="EHead"), disc(0.1, 0.1, (-0.12, -0.03, 0.08), WHITE, "EEyeW"), disc(0.05, 0.05, (-0.13, -0.05, 0.08), INK, "EEye"),
       tri([(0, -0.1), (0, 0.1), (-0.55, 0.0)], (-0.4, -0.02, -0.02), "#D9A441", "Beak")]
group(ehp, headE)
group(np_ + [headE], neck)
group(legs + feet + body + [neck], emu)

# ---------------------------------------------------------------- captions: one at a time, popping in, a dark drop shadow behind
cap_root = kit.empty(kit.screen(960, 930), "Captions")
for i, (txt, t, col) in enumerate(CAPTIONS):
    f0 = kit.f(t)
    f1 = kit.f(CAPTIONS[i + 1][1]) if i + 1 < len(CAPTIONS) else end + 1
    grp = kit.empty((0, 0, 0), f"Cap{i}")
    sh = kit.text(txt, font="Montserrat-Bold", size=1.15, color=INK, strength=1.0, loc=(0.06, 0.02, -0.07), name=f"CapShadow{i}")
    tx = kit.text(txt, font="Montserrat-Bold", size=1.15, color=col, strength=1.0, loc=(0, 0, 0), name=f"CapText{i}")
    group([sh, tx], grp)
    kit.parent(grp, cap_root)
    kit.key(grp, "scale", [(f0 - 1, (0.001,) * 3), (f0, (0.001,) * 3), (f0 + 5, (1.18,) * 3), (f0 + 9, (1.0,) * 3), (f1 - 1, (1.0,) * 3), (f1, (0.001,) * 3)],
            ease="out")


# ---------------------------------------------------------------- motion: bobs, blinks, mouth flaps, the emu's strut and the ending beat
def bob(obj, z0, amp, period_s, phase=0.0):
    for f in range(1, end + 1, 3):
        t = (f - 1) / a.fps
        obj.location.z = z0 + amp * math.sin(2 * math.pi * t / period_s + phase)
        obj.keyframe_insert("location", index=2, frame=f)


bob(sol, -3.6, 0.04, 0.9)
bob(emu, -3.6, 0.06, 0.7, 1.0)
for f in range(1, end + 1, 3):                                    # emu legs alternate, neck pecks
    t = (f - 1) / a.fps
    s = math.sin(2 * math.pi * t / 0.7)
    for ob, sign in ((legs[0], 1), (legs[1], 1), (legs[2], -1), (legs[3], -1)):     # ink + fill of each leg swing together
        ob.rotation_euler = kit.rot(90, 10 * s * sign, 0)
        ob.keyframe_insert("rotation_euler", frame=f)
    neck.rotation_euler = kit.rot(0, 6 * math.sin(2 * math.pi * t / 1.4), 0)
    neck.keyframe_insert("rotation_euler", frame=f)
    armL.rotation_euler = kit.rot(0, 8 * math.sin(2 * math.pi * t / 0.9 + 1.5), 0)
    armL.keyframe_insert("rotation_euler", frame=f)
for f in range(kit.f(TALK[0]), kit.f(TALK[1]), 4):                # mouth flap while he talks
    for df, sz in ((0, 1.0), (2, 0.3)):
        mouth.scale = (0.13, 0.07 * sz, 1)
        mouth.keyframe_insert("scale", frame=f + df)
mouth.scale = (0.13, 0.07, 1)
mouth.keyframe_insert("scale", frame=kit.f(TALK[1]) + 2)
for eye in (eyeL, eyeR):                                        # blinks
    for t in (1.3, 3.1, 4.9):
        f = kit.f(t)
        for df, sz in ((-1, 1.0), (1, 0.08), (3, 1.0)):
            eye.scale = (0.07, 0.07 * sz, 1)
            eye.keyframe_insert("scale", frame=f + df)
# the ending beat: the emu hops twice, the gun barrel droops, the soldier's head tilts
fb = kit.f(CAPTIONS[-1][1])
for k, dz in enumerate((0, 0.5, 0, 0.5, 0)):
    emu.location.z = -3.6 + dz
    emu.keyframe_insert("location", index=2, frame=fb + 4 * k)
kit.key(gun, "rotation_euler", [(fb, kit.rot(0, 0, 0)), (fb + 12, kit.rot(0, 14, 0))], ease="bounce")
kit.key(head, "rotation_euler", [(fb, kit.rot(0, 0, 0)), (fb + 10, kit.rot(0, -9, 0))], ease="out")
