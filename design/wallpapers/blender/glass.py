"""Maze Linux — monochrome glassmorphism wallpapers (v3). Frosted glass over
white light forms on true black; the mark appears at icon scale only.

    blender -b --factory-startup -P glass.py -- <scene> <out-dir> [--preview]
"""
import bpy, math, os, sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenes as S
from scenes import camera, bevel, mark_object, spot

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SCENE = argv[0] if argv else "stack"
OUT = argv[1] if len(argv) > 1 else "."
PREVIEW = "--preview" in argv


# ---------------------------------------------------------------- materials
def frosted(name="frosted", rough=0.22, ior=1.45, tint=(1, 1, 1)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*tint, 1)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = rough
    b.inputs["IOR"].default_value = ior
    b.inputs["Coat Weight"].default_value = 1.0      # crisp specular skin on a frosted body
    b.inputs["Coat Roughness"].default_value = 0.02
    return m

def glow(name, strength, color=(1, 1, 1)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1); e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m

def glow_fade(name, strength, axis="X", lo=-1.0, hi=1.0, invert=False):
    """White emission that fades to zero along an object-space axis:
    gives light forms a soft, directional falloff instead of a flat tube."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = hi if invert else lo
    mr.inputs["From Max"].default_value = lo if invert else hi
    mr.inputs["To Min"].default_value = 0.0; mr.inputs["To Max"].default_value = strength
    mr.interpolation_type = "SMOOTHSTEP"
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs[axis], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], e.inputs["Strength"])
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m

def matte_black():
    m = bpy.data.materials.new("black"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0, 0, 0, 1); b.inputs["Roughness"].default_value = 1.0
    b.inputs["Specular IOR Level"].default_value = 0.0
    return m


# ---------------------------------------------------------------- geometry
def rounded_card(w, h, d, r, loc, rot=(0, 0, 0), name="card"):
    """Rounded-rectangle card built from a 2D outline, extruded along Y."""
    import bmesh
    seg = 20
    pts = []
    for cx, cz, a0 in ((w/2 - r, h/2 - r, 0), (-w/2 + r, h/2 - r, 90),
                       (-w/2 + r, -h/2 + r, 180), (w/2 - r, -h/2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    bm = bmesh.new()
    vs = [bm.verts.new((x, -d / 2, z)) for x, z in pts]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, d, 0), verts=top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]
    bv = o.modifiers.new("soft", "BEVEL"); bv.width = min(d * 0.35, 0.03); bv.segments = 5
    bv.limit_method = "ANGLE"; bv.angle_limit = math.radians(40); bv.harden_normals = True
    for p in me.polygons: p.use_smooth = True
    return o

def tube_curve(name, points, radius, closed=False):
    """Smooth light tube through `points` (bezier, auto handles)."""
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"
    cu.bevel_depth = radius; cu.bevel_resolution = 8; cu.resolution_u = 48
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = "AUTO"
    sp.use_cyclic_u = closed
    o = bpy.data.objects.new(name, cu); bpy.context.scene.collection.objects.link(o)
    return o

def ribbon_curve(name, points, width, thick=0.0):
    """Flat light ribbon (a curve extruded sideways)."""
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"
    cu.extrude = width; cu.bevel_depth = thick; cu.resolution_u = 64
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu); bpy.context.scene.collection.objects.link(o)
    return o

def engrave_mark(card, size, loc, depth=0.02, glow_strength=0.0):
    """A thin mark sitting on a card's front face: frosted relief, optionally lit."""
    mk = mark_object(size=size, depth=depth, name="mark")
    mk.rotation_euler = (math.radians(90), 0, 0)
    mk.location = loc
    mk.data.materials.append(glow("mark-glow", glow_strength) if glow_strength else frosted("mark", 0.08))
    return mk


