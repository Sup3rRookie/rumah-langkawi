import pdfplumber, json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF = str(ROOT / 'data' / 'Langkawi-Interior_Floor_Layout.pdf')
OUT = ROOT / 'dist' / 'rumah-langkawi-3d.html'
GRAY = (0.49804, 0.49804, 0.49804)
RED = (1.0, 0.0, 0.0)
SNAP = 5.0
MINLEN = 120.0
PLANS = {'gf': (200, 560, 7640.0), 'ff': (590, 900, 8460.0)}

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    lines, curves = page.lines, page.curves

def openings(walls):
    """Recover window openings, and strip the lines that mark them.

    In this drawing a window is a glazing line run down the middle of a wall
    band: two parallel wall faces 100-200 mm apart with a third line between
    them, spanning only the opening. Left alone that line extrudes as a thin
    full-height wall sitting inside the wall, which is why windows did not read
    in the model. Returns (windows, kept_walls).
    """
    from collections import defaultdict

    def scan(walls, horiz, banned):
        """One pass over one orientation. `banned` holds lines already known to
        be glazing, so they are not themselves mistaken for wall faces — without
        that, a glazing line pairs with the far face and reports the same window
        twice at two different thicknesses."""
        wins, drop = [], set()
        byc = defaultdict(list)
        for w in walls:
            if horiz and abs(w[1] - w[3]) < 1:
                byc[w[1]].append((min(w[0], w[2]), max(w[0], w[2])))
            elif not horiz and abs(w[0] - w[2]) < 1:
                byc[w[0]].append((min(w[1], w[3]), max(w[1], w[3])))
        cs = sorted(byc)

        # A wall face is normally broken exactly where a window sits, so the
        # glazing line cannot be required to fall inside an unbroken run of it.
        # Test against the face's overall extent instead. That is loose on its
        # own, but the line must also sit strictly between two faces 100-200 mm
        # apart, and nothing but glazing is ever drawn inside a wall.
        extent = {c: (min(s for s, _ in byc[c]), max(e for _, e in byc[c])) for c in cs}

        def covered(span, c, tol=250.0):
            lo_, hi_ = extent[c]
            return lo_ - tol <= span[0] and span[1] <= hi_ + tol

        for i, ca in enumerate(cs):
            if ca in banned:
                continue
            for cb in cs[i + 1:]:
                if cb in banned:
                    continue
                # Real wall bands in this drawing measure 145-165 mm. Holding
                # the window to 130-185 mm is what stops a glazing line pairing
                # with the far face (110 mm) or with an unrelated partition
                # (200 mm) and reporting the same window twice.
                if cb - ca < 130:
                    continue
                if cb - ca > 185:
                    break
                for c in cs:
                    if not (ca + 20 < c < cb - 20):
                        continue
                    for span in byc[c]:
                        if span[1] - span[0] < 400:
                            continue
                        if covered(span, ca) and covered(span, cb):
                            wins.append({'o': 'h' if horiz else 'v',
                                         'c': (ca + cb) / 2.0,
                                         'a': span[0], 'b': span[1],
                                         't': cb - ca})
                            drop.add(('h' if horiz else 'v', c, span[0], span[1]))
        return wins, drop

    wins, drop = [], set()
    for horiz in (True, False):
        # pass 1 finds the glazing lines, pass 2 re-reads the wall bands with
        # those lines excluded so each window is reported once, at the real
        # wall thickness
        w1, d1 = scan(walls, horiz, set())
        wins += w1
        drop |= d1

    # merge anything still overlapping on the same wall
    merged = []
    for w in sorted(wins, key=lambda q: (q['o'], q['a'])):
        hit = None
        for m in merged:
            if (m['o'] == w['o'] and abs(m['c'] - w['c']) <= 150
                    and w['a'] <= m['b'] + 1 and m['a'] <= w['b'] + 1):
                hit = m
                break
        if hit:
            hit['a'] = min(hit['a'], w['a'])
            hit['b'] = max(hit['b'], w['b'])
        else:
            merged.append(dict(w))

    def is_glazing(w):
        if abs(w[1] - w[3]) < 1:
            key = ('h', w[1], min(w[0], w[2]), max(w[0], w[2]))
        elif abs(w[0] - w[2]) < 1:
            key = ('v', w[0], min(w[1], w[3]), max(w[1], w[3]))
        else:
            return False
        return key in drop

    kept = [w for w in walls if not is_glazing(w)]
    return merged, kept


CELL = 50.0          # footprint raster, mm per cell
BALCONY = (895, 13290, 4710, 17375)     # ff balcony, in plan mm
BALCONY_DROP = ('chair',)               # tiers the client wants left out of it


