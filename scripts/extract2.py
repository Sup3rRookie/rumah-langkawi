import pdfplumber, numpy as np, json, math
from PIL import Image, ImageDraw
from scipy import ndimage

PDF = '/mnt/user-data/uploads/Langkawi-Interior_Floor_Layout.pdf'
RES = 15.0
GRAY = (0.49804, 0.49804, 0.49804)

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    lines = page.lines
    curves = page.curves

def inbox(o, lo, hi):
    return lo < o['x0'] < hi and 100 < o['top'] < 620

PLANS = {'gf': (200, 560, 7640.0), 'ff': (590, 900, 8460.0)}
result = {}

for key, (lo, hi, known_w) in PLANS.items():
    wl = [l for l in lines
          if l.get('stroking_color') in (GRAY, 0, (0.0, 0.0, 0.0)) and inbox(l, lo, hi)]
    gc = [c for c in curves if c.get('stroking_color') == GRAY and inbox(c, lo, hi)]

    segs = [(l['x0'], l['top'], l['x1'], l['bottom']) for l in wl]

    arcs, leaves = [], []
    for c in gc:
        w, h = c['x1'] - c['x0'], c['y1'] - c['y0']
        pts = c['pts']
        if len(pts) == 2 and abs(w - h) < 0.6 and w > 4:
            arcs.append((pts[0], pts[1], w))
        else:
            leaves.append(c)

    for A, B, r in arcs:
        for cand in ((A[0], B[1]), (B[0], A[1])):
            dA = math.hypot(cand[0] - A[0], cand[1] - A[1])
            dB = math.hypot(cand[0] - B[0], cand[1] - B[1])
            if abs(dA - r) < 1.2 and abs(dB - r) < 1.2:
                segs.append((cand[0], cand[1], A[0], A[1]))
                segs.append((cand[0], cand[1], B[0], B[1]))
                break

    for c in leaves:
        p = c['pts']
        for i in range(len(p) - 1):
            segs.append((p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]))

    ys_all = [v for s in segs for v in (s[1], s[3])]
    xs_all = [v for s in segs for v in (s[0], s[2])]
    x0, x1 = min(xs_all), max(xs_all)
    y0, y1 = min(ys_all), max(ys_all)
    scale = known_w / (x1 - x0)

    W = int((x1 - x0) * scale / RES) + 10
    H = int((y1 - y0) * scale / RES) + 10
    img = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(img)
    def px(x, y):
        return ((x - x0) * scale / RES + 5, (y - y0) * scale / RES + 5)
    for s in segs:
        d.line([px(s[0], s[1]), px(s[2], s[3])], fill=255, width=3)

    a = np.array(img) > 0
    lab, n = ndimage.label(~a)
    border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])

    rooms = []
    for i in range(1, n + 1):
        if i in border:
            continue
        m = lab == i
        area = m.sum() * (RES / 1000.0) ** 2
        if area < 1.0:
            continue
        r_, c_ = np.where(m)
        rooms.append(dict(
            area_m2=round(area, 2),
            x_mm=int((c_.min() - 5) * RES), y_mm=int((r_.min() - 5) * RES),
            w_mm=int((c_.max() - c_.min() + 1) * RES),
            h_mm=int((r_.max() - r_.min() + 1) * RES),
            rect=round(area / ((c_.max() - c_.min() + 1) * (r_.max() - r_.min() + 1) * (RES / 1000.0) ** 2), 2)))
    rooms.sort(key=lambda r: -r['area_m2'])

    print('%s  scale %.4f mm/pt   plan %d x %d mm   arcs=%d   spaces=%d'
          % (key, scale, (x1 - x0) * scale, (y1 - y0) * scale, len(arcs), len(rooms)))
    for r in rooms:
        print('   %6.1f m2   %4d x %4d mm   at (%4d,%5d)   rect %.2f'
              % (r['area_m2'], r['w_mm'], r['h_mm'], r['x_mm'], r['y_mm'], r['rect']))

    result[key] = dict(scale_mm_per_pt=round(scale, 4),
                       plan_mm=[round((x1 - x0) * scale), round((y1 - y0) * scale)],
                       rooms=rooms)
    Image.fromarray((a * 255).astype('uint8')).save('/home/claude/w_%s.png' % key)
    col = np.zeros(lab.shape + (3,), 'uint8')
    rng = np.random.default_rng(3)
    for i in range(1, n + 1):
        if i in border:
            continue
        if (lab == i).sum() * (RES / 1000.) ** 2 < 1.0:
            continue
        col[lab == i] = rng.integers(70, 235, 3)
    col[a] = 255
    Image.fromarray(col).resize((W * 2, H * 2), Image.NEAREST).save('/home/claude/rooms_%s.png' % key)

json.dump(result, open('/home/claude/rooms.json', 'w'), indent=1)