# ---------------------------------------------------------------- scenes
def s_stack(sc):
    """Three frosted cards fanned in depth; a white light ribbon sweeps behind
    them, sharp where it's in the open and melted where it passes behind glass.
    The front card carries the mark at icon size."""
    # light behind
    rb = tube_curve("sweep", [(-14, 3.0, -4.6), (-5, 3.0, -2.0), (2.5, 3.0, 1.2), (8, 3.0, 2.8), (15, 3.0, 2.4)], 0.028)
    rb.data.materials.append(glow("sweep", 18))
    rb2 = tube_curve("sweep2", [(-14, 4.2, -6.0), (-3, 4.2, -3.4), (4, 4.2, -0.6), (15, 4.2, 0.2)], 0.014)
    rb2.data.materials.append(glow("sweep2", 10))
    # soft wide glow disc far behind, gives the glass something to diffuse
    light_disc("disc", 1.9, (1.6, 6.5, 0.2), 3.4)
    g = frosted("glass", 0.26)
    c1 = rounded_card(3.6, 4.6, 0.12, 0.42, (2.6, 1.6, 0.4), (0, 0, -8), "c1")
    c2 = rounded_card(3.6, 4.6, 0.12, 0.42, (1.2, 0.8, 0.0), (0, 0, -8), "c2")
    c3 = rounded_card(3.6, 4.6, 0.12, 0.42, (-0.2, 0.0, -0.4), (0, 0, -8), "c3")
    for c in (c1, c2, c3): c.data.materials.append(g)
    mk = mark_object(size=0.62, depth=0.012, name="mark")
    mk.rotation_euler = (math.radians(90), 0, math.radians(-8))
    mk.location = (-1.25, -0.2, 1.25)
    mk.data.materials.append(glow("mark", 3.2))
    # rim lights: they only exist to draw the card edges
    spot("rimL", (-7, -2, 5), (0.8, 0.8, 0), 3, 260, size_y=0.3)
    spot("rimR", (7, -1, -4), (0.8, 0.8, 0), 3, 160, size_y=0.3)
    camera((-3.5, -24, 0.2), (-1.2, 0, 0.1), lens=60, focus=(-0.2, 0.0, -0.4), fstop=4.0)


def mesh_grid(name, nu, nv, fn):
    verts = [fn(i / (nu - 1), j / (nv - 1)) for j in range(nv) for i in range(nu)]
    faces = [(j * nu + i, j * nu + i + 1, (j + 1) * nu + i + 1, (j + 1) * nu + i)
             for j in range(nv - 1) for i in range(nu - 1)]
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

def light_disc(name, r, loc, strength, falloff=2.2):
    """Soft light: a disc whose emission falls from `strength` at the centre to
    zero at the rim, so glass in front of it turns it into a smooth glow."""
    bpy.ops.mesh.primitive_circle_add(vertices=128, radius=1.0, fill_type="NGON", location=loc,
                                      rotation=(math.radians(90), 0, 0))
    o = bpy.context.active_object; o.name = name; o.scale = (r, r, r)
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = falloff
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = strength
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tc.outputs["Object"], gr.inputs["Vector"])
    nt.links.new(gr.outputs["Fac"], pw.inputs[0]); nt.links.new(pw.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], e.inputs["Strength"])
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    o.data.materials.append(m)
    return o

def mark_on(size, loc, rot_z=0, strength=3.0):
    mk = mark_object(size=size, depth=0.012, name="mark")
    mk.rotation_euler = (math.radians(90), 0, math.radians(rot_z)); mk.location = loc
    mk.data.materials.append(glow("mark", strength))
    return mk


