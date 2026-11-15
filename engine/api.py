"""
ASTRO-HEROES | Marswalk Route API (FastAPI)
Connects the route engine to the web game (map + HUD).

Run (from the folder that holds api.py, marswalk_router.py, web/):
    pip install fastapi uvicorn rasterio pyproj scipy matplotlib
    uvicorn api:app --port 8000
Then open  http://localhost:8000

DEM source (env var DEM_PATH):
    - default "dem_clip.tif" (exported from Colab, works offline)
    - or the full USGS CTX DTM URL (needs internet)

Endpoints (coordinates are lon/lat in degrees):
    GET  /info                 mission points + map bounds
    GET  /layer/{name}.png     slope | roughness | cost  (image overlay)
    POST /route      {"start":[lon,lat], "targets":[[lon,lat],...]}
    POST /reroute    {"current":[lon,lat], "targets":[[lon,lat],...],
                      "obstacle":{"lon":..,"lat":..,"radius_m":..,"kind":..,"note":..}}
    POST /obstacle   {"lon":..,"lat":..,"radius_m":40,"kind":"boulder","note":""}
    GET  /obstacles  GeoJSON of all reported obstacles (new map layer)
    DELETE /obstacles
"""

import io
import os

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from marswalk_router import MarswalkRouter, RouterConfig

HERE = os.path.dirname(os.path.abspath(__file__))
DEM_PATH = os.environ.get("DEM_PATH", os.path.join(HERE, "dem_clip.tif"))

if not os.path.exists(DEM_PATH) and not DEM_PATH.startswith("http"):
    # No local DEM: stream the real USGS/NASA CTX DTM (needs internet)
    import requests
    _item = requests.post(
        "https://g6goyz4w56.execute-api.us-west-2.amazonaws.com/prod/search",
        json={"collections": ["mro_ctx_controlled_usgs_dtms"],
              "ids": ["T01_000815_1749_XN_05S222W__P22_009571_1756_XI_04S222W"], "limit": 1},
        timeout=60).json()["features"][0]
    DEM_PATH = _item["assets"]["geoid_adjusted_dem"]["href"]
    print("Using remote NASA/USGS DTM:", DEM_PATH)

# Mission points (lon, lat) — same as colab_demo.py; change for your site
HABITAT = (137.44293, -4.58130)
TARGETS = [
    {"name": "Science Stop 1", "lon": 137.49000, "lat": -4.61500,
     "task": "Sample the layered sediments"},
    {"name": "Science Stop 2", "lon": 137.54758, "lat": -4.65420,
     "task": "Image the rock outcrop"},
]

POINTS = [HABITAT] + [(t["lon"], t["lat"]) for t in TARGETS]
router = MarswalkRouter(DEM_PATH, POINTS, RouterConfig(margin_m=800))

app = FastAPI(title="ASTRO-HEROES Marswalk API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Obstacle(BaseModel):
    lon: float
    lat: float
    radius_m: float = 40.0
    kind: str = "obstacle"
    note: str = ""


class RouteReq(BaseModel):
    start: list[float]
    targets: list[list[float]]


class RerouteReq(BaseModel):
    current: list[float]
    targets: list[list[float]]
    obstacle: Obstacle | None = None


def _bounds():
    """Lon/lat bounds of the working grid: [[south, west], [north, east]]."""
    t = router.transform
    h, w = router.shape
    lon0, lat0 = router._to_lonlat.transform(t.c, t.f)
    lon1, lat1 = router._to_lonlat.transform(t.c + w * t.a, t.f + h * t.e)
    return [[min(lat0, lat1), min(lon0, lon1)], [max(lat0, lat1), max(lon0, lon1)]]


@app.get("/info")
def info():
    return {
        "habitat": {"lon": HABITAT[0], "lat": HABITAT[1]},
        "targets": TARGETS,
        "bounds": _bounds(),
        "resolution_m": router.res,
        "max_slope_deg": router.cfg.max_slope_deg,
        "warn_slope_deg": router.cfg.warn_slope_deg,
        "data_source": "MRO CTX DTM (USGS Astrogeology / NASA), 20 m/pixel",
    }


_layer_cache = {}


@app.get("/layer/{name}.png")
def layer(name: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if name not in ("slope", "roughness", "cost"):
        raise HTTPException(404, "Unknown layer")
    if name not in _layer_cache:
        if name == "slope":
            arr, cmap, vmax = router.slope, "turbo", 25
        elif name == "roughness":
            arr, cmap, vmax = router.roughness, "viridis", 2
        else:
            arr = np.where(router.terrain_blocked, np.nan, router.base_cost)
            cmap, vmax = "magma_r", float(np.nanpercentile(router.base_cost, 98))
        rgba = plt.get_cmap(cmap)(np.clip(np.nan_to_num(arr, nan=0) / vmax, 0, 1))
        rgba[..., 3] = np.where(np.isfinite(arr), 0.85, 0.0)
        if name == "cost":  # show impassable terrain in red
            rgba[router.terrain_blocked] = [0.85, 0.1, 0.1, 0.6]
        buf = io.BytesIO()
        plt.imsave(buf, rgba, format="png")
        _layer_cache[name] = buf.getvalue()
    return Response(_layer_cache[name], media_type="image/png")


@app.post("/route")
def route(req: RouteReq):
    try:
        return router.plan(tuple(req.start), [tuple(t) for t in req.targets])
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/obstacle")
def obstacle(ob: Obstacle):
    router.add_obstacle(ob.lon, ob.lat, ob.radius_m, ob.kind, ob.note)
    return {"ok": True, "obstacles": len(router.obstacles)}


@app.post("/reroute")
def reroute(req: RerouteReq):
    try:
        return router.reroute(tuple(req.current), [tuple(t) for t in req.targets],
                              req.obstacle.model_dump() if req.obstacle else None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/obstacles")
def obstacles():
    return router.obstacles_geojson()


@app.delete("/obstacles")
def clear():
    router.clear_obstacles()
    return {"ok": True}


# Serve the game (web/index.html) at http://localhost:8000
_web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.isdir(_web):
    app.mount("/", StaticFiles(directory=_web, html=True), name="web")
