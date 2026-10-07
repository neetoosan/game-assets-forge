# Seeded game-prop generators. Each returns ONE mesh object (origin at its base) with UVs + materials.
import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix, Euler, noise
from .core import (TAU, make_mat, add_outline, get_col, bm_to_obj, loft, angles_uniform, add_box, box_uv,
                   strand, spike, merge_bm)

PROP_TYPES = [
    ('CRATE', "Crate", "Wooden crate with frame planks"),
    ('BARREL', "Barrel", "Wooden barrel with metal hoops"),
    ('ROCK', "Rock", "Low-poly rock, optional moss"),
    ('TREE', "Tree", "Stylized tree (round or pine)"),
    ('FENCE', "Fence", "Wooden fence section"),
    ('CHEST', "Treasure Chest", "Chest with metal bands and lock"),
    ('SWORD', "Sword", "One-handed sword (origin at the grip)"),
    ('POTION', "Potion", "Glass flask with liquid and cork"),
]


def _jit(rng, c, a=0.06):
    return tuple(min(1, max(0, x + rng.uniform(-a, a))) for x in c)


def _wood(rng, pre, dark=False):
    base = (0.55, 0.36, 0.20) if not dark else (0.36, 0.22, 0.12)
    return make_mat(pre + ('WoodDark' if dark else 'Wood'), _jit(rng, base, 0.05), 0.85)


def _metal(pre, gold=False):
    if gold:
        return make_mat(pre + 'Gold', (0.95, 0.72, 0.25), 0.35, 0.5, metal=1.0)
    return make_mat(pre + 'Iron', (0.42, 0.43, 0.46), 0.45, 0.5, metal=0.9)


def crate(rng, size, pre):
    s = size
    bm = bmesh.new()
    t = 0.11 * s
    add_box(bm, (0, 0, s / 2), (s * 0.94, s * 0.94, s * 0.94), mat=1)
    h = s / 2
    for ax in range(3):
        for a in (-1, 1):
            for b in (-1, 1):
                c = [0, 0, 0]
                dims = [t, t, t]
                dims[ax] = s if ax == 2 else s - 2 * t * 0.98   # horizontal planks butt into the posts
                o = [i for i in range(3) if i != ax]
                c[o[0]] = a * (h - t / 2)
                c[o[1]] = b * (h - t / 2)
                c[2] += h
                add_box(bm, c, dims, mat=0)
    # diagonal braces on the four sides
    diag = math.sqrt(2) * (s - 2 * t)
    for (n, rz) in ((Vector((0, -1, 0)), 0), (Vector((0, 1, 0)), 0), (Vector((1, 0, 0)), math.pi / 2), (Vector((-1, 0, 0)), math.pi / 2)):
        if rng.random() < 0.8:
            sgn = rng.choice((-1, 1))
            R = Euler((0, sgn * math.pi / 4, rz)).to_matrix()
            add_box(bm, n * (h + 0.01 * s) + Vector((0, 0, h)), (diag * 0.98, t * 0.6, t * 0.8), rot=R, mat=0)
    return bm, [_wood(rng, pre), _wood(rng, pre, dark=True)], False


def barrel(rng, size, pre):
    hgt, r0 = 1.0 * size, 0.36 * size
    bm = bmesh.new()
    n = 20
    secs = []
    for i in range(9):
        z = hgt * i / 8
        r = r0 * (1 + 0.14 * math.sin(math.pi * i / 8))
        secs.append(((0, 0, z), r, r, r, r, 2.0))
    loft(bm, secs, angles_uniform(n), tip0=(0, 0, 0), tip1=(0, 0, hgt - 0.04 * size),
         mat_fn=lambda i, j, th: j % 2)
    for f in bm.faces:            # lids: solid dark wood instead of a stave pinwheel
        if len(f.verts) == 3:
            f.material_index = 1
    for zf in (0.1, 0.32, 0.68, 0.9):
        z = hgt * zf
        r = r0 * (1 + 0.14 * math.sin(math.pi * zf)) + 0.008 * size
        hb = bmesh.new()
        loft(hb, [((0, 0, z - 0.025 * size), r, r, r, r, 2.0), ((0, 0, z + 0.025 * size), r, r, r, r, 2.0)],
             angles_uniform(n), cap0=False, cap1=False, mat_fn=lambda i, j, th: 2)
        # give hoops thickness by an inner ring
        merge_bm(bm, hb)
    return bm, [_wood(rng, pre), _wood(rng, pre, dark=True), _metal(pre)], True


