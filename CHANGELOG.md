# Changelog

## Stair rebuild
- Corrected the stair orientation: the turn strip is at the EAST end (x 6520-7490), not the west. Both flights run x 4490-6520, 7 treads at 290mm, straight half-space landing between them, 16 risers floor to floor
- Stripped the flight setting-out lines (z 6525/7365/8530, x 6520, x 4490 and the three landing nosings) that were extruding as 3m walls and boxing the stairwell in; GF wall faces 159 -> 151
- Modelled the stair as joinery: treads with 25mm nosing, risers, strings both sides of each flight, landing fascia, newel posts, continuous ramped handrail and balusters around the open well
- Made scripts/build_app.py and scripts/dims.py runnable from the repo instead of hardcoded sandbox paths
- Excluded the source PDF from the repo (title block carries client and consultant names) and removed those names from README and the painter spec
- Added root index.html redirect for GitHub Pages
- Found: scripts/dims.py no longer reproduces the dimension-chain validation on this PDF - see docs/STATUS.md open items

## Earlier session
- Extracted wall geometry from N.T.S. floor-plan PDF; validated to 0-10mm against annotated dimension chains
- Built single-file 3D app: two floors, orbit + walk, click-to-paint, daylight, side-by-side/stacked
- Reconstructed |_| dog-leg stair from tread lines; landing to west; stripped tread/partition lines that extruded as white walls
- Generated measured room + paint schedules at assumed 3.0m ceiling
- Open: elevation PDF re-upload, floor-to-floor (3135?), flight count (2 vs 3), room names, true north
