import pdfplumber, numpy as np, json, math
from PIL import Image, ImageDraw
from scipy import ndimage

PDF = '/mnt/user-data/uploads/Langkawi-Interior_Floor_Layout.pdf'
GRAY = (0.49804, 0.49804, 0.49804)
RES = 10.0
PLANS = {'gf': (200, 560, 7640.0, 'Ground floor', 3.0),
         'ff': (590, 900, 8460.0, 'First floor', 3.0)}

RATE = 12.0      # m2 per litre per coat, smooth plaster
COATS = 2
WASTE = 1.10
DEDUCT = 0.15    # openings

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    lines, curves = page.lines, page.curves

# provisional use + colour, pending room names from the client
ASSIGN = {
    ('gf', 1): ('Stair void', None),
    ('gf', 2): ('Open plan: living / dining / kitchen / stair', '1024'),
    ('gf', 3): ('Ground floor room', '11209'),
    ('gf', 4): ('WC', '1129'),
    ('ff', 1): ('Master suite (front bay)', '12306'),
    ('ff', 2): ('Stair void', None),
    ('ff', 3): ('Bath / walk-in', '1129'),
    ('ff', 4): ('Family area', '1024'),
    ('ff', 5): ('Bath / store', '1129'),
    ('ff', 6): ('Bedroom', '11209'),
    ('ff', 7): ('Bedroom', '11209'),
    ('ff', 8): ('Bath', '1129'),
}
NAMES = {'1024': 'Timeless', '11209': 'Light clay', '1129': 'Parchment',
         '12306': 'Tender greige', '12303': 'Natural white'}

allrows = []
totals = {}
ceil_total = 0.0

for key, (lo, hi, known_w, title, HT) in PLANS.items():
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
                segs += [(cd[0], cd[1], A[0], A[1]), (cd[0], cd[1], B[0], B[1])]
                break

    W = int((max(xs) - x0) * scale / RES) + 8
    H = int((max(ys) - y0) * scale / RES) + 8
    img = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(img)
    for s in segs:
        d.line([((s[0] - x0) * scale / RES + 4, (s[1] - y0) * scale / RES + 4),
                ((s[2] - x0) * scale / RES + 4, (s[3] - y0) * scale / RES + 4)], fill=255, width=2)

    a = ndimage.binary_closing(np.array(img) > 0, np.ones((3, 3)))
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
        rooms.append((int(r_.min()), int(c_.min()), m, area))
    rooms.sort(key=lambda t: (t[0], t[1]))

    print('\n%s   ceiling %.2f m' % (title, HT))
    print('  #  space                                   floor    perim   net wall   colour')
    for j, (_, _, m, area) in enumerate(rooms, 1):
        pad = np.pad(m, 1)
        edges = ((pad[1:-1, 1:-1] & ~pad[:-2, 1:-1]).sum() +
                 (pad[1:-1, 1:-1] & ~pad[2:, 1:-1]).sum() +
                 (pad[1:-1, 1:-1] & ~pad[1:-1, :-2]).sum() +
                 (pad[1:-1, 1:-1] & ~pad[1:-1, 2:]).sum())
        perim = edges * RES / 1000.0
        gross = perim * HT
        net = gross * (1 - DEDUCT)
        use, code = ASSIGN.get((key, j), ('Unassigned', '1024'))
        print('  %-2d %-40s %5.1f  %6.1f m  %7.1f m2  %s'
              % (j, use, area, perim, net, code or '—'))
        if code:
            totals[code] = totals.get(code, 0) + net
            ceil_total += area
            allrows.append(dict(floor=key, no=j, use=use, floor_m2=round(area, 1),
                                perimeter_m=round(perim, 1), wall_m2=round(net, 1), colour=code))

print('\n' + '=' * 68)
print('PAINT SCHEDULE   %.0f m2/L per coat, %d coats, %.0f%% wastage, %.0f%% openings deducted'
      % (RATE, COATS, (WASTE - 1) * 100, DEDUCT * 100))
print('=' * 68)
grand = 0
for code in sorted(totals, key=lambda c: -totals[c]):
    L = totals[code] * COATS / RATE * WASTE
    grand += L
    print('  Jotun %-6s %-15s %7.1f m2   %6.1f L   -> buy %2d x 5L'
          % (code, NAMES.get(code, ''), totals[code], L, math.ceil(L / 5)))
prim = sum(totals.values()) / RATE * WASTE
ceilL = ceil_total * 2 / RATE * WASTE
print('  %-29s %7.1f m2   %6.1f L   (Majestic Primer, 1 coat)' % ('Primer', sum(totals.values()), prim))
print('  %-29s %7.1f m2   %6.1f L   (Essence Easy Ceiling, 2 coats)' % ('Ceilings 12303', ceil_total, ceilL))
print('-' * 68)
print('  %-29s %7.1f m2   %6.1f L total wet product'
      % ('TOTAL', sum(totals.values()) + ceil_total, grand + prim + ceilL))

json.dump(dict(assumptions=dict(ceiling_gf=3.0, ceiling_ff=3.0, rate=RATE, coats=COATS,
                                wastage=WASTE, opening_deduction=DEDUCT),
               rooms=allrows,
               litres={c: round(totals[c] * COATS / RATE * WASTE, 1) for c in totals},
               primer_L=round(prim, 1), ceiling_L=round(ceilL, 1)),
          open('/mnt/user-data/outputs/paint-schedule.json', 'w'), indent=1)
print('\nwrote paint-schedule.json')
