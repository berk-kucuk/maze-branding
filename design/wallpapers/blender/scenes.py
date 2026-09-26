"""Maze Linux — Blender scenes for wallpapers, and the 3D logo export.

    blender -b --factory-startup -P scenes.py -- <scene> <out-dir> [--preview]
    blender -b --factory-startup -P scenes.py -- export-logo <out-dir>

Scenes: monolith, labyrinth, glass, corridor, relief.
--preview renders at half size with few samples, for quick iteration.

Everything is built from code: the Maze mark from mark.json (the logo's own
bar grid, measured from maze-simple-logo.png), mazes from a seeded
recursive-backtracker, so each render is reproducible. The world emits
nothing, so wherever no light falls the image is true black (OLED).
"""
import bpy, bmesh, json, math, os, random, sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SCENE = argv[0] if argv else "monolith"
OUT = argv[1] if len(argv) > 1 else HERE
PREVIEW = "--preview" in argv
W, H = 2560, 1440


# ---------------------------------------------------------------- setup
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    sc.cycles.device = "GPU"
    sc.cycles.samples = 64 if PREVIEW else 768
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02 if PREVIEW else 0.004
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 12
    sc.cycles.transmission_bounces = 12
    sc.cycles.volume_bounces = 2
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 50 if PREVIEW else 100
    sc.render.dither_intensity = 0.0          # grain is added later, never on black
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "16"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - High Contrast"
    except TypeError:
        pass
    world = bpy.data.worlds.new("black")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    sc.world = world
    return sc

def mat(name, base=(0.02, 0.02, 0.022), rough=0.3, metal=0.0, coat=0.0,
        emit=None, emit_strength=0.0, transmission=0.0, ior=1.45, aniso=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Transmission Weight"].default_value = transmission
    b.inputs["IOR"].default_value = ior
    b.inputs["Anisotropic"].default_value = aniso
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m

def area_light(name, loc, rot, size, energy, color=(1, 1, 1), shape="RECTANGLE", size_y=None):
    d = bpy.data.lights.new(name, "AREA")
    d.energy = energy; d.color = color; d.shape = shape
    d.size = size
    if size_y is not None: d.size_y = size_y
    o = bpy.data.objects.new(name, d)
    o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]
    o.visible_camera = False          # light, not a glowing bar in the frame
    bpy.context.scene.collection.objects.link(o)
    return o

def camera(loc, look_at, lens=50, focus=None, fstop=2.8):
    c = bpy.data.cameras.new("cam"); c.lens = lens
    o = bpy.data.objects.new("cam", c)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    d = Vector(look_at) - Vector(loc)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if focus is not None:
        c.dof.use_dof = True
        c.dof.focus_distance = (Vector(focus) - Vector(loc)).length
        c.dof.aperture_fstop = fstop
    bpy.context.scene.camera = o
    return o

def haze(density=0.01, size=60, anisotropy=0.5, center=(0, 0, 0), scale=None):
    bpy.ops.mesh.primitive_cube_add(size=size, location=center)
    o = bpy.context.active_object; o.name = "haze"
    if scale: o.scale = scale
    m = bpy.data.materials.new("haze"); m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = density
    v.inputs["Anisotropy"].default_value = anisotropy
    v.inputs["Color"].default_value = (1, 1, 1, 1)
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    o.data.materials.append(m)
    return o

def floor(material, size=200, z=0.0):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    o = bpy.context.active_object; o.name = "floor"
    o.data.materials.append(material)
    return o


# ---------------------------------------------------------------- geometry
def grid_mesh(name, grid, xs, ys, height, z0=0.0):
    """Extruded mesh of the filled cells of `grid` (rows top->bottom).
    xs/ys are the cell edge coordinates. Coplanar cells are merged into
    clean n-gons so a bevel modifier gives even highlights."""
    rows, cols = len(grid), len(grid[0])
    bm = bmesh.new()
    verts = {}
    def v(i, j):
        k = (i, j)
        if k not in verts:
            verts[k] = bm.verts.new((xs[i], ys[j], z0))
        return verts[k]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c]:
                bm.faces.new((v(c, r + 1), v(c + 1, r + 1), v(c + 1, r), v(c, r)))
    bmesh.ops.dissolve_limit(bm, angle_limit=0.001, verts=bm.verts[:], edges=bm.edges[:])
    ext = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, height), verts=top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    for p in me.polygons: p.use_smooth = False
    return o

