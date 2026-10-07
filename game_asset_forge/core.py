# Shared geometry / material helpers for Game Asset Forge.
import bpy
import bmesh
import math
from mathutils import Vector, Matrix

TAU = 2 * math.pi
AX = {'X': Vector((1, 0, 0)), 'Y': Vector((0, 1, 0)), 'Z': Vector((0, 0, 1))}


# ---------------------------------------------------------------- colors / materials
def srgb2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(rgb):
    return tuple(srgb2lin(c) for c in rgb[:3])


def hexrgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(x * (1 - t) + y * t for x, y in zip(a, b))


def principled(m):
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (-300, 0)
        nt.links.new(bsdf.outputs[0], out.inputs[0])
    return bsdf


def make_mat(name, rgb, rough=0.8, spec=0.15, metal=0.0, alpha=1.0, emit=0.0):
    """rgb is sRGB 0..1 (as shown in color pickers)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    bsdf = principled(m)
    c = lin(rgb)
    bsdf.inputs['Base Color'].default_value = (*c, 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = spec
    bsdf.inputs['Alpha'].default_value = alpha
    if emit > 0 and 'Emission Color' in bsdf.inputs:
        bsdf.inputs['Emission Color'].default_value = (*c, 1)
        bsdf.inputs['Emission Strength'].default_value = emit
    if alpha < 1.0:
        for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    m.diffuse_color = (*c, alpha)
    return m


def textured_mat(name, image, rough=0.7, fallback=(1, 1, 1)):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    bsdf = principled(m)
    nt = m.node_tree
    tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE'), None) or nt.nodes.new('ShaderNodeTexImage')
    tex.image = image
    tex.extension = 'EXTEND'
    tex.location = (-700, 0)
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = rough
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.15
    m.diffuse_color = (*lin(fallback), 1)
    return m


def image_from_array(name, arr):
    """arr: float32 (H, W, 3|4) sRGB, row 0 = bottom. Packed into the .blend."""
    import numpy as np
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], axis=2)
    im = bpy.data.images.get(name)
    if im is not None and (im.size[0] != w or im.size[1] != h):
        bpy.data.images.remove(im)
        im = None
    if im is None:
        im = bpy.data.images.new(name, w, h, alpha=False)
    im.pixels.foreach_set(arr.astype(np.float32).ravel())
    im.update()
    try:
        im.pack()
    except Exception:
        pass
    return im


def outline_mat():
    m = bpy.data.materials.get('GAF_Outline')
    if m is None:
        m = bpy.data.materials.new('GAF_Outline')
        bsdf = principled(m)
        bsdf.inputs['Base Color'].default_value = (0.02, 0.015, 0.03, 1)
        bsdf.inputs['Roughness'].default_value = 1.0
        if 'Specular IOR Level' in bsdf.inputs:
            bsdf.inputs['Specular IOR Level'].default_value = 0.0
    m.use_backface_culling = True
    m.diffuse_color = (0.02, 0.015, 0.03, 1)
    return m


def add_outline(ob, thick=0.003):
    """Inverted-hull anime outline (modifier 'Outline', uses the last material slot)."""
    om = outline_mat()
    if om.name not in [m.name for m in ob.data.materials if m]:
        ob.data.materials.append(om)
    md = ob.modifiers.get('Outline') or ob.modifiers.new('Outline', 'SOLIDIFY')
    md.thickness = thick
    md.offset = 1.0
    md.use_flip_normals = True
    md.use_rim = False
    md.material_offset = 64
    md.use_quality_normals = True
    return md


# ---------------------------------------------------------------- objects / collections
def get_col(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def clear_col(col):
    for ob in list(col.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Armature) and data.users == 0:
            bpy.data.armatures.remove(data)


def remove_obj(name):
    ob = bpy.data.objects.get(name)
    if ob is not None:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)


def bm_to_obj(bm, name, col, mats, smooth=True):
    remove_obj(name)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = smooth
    return ob


def add_subsurf(ob, lv=1, rlv=2):
    md = ob.modifiers.new('Subdivision', 'SUBSURF')
    md.levels = lv
    md.render_levels = rlv
    return md


def add_solidify(ob, t):
    md = ob.modifiers.new('Thickness', 'SOLIDIFY')
    md.thickness = t
    md.offset = -1
    return md


def apply_modifier(ob, name):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=name)


def merge_bm(dst, src):
    me = bpy.data.meshes.new('_gaf_tmp')
    src.to_mesh(me)
    src.free()
    dst.from_mesh(me)
    bpy.data.meshes.remove(me)


# ---------------------------------------------------------------- lofting
def _sp(c, e):
    return math.copysign(abs(c) ** (2.0 / e), c)


def angles_uniform(n, offset=0.0):
    return [(offset + TAU * k / n) % TAU for k in range(n)]


def angles_with(n, extra, tol=0.03):
    def ad(a, b):
        d = abs(a - b) % TAU
        return min(d, TAU - d)
    extra = [e % TAU for e in extra]
    base = [a for a in angles_uniform(n) if all(ad(a, e) > tol for e in extra)]
    return sorted(base + extra)


def loft(bm, sections, angles, a1='X', a2='Y', cap0=True, cap1=True,
         tip0=None, tip1=None, mat_fn=None):
    """sections: [(center, r1p, r1n, r2p, r2n, power)] — cross-section in the (a1, a2) plane.
    The loft must run along a1 x a2 for outward normals. Writes cylindrical UVs."""
    A1, A2 = AX[a1], AX[a2]
    rings, centers = [], []
    for (c, r1p, r1n, r2p, r2n, pw) in sections:
        c = Vector(c)
        centers.append(c)
        ring = []
        for th in angles:
            ca, sa = math.cos(th), math.sin(th)
            u = _sp(ca, pw) * (r1p if ca >= 0 else r1n)
            v = _sp(sa, pw) * (r2p if sa >= 0 else r2n)
            ring.append(bm.verts.new(c + A1 * u + A2 * v))
        rings.append(ring)
    n = len(angles)
    d = [0.0]
    for i in range(1, len(centers)):
        d.append(d[-1] + (centers[i] - centers[i - 1]).length + 1e-6)
    tv = [x / d[-1] for x in d]
    uvl = bm.loops.layers.uv.verify()

    def mid_ang(j):
        a, b = angles[j], angles[(j + 1) % n]
        if b < a:
            b += TAU
        return ((a + b) / 2) % TAU

    for i in range(len(rings) - 1):
        for j in range(n):
            j2 = (j + 1) % n
            f = bm.faces.new((rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]))
            uj, uj2 = j / n, (j + 1) / n
            for lp, uv in zip(f.loops, ((uj, tv[i]), (uj2, tv[i]), (uj2, tv[i + 1]), (uj, tv[i + 1]))):
                lp[uvl].uv = uv
            if mat_fn:
                f.material_index = mat_fn(i, j, mid_ang(j))
    for cap, idx, tip, order in ((cap0, 0, tip0, -1), (cap1, -1, tip1, 1)):
        if not cap:
            continue
        cv = bm.verts.new(Vector(tip) if tip is not None else centers[idx])
        r = rings[idx]
        for j in range(n):
            j2 = (j + 1) % n
            f = bm.faces.new((cv, r[j2], r[j]) if order < 0 else (cv, r[j], r[j2]))
            for lp in f.loops:
                co = lp.vert.co - centers[idx]
                lp[uvl].uv = (0.5 + co.dot(A1) * 2, 0.5 + co.dot(A2) * 2)
            if mat_fn:
                f.material_index = mat_fn(0 if idx == 0 else len(rings) - 2, j, mid_ang(j))


def mirror_bm(bm):
    """Duplicate all geometry mirrored across X (keeps normals correct)."""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    ret = bmesh.ops.duplicate(bm, geom=geom)
    nv = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
    nf = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMFace)]
    for v in nv:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(bm, faces=nf)


def spike(bm, base, d, length, width, thick=0.45, droop=0.0, sides=6, segs=4,
          wdir=None, bend=None, taper=0.8, belly=0.0):
    """Flattened tapering clump from base along d (hair spikes, leaves, horns...)."""
    d = Vector(d).normalized()
    if wdir is None:
        wdir = Vector((0, 0, 1)).cross(d) if abs(d.z) < 0.97 else Vector((1, 0, 0))
    W = Vector(wdir).normalized()
    bend = Vector(bend) if bend is not None else Vector((0, 0, -1))
    pts = [base + d * length * (k / segs) + bend * droop * length * (k / segs) ** 2 for k in range(segs + 1)]
    return strand(bm, pts, width, thick=thick, sides=sides, wdir=W, taper=taper, belly=belly)


def strand(bm, pts, width, thick=0.35, sides=6, wdir=(1, 0, 0), taper=1.1, belly=0.3, tmin=0.0):
    """Tapering flattened lock following a polyline (closed mesh)."""
    pts = [Vector(p) for p in pts]
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    W0 = Vector(wdir).normalized()
    angs = [TAU * a / sides for a in range(sides)]
    rings = []
    for k in range(len(pts) - 1):
        t = L[k] / L[-1]
        T = (pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]).normalized()
        Wk = W0 - T * W0.dot(T)
        if Wk.length < 1e-6:
            Wk = T.orthogonal()
        Wk.normalize()
        Nk = Wk.cross(T)
        w = 0.5 * width * max((1 - t) ** taper * (1 + belly * math.sin(math.pi * t)), tmin)
        rings.append([bm.verts.new(pts[k] + Wk * math.cos(a) * w + Nk * math.sin(a) * w * thick) for a in angs])
    tip = bm.verts.new(pts[-1])
    base_c = bm.verts.new(pts[0] - (pts[1] - pts[0]).normalized() * 0.002)
    faces = []
    for k in range(len(rings) - 1):
        for j in range(sides):
            j2 = (j + 1) % sides
            faces.append(bm.faces.new((rings[k][j], rings[k + 1][j], rings[k + 1][j2], rings[k][j2])))
    for j in range(sides):
        j2 = (j + 1) % sides
        faces.append(bm.faces.new((rings[-1][j], tip, rings[-1][j2])))
        faces.append(bm.faces.new((rings[0][j2], base_c, rings[0][j])))
    return faces


def add_box(bm, center, size, rot=None, mat=0):
    """Axis box (optionally rotated) with box-projected UVs."""
    ret = bmesh.ops.create_cube(bm, size=1.0)
    verts = ret['verts']
    M = Matrix.Translation(Vector(center))
    if rot is not None:
        M = M @ (rot.to_4x4() if hasattr(rot, 'to_4x4') else rot)
    M = M @ Matrix.Diagonal((*size, 1.0))
    bmesh.ops.transform(bm, matrix=M, verts=verts)
    faces = list({f for v in verts for f in v.link_faces})
    for f in faces:
        f.material_index = mat
    box_uv(bm, faces)
    return faces


def box_uv(bm, faces=None, scale=1.0):
    bm.normal_update()
    uvl = bm.loops.layers.uv.verify()
    for f in (faces if faces is not None else bm.faces):
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for lp in f.loops:
            co = lp.vert.co
            lp[uvl].uv = (co[a] * scale, co[b] * scale)


def tri_count(ob, outline=False):
    md = ob.modifiers.get('Outline')
    prev = None
    if md is not None:
        prev = md.show_viewport
        md.show_viewport = outline
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    e = ob.evaluated_get(dg)
    m = e.to_mesh()
    n = sum(len(p.vertices) - 2 for p in m.polygons)
    e.to_mesh_clear()
    if md is not None:
        md.show_viewport = prev
    return n
