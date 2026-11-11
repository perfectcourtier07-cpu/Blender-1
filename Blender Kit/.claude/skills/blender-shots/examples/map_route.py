"""Example: a history-style map. A dark stylised map (grid, a lighter landmass), four glowing city dots, an accent route line
that draws itself from city to city on the beats, each city's label fading in as the line arrives; the camera looks down at an
angle and drifts. 180 frames at 30 fps.
  python .claude/skills/blender-shots/scripts/render_blender.py .claude/skills/blender-shots/examples/map_route.py --out shots/map_route/map_route.mp4 --frames 180 --stills 1,90,180
"""
import math

import bpy
import blender_kit as kit

a = kit.args()
end = a.frames
ACCENT, INK, LAND, GRID = "#E0A040", "#F2EEE6", "#2A3648", "#34425A"

kit.setup(world="#05070A", motion_blur=0.25)

# The map: a flat matte plate lying on the floor (XY plane), a lighter landmass polygon on it, and a faint grid of thin lines.
plate = kit.rect(40, 24, material=kit.matte("#0E131B", 0.7, "Sea"), loc=(0, 0, 0), rot=(0, 0, 0), name="Sea")
land_pts = [(-16, -3), (-12, 2), (-9, 6), (-4, 8), (2, 9), (7, 7), (12, 8), (16, 5), (15, 0), (11, -4), (6, -6), (1, -8), (-4, -7),
            (-9, -8), (-14, -6)]
me = bpy.data.meshes.new("Land")
me.from_pydata([(x, y, 0.02) for x, y in land_pts], [], [list(range(len(land_pts)))])
land = bpy.data.objects.new("Land", me)
bpy.context.scene.collection.objects.link(land)
kit.assign(land, kit.matte(LAND, 0.8, "Land"))
for i in range(-20, 21, 2):
    kit.rect(0.03, 24, material=kit.emission(GRID, 1.2, "GridV"), loc=(i, 0, 0.03), rot=(0, 0, 0), name=f"gv{i}")
for j in range(-12, 13, 2):
    kit.rect(40, 0.03, material=kit.emission(GRID, 1.2, "GridH"), loc=(0, j, 0.03), rot=(0, 0, 0), name=f"gh{j}")

# Cities along the route, west to east, each with the beat (seconds) when the line reaches it.
cities = [("LISBON", (-13, -2), 0.6), ("PARIS", (-6, 3), 1.9), ("BERLIN", (2, 5), 3.2), ("WARSAW", (9, 4), 4.5)]
for name, (x, y), t in cities:
    f0 = kit.f(t)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(x, y, 0.15), segments=24, ring_count=12)
    dot = bpy.context.object
    dot.name = "dot_" + name
    kit.assign(dot, kit.emission(ACCENT, 6.0, "Dot" + name))
    kit.key(dot, "scale", [(max(1, f0 - 6), (0.001,) * 3), (f0, (1.6,) * 3, "back"), (f0 + 8, (1.0,) * 3)], ease="out")
    lab = kit.text(name, font="Montserrat-Bold", size=0.85, spacing=1.15, color=INK, strength=1.6, align="LEFT",
                   loc=(x + 0.5, y - 1.3, 0.1), rot=(0, 0, 0), name="lab_" + name)
    kit.fade(lab, [(f0, 0.0), (f0 + 10, 1.0)])

# The route: a smooth curve through the cities with a round bevel, drawn by animating its end factor on the beats.
cu = bpy.data.curves.new("Route", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.09
cu.bevel_resolution = 4
cu.use_fill_caps = True
sp = cu.splines.new("NURBS")
pts = [(-13, -2), (-9.5, 1.2), (-6, 3), (-2, 4.8), (2, 5), (5.5, 5.2), (9, 4)]
sp.points.add(len(pts) - 1)
for p, (x, y) in zip(sp.points, pts):
    p.co = (x, y, 0.12, 1.0)
sp.use_endpoint_u = True
sp.order_u = 3
route = bpy.data.objects.new("Route", cu)
bpy.context.scene.collection.objects.link(route)
kit.assign(route, kit.emission(ACCENT, 3.5, "RouteGlow"))
cu.bevel_factor_start = 0.0
# the drawn length reaches each city on its beat (fractions of the curve are approximate: the NURBS is nearly uniform here)
for frac, (_, _, t) in zip((0.0, 0.34, 0.68, 1.0), cities):
    cu.bevel_factor_end = frac
    cu.keyframe_insert("bevel_factor_end", frame=kit.f(t))

# A period line in the corner of the map (part of the chart, not a caption).
year = kit.text("1807  ·  THE MARCH EAST", font="Montserrat-Bold", size=0.8, spacing=1.2, color=ACCENT, strength=1.5, align="LEFT",
                loc=(-15, 10.2, 0.1), rot=(0, 0, 0), name="Year")
kit.fade(year, [(1, 0.0), (14, 1.0)])

# Light and air: a soft warm key from above, a cool fill, a few motes low over the map for depth.
kit.light("AREA", (-6, -10, 16), (0, 0, 0), power=6000, color="#FFE2BF", size=14, name="Key")
kit.light("AREA", (12, 8, 14), (0, 0, 0), power=2500, color="#9FB8FF", size=16, name="Fill")
kit.motes(count=40, center=(0, 0, 2.0), spread=(30, 18, 2.5), size=0.03, strength=1.5)

# Camera: high and tilted, drifting east with the route and pushing in slightly.
cam = kit.camera((-7, -26, 24), look_at=(-4, -1, 0), lens=35)
kit.key(cam, "location", [(1, (-7, -26, 24)), (end, (3, -23, 21))], ease="in_out")
kit.key(kit.aim(cam), "location", [(1, (-5, -1, 0)), (end, (1, 1, 0))], ease="in_out")
kit.depth_of_field(cam, focus=route, fstop=4.0)

kit.post(bloom=0.45, vignette=0.4, grain=0.03)