def _join(furn, idxs, tol):
    """union-find over segment endpoints closer than `tol`"""
    parent = {i: i for i in idxs}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    grid = {}
    for i in idxs:
        s = furn[i]
        for p in ((s[0], s[1]), (s[2], s[3])):
            grid.setdefault((int(p[0] // tol), int(p[1] // tol)), []).append(i)
    for i in idxs:
        s = furn[i]
        for p in ((s[0], s[1]), (s[2], s[3])):
            gx, gy = int(p[0] // tol), int(p[1] // tol)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if j == i:
                            continue
                        t = furn[j]
                        for q in ((t[0], t[1]), (t[2], t[3])):
                            if math.dist(p, q) <= tol:
                                ra, rb = find(i), find(j)
                                if ra != rb:
                                    parent[ra] = rb
    g = {}
    for i in idxs:
        g.setdefault(find(i), []).append(i)
    return list(g.values())


def _chains(tiny, anchors, minlen=400.0, minside=250.0, tol=15.0):
    """Keep short chords only when they chain into a real outline.

    An outline traces its own bounding box once or twice. The scribbles that
    draw hanging clothes on a wardrobe rail put 20 m of line into an 85 x 425 mm
    box, so length alone lets them through and they swamp the payload. Width and
    the length-to-perimeter ratio are what tell a shape from a scribble.

    `anchors` are the chords already long enough to keep. They take part in the
    chaining but are not returned: one drawn outline switches between long and
    short chords as its curvature changes, and without them a single shape reads
    as several disconnected arcs, none of them wide enough to survive.
    """
    segs = tiny + anchors
    n = len(segs)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    grid = {}
    for i, s in enumerate(segs):
        for p in ((s[0], s[1]), (s[2], s[3])):
            grid.setdefault((int(p[0] // tol), int(p[1] // tol)), []).append(i)
    for i, s in enumerate(segs):
        for p in ((s[0], s[1]), (s[2], s[3])):
            gx, gy = int(p[0] // tol), int(p[1] // tol)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if j == i:
                            continue
                        t = segs[j]
                        for q in ((t[0], t[1]), (t[2], t[3])):
                            if math.dist(p, q) <= tol:
                                ra, rb = find(i), find(j)
                                if ra != rb:
                                    parent[ra] = rb
    run = {}
    for i, s in enumerate(segs):
        r = find(i)
        c = run.setdefault(r, [0.0, [], [1e9, 1e9, -1e9, -1e9]])
        c[0] += math.dist((s[0], s[1]), (s[2], s[3]))
        if i < len(tiny):
            c[1].append(s)
        c[2][0] = min(c[2][0], s[0], s[2])
        c[2][1] = min(c[2][1], s[1], s[3])
        c[2][2] = max(c[2][2], s[0], s[2])
        c[2][3] = max(c[2][3], s[1], s[3])
    out = []
    for total, ss, b in run.values():
        w, d = b[2] - b[0], b[3] - b[1]
        if total < minlen or min(w, d) < minside:
            continue
        if total > 4.0 * 2 * (w + d):
            continue
        out += ss
    return out


def _bbox(furn, idxs):
    gx = [v for i in idxs for v in (furn[i][0], furn[i][2])]
    gy = [v for i in idxs for v in (furn[i][1], furn[i][3])]
    return [min(gx), min(gy), max(gx), max(gy)]


def _burn(furn, idxs, ox, oy, R, C):
    """draw the linework onto an occupancy grid by walking each segment"""
    m = [bytearray(C) for _ in range(R)]
    for i in idxs:
        s = furn[i]
        n = max(1, int(math.dist((s[0], s[1]), (s[2], s[3])) / (CELL * 0.4)))
        for t in range(n + 1):
            u = t / n
            cx = int((s[0] + (s[2] - s[0]) * u - ox) / CELL)
            cy = int((s[1] + (s[3] - s[1]) * u - oy) / CELL)
            if 0 <= cy < R and 0 <= cx < C:
                m[cy][cx] = 1
    return m


def _dilate(m, R, C):
    o = [bytearray(C) for _ in range(R)]
    for y in range(R):
        row = m[y]
        for x in range(C):
            if row[x]:
                for yy in range(max(0, y - 1), min(R, y + 2)):
                    orow = o[yy]
                    for xx in range(max(0, x - 1), min(C, x + 2)):
                        orow[xx] = 1
    return o


def _erode(m, R, C):
    o = [bytearray(C) for _ in range(R)]
    for y in range(1, R - 1):
        a, b, c = m[y - 1], m[y], m[y + 1]
        for x in range(1, C - 1):
            if (b[x] and b[x - 1] and b[x + 1] and a[x] and c[x]
                    and a[x - 1] and a[x + 1] and c[x - 1] and c[x + 1]):
                o[y][x] = 1
    return o


def _enclosed(m, R, C):
    """flood in from the padded border; whatever it cannot reach is inside the
    outline, which is how an open drawing becomes a solid footprint"""
    from collections import deque
    seen = [bytearray(C) for _ in range(R)]
    q = deque()
    for y in range(R):
        for x in (0, C - 1):
            if not m[y][x] and not seen[y][x]:
                seen[y][x] = 1
                q.append((y, x))
    for x in range(C):
        for y in (0, R - 1):
            if not m[y][x] and not seen[y][x]:
                seen[y][x] = 1
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < R and 0 <= xx < C and not seen[yy][xx] and not m[yy][xx]:
                seen[yy][xx] = 1
                q.append((yy, xx))
    return [bytearray(0 if seen[y][x] else 1 for x in range(C)) for y in range(R)]


def _split(fill, R, C, minc=24):
    """Break a footprint at thin necks.

    Two pieces that only touch — a wardrobe meeting the corner of a bed, a chair
    pushed against a table — join at a neck a few cells wide. Eroding kills the
    neck but leaves each piece's core, so the cores label out separately and can
    then be grown back over the full footprint. Returns a label grid, or None
    when there is only one piece to find.
    """
    from collections import deque
    core = _erode(fill, R, C)
    lab = [[0] * C for _ in range(R)]
    sizes = []
    for y in range(R):
        for x in range(C):
            if core[y][x] and not lab[y][x]:
                n = len(sizes) + 1
                cnt = 0
                q = deque([(y, x)])
                lab[y][x] = n
                while q:
                    cy, cx = q.popleft()
                    cnt += 1
                    for yy, xx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                        if 0 <= yy < R and 0 <= xx < C and core[yy][xx] and not lab[yy][xx]:
                            lab[yy][xx] = n
                            q.append((yy, xx))
                sizes.append(cnt)
    keep = [i + 1 for i, s in enumerate(sizes) if s >= minc]
    if len(keep) < 2:
        return None
    remap = {v: i + 1 for i, v in enumerate(keep)}
    q = deque()
    for y in range(R):
        for x in range(C):
            lab[y][x] = remap.get(lab[y][x], 0)
            if lab[y][x]:
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < R and 0 <= xx < C and fill[yy][xx] and not lab[yy][xx]:
                lab[yy][xx] = lab[y][x]
                q.append((yy, xx))
    return lab, len(keep)


def _maxrect(m, R, C):
    """largest all-filled axis-aligned rectangle, by the histogram stack method"""
    h = [0] * C
    best = (0, 0, 0, 0, 0)
    for y in range(R):
        row = m[y]
        for x in range(C):
            h[x] = h[x] + 1 if row[x] else 0
        st = []
        for x in range(C + 1):
            cur = h[x] if x < C else 0
            start = x
            while st and st[-1][1] >= cur:
                sx, sh = st.pop()
                a = sh * (x - sx)
                if a > best[0]:
                    best = (a, y - sh + 1, sx, y, x - 1)
                start = sx
            st.append((start, cur))
    return best


def _cover(m, R, C, maxr=6):
    """Greedy rectangle cover of the footprint.

    Rectangles rather than a polygon because three.js extrudes a BoxGeometry for
    free, and because a handful of merged rectangles is a fraction of the payload
    of per-cell data. An L comes out in two, a plain carcass in one.
    """
    m = [bytearray(r) for r in m]
    tot = sum(sum(r) for r in m)
    if not tot:
        return []
    got, out = 0, []
    while got < tot * 0.93 and len(out) < maxr:
        a, r0, c0, r1, c1 = _maxrect(m, R, C)
        if a <= 0:
            break
        for y in range(r0, r1 + 1):
            row = m[y]
            for x in range(c0, c1 + 1):
                if row[x]:
                    row[x] = 0
                    got += 1
        out.append((r0, c0, r1, c1))
    return out


def massing(furn, n_line, keepout=None, tol=30.0):
    """Group the plan's furniture linework into pieces and give each its footprint.

    The PDF gives loose red segments, not closed outlines. An earlier pass joined
    them at 80 mm and took each group's bounding box, which cannot say L: the
    kitchen return read as one 11 m2 slab, and a chair touching a table outline
    dragged the whole dining set into a single block.

    So: join tight (30 mm) so each drawn stroke stays its own thing, then merge
    strokes whose boxes sit inside one another — outline, hatching and cushion
    lines all overlap the piece they belong to, whereas a chair beside a table
    does not. What that still cannot separate is two pieces drawn corner to
    corner, so the footprint raster is split at thin necks afterwards.

    Segments from index `n_line` on come from PDF rects, four to a piece. Those
    are already complete closed outlines, so they seed their own groups and are
    never chained: a wardrobe drawn butted against a bed shares an edge, and no
    endpoint rule can tell that apart from one piece.

    Heights are a size heuristic, not data — the drawing carries no furniture
    schedule. They give scale and occlusion for judging paint, nothing more.
    """
    groups = _join(furn, list(range(n_line)), tol)
    groups += [list(range(i, i + 4)) for i in range(n_line, len(furn), 4)]
    boxes = [_bbox(furn, g) for g in groups]

    def ov(a, b):
        return (max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
                * max(0.0, min(a[3], b[3]) - max(a[1], b[1])))

    def ar(a):
        return max(1.0, (a[2] - a[0]) * (a[3] - a[1]))

    def curvy(g):
        """a traced outline: many chords, all of them short"""
        if len(g) < 20:
            return False
        tot = sum(math.dist((furn[i][0], furn[i][1]), (furn[i][2], furn[i][3])) for i in g)
        return tot / len(g) < 120

    curved = [curvy(g) for g in groups]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(len(groups) - 1, i, -1):
                # A curve switches between long and short chords as it bends, so
                # one drawn shape can reach the raster as two arcs that overlap
                # without either containing the other. Nothing else in the plan
                # is two overlapping runs of short chords, so they can be joined
                # on much less overlap than a carcass and its hatching need.
                need = 0.20 if (curved[i] and curved[j]) else 0.45
                if ov(boxes[i], boxes[j]) > need * min(ar(boxes[i]), ar(boxes[j])):
                    groups[i] += groups.pop(j)
                    curved[i] = curved[i] or curved.pop(j)
                    boxes.pop(j)
                    boxes[i] = _bbox(furn, groups[i])
                    merged = True
            if merged:
                break

    def module_run(a, b):
        """Are these two blocks arms of one modular piece?

        A sectional sofa is drawn as separate cushion blocks and nothing about
        one block says sofa. Worse, where the L turns the plan leaves the join
        open — the west sofa's right face is only drawn below the corner — so
        the arm cannot even flood-fill closed until the leg is merged in.

        Depth is the test that works. Two arms of one piece are the same depth
        and butt flush at one end; a chair pushed against a dining table is 450
        against 1050 and fails on that alone. Length is free to differ, because
        an L's long arm runs past its short one by definition.
        """
        aw, ad = a[2] - a[0], a[3] - a[1]
        bw, bd = b[2] - b[0], b[3] - b[1]
        da, db = min(aw, ad), min(bw, bd)
        if not (400 <= da <= 1400 and 400 <= db <= 1400):
            return False
        if max(da, db) / min(da, db) > 1.35:
            return False
        if ar(a) > 6.0e6 or ar(b) > 6.0e6:
            return False
        if max(a[0] - b[2], b[0] - a[2]) <= 60:          # side by side in x
            lap = min(a[3], b[3]) - max(a[1], b[1])
            if (lap >= 0.7 * min(ad, bd)
                    and (abs(a[1] - b[1]) <= 120 or abs(a[3] - b[3]) <= 120)):
                return True
        if max(a[1] - b[3], b[1] - a[3]) <= 60:          # end to end in z
            lap = min(a[2], b[2]) - max(a[0], b[0])
            if (lap >= 0.7 * min(aw, bw)
                    and (abs(a[0] - b[0]) <= 120 or abs(a[2] - b[2]) <= 120)):
                return True
        return False

    # Union-find on the original boxes, not one merge at a time: a three-block
    # run has to stay a run, and by the third block a growing box no longer
    # looks the same size as the module it is trying to pick up.
    par = list(range(len(groups)))

    def root(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            if module_run(boxes[i], boxes[j]):
                ra, rb = root(i), root(j)
                if ra != rb:
                    par[ra] = rb
    runs = {}
    for i in range(len(groups)):
        runs.setdefault(root(i), []).extend(groups[i])
    groups = list(runs.values())

    import os
    _dbg = [float(v) for v in os.environ['MASSDEBUG'].split(',')] if os.environ.get('MASSDEBUG') else None

    pieces = []
    for g in groups:
        b = _bbox(furn, g)
        if _dbg and _dbg[0] <= b[0] and b[2] <= _dbg[2] and _dbg[1] <= b[1] and b[3] <= _dbg[3]:
            print('   GROUP %6.0f %6.0f %6.0f %6.0f segs=%d' % (b[0], b[1], b[2], b[3], len(g)))
        # detail lines, hatching, noise. The min-side test drops leader lines and
        # dimension ticks, which pass on area alone and then extrude as fins.
        if ((b[2] - b[0]) * (b[3] - b[1]) < 0.15e6
                or min(b[2] - b[0], b[3] - b[1]) < 250):
            continue
        # the stair is outlined in red like furniture; it is already modelled
        if keepout and ov(b, keepout) > 0.6 * ar(b):
            continue
        pad = 2
        C = int((b[2] - b[0]) / CELL) + 1 + 2 * pad
        R = int((b[3] - b[1]) / CELL) + 1 + 2 * pad
        ox, oy = b[0] - pad * CELL, b[1] - pad * CELL
        fill = _erode(_enclosed(_dilate(_burn(furn, g, ox, oy, R, C), R, C), R, C), R, C)
        n_fill = sum(sum(r) for r in fill)
        solid = n_fill * CELL * CELL / ar(b)
        # planters and hatch bursts are open linework with nothing enclosed, so
        # there is no footprint to read; a chair's doubled outline does enclose
        # one but tracing it only buys a 50 mm step. Both want the box.
        if solid < 0.30 or ar(b) < 0.8e6:
            pieces.append((b, [list(b)], len(g)))
            continue
        parts = _split(fill, R, C)
        masks = []
        if parts:
            lab, nlab = parts
            for v in range(1, nlab + 1):
                masks.append([bytearray(1 if lab[y][x] == v else 0 for x in range(C))
                              for y in range(R)])
        else:
            masks = [fill]
        for mk in masks:
            rects = []
            for r0, c0, r1, c1 in _cover(mk, R, C):
                r = [ox + c0 * CELL, oy + r0 * CELL,
                     ox + (c1 + 1) * CELL, oy + (r1 + 1) * CELL]
                # a rectangle narrower than any real carcass is the offset
                # between a doubled outline, not a leg of the shape
                if min(r[2] - r[0], r[3] - r[1]) >= 150:
                    rects.append(r)
            if not rects:
                rects = [list(b)]
            pb = [min(r[0] for r in rects), min(r[1] for r in rects),
                  max(r[2] for r in rects), max(r[3] for r in rects)]
            if ((pb[2] - pb[0]) * (pb[3] - pb[1]) < 0.15e6
                    or min(pb[2] - pb[0], pb[3] - pb[1]) < 250):
                continue
            if ar(pb) < 0.8e6:
                rects = [list(pb)]
            n_seg = len(g) if len(masks) == 1 else sum(
                1 for i in g
                if mk[min(R - 1, max(0, int(((furn[i][1] + furn[i][3]) / 2 - oy) / CELL)))]
                     [min(C - 1, max(0, int(((furn[i][0] + furn[i][2]) / 2 - ox) / CELL)))])
            pieces.append((pb, rects, n_seg))

    out = []
    for b, rects, n_seg in pieces:
        w, d = b[2] - b[0], b[3] - b[1]
        # measure the piece by what is actually emitted: the rectangles cover the
        # footprint and never overlap, so their sum is the real plan area and
        # their share of the box is how far off rectangular the piece is
        area = sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects) / 1e6
        solid = area * 1e6 / ar(b)
        ratio = max(w, d) / max(1.0, min(w, d))
        # Planters and round tables are drawn as many short segments around a
        # small near-square outline; real carcasses are a handful of long ones.
        dense = n_seg / max(1.0, area)
        # deepest rectangle in the piece: cabinetry runs stay shallow whatever
        # their length, seating and beds do not
        short = max(min(r[2] - r[0], r[3] - r[1]) for r in rects)

        if area >= 5.0 and solid > 0.82:
            tier = 'rug'
        elif area <= 0.75 and ratio < 1.5 and dense > 28:
            tier = 'plant'
        elif area <= 0.55 and ratio < 1.45 and dense > 14:
            tier = 'round'
        elif area >= 0.80 and short <= 800:
            tier = 'counter'
        elif area >= 2.0 and solid < 0.78:
            tier = 'sofa'                        # an L or a U is seating
        elif area >= 2.0 and min(w, d) >= 1100:
            tier = 'bed'                         # nothing you sit on is that deep
        elif area >= 2.0:
            tier = 'sofa'
        elif area >= 0.75:
            tier = 'table'
        else:
            tier = 'chair'
        out.append([b[0], b[1], b[2], b[3], rects, tier, area])

    # A dining table and a sofa are the same box at this scale; what tells them
    # apart is the ring of chairs. Four or more is a setting, two is a bedside.
    seats = [p for p in out if p[6] <= 0.42]
    for p in out:
        if p[5] not in ('sofa', 'bed'):
            continue
        near = 0
        for q in seats:
            cx, cz = (q[0] + q[2]) / 2, (q[1] + q[3]) / 2
            if p[0] <= cx <= p[2] and p[1] <= cz <= p[3]:
                continue
            if p[0] - 900 <= cx <= p[2] + 900 and p[1] - 900 <= cz <= p[3] + 900:
                near += 1
        if near >= 4:
            p[5] = 'table'

    # A coffee table is a low slab parked in front of seating. Its own size says
    # nothing — at 0.7 x 1.2 m it reads as cabinetry — but its position does:
    # nothing else of that size sits against a sofa. Holding it to oblong is what
    # keeps the armchair beside the same sofa out, that being near-square. A
    # square one is only accepted if it also sits in the run between the sofa and
    # the console facing it, which is the arrangement the room is set out for.
    sofas = [p for p in out if p[5] == 'sofa']
    counters = [p for p in out if p[5] == 'counter']

    def between(p, s):
        """does p sit in the run between sofa s and a console facing it?"""
        cx, cz = (p[0] + p[2]) / 2, (p[1] + p[3]) / 2
        for c in counters:
            if (min(s[2], c[2]) < cx < max(s[0], c[0])
                    and max(s[1], c[1]) <= cz <= min(s[3], c[3])):
                return True
            if (min(s[3], c[3]) < cz < max(s[1], c[1])
                    and max(s[0], c[0]) <= cx <= min(s[2], c[2])):
                return True
        return False

    for p in out:
        if p[5] not in ('table', 'counter', 'chair', 'round'):
            continue
        if not 0.30 <= p[6] <= 1.6:
            continue
        w, d = p[2] - p[0], p[3] - p[1]
        oblong = max(w, d) / max(1.0, min(w, d)) >= 1.4
        for s in sofas:
            if not (s[0] - 1200 <= p[2] and p[0] <= s[2] + 1200
                    and s[1] - 1200 <= p[3] and p[1] <= s[3] + 1200):
                continue
            if oblong or between(p, s):
                p[5] = 'coffee'
                break
    return [p[:6] for p in out]


data = {}
STAIRBOX = {}
for key, (lo, hi, known_w) in PLANS.items():
    def inb(o):
        return lo < o['x0'] < hi and 100 < o['top'] < 620

    wl = [l for l in lines if l.get('stroking_color') in (GRAY, 0, (0.0, 0.0, 0.0)) and inb(l)]
    rl = [l for l in lines if l.get('stroking_color') == RED and inb(l)]
    rc = [c for c in curves if c.get('stroking_color') == RED and inb(c)]
    rr = [r for r in page.rects if r.get('stroking_color') == RED and inb(r)]

    xs = [v for l in wl for v in (l['x0'], l['x1'])]
    ys = [v for l in wl for v in (l['top'], l['bottom'])]
    x0, y0 = min(xs), min(ys)
    scale = known_w / (max(xs) - x0)
    def P(x, y):
        return (round((x - x0) * scale / SNAP) * SNAP, round((y - y0) * scale / SNAP) * SNAP)

    segs = set()
    for l in wl:
        a, b = P(l['x0'], l['top']), P(l['x1'], l['bottom'])
        if math.dist(a, b) >= MINLEN:
            segs.add(tuple(sorted([a, b])))

    def merge(axis):
        g = {}
        for a, b in segs:
            if axis == 'h' and abs(a[1] - b[1]) < 1:
                g.setdefault(a[1], []).append((min(a[0], b[0]), max(a[0], b[0])))
            elif axis == 'v' and abs(a[0] - b[0]) < 1:
                g.setdefault(a[0], []).append((min(a[1], b[1]), max(a[1], b[1])))
        r = []
        for c, iv in g.items():
            iv.sort(); cur = list(iv[0])
            for s, e in iv[1:]:
                if s <= cur[1] + SNAP: cur[1] = max(cur[1], e)
                else: r.append((c, tuple(cur))); cur = [s, e]
            r.append((c, tuple(cur)))
        return r

    walls = []
    for c, (s, e) in merge('h'):
        if e - s >= MINLEN: walls.append([s, c, e, c])
    for c, (s, e) in merge('v'):
        if e - s >= MINLEN: walls.append([c, s, c, e])
    for a, b in segs:
        if abs(a[0] - b[0]) > 1 and abs(a[1] - b[1]) > 1:
            walls.append([a[0], a[1], b[0], b[1]])

    furn, tiny = [], []
    for l in rl:
        a, b = P(l['x0'], l['top']), P(l['x1'], l['bottom'])
        d = math.dist(a, b)
        if d > 60:
            furn.append([a[0], a[1], b[0], b[1]])
        elif d > 5:
            tiny.append([a[0], a[1], b[0], b[1]])
    for c in rc:
        p = [P(*q) for q in c['pts']]
        for i in range(len(p) - 1):
            d = math.dist(p[i], p[i + 1])
            if d > 60:
                furn.append([p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]])
            elif d > 5:
                tiny.append([p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]])
    # Smooth outlines are drawn as chains of 20-40 mm chords, split across both
    # lines and curves. Judged one chord at a time they read as noise and were
    # thrown away, which is why the round coffee table never reached the model.
    # Judged as a chain they are unmistakable, and a hanger tick still is not.
    furn += _chains(tiny, furn)
    # Whole pieces are drawn as PDF rects, not lines: the dining table, the
    # wardrobe runs, most bed carcasses. Read as lines only, they were missing
    # from the model entirely, which is why the dining set was chairs and air.
    n_line = len(furn)
    for r in rr:
        a, b = P(r['x0'], r['top']), P(r['x1'], r['bottom'])
        if abs(b[0] - a[0]) < 60 or abs(b[1] - a[1]) < 60:
            continue
        furn += [[a[0], a[1], b[0], a[1]], [b[0], a[1], b[0], b[1]],
                 [b[0], b[1], a[0], b[1]], [a[0], b[1], a[0], a[1]]]

    from collections import defaultdict
    runs = defaultdict(list)
    for w in walls:
        if w[0] == w[2]:
            runs[(w[1], w[3])].append(w[0])
    treads = set()
    for (ya, yb), xs2 in runs.items():
        xs2 = sorted(xs2)
        if len(xs2) < 5:
            continue
        d = [xs2[i + 1] - xs2[i] for i in range(len(xs2) - 1)]
        if sum(1 for v in d if 250 < v < 330) >= 4:
            for x in xs2:
                treads.add((x, ya, x, yb))
    walls = [w for w in walls if tuple(w) not in treads]
    n_t = len(treads)
    n_i = 0
    if treads:
        tx = [v for t in treads for v in (t[0], t[2])]
        ty = [v for t in treads for v in (t[1], t[3])]
        allx = sorted({w[0] for w in walls if w[0] == w[2]})
        ally = sorted({w[1] for w in walls if w[1] == w[3]})
        bx0 = max([v for v in allx if v <= min(tx)], default=min(tx))
        bx1 = min([v for v in allx if v >= max(tx)], default=max(tx))
        by0 = max([v for v in ally if v <= min(ty)], default=min(ty))
        by1 = min([v for v in ally if v >= max(ty)], default=max(ty))
        def interior(w):
            inside = (bx0 - 1 <= w[0] <= bx1 + 1 and bx0 - 1 <= w[2] <= bx1 + 1 and
                      by0 - 1 <= w[1] <= by1 + 1 and by0 - 1 <= w[3] <= by1 + 1)
            onedge = (abs(w[0] - bx0) < 2 or abs(w[0] - bx1) < 2 or abs(w[2] - bx0) < 2 or
                      abs(w[2] - bx1) < 2 or abs(w[1] - by0) < 2 or abs(w[1] - by1) < 2 or
                      abs(w[3] - by0) < 2 or abs(w[3] - by1) < 2)
            return inside and not onedge
        keep = [w for w in walls if not interior(w)]
        n_i = len(walls) - len(keep)
        walls = keep
        STAIRBOX[key] = (bx0, by0, bx1, by1)
    print('   %s: removed %d tread lines, %d stairwell partitions' % (key, n_t, n_i))

    stair = well = guard = stair_below = parapet = parapet_cut = None
    SL = None
    if key == 'gf':
        # Half-turn stair with a straight half-space landing, set out from the
        # plan's own nosing lines. Both flights run along X and stop at x=6520;
        # the 970 mm strip at the EAST end is a flat landing, not steps.
        #   flight A  z 6525..7365   x 4490..6520   7 treads at 290 mm
        #   landing   x 6520..7490   z 6525..9560   flat, at half height
        #   flight B  z 8530..9560   x 6520..4490   7 treads at 290 mm
        # 8 risers per flight => 16 risers floor to floor.
        #
        # NOTE: the plan does carry four nosing-spaced lines across the landing
        # strip (z 7365/7655/7950/8235/8530 at 290/295/285/295). Read literally
        # those are winders, which is how an earlier pass modelled it. The
        # client's photograph of the built stair shows a straight landing, so
        # the landing wins and those lines are treated as setting-out only.
        stair = dict(x_low=4490, x_turn=6520, x_east=7490,
                     fa=[6525, 7365], fb=[8530, 9560],
                     treads_a=7, treads_b=7, risers=16)

        # These are stair setting-out lines, not walls. Left in, they extrude
        # as 3 m slabs and box the stairwell in. Drop them so the flights read
        # as an open stair with a balustrade. The x=4490 run is the line closing
        # off the head of flight B — the wall the stair appeared to run into.
        SL = [('h', 6525, 4490, 7490), ('h', 7365, 4490, 7490),
              ('h', 8530, 4490, 7490), ('v', 6520, 6525, 9560),
              ('v', 4490, 8530, 9705),
              ('hband', 7366, 8529, 6520, 7490)]

    if key == 'ff':
        # The first floor repeats the same stairwell, offset +820 mm in X
        # (the FF plan is 8460 wide against the GF's 7640; z is common):
        #   4490 -> 5310, 6520 -> 7340, 7490 -> 8310.
        # There is no stair to draw up here — what belongs on this floor is the
        # void the stair rises into, plus a guard along its open west edge.
        well = [5310, 6520, 8310, 9545]
        guard = [[5310, 6520, 5310, 8515]]   # stops short of the arrival gap
        # The same stair, in FF coordinates, so the first floor can show it
        # arriving from below instead of an empty hole in the slab.
        stair_below = dict(x_low=5310, x_turn=7340, x_east=8310,
                           fa=[6520, 7355], fb=[8515, 9545],
                           treads_a=7, treads_b=7, risers=16)

        # Balcony: the space with the planters, up to the door. Its west and
        # south edges are the building perimeter and want a waist-high parapet
        # rather than a wall.
        #
        # Both edges are full wall BANDS, not single lines: west 745/895 and
        # south 17375/17530. Dropping only the inner face leaves the outer one
        # standing full height, which reads as two walls stacked. Both faces
        # have to go. They also run past the balcony (x=745 carries on north to
        # z 9695, z=17530 carries on east to x 6015), so the balcony stretch is
        # clipped out and the rest of each run stays a wall.
        parapet = [[820, 13270, 820, 17452], [820, 17452, 4710, 17452]]
        parapet_cut = [('v', 745, 13270, 17530), ('v', 895, 13270, 17375),
                       ('h', 17530, 745, 4710), ('h', 17375, 895, 4710)]
        # x=5310 runs on to z 9695 where it meets the south wall, so the range
        # has to reach past the well or the whole line survives and stands as a
        # 3 m wall right at the stair. x=5380 is a second line down the well.
        SL = [('h', 6520, 5310, 8310), ('h', 7355, 5310, 8310),
              ('h', 8515, 5310, 8310), ('v', 7340, 6520, 9545),
              ('v', 5310, 6520, 9700), ('v', 5380, 7355, 9545),
              ('hband', 7356, 8514, 7340, 8310)]

    if SL:
        def stairline(w):
            for r in SL:
                if r[0] == 'hband':
                    _, z0, z1, a, b = r
                    if (abs(w[1] - w[3]) < 1 and z0 <= w[1] <= z1
                            and min(w[0], w[2]) >= a - 3 and max(w[0], w[2]) <= b + 3):
                        return True
                    continue
                kind, c, a, b = r
                if kind == 'h' and abs(w[1] - w[3]) < 1 and abs(w[1] - c) < 3:
                    if min(w[0], w[2]) >= a - 3 and max(w[0], w[2]) <= b + 3:
                        return True
                if kind == 'v' and abs(w[0] - w[2]) < 1 and abs(w[0] - c) < 3:
                    if min(w[1], w[3]) >= a - 3 and max(w[1], w[3]) <= b + 3:
                        return True
            return False

        n_before = len(walls)
        walls = [w for w in walls if not stairline(w)]
        print('   %s: removed %d stair setting-out lines' % (key, n_before - len(walls)))

    if parapet_cut:
        def clip(ws, cuts):
            out, n = [], 0
            for w in ws:
                horiz, vert = abs(w[1] - w[3]) < 1, abs(w[0] - w[2]) < 1
                if not (horiz or vert):
                    out.append(w)
                    continue
                c = w[1] if horiz else w[0]
                lo_ = min(w[0], w[2]) if horiz else min(w[1], w[3])
                hi_ = max(w[0], w[2]) if horiz else max(w[1], w[3])
                spans = [(lo_, hi_)]
                for kind, cc, a, b in cuts:
                    if (kind == 'h') != horiz or abs(cc - c) > 4:
                        continue
                    nxt = []
                    for p, q in spans:
                        if b <= p or a >= q:
                            nxt.append((p, q))
                            continue
                        n += 1
                        if p < a - 1:
                            nxt.append((p, a))
                        if b + 1 < q:
                            nxt.append((b, q))
                    spans = nxt
                for p, q in spans:
                    if q - p < 60:
                        continue
                    out.append([p, c, q, c] if horiz else [c, p, c, q])
            return out, n

        walls, n_cut = clip(walls, parapet_cut)
        print('   %s: opened %d wall runs along the balcony edges' % (key, n_cut))
    n_pre = len(walls)
    wins, walls = openings(walls)
    print('   %s: %d window openings, %d glazing lines pulled out of the walls'
          % (key, len(wins), n_pre - len(walls)))
    for q in wins:
        print('      %s wall at %-7.0f  %6.0f..%-6.0f  width %5.0f  thk %3.0f'
              % (q['o'], q['c'], q['a'], q['b'], q['b'] - q['a'], q['t']))

    # The stair is outlined in red, same as furniture, and reads as a 9 m2 U.
    # It is already modelled properly, so keep massing out of its footprint.
    keepout = None
    if stair:
        keepout = [stair['x_low'], stair['fa'][0], stair['x_east'], stair['fb'][1]]
    elif well:
        keepout = well
    furn3d = massing(furn, n_line, keepout)

    # Client instruction about one room, not an extraction problem, so it reads
    # as one. The balcony is to be furnished with the sofa alone: the armchairs
    # and the side table ARE drawn in the plan and come through correctly, and
    # are being suppressed on request. Widen BALCONY_DROP to strip it further.
    if key == 'ff':
        n_before = len(furn3d)
        furn3d = [f for f in furn3d
                  if not (f[5] in BALCONY_DROP
                          and BALCONY[0] <= (f[0] + f[2]) / 2 <= BALCONY[2]
                          and BALCONY[1] <= (f[1] + f[3]) / 2 <= BALCONY[3])]
        print('   %s: %d balcony seats suppressed at the client request'
              % (key, n_before - len(furn3d)))
    w_mm, d_mm = round((max(xs) - x0) * scale), round((max(ys) - y0) * scale)

    # Each plan is centred on its own width, but the FF plan is 820 mm west of
    # the GF one and 820 mm wider, so centring alone leaves them 410 mm out of
    # register. Stacked view needs that corrected or the stairwell void does not
    # sit over the stair. Z needs no correction: the common z 6525/6520 lands
    # within 6 mm. The 820 mm is measured — GF 4490/6520/7490 map to FF
    # 5310/7340/8310 exactly.
    align = None
    if key == 'ff':
        align = -(820 - w_mm / 2 + data['gf']['w'] / 2)

    data[key] = dict(w=w_mm, d=d_mm,
                     walls=walls, furn=furn, furn3d=furn3d, stair=stair,
                     well=well, guard=guard, align=align,
                     stair_below=stair_below, wins=wins, parapet=parapet)
    from collections import Counter
    print(key, data[key]['w'], 'x', data[key]['d'], 'walls', len(walls),
          'furn', len(furn), '->', len(furn3d), 'pieces,',
          sum(len(f[4]) for f in furn3d), 'footprint rects')
    print('   %s: %s' % (key, dict(Counter(f[5] for f in furn3d))))

blob = json.dumps(data, separators=(',', ':'))
print('embedded payload', round(len(blob) / 1024), 'KB')

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rumah Langkawi — full house</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Old+Mincho&family=Zen+Kaku+Gothic+New:wght@400;500&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
:root{--ink:#16171a;--ink2:#1e2024;--ink3:#282b30;--line:rgba(255,255,255,.10);
--line2:rgba(255,255,255,.20);--bone:#e9e6dd;--dim:#9b988f;--faint:#6d6b65;--live:#8fb8a8;
--sans:"Zen Kaku Gothic New",system-ui,sans-serif;--serif:"Zen Old Mincho",serif;--mono:"IBM Plex Mono",monospace}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--ink);color:var(--bone);font-family:var(--sans);font-size:14px;
display:flex;flex-direction:column;overflow:hidden;-webkit-font-smoothing:antialiased}
button,select,input{font:inherit;color:inherit}
header{flex:none;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
padding:13px 20px;border-bottom:1px solid var(--line)}
header h1{font-family:var(--serif);font-weight:400;font-size:19px;margin:0;letter-spacing:.02em}
header .sub{font-size:11px;color:var(--faint);letter-spacing:.09em;text-transform:uppercase}
header .spacer{flex:1}
.seg{display:flex;gap:2px;background:var(--ink2);border:1px solid var(--line);border-radius:2px;padding:2px}
.seg button{background:none;border:0;border-radius:2px;padding:5px 13px;font-size:12px;
color:var(--dim);cursor:pointer;letter-spacing:.03em}
.seg button[aria-pressed=true]{background:var(--ink3);color:var(--bone)}
main{flex:1;display:flex;min-height:0}
#stage{flex:1;position:relative;min-width:0;background:#0e0f11}
#stage canvas{display:block;width:100%;height:100%;touch-action:none;cursor:crosshair}
.overlay{position:absolute;background:rgba(14,15,17,.74);border:1px solid var(--line);
border-radius:2px;backdrop-filter:blur(6px)}
.tl{left:16px;top:16px;padding:2px}
.bl{left:16px;bottom:16px;padding:8px 11px;font-size:11px;color:var(--faint);letter-spacing:.04em}
.tr{right:16px;top:16px;padding:10px;width:158px}
.lbl{font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--faint);margin-bottom:7px}
.chip{height:34px;border-radius:2px;border:1px solid var(--line)}
.cap{font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:5px}
aside{flex:none;width:300px;border-left:1px solid var(--line);overflow-y:auto;padding:18px 20px 40px}
.grp{margin-bottom:24px}
.grp>h2{font-size:10px;font-weight:500;letter-spacing:.14em;text-transform:uppercase;
color:var(--faint);margin:0 0 11px;padding-bottom:7px;border-bottom:1px solid var(--line)}
.row{display:flex;align-items:center;gap:9px;margin-bottom:8px}
.row label{flex:none;width:74px;font-size:12px;color:var(--dim)}
select,input[type=number]{flex:1;min-width:0;background:var(--ink2);border:1px solid var(--line);
border-radius:2px;padding:6px 8px;font-size:12px}
input[type=number]{font-family:var(--mono)}
select:focus-visible,input:focus-visible,button:focus-visible{outline:2px solid var(--live);outline-offset:1px}
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;background:none;cursor:pointer;margin:0}
input[type=range]::-webkit-slider-runnable-track{height:2px;background:var(--line2)}
input[type=range]::-moz-range-track{height:2px;background:var(--line2)}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:13px;height:13px;
border-radius:50%;background:var(--bone);margin-top:-5.5px}
input[type=range]::-moz-range-thumb{width:13px;height:13px;border:0;border-radius:50%;background:var(--bone)}
.sun-read{display:flex;align-items:baseline;gap:9px;margin-bottom:8px}
.sun-read .h{font-family:var(--mono);font-size:21px}
.sun-read .d{font-size:11px;color:var(--dim);line-height:1.4}
.ticks{display:flex;justify-content:space-between;font-family:var(--mono);font-size:9px;color:var(--faint);margin-top:4px}
.pal{display:grid;grid-template-columns:repeat(6,1fr);gap:5px}
.pal button{aspect-ratio:1;border:1px solid var(--line2);border-radius:2px;cursor:pointer;padding:0}
.pal button[aria-pressed=true]{outline:2px solid var(--live);outline-offset:1px}
.note{font-size:11px;line-height:1.55;color:var(--faint);margin:10px 0 0}
.stat{font-family:var(--mono);font-size:12px;color:var(--bone)}
.spec{width:100%;background:var(--ink2);border:1px solid var(--line2);border-radius:2px;
padding:9px;font-size:12px;cursor:pointer}
.spec:hover{background:var(--ink3)}
@media (max-width:840px){main{flex-direction:column}#stage{height:50vh;flex:none}
aside{width:100%;border-left:0;border-top:1px solid var(--line)}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<header>
<h1>Rumah Langkawi</h1><span class="sub">full house · from plan geometry</span>
<span class="spacer"></span>
<div class="seg" role="group" aria-label="Floor">
<button id="fBoth" aria-pressed="true">Both</button>
<button id="fGf" aria-pressed="false">Ground</button>
<button id="fFf" aria-pressed="false">First</button></div>
<div class="seg" role="group" aria-label="Layout">
<button id="lSide" aria-pressed="true">Side by side</button>
<button id="lStack" aria-pressed="false">Stacked</button></div>
</header>
<main>
<div id="stage">
<div class="overlay tl seg" role="group" aria-label="View">
<button id="vOrb" aria-pressed="true">Orbit</button>
<button id="vWalk" aria-pressed="false">Walk</button></div>
<div class="overlay tr"><div class="lbl">Selected</div><div class="chip" id="chip"></div>
<div class="cap" id="cap">click a wall</div></div>
<div class="overlay bl" id="hint">Drag to orbit · scroll to zoom · click a wall to paint it</div>
</div>
<aside>
<div class="grp"><h2>Paint</h2><div class="pal" id="pal"></div>
<p class="note">Pick a colour, then click any wall face in the model. Shift-click paints every
wall on that floor at once.</p></div>
<div class="grp"><h2>Daylight</h2>
<div class="sun-read"><span class="h" id="sunH">13:00</span><span class="d" id="sunD"></span></div>
<input type="range" id="sun" min="7" max="19" step="0.5" value="13" aria-label="Time of day">
<div class="ticks"><span>07</span><span>10</span><span>13</span><span>16</span><span>19</span></div>
<div class="row" style="margin-top:12px"><label for="north">North</label>
<input type="number" id="north" value="0" step="5" min="0" max="359"><span class="stat">deg</span></div>
<p class="note">Set the building's true north bearing off the site plan. Until it's right, the
sun tracks across an assumed orientation and the room-by-room light story will be wrong.</p></div>
<div class="grp"><h2>Model</h2>
<div class="row"><label for="hGf">GF height</label><input type="number" id="hGf" value="3.0" step="0.1" min="2.2" max="6"><span class="stat">m</span></div>
<div class="row"><label for="hFf">FF height</label><input type="number" id="hFf" value="3.0" step="0.1" min="2.2" max="6"><span class="stat">m</span></div>
<div class="row"><label for="furn">Furniture</label><select id="furn">
<option value="2">3D massing</option><option value="1">Outline only</option>
<option value="0">Hide</option></select></div>
<p class="note" id="meta"></p></div>
<div class="grp"><h2>Spec</h2><button class="spec" id="copy">Copy painted spec</button></div>
</aside>
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const PLAN=__DATA__;
const PALETTE=[["1024","Timeless","#efe9df"],["12303","Natural white","#f4f0e8"],
["12308","Unbleached","#e3d7c3"],["1625","Soul","#f0e7d6"],["12306","Tender greige","#dbd4c9"],
["11209","Light clay","#e0d3c4"],["1129","Parchment","#e9dfcb"],["1877","Pebblestone","#b5aea4"],
["10051","Claywood","#a8907f"],["8493","Green tea","#a6ac94"],["1938","Tea leaves","#8b8a75"],
["9925","Fahm","#4c4c49"]];
let pick=0, mode="orbit", floors="both", layout="side", hour=13, northDeg=0;
const OFF={gf:0, ff:0};
const H={gf:3.0, ff:3.0};
const SCALE=4;

const stage=document.getElementById("stage");
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x0e0f11);
const camera=new THREE.PerspectiveCamera(50,1,0.1,2000);
const renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
stage.appendChild(renderer.domElement);
const amb=new THREE.AmbientLight(0xffffff,.46), hemi=new THREE.HemisphereLight(0xdfe7ef,0x6b5a45,.3),
      sun=new THREE.DirectionalLight(0xffffff,.46);
scene.add(amb,hemi,sun);
const root=new THREE.Group(); root.scale.setScalar(SCALE); scene.add(root);

const CX={}, CZ={};
for(const k in PLAN){ CX[k]=PLAN[k].w/2000; CZ[k]=PLAN[k].d/2000; }

const wallMeshes=[];

/* Half-turn stair, built from the plan's own nosing lines.
   Both flights run along X and stop at x_turn; the turn is the strip at the
   east end where turn_z climbs in Z. Ascent order is flight A -> turn ->
   flight B, so the top lands back at the west end, one floor up. */
function buildStair(g,P,ht){
  const S=P.stair;
  const px=v=>(v-P.w/2)/1000, pz=v=>(v-P.d/2)/1000;
  const mat=c=>new THREE.MeshLambertMaterial({color:new THREE.Color(c)});
  const treadM=mat("#4d2a24"), riserM=mat("#f3ede3"), stringM=mat("#ece5da"),
        railM=mat("#3a2119"), balM=mat("#e9e2d5");
  const nR=S.risers, rise=ht/nR, TT=0.05, NOSE=25;
  const goA=(S.x_turn-S.x_low)/S.treads_a;
  const nA=S.treads_a, LAND=nA+1;          /* landing is the (nA+1)th riser */

  const box=(w,h,d,x,y,z,m)=>{const o=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m);
    o.position.set(x,y,z); g.add(o); return o;};

  /* ---- treads, landing and risers, in order of ascent ------------------- */
  const steps=[];
  for(let i=0;i<nA;i++)                                   /* flight A, +X */
    steps.push({x0:S.x_low+goA*i,x1:S.x_low+goA*(i+1),
                z0:S.fa[0],z1:S.fa[1],sign:1,top:(i+1)*rise});
  steps.push({x0:S.x_turn,x1:S.x_east,                    /* half-space landing */
              z0:S.fa[0],z1:S.fb[1],sign:1,top:LAND*rise,landing:true});
  for(let i=0;i<S.treads_b;i++)                           /* flight B, -X */
    steps.push({x0:S.x_turn-goA*(i+1),x1:S.x_turn-goA*i,
                z0:S.fb[0],z1:S.fb[1],sign:-1,top:(LAND+1+i)*rise});

  steps.forEach(s=>{
    let X0=s.x0,X1=s.x1;
    if(s.sign>0) X0-=NOSE; else X1+=NOSE;
    box((X1-X0)/1000,TT,(s.z1-s.z0)/1000,
        px((X0+X1)/2),s.top-TT/2,pz((s.z0+s.z1)/2),treadM);
    const rx=(s.sign>0)?s.x0:s.x1;
    box(0.03,rise-TT,(s.z1-s.z0)/1000,px(rx),s.top-TT-(rise-TT)/2,
        pz((s.z0+s.z1)/2),riserM);
  });

  /* ---- sloped members: strings and handrail ----------------------------- */
  const XA=new THREE.Vector3(1,0,0);
  const slope=(a,b,w,h,m)=>{
    const d=new THREE.Vector3(b.x-a.x,b.y-a.y,b.z-a.z), len=d.length();
    if(len<1e-4) return;
    const o=new THREE.Mesh(new THREE.BoxGeometry(len,h,w),m);
    o.position.set((a.x+b.x)/2,(a.y+b.y)/2,(a.z+b.z)/2);
    o.quaternion.setFromUnitVectors(XA,d.normalize());
    g.add(o); return o;
  };
  const V=(x,y,z)=>new THREE.Vector3(px(x),y,pz(z));
  const SD=0.30, ST=0.04, DROP=0.11;   /* string depth, thickness, drop below pitch */

  /* flight A strings, both sides */
  [S.fa[0],S.fa[1]].forEach(z=>
    slope(V(S.x_low,rise-DROP,z),V(S.x_turn,LAND*rise-DROP,z),ST,SD,stringM));
  /* landing fascia across the well side */
  box(ST,SD,(S.fb[1]-S.fa[0])/1000,px(S.x_turn),LAND*rise-DROP,
      pz((S.fa[0]+S.fb[1])/2),stringM);
  /* flight B strings, both sides */
  [S.fb[0],S.fb[1]].forEach(z=>
    slope(V(S.x_turn,(LAND+1)*rise-DROP,z),V(S.x_low,nR*rise-DROP,z),ST,SD,stringM));

  /* ---- balustrade: one continuous rail around the open well ------------- */
  const RH=0.90, RT=0.055;             /* rail height above pitch, rail section */
  const runs=[
    {a:V(S.x_low, rise+RH,        S.fa[1]), b:V(S.x_turn,LAND*rise+RH,     S.fa[1])},
    {a:V(S.x_turn,LAND*rise+RH,   S.fa[1]), b:V(S.x_turn,(LAND+1)*rise+RH, S.fb[0])},
    {a:V(S.x_turn,(LAND+1)*rise+RH,S.fb[0]),b:V(S.x_low, nR*rise+RH,       S.fb[0])}
  ];
  const balGeo=new THREE.CylinderGeometry(0.017,0.021,1,8), BH=RH-RT;
  runs.forEach(r=>{
    slope(r.a,r.b,RT,RT,railM);
    const L=Math.hypot(r.b.x-r.a.x,r.b.z-r.a.z), n=Math.max(2,Math.round(L/0.115));
    for(let i=0;i<=n;i++){
      const t=i/n, x=r.a.x+(r.b.x-r.a.x)*t, z=r.a.z+(r.b.z-r.a.z)*t;
      const y0=r.a.y+(r.b.y-r.a.y)*t-RH;
      const o=new THREE.Mesh(balGeo,balM);
      o.position.set(x,y0+BH/2,z); o.scale.y=BH; g.add(o);
    }
  });
  /* newel posts at the foot, both landing corners and the head */
  [[S.x_low,S.fa[1],rise],[S.x_turn,S.fa[1],LAND*rise],
   [S.x_turn,S.fb[0],(LAND+1)*rise],[S.x_low,S.fb[0],nR*rise]
  ].forEach(p=>{const h=RH+0.09; box(0.075,h,0.075,px(p[0]),p[2]+h/2,pz(p[1]),railM);});
}

