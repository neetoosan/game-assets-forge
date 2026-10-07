# Game Asset Forge — generate game-ready anime characters and props, then clean & export them.
# Sidebar: 3D Viewport > N panel > "Game Forge".
import json
import random
import bpy
from bpy.props import (StringProperty, IntProperty, FloatProperty, BoolProperty, EnumProperty,
                       FloatVectorProperty, PointerProperty)

from . import core, character, props, pipeline

bl_info = {
    "name": "Game Asset Forge",
    "author": "tobii + Claude",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Game Forge",
    "description": "Generate rigged anime characters and props, make them game-ready, export GLB/FBX",
    "category": "Add Mesh",
}

D = character.DEFAULTS


def _col(name, default):
    return FloatVectorProperty(name=name, subtype='COLOR_GAMMA', size=3, min=0, max=1, default=default)


def _apply_preset(self, context):
    vals = dict(character.DEFAULTS)
    vals.update(character.PRESETS.get(self.preset, {}))
    for k, v in vals.items():
        if hasattr(self, k):
            setattr(self, k, v)


class GAF_CharSettings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Preset", update=_apply_preset, items=[
        ('KILLUA', "Silver Spiky", "Killua-style: silver spiky hair, layered tee, striped shorts"),
        ('WILD', "Wild Spikes", "Black upward spikes, green tee and shorts"),
        ('LONG', "Long Hair", "Long hair, long sleeves, pants"),
        ('CASUAL', "Casual Short", "Short hair, white tee, jeans"),
        ('MESSY', "Messy Blond", "Messy blond hair, dark long sleeves, orange pants"),
    ])
    name: StringProperty(name="Name", default="Killua")
    seed: IntProperty(name="Seed", default=D['seed'], min=0)
    height: FloatProperty(name="Height (m)", default=D['height'], min=0.8, max=2.4, step=5)
    head_size: FloatProperty(name="Head Size", default=D['head_size'], min=0.75, max=1.5)
    body_width: FloatProperty(name="Body Width", default=D['body_width'], min=0.8, max=1.3)
    skin_color: _col("Skin", D['skin_color'])
    eye_color: _col("Eyes", D['eye_color'])
    eye_shape: EnumProperty(name="Eye Shape", default=D['eye_shape'], items=[
        ('SHARP', "Sharp", "Narrow cat-like eyes"), ('ROUND', "Round", "Big round eyes")])
    mouth: EnumProperty(name="Mouth", default=D['mouth'], items=[
        ('SMILE', "Smile", ""), ('GRIN', "Grin", ""), ('NEUTRAL', "Neutral", "")])
    hair_style: EnumProperty(name="Hair Style", default=D['hair_style'], items=[
        ('SPIKY', "Spiky", "Fluffy spikes in every direction"), ('UPWARD', "Upward", "Tall spikes pointing up"),
        ('MESSY', "Messy", "Drooping messy clumps"), ('SHORT', "Short", "Short tidy hair"),
        ('LONG', "Long", "Long locks down the back")])
    hair_color: _col("Hair", D['hair_color'])
    hair_shadow: _col("Hair Shade", D['hair_shadow'])
    hair_amount: FloatProperty(name="Hair Density", default=1.0, min=0.5, max=1.5)
    top_style: EnumProperty(name="Top", default=D['top_style'], items=[
        ('LAYERED', "Tee + Turtleneck", "T-shirt over a long-sleeve turtleneck"),
        ('TSHIRT', "T-Shirt", "Short sleeves, bare arms"), ('LONGSLEEVE', "Long Sleeve", "Long-sleeve top")])
    top_color: _col("Top", D['top_color'])
    under_color: _col("Undershirt", D['under_color'])
    vneck: BoolProperty(name="V-Neck", default=True)
    bottom_style: EnumProperty(name="Bottom", default=D['bottom_style'], items=[
        ('SHORTS', "Shorts", ""), ('PANTS', "Pants", "")])
    bottom_color: _col("Bottom", D['bottom_color'])
    stripes: BoolProperty(name="Side Stripes", default=True)
    stripe_color: _col("Stripes", D['stripe_color'])
    shoe_color: _col("Shoes", D['shoe_color'])
    sole_color: _col("Soles", D['sole_color'])
    sock_color: _col("Socks", D['sock_color'])
    high_tops: BoolProperty(name="High-Top Shoes", default=True)
    outline: BoolProperty(name="Anime Outline", default=True)
    outline_width: FloatProperty(name="Outline Width", default=1.0, min=0.2, max=3.0)
    subdiv: IntProperty(name="Smoothness", default=1, min=0, max=2,
                        description="0 = low poly (~12k tris), 1 = detailed (~45k tris)")
    hair_decimate: FloatProperty(name="Hair Detail", default=0.45, min=0.1, max=1.0)
    rig: BoolProperty(name="Rig + Skin Weights", default=True)

    def as_kwargs(self):
        kw = {}
        for k in character.DEFAULTS:
            v = getattr(self, k)
            kw[k] = tuple(v) if hasattr(v, '__len__') and not isinstance(v, str) else v
        return kw


