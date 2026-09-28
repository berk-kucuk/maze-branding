"""Maze Linux — wallpaper set v2 ("studio"). OLED-black, cinematic, the mark
kept small or abstracted.

    blender -b --factory-startup -P studio.py -- <scene> <out-dir> [--preview]

Scenes: silk, eclipse, macro, fields, fluted, fluted-violet, ribbon, halo.
Reuses the geometry/light helpers from scenes.py.
"""
import bpy, bmesh, math, os, random, sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenes as S
from scenes import mat, camera, haze, floor, bevel, mark_object, maze_object, spot, area_light

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SCENE = argv[0] if argv else "silk"
OUT = argv[1] if len(argv) > 1 else "."
PREVIEW = "--preview" in argv


def mesh_from_grid(name, nu, nv, fn):
    """Quad mesh over (u,v) in [0,1]^2, vertex position fn(u,v) -> (x,y,z)."""
    verts = [fn(i / (nu - 1), j / (nv - 1)) for j in range(nv) for i in range(nu)]
    faces = [(j * nu + i, j * nu + i + 1, (j + 1) * nu + i + 1, (j + 1) * nu + i)
             for j in range(nv - 1) for i in range(nu - 1)]
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o

def emission(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1); e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m

def gradient_emission(name, c0, c1, strength, axis="X", lo=-2, hi=2):
    """Emission that blends c0 -> c1 along an object-space axis."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = lo; mr.inputs["From Max"].default_value = hi
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c0, 1); ramp.color_ramp.elements[1].color = (*c1, 1)
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Strength"].default_value = strength
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs[axis], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


# ---------------------------------------------------------------- scenes
def s_silk(sc):
    """Black satin folds; two grazing strip lights draw silver along the crests.
    A small debossed mark sits in the lower right fold."""
    def f(u, v):
        x = (u - 0.5) * 36; y = (v - 0.5) * 22
        warp = 1.6 * math.sin(y * 0.23 + 0.7) + 0.9 * math.sin(x * 0.11 + y * 0.07)
        t = x * 0.55 + y * 0.9 + warp * 2.2
        env = 0.55 + 0.45 * math.sin(x * 0.09 - y * 0.05 + 1.3)
        z = env * (0.55 * math.sin(t * 0.95) + 0.18 * math.sin(t * 2.1 + 0.4)) + 0.06 * math.sin(x * 0.8 + y * 0.3)
        return (x, y, z)
    n = 180 if PREVIEW else 420
    o = mesh_from_grid("silk", int(n * 1.64), n, f)
    sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = sub.render_levels = 1
    m = mat("satin", (0.006, 0.006, 0.007), rough=0.22, coat=0.6)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Sheen Weight"].default_value = 0.6
    b.inputs["Sheen Tint"].default_value = (0.7, 0.75, 0.85, 1)
    o.data.materials.append(m)
    spot("graze", (-26, 10, 2.5), (0, 0, 0), 30, 6500, (0.82, 0.87, 1.0), size_y=0.6)
    spot("fill", (22, -14, 3), (0, 0, 0), 20, 220, (0.95, 0.9, 0.86), size_y=0.4)
    camera((2, -15, 7), (0.5, 1.0, 0), lens=45, focus=(0.8, -2, 0), fstop=2.8)

def s_eclipse(sc):
    """The mark in silhouette; a hidden light behind it spills through the
    haze and out of every gap. Small, below centre, lots of black."""
    m = mark_object(size=2.4, depth=0.35)
    m.rotation_euler = (math.radians(90), 0, 0); m.location = (0, 0, 1.25)
    bevel(m, 0.012, 3)
    m.data.materials.append(mat("black", (0.004, 0.004, 0.005), rough=0.3, coat=0.0))
    back = area_light("back", (0, 1.2, 1.25), (-90, 0, 0), 0.6, 220, (0.80, 0.86, 1.0), shape="DISK")
    back.rotation_euler = (math.radians(-90), 0, 0)  # points toward -Y, the camera
    b2 = area_light("halo", (0, 3.5, 1.25), (-90, 0, 0), 3.0, 60, (0.72, 0.80, 1.0), shape="DISK")
    if "--nohaze" not in argv: haze(0.02, 16, 0.9, (0, 6.5, 1.25), scale=(1, 0.5, 0.6))
    camera((0, -34, 1.25), (0, 0, 1.25), lens=85, focus=(0, 0, 1.25), fstop=2.0)

def s_macro(sc):
    """Extreme close-up of a brushed-titanium mark's corner; f/1.4 so only one
    edge is sharp. Reads as abstract architecture."""
    m = mark_object(size=4.0, depth=0.5)
    bevel(m, 0.018, 5)
    m.data.materials.append(mat("titanium", (0.30, 0.31, 0.33), rough=0.22, metal=1.0, aniso=0.6))
    floor(mat("base", (0.003, 0.003, 0.003), rough=0.4), z=0.0)
    spot("strip", (-3, 6, 3.5), (-1.4, 1.4, 0.3), 12, 130, (0.85, 0.9, 1.0), size_y=0.08)
    spot("strip2", (4, -2, 5), (-1.4, 1.4, 0.3), 10, 60, (1.0, 0.92, 0.85), size_y=0.05)
    camera((-0.1, -0.9, 1.25), (-1.35, 1.35, 0.3), lens=100, focus=(-1.2, 1.1, 0.5), fstop=1.4)

def s_fields(sc):
    """Ground-level across an endless black maze; a distant light strip on the
    horizon runs along the polished wall tops. Shallow focus."""
    mz = maze_object(70, 70, 11, wall=0.14, corridor=0.7, height=0.42)
    bevel(mz, 0.012, 2)
    mz.data.materials.append(mat("wall", (0.004, 0.004, 0.005), rough=0.12, coat=1.0))
    floor(mat("ground", (0.002, 0.002, 0.002), rough=0.5))
    spot("horizon", (0, 55, 2.2), (0, 0, 0), 90, 5000, (0.78, 0.84, 1.0), size_y=1.6)
    haze(0.0005, 120, 0.8, (0, 30, 8), scale=(1, 1, 0.15))
    camera((1.3, -24, 1.15), (0.5, 20, 0.2), lens=40, focus=(1.0, -14, 0.3), fstop=1.6)

def _fluted(sc, c0, c1):
    """Fluted glass in front of a glowing mark: the mark dissolves into soft
    vertical light. Recognisable only as a shape."""
    rods = []
    r = 0.045
    for i in range(-185, 186):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=14, location=(i * 2 * r, 0, 0))
        rods.append(bpy.context.active_object)
    bpy.ops.object.select_all(action="DESELECT")
    for o in rods: o.select_set(True)
    bpy.context.view_layer.objects.active = rods[0]
    bpy.ops.object.join()
    g = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    g.data.materials.append(mat("glass", (1, 1, 1), rough=0.03, transmission=1.0, ior=1.5))
    mk = mark_object(size=4.5, depth=0.05)
    mk.rotation_euler = (math.radians(90), 0, 0); mk.location = (2.0, 5.0, -0.1)
    mk.data.materials.append(gradient_emission("glow", c0, c1, 3, "X", -1.5, 1.5))
    for loc, rad, col, st in (((-3.5, 6, 1.8), 1.6, c0, 0.5), ((4.5, 7, -2.2), 2.2, c1, 0.35)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=rad, location=loc)
        bpy.context.active_object.data.materials.append(emission("blob", col, st))
    camera((0, -9, 0), (0, 0, 0), lens=50, focus=(0, 0, 0), fstop=1.2)

def s_fluted(sc):
    _fluted(sc, (0.80, 0.86, 1.0), (1.0, 1.0, 1.0))

def s_fluted_violet(sc):
    _fluted(sc, (0.25, 0.18, 1.0), (0.05, 0.75, 0.95))

def s_ribbon(sc):
    """Three wide satin ribbons sweeping through black, edge-lit."""
    def ribbon(name, seed, width, y0, twist, amp):
        rnd = random.Random(seed)
        ph = [rnd.uniform(0, 6.28) for _ in range(4)]
        def f(u, v):
            t = (u - 0.5) * 30
            cy = y0 + amp * math.sin(t * 0.18 + ph[0]) + 0.6 * math.sin(t * 0.41 + ph[1])
            cz = 0.9 * math.sin(t * 0.23 + ph[2])
            a = twist * math.sin(t * 0.12 + ph[3]) + 0.35
            s = (v - 0.5) * width
            return (t, cy + s * math.cos(a), cz + s * math.sin(a))
        o = mesh_from_grid(name, 900, 40, f)
        s = o.modifiers.new("solid", "SOLIDIFY"); s.thickness = 0.02
        m = mat(name, (0.008, 0.008, 0.009), rough=0.2, coat=0.8)
        m.node_tree.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 0.8
        o.data.materials.append(m)
        return o
    ribbon("r1", 3, 2.4, 0.6, 1.3, 1.6)
    ribbon("r2", 8, 1.6, -1.0, 1.7, 1.2)
    ribbon("r3", 21, 0.9, -2.4, 2.1, 0.9)
    spot("top", (-10, 8, 12), (2, 0, 0), 18, 3000, (0.80, 0.86, 1.0), size_y=0.5)
    spot("under", (10, -8, -6), (0, 0, 0), 12, 1500, (0.55, 0.48, 1.0), size_y=0.4)
    camera((0, -3, 14), (0, -0.4, 0), lens=38, focus=(0, 0, 0), fstop=5.0)

def s_halo(sc):
    """A small obsidian mark under a vast thin ring of light; the ring reflects
    in the floor and on the mark's bevels."""
    m = mark_object(size=1.1, depth=0.18)
    m.rotation_euler = (math.radians(90), 0, math.radians(-12)); m.location = (0, 0, 0.56)
    bevel(m, 0.008, 3)
    m.data.materials.append(mat("obsidian", (0.006, 0.006, 0.007), rough=0.12, coat=1.0))
    floor(mat("mirror", (0.002, 0.002, 0.0025), rough=0.1, coat=1.0))
    bpy.ops.mesh.primitive_torus_add(major_radius=2.3, minor_radius=0.01, major_segments=400,
                                     minor_segments=12, location=(0, 2.5, 2.35), rotation=(math.radians(90), 0, 0))
    ring = bpy.context.active_object
    ring.data.materials.append(emission("ring", (0.85, 0.9, 1.0), 40))
    spot("key", (-3, -5, 3), (0, 0, 0.56), 1.5, 45, (0.9, 0.93, 1.0))
    haze(0.003, 30, 0.6, (0, 2, 5))
    camera((0, -22, 1.0), (0, 0, 2.1), lens=55, focus=(0, 0, 0.56), fstop=2.2)


