"""
ASTRO-HEROES | Real Curiosity Traverse + NASA Terrain Values
===========================================================
Builds the waypoint dataset from OFFICIAL NASA sources only:

  1. Curiosity (MSL) end-of-drive localizations
     NASA/JPL MMGIS feed:
     https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json
     (sol, lat/lon, geoid elevation, drive distance, odometer ...)

  2. Terrain values at every waypoint from the MRO CTX DTM
     (USGS Astrogeology, 20 m/pixel) via MarswalkRouter:
     elevation, slope (Horn), roughness (detrended 5x5).

  3. Mobility indicators that NASA does not measure directly are
     ESTIMATED from the real slope/roughness with simple, documented
     formulas (clearly labelled "Est_" in the output):
       - Est_Required_Friction = tan(slope)            (incline physics)
       - Est_Traction_Margin   = MU_AVAILABLE - tan(slope)
       - Est_Boot_Sinkage_cm   = BASE_SINKAGE * (1 + slope/15 + roughness/2)
       - Est_Stability_Index   = 1 - 0.6*(slope/15) - 0.4*(roughness/2)  [0..1]
     These are illustrative screening models, NOT validated EVA data.

Validation: the rover's own NASA elevation is compared with the DTM
elevation at the same point, which shows how well the terrain model
matches ground truth.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import requests

from marswalk_router import MarswalkRouter, RouterConfig

MSL_WAYPOINTS_URL = "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json"

MU_AVAILABLE = 0.6      # assumed boot-regolith friction coefficient (illustrative)
BASE_SINKAGE_CM = 1.0   # assumed sinkage on flat, firm regolith (illustrative)
MARS_R_KM = 3389.5


# ---------------------------------------------------------------------
# 1. Load NASA Curiosity waypoints
# ---------------------------------------------------------------------

def _pick(props: dict, *names):
    """Return the first property that exists (feed field names can vary)."""
    lower = {k.lower(): v for k, v in props.items()}
    for n in names:
        if n.lower() in lower and lower[n.lower()] not in (None, ""):
            return lower[n.lower()]
    return None


def load_msl_waypoints(source: str = MSL_WAYPOINTS_URL) -> pd.DataFrame:
    """Read the NASA MMGIS waypoint GeoJSON (URL or local file)."""
    if source.startswith("http"):
        resp = requests.get(source, timeout=60)
        resp.raise_for_status()
        gj = resp.json()
    else:
        with open(source) as f:
            gj = json.load(f)

    rows = []
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        coords = geom["coordinates"]
        p = feat.get("properties", {}) or {}
        lon = _pick(p, "lon", "longitude") or coords[0]
        lat = _pick(p, "lat", "latitude") or coords[1]
        rows.append({
            "Sol": _pick(p, "sol"),
            "Site": _pick(p, "site"),
            "Drive": _pick(p, "drive"),
            "Latitude": float(lat),
            "Longitude": float(lon),
            "NASA_Elevation_m": _pick(p, "elev_geoid", "elevation", "elev"),
            "NASA_Odometer_m": _pick(p, "dist_total_m", "dist_total", "odometer"),
        })

    df = pd.DataFrame(rows)
    for col in ["Sol", "NASA_Elevation_m", "NASA_Odometer_m"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Latitude", "Longitude"])
    if df["Sol"].notna().any():
        df = df.sort_values(["Sol"], kind="stable")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------
# 2. Select a segment and thin it to evenly spaced waypoints
# ---------------------------------------------------------------------

def _haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * MARS_R_KM * 1000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def select_segment(df, sol_min=None, sol_max=None, spacing_m=150.0, max_points=None):
    """Keep sols in range, then keep a point every ~spacing_m along the path."""
    seg = df.copy()
    if sol_min is not None:
        seg = seg[seg["Sol"] >= sol_min]
    if sol_max is not None:
        seg = seg[seg["Sol"] <= sol_max]
    seg = seg.reset_index(drop=True)
    if seg.empty:
        raise ValueError("No Curiosity waypoints in the selected sol range.")

    keep = [0]
    acc = 0.0
    for i in range(1, len(seg)):
        acc += _haversine_m(seg.at[i - 1, "Latitude"], seg.at[i - 1, "Longitude"],
                            seg.at[i, "Latitude"], seg.at[i, "Longitude"])
        if acc >= spacing_m:
            keep.append(i)
            acc = 0.0
    if keep[-1] != len(seg) - 1:
        keep.append(len(seg) - 1)
    seg = seg.loc[keep].reset_index(drop=True)

    if max_points and len(seg) > max_points:
        idx = np.linspace(0, len(seg) - 1, max_points).round().astype(int)
        seg = seg.loc[np.unique(idx)].reset_index(drop=True)
    return seg


# ---------------------------------------------------------------------
# 3. Attach real DTM terrain values + estimated mobility indicators
# ---------------------------------------------------------------------

def attach_terrain(seg: pd.DataFrame, router: MarswalkRouter) -> pd.DataFrame:
    out = seg.copy()
    cfg = router.cfg
    elev, slope, rough = [], [], []
    for lon, lat in zip(out["Longitude"], out["Latitude"]):
        r, c = router.lonlat_to_rc(lon, lat)
        if 0 <= r < router.shape[0] and 0 <= c < router.shape[1]:
            elev.append(router.z[r, c])
            slope.append(router.slope[r, c])
            rough.append(router.roughness[r, c])
        else:
            elev.append(np.nan); slope.append(np.nan); rough.append(np.nan)

    out["DEM_Elevation_m"] = np.round(elev, 2)
    out["DEM_Slope_deg"] = np.round(slope, 2)
    out["DEM_Roughness_m"] = np.round(rough, 3)

    # distance along the selected path
    d = [0.0]
    for i in range(1, len(out)):
        d.append(d[-1] + _haversine_m(out.at[i - 1, "Latitude"], out.at[i - 1, "Longitude"],
                                      out.at[i, "Latitude"], out.at[i, "Longitude"]))
    out["Path_Distance_m"] = np.round(d, 1)

    s = out["DEM_Slope_deg"]
    g = out["DEM_Roughness_m"]
    tan_s = np.tan(np.radians(s))
    out["Est_Required_Friction"] = tan_s.round(3)
    out["Est_Traction_Margin"] = (MU_AVAILABLE - tan_s).round(3)
    out["Est_Boot_Sinkage_cm"] = (BASE_SINKAGE_CM * (1 + s / 15 + g / 2)).round(2)
    out["Est_Stability_Index"] = (1 - 0.6 * (s / 15) - 0.4 * (g / 2)).clip(0, 1).round(3)

    def risk(row):
        if pd.isna(row["DEM_Slope_deg"]):
            return "Unknown"
        if row["DEM_Slope_deg"] >= cfg.max_slope_deg * 0.9 or row["DEM_Roughness_m"] >= 2 * cfg.rough_warn_m:
            return "High"
        if row["DEM_Slope_deg"] >= cfg.warn_slope_deg or row["DEM_Roughness_m"] >= cfg.rough_warn_m:
            return "Medium"
        return "Low"

    out["Risk_Level"] = out.apply(risk, axis=1)
    out["NASA_vs_DEM_Diff_m"] = (out["NASA_Elevation_m"] - out["DEM_Elevation_m"]).round(2)
    out["DataSource"] = "NASA MMGIS MSL_waypoints + USGS/NASA MRO CTX DTM"
    out.insert(0, "Waypoint_ID", range(1, len(out) + 1))
    return out


def validation_report(df: pd.DataFrame) -> dict:
    """How well does the DTM match the rover's own NASA elevations?"""
    v = df.dropna(subset=["NASA_Elevation_m", "DEM_Elevation_m"])
    if len(v) < 3:
        return {"note": "Not enough NASA elevations in the feed to validate."}
    diff = v["NASA_Elevation_m"] - v["DEM_Elevation_m"]
    detrended = diff - diff.mean()
    return {
        "points_compared": int(len(v)),
        "mean_offset_m": round(float(diff.mean()), 2),
        "offset_std_m": round(float(diff.std()), 2),
        "max_abs_residual_after_offset_m": round(float(detrended.abs().max()), 2),
        "elevation_change_correlation": round(float(
            v["NASA_Elevation_m"].diff().corr(v["DEM_Elevation_m"].diff())), 3),
        "note": ("A near-constant offset means a different vertical reference; "
                 "small residuals + high correlation mean the DTM matches the real terrain."),
    }


