"""
ASTRO-HEROES | Build the real Curiosity waypoint dataset (local run)
Outputs (in ./outputs):
  Curiosity_Traverse_NASA_DEM.csv / .geojson
  curiosity_map.png, curiosity_profile.png, validation.json
and copies the GeoJSON to ./web so the game can show it.
"""
import json, os, shutil
import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from curiosity_traverse import build_curiosity_dataset, validation_report, to_geojson

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
os.makedirs(OUT, exist_ok=True)

item = requests.post(
    "https://g6goyz4w56.execute-api.us-west-2.amazonaws.com/prod/search",
    json={"collections": ["mro_ctx_controlled_usgs_dtms"],
          "ids": ["T01_000815_1749_XN_05S222W__P22_009571_1756_XI_04S222W"], "limit": 1},
    timeout=60).json()["features"][0]
DEM_URL = item["assets"]["geoid_adjusted_dem"]["href"]
print("DEM:", DEM_URL)

raw, df, router = build_curiosity_dataset(DEM_URL, spacing_m=150, max_points=50)
print("NASA localizations in feed:", len(raw), "| sols", raw["Sol"].min(), "-", raw["Sol"].max())
print("Waypoints:", len(df), "| inside DTM:", int(df["DEM_Elevation_m"].notna().sum()))

val = validation_report(df)
print(json.dumps(val, indent=2))
print(df["Risk_Level"].value_counts())

df.to_csv(os.path.join(OUT, "Curiosity_Traverse_NASA_DEM.csv"), index=False)
gj = to_geojson(df)
with open(os.path.join(OUT, "Curiosity_Traverse_NASA_DEM.geojson"), "w") as f:
    json.dump(gj, f)
with open(os.path.join(OUT, "validation.json"), "w") as f:
    json.dump(val, f, indent=2)
os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
shutil.copy(os.path.join(OUT, "Curiosity_Traverse_NASA_DEM.geojson"), os.path.join(HERE, "web", "curiosity.geojson"))

colors = {"Low": "lime", "Medium": "orange", "High": "red", "Unknown": "grey"}
fig, ax = plt.subplots(figsize=(10, 9))
im = ax.imshow(np.ma.masked_invalid(router.slope), cmap="terrain", vmin=0, vmax=25)
rc = [router.lonlat_to_rc(lo, la) for lo, la in zip(df["Longitude"], df["Latitude"])]
ax.plot([c for _, c in rc], [r for r, _ in rc], color="white", lw=1.5, label="Curiosity traverse")
for lvl, col in colors.items():
    idx = np.where(df["Risk_Level"] == lvl)[0]
    if len(idx):
        ax.scatter([rc[i][1] for i in idx], [rc[i][0] for i in idx], c=col, s=45, edgecolors="black", zorder=3, label=f"{lvl} risk")
fig.colorbar(im, ax=ax, label="Slope (degrees)")
ax.set_title("ASTRO-HEROES | Real Curiosity Traverse on NASA CTX DTM Slope")
ax.legend(); fig.savefig(os.path.join(OUT, "curiosity_map.png"), dpi=130, bbox_inches="tight")

plt.figure(figsize=(12, 5))
plt.plot(df["Path_Distance_m"] / 1000, df["DEM_Elevation_m"], "o-", ms=3, label="CTX DTM elevation")
if df["NASA_Elevation_m"].notna().any():
    plt.plot(df["Path_Distance_m"] / 1000, df["NASA_Elevation_m"], "s--", ms=3, label="Curiosity (NASA) elevation")
plt.xlabel("Distance along traverse (km)"); plt.ylabel("Elevation (m)")
plt.title("ASTRO-HEROES | Elevation Profile — Rover vs Terrain Model")
plt.grid(alpha=0.3); plt.legend(); plt.savefig(os.path.join(OUT, "curiosity_profile.png"), dpi=130, bbox_inches="tight")
print("Saved outputs to", OUT)