class GAF_PropSettings(bpy.types.PropertyGroup):
    kind: EnumProperty(name="Prop", items=props.PROP_TYPES)
    seed: IntProperty(name="Seed", default=1, min=0)
    random_seed: BoolProperty(name="Random Seed", default=True, description="Pick a new seed each click")
    size: FloatProperty(name="Size", default=1.0, min=0.1, max=10.0)
    count: IntProperty(name="Count", default=1, min=1, max=50, description="Make several variations in a row")
    tree_kind: EnumProperty(name="Tree", items=[('ROUND', "Round", ""), ('PINE', "Pine", "")])
    fence_segments: IntProperty(name="Segments", default=3, min=1, max=20)
    outline: BoolProperty(name="Anime Outline", default=False)


class GAF_PipeSettings(bpy.types.PropertyGroup):
    merge: BoolProperty(name="Merge Duplicates", default=True)
    fix_normals: BoolProperty(name="Fix Normals", default=True)
    delete_loose: BoolProperty(name="Remove Loose", default=True)
    ensure_uv: BoolProperty(name="Auto UV if missing", default=True)
    apply_xform: BoolProperty(name="Apply Rot/Scale", default=True)
    triangulate: BoolProperty(name="Triangulate", default=False)
    origin_bottom: BoolProperty(name="Origin to Bottom", default=False)
    lod1: FloatProperty(name="LOD1", default=0.5, min=0.05, max=1.0)
    lod2: FloatProperty(name="LOD2", default=0.25, min=0.02, max=1.0)
    collision: EnumProperty(name="Collision", items=[('CONVEX', "Convex Hull", ""), ('BOX', "Box", "")])
    budget: IntProperty(name="Tri Budget", default=50000, min=100)
    scope: EnumProperty(name="Export", items=[
        ('SELECTED', "Selected", "Selected objects (plus their children)"),
        ('FORGE', "All Forge Assets", "Every generated character and prop")])
    fmt: EnumProperty(name="Format", items=[('GLB', "GLB (Godot/web)", ""), ('GLTF', "glTF + files", ""),
                                            ('FBX', "FBX", "")])
    directory: StringProperty(name="Folder", subtype='DIR_PATH', default="",
                              description="Empty = //exports next to the .blend, or Documents/GameAssetForge")
    per_asset: BoolProperty(name="One File per Asset", default=True)
    hide_outline: BoolProperty(name="Skip Outline Mesh", default=True,
                               description="Do not bake the inverted-hull outline into exported meshes")
    animations: BoolProperty(name="Include Animations", default=False)
    last_report: StringProperty(default="[]")


# ---------------------------------------------------------------- operators
def _targets(context, scope='SELECTED'):
    if scope == 'FORGE':
        out = []
        for ob in context.scene.objects:
            if ob.get('gaf_prop') or ob.get('gaf_part') or (ob.type == 'ARMATURE' and ob.name.endswith('_Rig')):
                out.append(ob)
        return out
    objs = set(context.selected_objects)
    for o in list(objs):          # selecting a rig means its meshes too
        if o.type == 'ARMATURE':
            objs.update(o.children_recursive)
    return list(objs)


def _store(context, lines):
    context.scene.gaf_pipe.last_report = json.dumps(lines[:60])


