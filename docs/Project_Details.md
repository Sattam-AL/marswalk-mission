# Project details (draft)

**What it does**
Marswalk Mission is a layered terrain map and route planner for an astronaut on a Mars surface EVA. It combines NASA orbital terrain data into hazard layers, computes the safest walking route from the habitat to one or more science targets, and re-plans the route in seconds when the astronaut reports an obstacle that the orbital data missed.

**How it works**
1. Data: a 20 m/pixel digital terrain model (MRO CTX stereo DTM, USGS Astrogeology) of Gale Crater / Mount Sharp, with NASA Mars Trek CTX imagery as the base map.
2. Terrain layers: slope (Horn method) and surface roughness (deviation from a locally fitted plane over ~100 m).
3. Cost map: terrain steeper than 15°, missing data, and a 20 m safety buffer are impassable; other cells get a cost that rises with slope and roughness.
4. Route planning: A* search for the lowest-effort path with a climb penalty. Output: distance, ascent/descent, maximum slope, estimated walking time, and per-point HUD alerts.
5. Re-routing: when the astronaut flags an obstacle from the tablet or helmet HUD, the area becomes impassable and a new route to the same target is computed on site, without waiting for Earth (4–24 min signal delay).
6. Learning map: every reported obstacle is saved as a new GeoJSON layer, so the next crew plans on a more accurate map.

**Benefits**
Astronaut safety first; works in real time on the surface; the map improves with every Marswalk.

**Tools & technologies**
Python (NumPy, SciPy, Rasterio, PyProj, Matplotlib, Pandas), Google Colab, FastAPI, JavaScript + Leaflet, GeoJSON, GitHub Pages, NASA Mars Trek WMTS, USGS STAC API.

**Limitations**
Slope limits and cost weights are illustrative, not NASA EVA limits. A 20 m DTM cannot resolve boot-scale hazards — which is exactly why the re-routing feature exists.
