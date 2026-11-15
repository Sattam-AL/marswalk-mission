# Marswalk Mission — ASTRO-HEROES

**NASA Space Apps Challenge 2026 · Interplanetary Survival Guide: Martian Map**

▶ **Play:** https://sattam-al.github.io/marswalk-mission/

An interactive Marswalk planner on real NASA terrain of Gale Crater / Mount Sharp:
- Terrain: MRO CTX stereo DTM (USGS Astrogeology / NASA), 20 m/pixel — slope (Horn 3×3) and roughness (5×5 detrended).
- Route engine: cost grid + A* with a climb penalty and a 20 m safety buffer; slopes over 15° are no-go (illustrative thresholds, not NASA EVA limits).
- Live re-routing: report a hazard and a new safe route is computed on site (Earth is 4–24 min away by radio).
- Learning map: every reported hazard is saved as a no-go layer for later routes.

## Repository
- `index.html` — browser version (engine runs in the page).
- `engine/` — Python engine (`marswalk_router.py`), Curiosity traverse builder (`curiosity_traverse.py`), FastAPI server (`api.py`) and web game (`web/`). Run `engine/start_game.bat` on Windows or `uvicorn api:app` from `engine/`.

## AI disclosure
AI tools (Claude by Anthropic) assisted in writing the code. All terrain data comes from NASA/USGS sources; maps and routes are computed by our code from that data.
