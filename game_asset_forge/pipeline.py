# Game-ready pipeline: cleanup, UVs, LODs, collision (Godot import hints), report, export.
import os
import bpy
import bmesh
from mathutils import Vector
from .core import tri_count, get_col


def _is_rigged(ob):
    return any(m.type == 'ARMATURE' for m in ob.modifiers) or (ob.parent is not None and ob.parent.type == 'ARMATURE')


def _meshes(objs):
    return [o for o in objs if o.type == 'MESH' and not o.name.endswith(('-colonly', '-convcolonly'))]


def _ensure_object_mode():
    ob = bpy.context.view_layer.objects.active
    if ob is not None and ob.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def smart_uv(ob, angle=66.0, margin=0.02):
    vl = bpy.context.view_layer
    prev = vl.objects.active
    sel = list(bpy.context.selected_objects)
    for o in sel:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    import math
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select_set(False)
    for o in sel:
        o.select_set(True)
    vl.objects.active = prev


def make_game_ready(objs, merge=True, fix_normals=True, delete_loose=True, ensure_uv=True,
                    apply_xform=True, triangulate=False, origin_bottom=False):
    _ensure_object_mode()
    log = []
    for ob in _meshes(objs):
        notes = []
        rigged = _is_rigged(ob)
        if ob.data.users > 1:
            ob.data = ob.data.copy()
            notes.append("made mesh single-user")
        if apply_xform and not rigged and (ob.scale != Vector((1, 1, 1)) or ob.matrix_basis.to_euler() != ob.matrix_basis.to_euler().__class__()):
            if ob.children:
                notes.append("transform NOT applied (object has children)")
            else:
                ob.data.transform(ob.matrix_basis.to_3x3().to_4x4())
                ob.rotation_mode = 'XYZ'
                ob.rotation_euler = (0, 0, 0)
                ob.scale = (1, 1, 1)
                notes.append("applied rotation/scale")
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        if merge and not rigged:
            n0 = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
            if len(bm.verts) != n0:
                notes.append(f"merged {n0 - len(bm.verts)} duplicate verts")
        if delete_loose:
            loose_v = [v for v in bm.verts if not v.link_edges]
            loose_e = [e for e in bm.edges if not e.link_faces]
            if loose_v or loose_e:
                bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
                bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context='VERTS')
                notes.append(f"removed {len(loose_v)} loose verts / {len(loose_e)} loose edges")
        if fix_normals and not rigged:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        if triangulate:
            bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
            notes.append("triangulated")
        if origin_bottom and not rigged and bm.verts:
            zmin = min(v.co.z for v in bm.verts)
            cx = sum(v.co.x for v in bm.verts) / len(bm.verts)
            cy = sum(v.co.y for v in bm.verts) / len(bm.verts)
            off = Vector((cx, cy, zmin))
            if off.length > 1e-5:
                for v in bm.verts:
                    v.co -= off
                ob.location += off
                notes.append("origin -> bottom centre")
        bm.to_mesh(ob.data)
        bm.free()
        if ensure_uv and not ob.data.uv_layers:
            smart_uv(ob)
            notes.append("auto UV unwrapped")
        if not ob.data.materials:
            notes.append("WARNING: no material")
        log.append(f"{ob.name}: " + (", ".join(notes) if notes else "ok"))
    return log


def generate_lods(objs, ratios=(0.5, 0.25)):
    _ensure_object_mode()
    out = []
    for ob in _meshes(objs):
        if ob.name.rsplit('_LOD', 1)[-1].isdigit():
            continue
        col = get_col(ob.users_collection[0].name + "_LODs") if ob.users_collection else get_col("LODs")
        for i, r in enumerate(ratios, 1):
            name = f"{ob.name}_LOD{i}"
            old = bpy.data.objects.get(name)
            if old:
                bpy.data.objects.remove(old, do_unlink=True)
            lod = ob.copy()
            lod.data = ob.data.copy()
            lod.name = name
            col.objects.link(lod)
            dm = lod.modifiers.new('LOD_Decimate', 'DECIMATE')
            dm.ratio = r
            dm.use_collapse_triangulate = True
            # keep the armature first so skinning still works on LODs
            if 'Outline' in lod.modifiers:
                lod.modifiers.remove(lod.modifiers['Outline'])
            lod.hide_set(True)
            out.append(f"{name}: {tri_count(lod)} tris")
    return out