/* Furniture massing in a Japandi register: pale oak carcasses, oat and linen
   soft goods, one charcoal moment in every five small pieces. Follows the
   composition target in HANDOFF.md — mostly light ground, a little mid neutral,
   a small dark/green accent. Blocks are massing for scale and occlusion, not a
   furnishing proposal; the plan carries no furniture schedule. */
const JAPANDI={oak:"#cbb08a",oakDark:"#a8907f",linen:"#dbd4c9",
               oat:"#e3d7c3",char:"#4c4c49",sage:"#a6ac94"};
function buildFurniture(g,P){
  const M={}; for(const k in JAPANDI)
    M[k]=new THREE.MeshLambertMaterial({color:new THREE.Color(JAPANDI[k])});
  const sh=(v,c)=>Math.max(0.06,v-c);
  const box=(w,h,d,x,y,z,m)=>{const o=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m);
    o.position.set(x,y,z); g.add(o);};
  const cyl=(r,h,x,y,z,m)=>{const o=new THREE.Mesh(new THREE.CylinderGeometry(r,r*0.82,h,14),m);
    o.position.set(x,y,z); g.add(o);};
  P.furn3d.forEach((b,i)=>{
    const tier=b[5];
    /* b[4] is the piece's real footprint, merged rectangles rather than one box,
       so an L stays an L. Carcass parts repeat per rectangle; the accents that
       only make sense once (a sofa back, a pillow) go on the largest. */
    const R=b[4].map(r=>({cx:((r[0]+r[2])/2-P.w/2)/1000, cz:((r[1]+r[3])/2-P.d/2)/1000,
                          w:(r[2]-r[0])/1000, d:(r[3]-r[1])/1000}));
    if(!R.length) return;
    let m0=R[0]; R.forEach(r=>{if(r.w*r.d>m0.w*m0.d) m0=r;});
    const cx=m0.cx, cz=m0.cz, w=m0.w, d=m0.d;
    const along=(w>=d)?"x":"z";                    /* long axis of the piece */
    if(tier==="rug"){
      R.forEach(r=>box(sh(r.w,0.06),0.012,sh(r.d,0.06),r.cx,0.012,r.cz,M.oat));

    }else if(tier==="counter"){     /* cabinetry run: toe recess, carcass, top */
      R.forEach(r=>{
        box(sh(r.w,0.10),0.10,sh(r.d,0.10),r.cx,0.05,r.cz,M.char);
        box(r.w,0.72,r.d,r.cx,0.46,r.cz,M.oak);
        box(r.w,0.04,r.d,r.cx,0.84,r.cz,M.oat);
      });

    }else if(tier==="sofa"){        /* seat on a recessed oak plinth, back, arms */
      R.forEach(r=>{
        box(sh(r.w,0.10),0.06,sh(r.d,0.10),r.cx,0.09,r.cz,M.oakDark);
        box(r.w,0.22,r.d,r.cx,0.27,r.cz,M.linen);
      });
      const bx=(along==="x")?cx:cx-(w/2-0.09), bz=(along==="x")?cz-(d/2-0.09):cz;
      box((along==="x")?w:0.18,0.42,(along==="x")?0.18:d,bx,0.44,bz,M.linen);
      const s=(along==="x")?1:0;
      box(s?0.14:w,0.14,s?d:0.14,cx-(s?w/2-0.07:0),0.45,cz-(s?0:d/2-0.07),M.linen);
      box(s?0.14:w,0.14,s?d:0.14,cx+(s?w/2-0.07:0),0.45,cz+(s?0:d/2-0.07),M.linen);

    }else if(tier==="bed"){                        /* low platform, quilt, pillow */
      R.forEach(r=>box(r.w,0.14,r.d,r.cx,0.07,r.cz,M.oak));
      box(sh(w,0.10),0.20,sh(d,0.10),cx,0.24,cz,M.linen);
      box(sh(w,0.30),0.10,0.34,cx,0.39,cz-(d/2-0.28),M.oat);

    }else if(tier==="coffee"){  /* low slab on a recessed plinth: at 400 mm a
                                   dining top on four legs reads as a cuboid */
      R.forEach(r=>{
        box(sh(r.w,0.44),0.34,sh(r.d,0.44),r.cx,0.17,r.cz,M.oakDark);
        box(r.w,0.065,r.d,r.cx,0.4025,r.cz,M.oak);
      });

    }else if(tier==="table"){                      /* thin top, four slim legs */
      R.forEach(r=>{
        box(r.w,0.04,r.d,r.cx,0.73,r.cz,M.oak);
        [[-1,-1],[1,-1],[-1,1],[1,1]].forEach(q=>
          box(0.055,0.71,0.055,r.cx+q[0]*(r.w/2-0.07),0.355,r.cz+q[1]*(r.d/2-0.07),M.oakDark));
      });

    }else if(tier==="round"){                      /* pedestal side table */
      cyl(Math.min(w,d)/2,0.035,cx,0.44,cz,M.oak);
      cyl(0.045,0.42,cx,0.22,cz,M.char);
      cyl(Math.min(w,d)/4,0.025,cx,0.02,cz,M.char);

    }else if(tier==="plant"){                      /* planter and foliage */
      cyl(Math.min(w,d)/2.6,0.34,cx,0.17,cz,M.oakDark);
      const f=new THREE.Mesh(new THREE.SphereGeometry(Math.min(w,d)/2.2,12,9),M.sage);
      f.position.set(cx,0.34+Math.min(w,d)/2.4,cz); f.scale.y=1.25; g.add(f);

    }else{                                         /* chair: seat, legs, back */
      const m=(i%5===0)?M.char:M.oak;
      box(sh(w,0.08),0.05,sh(d,0.08),cx,0.42,cz,M.linen);
      [[-1,-1],[1,-1],[-1,1],[1,1]].forEach(q=>
        box(0.04,0.40,0.04,cx+q[0]*(w/2-0.06),0.20,cz+q[1]*(d/2-0.06),m));
      box((along==="x")?w:0.06,0.38,(along==="x")?0.06:d,
          (along==="x")?cx:cx-(w/2-0.04),0.63,
          (along==="x")?cz-(d/2-0.04):cz,m);
    }
  });
}