def rock(rng, size, pre):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    off = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
    sc = Vector((rng.uniform(0.9, 1.3), rng.uniform(0.8, 1.1), rng.uniform(0.55, 0.8))) * size
    for v in bm.verts:
        d = noise.noise(v.co * 2.2 + off) * 0.22 + noise.noise(v.co * 5.0 + off) * 0.06
        v.co = v.co * (1 + d)
        v.co = Vector((v.co.x * sc.x, v.co.y * sc.y, v.co.z * sc.z))
    zmin = min(v.co.z for v in bm.verts)
    cut = zmin + 0.18 * sc.z
    for v in bm.verts:
        if v.co.z < cut:
            v.co.z = cut
        v.co.z -= cut
    bm.normal_update()
    mats = [make_mat(pre + 'Stone', _jit(rng, (0.48, 0.47, 0.50), 0.05), 0.9)]
    if rng.random() < 0.6:
        mats.append(make_mat(pre + 'Moss', _jit(rng, (0.33, 0.50, 0.22), 0.04), 0.95))
        for f in bm.faces:
            if f.normal.z > 0.75 and f.calc_center_median().z > 0.4 * sc.z:
                f.material_index = 1
    box_uv(bm)
    return bm, mats, False


def tree(rng, size, pre, kind='ROUND'):
    bm = bmesh.new()
    h = 2.6 * size
    th = 0.42 * h if kind == 'ROUND' else 0.25 * h
    bx, by = rng.uniform(-0.05, 0.05) * size, rng.uniform(-0.05, 0.05) * size
    secs = []
    for i in range(6):
        t = i / 5
        r = (0.11 - 0.05 * t) * size * (1.5 if i == 0 else 1.0)
        secs.append(((bx * t * t, by * t * t, th * t * 1.05), r, r, r, r, 2.0))
    loft(bm, secs, angles_uniform(10), cap0=True, cap1=True, mat_fn=lambda i, j, a: 0)
    top = Vector((bx, by, th))
    if kind == 'ROUND':
        for k in range(rng.randint(4, 6)):
            fb = bmesh.new()
            r = rng.uniform(0.38, 0.55) * size
            bmesh.ops.create_icosphere(fb, subdivisions=2, radius=r)
            off = Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), rng.uniform(0.2, 0.75))) * size
            if k == 0:
                off = Vector((0, 0, 0.55 * size))
            o = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
            for v in fb.verts:
                v.co = v.co * (1 + noise.noise(v.co * 3 / size + o) * 0.18) + top + off
            for f in fb.faces:
                f.material_index = 1 if rng.random() < 0.7 else 2
            merge_bm(bm, fb)
    else:
        tiers = rng.randint(3, 4)
        for k in range(tiers):
            t = k / tiers
            z0 = th + (h - th) * t * 0.8
            r = (0.75 - 0.5 * t) * size
            hh = (h - th) / tiers * 1.7
            ring = 14
            fb = bmesh.new()
            # jagged skirt: alternating radius
            angs = angles_uniform(ring)
            vs_out = [fb.verts.new((math.cos(a) * r * (1 if i % 2 == 0 else 0.8), math.sin(a) * r * (1 if i % 2 == 0 else 0.8),
                                    z0 - (0.06 * size if i % 2 == 0 else 0))) for i, a in enumerate(angs)]
            tip = fb.verts.new((bx, by, z0 + hh))
            bot = fb.verts.new((bx, by, z0 + 0.05 * size))
            for i in range(ring):
                a, b = vs_out[i], vs_out[(i + 1) % ring]
                fb.faces.new((a, b, tip)).material_index = 1 if k % 2 == 0 else 2
                fb.faces.new((b, a, bot)).material_index = 2
            merge_bm(bm, fb)
    box_uv(bm)
    mats = [_wood(rng, pre, dark=True),
            make_mat(pre + 'Leaf', _jit(rng, (0.30, 0.62, 0.25) if kind == 'ROUND' else (0.16, 0.42, 0.26), 0.05), 0.9),
            make_mat(pre + 'LeafDark', _jit(rng, (0.20, 0.45, 0.18) if kind == 'ROUND' else (0.10, 0.30, 0.20), 0.04), 0.9)]
    return bm, mats, kind == 'ROUND'


