"""Source adapters that yield candidate live geographic endpoints."""

from __future__ import annotations

from typing import Callable, Dict, List

from ..models import Endpoint
from . import arcgis_online, ckan, seeds

# Registry of discovery sources. Each callable returns a list of candidate
# Endpoints (some may be service roots flagged for capabilities expansion).
SOURCES: Dict[str, Callable[..., List[Endpoint]]] = {
    "seed": seeds.get_seed_endpoints,
    "arcgis_online": arcgis_online.get_endpoints,
    "ckan": ckan.get_endpoints,
}

__all__ = ["SOURCES", "seeds", "arcgis_online", "ckan"]
