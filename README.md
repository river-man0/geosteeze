# geosteeze

**Compile live geographic data endpoints and explore them on a Cesium globe.**

geosteeze finds geographic data that is served *live* — WMS/WMTS tiles, Esri
map/feature services, XYZ basemaps, and GeoJSON feeds — and that can be piped
straight into a web map with **no download step**. A Python scraper discovers
and validates these endpoints into a normalized `catalog.json`; a zero-build
[Cesium.js](https://cesium.com/platform/cesiumjs/) front-end lets you browse the
catalog and drop any layer onto a 3D globe.

```
┌─────────────┐     discover + validate      ┌──────────────┐    fetch    ┌───────────┐
│  catalogs   │ ───────────────────────────► │ catalog.json │ ──────────► │  Cesium   │
│ ArcGIS/CKAN │     scraper/ (Python)        │  (web/)      │             │  globe    │
│  + seeds    │                              └──────────────┘             └───────────┘
└─────────────┘
```

---

## Quick start

```bash
# 1. (optional) install the scraper's one dependency
pip install -r requirements.txt

# 2. A working catalog of curated seed endpoints already ships in web/catalog.json.
#    Serve the front-end and open the globe:
python serve.py
#    → http://localhost:8000
```

Click any layer in the sidebar to stream it onto the globe. Use the category
chips and search box to filter, the opacity sliders to blend overlays, and the
⊕ button to fly to a layer's extent.

> **No Cesium Ion account needed.** The globe runs Ion-free with an
> OpenStreetMap basemap by default. Add a free token in `web/config.js`
> (`cesiumIonToken`) to unlock world terrain and premium imagery.

---

## Discovering more endpoints (running the scraper)

The shipped catalog contains ~16 hand-verified seed services. To discover
thousands more, run the crawlers against public catalogs:

```bash
# Validate the seeds only (fast):
python -m scraper.scrape --sources seed

# Full crawl: seeds + ArcGIS Online + data.gov (CKAN), validated,
# dropping anything that doesn't answer:
python -m scraper.scrape --sources seed arcgis_online ckan --drop-dead

# Offline: regenerate the seed catalog with no network calls:
python -m scraper.scrape --sources seed --no-validate
```

The result is written to `web/catalog.json`, which the front-end loads on
refresh. Useful flags:

| flag | meaning |
|------|---------|
| `--sources ...` | which adapters to run: `seed`, `arcgis_online`, `ckan` |
| `--drop-dead` | exclude endpoints that fail their liveness check |
| `--no-validate` | skip network validation entirely (offline) |
| `--per-topic N` | max ArcGIS Online results per topic query (default 30) |
| `--ckan-rows N` | max CKAN datasets per resource format (default 200) |
| `--max-layers N` | max layers extracted per WMS/WMTS service root (default 40) |
| `--out PATH` | output path (default `web/catalog.json`) |

> **Note on network access:** the crawlers reach out to `www.arcgis.com`,
> `catalog.data.gov`, and the individual services they discover. Run the
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
| `sources/ckan.py` | crawls a CKAN portal (data.gov) by resource format |
| `sources/ogc.py` | parses WMS/WMTS `GetCapabilities` → per-layer endpoints |
| `validate.py` | cheap liveness checks (live? latency? CORS?) run concurrently |
| `scrape.py` | CLI that ties collect → expand → dedupe → validate → write together |

Each endpoint is validated with a check appropriate to its type — an ArcGIS
`?f=json` descriptor, an OGC `GetCapabilities` document, a sample tile's
content-type, or the first bytes of a GeoJSON response — recording whether it's
live, its latency, and whether it sends permissive CORS headers.

### Front-end (`web/`)

A dependency-free single page (`index.html` + `app.js` + `style.css`) that loads
Cesium from a CDN, fetches `catalog.json`, and maps each endpoint type to the
right Cesium provider:

| catalog type | Cesium provider |
|--------------|-----------------|
| `XYZ` | `UrlTemplateImageryProvider` |
| `WMS` | `WebMapServiceImageryProvider` |
| `WMTS` | `WebMapTileServiceImageryProvider` |
| `ArcGISMapServer` / `ArcGISImageServer` | `ArcGisMapServerImageryProvider` |
| `ArcGISFeatureServer` | queried as GeoJSON → `GeoJsonDataSource` |
| `GeoJSON` | `GeoJsonDataSource` |

### Local server + CORS proxy (`serve.py`)

`serve.py` serves `web/` and, by default, exposes a `/proxy?url=…` endpoint.
Imagery (tiles, WMS `GetMap`) loads as `<img>` and isn't subject to CORS, but
GeoJSON and ArcGIS feature queries are fetched with JavaScript and **are**. When
served via `serve.py`, the front-end routes those fetches through the proxy so
CORS-restricted feeds still stream in. Disable it with `--no-proxy`. The proxy
refuses non-HTTP(S) URLs and blocks private/loopback hosts as a basic SSRF
guard; it is a development convenience, not a production gateway.

---

## Configuration (`web/config.js`)

| key | default | purpose |
|-----|---------|---------|
| `cesiumIonToken` | `""` | optional Cesium Ion token (premium terrain/imagery) |
| `catalogUrl` | `"catalog.json"` | where to load the catalog from |
| `proxyUrl` | `""` | CORS proxy prefix (`serve.py` sets `/proxy?url=`) |
| `defaultDate` | `"2023-08-01"` | date for time-aware WMTS (e.g. NASA GIBS daily) |
| `cesiumVersion` | `"1.119"` | Cesium build loaded from the CDN |

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
      "attribution": "USGS Earthquake Hazards Program",
      "live": true, "cors": true, "latency_ms": 142,
      "checked_at": "2026-06-27T03:20:39+00:00"
    }
  ]
}
```

## License

MIT — see `LICENSE`.