def s_orb(sc):
    """A big frosted sphere half out of frame; a thin light ring passes behind
    it, crisp in the open and dissolved inside the glass."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=4.2, location=(4.6, 0, -1.2))
    o = bpy.context.active_object; bpy.ops.object.shade_smooth()
    o.data.materials.append(frosted("orb", 0.3))
    bpy.ops.mesh.primitive_torus_add(major_radius=5.0, minor_radius=0.016, major_segments=512, minor_segments=12,
                                     location=(3.6, 6.0, -0.6), rotation=(math.radians(72), math.radians(-22), 0))
    r = bpy.context.active_object; r.data.materials.append(glow("ring", 20))
    light_disc("core", 3.0, (4.6, 8.0, -1.0), 1.3)
    card = rounded_card(1.3, 1.3, 0.08, 0.3, (-4.6, -3.0, -2.3), (8, 0, 14), "tile")
    card.data.materials.append(frosted("tile", 0.2))
    mark_on(0.56, (-4.6, -3.08, -2.3), 14, 2.4).rotation_euler.x = math.radians(98)
    spot("rimL", (-8, -4, 6), (0, 0, 0), 4, 380, size_y=0.3)
    spot("rimR", (10, -2, -2), (4, 0, -1), 4, 200, size_y=0.3)
    camera((0, -22, 0.4), (0.4, 0, 0), lens=55, focus=(-4.6, -3.0, -2.3), fstop=5.6)

def s_wave(sc):
    """An S-curved frosted sheet, like a pane of glass caught mid-bend, over
    one thin line of light."""
    def f(u, v):
        x = (u - 0.5) * 11; z = (v - 0.5) * 4.2
        y = 1.1 * math.sin(x * 0.42 + 0.6) + 0.25 * z * math.sin(x * 0.2)
        return (x, y, z + 0.18 * x)
    sh = mesh_grid("sheet", 260, 120, f)
    so = sh.modifiers.new("solid", "SOLIDIFY"); so.thickness = 0.14; so.offset = 0
    bv = sh.modifiers.new("bevel", "BEVEL"); bv.width = 0.05; bv.segments = 4; bv.limit_method = "ANGLE"
    sh.rotation_euler = (0, math.radians(-14), 0); sh.location = (2.4, 0, 0.3)
    sh.data.materials.append(frosted("sheet", 0.28))
    ln = tube_curve("line", [(-16, 3.0, -2.6), (-5, 3.0, -0.6), (3, 3.0, 0.8), (16, 3.0, 3.8)], 0.022)
    ln.data.materials.append(glow("line", 22))
    ln2 = tube_curve("line2", [(-16, 5.0, 1.8), (-2, 5.0, 2.8), (16, 5.0, 5.8)], 0.012)
    ln2.data.materials.append(glow("line2", 12))
    light_disc("back", 2.3, (2.4, 8.0, 0.3), 2.6)
    mark_on(0.42, (-9.2, -2.0, -4.2), 0, 2.6)
    spot("rimT", (-2, -4, 9), (1, 0, 0), 6, 420, size_y=0.3)
    spot("rimB", (6, -3, -7), (1, 0, 0), 6, 200, size_y=0.3)
    camera((0, -26, 0.2), (0.3, 0, 0.1), lens=50, focus=(0, 0, 0), fstop=8)

def s_icon(sc):
    """A single frosted tile carrying the mark, seen three-quarter on; a large
    light arc behind it sets up one long highlight gradient."""
    t = rounded_card(2.6, 2.6, 0.32, 0.62, (2.8, 0, 0.1), (0, 0, -24), "tile")
    t.data.materials.append(frosted("tile", 0.24))
    mk = mark_object(size=1.25, depth=0.05, name="mark")
    mk.rotation_euler = (math.radians(90), 0, math.radians(-24))
    import mathutils
    off = mathutils.Matrix.Rotation(math.radians(-24), 3, "Z") @ Vector((0, -0.19, 0))
    mk.location = Vector((2.8, 0, 0.1)) + off
    mk.data.materials.append(glow("markglow", 1.6))
    bpy.ops.mesh.primitive_torus_add(major_radius=3.4, minor_radius=0.014, major_segments=512, minor_segments=12,
                                     location=(3.6, 3.2, 0.3), rotation=(math.radians(90), 0, 0))
    a = bpy.context.active_object; a.data.materials.append(glow("arc", 16))
    light_disc("core", 1.35, (3.0, 3.0, 0.2), 3.0)
    spot("rimL", (-6, -3, 5), (2.8, 0, 0), 3, 320, size_y=0.25)
    spot("rimR", (9, -2, -3), (2.8, 0, 0), 3, 160, size_y=0.25)
    camera((0, -20, 0.8), (0.4, 0, 0.2), lens=55, focus=(2.8, 0, 0.1), fstop=4.0)

def s_matrix(sc):
    """Nothing-style: a field of small light dots; a frosted card floats in
    front, turning the dots inside it into a soft glow."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.035, location=(0, 0, 0))
    dot = bpy.context.active_object; dot.data.materials.append(glow("dot", 6))
    cx, cz = 3.0, 0.4
    for i in range(-40, 41):
        for j in range(-22, 23):
            x, z = i * 0.34, j * 0.34
            fall = math.exp(-(((x - cx) / 7.0) ** 2 + ((z - cz) / 4.0) ** 2))
            if fall < 0.12: continue
            o = dot.copy(); o.location = (x, 3.0, z)
            k = 0.4 + 0.9 * fall; o.scale = (k, k, k)
            sc.collection.objects.link(o)
    bpy.data.objects.remove(dot)
    c = rounded_card(4.2, 5.2, 0.14, 0.5, (3.6, 0.0, 0.2), (0, 0, -10), "card")
    c.data.materials.append(frosted("card", 0.16))
    mark_on(0.5, (2.1, -0.1, 2.0), -10, 2.8)
    spot("rimL", (-6, -3, 6), (3.6, 0, 0), 3, 300, size_y=0.25)
    spot("rimR", (10, -2, -4), (3.6, 0, 0), 3, 160, size_y=0.25)
    camera((0, -24, 0.3), (0.6, 0, 0.2), lens=55, focus=(3.6, 0, 0.2), fstop=6.0)

