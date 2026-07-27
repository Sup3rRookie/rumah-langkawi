import pdfplumber, numpy as np, json, math
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

PDF = '/mnt/user-data/uploads/Langkawi-Interior_Floor_Layout.pdf'
GRAY = (0.49804, 0.49804, 0.49804)
RES = 10.0
PLANS = {'gf': (200, 560, 7640.0, 'Ground floor'), 'ff': (590, 900, 8460.0, 'First floor')}

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    lines, curves = page.lines, page.curves

schedule = {}
for key, (lo, hi, known_w, title) in PLANS.items():
    def inb(o):
        return lo < o['x0'] < hi and 100 < o['top'] < 620

    wl = [l for l in lines if l.get('stroking_color') in (GRAY, 0, (0.0, 0.0, 0.0)) and inb(l)]
    gc = [c for c in curves if c.get('stroking_color') == GRAY and inb(c)]

    xs = [v for l in wl for v in (l['x0'], l['x1'])]
    ys = [v for l in wl for v in (l['top'], l['bottom'])]
    x0, y0 = min(xs), min(ys)
    scale = known_w / (max(xs) - x0)

    segs = [(l['x0'], l['top'], l['x1'], l['bottom']) for l in wl]

    arcs = []
    for c in gc:
        w, h = c['x1'] - c['x0'], c['y1'] - c['y0']
        p = c['pts']
        if len(p) == 2 and abs(w - h) < 0.6 and w > 4:
            arcs.append((p[0], p[1], w))
        else:
            for i in range(len(p) - 1):
                segs.append((p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]))
    for A, B, r in arcs:
        for cd in ((A[0], B[1]), (B[0], A[1])):
            if abs(math.hypot(cd[0] - A[0], cd[1] - A[1]) - r) < 1.2 and \
               abs(math.hypot(cd[0] - B[0], cd[1] - B[1]) - r) < 1.2:
                segs.append((cd[0], cd[1], A[0], A[1]))
                segs.append((cd[0], cd[1], B[0], B[1]))
                break

    W = int((max(xs) - x0) * scale / RES) + 8
    H = int((max(ys) - y0) * scale / RES) + 8
    img = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(img)
    def px(x, y):
        return ((x - x0) * scale / RES + 4, (y - y0) * scale / RES + 4)
    for s in segs:
        d.line([px(s[0], s[1]), px(s[2], s[3])], fill=255, width=2)

    a = np.array(img) > 0
    a = ndimage.binary_closing(a, np.ones((3, 3)))
    lab, n = ndimage.label(~a)
    border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])

    rooms = []
    for i in range(1, n + 1):
        if i in border:
            continue
        m = lab == i
        area = m.sum() * (RES / 1000.0) ** 2
        if area < 1.3:
            continue
        r_, c_ = np.where(m)
        w_mm = int((c_.max() - c_.min() + 1) * RES)
        h_mm = int((r_.max() - r_.min() + 1) * RES)
        rooms.append(dict(area=round(area, 1), w=w_mm, h=h_mm,
                          x=int(c_.min() * RES), y=int(r_.min() * RES),
                          cx=int(c_.mean()), cy=int(r_.mean()),
                          rect=round(area / (w_mm * h_mm / 1e6), 2), mask=m))
    rooms.sort(key=lambda r: (r['y'], r['x']))

    print('\n%s   %d x %d mm   scale %.4f mm/pt   %d enclosed spaces'
          % (title, round((max(xs) - x0) * scale), round((max(ys) - y0) * scale), scale, len(rooms)))
    print('  #   area      internal envelope        position (x,y)    rectangularity')
    for j, r in enumerate(rooms, 1):
        print('  %-3d %5.1f m2  %5d x %5d mm      (%5d, %5d)     %.2f'
              % (j, r['area'], r['w'], r['h'], r['x'], r['y'], r['rect']))

    col = np.full(lab.shape + (3,), 255, 'uint8')
    rng = np.random.default_rng(7)
    for j, r in enumerate(rooms, 1):
        col[r['mask']] = rng.integers(150, 245, 3)
    col[a] = 30
    im = Image.fromarray(col)
    SC = 3
    im = im.resize((W * SC, H * SC), Image.NEAREST)
    dd = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 34)
        fs = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
    except Exception:
        f = fs = ImageFont.load_default()
    for j, r in enumerate(rooms, 1):
        cx, cy = r['cx'] * SC, r['cy'] * SC
        dd.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=(20, 20, 20))
        dd.text((cx, cy), str(j), fill=(255, 255, 255), font=f, anchor='mm')
        dd.text((cx, cy + 40), '%.1f m²' % r['area'], fill=(30, 30, 30), font=fs, anchor='mm')
        dd.text((cx, cy + 62), '%d x %d' % (r['w'], r['h']), fill=(90, 90, 90), font=fs, anchor='mm')
    im.save('/mnt/user-data/outputs/keyplan_%s.png' % key)

    schedule[key] = dict(title=title, scale_mm_per_pt=round(scale, 4),
                         extent_mm=[round((max(xs) - x0) * scale), round((max(ys) - y0) * scale)],
                         spaces=[{k: v for k, v in r.items() if k != 'mask'} for r in rooms])

json.dump(schedule, open('/mnt/user-data/outputs/room-schedule.json', 'w'), indent=1)
print('\nwrote room-schedule.json and keyplan_gf.png / keyplan_ff.png')