/* Guarding around a floor opening — same balustrade language as the stair,
   but level. Used on the first floor where the slab is cut for the stairwell. */
function buildGuard(g,P){
  const railM=new THREE.MeshLambertMaterial({color:new THREE.Color("#3a2119")}),
        balM=new THREE.MeshLambertMaterial({color:new THREE.Color("#e9e2d5")});
  const balGeo=new THREE.CylinderGeometry(0.017,0.021,1,8);
  const RH=0.95, RT=0.055, BH=RH-RT;
  P.guard.forEach(q=>{
    const ax=(q[0]-P.w/2)/1000, az=(q[1]-P.d/2)/1000,
          bx=(q[2]-P.w/2)/1000, bz=(q[3]-P.d/2)/1000;
    const L=Math.hypot(bx-ax,bz-az); if(L<0.1) return;
    const rail=new THREE.Mesh(new THREE.BoxGeometry(L,RT,RT),railM);
    rail.position.set((ax+bx)/2,RH,(az+bz)/2);
    rail.rotation.y=-Math.atan2(bz-az,bx-ax);
    g.add(rail);
    const n=Math.max(2,Math.round(L/0.115));
    for(let i=0;i<=n;i++){
      const t=i/n, o=new THREE.Mesh(balGeo,balM);
      o.position.set(ax+(bx-ax)*t,BH/2,az+(bz-az)*t);
      o.scale.y=BH; g.add(o);
    }
    [[ax,az],[bx,bz]].forEach(p=>{
      const o=new THREE.Mesh(new THREE.BoxGeometry(0.075,RH+0.09,0.075),railM);
      o.position.set(p[0],(RH+0.09)/2,p[1]); g.add(o);
    });
  });
}