class GAF_OT_character(bpy.types.Operator):
    bl_idname = "gaf.character"
    bl_label = "Generate Character"
    bl_description = "Build (or rebuild) a rigged, game-ready anime character at the 3D cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.gaf_char
        rig, b = character.build_character(**s.as_kwargs())
        tris = sum(core.tri_count(o) for o in b.parts.values())
        msg = f"{s.name}: {len(b.parts)} meshes, {tris:,} tris" + (f", {len(rig.data.bones)} bones" if rig else "")
        _store(context, [msg])
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class GAF_OT_char_randomize(bpy.types.Operator):
    bl_idname = "gaf.char_randomize"
    bl_label = "Randomize Look"
    bl_description = "Roll random hair, eyes, outfit and colors (then click Generate)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.gaf_char
        r = random.Random()
        hsv = lambda h, sat, v: __import__('colorsys').hsv_to_rgb(h, sat, v)
        s.seed = r.randint(0, 9999)
        s.hair_style = r.choice(['SPIKY', 'UPWARD', 'MESSY', 'SHORT', 'LONG'])
        hc = r.choice([(0.92, 0.92, 0.95), (0.10, 0.10, 0.12), (0.45, 0.26, 0.16), (0.95, 0.78, 0.35),
                       hsv(r.random(), 0.6, 0.85), (0.85, 0.30, 0.25)])
        s.hair_color = hc
        s.hair_shadow = tuple(c * 0.6 for c in hc)
        s.eye_color = hsv(r.random(), 0.65, 0.8)
        s.eye_shape = r.choice(['SHARP', 'ROUND'])
        s.mouth = r.choice(['SMILE', 'GRIN', 'NEUTRAL'])
        s.skin_color = r.choice([(0.97, 0.86, 0.82), (0.95, 0.80, 0.70), (0.80, 0.60, 0.45), (0.55, 0.38, 0.28)])
        s.top_style = r.choice(['LAYERED', 'TSHIRT', 'LONGSLEEVE'])
        s.top_color = hsv(r.random(), r.uniform(0.1, 0.7), r.uniform(0.5, 0.95))
        s.under_color = hsv(r.random(), 0.6, r.uniform(0.15, 0.4))
        s.vneck = r.random() < 0.5
        s.bottom_style = r.choice(['SHORTS', 'PANTS'])
        s.bottom_color = hsv(r.random(), r.uniform(0.2, 0.6), r.uniform(0.2, 0.6))
        s.stripes = r.random() < 0.5
        s.shoe_color = hsv(r.random(), 0.6, r.uniform(0.3, 0.8))
        s.high_tops = r.random() < 0.6
        s.height = round(r.uniform(1.4, 1.75), 2)
        s.body_width = round(r.uniform(0.9, 1.1), 2)
        return {'FINISHED'}


class GAF_OT_test_pose(bpy.types.Operator):
    bl_idname = "gaf.test_pose"
    bl_label = "Toggle Test Pose"
    bl_description = "Pose the selected Forge rig (arms down, knee bent, head turned) to check deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import math
        from mathutils import Matrix
        rig = context.active_object
        if rig is not None and rig.type != 'ARMATURE' and rig.parent and rig.parent.type == 'ARMATURE':
            rig = rig.parent
        if rig is None or rig.type != 'ARMATURE':
            self.report({'WARNING'}, "Select a character rig (or one of its meshes)")
            return {'CANCELLED'}
        pb = rig.pose.bones
        posed = any(b.matrix_basis != Matrix.Identity(4) for b in pb)
        for b in pb:
            b.matrix_basis = Matrix.Identity(4)
        context.view_layer.update()
        if not posed:
            def rot(n, axis, deg):
                if n not in pb:
                    return
                b = pb[n]
                h = b.head.copy()
                b.matrix = (Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, axis)
                            @ Matrix.Translation(-h)) @ b.matrix
                context.view_layer.update()
            rot('LeftUpperArm', 'Y', 62); rot('RightUpperArm', 'Y', -62)
            rot('LeftLowerArm', 'Z', 35); rot('RightLowerArm', 'Z', -35)
            for f in ('Index', 'Middle', 'Ring', 'Little'):
                for side, sg in (('Left', 1), ('Right', -1)):
                    for seg, a in (('Proximal', 35), ('Intermediate', 35), ('Distal', 25)):
                        rot(side + f + seg, 'Y', sg * a)
            rot('LeftUpperLeg', 'X', -35); rot('LeftLowerLeg', 'X', 60); rot('Head', 'Z', 20)
        return {'FINISHED'}


class GAF_OT_prop(bpy.types.Operator):
    bl_idname = "gaf.prop"
    bl_label = "Generate Prop"
    bl_description = "Generate seeded prop variations at the 3D cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.gaf_prop
        if s.random_seed:
            s.seed = random.randint(0, 9999)
        cur = context.scene.cursor.location.copy()
        made = []
        step = s.size * (4.2 if s.kind == 'FENCE' else 1.6)
        for i in range(s.count):
            loc = cur.copy()
            loc.x += i * step * (s.fence_segments / 3 if s.kind == 'FENCE' else 1)
            ob = props.build_prop(s.kind, s.seed + i, s.size, s.outline, s.tree_kind, s.fence_segments, loc)
            made.append(ob)
        for o in context.selected_objects:
            o.select_set(False)
        for o in made:
            o.select_set(True)
        context.view_layer.objects.active = made[-1]
        _store(context, [f"{o.name}: {core.tri_count(o):,} tris" for o in made])
        return {'FINISHED'}