def bevel(o, width, segments=3):
    b = o.modifiers.new("bevel", "BEVEL")
    b.width = width; b.segments = segments; b.limit_method = "ANGLE"
    b.harden_normals = True
    try: o.data.use_auto_smooth = True
    except AttributeError: pass
    return b

def mark_object(size=4.0, depth=0.3, name="maze-mark"):
    """The Maze mark, `size` wide, centred on the origin, lying in XY, +Z up."""
    d = json.load(open(os.path.join(HERE, "mark.json")))
    e = d["edges"]; span = e[-1] - e[0]
    xs = [(x - e[0]) / span * size - size / 2 for x in e]
    ys = [size / 2 - (x - e[0]) / span * size for x in e]   # row 0 at the top
    return grid_mesh(name, d["grid"], xs, ys, depth)

def maze_grid(cols, rows, seed, hole=None):
    rnd = random.Random(seed)
    h = [[True] * cols for _ in range(rows + 1)]
    v = [[True] * (cols + 1) for _ in range(rows)]
    inhole = lambda c, r: bool(hole) and hole[0] <= c < hole[2] and hole[1] <= r < hole[3]
    seen = [[False] * cols for _ in range(rows)]
    stack = [(0, 0)]; seen[0][0] = True
    while stack:
        c, r = stack[-1]
        nb = [(c+dc, r+dr) for dc, dr in ((1,0),(-1,0),(0,1),(0,-1))
              if 0 <= c+dc < cols and 0 <= r+dr < rows and not seen[r+dr][c+dc] and not inhole(c+dc, r+dr)]
        if not nb: stack.pop(); continue
        nc, nr = rnd.choice(nb)
        if nc != c: v[r][max(c, nc)] = False
        else: h[max(r, nr)][c] = False
        seen[nr][nc] = True; stack.append((nc, nr))
    gc, gr = 2 * cols + 1, 2 * rows + 1
    g = [[False] * gc for _ in range(gr)]
    for r in range(0, gr, 2):
        for c in range(0, gc, 2): g[r][c] = True
    for r in range(rows + 1):
        for c in range(cols):
            if h[r][c]: g[2*r][2*c+1] = True
    for r in range(rows):
        for c in range(cols + 1):
            if v[r][c]: g[2*r+1][2*c] = True
    if hole:  # empty the hole, keep its outline, open one door on each side
        c0, r0, c1, r1 = hole
        for r in range(2*r0 + 1, 2*r1):
            for c in range(2*c0 + 1, 2*c1): g[r][c] = False
        mr, mc = r0 + r1, c0 + c1
        g[mr][2*c0] = g[mr][2*c1] = g[2*r0][mc] = g[2*r1][mc] = False
    return g

def maze_object(cols, rows, seed, wall, corridor, height, hole=None, name="maze"):
    g = maze_grid(cols, rows, seed, hole)
    def edges(n):
        out, x = [0.0], 0.0
        for i in range(n):
            x += wall if i % 2 == 0 else corridor
            out.append(x)
        return out
    xs = edges(len(g[0])); ys = edges(len(g))
    cx, cy = xs[-1] / 2, ys[-1] / 2
    xs = [x - cx for x in xs]; ys = [cy - y for y in ys]
    return grid_mesh(name, g, xs, ys, height)


# ---------------------------------------------------------------- scenes
def aim(o, target):
    d = Vector(target) - o.location
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o

def spot(name, loc, target, size, energy, color=(1, 1, 1), size_y=None):
    o = area_light(name, loc, (0, 0, 0), size, energy, color, size_y=size_y)
    return aim(o, target)