def s_rings(sc):
    """Two interlocked frosted rings, one light bar behind them."""
    bpy.ops.mesh.primitive_torus_add(major_radius=2.6, minor_radius=0.42, major_segments=256, minor_segments=64,
                                     location=(2.4, 0, 0.3), rotation=(math.radians(90), math.radians(28), 0))
    a = bpy.context.active_object; bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_torus_add(major_radius=2.6, minor_radius=0.42, major_segments=256, minor_segments=64,
                                     location=(4.4, 0.3, -0.4), rotation=(math.radians(20), math.radians(-10), math.radians(70)))
    b = bpy.context.active_object; bpy.ops.object.shade_smooth()
    g = frosted("ring", 0.22)
    a.data.materials.append(g); b.data.materials.append(g)
    ln = tube_curve("bar", [(-16, 4.0, -1.4), (0, 4.0, -0.2), (16, 4.0, 1.6)], 0.03)
    ln.data.materials.append(glow("bar", 20))
    light_disc("core", 3.4, (3.4, 8.0, 0.0), 3.0)
    mark_on(0.42, (-9.4, -1.5, -4.3), 0, 2.6)
    spot("rimL", (-6, -4, 6), (3.4, 0, 0), 3, 380, size_y=0.3)
    spot("rimR", (10, -2, -4), (3.4, 0, 0), 3, 200, size_y=0.3)
    camera((0, -26, 0.2), (0.3, 0, 0), lens=50, focus=(3.4, 0, 0), fstop=5.6)

def s_fins(sc):
    """A row of tall frosted fins, each turned a little more than the last,
    with light rising behind them."""
    for i in range(9):
        x = -1.0 + i * 0.95
        c = rounded_card(0.75, 6.0, 0.1, 0.36, (x, i * 0.12, 0.0), (0, 0, -35 + i * 9), f"fin{i}")
        c.data.materials.append(frosted("fin", 0.26))
    ln = tube_curve("rise", [(-16, 3.2, -3.4), (0, 3.2, -1.2), (6, 3.2, 1.0), (16, 3.2, 4.2)], 0.024)
    ln.data.materials.append(glow("rise", 22))
    light_disc("core", 3.4, (3.4, 7.5, 0.4), 3.0)
    mark_on(0.42, (-9.4, -1.5, -4.3), 0, 2.6)
    spot("rimL", (-6, -4, 7), (3, 0, 0), 3, 380, size_y=0.3)
    spot("rimR", (10, -2, -5), (3, 0, 0), 3, 200, size_y=0.3)
    camera((0, -26, 0.4), (0.3, 0, 0), lens=50, focus=(3, 0, 0), fstop=6.0)