def fence(rng, size, pre, segments=3):
    bm = bmesh.new()
    span = 1.2 * size
    ph, pw = 1.0 * size, 0.1 * size
    for i in range(segments + 1):
        x = (i - segments / 2) * span
        tilt = Euler((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0)).to_matrix()
        add_box(bm, (x, 0, ph / 2), (pw, pw, ph), rot=tilt, mat=0)
        # pointed cap
        c = Vector((x, 0, ph))
        vs = [bm.verts.new(c + Vector((sx * pw / 2, sy * pw / 2, 0))) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        tp = bm.verts.new(c + Vector((0, 0, pw * 0.9)))
        for k in range(4):
            bm.faces.new((vs[k], vs[(k + 1) % 4], tp)).material_index = 0
    for i in range(segments):
        x = (i + 0.5 - segments / 2) * span
        for z in (0.35, 0.75):
            R = Euler((0, rng.uniform(-0.03, 0.03), 0)).to_matrix()
            add_box(bm, (x, -pw * 0.65, z * ph), (span * 1.02, pw * 0.35, pw * 0.9), rot=R, mat=1)
    box_uv(bm)
    return bm, [_wood(rng, pre, dark=True), _wood(rng, pre)], False


def chest(rng, size, pre):
    w, d, h = 0.8 * size, 0.5 * size, 0.38 * size
    bm = bmesh.new()
    add_box(bm, (0, 0, h / 2), (w, d, h), mat=0)
    # lid: half cylinder along X
    r = d / 2
    lb = bmesh.new()
    loft(lb, [((-w / 2, 0, h), r, r, r * 0.9, 0.0001, 2.0), ((w / 2, 0, h), r, r, r * 0.9, 0.0001, 2.0)],
         angles_uniform(16), 'Y', 'Z', mat_fn=lambda i, j, a: 0)
    merge_bm(bm, lb)
    # metal bands
    for x in (-w * 0.32, w * 0.32):
        add_box(bm, (x, 0, h / 2), (0.06 * size, d * 1.03, h * 1.02), mat=1)
        bb = bmesh.new()
        rr = r * 1.04
        loft(bb, [((x - 0.03 * size, 0, h), rr, rr, rr * 0.9, 0.0001, 2.0), ((x + 0.03 * size, 0, h), rr, rr, rr * 0.9, 0.0001, 2.0)],
             angles_uniform(16), 'Y', 'Z', mat_fn=lambda i, j, a: 1)
        merge_bm(bm, bb)
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_box(bm, (sx * (w / 2 - 0.02 * size), sy * (d / 2 - 0.02 * size), h / 2), (0.07 * size, 0.07 * size, h * 1.02), mat=1)
    # lock
    add_box(bm, (0, -d / 2 - 0.015 * size, h * 0.95), (0.1 * size, 0.04 * size, 0.13 * size), mat=2)
    box_uv(bm)
    gold = rng.random() < 0.5
    return bm, [_wood(rng, pre), _metal(pre, gold=gold), _metal(pre, gold=True)], False


def sword(rng, size, pre):
    L = rng.uniform(0.75, 0.95) * size
    bw = rng.uniform(0.045, 0.06) * size
    bm = bmesh.new()
    # blade (diamond cross-section via superellipse power 1), from guard up
    secs = []
    for i in range(6):
        t = i / 5
        w = bw * (1 - 0.25 * t) * (0.5 if i == 5 else 1)
        z = 0.1 * size + L * t * (0.92 if i == 5 else 1)
        secs.append(((0, 0, z), w, w, 0.007 * size, 0.007 * size, 1.0))
    loft(bm, secs, angles_uniform(8), tip1=(0, 0, 0.1 * size + L + 0.06 * size), mat_fn=lambda i, j, a: 0)
    gw = rng.uniform(0.2, 0.28) * size
    add_box(bm, (0, 0, 0.09 * size), (gw, 0.04 * size, 0.035 * size), mat=1)
    for sx in (-1, 1):
        add_box(bm, (sx * gw / 2, 0, 0.09 * size), (0.04 * size, 0.05 * size, 0.05 * size), mat=1)
    gb = bmesh.new()
    loft(gb, [((0, 0, z), 0.018 * size, 0.018 * size, 0.018 * size, 0.018 * size, 2.0)
              for z in (-0.10 * size, -0.03 * size, 0.07 * size)], angles_uniform(10), mat_fn=lambda i, j, a: 2)
    merge_bm(bm, gb)
    pb = bmesh.new()
    bmesh.ops.create_icosphere(pb, subdivisions=1, radius=0.032 * size)
    bmesh.ops.translate(pb, verts=pb.verts, vec=(0, 0, -0.12 * size))
    for f in pb.faces:
        f.material_index = 1
    merge_bm(bm, pb)
    box_uv(bm, scale=4)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.12 * size + 0.032 * size))   # base at z=0
    return bm, [make_mat(pre + 'Steel', (0.80, 0.82, 0.86), 0.25, 0.5, metal=1.0), _metal(pre, gold=rng.random() < 0.5),
                make_mat(pre + 'Leather', _jit(rng, (0.35, 0.18, 0.12), 0.05), 0.8)], False


