# =====================================================
# ASTRO-HEROES | MARSWALK ROUTE ENGINE — COLAB DEMO
# Paste into a new cell AFTER the cell that defines
# `third_dem_url` (STEP 68), and upload marswalk_router.py
# to /content first.
# =====================================================

import sys, json
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, "/content")
from marswalk_router import MarswalkRouter, RouterConfig

# Real NASA/USGS CTX DTM (geoid-adjusted, 20 m/pixel)
DEM_URL = third_dem_url

# Start = habitat / landing point, targets = science stops (lon, lat)
# (example points inside Gale / Mount Sharp; replace with the team's choice)
HABITAT = (137.44293, -4.58130)

# Size of the obstacle the astronaut reports (metres)
OBSTACLE_RADIUS_M = 300
TARGETS = [
    (137.49000, -4.61500),   # science stop 1
    (137.54758, -4.65420),   # science stop 2
]

cfg = RouterConfig(
    max_slope_deg=15,     # impassable above this (illustrative)
    warn_slope_deg=10,    # HUD warning
    safety_buffer_m=20,
)

router = MarswalkRouter(DEM_URL, [HABITAT, *TARGETS], cfg)
print("Working grid:", router.shape, "cells at", router.res, "m")

# 1) Plan the safe route
route = router.plan(HABITAT, TARGETS)
print("PLANNED ROUTE:", json.dumps(route["summary"], indent=2))

# 2) Astronaut reports an obstacle ahead -> re-route from current position
current = route["points"][len(route["points"]) // 4]
ahead = route["points"][len(route["points"]) // 2]

new_route = router.reroute(
    current_lonlat=(current["lon"], current["lat"]),
    goal_lonlats=TARGETS,
    obstacle={"lon": ahead["lon"], "lat": ahead["lat"],
              "radius_m": OBSTACLE_RADIUS_M, "kind": "boulder field",
              "note": "Reported by astronaut"},
)
print("RE-ROUTED:", json.dumps(new_route["summary"], indent=2))

# 3) Plot on the slope map
fig, ax = plt.subplots(figsize=(10, 9))
im = ax.imshow(np.ma.masked_invalid(router.slope), cmap="terrain", vmin=0, vmax=25)
ax.imshow(np.ma.masked_where(~router.blocked, router.blocked), cmap="Reds", alpha=0.35)
for r, color, label in [(route, "cyan", "Planned"), (new_route, "lime", "Re-routed")]:
    rc = [router.lonlat_to_rc(p["lon"], p["lat"]) for p in r["points"]]
    ax.plot([c for _, c in rc], [r_ for r_, _ in rc], color=color, lw=3, label=label)
for lon, lat in [HABITAT, *TARGETS]:
    rr, cc = router.lonlat_to_rc(lon, lat)
    ax.plot(cc, rr, "o", ms=10, mec="white", mfc="blue")
orr, occ = router.lonlat_to_rc(ahead["lon"], ahead["lat"])
ax.add_patch(plt.Circle((occ, orr), OBSTACLE_RADIUS_M / router.res, color="red", fill=False, lw=2))
fig.colorbar(im, ax=ax, label="Slope (degrees)")
ax.set_title("ASTRO-HEROES | Safe Marswalk Route + Re-routing (CTX DTM)")
ax.legend()
plt.show()

# 4) Export for the map / HUD team
router.save_layers("/content/ASTRO_HEROES/outputs/layers")      # dem_clip, slope, roughness, cost .tif
router.save_json(route, "/content/ASTRO_HEROES/outputs/route.json")
router.save_json(new_route, "/content/ASTRO_HEROES/outputs/route_rerouted.json")
router.save_json(router.obstacles_geojson(), "/content/ASTRO_HEROES/outputs/obstacles.geojson")
print("Exports saved.")