SCENES = {"stack": s_stack, "orb": s_orb, "wave": s_wave, "icon": s_icon,
          "matrix": s_matrix, "rings": s_rings, "fins": s_fins}


# ---------------------------------------------------------------- v3b: the mark as the subject
def backlight(cx=0.0, cz=0.0, y=4.0, tilt=0.22, disc=2.2, disc_strength=3.0, lines=True, style="diag"):
    """Shared light rig: a soft glow disc behind the subject plus thin light
    lines. style: "diag" two lines on a gentle diagonal, "s" one S-curve
    sweeping under and over the subject, "arc" a partial light ring."""
    light_disc("glow", disc, (cx, y + 3.0, cz), disc_strength)
    if not lines:
        return
    if style == "diag":
        t = tube_curve("l1", [(-18, y, cz - 18 * tilt - 0.8), (cx, y, cz), (18, y, cz + 18 * tilt + 0.5)], 0.024)
        t.data.materials.append(glow("l1", 20))
        t2 = tube_curve("l2", [(-18, y + 1.2, cz - 18 * tilt - 2.6), (cx + 1, y + 1.2, cz - 1.3), (18, y + 1.2, cz + 18 * tilt - 1.6)], 0.011)
        t2.data.materials.append(glow("l2", 12))
    elif style == "s":
        t = tube_curve("l1", [(-18, y, cz - 6.5), (-6, y, cz - 3.8), (cx - 1.5, y, cz - 1.6), (cx + 1.5, y, cz + 1.4),
                              (cx + 5, y, cz + 2.2), (18, y, cz + 1.2)], 0.022)
        t.data.materials.append(glow("l1", 20))
        t2 = tube_curve("l2", [(-18, y + 1.5, cz - 8.0), (-4, y + 1.5, cz - 4.6), (cx + 1, y + 1.5, cz - 0.8),
                               (18, y + 1.5, cz - 0.2)], 0.01)
        t2.data.materials.append(glow("l2", 10))
    elif style == "arc":
        bpy.ops.mesh.primitive_torus_add(major_radius=disc * 1.9, minor_radius=0.016, major_segments=512, minor_segments=12,
                                         location=(cx + 0.8, y, cz + 0.4), rotation=(math.radians(90), 0, 0))
        bpy.context.active_object.data.materials.append(glow("arc", 16))

def rims(target, k=1.0):
    spot("rimL", (-7, -3, 6), target, 3, 320 * k, size_y=0.25)
    spot("rimR", (9, -2, -4), target, 3, 170 * k, size_y=0.25)
    spot("top", (0, -1, 9), target, 5, 120 * k, size_y=0.2)

def s_glassmark(sc):
    """The mark itself as a thick frosted-glass object, three-quarter view,
    with light passing behind it."""
    m = mark_object(size=3.0, depth=0.75, name="mark")
    bevel(m, 0.05, 6)
    m.rotation_euler = (math.radians(90), 0, math.radians(-22)); m.location = (2.6, 0, 0.1)
    m.data.materials.append(frosted("markglass", 0.2))
    backlight(2.6, 0.1, 3.0, 0.18, 1.2, 3.2, style="s")
    rims((2.6, 0, 0.1))
    camera((0, -20, 0.6), (0.5, 0, 0.1), lens=55, focus=(2.6, 0, 0.1), fstop=5.6)