function build(){
  while(root.children.length){const c=root.children.pop();
    if(c.geometry)c.geometry.dispose(); if(c.material)c.material.dispose();}
  wallMeshes.length=0;
  let base=0;
  ["gf","ff"].forEach(k=>{
    const P=PLAN[k]; if(!P) return;
    const g=new THREE.Group(); g.name=k;
    const gap=2.5, wg=PLAN.gf.w/1000, wf2=PLAN.ff.w/1000;
    if(layout==="side"){
      OFF.gf=-(wg+gap)/2; OFF.ff=(wf2+gap)/2;
      g.position.set(OFF[k],0,0);
    }else{
      OFF.gf=0; OFF.ff=(PLAN.ff.align||0)/1000;
      g.position.set(OFF[k],(k==="ff")?H.gf:0,0);
    }
    /* slab, with the stairwell cut out of it where there is one. ShapeGeometry
       lies in XY and is laid down by rotation.x=-PI/2, which maps shape +Y to
       world -Z, so the hole's Y coordinates are negated. */
    const sw=P.w/1000, sd=P.d/1000;
    let slabGeo;
    if(P.well){
      const sh=new THREE.Shape();
      sh.moveTo(-sw/2,-sd/2); sh.lineTo(sw/2,-sd/2);
      sh.lineTo(sw/2,sd/2);   sh.lineTo(-sw/2,sd/2); sh.closePath();
      const hx0=(P.well[0]-P.w/2)/1000, hx1=(P.well[2]-P.w/2)/1000,
            hy0=-(P.well[1]-P.d/2)/1000, hy1=-(P.well[3]-P.d/2)/1000;
      const hole=new THREE.Path();
      hole.moveTo(hx0,hy0); hole.lineTo(hx1,hy0);
      hole.lineTo(hx1,hy1); hole.lineTo(hx0,hy1); hole.closePath();
      sh.holes.push(hole);
      slabGeo=new THREE.ShapeGeometry(sh);
    }else{
      slabGeo=new THREE.PlaneGeometry(sw,sd);
    }
    const slab=new THREE.Mesh(slabGeo,
      new THREE.MeshLambertMaterial({color:new THREE.Color(k==="gf"?"#a9835a":"#b98d5f")}));
    slab.rotation.x=-Math.PI/2; slab.position.set(0,0.004,0); g.add(slab);
    const th=0.055, ht=H[k];
    const glassM=new THREE.MeshLambertMaterial({color:new THREE.Color("#9fb4bd"),
      transparent:true,opacity:0.34});
    const frameM=new THREE.MeshLambertMaterial({color:new THREE.Color("#6b6257")});
    P.walls.forEach((w,i)=>{
      const horiz=Math.abs(w[1]-w[3])<1, vert=Math.abs(w[0]-w[2])<1;
      /* window spans that sit on this wall, in plan mm along its own axis */
      let cuts=[];
      if((horiz||vert)&&P.wins){
        const c=horiz?w[1]:w[0], s0=Math.min(horiz?w[0]:w[1],horiz?w[2]:w[3]),
              s1=Math.max(horiz?w[0]:w[1],horiz?w[2]:w[3]);
        P.wins.forEach(q=>{
          if((q.o==="h")!==horiz) return;
          if(Math.abs(q.c-c)>q.t/2+30) return;
          const a=Math.max(q.a,s0), b=Math.min(q.b,s1);
          if(b-a>200) cuts.push([a,b,q.b-q.a]);
        });
        cuts.sort((p,q)=>p[0]-q[0]);
      }
      const piece=(a,b,y0,y1,mat,paintable)=>{
        const t0=(a-(horiz?w[0]:w[1]))/((horiz?w[2]-w[0]:w[3]-w[1])||1);
        const t1=(b-(horiz?w[0]:w[1]))/((horiz?w[2]-w[0]:w[3]-w[1])||1);
        const ax=(w[0]+(w[2]-w[0])*t0-P.w/2)/1000, az=(w[1]+(w[3]-w[1])*t0-P.d/2)/1000,
              bx=(w[0]+(w[2]-w[0])*t1-P.w/2)/1000, bz=(w[1]+(w[3]-w[1])*t1-P.d/2)/1000;
        const len=Math.hypot(bx-ax,bz-az); if(len<0.02) return;
        const m=new THREE.Mesh(new THREE.BoxGeometry(len,y1-y0,th),mat);
        m.position.set((ax+bx)/2,(y0+y1)/2,(az+bz)/2);
        m.rotation.y=-Math.atan2(bz-az,bx-ax);
        if(paintable){m.userData={floor:k,idx:i,code:"1024"}; wallMeshes.push(m);}
        g.add(m);
      };
      const solid=new THREE.MeshLambertMaterial({color:new THREE.Color("#efe9df")});
      if(!cuts.length){
        const ax=(w[0]-P.w/2)/1000, az=(w[1]-P.d/2)/1000,
              bx=(w[2]-P.w/2)/1000, bz=(w[3]-P.d/2)/1000;
        if(Math.hypot(bx-ax,bz-az)<0.1) return;
        const m=new THREE.Mesh(new THREE.BoxGeometry(Math.hypot(bx-ax,bz-az),ht,th),solid);
        m.position.set((ax+bx)/2,ht/2,(az+bz)/2);
        m.rotation.y=-Math.atan2(bz-az,bx-ax);
        m.userData={floor:k,idx:i,code:"1024"};
        g.add(m); wallMeshes.push(m);
        return;
      }
      const s0=Math.min(horiz?w[0]:w[1],horiz?w[2]:w[3]),
            s1=Math.max(horiz?w[0]:w[1],horiz?w[2]:w[3]);
      let at=s0;
      cuts.forEach(cut=>{
        if(cut[0]>at) piece(at,cut[0],0,ht,solid,true);
        /* a wide opening is a glazed door to a terrace, so it runs to the floor */
        const sill=(cut[2]>=2000)?0.05:0.90, head=Math.min(2.40,ht-0.15);
        piece(cut[0],cut[1],0,sill,solid,true);
        piece(cut[0],cut[1],head,ht,solid,true);
        piece(cut[0],cut[1],sill,head,glassM,false);
        piece(cut[0],cut[0]+40,sill,head,frameM,false);
        piece(cut[1]-40,cut[1],sill,head,frameM,false);
        at=cut[1];
      });
      if(at<s1) piece(at,s1,0,ht,solid,true);
    });
    const fmode=document.getElementById("furn").value;
    if(fmode!=="0"){
      if(fmode==="2"&&P.furn3d) buildFurniture(g,P);
      const pts=[];
      P.furn.forEach(f=>{
        pts.push((f[0]-P.w/2)/1000,0.012,(f[1]-P.d/2)/1000,
                 (f[2]-P.w/2)/1000,0.012,(f[3]-P.d/2)/1000);
      });
      const bg=new THREE.BufferGeometry();
      bg.setAttribute("position",new THREE.Float32BufferAttribute(pts,3));
      g.add(new THREE.LineSegments(bg,new THREE.LineBasicMaterial({color:0x6f6a60})));
    }
    if(P.stair) buildStair(g,P,ht);
    /* Side by side, the first floor is shown on its own, so its stairwell would
       otherwise be a hole onto the background. Draw the flight arriving from
       below, on a patch of the floor it lands on. Stacked, the ground floor is
       genuinely underneath and draws it already. */
    if(P.stair_below&&layout==="side"){
      const sg=new THREE.Group(); sg.position.y=-H.gf; g.add(sg);
      const patch=new THREE.Mesh(
        new THREE.PlaneGeometry((P.well[2]-P.well[0])/1000,(P.well[3]-P.well[1])/1000),
        new THREE.MeshLambertMaterial({color:new THREE.Color("#a9835a")}));
      patch.rotation.x=-Math.PI/2;
      patch.position.set(((P.well[0]+P.well[2])/2-P.w/2)/1000,0.004,
                         ((P.well[1]+P.well[3])/2-P.d/2)/1000);
      sg.add(patch);
      buildStair(sg,{w:P.w,d:P.d,stair:P.stair_below},H.gf);
    }
    if(P.guard) buildGuard(g,P);
    /* balcony parapet: waist height with a timber coping, not a wall */
    if(P.parapet){
      const PH=1.00, PT=0.11;
      const wallM=new THREE.MeshLambertMaterial({color:new THREE.Color("#efe9df")}),
            copeM=new THREE.MeshLambertMaterial({color:new THREE.Color("#cbb08a")});
      P.parapet.forEach(p=>{
        const ax=(p[0]-P.w/2)/1000, az=(p[1]-P.d/2)/1000,
              bx=(p[2]-P.w/2)/1000, bz=(p[3]-P.d/2)/1000;
        const len=Math.hypot(bx-ax,bz-az), rot=-Math.atan2(bz-az,bx-ax);
        const m=new THREE.Mesh(new THREE.BoxGeometry(len,PH,PT),wallM);
        m.position.set((ax+bx)/2,PH/2,(az+bz)/2); m.rotation.y=rot; g.add(m);
        const c=new THREE.Mesh(new THREE.BoxGeometry(len,0.05,PT+0.05),copeM);
        c.position.set((ax+bx)/2,PH+0.025,(az+bz)/2); c.rotation.y=rot; g.add(c);
      });
    }
    root.add(g);
  });
  applyFloors();
  document.getElementById("meta").textContent=
    "Ground "+PLAN.gf.w+" x "+PLAN.gf.d+" mm, "+PLAN.gf.walls.length+" wall faces. First "+
    PLAN.ff.w+" x "+PLAN.ff.d+" mm, "+PLAN.ff.walls.length+" wall faces. Scale recovered from "+
    "the annotated 7640 and 8460 widths.";
}
function applyFloors(){
  root.children.forEach(g=>{
    g.visible = floors==="both" || (floors==="gf"&&g.name==="gf") || (floors==="ff"&&g.name==="ff");
  });
}
function sunState(h){
  const t=(h-7)/12, az=Math.PI*(0.18+t*1.28)+northDeg*Math.PI/180, el=Math.sin(Math.PI*t);
  sun.position.set(Math.cos(az)*30,0.8+el*26,Math.sin(az)*30);
  const warm=Math.pow(1-el,1.6);
  sun.color.copy(new THREE.Color(0xfff8ef).lerp(new THREE.Color(0xffb463),warm*0.85));
  sun.intensity=0.20+el*0.42; amb.intensity=0.40+el*0.12;
  amb.color.copy(new THREE.Color(0xfdfaf4).lerp(new THREE.Color(0xffd9ac),warm*0.55));
  hemi.intensity=0.20+el*0.16;
  document.getElementById("sunD").textContent =
    h<9?"Low east light. Warm cast.":h<11?"Climbing. Still warm.":
    h<15?"Near overhead. Brightest.":h<17.5?"Dropping west.":"Late gold. Beiges read warmer.";
  const hh=Math.floor(h); document.getElementById("sunH").textContent=
    String(hh).padStart(2,"0")+":"+((h%1)?"30":"00");
}
let theta=0.9, phi=0.92, radius=184, yaw=0, pitch=-0.08, wx=0, wz=6, wf="gf";
function frame(){
  if(mode==="orbit"){
    camera.fov=50;
    const ty=((layout==="stack"&&floors==="both")?H.gf*0.6:1.6)*SCALE;
    camera.position.set(radius*Math.sin(phi)*Math.sin(theta), radius*Math.cos(phi)+2,
                        radius*Math.sin(phi)*Math.cos(theta));
    camera.lookAt(0,ty,0);
  }else{
    camera.fov=62; camera.rotation.order="YXZ";
    camera.position.set((wx+OFF[wf])*SCALE,((layout==="stack"&&wf==="ff"?H.gf:0)+1.58)*SCALE,wz*SCALE);
    camera.rotation.set(pitch,yaw,0);
  }
  camera.updateProjectionMatrix(); renderer.render(scene,camera);
}
function resize(){const w=stage.clientWidth,h=stage.clientHeight;
  renderer.setSize(w,h,false); camera.aspect=w/h; camera.updateProjectionMatrix(); frame();}