def to_geojson(df: pd.DataFrame) -> dict:
    feats = []
    for _, r in df.iterrows():
        props = {k: (None if (isinstance(v, float) and math.isnan(v)) else v)
                 for k, v in r.items() if k not in ("Latitude", "Longitude")}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [r["Longitude"], r["Latitude"]]},
                      "properties": props})
    line = {"type": "Feature",
            "geometry": {"type": "LineString",
                         "coordinates": df[["Longitude", "Latitude"]].values.tolist()},
            "properties": {"name": "Curiosity traverse (NASA)"}}
    return {"type": "FeatureCollection", "features": [line] + feats}


# ---------------------------------------------------------------------
# One call does everything
# ---------------------------------------------------------------------

def build_curiosity_dataset(dem_url, waypoints_source=MSL_WAYPOINTS_URL,
                            sol_min=None, sol_max=None, spacing_m=150.0,
                            max_points=50, config: RouterConfig | None = None):
    raw = load_msl_waypoints(waypoints_source)
    seg = select_segment(raw, sol_min, sol_max, spacing_m, max_points)
    router = MarswalkRouter(dem_url, list(zip(seg["Longitude"], seg["Latitude"])),
                            config or RouterConfig(margin_m=600))
    data = attach_terrain(seg, router)
    return raw, data, router
