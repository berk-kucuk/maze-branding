"""Maze Linux — monochrome material studies (v5): machined metal, black
ceramic, projected light. OLED black, the mark at a moderate size.

    blender -b --factory-startup -P matter.py -- <scene> <out-dir> [--preview]
"""
import bpy, math, os, sys
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenes as S
from scenes import camera, bevel, mark_object, spot, haze, floor
from glass import rounded_card, light_disc, glow

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SCENE = argv[0] if argv else "machined"
OUT = argv[1] if len(argv) > 1 else "."
PREVIEW = "--preview" in argv


def principled(name, base, rough, metal=0.0, aniso=0.0, coat=0.0, coat_rough=0.03):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Anisotropic"].default_value = aniso
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    return m, b

def radial_brushed(m, b):
    """Concentric (lathe) brushing: anisotropy tangent runs around the Z axis."""
    nt = m.node_tree
    tg = nt.nodes.new("ShaderNodeTangent"); tg.direction_type = "RADIAL"; tg.axis = "Z"
    nt.links.new(tg.outputs["Tangent"], b.inputs["Tangent"])

def cut(obj, cutter):
    """Boolean-subtract `cutter`, whose transform is given in obj's local space."""
    bo = obj.modifiers.new("cut", "BOOLEAN"); bo.object = cutter; bo.operation = "DIFFERENCE"; bo.solver = "EXACT"
    cutter.parent = obj
    cutter.hide_render = True
    return bo


# ---------------------------------------------------------------- scenes
def s_machined(sc):
    """A thick disc of dark anodised titanium, lathe-brushed, the mark milled
    into its face. One long strip light draws the brushing into a fan."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=2.4, depth=0.5, location=(0, 0, 0.25))
    d = bpy.context.active_object
    c = mark_object(size=2.0, depth=0.4, name="cutter"); c.location = (0, 0, 0.13)
    cut(d, c)
    bv = d.modifiers.new("bevel", "BEVEL"); bv.width = 0.02; bv.segments = 4
    bv.limit_method = "ANGLE"; bv.angle_limit = math.radians(40); bv.harden_normals = True
    bpy.ops.object.shade_smooth()
    m, b = principled("ti", (0.16, 0.165, 0.175), 0.3, metal=1.0, aniso=0.85)
    radial_brushed(m, b)
    d.data.materials.append(m)
    d.rotation_euler = (math.radians(-6), 0, math.radians(12))
    d.location = (2.2, 0, 0)
    spot("strip", (-2.5, 7.5, 6.0), (2.2, 0, 0), 16, 380, (0.95, 0.97, 1.0), size_y=0.12)
    spot("kick", (7, -3, 1.2), (2.2, 0, 0.3), 3, 160, size_y=0.1)
    camera((-0.4, -10.4, 7.4), (1.5, 0.3, 0.1), lens=60, focus=(2.2, 0, 0.5), fstop=2.8)

def s_ceramic(sc):
    """Black on black: a matte black field with the mark raised in glossy
    black ceramic. Only a grazing light reveals it."""
    fm, fb = principled("matte", (0.003, 0.003, 0.003), 0.9)
    fb.inputs["Specular IOR Level"].default_value = 0.05
    floor(fm, size=60)
    mk = mark_object(size=3.0, depth=0.12, name="mark")
    bevel(mk, 0.018, 5)
    mk.data.materials.append(principled("gloss", (0.01, 0.01, 0.011), 0.08, coat=1.0)[0])
    mk.rotation_euler = (0, 0, math.radians(0)); mk.location = (2.4, 0.6, 0)
    spot("graze", (-11, 6, 1.1), (2.4, 0.6, 0), 8, 700, (0.95, 0.97, 1.0), size_y=0.25)
    spot("spec", (5, 11, 6), (2.4, 0.6, 0), 10, 700, size_y=0.3)
    camera((0.2, -8.8, 7.4), (1.5, 0.5, 0), lens=55, focus=(2.4, 0.6, 0.1), fstop=2.2)

def s_gobo(sc):
    """Light projected through a stencil of the mark onto a dark plaster wall,
    beams visible in a little haze. The mark exists only as light."""
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 6, 0), rotation=(math.radians(90), 0, 0))
    w = bpy.context.active_object
    m, b = principled("plaster", (0.18, 0.18, 0.18), 0.95)
    nt = m.node_tree
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 60; nz.inputs["Detail"].default_value = 12
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.25
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    w.data.materials.append(m)
    floor(principled("floor", (0.03, 0.03, 0.03), 0.6)[0], size=40, z=-3.5)
    # stencil: a big opaque card with the mark cut through
    st = rounded_card(3.0, 3.0, 0.02, 0.01, (0, 0, 0), (0, 0, 0), "stencil")
    st.modifiers.remove(st.modifiers["soft"])
    c = mark_object(size=0.8, depth=0.4, name="cutter"); c.rotation_euler = (math.radians(90), 0, 0); c.location = (0, 0.2, 0)
    cut(st, c)
    st.data.materials.append(principled("black", (0, 0, 0), 1.0)[0])
    st.visible_camera = False
    L = bpy.data.lights.new("proj", "SPOT"); L.energy = 40000; L.spot_size = math.radians(20)
    L.shadow_soft_size = 0.02; L.spot_blend = 0.0; L.color = (0.95, 0.97, 1.0)
    lo = bpy.data.objects.new("proj", L); sc.collection.objects.link(lo)
    lo.location = (-1.6, -9.0, 1.0)
    aim_dir = (Vector((1.6, 6, -0.2)) - lo.location).normalized()
    lo.rotation_euler = aim_dir.to_track_quat("-Z", "Y").to_euler()
    st.location = lo.location + aim_dir * 3.5
    st.rotation_euler = aim_dir.to_track_quat("Y", "Z").to_euler()
    haze(0.012, 30, 0.5, (0, -2, 0))
    camera((5.5, -12, 0.6), (1.0, 4, 0.0), lens=45, focus=(1.6, 6, -0.2), fstop=4.0)


SCENES = {"machined": s_machined, "ceramic": s_ceramic, "gobo": s_gobo}

if __name__ == "__main__":
    sc = S.reset()
    sc.cycles.samples = 96 if PREVIEW else 1024
    sc.view_settings.look = "None"
    SCENES[SCENE](sc)
    os.makedirs(OUT, exist_ok=True)
    sc.render.filepath = os.path.join(OUT, f"raw-{SCENE}{'-preview' if PREVIEW else ''}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
