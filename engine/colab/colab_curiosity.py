# =====================================================
# ASTRO-HEROES | REAL CURIOSITY TRAVERSE + NASA TERRAIN
# New Colab cell. Needs (uploaded to /content):
#   marswalk_router.py, curiosity_traverse.py
# =====================================================

import sys, json, os, requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, "/content")
from curiosity_traverse import build_curiosity_dataset, validation_report, to_geojson

# ---------- 1. NASA/USGS CTX DTM (Third DEM) ----------
search_url = "https://g6goyz4w56.execute-api.us-west-2.amazonaws.com/prod/search"
third_item_id = "T01_000815_1749_XN_05S222W__P22_009571_1756_XI_04S222W"
item = requests.post(search_url, json={
    "collections": ["mro_ctx_controlled_usgs_dtms"],
    "ids": [third_item_id], "limit": 1}, timeout=60).json()["features"][0]
DEM_URL = item["assets"]["geoid_adjusted_dem"]["href"]

# ---------- 2. Settings ----------
SOL_MIN = None        # e.g. 3000  -> only the Mount Sharp climb
SOL_MAX = None        # e.g. 4500
SPACING_M = 150       # one waypoint every ~150 m of real rover path
MAX_POINTS = 50       # same size as the old CSV

# ---------- 3. Build the dataset ----------
raw, curiosity_df, router = build_curiosity_dataset(
    DEM_URL, sol_min=SOL_MIN, sol_max=SOL_MAX,
    spacing_m=SPACING_M, max_points=MAX_POINTS)

print("NASA Curiosity localizations in feed:", len(raw))
print("Sol range in feed:", raw["Sol"].min(), "to", raw["Sol"].max())
print("Waypoints selected:", len(curiosity_df))
print("Inside DTM:", curiosity_df["DEM_Elevation_m"].notna().sum())

print("\nVALIDATION — NASA rover elevation vs CTX DTM:")
print(json.dumps(validation_report(curiosity_df), indent=2))

print("\nRISK LEVELS (from real slope/roughness):")
print(curiosity_df["Risk_Level"].value_counts())

display(curiosity_df[[
    "Waypoint_ID", "Sol", "Latitude", "Longitude",
    "NASA_Elevation_m", "DEM_Elevation_m", "DEM_Slope_deg", "DEM_Roughness_m",
    "Est_Boot_Sinkage_cm", "Est_Traction_Margin", "Est_Stability_Index", "Risk_Level"
]].head(15))

# ---------- 4. Map: real traverse on the slope layer ----------
colors = {"Low": "lime", "Medium": "orange", "High": "red", "Unknown": "grey"}
fig, ax = plt.subplots(figsize=(10, 9))
im = ax.imshow(np.ma.masked_invalid(router.slope), cmap="terrain", vmin=0, vmax=25)
rc = [router.lonlat_to_rc(lo, la) for lo, la in zip(curiosity_df["Longitude"], curiosity_df["Latitude"])]
ax.plot([c for _, c in rc], [r for r, _ in rc], color="white", lw=1.5, alpha=0.8, label="Curiosity traverse")
for lvl, col in colors.items():
    m = curiosity_df["Risk_Level"] == lvl
    if m.any():
        pts = [rc[i] for i in np.where(m)[0]]
        ax.scatter([c for _, c in pts], [r for r, _ in pts], c=col, s=45,
                   edgecolors="black", zorder=3, label=f"{lvl} risk")
fig.colorbar(im, ax=ax, label="Slope (degrees)")
ax.set_title("ASTRO-HEROES | Real Curiosity Traverse on NASA CTX DTM Slope")
ax.legend()
plt.show()

# ---------- 5. Elevation profile: NASA rover vs DTM ----------
plt.figure(figsize=(12, 5))
plt.plot(curiosity_df["Path_Distance_m"] / 1000, curiosity_df["DEM_Elevation_m"],
         "o-", ms=3, label="CTX DTM elevation")
if curiosity_df["NASA_Elevation_m"].notna().any():
    plt.plot(curiosity_df["Path_Distance_m"] / 1000, curiosity_df["NASA_Elevation_m"],
             "s--", ms=3, label="Curiosity (NASA) elevation")
plt.xlabel("Distance along traverse (km)")
plt.ylabel("Elevation (m)")
plt.title("ASTRO-HEROES | Elevation Profile — Rover vs Terrain Model")
plt.grid(alpha=0.3); plt.legend(); plt.show()

# ---------- 6. Export ----------
out = "/content/ASTRO_HEROES/outputs"
os.makedirs(out, exist_ok=True)
curiosity_df.to_csv(f"{out}/Curiosity_Traverse_NASA_DEM.csv", index=False)
with open(f"{out}/Curiosity_Traverse_NASA_DEM.geojson", "w") as f:
    json.dump(to_geojson(curiosity_df), f)
print("\nSaved: Curiosity_Traverse_NASA_DEM.csv + .geojson in", out)

# ---------- 7. Our planner vs the rover's real path (one segment) ----------
valid = curiosity_df.index[curiosity_df["DEM_Elevation_m"].notna()].tolist()
if len(valid) >= 2:
    mid = len(valid) // 2
    a, b = valid[mid], valid[min(len(valid) - 1, mid + 8)]
    start = (curiosity_df.at[a, "Longitude"], curiosity_df.at[a, "Latitude"])
    goal = (curiosity_df.at[b, "Longitude"], curiosity_df.at[b, "Latitude"])
    try:
        plan = router.plan(start, goal)
        print("\nPLANNED SAFE WALK between waypoints", a + 1, "and", b + 1)
        print(json.dumps(plan.get("summary", plan), indent=2))
    except ValueError as e:
        print("Planner note:", e)
