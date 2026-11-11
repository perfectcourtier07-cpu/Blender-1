"""Example: real photos fanned in depth on a dark table, a date card landing on the beat, the camera drifting.

Use it for "On March 28, 2026..." over the actual photos of that day (2 or 3 is best; 4 still reads).
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/photo_stack_date.py --out shots/photos/photos.mp4 --frames 150 \
      --arg photo=C:/Users/you/Pictures/one.jpg --arg photo=C:/Users/you/Pictures/two.jpg \
      --arg date="MARCH 28, 2026" --arg where="Old Faithful, Yellowstone" --arg beat=1.8
photo: repeat for each image (front first). date: the card text. where: optional smaller line. beat: second the card lands.

Run it from the Blender Kit folder (the one with CLAUDE.md), in the background.
"""
import blender_kit as kit

a = kit.args()
photos = a.all("photo")
if not photos:
    raise SystemExit("pass at least one --arg photo=PATH")
date, where = a.get("date", "MARCH 28, 2026"), a.get("where", "")
beat = kit.f(a.get("beat", 1.8, float))
end = a.frames

kit.setup(world="#0A0908", look="Medium High Contrast")
kit.backdrop("#0C0B09", center="#2B261F", distance=4.5, lit=True)      # close behind: the prints throw shadows on it

# Photos: the first is the hero, in front. Each is turned a little; the back one lands first, the hero last.
n = len(photos)
layout = [(1.0, 0.0, -2, 4, -0.2), (-2.3, 1.5, 4, -7, 0.5), (3.3, 2.9, -5, 8, 1.0), (-4.0, 3.9, 3, -5, 1.4)]   # front to back
planes = []
for i, path in enumerate(photos[:4]):
    x, y, tilt, yaw, z = layout[i] if n > 1 else (0, 0.5, -2, 4, 0)
    p = kit.image_plane(path, width=5.2 if n > 1 else 7.5, loc=(x, y, z), rot=(90, tilt, yaw), border=0.08, strength=1.1)
    t0 = 1 + (min(n, 4) - 1 - i) * 7
    kit.key(p, "location", [(t0, (x, y - 0.6, z + 1.6)), (t0 + 18, (x, y, z))], ease="expo")
    kit.key(p, "rotation_euler", [(t0, kit.rot(90, tilt * 2.2, yaw * 1.6)), (t0 + 22, kit.rot(90, tilt, yaw))], ease="out")
    kit.fade(p, [(t0, 0.0), (t0 + 6, 1.0)])
    planes.append(p)

# The date card: a dark plate with a warm accent bar, landing with a small overshoot exactly on the beat.
card = kit.empty((-0.2, -3.0, -1.75), "DateCard")
pw, ph = (6.0, 1.7) if where else (5.4, 1.25)
plate = kit.rect(pw, ph, material=kit.matte("#101215", 0.6, "Plate"), loc=(0, 0.02, 0), name="Plate")
bar = kit.rect(0.09, ph, "#E0A040", loc=(-pw / 2, 0, 0), name="Bar")
dt = kit.text(date, font="Montserrat-Bold", size=0.62, spacing=1.08, color="#F4F1EA", strength=1.5, align="LEFT",
              loc=(-pw / 2 + 0.3, -0.01, 0.18 if where else 0.0), name="Date")
parts = [plate, bar, dt]
if where:
    wh = kit.text(where, font="Gelasio-Variable", size=0.38, color="#E0A040", strength=1.3, align="LEFT",
                  loc=(-pw / 2 + 0.32, -0.01, -0.45), name="Where")
    parts.append(wh)
for part in parts:
    kit.parent(part, card)
    kit.fade(part, [(beat - 4, 0.0), (beat, 1.0)])
kit.key(card, "scale", [(beat - 4, (1.18,) * 3), (beat + 6, (1.0,) * 3, "out"), (end, (1.03,) * 3)], ease="back")
kit.key(card, "location", [(beat - 4, (-0.2, -3.4, -1.55)), (beat + 6, (-0.2, -3.0, -1.75))], ease="expo")

# Light: one warm key from the top left (long soft shadows on the table) and a faint cool rim.
kit.light("AREA", (-6, -7, 7), (0, 1, 0), power=1500, color="#FFE1BC", size=5, name="Key")
kit.rim((0, 1, 0), "#9FB8FF", power=500, distance=8, side=1)

# Camera: slow lateral drift with a gentle push; focus pulls from the prints to the card as it lands.
cam = kit.camera((-1.2, -15.0, 1.5), look_at=(0, 1.0, -0.4), lens=40)
kit.key(cam, "location", [(1, (-1.2, -15.0, 1.5)), (end, (0.8, -13.4, 0.8))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (-0.2, 1.0, -0.3)), (end, (0.3, 1.0, -0.6))], ease="in_out")
kit.shake(cam, strength=0.012, speed=45)
dof = kit.depth_of_field(cam, focus=15.0, fstop=3.2)
kit.key(dof, "focus_distance", [(1, 15.2), (beat - 2, 14.8), (beat + 8, 12.0), (end, 10.9)], ease="in_out")

kit.post(bloom=0.25, vignette=0.45, grain=0.04)
