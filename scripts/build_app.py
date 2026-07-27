import pdfplumber, json, math

PDF = '/mnt/user-data/uploads/Langkawi-Interior_Floor_Layout.pdf'
GRAY = (0.49804, 0.49804, 0.49804)
RED = (1.0, 0.0, 0.0)
SNAP = 5.0
MINLEN = 120.0
PLANS = {'gf': (200, 560, 7640.0), 'ff': (590, 900, 8460.0)}

with pdfplumber.open(PDF) as pdf:
    page = pdf.pages[0]
    lines, curves = page.lines, page.curves

data = {}
STAIRBOX = {}
for key, (lo, hi, known_w) in PLANS.items():
    def inb(o):
        return lo < o['x0'] < hi and 100 < o['top'] < 620

    wl = [l for l in lines if l.get('stroking_color') in (GRAY, 0, (0.0, 0.0, 0.0)) and inb(l)]
    rl = [l for l in lines if l.get('stroking_color') == RED and inb(l)]
    rc = [c for c in curves if c.get('stroking_color') == RED and inb(c)]

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

    furn = []
    for l in rl:
        a, b = P(l['x0'], l['top']), P(l['x1'], l['bottom'])
        if math.dist(a, b) > 60:
            furn.append([a[0], a[1], b[0], b[1]])
    for c in rc:
        p = [P(*q) for q in c['pts']]
        for i in range(len(p) - 1):
            if math.dist(p[i], p[i + 1]) > 60:
                furn.append([p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]])

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

    stair = None
    if key == 'gf':
        stair = dict(x0=4490, x1=7490, landw=970,
                     fa=[6525, 7365], fb=[8530, 9560], risers=16)
    data[key] = dict(w=round((max(xs) - x0) * scale), d=round((max(ys) - y0) * scale),
                     walls=walls, furn=furn, stair=stair)
    print(key, data[key]['w'], 'x', data[key]['d'], 'walls', len(walls), 'furn', len(furn))

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
<option value="1">Show layout</option><option value="0">Hide</option></select></div>
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
      OFF.gf=0; OFF.ff=0;
      g.position.set(0,(k==="ff")?H.gf:0,0);
    }
    const slab=new THREE.Mesh(new THREE.PlaneGeometry(P.w/1000,P.d/1000),
      new THREE.MeshLambertMaterial({color:new THREE.Color(k==="gf"?"#a9835a":"#b98d5f")}));
    slab.rotation.x=-Math.PI/2; slab.position.set(0,0.004,0); g.add(slab);
    const th=0.055, ht=H[k];
    P.walls.forEach((w,i)=>{
      const ax=(w[0]-P.w/2)/1000, az=(w[1]-P.d/2)/1000,
            bx=(w[2]-P.w/2)/1000, bz=(w[3]-P.d/2)/1000;
      const len=Math.hypot(bx-ax,bz-az); if(len<0.1)return;
      const m=new THREE.Mesh(new THREE.BoxGeometry(len,ht,th),
        new THREE.MeshLambertMaterial({color:new THREE.Color("#efe9df")}));
      m.position.set((ax+bx)/2,ht/2,(az+bz)/2);
      m.rotation.y=-Math.atan2(bz-az,bx-ax);
      m.userData={floor:k,idx:i,code:"1024"};
      g.add(m); wallMeshes.push(m);
    });
    if(document.getElementById("furn").value==="1"){
      const pts=[];
      P.furn.forEach(f=>{
        pts.push((f[0]-P.w/2)/1000,0.012,(f[1]-P.d/2)/1000,
                 (f[2]-P.w/2)/1000,0.012,(f[3]-P.d/2)/1000);
      });
      const bg=new THREE.BufferGeometry();
      bg.setAttribute("position",new THREE.Float32BufferAttribute(pts,3));
      g.add(new THREE.LineSegments(bg,new THREE.LineBasicMaterial({color:0x6f6a60})));
    }
    if(P.stair){
      const S=P.stair, oakM=new THREE.MeshLambertMaterial({color:new THREE.Color("#b98d5f")});
      const px=v=>(v-P.w/2)/1000, pz=v=>(v-P.d/2)/1000;
      const nR=S.risers, riser=ht/nR, n1=Math.floor(nR/2)-1, n2=nR-n1-2;
      const edge=S.x0+S.landw, run=S.x1-edge, go=run/(n1+1);
      const fa=[pz(S.fa[0]),pz(S.fa[1])], fb=[pz(S.fb[0]),pz(S.fb[1])];
      const T=(w,d2,x,y,z)=>{const m=new THREE.Mesh(new THREE.BoxGeometry(w,0.05,d2),oakM);
        m.position.set(x,y,z); g.add(m);};
      for(let i=0;i<n1;i++)
        T(go/1000-0.01, fa[1]-fa[0], px(S.x1-go*(i+0.5)), riser*(i+1), (fa[0]+fa[1])/2);
      T(S.landw/1000, fb[1]-fa[0], px(S.x0+S.landw/2), riser*(n1+1), (fa[0]+fb[1])/2);
      for(let i=0;i<n2;i++)
        T(go/1000-0.01, fb[1]-fb[0], px(edge+go*(i+0.5)), riser*(n1+2+i), (fb[0]+fb[1])/2);
      const railM=new THREE.MeshLambertMaterial({color:new THREE.Color("#54524c")});
      const post=(x,z,yb)=>{const m=new THREE.Mesh(new THREE.BoxGeometry(0.05,1.0,0.05),railM);
        m.position.set(x,(yb||0)+0.5,z); g.add(m);};
      post(px(S.x1),(fa[0]+fa[1])/2,0);
      post(px(edge),(fa[0]+fa[1])/2,riser*n1);
      post(px(edge),(fb[0]+fb[1])/2,riser*(n1+1));
      post(px(S.x1),(fb[0]+fb[1])/2,ht-riser);
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
  const tally={};
  wallMeshes.forEach(m=>{const k=m.userData.floor+"|"+m.userData.code;
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

open('/mnt/user-data/outputs/rumah-langkawi-3d.html', 'w').write(HTML.replace('__DATA__', blob))
print('wrote rumah-langkawi-3d.html')
