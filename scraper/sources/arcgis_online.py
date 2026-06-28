"""Discover live endpoints from the ArcGIS Online content catalog.

ArcGIS Online exposes a public search API that returns items pointing at live
REST service endpoints (Map / Feature / Image services and registered WMS).
We translate matching items into normalized Endpoints. No API key required for
public content.
"""

from __future__ import annotations

from typing import List

import requests

from ..models import Endpoint

SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
USER_AGENT = "geosteeze-scraper/0.1 (+https://github.com/river-man0/geosteeze)"

# ArcGIS item "type" -> our normalized endpoint type.
_TYPE_MAP = {
    "Map Service": "ArcGISMapServer",
    "Feature Service": "ArcGISFeatureServer",
    "Image Service": "ArcGISImageServer",
    "WMS": "WMS",
}

# Topic queries -> category. Tuned for the catalog's focus: global imagery,
# Arctic / sea-ice / cryosphere, and Canadian data. The API ranks by relevance.
_TOPICS = {
    "sea ice OR sea-ice OR ice concentration OR ice extent": "oceans",
    "arctic OR polar OR antarctic": "oceans",
    "glacier OR permafrost OR snow OR cryosphere": "environment",
    "satellite OR imagery OR sentinel OR landsat OR mosaic": "imagery",
    "Canada OR Canadian": "boundaries",
    "ocean OR bathymetry OR sea surface temperature": "oceans",
    "climate OR temperature anomaly OR precipitation": "weather",
    "wildfire OR flood OR earthquake OR hazard": "hazards",
    "elevation OR terrain OR digital elevation": "elevation",
    "global OR world OR worldwide": "imagery",
}


def _extent_to_bbox(extent) -> List[float] | None:
    # ArcGIS item extent: [[xmin, ymin], [xmax, ymax]] in WGS84.
    try:
        (xmin, ymin), (xmax, ymax) = extent
        return [float(xmin), float(ymin), float(xmax), float(ymax)]
    except Exception:  # noqa: BLE001
        return None


def _search(session: requests.Session, query: str, per_topic: int, timeout: float) -> list:
    items, start, page = [], 1, 100
    while len(items) < per_topic and start > 0:
        params = {
            "q": query,
            "f": "json",
            "num": min(page, per_topic - len(items)),
            "start": start,
            "sortField": "numviews",
            "sortOrder": "desc",
        }
        r = session.get(SEARCH_URL, params=params,
                        headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("results", []))
        start = data.get("nextStart", -1)
    return items[:per_topic]


def get_endpoints(per_topic: int = 30, timeout: float = 25.0) -> List[Endpoint]:
    session = requests.Session()
    out: List[Endpoint] = []
    seen = set()
    for query, category in _TOPICS.items():
        type_filter = " OR ".join(f'type:"{t}"' for t in _TYPE_MAP)
        full_q = f"({query}) AND ({type_filter}) AND access:public"
        try:
            results = _search(session, full_q, per_topic, timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! arcgis_online query failed ({category}): {exc}", flush=True)
            continue
        for item in results:
            url = (item.get("url") or "").strip()
            etype = _TYPE_MAP.get(item.get("type", ""))
            if not url or not etype or url in seen:
                continue
            seen.add(url)
            ep = Endpoint(
                title=item.get("title") or url,
                type=etype,
                url=url,
                source="arcgis_online",
                category=category,
                description=(item.get("snippet") or "")[:400],
                attribution=item.get("accessInformation") or "ArcGIS Online",
                bbox=_extent_to_bbox(item.get("extent")),
                # A WMS item points at a service root; let the OGC parser pick layers.
                needs_expansion=(etype == "WMS"),
            )
            # Feature/Map services from the item URL may be a folder; the
            # validator will tell us if it answers as a real service.
            out.append(ep)
    print(f"  arcgis_online: {len(out)} candidate endpoints", flush=True)
    return out
