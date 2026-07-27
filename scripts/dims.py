import pdfplumber, math, pathlib
from collections import defaultdict

PDF = str(pathlib.Path(__file__).resolve().parent.parent / 'data' / 'Langkawi-Interior_Floor_Layout.pdf')
BLACKS = (0, (0.0, 0.0, 0.0))

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    L = page.lines
    C = page.curves

SCALE = {'gf': 34.2478, 'ff': 34.2067}
ZONE = {'gf': (280, 580), 'ff': (600, 900)}

print('=== glyph audit: is there any text-like geometry inside the plans? ===')
for k, (lo, hi) in ZONE.items():
    small = [c for c in C if lo < c['x0'] < hi and 130 < c['top'] < 620
             and (c['x1'] - c['x0']) < 6 and (c['y1'] - c['y0']) < 6]
    print(' %s: %d tiny curves inside plan outline' % (k, len(small)))

print()
print('=== dimension chains, measured from tick geometry ===')

for k, (lo, hi) in ZONE.items():
    sc = SCALE[k]
    band = [l for l in L if l.get('stroking_color') in BLACKS
            and lo - 40 < l['x0'] < hi + 40 and l['top'] < 180]

    horiz = [l for l in band if abs(l['top'] - l['bottom']) < 0.4
             and (l['x1'] - l['x0']) > 40]
    ticks = [l for l in band if abs(l['top'] - l['bottom']) > 1.0
             and abs(l['x1'] - l['x0']) > 0.5]

    rows = defaultdict(list)
    for l in horiz:
        rows[round(l['top'], 1)].append(l)

    print('\n--- %s : %d dimension lines, %d tick marks' % (k.upper(), len(horiz), len(ticks)))
    for y in sorted(rows):
        run = rows[y]
        x_lo = min(l['x0'] for l in run)
        x_hi = max(l['x1'] for l in run)
        near = sorted({round(t['x0'], 1) for t in ticks if abs((t['top'] + t['bottom']) / 2 - y) < 6})
        merged = []
        for x in near:
            if not merged or x - merged[-1] > 1.5:
                merged.append(x)
        if len(merged) < 2:
            continue
        spans = [round((merged[i + 1] - merged[i]) * sc) for i in range(len(merged) - 1)]
        total = round((merged[-1] - merged[0]) * sc)
        print('  chain @y=%6.1f  %-42s  total %5d' %
              (y, ' + '.join(str(s) for s in spans), total))

print()
print('=== vertical chain (first floor, right side) ===')
sc = SCALE['ff']
vband = [l for l in L if l.get('stroking_color') in BLACKS and l['x0'] > 880]
vert = [l for l in vband if abs(l['x0'] - l['x1']) < 0.4 and (l['bottom'] - l['top']) > 30]
vticks = [l for l in vband if abs(l['bottom'] - l['top']) > 0.5 and abs(l['x1'] - l['x0']) > 1.0]
cols = defaultdict(list)
for l in vert:
    cols[round(l['x0'], 1)].append(l)
for x in sorted(cols):
    near = sorted({round(t['top'], 1) for t in vticks if abs(t['x0'] - x) < 7})
    merged = []
    for y in near:
        if not merged or y - merged[-1] > 1.5:
            merged.append(y)
    if len(merged) < 2:
        continue
    spans = [round((merged[i + 1] - merged[i]) * sc) for i in range(len(merged) - 1)]
    print('  chain @x=%6.1f  %-42s  total %5d' %
          (x, ' + '.join(str(s) for s in spans), round((merged[-1] - merged[0]) * sc)))
