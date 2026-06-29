"""Liveness checks for candidate endpoints.

Each check is intentionally cheap: we want to know "is this thing answering and
does it look like the service it claims to be" without downloading real data.
Results (live / latency / CORS) are written back onto the Endpoint in place.
"""

from __future__ import annotations

import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import requests

from .models import Endpoint

# Web-Mercator world extent in metres, for GetMap render checks.
_MERC_R = 20037508.342789244

USER_AGENT = "geosteeze-scraper/0.1 (+https://github.com/river-man0/geosteeze)"

# Capabilities documents are shared across many layers from the same service,
# so cache the liveness verdict per (type, base-url) within a single run.
_caps_cache: dict = {}


def _headers() -> dict:
    # Send an Origin so servers reveal their CORS policy in the response.
    return {"User-Agent": USER_AGENT, "Origin": "https://example.com"}


def _has_cors(resp: requests.Response) -> bool:
    acao = resp.headers.get("Access-Control-Allow-Origin", "")
    return acao == "*" or acao == "https://example.com"


def _check_arcgis(ep: Endpoint, session: requests.Session, timeout: float) -> None:
    sep = "&" if "?" in ep.url else "?"
    r = session.get(ep.url + sep + "f=json", headers=_headers(), timeout=timeout)
    ep.cors = _has_cors(r)
    data = r.json()
    if "error" in data:
        err = data["error"]
        msg = err.get("message", "arcgis error") if isinstance(err, dict) else "arcgis error"
        raise RuntimeError(msg)
    # A valid service exposes currentVersion and/or layers/fields.
    if not any(k in data for k in ("currentVersion", "layers", "fields", "tileInfo", "name")):
        raise RuntimeError("response is not an ArcGIS service descriptor")
    # Record the service's native CRS. The viewer reprojects ArcGIS layers
    # server-side (export) or, for tile caches, requires Web Mercator — either
    # way the projection is surfaced in the catalog. The spatial reference can
    # live in a few places depending on the service kind.
    sr = {}
    for holder in (data.get("tileInfo"), data, data.get("fullExtent"),
                   data.get("initialExtent"), data.get("extent")):
        if isinstance(holder, dict) and isinstance(holder.get("spatialReference"), dict):
            sr = holder["spatialReference"]
            break
    wkid = sr.get("latestWkid") or sr.get("wkid")
    if wkid:
        ep.crs = f"EPSG:{wkid}"


def _check_geojson(ep: Endpoint, session: requests.Session, timeout: float) -> None:
    sep = "&" if "?" in ep.url else "?"
    url = ep.url
    if ep.type == "ArcGISFeatureServer":
        url = ep.url.rstrip("/") + "/query?where=1%3D1&outFields=*&f=geojson&resultRecordCount=1&outSR=4326"
    with session.get(url, headers=_headers(), timeout=timeout, stream=True) as r:
        ep.cors = _has_cors(r)
        r.raise_for_status()
        head = next(r.iter_content(4096), b"") or b""
    text = head.decode("utf-8", "ignore")
    if "FeatureCollection" not in text and '"Feature"' not in text and '"type"' not in text:
        raise RuntimeError("response does not look like GeoJSON")
    # GeoJSON is WGS84 by spec; esri-leaflet queries features as 4326 too.
    ep.crs = "EPSG:4326"


def _check_xyz(ep: Endpoint, session: requests.Session, timeout: float) -> None:
    sample = (
        ep.url.replace("{z}", "1").replace("{x}", "1").replace("{y}", "1")
        .replace("{s}", "a").replace("{TileMatrix}", "1").replace("{TileRow}", "1")
        .replace("{TileCol}", "1")
    )
    r = session.get(sample, headers=_headers(), timeout=timeout, stream=True)
    ep.cors = _has_cors(r)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    if not ctype.startswith("image/"):
        raise RuntimeError(f"tile response is not an image ({ctype})")