def s_cutout(sc):
    """A thick frosted plate with the mark cut clean through: light behind is
    blurred by the glass and crisp through the cut."""
    p_ = rounded_card(4.2, 4.2, 0.36, 0.7, (2.8, 0, 0.1), (0, 0, -18), "plate")
    bv = p_.modifiers["soft"]; p_.modifiers.remove(bv)
    cut = mark_object(size=2.3, depth=1.2, name="cutter")
    cut.rotation_euler = (math.radians(90), 0, math.radians(-18))
    cut.location = (2.8, 0, 0.1)
    import mathutils
    cut.location += mathutils.Matrix.Rotation(math.radians(-18), 3, "Z") @ Vector((0, 0.6, 0))
    bo = p_.modifiers.new("cut", "BOOLEAN"); bo.object = cut; bo.operation = "DIFFERENCE"; bo.solver = "EXACT"
    cut.hide_render = True
    sb = p_.modifiers.new("soft", "BEVEL"); sb.width = 0.02; sb.segments = 4
    sb.limit_method = "ANGLE"; sb.angle_limit = math.radians(40); sb.harden_normals = True
    p_.data.materials.append(frosted("plate", 0.3))
    backlight(2.8, 0.1, 2.6, 0.2, 1.7, 3.6)
    rims((2.8, 0, 0.1))
    camera((0, -20, 0.5), (0.6, 0, 0.1), lens=55, focus=(2.8, 0, 0.1), fstop=5.6)

def s_exploded(sc):
    """The mark taken apart: each of its pieces a glass bar at its own depth,
    like an exploded technical drawing."""
    import random
    m = mark_object(size=3.2, depth=0.22, name="mark")
    bpy.context.view_layer.objects.active = m; m.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE"); bpy.ops.object.mode_set(mode="OBJECT")
    parts = [o for o in sc.objects if o.name.startswith("mark")]
    g = frosted("bar", 0.16)
    rnd = random.Random(3)
    root = bpy.data.objects.new("root", None); sc.collection.objects.link(root)
    for i, o in enumerate(parts):
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.select_all(action="DESELECT"); o.select_set(True)
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")
        o.location.z += rnd.uniform(-1.8, 1.8)          # local Z = depth once rotated
        bevel(o, 0.02, 4); o.data.materials.clear(); o.data.materials.append(g)
        o.parent = root
    root.rotation_euler = (math.radians(90), math.radians(8), math.radians(-38)); root.location = (2.6, 0, 0.2)
    backlight(2.6, 0.2, 4.5, 0.2, 1.0, 1.8, style="arc")
    rims((2.6, 0, 0.2))
    camera((0, -21, 1.4), (0.5, 0, 0.1), lens=55, focus=(2.6, 0, 0.2), fstop=6.3)

def s_finsmark(sc):
    """The glowing mark hidden behind a row of frosted fins: each fin shows
    a soft slice of it."""
    for i in range(11):
        x = 0.2 + i * 0.62
        c = rounded_card(0.5, 5.2, 0.1, 0.24, (x, 0, 0.0), (0, 0, -30 + i * 6), f"fin{i}")
        c.data.materials.append(frosted("fin", 0.22))
    mk = mark_object(size=2.6, depth=0.04, name="mark")
    mk.rotation_euler = (math.radians(90), 0, 0); mk.location = (3.3, 1.4, 0.0)
    mk.data.materials.append(glow("markglow", 1.8))
    light_disc("glow", 2.4, (3.3, 3.5, 0.0), 0.7)
    ln = tube_curve("l1", [(-18, 2.2, -3.8), (0, 2.2, -1.2), (18, 2.2, 2.6)], 0.02)
    ln.data.materials.append(glow("l1", 18))
    rims((3.3, 0, 0))
    camera((0, -21, 0.3), (0.5, 0, 0), lens=55, focus=(3.3, 0, 0), fstop=6.3)