let drag=null, moved=0;
renderer.domElement.addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY};moved=0;
  renderer.domElement.setPointerCapture(e.pointerId);});
renderer.domElement.addEventListener("pointermove",e=>{
  if(!drag)return; const dx=e.clientX-drag.x, dy=e.clientY-drag.y;
  moved+=Math.abs(dx)+Math.abs(dy); drag={x:e.clientX,y:e.clientY};
  if(mode==="orbit"){theta-=dx*.006; phi=Math.max(.12,Math.min(1.52,phi-dy*.005));}
  else{yaw-=dx*.004; pitch=Math.max(-.9,Math.min(.8,pitch-dy*.004));}
  frame();});
["pointerup","pointercancel","pointerleave"].forEach(t=>
  renderer.domElement.addEventListener(t,()=>{drag=null}));
renderer.domElement.addEventListener("wheel",e=>{e.preventDefault();
  if(mode==="orbit") radius=Math.max(20,Math.min(360,radius+e.deltaY*.12));
  else{const s=e.deltaY*.004; wx-=Math.sin(yaw)*s*-1; wz-=Math.cos(yaw)*s*-1;}
  frame();},{passive:false});
addEventListener("keydown",e=>{
  if(mode!=="walk")return; const s=.35;
  if(e.key==="ArrowUp"||e.key==="w"){wx-=Math.sin(yaw)*s; wz-=Math.cos(yaw)*s;}
  if(e.key==="ArrowDown"||e.key==="s"){wx+=Math.sin(yaw)*s; wz+=Math.cos(yaw)*s;}
  if(e.key==="ArrowLeft"||e.key==="a"){wx-=Math.cos(yaw)*s; wz+=Math.sin(yaw)*s;}
  if(e.key==="ArrowRight"||e.key==="d"){wx+=Math.cos(yaw)*s; wz-=Math.sin(yaw)*s;}
  frame();});
