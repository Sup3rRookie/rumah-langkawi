import pdfplumber, json, math

PDF = '/mnt/user-data/uploads/Langkawi-Interior_Floor_Layout.pdf'
GRAY = (0.49804, 0.49804, 0.49804)
SNAP = 5.0
MINLEN = 120.0

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    lines, curves = page.lines, page.curves

PLANS = {'gf': (200, 560, 7640.0), 'ff': (590, 900, 8460.0)}
out = {'units': 'mm', 'source': 'Langkawi-Interior_Floor_Layout.pdf',
       'note': 'Coordinates are plan-local, origin at the north-west extent of each floor. '
               'X runs east, Y runs south. Scale derived from the annotated overall widths '
               '(GF 7640, FF 8460) and cross-checked against the 17317 depth chain.',
       'floors': {}}

for key, (lo, hi, known_w) in PLANS.items():
    def inb(o):
        return lo < o['x0'] < hi and 100 < o['top'] < 620

    wl = [l for l in lines
          if l.get('stroking_color') in (GRAY, 0, (0.0, 0.0, 0.0)) and inb(l)]
    gc = [c for c in curves if c.get('stroking_color') == GRAY and inb(c)]

    xs = [v for l in wl for v in (l['x0'], l['x1'])]
    ys = [v for l in wl for v in (l['top'], l['bottom'])]
    x0, y0 = min(xs), min(ys)
    scale = known_w / (max(xs) - x0)

    def P(x, y):
        return (round((x - x0) * scale / SNAP) * SNAP, round((y - y0) * scale / SNAP) * SNAP)

    segs = set()
    for l in wl:
        a, b = P(l['x0'], l['top']), P(l['x1'], l['bottom'])
        if math.dist(a, b) < MINLEN:
            continue
        segs.add(tuple(sorted([a, b])))

    def merge(axis):
        groups = {}
        for a, b in segs:
            if axis == 'h' and abs(a[1] - b[1]) < 1:
                groups.setdefault(('h', a[1]), []).append((min(a[0], b[0]), max(a[0], b[0])))
            elif axis == 'v' and abs(a[0] - b[0]) < 1:
                groups.setdefault(('v', a[0]), []).append((min(a[1], b[1]), max(a[1], b[1])))
        res = []
        for k, iv in groups.items():
            iv.sort()
            cur = list(iv[0])
            for s, e in iv[1:]:
                if s <= cur[1] + SNAP:
                    cur[1] = max(cur[1], e)
                else:
                    res.append((k, tuple(cur))); cur = [s, e]
            res.append((k, tuple(cur)))
        return res

    walls = []
    for (ax, c), (s, e) in merge('h') + merge('v'):
        if e - s < MINLEN:
            continue
        walls.append([s, c, e, c] if ax == 'h' else [c, s, c, e])

    diag = []
    for a, b in segs:
        if abs(a[0] - b[0]) > 1 and abs(a[1] - b[1]) > 1:
            diag.append([a[0], a[1], b[0], b[1]])

    doors = []
    for c in gc:
        w, h = c['x1'] - c['x0'], c['y1'] - c['y0']
        p = c['pts']
        if len(p) == 2 and abs(w - h) < 0.6 and w > 4:
            A, B = P(*p[0]), P(*p[1])
            for cand in ((A[0], B[1]), (B[0], A[1])):
                if abs(math.dist(cand, A) - w * scale) < 45 and abs(math.dist(cand, B) - w * scale) < 45:
                    doors.append(dict(hinge=[cand[0], cand[1]],
                                      leaf=[A[0], A[1]], open_to=[B[0], B[1]],
                                      width=round(w * scale)))
                    break

    W = round((max(xs) - x0) * scale)
    H = round((max(ys) - y0) * scale)
    out['floors'][key] = dict(
        scale_mm_per_pt=round(scale, 4),
        extent_mm=[W, H],
        wall_count=len(walls),
        walls=walls, diagonal_walls=diag, doors=doors)
    print('%s  %d x %d mm   walls=%d  diagonals=%d  doors=%d'
          % (key, W, H, len(walls), len(diag), len(doors)))
    tk = sorted({round(abs(w[1] - v[1])) for w in walls for v in walls
                 if w[0] == v[0] and w[2] == v[2] and w is not v and abs(w[1] - v[1]) > 0})[:6]
    print('    parallel wall face spacings seen:', tk)

json.dump(out, open('/mnt/user-data/outputs/walls.json', 'w'), indent=1)
print('\nwrote walls.json')