def s_monolith(sc):
    """A polished-obsidian Maze mark standing on a black mirror, rim-lit."""
    m = mark_object(size=4.0, depth=0.42)
    m.rotation_euler = (math.radians(90), 0, math.radians(-20))
    m.location = (0.0, 0, 2.02)
    bevel(m, 0.02, 4)
    m.data.materials.append(mat("obsidian", (0.010, 0.010, 0.012), rough=0.16, coat=1.0))
    floor(mat("mirror", (0.003, 0.003, 0.004), rough=0.08, coat=0.6))
    # a light bar behind and above: it draws the bevels as thin silver lines
    spot("rim", (0.6, 4.5, 5.2), (0, 0, 2.0), 8.0, 1400, (0.86, 0.90, 1.0), size_y=0.3)
    spot("side", (6.5, 1.0, 2.2), (0, 0, 2.0), 3.0, 260, (0.82, 0.88, 1.0), size_y=0.2)
    spot("key", (-6.0, -5.0, 6.0), (0, 0, 2.0), 4.0, 70)
    haze(0.0008, 40, 0.7)
    camera((-5.5, -13.5, 1.9), (0.6, 0, 2.1), lens=50, focus=(0, 0, 2.0), fstop=2.4)

def s_labyrinth(sc):
    """Looking across a dark maze; the mark at its heart is the only light."""
    hc = 5
    mz = maze_object(29, 29, 7, wall=0.36, corridor=1.0, height=1.1, hole=(12, 12, 12 + hc, 12 + hc))
    bevel(mz, 0.03, 2)
    mz.data.materials.append(mat("stone", (0.05, 0.05, 0.055), rough=0.45))
    floor(mat("floor", (0.02, 0.02, 0.022), rough=0.3, coat=0.4), z=0.0)
    mk = mark_object(size=2.6, depth=0.06)
    mk.location = (0, 0, 0.01)
    mk.data.materials.append(mat("glow", (0.9, 0.93, 1.0), emit=(0.85, 0.9, 1.0), emit_strength=9))
    pt = bpy.data.lights.new("core", "POINT"); pt.energy = 900; pt.color = (0.85, 0.9, 1.0); pt.shadow_soft_size = 1.5
    po = bpy.data.objects.new("core", pt); po.location = (0, 0, 0.8); sc.collection.objects.link(po)
    spot("moon", (-18, 26, 14), (0, 0, 0), 10.0, 900, (0.70, 0.78, 1.0))
    haze(0.006, 70, 0.4, (0, 0, 10))
    camera((6.5, -21.0, 8.0), (0, 1.0, 0), lens=45, focus=(0, 0, 0.6), fstop=1.8)

def s_glass(sc):
    """The Maze mark in frosted glass, lit through from behind."""
    m = mark_object(size=4.0, depth=0.5)
    m.rotation_euler = (math.radians(90), 0, math.radians(-14))
    m.location = (0.0, 0, 2.02)
    bevel(m, 0.035, 4)
    m.data.materials.append(mat("glass", (0.95, 0.97, 1.0), rough=0.22, transmission=1.0, ior=1.47))
    floor(mat("mirror", (0.003, 0.003, 0.004), rough=0.1, coat=0.5))
    # soft panel of light right behind the glass: the mark glows from inside
    spot("back", (0.3, 2.6, 2.0), (0, 0, 2.0), 3.2, 700, (0.80, 0.87, 1.0), size_y=3.2)
    spot("top", (0, 1.0, 7.0), (0, 0, 2.0), 5.0, 200)
    # no haze here: the back light would turn it into a grey backdrop
    camera((-4.8, -15.0, 2.2), (0.3, 0, 2.05), lens=50, focus=(0, 0, 2.0), fstop=2.0)

def longest_corridor(g):
    """Longest straight horizontal run of open cells in the block grid."""
    best = (0, 0, 0, 0)
    for r in range(1, len(g), 2):
        run = 0
        for c in range(len(g[0])):
            run = run + 1 if not g[r][c] else 0
            if run > best[0]: best = (run, r, c - run + 1, c)
    return best

