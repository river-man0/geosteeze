"""geosteeze scraper CLI.

Discover live geographic endpoints from one or more sources, expand OGC service
roots into per-layer endpoints, validate that everything is actually live, and
write a normalized ``catalog.json`` for the Cesium front-end.

Examples
--------
  # Seed-only catalog, no network validation (instant, offline):
  python -m scraper.scrape --sources seed --no-validate

  # Full crawl of all sources, validated, dropping dead endpoints:
  python -m scraper.scrape --sources seed arcgis_online ckan --drop-dead

  # Just refresh/validate the seeds:
  python -m scraper.scrape --sources seed
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .models import Endpoint
from .sources import SOURCES
from .sources import ogc
from .validate import validate_all

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "docs" / "catalog.json"


def collect(source_names: List[str], per_topic: int, ckan_rows: int) -> List[Endpoint]:
    candidates: List[Endpoint] = []
    for name in source_names:
        fn = SOURCES.get(name)
        if fn is None:
            print(f"! unknown source: {name} (have: {', '.join(SOURCES)})", file=sys.stderr)
            continue
        print(f"[collect] {name} ...", flush=True)
        if name == "arcgis_online":
            candidates.extend(fn(per_topic=per_topic))
        elif name == "ckan":
            candidates.extend(fn(rows=ckan_rows))
        else:
            candidates.extend(fn())
    return candidates


def expand_roots(candidates: List[Endpoint], max_layers: int) -> List[Endpoint]:
    """Replace WMS/WMTS service roots with their concrete per-layer endpoints."""
    expanded: List[Endpoint] = []
    roots = [c for c in candidates if c.needs_expansion and c.type in ("WMS", "WMTS")]
    if roots:
        print(f"[expand] parsing capabilities for {len(roots)} service root(s) ...", flush=True)
    for c in candidates:
        if c.needs_expansion and c.type in ("WMS", "WMTS"):
            layers = ogc.expand(c, max_layers=max_layers)
            if layers:
                expanded.extend(layers)
            # If expansion fails, keep the root only if it already names a layer.
            elif c.layer:
                c.needs_expansion = False
                expanded.append(c)
        else:
            expanded.append(c)
    return expanded


def dedupe(endpoints: List[Endpoint]) -> List[Endpoint]:
    by_id = {}
    for ep in endpoints:
        by_id.setdefault(ep.id, ep)
    return list(by_id.values())


def write_catalog(endpoints: List[Endpoint], out: Path, sources: List[str]) -> dict:
    records = [ep.to_dict() for ep in endpoints]
    records.sort(key=lambda r: (r["category"], r["title"].lower()))
    live = sum(1 for r in records if r["live"])
    by_type: dict = {}
    by_category: dict = {}
    for r in records:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1
    catalog = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
        "stats": {
            "total": len(records),
            "live": live,
            "by_type": by_type,
            "by_category": by_category,
        },
        "endpoints": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compile live geographic data endpoints.")
    p.add_argument("--sources", nargs="+", default=["seed"],
                   choices=list(SOURCES), help="discovery sources to run")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output catalog.json path")
    p.add_argument("--no-validate", action="store_true",
                   help="skip liveness checks (offline; everything marked unverified)")
    p.add_argument("--drop-dead", action="store_true",
                   help="exclude endpoints that fail validation")
    p.add_argument("--per-topic", type=int, default=30,
                   help="max ArcGIS Online results per topic query")
    p.add_argument("--ckan-rows", type=int, default=200,
                   help="max CKAN datasets fetched per resource format")
    p.add_argument("--max-layers", type=int, default=40,
                   help="max layers to extract per WMS/WMTS service root")
    p.add_argument("--workers", type=int, default=16, help="validation concurrency")
    p.add_argument("--timeout", type=float, default=12.0, help="per-request timeout (s)")
    args = p.parse_args(argv)

    candidates = collect(args.sources, args.per_topic, args.ckan_rows)
    print(f"[collect] {len(candidates)} raw candidate(s)", flush=True)

    candidates = expand_roots(candidates, args.max_layers)
    candidates = dedupe(candidates)
    print(f"[dedupe] {len(candidates)} unique endpoint(s)", flush=True)

    if args.no_validate:
        print("[validate] skipped (--no-validate)", flush=True)
    else:
        print(f"[validate] checking {len(candidates)} endpoint(s) ...", flush=True)
        validate_all(candidates, workers=args.workers, timeout=args.timeout)
        if args.drop_dead:
            before = len(candidates)
            candidates = [c for c in candidates if c.live]
            print(f"[validate] dropped {before - len(candidates)} dead endpoint(s)", flush=True)

    catalog = write_catalog(candidates, args.out, args.sources)
    s = catalog["stats"]
    print(f"\n[done] wrote {args.out}")
    print(f"       {s['total']} endpoints ({s['live']} live)")
    print(f"       by type:     {s['by_type']}")
    print(f"       by category: {s['by_category']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
