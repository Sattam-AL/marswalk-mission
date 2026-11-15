# Marswalk Mission — ASTRO-HEROES

**NASA Space Apps Challenge 2026 · Interplanetary Survival Guide: Martian Map**

▶ **Play:** https://sattam-al.github.io/marswalk-mission/

An interactive Marswalk planner on real NASA terrain of Gale Crater / Mount Sharp (English / العربية):
- Terrain: MRO CTX stereo DTM (USGS Astrogeology / NASA), 20 m/pixel — slope (Horn 3×3) and roughness (5×5 detrended).
- Route engine: cost grid + A* with a climb penalty and a 20 m safety buffer; slopes over 15° are no-go (illustrative thresholds, not NASA EVA limits).
- Live re-routing: report a hazard and a new safe route is computed on site (Earth is 4–24 min away by radio).
- Learning map: every reported hazard is saved as a no-go layer for later routes.
- Planner mode: tap the map to choose your own science stops; live elevation profile and mission log.
- Base map: NASA/JPL Mars Trek CTX imagery with DTM shaded relief, slope, roughness and walk-cost overlays.

## Repository
| Folder | Contents |
|---|---|
| `index.html` | Browser version of the game (route engine runs in the page) — published at the Play link |
| `engine/` | Python route engine (`marswalk_router.py`), Curiosity traverse builder, FastAPI server (`api.py`), Windows launcher (`start_game.bat`), API web UI (`web/`) |
| `engine/colab/` | Ready Colab cells: route demo, Curiosity traverse, helper cells (DEM URL, Drive save, zip, layer previews) |
| `notebooks/` | `ASTRO_HEROES_Marswalk_DEM_Ready.ipynb` — full analysis notebook (runs top to bottom, includes the engine) |
| `data/route_outputs/` | Planned route, re-routed route and reported obstacle, computed on the NASA CTX DTM |
| `data/terrain_layers/` | Elevation, slope, roughness and walk-cost maps + 20 m terrain grids (`.npz`: slope, elev, rough) |
| `docs/` | NASA data sources, CSV data review, project details, AI disclosure, team guide (Arabic) |
| `images/` | Colab result on the real DTM and game screenshots; `illustrations_ai/` = AI-assisted concept drawings (internal) |
| `video/` | Explainer motion-graphics video (AI-assisted, internal) |

Run the Python version: `engine/start_game.bat` on Windows, or `uvicorn api:app` from `engine/`.

## AI disclosure
AI tools (Claude by Anthropic) assisted in writing the code. All terrain data comes from NASA/USGS sources; maps and routes are computed by our code from that data.