def s_corridor(sc):
    """Inside the maze at eye level: the wall tops are thin lines of light."""
    cols = rows = 41; wall, corr, height = 0.30, 1.3, 2.4
    g = maze_grid(cols, rows, 19)
    mz = maze_object(cols, rows, 19, wall=wall, corridor=corr, height=height)
    bevel(mz, 0.02, 2)
    mz.data.materials.append(mat("wall", (0.018, 0.018, 0.02), rough=0.5))
    mz.data.materials.append(mat("edge", emit=(0.80, 0.88, 1.0), emit_strength=3.5))
    for p in mz.data.polygons:
        if p.normal.z > 0.9: p.material_index = 1
    floor(mat("wet", (0.008, 0.008, 0.009), rough=0.08, coat=0.9))
    # block-grid coordinate -> world (same layout as maze_object)
    def edges(n):
        out, x = [0.0], 0.0
        for i in range(n):
            x += wall if i % 2 == 0 else corr
            out.append(x)
        return out
    xs, ys = edges(len(g[0])), edges(len(g))
    cx, cy = xs[-1] / 2, ys[-1] / 2
    run, r, c0, c1 = longest_corridor(g)
    y = cy - (ys[r] + ys[r + 1]) / 2
    x0 = (xs[c0] + xs[c0 + 1]) / 2 - cx
    x1 = (xs[c1] + xs[c1 + 1]) / 2 - cx
    haze(0.004, 100, 0.3, (0, 0, 4))
    # just above the wall tops, looking down the corridor: the lit tops run
    # away into the haze as lines of light
    camera((x0 - 2.0, y, height + 2.6), (x1 + 6, y, height - 1.2), lens=35,
           focus=(x0 + (x1 - x0) * 0.25, y, height), fstop=1.6)
    print("CORRIDOR", run, r, c0, c1)

def s_relief(sc):
    """A maze carved into dark brushed metal, raked by low light."""
    mz = maze_object(34, 20, 51, wall=0.25, corridor=0.62, height=0.07)
    bevel(mz, 0.012, 3)
    metal = mat("metal", (0.20, 0.205, 0.215), rough=0.32, metal=1.0, aniso=0.6)
    mz.data.materials.append(metal)
    floor(metal, size=60, z=0.0)
    spot("rake", (-14, 6, 1.0), (3, 0, 0), 10.0, 9000, (0.85, 0.9, 1.0), size_y=1.5)
    spot("top", (4, 12, 9), (0, 0, 0), 8.0, 250)
    camera((5.5, -10.5, 4.2), (0, 1.0, 0), lens=55, focus=(0.8, 0, 0), fstop=1.8)


def s_cube(sc):
    """A floating satin-metal cube, a maze raised on each visible face."""
    size, zc = 3.0, 2.4
    half = size / 2
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, zc))
    cube = bpy.context.active_object
    bevel(cube, 0.04, 4)
    satin = mat("satin", (0.045, 0.045, 0.05), rough=0.3, metal=0.7)
    cube.data.materials.append(satin)
    faces = (((0, 0, 0), (0, 0, zc + half)),
             ((90, 0, 0), (0, -half, zc)),
             ((0, 90, 0), (half, 0, zc)))
    for i, (rot, loc) in enumerate(faces):
        mz = maze_object(12, 12, 100 + i, wall=0.07, corridor=0.155, height=0.05, name=f"face{i}")
        mz.rotation_euler = [math.radians(a) for a in rot]
        mz.location = loc
        bevel(mz, 0.008, 2)
        mz.data.materials.append(mat(f"relief{i}", (0.07, 0.07, 0.075), rough=0.25, metal=0.8))
    floor(mat("mirror", (0.003, 0.003, 0.004), rough=0.15, coat=0.5))
    spot("rim", (-6, 7, 8), (0, 0, zc), 6.0, 1600, (0.82, 0.88, 1.0))
    spot("front", (-2.5, -9, 3.2), (0, -half, zc), 5.0, 420)
    spot("right", (9, 1.5, 3.0), (half, 0, zc), 4.0, 320, (0.85, 0.9, 1.0))
    camera((9.5, -12.0, 8.6), (0, 0, zc - 0.2), lens=60, focus=(half, -half, zc + half), fstop=2.8)

