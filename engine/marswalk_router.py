"""
ASTRO-HEROES | Marswalk Route Engine
====================================
Safe-path planning and live re-routing for an astronaut Marswalk,
computed directly from a NASA/USGS CTX DTM (20 m/pixel GeoTIFF).

Pipeline
--------
1. Read a window of the DTM around the area of interest.
2. Derive terrain layers: slope (Horn 3x3) and roughness
   (std of residuals after fitting a local plane, 5x5 = ~100 m).
3. Build a traversal cost grid:
     - cells steeper than MAX_SLOPE, NoData cells and reported
       obstacles are impassable
     - cost grows with slope and roughness
4. A* search (8-connected) for the lowest-cost path,
   with an extra penalty for climbing.
5. Re-routing: the astronaut (or a suit sensor) reports an obstacle
   -> the area becomes impassable -> a new path is computed from the
   astronaut's current position to the same target.

Every reported obstacle is stored, so it can be saved as a new map layer
(the "learning" part: the next crew plans on the updated map).

Thresholds are ILLUSTRATIVE engineering screening values, not NASA
EVA safety limits.
"""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass, field, asdict

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import CRS, Transformer
from scipy.ndimage import correlate, binary_dilation, distance_transform_edt


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

@dataclass
class RouterConfig:
    max_slope_deg: float = 15.0      # steeper than this = impassable
    warn_slope_deg: float = 10.0     # HUD warning above this slope
    rough_warn_m: float = 1.0        # HUD warning above this roughness
    w_slope: float = 4.0             # weight of slope in cell cost
    w_rough: float = 2.0             # weight of roughness in cell cost
    rough_ref_m: float = 2.0         # roughness that counts as "very rough"
    climb_penalty: float = 8.0       # extra cost per metre climbed
    safety_buffer_m: float = 20.0    # keep this far from impassable cells
    margin_m: float = 1500.0         # extra DTM area read around the points
    walk_speed_kmh: float = 2.5      # suited walking speed on flat ground


@dataclass
class Obstacle:
    lon: float
    lat: float
    radius_m: float
    kind: str = "obstacle"
    note: str = ""


# ---------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------