class GAF_OT_prop_pack(bpy.types.Operator):
    bl_idname = "gaf.prop_pack"
    bl_label = "Generate Prop Pack"
    bl_description = "One of every prop type, laid out in a row at the 3D cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.gaf_prop
        cur = context.scene.cursor.location.copy()
        x = 0.0
        made = []
        for kind, _, _ in props.PROP_TYPES:
            seed = random.randint(0, 9999)
            loc = cur.copy()
            ob = props.build_prop(kind, seed, s.size, s.outline, random.choice(['ROUND', 'PINE']), 2, loc)
            w = ob.dimensions.x
            ob.location.x = cur.x + x + w / 2
            x += w + 0.5 * s.size
            made.append(ob)
        _store(context, [f"{o.name}: {core.tri_count(o):,} tris" for o in made])
        return {'FINISHED'}


class GAF_OT_game_ready(bpy.types.Operator):
    bl_idname = "gaf.game_ready"
    bl_label = "Make Game Ready"
    bl_description = "Clean up selected meshes: transforms, duplicates, normals, loose geometry, UVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.gaf_pipe
        log = pipeline.make_game_ready(_targets(context), p.merge, p.fix_normals, p.delete_loose, p.ensure_uv,
                                       p.apply_xform, p.triangulate, p.origin_bottom)
        _store(context, log or ["Nothing selected"])
        self.report({'INFO'}, f"Processed {len(log)} meshes")
        return {'FINISHED'}


class GAF_OT_lods(bpy.types.Operator):
    bl_idname = "gaf.lods"
    bl_label = "Generate LODs"
    bl_description = "Decimated LOD copies (hidden). Note: Godot can also auto-generate LODs on import"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.gaf_pipe
        _store(context, pipeline.generate_lods(_targets(context), (p.lod1, p.lod2)) or ["Nothing selected"])
        return {'FINISHED'}


class GAF_OT_collision(bpy.types.Operator):
    bl_idname = "gaf.collision"
    bl_label = "Add Collision"
    bl_description = "Child collision mesh named '-convcolonly' — Godot turns it into a physics shape on import"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.gaf_pipe
        _store(context, pipeline.add_collision(_targets(context), p.collision) or ["Nothing selected"])
        return {'FINISHED'}


class GAF_OT_report(bpy.types.Operator):
    bl_idname = "gaf.report"
    bl_label = "Check Assets"
    bl_description = "Triangle count, materials, UVs and problems for the selection"

    def execute(self, context):
        p = context.scene.gaf_pipe
        _store(context, pipeline.report(_targets(context, p.scope), p.budget))
        return {'FINISHED'}


class GAF_OT_export(bpy.types.Operator):
    bl_idname = "gaf.export"
    bl_label = "Export"
    bl_description = "Export game assets (modifiers applied, skinning + materials included)"

    def execute(self, context):
        p = context.scene.gaf_pipe
        objs = _targets(context, p.scope)
        if not objs:
            self.report({'WARNING'}, "Nothing to export")
            return {'CANCELLED'}
        files = pipeline.export_assets(objs, p.directory, p.fmt, p.per_asset, p.hide_outline, p.animations)
        _store(context, [f"wrote {f}" for f in files])
        self.report({'INFO'}, f"Exported {len(files)} file(s)")
        return {'FINISHED'}


# ---------------------------------------------------------------- panels
class _Panel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Game Forge"


