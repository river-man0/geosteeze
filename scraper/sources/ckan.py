"""Discover live endpoints from CKAN open-data portals (default: data.gov).

CKAN's ``package_search`` API returns datasets whose resources frequently point
at live OGC or Esri services. We filter by resource format and translate the
matching resources into normalized Endpoints.
"""

from __future__ import annotations

from typing import List

import requests

from ..models import Endpoint

DEFAULT_PORTAL = "https://catalog.data.gov"
USER_AGENT = "geosteeze-scraper/0.1 (+https://github.com/river-man0/geosteeze)"

# CKAN resource format (lower-cased) -> normalized endpoint type.
_FORMAT_MAP = {
    "wms": "WMS",
    "wmts": "WMTS",
    "esri rest": "ArcGISMapServer",
    "arcgis geoservices rest api": "ArcGISMapServer",
    "geojson": "GeoJSON",
}

# Map a few dataset keywords to categories (best effort).
_CATEGORY_HINTS = [
    ("earthquake", "hazards"), ("fire", "hazards"), ("flood", "hazards"),
    ("weather", "weather"), ("climate", "weather"), ("precip", "weather"),
    ("imagery", "imagery"), ("satellite", "imagery"), ("landsat", "imagery"),
    ("elevation", "elevation"), ("terrain", "elevation"),
    ("boundary", "boundaries"), ("census", "boundaries"), ("county", "boundaries"),
    ("water", "environment"), ("river", "environment"), ("forest", "environment"),
    ("road", "infrastructure"), ("transit", "infrastructure"),
    ("ocean", "oceans"), ("coast", "oceans"), ("marine", "oceans"),
]


def _guess_category(text: str) -> str:
    low = text.lower()
    for kw, cat in _CATEGORY_HINTS:
        if kw in low:
            return cat
    return "other"


def get_endpoints(portal: str = DEFAULT_PORTAL, rows: int = 200,
                  timeout: float = 25.0) -> List[Endpoint]:
    session = requests.Session()
    out: List[Endpoint] = []
    seen = set()
    api = portal.rstrip("/") + "/api/3/action/package_search"

    for fmt, etype in _FORMAT_MAP.items():
        params = {"q": "", "fq": f'res_format:"{fmt}"', "rows": rows, "start": 0}
        try:
            r = session.get(api, params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ckan query failed (format={fmt}): {exc}", flush=True)
            continue

        for pkg in payload.get("result", {}).get("results", []):
            category = _guess_category(
                f"{pkg.get('title', '')} {pkg.get('notes', '')}"
            )
            for res in pkg.get("resources", []):
                if (res.get("format") or "").strip().lower() != fmt:
                    continue
                url = (res.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append(Endpoint(
                    title=res.get("name") or pkg.get("title") or url,
                    type=etype,
                    url=url,
                    source="ckan",
                    category=category,
                    description=(pkg.get("notes") or "")[:400],
                    attribution=pkg.get("organization", {}).get("title", "")
                    if isinstance(pkg.get("organization"), dict) else "",
                    # WMS/WMTS resources are usually service roots needing a layer.
                    needs_expansion=(etype in ("WMS", "WMTS")),
                ))
    print(f"  ckan: {len(out)} candidate endpoints", flush=True)
    return out