def s_fan(sc):
    """Five frosted cards fanned open around a shared corner; the front card
    carries the mark."""
    import mathutils
    piv = Vector((1.2, 0, -2.4))
    for i in range(5):
        a = -34 + i * 15
        R = mathutils.Matrix.Rotation(math.radians(a), 3, "Y")
        c = rounded_card(2.6, 4.2, 0.1, 0.38, (0, 0, 0), (0, 0, 0), f"card{i}")
        c.location = piv + R @ Vector((0.9, -0.25 * (4 - i), 2.1)) + Vector((0, 0.3 * i, 0))
        c.rotation_euler = (0, math.radians(a), math.radians(-6))
        c.data.materials.append(frosted("card", 0.24))
        if i == 0:
            front = c
    mk = mark_object(size=0.5, depth=0.012, name="mark")
    mk.rotation_euler = front.rotation_euler.copy(); mk.rotation_euler.x += math.radians(90)
    mk.location = front.location + front.matrix_world.to_3x3() @ Vector((-0.75, -0.07, 1.45))
    mk.data.materials.append(glow("mark", 3.2))
    backlight(2.4, 0.2, 3.0, 0.24, 1.8, 3.0, style="s")
    rims((1.8, 0, 0))
    camera((0, -20, 0.6), (0.4, 0, 0.2), lens=55, focus=(1.8, 0, 0), fstop=6.3)