def _mercator_bbox(bbox) -> str:
    """A degrees bbox -> an EPSG:3857 'minx,miny,maxx,maxy' string (clamped)."""
    if not bbox or len(bbox) != 4:
        return f"{-_MERC_R},{-_MERC_R},{_MERC_R},{_MERC_R}"
    w, s, e, n = bbox
    w = max(-179.9, min(179.9, w)); e = max(-179.9, min(179.9, e))
    s = max(-85.0, min(85.0, s)); n = max(-85.0, min(85.0, n))
    if e <= w or n <= s:
        return f"{-_MERC_R},{-_MERC_R},{_MERC_R},{_MERC_R}"
    x = lambda lon: _MERC_R * lon / 180.0
    y = lambda lat: _MERC_R * math.log(math.tan((90 + lat) * math.pi / 360.0)) / math.pi
    return f"{x(w)},{y(s)},{x(e)},{y(n)}"


def _service_exception(text: str) -> Optional[str]:
    m = re.search(r"<(?:\w+:)?ServiceException[^>]*>(.*?)</", text, re.S)
    return m.group(1).strip()[:160] if m else None


def _check_wms(ep: Endpoint, session: requests.Session, timeout: float) -> None:
    """Render-check a WMS layer the way the viewer does: a GetMap in EPSG:3857.

    The viewer draws WMS layers on a Web-Mercator map, so the real question is
    "does this layer return an image when asked for EPSG:3857?". A definitive
    ServiceException means it won't (drop it). Network hiccups or odd non-image
    responses (e.g. proxy artefacts) are inconclusive, so we fall back to a
    GetCapabilities liveness check rather than dropping a layer that may work.
    """
    fmt = ep.tile_format or "image/png"
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetMap",
        "layers": ep.layer or "", "styles": "", "srs": "EPSG:3857",
        "bbox": _mercator_bbox(ep.bbox), "width": "256", "height": "256",
        "format": fmt, "transparent": "false" if "jpeg" in fmt or "jpg" in fmt else "true",
    }
    try:
        with session.get(ep.url, params=params, headers=_headers(),
                         timeout=timeout, stream=True) as r:
            ep.cors = _has_cors(r)
            ctype = r.headers.get("Content-Type", "").lower()
            if ctype.startswith("image/"):
                ep.crs = "EPSG:3857"
                return
            head = (next(r.iter_content(2048), b"") or b"").decode("utf-8", "ignore")
        is_error_doc = (
            "ServiceException" in head or "ows:Exception" in head
            or ctype.startswith(("text/xml", "application/xml", "application/vnd.ogc"))
        )
        if is_error_doc:
            raise RuntimeError(
                "GetMap rejected EPSG:3857: " + (_service_exception(head) or "service exception")
            )
        # Inconclusive response -> fall through to the capabilities check.
    except requests.RequestException:
        pass  # transient network issue -> fall back rather than drop
    _check_ogc(ep, session, timeout)
    if not ep.crs:
        ep.crs = "EPSG:3857"


