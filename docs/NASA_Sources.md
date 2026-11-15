# NASA / USGS data sources used

## 1. Terrain model (main source)
- **MRO CTX stereo DTM** — USGS Astrogeology, "mro_ctx_controlled_usgs_dtms" collection (Mars Reconnaissance Orbiter, Context Camera — NASA).
- Product ID: `T01_000815_1749_XN_05S222W__P22_009571_1756_XI_04S222W` ("Third DEM" in our notebook)
- Asset: `geoid_adjusted_dem` (cloud-optimized GeoTIFF), 20 m/pixel, CRS: Mars 2015 sphere, equirectangular.
- Catalog (STAC search): https://g6goyz4w56.execute-api.us-west-2.amazonaws.com/prod/search
- Covers all route points; two other CTX DTMs were compared (vertical offsets of ~505 m and ~73 m = different vertical references; terrain shape agrees).

## 2. Imagery
- **NASA/JPL Mars Trek — Gale_CTX_BlockAdj_dd** (CTX mosaic of Gale Crater), WMTS:
  https://trek.nasa.gov/tiles/Mars/EQ/Gale_CTX_BlockAdj_dd/1.0.0/WMTSCapabilities.xml
- Viking MDIM 2.1 colour mosaic (global background), Mars Trek.
- HiRISE mosaic of the Curiosity area (`curiosity_hirise_mosaic.tif`, ~8 GB) in the team Drive (Rimas).

## 3. Curiosity rover traverse (optional layer)
- NASA/JPL MMGIS waypoints feed: https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json
  (sol, lat/lon, geoid elevation, odometer) — used by `curiosity_traverse.py`.

## Derived layers (our code)
- Slope: Horn 3×3 method. Roughness: std of residuals after fitting a local plane over 5×5 cells (~100 m).
- Cost: 1 + 4·(slope/15)² + 2·min(roughness/2, 3); slope > 15° and NoData = impassable, 20 m safety buffer.
- Thresholds are illustrative screening values, not NASA EVA safety limits.