def s_medallion(sc):
    """A thick frosted-glass disc standing on edge, the mark cut into its face;
    a thin light ring sits behind, slightly offset."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=2.0, depth=0.4, location=(2.8, 0, 0.2),
                                        rotation=(math.radians(90), 0, math.radians(-20)))
    d = bpy.context.active_object
    cut = mark_object(size=1.5, depth=0.2, name="cutter")
    cut.rotation_euler = (math.radians(90), 0, math.radians(-20))
    import mathutils
    cut.location = Vector((2.8, 0, 0.2)) + mathutils.Matrix.Rotation(math.radians(-20), 3, "Z") @ Vector((0, -0.12, 0))
    bo = d.modifiers.new("cut", "BOOLEAN"); bo.object = cut; bo.operation = "DIFFERENCE"; bo.solver = "EXACT"
    cut.hide_render = True
    bv = d.modifiers.new("soft", "BEVEL"); bv.width = 0.05; bv.segments = 6
    bv.limit_method = "ANGLE"; bv.angle_limit = math.radians(40); bv.harden_normals = True
    bpy.ops.object.shade_smooth()
    d.data.materials.append(frosted("disc", 0.22))
    bpy.ops.mesh.primitive_torus_add(major_radius=2.9, minor_radius=0.014, major_segments=512, minor_segments=12,
                                     location=(3.5, 3.0, 0.5), rotation=(math.radians(90), 0, 0))
    bpy.context.active_object.data.materials.append(glow("ring", 16))
    light_disc("glow", 1.6, (2.9, 3.4, 0.2), 2.2)
    rims((2.8, 0, 0.2))
    camera((0, -20, 0.5), (0.6, 0, 0.1), lens=55, focus=(2.8, 0, 0.2), fstop=5.6)

def s_columns(sc):
    """A row of frosted pill columns of different heights, like a quiet level
    meter; light rises behind them and the mark sits on the tallest."""
    hs = [1.6, 2.4, 3.4, 4.6, 3.8, 2.8, 2.0, 1.4]
    for i, h in enumerate(hs):
        c = rounded_card(0.62, h, 0.62, 0.3, (0.2 + i * 0.86, 0, -2.3 + h / 2), (0, 0, 0), f"col{i}")
        c.data.materials.append(frosted("col", 0.24))
    mk = mark_object(size=0.4, depth=0.01, name="mark")
    mk.rotation_euler = (math.radians(90), 0, 0); mk.location = (0.2 + 3 * 0.86, -0.32, -2.3 + 4.6 - 0.5)
    mk.data.materials.append(glow("mark", 3.0))
    backlight(3.2, -0.6, 2.4, 0.2, 2.6, 3.0)
    rims((3.2, 0, 0))
    camera((0, -21, 0.3), (0.6, 0, -0.1), lens=55, focus=(3.2, 0, 0), fstop=6.3)

SCENES.update({"glassmark": s_glassmark, "cutout": s_cutout, "exploded": s_exploded,
               "finsmark": s_finsmark, "fan": s_fan, "medallion": s_medallion, "columns": s_columns})


# ---------------------------------------------------------------- v7: lens, keys
def image_emission(name, path, strength=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(path)
    tex.interpolation = "Cubic"
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m

def s_lens(sc):
    """A clear glass lens resting over the topographic map, magnifying the
    mark at the summit. Everything outside the lens stays flat line art."""
    topo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "adaylar-v5", "maze-topo.png")
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    pl = bpy.context.active_object; pl.scale = (16, 9, 1)
    pl.data.materials.append(image_emission("topo", os.path.abspath(topo), 1.0))
    lx, ly = (1720 / 2560 - 0.5) * 16, (0.5 - 700 / 1440) * 9
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.55, location=(lx - 0.35, ly + 0.2, 0.3))
    le = bpy.context.active_object; le.scale = (1, 1, 0.2); bpy.ops.object.shade_smooth()
    g = frosted("lens", 0.0, ior=1.52)
    g.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0.0
    le.data.materials.append(g)
    spot("rimL", (-6, 4, 5), (lx, ly, 0.5), 3, 260, size_y=0.25)
    spot("rimR", (8, -5, 3), (lx, ly, 0.5), 3, 140, size_y=0.25)
    camera((lx - 1.2, ly - 9.5, 8.5), (lx - 1.6, ly + 0.4, 0), lens=50, focus=(lx - 0.35, ly + 0.2, 0.5), fstop=4.0)

def s_keys(sc):
    """A field of frosted glass tiles, like keycaps; one of them is lit from
    beneath by the mark, and the glow spills into its neighbours."""
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    fl = bpy.context.active_object
    fm = bpy.data.materials.new("floor"); fm.use_nodes = True
    fb = fm.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1); fb.inputs["Roughness"].default_value = 1.0
    fb.inputs["Specular IOR Level"].default_value = 0.0
    fl.data.materials.append(fm)
    g = frosted("key", 0.28)
    t, gap = 1.5, 0.26
    lit = (1, 0)
    for i in range(-3, 5):
        for j in range(-2, 3):
            x, y = i * (t + gap), j * (t + gap)
            k = rounded_card(t, t, 0.34, 0.3, (x, y, 0.22), (90, 0, 0), f"k{i}_{j}")
            k.data.materials.append(g)
    lx, ly = lit[0] * (t + gap), lit[1] * (t + gap)
    mk = mark_object(size=0.9, depth=0.01, name="mark"); mk.location = (lx, ly, 0.02)
    mk.data.materials.append(glow("mark", 8))
    light_disc("under", 1.6, (lx, ly, 0.01), 2.2).rotation_euler = (0, 0, 0)
    spot("rimL", (-8, 6, 6), (lx, ly, 0.3), 4, 260, size_y=0.25)
    spot("rimR", (8, -6, 3), (lx, ly, 0.3), 4, 120, size_y=0.25)
    spot("soft", (0, -2, 14), (0, 0, 0), 16, 45, size_y=16)
    camera((lx - 5.0, ly - 12.5, 10.5), (lx - 1.4, ly + 0.2, 0.2), lens=50, focus=(lx, ly, 0.3), fstop=3.5)

SCENES.update({"lens": s_lens, "keys": s_keys})

if __name__ == "__main__":
    sc = S.reset()
    sc.cycles.samples = 96 if PREVIEW else 1024
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.glossy_bounces = 12
    sc.view_settings.look = "None"
    SCENES[SCENE](sc)
    os.makedirs(OUT, exist_ok=True)
    sc.render.filepath = os.path.join(OUT, f"raw-{SCENE}{'-preview' if PREVIEW else ''}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
