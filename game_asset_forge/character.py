# Parametric anime character generator: mesh, face texture, hair, clothes, rig, skin weights.
# Built at a 1.5 m reference size facing -Y (Blender front view), then scaled to `height`.
import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix
from .core import (TAU, lin, mix, make_mat, textured_mat, image_from_array, add_outline, get_col, clear_col,
                   bm_to_obj, add_subsurf, add_solidify, apply_modifier, merge_bm, loft, angles_uniform,
                   angles_with, mirror_bm, spike, strand, principled)

DEFAULTS = dict(
    name="Character", seed=7, height=1.5, head_size=1.0, body_width=1.0,
    skin_color=(0.969, 0.863, 0.816), eye_color=(0.30, 0.62, 0.86), eye_shape='SHARP', mouth='SMILE',
    hair_style='SPIKY', hair_color=(0.92, 0.92, 0.95), hair_shadow=(0.66, 0.62, 0.80), hair_amount=1.0,
    top_style='LAYERED', top_color=(0.866, 0.827, 0.925), under_color=(0.106, 0.118, 0.298), vneck=True,
    bottom_style='SHORTS', bottom_color=(0.294, 0.282, 0.384), stripes=True, stripe_color=(0.925, 0.918, 0.95),
    shoe_color=(0.431, 0.149, 0.192), sole_color=(0.804, 0.682, 0.675), sock_color=(0.733, 0.643, 0.690),
    high_tops=True, outline=True, outline_width=1.0, subdiv=1, hair_decimate=0.45, rig=True,
)

PRESETS = {
    'KILLUA': dict(name="Killua"),
    'WILD': dict(name="WildSpikes", seed=3, hair_style='UPWARD', hair_color=(0.10, 0.10, 0.12),
                 hair_shadow=(0.03, 0.05, 0.08), eye_color=(0.45, 0.30, 0.18), eye_shape='ROUND', mouth='GRIN',
                 skin_color=(0.95, 0.80, 0.70), top_style='TSHIRT', top_color=(0.22, 0.55, 0.30), vneck=False,
                 bottom_style='SHORTS', bottom_color=(0.20, 0.42, 0.24), stripes=False,
                 shoe_color=(0.20, 0.45, 0.25), sole_color=(0.92, 0.88, 0.78), sock_color=(0.95, 0.95, 0.95)),
    'LONG': dict(name="LongHair", seed=11, height=1.55, body_width=0.92, hair_style='LONG',
                 hair_color=(0.45, 0.26, 0.16), hair_shadow=(0.24, 0.12, 0.10), eye_color=(0.55, 0.30, 0.65),
                 eye_shape='ROUND', mouth='NEUTRAL', top_style='LONGSLEEVE', top_color=(0.75, 0.22, 0.25),
                 vneck=True, bottom_style='PANTS', bottom_color=(0.15, 0.16, 0.22), stripes=False,
                 shoe_color=(0.12, 0.12, 0.14), sole_color=(0.85, 0.85, 0.85), high_tops=False),
    'CASUAL': dict(name="Casual", seed=5, height=1.6, hair_style='SHORT', hair_color=(0.30, 0.20, 0.13),
                   hair_shadow=(0.15, 0.09, 0.07), eye_color=(0.25, 0.45, 0.30), eye_shape='ROUND',
                   mouth='SMILE', top_style='TSHIRT', top_color=(0.95, 0.95, 0.95), vneck=False,
                   bottom_style='PANTS', bottom_color=(0.22, 0.32, 0.55), stripes=False,
                   shoe_color=(0.85, 0.20, 0.18), sole_color=(0.95, 0.95, 0.95), high_tops=False),
    'MESSY': dict(name="Messy", seed=21, hair_style='MESSY', hair_color=(0.95, 0.75, 0.30),
                  hair_shadow=(0.75, 0.45, 0.20), eye_color=(0.20, 0.55, 0.75), top_style='LONGSLEEVE',
                  top_color=(0.20, 0.22, 0.28), vneck=False, bottom_style='PANTS',
                  bottom_color=(0.85, 0.55, 0.20), stripes=True, stripe_color=(0.15, 0.15, 0.18)),
}

LX = 0.084          # leg x offset at reference size
NECK_PIVOT = Vector((0, 0.012, 1.19))


def V(z, rx, ryb, ryf, yc=0.0, x=0.0, pw=2.2):
    return ((x, yc, z), rx, rx, ryb, ryf, pw)


def H(x, ryb, ryf, rzu, rzd, zc, yc=0.0, pw=2.0):
    return ((x, yc, zc), ryb, ryf, rzu, rzd, pw)


