# =====================================================
# ASTRO-HEROES | Colab helper cells (paste each block in its own cell)
# =====================================================

# --- Cell A: get the NASA/USGS "Third DEM" URL ---
import requests
search_url = "https://g6goyz4w56.execute-api.us-west-2.amazonaws.com/prod/search"
third_item_id = "T01_000815_1749_XN_05S222W__P22_009571_1756_XI_04S222W"
item = requests.post(search_url, json={"collections": ["mro_ctx_controlled_usgs_dtms"],
                                       "ids": [third_item_id], "limit": 1}, timeout=60).json()["features"][0]
third_dem_url = item["assets"]["geoid_adjusted_dem"]["href"]
print("Third DEM:", third_dem_url)

# --- Cell B: save outputs to Google Drive ---
from google.colab import drive
import shutil
drive.mount("/content/drive")
shutil.copytree("/content/ASTRO_HEROES/outputs", "/content/drive/MyDrive/ASTRO_HEROES_outputs", dirs_exist_ok=True)
print("Saved to Google Drive")

# --- Cell C: download all outputs as one zip ---
from google.colab import files
shutil.make_archive("/content/ASTRO_HEROES_outputs", "zip", "/content/ASTRO_HEROES/outputs")
files.download("/content/ASTRO_HEROES_outputs.zip")

# --- Cell D: PNG previews of the GeoTIFF layers ---
import rasterio, matplotlib.pyplot as plt
folder = "/content/ASTRO_HEROES/outputs/layers"
for name, cmap in {"dem_clip": "terrain", "slope": "turbo", "roughness": "viridis", "cost": "magma"}.items():
    with rasterio.open(f"{folder}/{name}.tif") as src:
        data = src.read(1, masked=True)
    plt.figure(figsize=(8, 6)); plt.imshow(data, cmap=cmap); plt.colorbar(); plt.title(name); plt.axis("off")
    plt.savefig(f"{folder}/{name}.png", dpi=150, bbox_inches="tight"); plt.show()