const ray=new THREE.Raycaster(), mouse=new THREE.Vector2();
renderer.domElement.addEventListener("click",e=>{
  if(moved>6)return;
  const r=renderer.domElement.getBoundingClientRect();
  mouse.x=((e.clientX-r.left)/r.width)*2-1; mouse.y=-((e.clientY-r.top)/r.height)*2+1;
  ray.setFromCamera(mouse,camera);
  const hit=ray.intersectObjects(wallMeshes.filter(m=>m.parent.visible),false)[0];
  if(!hit)return;
  const P=PALETTE[pick];
  if(e.shiftKey){
    const f=hit.object.userData.floor;
    wallMeshes.forEach(m=>{if(m.userData.floor===f){m.material.color.set(P[2]);m.userData.code=P[0];}});
  }else{hit.object.material.color.set(P[2]); hit.object.userData.code=P[0];}
  document.getElementById("chip").style.background=P[2];
  document.getElementById("cap").textContent=P[0]+" "+P[1];
  frame();});
const pal=document.getElementById("pal");
PALETTE.forEach((p,i)=>{const b=document.createElement("button");
  b.style.background=p[2]; b.title=p[0]+" "+p[1]; b.setAttribute("aria-label",p[0]+" "+p[1]);
  b.setAttribute("aria-pressed",i===0);
  b.onclick=()=>{pick=i;[...pal.children].forEach((c,j)=>c.setAttribute("aria-pressed",j===i));
    document.getElementById("chip").style.background=p[2];
    document.getElementById("cap").textContent=p[0]+" "+p[1];};
  pal.appendChild(b);});