def s_bokeh(sc):
    """A small chrome mark in sharp focus; far behind it a maze of tiny lights
    melts into soft bokeh."""
    m = mark_object(size=0.55, depth=0.08)
    m.rotation_euler = (math.radians(90), 0, math.radians(18)); m.location = (-1.0, 0, 0.15)
    bevel(m, 0.01, 4)
    m.data.materials.append(mat("titanium", (0.35, 0.36, 0.38), rough=0.25, metal=1.0, aniso=0.4))
    rnd = random.Random(4)
    g = S.maze_grid(24, 14, 5)
    pts = [(c, r) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] and rnd.random() < 0.22]
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.06)
    base = bpy.context.active_object
    warm = emission("warm", (0.85, 0.9, 1.0), 9); cool = emission("cool", (0.45, 0.5, 1.0), 12)
    base.data.materials.append(warm)
    for i, (c, r) in enumerate(pts):
        o = base.copy(); o.data = base.data.copy() if i % 5 == 0 else base.data
        if i % 5 == 0: o.data.materials[0] = cool
        o.location = ((c - 24) * 0.55 + 3, 22 + rnd.uniform(-2, 2), (14 - r) * 0.55)
        k = rnd.uniform(0.35, 1.3); o.scale = (k, k, k)
        sc.collection.objects.link(o)
    bpy.data.objects.remove(base)
    spot("rim", (-5, 3, 4), (-1.0, 0, 0.15), 4, 500, (0.85, 0.9, 1.0), size_y=0.2)
    spot("rim2", (2, 2, -2), (-1.0, 0, 0.15), 4, 160, (0.5, 0.55, 1.0), size_y=0.2)
    camera((-0.6, -6.5, 0.4), (-0.3, 0, 0.3), lens=85, focus=(-1.0, 0, 0.15), fstop=1.0)


SCENES = {"bokeh": s_bokeh, "silk": s_silk, "eclipse": s_eclipse, "macro": s_macro, "fields": s_fields,
          "fluted": s_fluted, "fluted-violet": s_fluted_violet, "ribbon": s_ribbon, "halo": s_halo}

if __name__ == "__main__":
    sc = S.reset()
    if not PREVIEW:
        sc.cycles.samples = 512
    SCENES[SCENE](sc)
    os.makedirs(OUT, exist_ok=True)
    sc.render.filepath = os.path.join(OUT, f"raw-{SCENE}{'-preview' if PREVIEW else ''}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