class Builder:
    def __init__(self, p):
        self.p = p
        name = p['name'] or "Character"
        # never wipe a collection the Forge didn't create: pick a free name instead
        base, i = name, 1
        while bpy.data.collections.get(name) is not None and not bpy.data.collections[name].get('gaf_char'):
            name = f"{base}_{i}"
            i += 1
        p['name'] = name
        self.name = name
        self.col = get_col(self.name)
        self.col['gaf_char'] = True
        clear_col(self.col)
        self.rng = random.Random(p['seed'])
        self.parts = {}            # part key -> object
        pre = self.name + "_"
        self.M = {
            'skin': make_mat(pre + 'Skin', p['skin_color'], 0.7),
            'top': make_mat(pre + 'Top', p['top_color'], 0.85),
            'under': make_mat(pre + 'Under', p['under_color'], 0.85),
            'bottom': make_mat(pre + 'Bottom', p['bottom_color'], 0.9),
            'stripe': make_mat(pre + 'Stripe', p['stripe_color'], 0.9),
            'shoe': make_mat(pre + 'Shoe', p['shoe_color'], 0.7),
            'sole': make_mat(pre + 'Sole', p['sole_color'], 0.8),
            'sock': make_mat(pre + 'Sock', p['sock_color'], 0.9),
        }

    def obj(self, key, bm, mats, smooth=True):
        ob = bm_to_obj(bm, f"{self.name}_{key}", self.col, mats, smooth)
        ob['gaf_part'] = key
        self.parts[key] = ob
        return ob

    def sub(self, ob):
        if self.p['subdiv'] > 0:
            add_subsurf(ob, self.p['subdiv'], self.p['subdiv'] + 1)

    # ------------------------------------------------------------ torso / top
    def build_top(self):
        p, bw = self.p, self.p['body_width']
        style = p['top_style']
        bm = bmesh.new()
        S = [(0.685, 0.156, 0.110, 0.114), (0.720, 0.152, 0.107, 0.111), (0.800, 0.146, 0.102, 0.107),
             (0.900, 0.147, 0.100, 0.109), (0.980, 0.153, 0.100, 0.110), (1.040, 0.158, 0.098, 0.104),
             (1.080, 0.150, 0.090, 0.092)]
        secs = [V(z, rx * bw, ryb * (0.5 + 0.5 * bw), ryf * (0.5 + 0.5 * bw)) for z, rx, ryb, ryf in S]
        secs += [V(1.105, 0.116 * bw, 0.076, 0.076, pw=2.0), V(1.125, 0.070, 0.062, 0.060, yc=0.004, pw=2.0),
                 V(1.138, 0.050, 0.050, 0.047, yc=0.008, pw=2.0)]
        loft(bm, secs, angles_uniform(24), cap0=False, cap1=False)
        ob = self.obj('Shirt', bm, [self.M['top']])
        add_solidify(ob, 0.006)
        self.sub(ob)

        if style in ('LAYERED', 'TSHIRT'):
            bm = bmesh.new()
            loft(bm, [H(0.095, 0.070, 0.070, 0.060, 0.060, 1.060), H(0.150, 0.066, 0.066, 0.058, 0.056, 1.072),
                      H(0.210, 0.060, 0.060, 0.052, 0.050, 1.078), H(0.268, 0.058, 0.058, 0.050, 0.048, 1.080)],
                 angles_uniform(16), 'Y', 'Z', cap0=False, cap1=False)
            mirror_bm(bm)
            ob = self.obj('Sleeves', bm, [self.M['top']])
            add_solidify(ob, 0.005)
            self.sub(ob)

        # arms: undershirt (LAYERED), bare skin (TSHIRT) or long sleeves (LONGSLEEVE)
        k = {'LAYERED': 1.0, 'TSHIRT': 0.86, 'LONGSLEEVE': 1.06}[style]
        A = [(0.110, 0.050, 1.072), (0.200, 0.042, 1.077), (0.280, 0.038, 1.078), (0.340, 0.035, 1.078),
             (0.400, 0.033, 1.078), (0.470, 0.030, 1.078), (0.508, 0.031, 1.078), (0.522, 0.029, 1.078)]
        secs = []
        for i, (x, r, z) in enumerate(A):
            kk = 1.0 if i == 0 else k
            if style == 'LONGSLEEVE' and i == 0:
                r = 0.068
            secs.append(H(x, r * kk, r * kk, r * kk * 0.97, r * kk * 0.97, z))
        bm = bmesh.new()
        loft(bm, secs, angles_uniform(16), 'Y', 'Z', cap0=False, cap1=True)
        mirror_bm(bm)
        mat = {'LAYERED': self.M['under'], 'TSHIRT': self.M['skin'], 'LONGSLEEVE': self.M['top']}[style]
        ob = self.obj('Arms', bm, [mat])
        self.sub(ob)

        if style == 'LAYERED':
            bm = bmesh.new()
            loft(bm, [V(1.070, 0.066, 0.064, 0.062, yc=0.004, pw=2.0), V(1.120, 0.060, 0.058, 0.057, yc=0.006, pw=2.0),
                      V(1.150, 0.058, 0.056, 0.055, yc=0.008, pw=2.0), V(1.166, 0.062, 0.060, 0.059, yc=0.008, pw=2.0),
                      V(1.182, 0.060, 0.058, 0.057, yc=0.009, pw=2.0), V(1.188, 0.052, 0.050, 0.049, yc=0.009, pw=2.0)],
                 angles_uniform(20), cap0=False, cap1=False)
            ob = self.obj('Turtleneck', bm, [self.M['under']])
            add_solidify(ob, 0.008)
            self.sub(ob)

        if p['vneck']:
            col = self.M['under'] if style == 'LAYERED' else self.M['skin']
            self.decal('VNeck', self.vneck_pts, 6, 8, col, 'Shirt', 0.0012, project='Y', merge=True)

    @staticmethod
    def vneck_pts(u, v):
        z = 1.036 + (1.117 - 1.036) * v
        w = 0.050 * v ** 0.9
        return Vector(((u - 0.5) * 2 * w, -0.16, z))

    def decal(self, key, fn, nu, nv, mat, target, offset, project=None, merge=False):
        bm = bmesh.new()
        vs = [[bm.verts.new(fn(i / nu, j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
        uvl = bm.loops.layers.uv.verify()
        for j in range(nv):
            for i in range(nu):
                f = bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
                for lp, uv in zip(f.loops, ((i / nu, j / nv), ((i + 1) / nu, j / nv),
                                            ((i + 1) / nu, (j + 1) / nv), (i / nu, (j + 1) / nv))):
                    lp[uvl].uv = uv
        if merge:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        ob = self.obj(key, bm, [mat])
        sw = ob.modifiers.new('Wrap', 'SHRINKWRAP')
        sw.target = self.parts[target]
        sw.offset = offset
        if project:
            sw.wrap_method = 'PROJECT'
            sw.use_project_y = project == 'Y'
            sw.use_project_z = project == 'Z'
            sw.use_negative_direction = True
            sw.use_positive_direction = True
            sw.wrap_mode = 'ON_SURFACE'
        else:
            sw.wrap_method = 'NEAREST_SURFACEPOINT'
            sw.wrap_mode = 'OUTSIDE_SURFACE'
        ob['gaf_decal'] = True
        return ob

    # ------------------------------------------------------------ hands
    def build_hands(self):
        ZH = 1.078
        bm = bmesh.new()
        loft(bm, [H(0.505, 0.022, 0.022, 0.019, 0.019, ZH), H(0.530, 0.030, 0.032, 0.017, 0.016, ZH),
                  H(0.560, 0.034, 0.036, 0.015, 0.014, ZH, pw=2.4), H(0.588, 0.035, 0.036, 0.013, 0.012, ZH, pw=2.6),
                  H(0.598, 0.032, 0.033, 0.011, 0.010, ZH, pw=2.6)],
             angles_uniform(16), 'Y', 'Z')
        for (fy, fl, fr) in FINGER_GEO.values():
            x0 = 0.585
            secs = [H(x0 + fl * t, fr * rs, fr * rs, fr * rs * 0.85, fr * rs * 0.85, ZH - 0.002 - 0.004 * t,
                      yc=fy * (1 + 0.08 * t)) for t, rs in ((0.0, 1.0), (0.35, 0.95), (0.7, 0.88), (0.95, 0.75))]
            loft(bm, secs, angles_uniform(8), 'Y', 'Z', tip1=(x0 + fl + fr * 0.6, fy * 1.08, ZH - 0.006))
        secs = [H(0.530 + 0.050 * t, 0.010 * rs, 0.010 * rs, 0.009 * rs, 0.009 * rs, ZH - 0.004, yc=-0.030 - 0.018 * t)
                for t, rs in ((0.0, 1.0), (0.4, 0.95), (0.8, 0.85))]
        loft(bm, secs, angles_uniform(8), 'Y', 'Z', tip1=(0.588, -0.051, ZH - 0.004))
        mirror_bm(bm)
        ob = self.obj('Hands', bm, [self.M['skin']])
        self.sub(ob)

    # ------------------------------------------------------------ legs / bottoms / shoes
    def build_lower(self):
        p, bw = self.p, self.p['body_width']
        lx = LX * bw
        style = p['bottom_style']

        def stripe_angles(c):
            out = []
            for s in (1, -1):
                out += [c + s * 0.072, c + s * 0.115, c + s * 0.143, c + s * 0.186]
            return out

        def is_stripe(th, c):
            d = (th - c + math.pi) % TAU - math.pi
            return p['stripes'] and (0.072 < abs(d) < 0.115 or 0.143 < abs(d) < 0.186)

        if style == 'SHORTS':
            bm = bmesh.new()
            loft(bm, [V(z, rx * bw, 0.096 + (ry - 0.096) * bw, 0.096 + (ry - 0.096) * bw, x=lx)
                      for z, rx, ry in ((0.56, 0.052, 0.055), (0.46, 0.045, 0.048), (0.40, 0.040, 0.043))] +
                 [V(0.345, 0.035, 0.038, 0.038, x=lx, pw=2.0), V(0.310, 0.034, 0.036, 0.038, x=lx, yc=-0.002, pw=2.0),
                  V(0.265, 0.036, 0.043, 0.036, x=lx, yc=0.002, pw=2.0), V(0.220, 0.033, 0.038, 0.033, x=lx, pw=2.0),
                  V(0.175, 0.027, 0.030, 0.028, x=lx, pw=2.0), V(0.120, 0.027, 0.029, 0.028, x=lx, pw=2.0)],
                 angles_uniform(16))
            mirror_bm(bm)
            ob = self.obj('Legs', bm, [self.M['skin']])
            self.sub(ob)

        # pelvis + leg tubes
        bm = bmesh.new()
        pel = [(0.730, 0.135, 0.095), (0.700, 0.143, 0.100), (0.675, 0.152, 0.104), (0.640, 0.160, 0.106),
               (0.580, 0.163, 0.106), (0.540, 0.160, 0.100)]
        loft(bm, [V(z, rx * bw, ry * (0.5 + 0.5 * bw), ry * (0.5 + 0.5 * bw)) for z, rx, ry in pel],
             angles_with(32, stripe_angles(0.0) + stripe_angles(math.pi), tol=0.035), cap0=False, cap1=True,
             tip1=(0, 0, 0.528), mat_fn=lambda i, j, th: 1 if (is_stripe(th, 0) or is_stripe(th, math.pi)) else 0)
        bm2 = bmesh.new()
        if style == 'SHORTS':
            legsec = [(0.560, 0.082, 0.100), (0.505, 0.081, 0.098), (0.455, 0.080, 0.097)]
        else:
            legsec = [(0.630, 0.066, 0.082), (0.560, 0.077, 0.094), (0.480, 0.073, 0.087), (0.400, 0.064, 0.074), (0.320, 0.057, 0.064),
                      (0.240, 0.054, 0.060), (0.170, 0.055, 0.061), (0.140, 0.057, 0.063)]
        loft(bm2, [V(z, rx * bw, ry * (0.5 + 0.5 * bw), ry * (0.5 + 0.5 * bw), x=lx * (0.988 if z > 0.3 else 1.0), pw=2.1)
                   for z, rx, ry in legsec],
             angles_with(24, stripe_angles(0.0), tol=0.04), cap0=False, cap1=False,
             mat_fn=lambda i, j, th: 1 if is_stripe(th, 0) else 0)
        mirror_bm(bm2)
        merge_bm(bm, bm2)
        ob = self.obj('Bottom', bm, [self.M['bottom'], self.M['stripe']])
        add_solidify(ob, 0.006)
        self.sub(ob)

        # socks
        bm = bmesh.new()
        loft(bm, [V(z, r, r + 0.002, r, x=lx, yc=0.010, pw=2.0)
                  for z, r in ((0.125, 0.036), (0.140, 0.044), (0.160, 0.047), (0.174, 0.044), (0.180, 0.034))],
             angles_uniform(16), cap0=False, cap1=False)
        mirror_bm(bm)
        ob = self.obj('Socks', bm, [self.M['sock']])
        self.sub(ob)

        # sneakers
        ht = 1.0 if p['high_tops'] else 0.72

        def SH(y, hw, hh, zc=None, pw=3.0):
            zc = hh if zc is None else zc
            return ((lx, y, zc), hw, hw, hh, hh, pw)
        sole = (math.radians(222), math.radians(318))

        def shoe_mat(i, j, th):
            if sole[0] <= th <= sole[1]:
                return 1
            if i >= 6 and th > math.pi:
                return 1
            return 0
        bm = bmesh.new()
        loft(bm, [SH(0.080, 0.028, 0.060 * ht, zc=0.068 * ht, pw=2.2), SH(0.070, 0.040, 0.072 * ht, zc=0.074 * ht, pw=2.6),
                  SH(0.045, 0.047, 0.076 * ht, zc=0.077 * ht), SH(0.010, 0.050, 0.074 * ht, zc=0.075 * ht),
                  SH(-0.025, 0.053, 0.058), SH(-0.065, 0.055, 0.046), SH(-0.100, 0.056, 0.039),
                  SH(-0.135, 0.054, 0.033), SH(-0.160, 0.046, 0.027), SH(-0.176, 0.030, 0.020, pw=2.4)],
             angles_with(24, list(sole), tol=0.06), 'X', 'Z', tip1=(lx, -0.180, 0.018), mat_fn=shoe_mat)
        mirror_bm(bm)
        ob = self.obj('Shoes', bm, [self.M['shoe'], self.M['sole']])
        self.sub(ob)
        for s, nm in ((1, 'L'), (-1, 'R')):
            def disc(u, v, s=s):
                a = u * TAU
                return Vector((s * (lx + 0.06), 0.022 + math.cos(a) * 0.021 * v, 0.092 * ht + math.sin(a) * 0.021 * v))
            self.decal('ShoePatch' + nm, disc, 16, 3, self.M['sole'], 'Shoes', 0.0012, merge=True)

            def laces(u, v, s=s):
                return Vector((s * lx + (u - 0.5) * 0.030 * (1 - 0.3 * v), 0.030 - 0.105 * v, 0.25))
            self.decal('Laces' + nm, laces, 3, 10, self.M['sole'], 'Shoes', 0.0012, project='Z')

    # ------------------------------------------------------------ head + face
    def build_head(self):
        p = self.p
        im = paint_face(self.name + "_Face", p)
        mf = textured_mat(self.name + "_Face", im, fallback=p['skin_color'])
        bm = bmesh.new()
        loft(bm, [V(1.158, 0.016, 0.014, 0.010, yc=-0.046, pw=2.0), V(1.168, 0.034, 0.030, 0.022, yc=-0.040, pw=2.25),
                  V(1.182, 0.053, 0.048, 0.036, yc=-0.030, pw=2.25), V(1.200, 0.071, 0.066, 0.056, yc=-0.018, pw=2.25),
                  V(1.220, 0.086, 0.084, 0.076, yc=-0.008, pw=2.25), V(1.245, 0.097, 0.098, 0.090, yc=-0.001, pw=2.25),
                  V(1.272, 0.101, 0.106, 0.096, yc=0.003, pw=2.25), V(1.300, 0.101, 0.110, 0.097, yc=0.005, pw=2.25),
                  V(1.330, 0.095, 0.106, 0.091, yc=0.006, pw=2.25), V(1.358, 0.082, 0.093, 0.078, yc=0.007, pw=2.25),
                  V(1.382, 0.061, 0.070, 0.058, yc=0.008, pw=2.25), V(1.398, 0.034, 0.040, 0.032, yc=0.008, pw=2.0)],
             angles_uniform(32), tip0=(0, -0.052, 1.153), tip1=(0, 0.008, 1.405))
        uvl = bm.loops.layers.uv.verify()
        for f in bm.faces:
            for lp in f.loops:
                co = lp.vert.co
                lp[uvl].uv = ((co.x - FACE_WIN[0]) / (FACE_WIN[1] - FACE_WIN[0]),
                              (co.z - FACE_WIN[2]) / (FACE_WIN[3] - FACE_WIN[2]))
        ob = self.obj('Head', bm, [mf])
        self.sub(ob)

        bm = bmesh.new()
        loft(bm, [((0, 0.012, 1.120), 0.044, 0.044, 0.044, 0.044, 2.0), ((0, 0.012, 1.200), 0.041, 0.041, 0.042, 0.040, 2.0),
                  ((0, 0.010, 1.250), 0.042, 0.042, 0.045, 0.040, 2.0)], angles_uniform(16), cap0=False, cap1=False)
        ob = self.obj('Neck', bm, [self.M['skin']])
        self.sub(ob)

        bm = bmesh.new()
        bm.loops.layers.uv.verify()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1.0, calc_uvs=True)
        R = Matrix.Rotation(math.radians(-12), 3, 'X')
        for v in bm.verts:
            v.co = R @ Vector((v.co.x * 0.008, v.co.y * 0.015, v.co.z * 0.022)) + Vector((0.095, 0.016, 1.236))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        mirror_bm(bm)
        ob = self.obj('Ears', bm, [self.M['skin']])
        self.sub(ob)

    # ------------------------------------------------------------ hair
    def build_hair(self):
        p = self.p
        bm = build_hair_mesh(p, self.rng)
        im = hair_gradient(self.name + "_HairGrad", p['hair_color'], p['hair_shadow'])
        mh = textured_mat(self.name + "_Hair", im, rough=0.6, fallback=p['hair_color'])
        ob = self.obj('Hair', bm, [mh])
        if p['subdiv'] > 0:
            add_subsurf(ob, 1, 1)
            if p['hair_decimate'] < 0.999:
                dm = ob.modifiers.new('Decimate', 'DECIMATE')
                dm.ratio = p['hair_decimate']
                dm.use_collapse_triangulate = True

    # ------------------------------------------------------------ finish
    def finish(self):
        p = self.p
        # bake decals onto their surfaces
        for ob in list(self.col.objects):
            if ob.get('gaf_decal') and 'Wrap' in ob.modifiers:
                apply_modifier(ob, 'Wrap')
        # head size, then overall height
        hs, s = p['head_size'], p['height'] / 1.5
        Mh = Matrix.Translation(NECK_PIVOT) @ Matrix.Scale(hs, 4) @ Matrix.Translation(-NECK_PIVOT)
        Ms = Matrix.Scale(s, 4)
        for key, ob in self.parts.items():
            M = Ms @ (Mh if key in HEAD_PARTS else Matrix.Identity(4))
            ob.data.transform(M)
            for md in ob.modifiers:
                if md.type == 'SOLIDIFY':
                    md.thickness *= s
        if p['outline']:
            th = {'Hair': 0.0030, 'Head': 0.0022, 'Ears': 0.0015, 'Hands': 0.0015, 'Neck': 0.0015}
            for key, ob in self.parts.items():
                if not ob.get('gaf_decal'):
                    add_outline(ob, th.get(key, 0.0030) * s * p['outline_width'])
        rig = None
        if p['rig']:
            rig = build_rig(self, Ms, Mh)
        # place at the 3D cursor
        cur = bpy.context.scene.cursor.location.copy()
        if rig is not None:
            rig.location = cur
        else:
            for ob in self.parts.values():
                ob.location = cur
        return rig


HEAD_PARTS = {'Head', 'Ears', 'Hair'}
FACE_WIN = (-0.12, 0.12, 1.13, 1.37)
FINGER_GEO = {'Index': (-0.025, 0.058, 0.0085), 'Middle': (-0.008, 0.064, 0.0088),
              'Ring': (0.009, 0.060, 0.0085), 'Little': (0.025, 0.048, 0.0078)}


# ---------------------------------------------------------------- face texture
def paint_face(name, p, res=1024, ss=2):
    import numpy as np
    X0, X1, Z0, Z1 = FACE_WIN
    N = res * ss
    X, Z = np.meshgrid(np.linspace(X0, X1, N, dtype=np.float32), np.linspace(Z0, Z1, N, dtype=np.float32))
    px = (X1 - X0) / N
    img = np.empty((N, N, 3), np.float32)
    skin = np.array(p['skin_color'][:3], np.float32)
    img[:] = skin

    def C(c):
        return np.array(c[:3], np.float32)

    def paint(mask, col, alpha=1.0):
        m = np.clip(mask, 0, 1)[..., None] * alpha
        img[:] = img * (1 - m) + C(col) * m

    def soft(d):
        return np.clip(0.5 - d / (1.5 * px), 0, 1)

    eye = C(p['eye_color'])
    eye_dark = tuple(eye * 0.55)
    eye_light = tuple(eye * 0.45 + 0.55)
    eye_rim = tuple(eye * 0.3)
    dark = (0.106, 0.075, 0.125)
    sharp = p['eye_shape'] == 'SHARP'
    A = 0.0255 if sharp else 0.024
    top_h, tilt = (0.0150, 0.0050) if sharp else (0.0185, 0.0015)
    iris_r = 0.0128 if sharp else 0.0138
    for side in (1, -1):
        lx = (X - side * 0.037) * side
        lz = Z - 1.2465
        t = np.clip(lx / A, -1, 1)
        top = top_h * np.sqrt(np.clip(1 - t ** 2, 0, 1)) ** 0.7 + tilt * t - 0.0005
        bot = -0.0135 * np.clip(1 - t ** 2, 0, 1) ** 0.75 + 0.0025 * t - 0.001
        cov = soft(np.maximum(np.maximum(lz - top, bot - lz), np.abs(lx) - A))
        paint(cov, (1, 1, 1))
        icx, icz = -0.0015, -0.0005
        dr = np.sqrt((lx - icx) ** 2 + ((lz - icz) / 1.12) ** 2)
        iris = soft(dr - iris_r) * cov
        g = np.clip((lz - icz + 0.013) / 0.026, 0, 1)[..., None]
        icol = C(eye_light) * (1 - g) + C(eye_dark) * g
        m = iris[..., None]
        img[:] = img * (1 - m) + icol * m
        paint(soft(np.abs(dr - iris_r + 0.0006) - 0.0008) * cov, eye_rim)
        paint(soft(np.sqrt((lx - icx) ** 2 + ((lz - icz) / 1.25) ** 2) - 0.0052) * cov, tuple(eye * 0.18))
        paint(soft(np.sqrt((lx - icx - 0.0045) ** 2 + (lz - icz - 0.0055) ** 2) - 0.0034) * cov, (1, 1, 1))
        paint(soft(np.sqrt((lx - icx + 0.0045) ** 2 + (lz - icz + 0.0060) ** 2) - 0.0016) * cov, (1, 1, 1))
        paint(np.clip(1 - (top - lz) / 0.004, 0, 1) * cov * 0.35, (0.35, 0.29, 0.44))
        thick = 0.0016 + 0.0016 * np.clip((t + 1) / 2, 0, 1)
        paint(soft(np.abs(lz - top - thick * 0.4) - thick) * ((lx > -A - 0.0008) & (lx < A + 0.0005)), dark)
        fl = (lx >= A - 0.002) & (lx < A + 0.0075)
        fl_z = top_h * 0 + tilt + 0.0005 - (lx - A + 0.002) * 0.25
        paint(soft(np.abs(lz - fl_z) - 0.0018 * np.clip(1 - (lx - A + 0.002) / 0.0095, 0.15, 1)) * fl, dark)
        paint(soft(np.abs(lz - bot) - 0.0006) * ((lx > -0.006) & (lx < A)), (0.42, 0.27, 0.31))
        paint(soft(np.abs(lz - top - 0.0065) - 0.00045) * ((lx > -0.012) & (lx < A - 0.002)) * 0.7, (0.69, 0.49, 0.49))
        bz = 0.0275 + 0.004 * np.clip(lx / 0.02, -1, 1) - 0.004 * (lx / 0.025) ** 2
        brow = tuple(C(p['hair_shadow']) * 0.8)
        paint(soft(np.abs(lz - bz) - 0.0012) * ((lx > -0.018) & (lx < 0.022)), brow)
    hl = 1.318 + 0.012 * (X / 0.1) ** 2
    paint(soft(hl - Z), p['hair_shadow'])
    paint(soft(np.sqrt(((X - 0.004) / 1.8) ** 2 + (Z - 1.213) ** 2) - 0.0018), tuple(skin * 0.86))
    mz, mw = 1.1855, 0.0135
    tt = np.clip(X / mw, -1, 1)
    inm = np.abs(X) < mw
    if p['mouth'] == 'NEUTRAL':
        paint(soft(np.abs(Z - mz + 0.0008 * tt ** 2) - 0.0006) * (np.abs(X) < mw * 0.8), (0.42, 0.20, 0.24))
    else:
        depth = 0.0045 if p['mouth'] == 'SMILE' else 0.0075
        upper = mz + 0.0012 * (1 - tt ** 2) - 0.0005
        lower = mz - depth * (1 - tt ** 2) ** 1.2
        mouth = soft(np.maximum(Z - upper, lower - Z)) * inm
        paint(mouth, (0.55, 0.20, 0.25))
        paint(soft(np.sqrt((X / 1.6) ** 2 + (Z - (lower + 0.0014)) ** 2) - 0.0022) * mouth, (0.85, 0.42, 0.47))
        if p['mouth'] == 'GRIN':
            paint(soft(np.abs(Z - (upper - 0.0013)) - 0.0008) * mouth, (1, 1, 1))
        paint(soft(np.abs(Z - upper) - 0.0006) * (np.abs(X) < mw + 0.0015), (0.35, 0.15, 0.19))
    for side in (1, -1):
        paint(((np.abs(X - side * 0.052) < 0.008) & (np.abs(Z - 1.222) < 0.003)) * 0.12, (0.88, 0.54, 0.54))
    small = img.reshape(res, ss, res, ss, 3).mean(axis=(1, 3))
    return image_from_array(name, small)


def hair_gradient(name, top, bottom):
    import numpy as np
    H = 256
    v = np.linspace(0, 1, H)
    stops = [(0.00, mix(bottom, top, 0.0)), (0.22, mix(bottom, top, 0.35)), (0.38, mix(bottom, top, 0.75)),
             (0.55, mix(bottom, top, 0.93)), (1.0, mix(top, (1, 1, 1), 0.15))]
    col = np.zeros((H, 3))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        m = (v >= a) & (v <= b)
        t = ((v[m] - a) / (b - a))[:, None]
        col[m] = np.array(ca) * (1 - t) + np.array(cb) * t
    arr = np.ones((H, 4, 3), np.float32) * col[:, None, :]
    return image_from_array(name, arr)


# ---------------------------------------------------------------- hair styles
HC = Vector((0, 0.014, 1.318))
HR = Vector((0.117, 0.126, 0.112))


def _on_cap(d, k=1.0):
    return HC + Vector((d.x * HR.x, d.y * HR.y, d.z * HR.z)) * k


def _cap_pt(x, z, k=1.06):
    q = 1 - (x / (HR.x * k)) ** 2 - ((z - HC.z) / (HR.z * k)) ** 2
    return Vector((x, HC.y - HR.y * k * math.sqrt(max(q, 0.004)), z))


def _fib(n):
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - z * z)
        yield Vector((math.cos(ga * i) * r, math.sin(ga * i) * r, z))


STYLE = {
    #           layers: (count, lmin, lmax, wmin, wmax, k)     up: upward sweep  droop  bang_drop  crown
    'SPIKY': dict(layers=((105, 0.070, 0.118, 0.082, 0.108, 0.86), (85, 0.035, 0.060, 0.065, 0.085, 0.90)),
                  up=0.28, droop=(0.05, 0.22), back_down=0.55, bang_len=1.0, crown=1.0, side=1.0, long=False),
    'UPWARD': dict(layers=((90, 0.090, 0.150, 0.085, 0.110, 0.86), (70, 0.040, 0.070, 0.065, 0.085, 0.90)),
                   up=0.95, droop=(0.0, 0.08), back_down=-0.2, bang_len=0.45, crown=1.5, side=0.6, long=False),
    'MESSY': dict(layers=((110, 0.045, 0.085, 0.075, 0.100, 0.88), (90, 0.030, 0.050, 0.060, 0.080, 0.91)),
                  up=0.05, droop=(0.25, 0.50), back_down=0.8, bang_len=1.15, crown=0.6, side=1.25, long=False),
    'SHORT': dict(layers=((120, 0.022, 0.040, 0.070, 0.090, 0.93),),
                  up=0.20, droop=(0.05, 0.15), back_down=0.6, bang_len=0.55, crown=0.35, side=0.55, long=False),
    'LONG': dict(layers=((110, 0.022, 0.040, 0.075, 0.095, 0.93),),
                 up=0.0, droop=(0.10, 0.20), back_down=0.9, bang_len=1.0, crown=0.0, side=1.6, long=True),
}


def build_hair_mesh(p, rng):
    st = STYLE[p['hair_style']]
    amt = p['hair_amount']
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=16, radius=1.0)
    for v in bm.verts:
        v.co = _on_cap(v.co)
    kill = [v for v in bm.verts if (v.co.y < -0.030 and v.co.z < 1.338) or (v.co.z < 1.255 and v.co.y < 0.03)
            or v.co.z < 1.215]
    bmesh.ops.delete(bm, geom=kill, context='VERTS')

    def keep(d):
        if d.z < -0.6:
            return False
        if d.y < -0.25 and d.z < 0.78:
            return False
        if d.z < -0.15 and d.y < 0.25:
            return False
        return True

    for (n, lmin, lmax, wmin, wmax, k) in st['layers']:
        for d in _fib(int(n * amt)):
            d = (d + Vector([rng.uniform(-.12, .12) for _ in range(3)])).normalized()
            if not keep(d):
                continue
            base = _on_cap(d, k)
            out = Vector((d.x / HR.x, d.y / HR.y, d.z / HR.z)).normalized()
            fr = max(0.0, -d.y)
            sweep = Vector((0, 0.10 + 0.55 * fr * max(d.z, 0), (st['up'] + 0.45 * fr) if d.z > -0.2 else -0.1))
            bk = max(0.0, d.y)
            if bk > 0.2 and d.z < 0.6:
                sweep = Vector((0, -0.25 * bk, -st['back_down'] * bk - 0.35 * max(0.0, 0.3 - d.z)))
            direction = (out + sweep).normalized()
            L = rng.uniform(lmin, lmax) * (1.15 if abs(d.x) > 0.6 else 1.0) * (0.8 if d.z > 0.85 else 1.0)
            droop = rng.uniform(*st['droop']) * (1.0 if d.z < 0.6 else 0.3) + 0.15 * bk
            spike(bm, base, direction, L, rng.uniform(wmin, wmax), thick=0.45, droop=droop, sides=6, segs=5,
                  taper=1.1, belly=0.35)

    # fringe
    bl = st['bang_len']
    bangs = [(-0.090, -0.108, 1.230, 0.066), (-0.064, -0.076, 1.268, 0.072), (-0.036, -0.040, 1.290, 0.072),
             (-0.008, -0.010, 1.270, 0.074), (0.020, 0.024, 1.292, 0.072), (0.048, 0.058, 1.266, 0.072),
             (0.076, 0.094, 1.250, 0.070), (0.098, 0.114, 1.225, 0.060), (-0.050, -0.056, 1.255, 0.060),
             (-0.022, -0.024, 1.278, 0.060), (0.006, 0.008, 1.252, 0.062), (0.034, 0.040, 1.280, 0.060),
             (0.062, 0.074, 1.262, 0.060)]
    for idx, (xb, xt, tz, w) in enumerate(bangs):
        front = idx >= 8
        kk = 1.10 if front else 1.06
        tz = 1.335 - (1.335 - tz) * bl + rng.uniform(-0.006, 0.006)
        pts = [_cap_pt(xb * (0.35 + 0.65 * (1.445 - zz) / 0.11), zz, kk) for zz in (1.445, 1.43, 1.41, 1.385, 1.36, 1.335)]
        tip = Vector((xt, -0.114 + abs(xt) * 0.22 - (0.006 if front else 0), min(tz, 1.32)))
        if tz < 1.33:
            pts += [(pts[-1] + tip) / 2 + Vector((0, -0.010, 0)), tip]
        else:
            pts += [tip + Vector((0, -0.01, 0))]
        strand(bm, pts, w, thick=0.32, sides=6, taper=1.4, belly=0.5)

    # crown spikes
    if st['crown'] > 0:
        for (x, z, lxx, L, w) in ((-0.075, 1.405, -0.9, 0.095, 0.075), (-0.040, 1.425, -0.45, 0.105, 0.080),
                                  (0.000, 1.432, 0.05, 0.110, 0.080), (0.042, 1.425, 0.5, 0.100, 0.080),
                                  (0.078, 1.405, 0.95, 0.092, 0.075), (-0.020, 1.440, -0.2, 0.09, 0.07),
                                  (0.022, 1.440, 0.25, 0.085, 0.07)):
            d = Vector((lxx, -0.55 / st['crown'], 1.0)).normalized()
            spike(bm, _cap_pt(x, z, 0.95), d, L * st['crown'], w, thick=0.45, droop=0.10 / st['crown'], sides=6,
                  segs=5, taper=1.1, belly=0.35, bend=Vector((0, 0.3, -1)))

    # side locks
    for s in (1, -1):
        for (yb, tz, xo, w) in ((-0.035, 1.190, 0.108, 0.042), (0.005, 1.205, 0.118, 0.046), (0.045, 1.215, 0.120, 0.05)):
            tz = 1.33 - (1.33 - tz) * st['side']
            base = Vector((s * 0.100, yb, 1.330))
            tip = Vector((s * (xo + 0.01 * (st['side'] - 1)), yb - 0.02, tz))
            spike(bm, base, tip - base, (tip - base).length, w, thick=0.35, droop=0.12, sides=6, segs=6,
                  wdir=Vector((0, 1, 0)), bend=Vector((s, 0, 0)))

    # long hair: locks falling down the back
    if st['long']:
        n = int(36 * amt)
        for i in range(n):
            a = math.radians(-115 + 230 * i / (n - 1)) + rng.uniform(-0.05, 0.05)   # 0 = straight back
            sx, sy = math.sin(a), math.cos(a)
            pts = []
            for zz in (1.44, 1.40, 1.35, 1.30, 1.25):
                q = max(0.02, 1 - ((zz - HC.z) / (HR.z * 1.05)) ** 2)
                r = math.sqrt(q) * 1.05
                pts.append(Vector((sx * HR.x * r, HC.y + sy * HR.y * r, zz)))
            side = abs(sx) > 0.75
            end_z = (1.12 if side else 0.98) + rng.uniform(-0.03, 0.03)
            last = pts[-1]
            outward = Vector((sx * 0.02, max(sy, 0.2) * 0.03, 0))
            for t in (0.33, 0.66, 1.0):
                pts.append(last + outward * t + Vector((0, 0.01 * t * max(sy, 0), (end_z - last.z) * t)))
            strand(bm, pts, rng.uniform(0.085, 0.110), thick=0.40, sides=6, taper=1.5, belly=0.35,
                   wdir=Vector((math.cos(a), -math.sin(a), 0)))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    HZ0, HZ1 = 1.16, 1.56
    if st['long']:
        HZ0 = 0.95
    uvl = bm.loops.layers.uv.verify()
    for f in bm.faces:
        for lp in f.loops:
            co = lp.vert.co - HC
            lp[uvl].uv = (0.5 + math.atan2(co.x, -co.y) / TAU, (lp.vert.co.z - HZ0) / (HZ1 - HZ0))
    return bm


# ---------------------------------------------------------------- rig (Godot humanoid bone names)
def bone_table(bw=1.0):
    lx = LX * bw
    B = {
        'Root': ((0, 0, 0), (0, 0.12, 0), None, 0),
        'Hips': ((0, 0.005, 0.560), (0, 0.005, 0.680), 'Root', 0.13),
        'Spine': ((0, 0.005, 0.680), (0, 0.004, 0.800), 'Hips', 0.13),
        'Chest': ((0, 0.004, 0.800), (0, 0.003, 0.940), 'Spine', 0.13),
        'UpperChest': ((0, 0.003, 0.940), (0, 0.006, 1.070), 'Chest', 0.12),
        'Neck': ((0, 0.010, 1.100), (0, 0.012, 1.190), 'UpperChest', 0.05),
        'Head': ((0, 0.012, 1.190), (0, 0.012, 1.400), 'Neck', 0.10),
    }
    SIDE = {
        'Shoulder': ((0.020, 0.0, 1.074), (0.115, 0.0, 1.078), 'UpperChest', 0.06),
        'UpperArm': ((0.115, 0.0, 1.078), (0.325, 0.004, 1.078), 'Shoulder', 0.045),
        'LowerArm': ((0.325, 0.004, 1.078), (0.515, 0.0, 1.078), 'UpperArm', 0.035),
        'Hand': ((0.515, 0.0, 1.078), (0.585, 0.0, 1.077), 'LowerArm', 0.028),
        'UpperLeg': ((lx, 0.0, 0.560), (lx, -0.004, 0.310), 'Hips', 0.05),
        'LowerLeg': ((lx, -0.004, 0.310), (lx, 0.012, 0.075), 'UpperLeg', 0.04),
        'Foot': ((lx, 0.012, 0.075), (lx, -0.090, 0.025), 'LowerLeg', 0.05),
        'Toes': ((lx, -0.090, 0.025), (lx, -0.170, 0.025), 'Foot', 0.04),
        'ThumbMetacarpal': ((0.512, -0.012, 1.075), (0.530, -0.028, 1.074), 'Hand', 0.012),
        'ThumbProximal': ((0.530, -0.028, 1.074), (0.556, -0.039, 1.074), 'ThumbMetacarpal', 0.011),
        'ThumbDistal': ((0.556, -0.039, 1.074), (0.588, -0.051, 1.074), 'ThumbProximal', 0.010),
    }
    for fn, (fy, fl, _) in FINGER_GEO.items():
        x0, prev = 0.585, 'Hand'
        for i, seg in enumerate(('Proximal', 'Intermediate', 'Distal')):
            a, b = i / 3, (i + 1) / 3
            SIDE[fn + seg] = ((x0 + fl * a, fy * (1 + 0.08 * a), 1.076 - 0.005 * a),
                              (x0 + fl * b, fy * (1 + 0.08 * b), 1.076 - 0.005 * b), prev, 0.009)
            prev = fn + seg
    for n, (h, t, par, r) in SIDE.items():
        for side, sx in (('Left', 1), ('Right', -1)):
            pp = par if par in B else side + par
            B[side + n] = ((sx * h[0], h[1], h[2]), (sx * t[0], t[1], t[2]), pp, r)
    return B


def _sides(names):
    out = []
    for n in names:
        out += [n] if n in ('Root', 'Hips', 'Spine', 'Chest', 'UpperChest', 'Neck', 'Head') else ['Left' + n, 'Right' + n]
    return out


FINGERS = ['Index', 'Middle', 'Ring', 'Little']
PARTS = {
    'Head': ['Head'], 'Ears': ['Head'], 'Hair': ['Head'],
    'Neck': ['Neck', 'Head', 'UpperChest'],
    'Turtleneck': ['Neck', 'UpperChest', 'Head'],
    'Shirt': _sides(['Hips', 'Spine', 'Chest', 'UpperChest', 'Shoulder', 'UpperArm']),
    'VNeck': ['Chest', 'UpperChest'],
    'Sleeves': _sides(['UpperChest', 'Shoulder', 'UpperArm']),
    'Arms': _sides(['UpperChest', 'Shoulder', 'UpperArm', 'LowerArm', 'Hand']),
    'Hands': None,   # per-island
    'Bottom': _sides(['Hips', 'Spine', 'UpperLeg', 'LowerLeg']),
    'Legs': _sides(['Hips', 'UpperLeg', 'LowerLeg', 'Foot']),
    'Socks': _sides(['LowerLeg', 'Foot']),
    'Shoes': _sides(['LowerLeg', 'Foot', 'Toes']),
    'ShoePatchL': ['LeftLowerLeg', 'LeftFoot'], 'ShoePatchR': ['RightLowerLeg', 'RightFoot'],
    'LacesL': ['LeftFoot', 'LeftToes', 'LeftLowerLeg'], 'LacesR': ['RightFoot', 'RightToes', 'RightLowerLeg'],
}
SIGMA = {'Shirt': 0.30, 'Bottom': 0.30, 'Hands': 0.18}


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def _islands(me):
    import collections
    adj = collections.defaultdict(list)
    for e in me.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    seen = [-1] * len(me.vertices)
    k = 0
    for s in range(len(me.vertices)):
        if seen[s] >= 0:
            continue
        stack = [s]
        seen[s] = k
        while stack:
            v = stack.pop()
            for w in adj[v]:
                if seen[w] < 0:
                    seen[w] = k
                    stack.append(w)
        k += 1
    return seen, k


def build_rig(b, Ms, Mh):
    p = b.p
    name = b.name + "_Rig"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    B0 = bone_table(p['body_width'])
    B = {}
    for n, (h, t, par, r) in B0.items():
        M = Ms @ (Mh if n == 'Head' else Matrix.Identity(4))
        rs = r * Ms[0][0] * (p['head_size'] if n == 'Head' else 1.0)
        B[n] = (M @ Vector(h), M @ Vector(t), par, rs)
    arm = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, arm)
    b.col.objects.link(rig)
    rig.show_in_front = True
    vl = bpy.context.view_layer
    prev_active = vl.objects.active
    for o in bpy.context.selected_objects:
        o.select_set(False)
    vl.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones
    for n, (h, t, par, r) in B.items():
        e = eb.new(n)
        e.head, e.tail = h, t
    for n, (h, t, par, r) in B.items():
        if par:
            eb[n].parent = eb[par]
            eb[n].use_connect = (eb[par].tail - h).length < 1e-5 and n != 'Hips'
        if any(k in n for k in ('Shoulder', 'Arm', 'Hand', 'Thumb', 'Index', 'Middle', 'Ring', 'Little', 'Foot', 'Toes')):
            eb[n].align_roll(Vector((0, 0, 1)))
        else:
            eb[n].align_roll(Vector((0, -1, 0)))
    bpy.ops.object.mode_set(mode='OBJECT')

    for key, ob in b.parts.items():
        allowed = PARTS.get(key)
        if key not in PARTS:
            continue
        me = ob.data
        ob.vertex_groups.clear()
        sig = SIGMA.get(key, 0.25)
        if key == 'Hands':
            isl, k = _islands(me)
            cent = [Vector() for _ in range(k)]
            cnt = [0] * k
            for v in me.vertices:
                cent[isl[v.index]] += v.co
                cnt[isl[v.index]] += 1
            allow_isl = []
            for i in range(k):
                c = cent[i] / cnt[i]
                side = 'Left' if c.x > 0 else 'Right'
                best, bd = None, 1e9
                for f in FINGERS + ['Thumb']:
                    first = side + f + ('Metacarpal' if f == 'Thumb' else 'Proximal')
                    last = side + f + 'Distal'
                    d = _seg_dist(c, B[first][0], B[last][1])
                    if d < bd:
                        best, bd = f, d
                if bd < 0.006 * Ms[0][0]:
                    if best == 'Thumb':
                        allow_isl.append([side + 'ThumbProximal', side + 'ThumbDistal', side + 'ThumbMetacarpal'])
                    else:
                        allow_isl.append([side + best + s for s in ('Proximal', 'Intermediate', 'Distal')] + [side + 'Hand'])
                else:
                    allow_isl.append([side + 'LowerArm', side + 'Hand', side + 'ThumbMetacarpal'] +
                                     [side + f + 'Proximal' for f in FINGERS])
            per_vert = [allow_isl[isl[v.index]] for v in me.vertices]
        else:
            per_vert = None
        groups = {}
        for v in me.vertices:
            names = per_vert[v.index] if per_vert else allowed
            if len(names) == 1:
                ws = [(1.0, names[0])]
            else:
                de = [(_seg_dist(v.co, B[n][0], B[n][1]) / max(B[n][3], 1e-4), n) for n in names]
                dmin = min(d for d, _ in de)
                ws = sorted(((math.exp(-(d - dmin) / sig), n) for d, n in de), reverse=True)[:4]
                ws = [(w, n) for w, n in ws if w > 0.03]
                tot = sum(w for w, _ in ws)
                ws = [(w / tot, n) for w, n in ws]
            for w, n in ws:
                g = groups.get(n) or ob.vertex_groups.new(name=n)
                groups[n] = g
                g.add([v.index], w, 'REPLACE')
        ob.parent = rig
        md = ob.modifiers.new('Armature', 'ARMATURE')
        md.object = rig
        md.use_deform_preserve_volume = key in ('Arms', 'Legs', 'Hands', 'Sleeves')
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_move_to_index(modifier='Armature', index=0)
    if prev_active is not None and prev_active.name in bpy.data.objects:
        pass
    return rig


def build_character(**kw):
    """Create a rigged, game-ready anime character. Returns the armature (or None if rig=False)."""
    p = dict(DEFAULTS)
    p.update(kw)
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    b = Builder(p)
    b.build_top()
    b.build_hands()
    b.build_lower()
    b.build_head()
    b.build_hair()
    rig = b.finish()
    return rig, b