class GAF_PT_character(_Panel, bpy.types.Panel):
    bl_label = "Anime Character"

    def draw(self, context):
        s = context.scene.gaf_char
        L = self.layout
        L.prop(s, "preset")
        row = L.row(align=True)
        row.prop(s, "name")
        row.prop(s, "seed")
        b = L.box()
        b.label(text="Body & Face", icon='USER')
        b.prop(s, "height"); b.prop(s, "head_size"); b.prop(s, "body_width")
        r = b.row(); r.prop(s, "skin_color"); r.prop(s, "eye_color")
        r = b.row(); r.prop(s, "eye_shape", text=""); r.prop(s, "mouth", text="")
        b = L.box()
        b.label(text="Hair", icon='OUTLINER_OB_CURVES')
        b.prop(s, "hair_style")
        r = b.row(); r.prop(s, "hair_color"); r.prop(s, "hair_shadow")
        b.prop(s, "hair_amount")
        b = L.box()
        b.label(text="Outfit", icon='MATCLOTH')
        b.prop(s, "top_style")
        r = b.row(); r.prop(s, "top_color")
        if s.top_style == 'LAYERED':
            r.prop(s, "under_color")
        b.prop(s, "vneck")
        b.prop(s, "bottom_style")
        r = b.row(); r.prop(s, "bottom_color"); r.prop(s, "stripes")
        if s.stripes:
            b.prop(s, "stripe_color")
        r = b.row(); r.prop(s, "shoe_color"); r.prop(s, "sole_color")
        r = b.row(); r.prop(s, "sock_color"); r.prop(s, "high_tops")
        b = L.box()
        b.label(text="Game Settings", icon='SETTINGS')
        b.prop(s, "subdiv"); b.prop(s, "hair_decimate")
        r = b.row(); r.prop(s, "outline"); r.prop(s, "outline_width", text="Width")
        b.prop(s, "rig")
        r = L.row(align=True)
        r.scale_y = 1.4
        r.operator("gaf.character", icon='OUTLINER_OB_ARMATURE')
        r.operator("gaf.char_randomize", text="", icon='FILE_REFRESH')
        L.operator("gaf.test_pose", icon='POSE_HLT')


class GAF_PT_props(_Panel, bpy.types.Panel):
    bl_label = "Props"

    def draw(self, context):
        s = context.scene.gaf_prop
        L = self.layout
        L.prop(s, "kind")
        if s.kind == 'TREE':
            L.prop(s, "tree_kind")
        if s.kind == 'FENCE':
            L.prop(s, "fence_segments")
        r = L.row(align=True); r.prop(s, "seed"); r.prop(s, "random_seed", text="", icon='FILE_REFRESH')
        r = L.row(align=True); r.prop(s, "size"); r.prop(s, "count")
        L.prop(s, "outline")
        r = L.row(align=True)
        r.scale_y = 1.3
        r.operator("gaf.prop", icon='MESH_CUBE')
        r.operator("gaf.prop_pack", text="Pack", icon='PACKAGE')


class GAF_PT_pipeline(_Panel, bpy.types.Panel):
    bl_label = "Game-Ready & Export"

    def draw(self, context):
        p = context.scene.gaf_pipe
        L = self.layout
        b = L.box()
        b.label(text="Clean Up (selected)", icon='BRUSH_DATA')
        g = b.grid_flow(columns=2, align=True)
        for k in ("merge", "fix_normals", "delete_loose", "ensure_uv", "apply_xform", "triangulate", "origin_bottom"):
            g.prop(p, k)
        b.operator("gaf.game_ready", icon='CHECKMARK')
        r = b.row(align=True); r.prop(p, "lod1"); r.prop(p, "lod2")
        b.operator("gaf.lods", icon='MOD_DECIM')
        r = b.row(align=True); r.prop(p, "collision", text=""); r.operator("gaf.collision", icon='MOD_PHYSICS')
        b = L.box()
        b.label(text="Check & Export", icon='EXPORT')
        b.prop(p, "scope")
        r = b.row(align=True); r.prop(p, "budget"); r.operator("gaf.report", text="Check", icon='VIEWZOOM')
        b.prop(p, "fmt")
        b.prop(p, "directory")
        g = b.grid_flow(columns=2, align=True)
        g.prop(p, "per_asset"); g.prop(p, "hide_outline"); g.prop(p, "animations")
        r = b.row(); r.scale_y = 1.3
        r.operator("gaf.export", icon='EXPORT')
        try:
            lines = json.loads(p.last_report)
        except Exception:
            lines = []
        if lines:
            b = L.box()
            for ln in lines[:25]:
                b.label(text=ln)


CLASSES = (GAF_CharSettings, GAF_PropSettings, GAF_PipeSettings,
           GAF_OT_character, GAF_OT_char_randomize, GAF_OT_test_pose, GAF_OT_prop, GAF_OT_prop_pack,
           GAF_OT_game_ready, GAF_OT_lods, GAF_OT_collision, GAF_OT_report, GAF_OT_export,
           GAF_PT_character, GAF_PT_props, GAF_PT_pipeline)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.gaf_char = PointerProperty(type=GAF_CharSettings)
    bpy.types.Scene.gaf_prop = PointerProperty(type=GAF_PropSettings)
    bpy.types.Scene.gaf_pipe = PointerProperty(type=GAF_PipeSettings)


def unregister():
    del bpy.types.Scene.gaf_char
    del bpy.types.Scene.gaf_prop
    del bpy.types.Scene.gaf_pipe
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
