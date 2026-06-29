"""Normalized data model for a live geographic endpoint."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import List, Optional

# Endpoint "type" controls which Cesium provider the front-end uses.
ENDPOINT_TYPES = {
    "WMS",                  # OGC Web Map Service          -> WebMapServiceImageryProvider
    "WMTS",                 # OGC Web Map Tile Service      -> WebMapTileServiceImageryProvider
    "XYZ",                  # {z}/{x}/{y} tile template     -> UrlTemplateImageryProvider
    "ArcGISMapServer",      # Esri tiled/dynamic map service-> ArcGisMapServerImageryProvider
    "ArcGISImageServer",    # Esri image service            -> ArcGisMapServerImageryProvider (export)
    "ArcGISFeatureServer",  # Esri feature service          -> queried as GeoJSON
    "GeoJSON",              # GeoJSON / live feed           -> GeoJsonDataSource
}

# Coarse categories used for filtering / colouring in the UI.
CATEGORIES = {
    "basemap",
    "imagery",
    "elevation",
    "weather",
    "hazards",
    "environment",
    "boundaries",
    "infrastructure",
    "oceans",
    "live-events",
    "other",
}


@dataclass
class Endpoint:
    """A single live, map-ready geographic data endpoint."""

    title: str
    type: str
    url: str
    source: str                     # which adapter produced it (seed/arcgis_online/ckan/ogc)
    category: str = "other"
    layer: Optional[str] = None     # WMS/WMTS layer identifier
    description: str = ""
    attribution: str = ""
    bbox: Optional[List[float]] = None  # [west, south, east, north] in degrees

    # WMTS / tile specifics (needed to construct the provider client-side)
    tile_matrix_set: Optional[str] = None
    tile_format: Optional[str] = None
    style: Optional[str] = None
    tiling_scheme: Optional[str] = None  # "geographic" | "web-mercator"
    time_dimension: bool = False         # endpoint expects a TIME parameter

    # Native/source coordinate reference system, e.g. "EPSG:3857". Used both to
    # tell the viewer whether a layer can be drawn on its Web-Mercator map and
    # to surface the projection in the UI. None = unknown / not applicable.
    crs: Optional[str] = None

    # Validation results (filled in by validate.py)
    live: bool = False
    cors: Optional[bool] = None
    latency_ms: Optional[int] = None
    checked_at: Optional[str] = None
    error: Optional[str] = None

    # Free-form expansion hint: WMS/WMTS "service roots" with no layer get
    # expanded into concrete per-layer endpoints by the OGC parser.
    needs_expansion: bool = False

    def __post_init__(self) -> None:
        if self.type not in ENDPOINT_TYPES:
            raise ValueError(f"unknown endpoint type: {self.type!r}")
        if self.category not in CATEGORIES:
            self.category = "other"
        self.url = self.url.strip()

    @property
    def id(self) -> str:
        key = f"{self.type}|{self.url}|{self.layer or ''}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("needs_expansion", None)  # internal flag, not part of the catalog
        d["id"] = self.id
        return d