def _deg2tile(lon: float, lat: float, z: int):
    n = 2 ** z
    lat = max(-85.05, min(85.05, lat))
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _check_wmts(ep: Endpoint, session: requests.Session, timeout: float) -> None:
    """Validate WMTS the way the viewer consumes it.

    NASA GIBS is fetched through its dedicated EPSG:3857 REST endpoint, so a
    capabilities check is enough (and avoids GIBS' multi-megabyte tile-by-tile
    flakiness). Every other WMTS is drawn as plain Web-Mercator {z}/{x}/{y}
    tiles, so we fetch one real GetTile: an image means it aligns, a tile
    exception means the cache can't serve our grid (drop it), and anything
    inconclusive falls back to the capabilities liveness check.
    """
    host = ep.url.split("/")[2] if "://" in ep.url else ""
    if host.endswith("gibs.earthdata.nasa.gov") and ep.tiling_scheme == "geographic":
        _check_ogc(ep, session, timeout)
        return

    bbox = ep.bbox or [-180.0, -85.0, 180.0, 85.0]
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    z = 5
    x, y = _deg2tile(cx, cy, z)
    sep = "&" if "?" in ep.url else "?"
    params = [
        "SERVICE=WMTS", "REQUEST=GetTile", "VERSION=1.0.0",
        "LAYER=" + (ep.layer or ""), "STYLE=" + (ep.style or "default"),
        "TILEMATRIXSET=" + (ep.tile_matrix_set or ""),
        "FORMAT=" + (ep.tile_format or "image/png"),
        f"TILEMATRIX={z}", f"TILEROW={y}", f"TILECOL={x}",
    ]
    try:
        with session.get(ep.url + sep + "&".join(params), headers=_headers(),
                         timeout=timeout, stream=True) as r:
            ep.cors = _has_cors(r)
            ctype = r.headers.get("Content-Type", "").lower()
            if ctype.startswith("image/"):
                ep.crs = "EPSG:3857"
                return
            head = (next(r.iter_content(2048), b"") or b"").decode("utf-8", "ignore")
        if ("Exception" in head or ctype.startswith(
                ("text/xml", "application/xml", "application/vnd.ogc"))):
            raise RuntimeError(
                "GetTile failed: " + (_service_exception(head) or "tile exception")
            )
    except requests.RequestException:
        pass
    _check_ogc(ep, session, timeout)
    if not ep.crs:
        ep.crs = "EPSG:3857"


def _check_ogc(ep: Endpoint, session: requests.Session, timeout: float) -> None:
    cache_key = (ep.type, ep.url.split("?")[0])
    if cache_key in _caps_cache:
        ok, err = _caps_cache[cache_key]
        if not ok:
            raise RuntimeError(err)
        return
    service = "WMTS" if ep.type == "WMTS" else "WMS"
    sep = "&" if "?" in ep.url else "?"
    caps_url = f"{ep.url}{sep}service={service}&request=GetCapabilities"
    try:
        r = session.get(caps_url, headers=_headers(), timeout=timeout)
        ep.cors = _has_cors(r)
        r.raise_for_status()
        body = r.text[:4000]
        if "Capabilities" not in body and "<WMT_MS_Capabilities" not in body:
            raise RuntimeError("no capabilities document returned")
        _caps_cache[cache_key] = (True, "")
    except Exception as exc:  # noqa: BLE001 - cache the failure too
        _caps_cache[cache_key] = (False, str(exc))
        raise


_CHECKERS = {
    "ArcGISMapServer": _check_arcgis,
    "ArcGISImageServer": _check_arcgis,
    "ArcGISFeatureServer": _check_geojson,
    "GeoJSON": _check_geojson,
    "XYZ": _check_xyz,
    "WMS": _check_wms,
    "WMTS": _check_wmts,
}


def validate_one(ep: Endpoint, timeout: float = 12.0) -> Endpoint:
    """Run the appropriate liveness check for a single endpoint."""
    session = requests.Session()
    started = time.perf_counter()
    try:
        checker = _CHECKERS.get(ep.type)
        if checker is None:
            raise RuntimeError(f"no validator for type {ep.type}")
        checker(ep, session, timeout)
        ep.live = True
        ep.error = None
    except Exception as exc:  # noqa: BLE001 - record, never crash the run
        ep.live = False
        ep.error = f"{type(exc).__name__}: {exc}"[:240]
    finally:
        ep.latency_ms = int((time.perf_counter() - started) * 1000)
        ep.checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        session.close()
    return ep


def validate_all(
    endpoints: Iterable[Endpoint],
    workers: int = 16,
    timeout: float = 12.0,
    progress: bool = True,
) -> List[Endpoint]:
    """Validate endpoints concurrently. Returns the same Endpoint objects."""
    eps = list(endpoints)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(validate_one, ep, timeout): ep for ep in eps}
        for fut in as_completed(futures):
            fut.result()
            done += 1
            if progress and (done % 10 == 0 or done == len(eps)):
                live = sum(1 for e in eps if e.checked_at and e.live)
                print(f"  validated {done}/{len(eps)} ({live} live)", flush=True)
    return eps