def add_collision(objs, kind='CONVEX'):
    """Adds a child collision mesh named '<name>-convcolonly' (Godot creates a ConvexPolygonShape3D on import)."""
    _ensure_object_mode()
    out = []
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in _meshes(objs):
        if _is_rigged(ob):
            out.append(f"{ob.name}: skipped (rigged meshes use per-bone colliders in-engine)")
            continue
        e = ob.evaluated_get(dg)
        me = e.to_mesh()
        pts = [v.co.copy() for v in me.vertices]
        e.to_mesh_clear()
        bm = bmesh.new()
        if kind == 'BOX':
            mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            ret = bmesh.ops.create_cube(bm, size=1.0)
            for v in ret['verts']:
                v.co = Vector(((mn.x + mx.x) / 2 + v.co.x * (mx.x - mn.x), (mn.y + mx.y) / 2 + v.co.y * (mx.y - mn.y),
                               (mn.z + mx.z) / 2 + v.co.z * (mx.z - mn.z)))
        else:
            for p in pts:
                bm.verts.new(p)
            bmesh.ops.convex_hull(bm, input=bm.verts[:])
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
            if len(bm.faces) > 250:   # keep hulls cheap
                bmesh.ops.dissolve_limit(bm, angle_limit=0.35, verts=bm.verts[:], edges=bm.edges[:])
                bmesh.ops.triangulate(bm, faces=bm.faces[:])
        name = f"{ob.name}-convcolonly"
        old = bpy.data.objects.get(name)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        cm = bpy.data.meshes.new(name)
        bm.to_mesh(cm)
        bm.free()
        co = bpy.data.objects.new(name, cm)
        for c in ob.users_collection:
            c.objects.link(co)
        co.parent = ob
        co.display_type = 'WIRE'
        co.hide_render = True
        out.append(f"{name}: {len(cm.polygons)} faces")
    return out


def report(objs, budget=50000):
    """Per-asset triangle totals (asset = top-level parent, e.g. a character rig) plus per-mesh issues."""
    assets = {}
    for ob in _meshes(objs):
        root = ob
        while root.parent is not None:
            root = root.parent
        assets.setdefault(_asset_name(root), []).append(ob)
    head, lines = [], []
    for name in sorted(assets):
        total, mats = 0, set()
        for ob in assets[name]:
            t = tri_count(ob)
            total += t
            me = ob.data
            mats.update(m.name for m in me.materials if m and m.name != 'GAF_Outline')
            issues = []
            if not me.uv_layers:
                issues.append("no UVs")
            if not me.materials:
                issues.append("no material")
            if not _is_rigged(ob) and ob.scale != Vector((1, 1, 1)):
                issues.append("unapplied scale")
            bm = bmesh.new()
            bm.from_mesh(me)
            nm = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
            bm.free()
            if nm:
                issues.append(f"{nm} non-manifold edges")
            if issues:
                lines.append(f"   {ob.name}: {'; '.join(issues)}")
        flag = "OK" if total <= budget else "OVER BUDGET"
        head.append(f"{name}: {total:,} tris, {len(mats)} materials, {len(assets[name])} meshes  [{flag}]")
    if not head:
        return ["Nothing selected"]
    return head + (["Issues:"] + lines if lines else ["No issues found"])


def default_export_dir():
    if bpy.data.filepath:
        return bpy.path.abspath("//exports")
    return os.path.join(os.path.expanduser("~"), "Documents", "GameAssetForge")


def _descendants(ob):
    out = [ob]
    for c in ob.children:
        out += _descendants(c)
    return out


def export_assets(objs, directory="", fmt='GLB', per_asset=True, hide_outline=True, animations=False):
    _ensure_object_mode()
    directory = bpy.path.abspath(directory) if directory else default_export_dir()
    os.makedirs(directory, exist_ok=True)
    objs = [o for o in objs if o.type in ('MESH', 'ARMATURE', 'EMPTY')]
    # pull in children (meshes under a rig, collision children)
    full = set()
    for o in objs:
        full.update(_descendants(o))
    roots = [o for o in full if o.parent not in full]
    groups = [(_asset_name(r), _descendants(r)) for r in roots] if per_asset else [("assets", list(full))]
    outlines = [o.modifiers['Outline'] for o in full if o.type == 'MESH' and 'Outline' in o.modifiers]
    states = [(m, m.show_viewport, m.show_render) for m in outlines]
    if hide_outline:
        for m in outlines:
            m.show_viewport = False
            m.show_render = False
    vl = bpy.context.view_layer
    prev_sel = list(bpy.context.selected_objects)
    prev_active = vl.objects.active
    hidden = [o for o in full if o.hide_get()]
    written = []
    try:
        for name, members in groups:
            for o in vl.objects:
                o.select_set(False)
            for o in members:
                if o.name.endswith('_LOD1') or o.name.endswith('_LOD2'):
                    continue
                o.hide_set(False)
                o.select_set(True)
            vl.objects.active = members[0]
            if fmt == 'FBX':
                path = os.path.join(directory, name + ".fbx")
                bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH', 'EMPTY'},
                                         use_mesh_modifiers=True, mesh_smooth_type='FACE', add_leaf_bones=False,
                                         bake_anim=animations, apply_scale_options='FBX_SCALE_ALL',
                                         path_mode='COPY', embed_textures=True)
            else:
                ext = ".glb" if fmt == 'GLB' else ".gltf"
                path = os.path.join(directory, name + ext)
                bpy.ops.export_scene.gltf(filepath=path, export_format='GLB' if fmt == 'GLB' else 'GLTF_SEPARATE',
                                          use_selection=True, export_apply=True, export_animations=animations,
                                          export_skins=True, export_yup=True)
            written.append(path)
    finally:
        for m, v, r in states:
            m.show_viewport, m.show_render = v, r
        for o in hidden:
            o.hide_set(True)
        for o in vl.objects:
            o.select_set(o in prev_sel)
        vl.objects.active = prev_active
    return written


def _asset_name(root):
    n = root.name
    return n[:-4] if n.endswith('_Rig') else n