class MarswalkRouter:

    NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1),
                 (0, -1),           (0, 1),
                 (1, -1),  (1, 0),  (1, 1)]

    def __init__(self, dem_path: str, points_lonlat, config: RouterConfig | None = None):
        """
        dem_path       : local path or URL of the DTM GeoTIFF
                         (URLs work through GDAL /vsicurl/).
        points_lonlat  : list of (lon, lat) that must be inside the
                         working area (start, targets, ...).
        """
        self.cfg = config or RouterConfig()
        self.obstacles: list[Obstacle] = []

        path = dem_path
        if path.startswith("http") and not path.startswith("/vsicurl/"):
            path = "/vsicurl/" + path

        with rasterio.open(path) as src:
            proj_crs = CRS.from_wkt(src.crs.to_wkt())
            self._to_xy = Transformer.from_crs(proj_crs.geodetic_crs, proj_crs, always_xy=True)
            self._to_lonlat = Transformer.from_crs(proj_crs, proj_crs.geodetic_crs, always_xy=True)

            lons = [p[0] for p in points_lonlat]
            lats = [p[1] for p in points_lonlat]
            xs, ys = self._to_xy.transform(lons, lats)
            m = self.cfg.margin_m
            win = from_bounds(min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m,
                              transform=src.transform)
            win = win.round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))

            data = src.read(1, window=win, masked=True).astype("float64")
            self.transform = src.window_transform(win)
            self.crs_wkt = src.crs.to_wkt()

        self.z = data.filled(np.nan)
        self.z[~np.isfinite(self.z)] = np.nan
        self.res = abs(self.transform.a)
        self.shape = self.z.shape

        self._build_layers()
        self._build_cost()

    # ------------------------------------------------------------------
    # Terrain layers
    # ------------------------------------------------------------------

    def _build_layers(self):
        z = self.z
        valid = np.isfinite(z)
        zf = np.where(valid, z, np.nanmean(z))
        d = self.res

        # Horn slope
        kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]) / (8 * d)
        ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]]) / (8 * d)
        gx = correlate(zf, kx, mode="nearest")
        gy = correlate(zf, ky, mode="nearest")
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        full3 = correlate(valid.astype(float), np.ones((3, 3)), mode="constant") > 8.5
        slope[~full3] = np.nan

        # Roughness: std of residuals after removing a best-fit plane (5x5)
        n = 5
        r = np.arange(n) - n // 2
        X, Y = np.meshgrid(r * d, r * d)
        ones = np.ones((n, n))
        N = n * n
        mean_z = correlate(zf, ones, mode="nearest") / N
        mean_z2 = correlate(zf ** 2, ones, mode="nearest") / N
        sxz = correlate(zf, X, mode="nearest")
        syz = correlate(zf, Y, mode="nearest")
        sxx = (X ** 2).sum()
        syy = (Y ** 2).sum()
        a = sxz / sxx
        b = syz / syy
        var = mean_z2 - mean_z ** 2 - (a ** 2) * sxx / N - (b ** 2) * syy / N
        rough = np.sqrt(np.clip(var, 0, None))
        full5 = correlate(valid.astype(float), ones, mode="constant") > N - 0.5
        rough[~full5] = np.nan

        self.slope = slope
        self.roughness = rough

    def _build_cost(self):
        c = self.cfg
        s = self.slope
        rgh = np.nan_to_num(self.roughness, nan=c.rough_ref_m)

        blocked = ~np.isfinite(s) | (s > c.max_slope_deg)

        # safety buffer around impassable terrain
        buf = int(math.ceil(c.safety_buffer_m / self.res))
        if buf > 0:
            blocked = binary_dilation(blocked, iterations=buf)

        cost = (1.0
                + c.w_slope * (np.nan_to_num(s) / c.max_slope_deg) ** 2
                + c.w_rough * np.clip(rgh / c.rough_ref_m, 0, 3))

        self.terrain_blocked = blocked
        self.base_cost = cost
        self._refresh_blocked()

    def _refresh_blocked(self):
        self.blocked = self.terrain_blocked.copy()
        rr, cc = np.indices(self.shape)
        for ob in self.obstacles:
            r0, c0 = self.lonlat_to_rc(ob.lon, ob.lat)
            rad = (ob.radius_m + self.cfg.safety_buffer_m) / self.res
            self.blocked |= (rr - r0) ** 2 + (cc - c0) ** 2 <= rad ** 2

    # ------------------------------------------------------------------
    # Coordinates
    # ------------------------------------------------------------------

    def lonlat_to_rc(self, lon, lat):
        x, y = self._to_xy.transform(lon, lat)
        col = (x - self.transform.c) / self.transform.a
        row = (y - self.transform.f) / self.transform.e
        return int(math.floor(row)), int(math.floor(col))

    def rc_to_lonlat(self, row, col):
        x = self.transform.c + (col + 0.5) * self.transform.a
        y = self.transform.f + (row + 0.5) * self.transform.e
        lon, lat = self._to_lonlat.transform(x, y)
        return float(lon), float(lat)

    def _inside(self, r, c):
        return 0 <= r < self.shape[0] and 0 <= c < self.shape[1]

    def _snap(self, r, c, max_m=300):
        """Move a point that falls on blocked terrain to the nearest free cell."""
        if self._inside(r, c) and not self.blocked[r, c]:
            return r, c, 0.0
        free = ~self.blocked
        rr, cc = np.nonzero(free)
        if len(rr) == 0:
            raise ValueError("No passable terrain in the working area.")
        d2 = (rr - r) ** 2 + (cc - c) ** 2
        k = int(np.argmin(d2))
        moved = math.sqrt(d2[k]) * self.res
        if moved > max_m:
            raise ValueError(f"Point is {moved:.0f} m from passable terrain.")
        return int(rr[k]), int(cc[k]), moved

    # ------------------------------------------------------------------
    # Obstacles (re-routing input)
    # ------------------------------------------------------------------

    def add_obstacle(self, lon, lat, radius_m=40.0, kind="obstacle", note=""):
        self.obstacles.append(Obstacle(lon, lat, radius_m, kind, note))
        self._refresh_blocked()

    def clear_obstacles(self):
        self.obstacles = []
        self._refresh_blocked()

    def obstacles_geojson(self):
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [o.lon, o.lat]},
                "properties": {"radius_m": o.radius_m, "kind": o.kind, "note": o.note},
            } for o in self.obstacles],
        }

    # ------------------------------------------------------------------
    # A* search
    # ------------------------------------------------------------------

    def _astar(self, start, goal):
        H, W = self.shape
        cost = self.base_cost
        z = np.nan_to_num(self.z, nan=0.0)
        blocked = self.blocked
        res = self.res
        cp = self.cfg.climb_penalty

        sr, sc = start
        gr, gc = goal
        g = np.full(H * W, np.inf)
        parent = np.full(H * W, -1, dtype=np.int64)
        closed = np.zeros(H * W, dtype=bool)

        s_idx = sr * W + sc
        g_idx = gr * W + gc
        g[s_idx] = 0.0
        heap = [(math.hypot(sr - gr, sc - gc) * res, s_idx)]

        steps = [(dr, dc, res * math.hypot(dr, dc)) for dr, dc in self.NEIGHBORS]

        while heap:
            _, idx = heapq.heappop(heap)
            if closed[idx]:
                continue
            if idx == g_idx:
                break
            closed[idx] = True
            r, c = divmod(idx, W)
            gi = g[idx]
            ci = cost[r, c]
            zi = z[r, c]
            for dr, dc, dist in steps:
                nr, nc = r + dr, c + dc
                if nr < 0 or nc < 0 or nr >= H or nc >= W or blocked[nr, nc]:
                    continue
                nidx = nr * W + nc
                if closed[nidx]:
                    continue
                climb = z[nr, nc] - zi
                step = dist * 0.5 * (ci + cost[nr, nc]) + (cp * climb if climb > 0 else 0.0)
                ng = gi + step
                if ng < g[nidx]:
                    g[nidx] = ng
                    parent[nidx] = idx
                    h = math.hypot(nr - gr, nc - gc) * res
                    heapq.heappush(heap, (ng + h, nidx))

        if not np.isfinite(g[g_idx]):
            return None

        path = []
        idx = g_idx
        while idx != -1:
            path.append(divmod(int(idx), W))
            idx = parent[idx]
        return path[::-1]

    # ------------------------------------------------------------------
    # Public planning API
    # ------------------------------------------------------------------

    def plan(self, start_lonlat, goal_lonlats, simplify_every=3):
        """
        start_lonlat : (lon, lat)
        goal_lonlats : (lon, lat) or a list of them (visited in order)
        Returns a route dict ready for JSON / the HUD.
        """
        if isinstance(goal_lonlats[0], (int, float)):
            goal_lonlats = [goal_lonlats]

        legs = []
        cells = []
        cur = self.lonlat_to_rc(*start_lonlat)
        sr, sc, moved_start = self._snap(*cur)
        cur = (sr, sc)
        notes = []
        if moved_start:
            notes.append(f"Start moved {moved_start:.0f} m to the nearest safe ground.")

        for i, goal in enumerate(goal_lonlats, 1):
            gr, gc, moved = self._snap(*self.lonlat_to_rc(*goal))
            if moved:
                notes.append(f"Target {i} moved {moved:.0f} m to the nearest safe ground.")
            path = self._astar(cur, (gr, gc))
            if path is None:
                return {"ok": False, "reason": f"No safe path to target {i}.", "notes": notes}
            if cells:
                path = path[1:]
            legs.append(len(path))
            cells.extend(path)
            cur = (gr, gc)

        return self._describe(cells, notes, simplify_every)

    def reroute(self, current_lonlat, goal_lonlats, obstacle=None):
        """
        obstacle: optional dict {lon, lat, radius_m, kind, note}
                  reported by the astronaut before re-planning.
        """
        if obstacle:
            self.add_obstacle(obstacle["lon"], obstacle["lat"],
                              obstacle.get("radius_m", 40.0),
                              obstacle.get("kind", "obstacle"),
                              obstacle.get("note", ""))
        route = self.plan(current_lonlat, goal_lonlats)
        route["rerouted"] = True
        return route

    # ------------------------------------------------------------------
    # Route description (stats + HUD alerts)
    # ------------------------------------------------------------------

    def _describe(self, cells, notes, simplify_every):
        c = self.cfg
        pts = []
        cum = 0.0
        ascent = descent = 0.0
        minutes = 0.0
        prev = None
        for k, (r, col) in enumerate(cells):
            lon, lat = self.rc_to_lonlat(r, col)
            elev = float(self.z[r, col])
            slope = float(np.nan_to_num(self.slope[r, col]))
            rough = float(np.nan_to_num(self.roughness[r, col]))
            if prev is not None:
                pr, pc, pz = prev
                dist = self.res * math.hypot(r - pr, col - pc)
                dz = elev - pz
                cum += dist
                ascent += max(dz, 0)
                descent += max(-dz, 0)
                grade = dz / dist
                # Tobler-style speed, scaled to suited walking speed
                v = c.walk_speed_kmh * math.exp(-3.5 * abs(grade + 0.05)) / math.exp(-3.5 * 0.05)
                minutes += (dist / 1000) / max(v, 0.3) * 60
            prev = (r, col, elev)

            alerts = []
            if slope >= c.warn_slope_deg:
                alerts.append({"type": "slope", "level": "warning",
                               "msg": f"Steep slope {slope:.1f}°"})
            if rough >= c.rough_warn_m:
                alerts.append({"type": "roughness", "level": "caution",
                               "msg": f"Rough terrain ({rough:.1f} m)"})
            pts.append({
                "i": k, "lon": round(lon, 6), "lat": round(lat, 6),
                "elevation_m": round(elev, 1), "slope_deg": round(slope, 1),
                "roughness_m": round(rough, 2), "dist_m": round(cum, 1),
                "alerts": alerts,
            })

        # keep every Nth point (plus every point with an alert) for the UI
        keep = [p for p in pts if p["i"] % simplify_every == 0 or p["alerts"]]
        if keep[-1] is not pts[-1]:
            keep.append(pts[-1])

        hazard = "Low"
        max_slope = max(p["slope_deg"] for p in pts)
        if max_slope >= c.warn_slope_deg:
            hazard = "Moderate"
        if max_slope >= 0.9 * c.max_slope_deg:
            hazard = "High"

        return {
            "ok": True,
            "summary": {
                "length_m": round(cum, 1),
                "ascent_m": round(ascent, 1),
                "descent_m": round(descent, 1),
                "max_slope_deg": round(max_slope, 1),
                "mean_slope_deg": round(float(np.mean([p["slope_deg"] for p in pts])), 1),
                "est_duration_min": round(minutes),
                "hazard": hazard,
                "alerts": sum(1 for p in pts if p["alerts"]),
                "obstacles_known": len(self.obstacles),
            },
            "notes": notes,
            "points": keep,
            "geojson": {
                "type": "Feature",
                "geometry": {"type": "LineString",
                             "coordinates": [[p["lon"], p["lat"]] for p in keep]},
                "properties": {"name": "Marswalk safe route"},
            },
        }

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------

    def save_layers(self, folder):
        """Save slope / roughness / cost as GeoTIFFs (for the map team)."""
        import os
        os.makedirs(folder, exist_ok=True)
        profile = dict(driver="GTiff", height=self.shape[0], width=self.shape[1],
                       count=1, dtype="float32", crs=self.crs_wkt,
                       transform=self.transform, nodata=-32767.0, compress="deflate")
        cost = np.where(self.blocked, np.nan, self.base_cost)
        for name, arr in [("dem_clip", self.z), ("slope", self.slope),
                          ("roughness", self.roughness), ("cost", cost)]:
            with rasterio.open(os.path.join(folder, f"{name}.tif"), "w", **profile) as dst:
                dst.write(np.nan_to_num(arr, nan=-32767.0).astype("float32"), 1)

    @staticmethod
    def save_json(obj, path):
        with open(path, "w") as f:
            json.dump(obj, f, indent=2)
