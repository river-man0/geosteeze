"""Parse OGC WMS / WMTS GetCapabilities documents into concrete layer endpoints.

A "service root" endpoint (a WMS/WMTS base URL with no specific layer) is not
directly usable by a map client - you need a layer name, and for WMTS also a
tile-matrix-set, format and style. This module fetches the capabilities
document and turns one root into many ready-to-render Endpoints.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Optional

import requests

from ..models import Endpoint

USER_AGENT = "geosteeze-scraper/0.1 (+https://github.com/river-man0/geosteeze)"


def _localname(tag: str) -> str:
    """Strip the XML namespace from a tag, e.g. '{...wms}Layer' -> 'Layer'."""
    return tag.rsplit("}", 1)[-1]


def _find(el: ET.Element, *names: str) -> Optional[ET.Element]:
    for child in el.iter():
        if _localname(child.tag) in names:
            return child
    return None


def _direct_children(el: ET.Element, name: str) -> List[ET.Element]:
    return [c for c in el if _localname(c.tag) == name]


def _text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _fetch_caps(url: str, service: str, timeout: float) -> ET.Element:
    sep = "&" if "?" in url else "?"
    caps_url = f"{url}{sep}service={service}&request=GetCapabilities"
    r = requests.get(caps_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return ET.fromstring(r.content)


# --------------------------------------------------------------------------- WMS


def _wms_layers(layer_el: ET.Element) -> List[ET.Element]:
    """Recursively collect named (renderable) WMS layers."""
    out: List[ET.Element] = []
    name = None
    for c in _direct_children(layer_el, "Name"):
        name = _text(c)
        break
    if name:
        out.append(layer_el)
    for sub in _direct_children(layer_el, "Layer"):
        out.extend(_wms_layers(sub))
    return out


def _wms_bbox(layer_el: ET.Element) -> Optional[List[float]]:
    # WMS 1.3.0
    geo = _find(layer_el, "EX_GeographicBoundingBox")
    if geo is not None:
        try:
            w = float(_text(_find(geo, "westBoundLongitude")))
            e = float(_text(_find(geo, "eastBoundLongitude")))
            s = float(_text(_find(geo, "southBoundLatitude")))
            n = float(_text(_find(geo, "northBoundLatitude")))
            return [w, s, e, n]
        except (TypeError, ValueError):
            pass
    # WMS 1.1.1
    ll = _find(layer_el, "LatLonBoundingBox")
    if ll is not None:
        try:
            return [
                float(ll.get("minx")), float(ll.get("miny")),
                float(ll.get("maxx")), float(ll.get("maxy")),
            ]
        except (TypeError, ValueError):
            pass
    return None


def expand_wms(root: Endpoint, timeout: float = 20.0, max_layers: int = 40) -> List[Endpoint]:
    tree = _fetch_caps(root.url, "WMS", timeout)
    cap = _find(tree, "Capability")
    if cap is None:
        return []
    top = _direct_children(cap, "Layer")
    candidates: List[ET.Element] = []
    for t in top:
        candidates.extend(_wms_layers(t))

    out: List[Endpoint] = []
    for layer_el in candidates[:max_layers]:
        name = _text(_find(layer_el, "Name"))
        if not name:
            continue
        title = _text(_find(layer_el, "Title")) or name
        out.append(Endpoint(
            title=title,
            type="WMS",
            url=root.url.split("?")[0],
            source=root.source,
            category=root.category,
            layer=name,
            description=_text(_find(layer_el, "Abstract"))[:400],
            attribution=root.attribution,
            bbox=_wms_bbox(layer_el),
        ))
    return out


# -------------------------------------------------------------------------- WMTS


def expand_wmts(root: Endpoint, timeout: float = 20.0, max_layers: int = 40) -> List[Endpoint]:
    tree = _fetch_caps(root.url, "WMTS", timeout)
    contents = _find(tree, "Contents")
    if contents is None:
        return []

    out: List[Endpoint] = []
    for layer_el in _direct_children(contents, "Layer")[:max_layers]:
        ident = _text(_find(layer_el, "Identifier"))
        if not ident:
            continue
        fmt = ""
        for f in _direct_children(layer_el, "Format"):
            fmt = _text(f)
            break
        style = "default"
        for st in _direct_children(layer_el, "Style"):
            sid = _find(st, "Identifier")
            if sid is not None:
                style = _text(sid) or "default"
            break
        tms = ""
        link = _find(layer_el, "TileMatrixSetLink")
        if link is not None:
            tms = _text(_find(link, "TileMatrixSet"))
        # WGS84 bounding box
        bbox = None
        bb = _find(layer_el, "WGS84BoundingBox")
        if bb is not None:
            lc = _text(_find(bb, "LowerCorner")).split()
            uc = _text(_find(bb, "UpperCorner")).split()
            try:
                bbox = [float(lc[0]), float(lc[1]), float(uc[0]), float(uc[1])]
            except (IndexError, ValueError):
                bbox = None
        has_time = any(_localname(d.tag) == "Dimension" for d in layer_el)

        scheme = "geographic" if "4326" in tms or "epsg4326" in root.url.lower() else "web-mercator"
        out.append(Endpoint(
            title=_text(_find(layer_el, "Title")) or ident,
            type="WMTS",
            url=root.url.split("?")[0],
            source=root.source,
            category=root.category,
            layer=ident,
            attribution=root.attribution,
            bbox=bbox,
            tile_matrix_set=tms,
            tile_format=fmt or "image/png",
            style=style,
            tiling_scheme=scheme,
            time_dimension=has_time,
        ))
    return out


def expand(root: Endpoint, timeout: float = 20.0, max_layers: int = 40) -> List[Endpoint]:
    """Expand a WMS/WMTS service root into per-layer endpoints (best effort)."""
    try:
        if root.type == "WMS":
            return expand_wms(root, timeout, max_layers)
        if root.type == "WMTS":
            return expand_wmts(root, timeout, max_layers)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! capabilities expansion failed for {root.url}: {exc}", flush=True)
    return []