document.getElementById("chip").style.background=PALETTE[0][2];
const seg=(id,fn)=>document.getElementById(id).onclick=fn;
seg("fBoth",()=>setFloors("both")); seg("fGf",()=>setFloors("gf")); seg("fFf",()=>setFloors("ff"));
function setFloors(v){floors=v;
  ["fBoth","fGf","fFf"].forEach((id,i)=>document.getElementById(id)
    .setAttribute("aria-pressed",["both","gf","ff"][i]===v));
  if(mode==="walk"&&v!=="both") wf=(v==="ff")?"ff":"gf";
  applyFloors(); frame();}
seg("lSide",()=>setLayout("side")); seg("lStack",()=>setLayout("stack"));
function setLayout(v){layout=v;
  document.getElementById("lSide").setAttribute("aria-pressed",v==="side");
  document.getElementById("lStack").setAttribute("aria-pressed",v==="stack");
  radius=(v==="side")?184:136; build(); frame();}
seg("vOrb",()=>setMode("orbit")); seg("vWalk",()=>setMode("walk"));
function setMode(m){mode=m;
  document.getElementById("vOrb").setAttribute("aria-pressed",m==="orbit");
  document.getElementById("vWalk").setAttribute("aria-pressed",m==="walk");
  document.getElementById("hint").textContent = m==="orbit"
    ? "Drag to orbit · scroll to zoom · click a wall to paint it"
    : "Drag to look · WASD or arrows to move · click a wall to paint it";
  frame();}
document.getElementById("sun").oninput=e=>{hour=+e.target.value;sunState(hour);frame();};
document.getElementById("north").oninput=e=>{northDeg=+e.target.value||0;sunState(hour);frame();};
document.getElementById("hGf").oninput=e=>{H.gf=+e.target.value||3.0;build();frame();};
document.getElementById("hFf").oninput=e=>{H.ff=+e.target.value||3.0;build();frame();};
document.getElementById("furn").onchange=()=>{build();frame();};
document.getElementById("copy").onclick=()=>{
  /* walls split around a window contribute several meshes; count each wall once */
  const tally={}, seen=new Set();
  wallMeshes.forEach(m=>{
    const id=m.userData.floor+"#"+m.userData.idx;
    if(seen.has(id))return; seen.add(id);
    const k=m.userData.floor+"|"+m.userData.code;
    tally[k]=(tally[k]||0)+1;});
  const nm=c=>{const p=PALETTE.find(x=>x[0]===c);return p?p[0]+" "+p[1]:c;};
  const rows=Object.keys(tally).sort().map(k=>{const [f,c]=k.split("|");
    return (f==="gf"?"Ground":"First")+" floor — Jotun "+nm(c)+" — "+tally[k]+" wall faces";});
  const txt=["Rumah Langkawi — painted spec","Geometry from Interior Floor Layout, 06.05.2026",
    "Ground floor "+PLAN.gf.w+" x "+PLAN.gf.d+" mm, ceiling "+H.gf+" m",
    "First floor "+PLAN.ff.w+" x "+PLAN.ff.d+" mm, ceiling "+H.ff+" m","",...rows,"",
    "Trims and skirting: Jotun 12303 Natural white",
    "Walls: Majestic True Beauty Matt over Majestic Primer, 2 coats",
    "Wet areas: Majestic True Beauty Sheen"].join("\n");
  const b=document.getElementById("copy");
  navigator.clipboard.writeText(txt).then(()=>{b.textContent="Copied";
    setTimeout(()=>b.textContent="Copy painted spec",1500);},()=>{b.textContent="Copy failed";});
};
addEventListener("resize",resize);
build(); sunState(13); resize();
</script>
</body>
</html>'''

OUT.write_text(HTML.replace('__DATA__', blob), encoding='utf-8')
print('wrote', OUT)