def potion(rng, size, pre):
    bm = bmesh.new()
    s = size * 0.25
    prof = [(0.00, 0.30), (0.05, 0.42), (0.25, 0.50), (0.45, 0.42), (0.58, 0.18), (0.80, 0.16), (0.86, 0.20)]
    loft(bm, [((0, 0, z * s * 2), r * s, r * s, r * s, r * s, 2.0) for z, r in prof], angles_uniform(16),
         cap0=True, cap1=False, mat_fn=lambda i, j, a: 0)
    fill = rng.uniform(0.35, 0.5)
    lb = bmesh.new()
    lp = [(z, r * 0.9) for z, r in prof if z <= fill] + [(fill, 0.46 * 0.9)]
    loft(lb, [((0, 0, max(z, 0.01) * s * 2), r * s, r * s, r * s, r * s, 2.0) for z, r in lp], angles_uniform(16),
         mat_fn=lambda i, j, a: 1)
    merge_bm(bm, lb)
    cb = bmesh.new()
    loft(cb, [((0, 0, z * s * 2), 0.15 * s, 0.15 * s, 0.15 * s, 0.15 * s, 2.0) for z in (0.74, 0.95)],
         angles_uniform(10), mat_fn=lambda i, j, a: 2)
    merge_bm(bm, cb)
    liquid = rng.choice([(0.85, 0.15, 0.20), (0.20, 0.45, 0.95), (0.30, 0.85, 0.35), (0.70, 0.30, 0.90), (0.98, 0.75, 0.15)])
    return bm, [make_mat(pre + 'Glass', (0.80, 0.90, 0.95), 0.05, 0.5, alpha=0.35),
                make_mat(pre + 'Liquid', liquid, 0.2, 0.5, emit=0.3), make_mat(pre + 'Cork', (0.62, 0.45, 0.28), 0.9)], True


GEN = {'CRATE': crate, 'BARREL': barrel, 'ROCK': rock, 'TREE': tree, 'FENCE': fence, 'CHEST': chest,
       'SWORD': sword, 'POTION': potion}


def build_prop(kind='CRATE', seed=1, size=1.0, outline=False, tree_kind='ROUND', fence_segments=3,
               location=None, collection="Props", bevel=True):
    rng = random.Random(seed)
    pre = f"Prop_{kind.title()}_"
    if kind == 'TREE':
        bm, mats, smooth = tree(rng, size, pre, tree_kind)
    elif kind == 'FENCE':
        bm, mats, smooth = fence(rng, size, pre, fence_segments)
    else:
        bm, mats, smooth = GEN[kind](rng, size, pre)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    col = get_col(collection)
    base = f"{kind.title()}_{seed:03d}"
    name, i = base, 1
    while bpy.data.objects.get(name):
        name = f"{base}.{i:02d}"
        i += 1
    ob = bm_to_obj(bm, name, col, mats, smooth=smooth)
    if bevel and kind in ('CRATE', 'CHEST', 'FENCE'):
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width = 0.008 * size
        md.segments = 1
        md.limit_method = 'ANGLE'
        md.harden_normals = False
    if outline:
        add_outline(ob, 0.006 * size)
    ob['gaf_prop'] = kind
    ob['gaf_seed'] = seed
    ob.location = location if location is not None else bpy.context.scene.cursor.location
    return ob