def s_chrome(sc):
    """A mirror-chrome Maze mark; studio strips only show in its reflections."""
    m = mark_object(size=4.0, depth=0.5)
    m.rotation_euler = (math.radians(90), 0, math.radians(-24))
    m.location = (0.0, 0, 2.05)
    bevel(m, 0.04, 5)
    m.data.materials.append(mat("chrome", (0.92, 0.93, 0.95), rough=0.05, metal=1.0))
    floor(mat("mirror", (0.003, 0.003, 0.004), rough=0.1, coat=0.6))
    strip = mat("strip", emit=(0.9, 0.93, 1.0), emit_strength=40)
    for loc, sc_ in (((-3.5, -16, 6.0), (10, 0.5, 1)), ((5.0, -15, 2.5), (0.5, 8, 1)),
                     ((0.0, -12, 9.5), (12, 0.6, 1)), ((-8.0, -6, 3.0), (0.5, 6, 1)),
                     ((7.0, -4, 6.0), (0.4, 7, 1))):
        bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
        pl = bpy.context.active_object; pl.scale = sc_
        aim(pl, (0, 0, 2.0)); pl.rotation_euler.rotate_axis("X", math.radians(180))
        pl.data.materials.append(strip)
        pl.visible_camera = False
    spot("top", (0, 0, 9), (0, 0, 2), 6.0, 120)
    camera((-4.6, -13.5, 2.4), (0.4, 0, 2.1), lens=55, focus=(0, 0, 2.0), fstop=2.4)

def s_glowpath(sc):
    """Tall black walls from above; the corridors between them glow."""
    cols, rows, wall, corr = 26, 16, 0.32, 0.95
    mz = maze_object(cols, rows, 64, wall=wall, corridor=corr, height=1.4)
    bevel(mz, 0.02, 2)
    mz.data.materials.append(mat("black", (0.012, 0.012, 0.013), rough=0.45))
    wx = cols * corr + (cols + 1) * wall; wy = rows * corr + (rows + 1) * wall
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.001))
    glow = bpy.context.active_object; glow.scale = (wx, wy, 1)
    glow.data.materials.append(mat("glowfloor", (0.9, 0.93, 1.0), emit=(0.80, 0.87, 1.0), emit_strength=0.45))
    haze(0.006, 60, 0.3, (0, 0, 3))
    camera((2.0, -15.5, 17.0), (0.3, 1.0, 0), lens=40, focus=(0.3, 1.0, 1.2), fstop=1.8)

def s_tunnel(sc):
    """A tunnel of Maze marks, each turned a little; light pours through."""
    n, gap = 10, 2.3
    obs = mat("obsidian", (0.012, 0.012, 0.014), rough=0.2, coat=1.0)
    for i in range(n):
        m = mark_object(size=4.0, depth=0.22, name=f"gate{i}")
        m.rotation_euler = (math.radians(90), math.radians(i * 7.5), 0)
        m.location = (0, i * gap, 0)
        bevel(m, 0.015, 3)
        m.data.materials.append(obs)
    far = (n - 1) * gap
    spot("source", (0, far + 3.5, 0), (0, 0, 0), 3.2, 9000, (0.82, 0.88, 1.0))
    spot("fill", (0, -8, 5), (0, far / 2, 0), 5.0, 30)
    haze(0.03, 1, 0.6, (0, far / 2 + 1.5, 0), scale=(4.4, far + 7, 4.4))
    camera((0.35, -10.5, 0.25), (0, far, 0), lens=52, focus=(0, 0, 0), fstop=2.2)


ANIM = {}   # scenes that animate set ANIM["frames"] (seamless loop length)

