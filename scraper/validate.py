"""Liveness checks for candidate endpoints.

Each check is intentionally cheap: we want to know "is this thing answering and
does it look like the service it claims to be" without downloading real data.
Results (live / latency / CORS) are written back onto the Endpoint in place.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterable, List

import requests

from .models import Endpoint

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
    "WMS": _check_ogc,
    "WMTS": _check_ogc,
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
