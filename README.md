# geosteeze

**Compile live geographic data endpoints and explore them on an interactive map.**

geosteeze finds geographic data that is served *live* — WMS/WMTS tiles, Esri
map/feature services, XYZ basemaps, and GeoJSON feeds — and that can be piped
straight into a web map with **no download step**. A Python scraper discovers
and validates these endpoints into a normalized `catalog.json`; a zero-build
[Leaflet](https://leafletjs.com/) + [esri-leaflet](https://developers.arcgis.com/esri-leaflet/)
front-end (dark theme, mobile-friendly) lets you browse the catalog and drop any
layer onto the map.

The curated seeds and discovery crawlers are tuned toward **global satellite
imagery, Arctic sea-ice extent, and Canadian data** (Environment Canada GeoMet,
NRCan, and the `open.canada.ca` open-data portal).

```
┌─────────────┐     discover + validate      ┌──────────────┐    fetch    ┌───────────┐
│  catalogs   │ ───────────────────────────► │ catalog.json │ ──────────► │  Leaflet  │
│ ArcGIS/CKAN │     scraper/ (Python)        │  (docs/)     │             │  web map  │
│  + seeds    │                              └──────────────┘             └───────────┘
└─────────────┘
```

---

## Quick start

```bash
# 1. (optional) install the scraper's one dependency
pip install -r requirements.txt

# 2. A working catalog of curated seed endpoints already ships in docs/catalog.json.
#    Serve the front-end and open the map:
python serve.py
#    → http://localhost:8000
```

Click any layer in the sidebar to stream it onto the map. Use the category
chips and search box to filter, the opacity sliders to blend overlays, and the
⊕ button to fly to a layer's extent. On phones the sidebar collapses into a
slide-in drawer (tap ☰) so the map gets the full screen.

> **No account or API key needed.** The map uses a dark
> [CARTO](https://carto.com/) basemap by default; change `basemapUrl` in
> `docs/config.js` to any `{z}/{x}/{y}` tile template.

### Host it as a static site (GitHub Pages)

The front-end is fully static, so you can publish `docs/` straight to GitHub
Pages and open the map from any browser (including your phone):

1. Push this branch to GitHub.
2. In the repo, go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to *Deploy from a branch*,
   pick this branch, and choose the **`/docs`** folder. Save.
4. Open `https://<owner>.github.io/<repo>/`.

The seed catalog's feeds (NASA GIBS global imagery, Arctic sea-ice
concentration, Environment Canada GeoMet radar, USGS earthquakes, …) are
CORS-enabled and stream in directly — no `serve.py` proxy needed. A
`.nojekyll` file is included so Pages serves the folder as-is.

---

## Discovering more endpoints (running the scraper)

The shipped catalog contains ~16 hand-verified seed services. To discover
thousands more, run the crawlers against public catalogs:

```bash
# Validate the seeds only (fast):
python -m scraper.scrape --sources seed

# Full crawl: seeds + ArcGIS Online + open.canada.ca (CKAN), validated,
# dropping anything that doesn't answer:
python -m scraper.scrape --sources seed arcgis_online ckan --drop-dead

# Offline: regenerate the seed catalog with no network calls:
python -m scraper.scrape --sources seed --no-validate
```

The result is written to `docs/catalog.json`, which the front-end loads on
refresh. Useful flags:

| flag | meaning |
|------|---------|
| `--sources ...` | which adapters to run: `seed`, `arcgis_online`, `ckan` |
| `--drop-dead` | exclude endpoints that fail their liveness check |
| `--no-validate` | skip network validation entirely (offline) |
| `--per-topic N` | max ArcGIS Online results per topic query (default 30) |
| `--ckan-rows N` | max CKAN datasets per resource format (default 200) |
| `--max-layers N` | max layers extracted per WMS/WMTS service root (default 40) |
| `--out PATH` | output path (default `docs/catalog.json`) |

> **Note on network access:** the crawlers reach out to `www.arcgis.com`,
> `open.canada.ca`, and the individual services they discover. Run the
> scraper from an environment with open outbound HTTPS. (In a locked-down CI
> sandbox, only `--sources seed --no-validate` will succeed.)

---

## How it works

### Scraper (`scraper/`)

| module | responsibility |
|--------|----------------|
| `models.py` | `Endpoint` dataclass — the normalized record + stable id |
| `sources/seeds.py` | curated, hand-verified live services |
| `sources/arcgis_online.py` | crawls the ArcGIS Online content search API by topic |
| `sources/ckan.py` | crawls a CKAN portal (open.canada.ca) by resource format |
| `sources/ogc.py` | parses WMS/WMTS `GetCapabilities` → per-layer endpoints |
| `validate.py` | cheap liveness checks (live? latency? CORS?) run concurrently |
| `scrape.py` | CLI that ties collect → expand → dedupe → validate → write together |

Each endpoint is validated with a check appropriate to its type, recording
whether it's live, its latency, whether it sends permissive CORS headers, and
its coordinate reference system (`crs`):

- **WMS** — a real `GetMap` in **EPSG:3857**, the projection the Leaflet map
  uses. A layer that renders is kept; one that returns a CRS `ServiceException`
  (it can't serve Web Mercator) is dropped, so the catalog only contains WMS
  layers that actually line up on the map.
- **WMTS** — a real `GetTile` for ordinary caches (NASA GIBS is checked via its
  capabilities and drawn through its dedicated EPSG:3857 REST endpoint). The OGC
  parser reads each tile-matrix-set's `SupportedCRS` and discards non-Web-
  Mercator caches (e.g. EPSG:3978 Canada Lambert) that a 2D map can't reproject.
- **ArcGIS** — the `?f=json` descriptor, capturing the service's native `wkid`.
  Dynamic services are reprojected server-side; only Web-Mercator tile caches
  are drawn directly.
- **XYZ / GeoJSON** — a sample tile's content-type / the first bytes of the feed.

### Front-end (`docs/`)

A dependency-free single page (`index.html` + `app.js` + `style.css`) that loads
Leaflet + esri-leaflet from a CDN, fetches `catalog.json`, and maps each endpoint
type to the right Leaflet layer. It's a dark-themed, touch-friendly 2D web map —
no WebGL globe or 3D Tiles required, since every catalog layer is plain imagery
or vector that drapes onto the map directly. Each row shows the layer's
projection (`crs` badge) and its endpoint URL (click to open, or copy it), so
you can see and reach the underlying service at a glance:

| catalog type | Leaflet layer |
|--------------|---------------|
| `XYZ` | `L.tileLayer` |
| `WMS` | `L.tileLayer.wms` |
| `WMTS` | `L.tileLayer` (web-mercator KVP `GetTile`; NASA GIBS via its EPSG:3857 REST endpoint) |
| `ArcGISMapServer` | `L.esri.dynamicMapLayer` |
| `ArcGISImageServer` | `L.esri.imageMapLayer` |
| `ArcGISFeatureServer` | `L.esri.featureLayer` |
| `GeoJSON` | fetched → `L.geoJSON` |

### Local server + CORS proxy (`serve.py`)

`serve.py` serves `docs/` and, by default, exposes a `/proxy?url=…` endpoint.
Imagery (tiles, WMS `GetMap`) loads as `<img>` and isn't subject to CORS, but
GeoJSON and ArcGIS feature queries are fetched with JavaScript and **are**. When
served via `serve.py`, the front-end routes those fetches through the proxy so
CORS-restricted feeds still stream in. Disable it with `--no-proxy`. The proxy
refuses non-HTTP(S) URLs and blocks private/loopback hosts as a basic SSRF
guard; it is a development convenience, not a production gateway.

---

## Configuration (`docs/config.js`)

| key | default | purpose |
|-----|---------|---------|
| `catalogUrl` | `"catalog.json"` | where to load the catalog from |
| `proxyUrl` | `""` | CORS proxy prefix (`serve.py` sets `/proxy?url=`) |
| `defaultDate` | `"2024-03-05"` | date for time-aware WMTS (NASA GIBS daily imagery + sea ice) |
| `basemapUrl` | CARTO `dark_all` | dark `{z}/{x}/{y}` basemap tile template |
| `basemapAttribution` | OSM + CARTO | attribution string for the basemap |

---

## Catalog format

```jsonc
{
  "generated_at": "2026-06-27T03:20:39+00:00",
  "sources": ["seed"],
  "stats": { "total": 16, "live": 16, "by_type": {…}, "by_category": {…} },
  "endpoints": [
    {
      "id": "ab12cd34ef56",
      "title": "USGS Earthquakes — past 24 hours",
      "type": "GeoJSON",
      "url": "https://earthquake.usgs.gov/.../all_day.geojson",
      "category": "hazards",
      "layer": null,
      "bbox": [-180, -85, 180, 85],
      "crs": "EPSG:4326",
      "attribution": "USGS Earthquake Hazards Program",
      "live": true, "cors": true, "latency_ms": 142,
      "checked_at": "2026-06-27T03:20:39+00:00"
    }
  ]
}
```

## License

MIT — see `LICENSE`.