def s_tunnelfly(sc):
    """Endless flight down the tunnel of Maze marks, as a seamless loop.
    Gate i is gate 0 moved `gap` along Y and turned `twist` about Y, so moving
    the camera rig by exactly one gap and one twist over the loop lands on a
    frame identical to the first: the loop has no seam."""
    n, gap, twist = 34, 2.3, 7.5
    obs = mat("obsidian", (0.012, 0.012, 0.014), rough=0.2, coat=1.0)
    for i in range(-4, n):
        m = mark_object(size=4.0, depth=0.22, name=f"gate{i}")
        m.rotation_euler = (math.radians(90), math.radians(i * twist), 0)
        m.location = (0, i * gap, 0)
        bevel(m, 0.015, 3)
        m.data.materials.append(obs)
    rig = bpy.data.objects.new("rig", None); sc.collection.objects.link(rig)
    cam = camera((0.35, 0, 0.25), (0.35 - 0.35, 30, 0), lens=40, focus=(0, 10.5, 0), fstop=2.4)
    cam.parent = rig
    src = spot("source", (0, 26, 0), (0, 0, 0), 3.2, 9000, (0.82, 0.88, 1.0))
    src.parent = rig
    # thin haze: only the light's path glows, the edges of the frame stay black
    haze(0.011, 1, 0.6, (0, n * gap / 2, 0), scale=(4.4, n * gap + 20, 4.4))
    frames = 72 if not PREVIEW else 8
    sc.frame_start, sc.frame_end = 1, frames
    rig.location = (0, 0, 0); rig.rotation_euler = (0, 0, 0)
    rig.keyframe_insert("location", frame=1); rig.keyframe_insert("rotation_euler", frame=1)
    rig.location = (0, gap, 0); rig.rotation_euler = (0, math.radians(twist), 0)
    rig.keyframe_insert("location", frame=frames + 1); rig.keyframe_insert("rotation_euler", frame=frames + 1)
    for fc in rig.animation_data.action.fcurves if hasattr(rig.animation_data.action, "fcurves") else []:
        for k in fc.keyframe_points: k.interpolation = "LINEAR"
    try:   # Blender 5: layered actions
        for layer in rig.animation_data.action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        for k in fc.keyframe_points: k.interpolation = "LINEAR"
    except AttributeError:
        pass
    ANIM["frames"] = frames
    if os.environ.get("MAZE_SEAM_TEST"):        # also render frame N+1 (must equal frame 1)
        sc.frame_end = frames + 1
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.cycles.samples = 48 if PREVIEW else 128

SCENES = {"monolith": s_monolith, "labyrinth": s_labyrinth, "glass": s_glass,
          "corridor": s_corridor, "relief": s_relief,
          "cube": s_cube, "chrome": s_chrome, "glowpath": s_glowpath, "tunnel": s_tunnel,
          "tunnelfly": s_tunnelfly}


# ---------------------------------------------------------------- logo export
def export_logo(out):
    """The Maze mark as a reusable 3D model, 100 mm wide, 10 mm deep.
    Plain (sharp edges) and bevelled variants, in .blend/.glb/.obj/.stl."""
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"; sc.unit_settings.length_unit = "MILLIMETERS"
    sc.unit_settings.scale_length = 0.001            # 1 Blender unit = 1 mm
    plain = mark_object(size=100.0, depth=10.0, name="maze-mark")
    plain.data.materials.append(mat("maze-white", (0.9, 0.9, 0.92), rough=0.3))
    bev = mark_object(size=100.0, depth=10.0, name="maze-mark-bevel")
    bev.data.materials.append(plain.data.materials[0])
    bevel(bev, 0.6, 3)
    bev.location.x = 130
    bpy.context.view_layer.update()
    # apply the bevel so every exporter gets the same geometry
    bpy.context.view_layer.objects.active = bev; bev.select_set(True)
    bpy.ops.object.modifier_apply(modifier="bevel")
    bev.location.x = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "maze-mark.blend"))
    for o, stem in ((plain, "maze-mark"), (bev, "maze-mark-bevel")):
        for x in bpy.context.scene.objects: x.select_set(False)
        o.select_set(True); bpy.context.view_layer.objects.active = o
        base = os.path.join(out, stem)
        bpy.ops.export_scene.gltf(filepath=base + ".glb", use_selection=True, export_format="GLB")
        bpy.ops.wm.obj_export(filepath=base + ".obj", export_selected_objects=True, global_scale=1.0)
        bpy.ops.wm.stl_export(filepath=base + ".stl", export_selected_objects=True, global_scale=1.0)
    print("EXPORTED", sorted(os.listdir(out)))


if __name__ == "__main__":
    if SCENE == "export-logo":
        export_logo(OUT)
    else:
        sc = reset()
        SCENES[SCENE](sc)
        os.makedirs(OUT, exist_ok=True)
        if ANIM:
            sc.render.filepath = os.path.join(OUT, f"{SCENE}{'-preview' if PREVIEW else ''}", "f####")
            bpy.ops.render.render(animation=True)
            print("RENDERED ANIMATION", sc.render.filepath, ANIM["frames"])
        else:
            sc.render.filepath = os.path.join(OUT, f"raw-{SCENE}{'-preview' if PREVIEW else ''}.png")
            bpy.ops.render.render(write_still=True)
            print("RENDERED", sc.render.filepath)
