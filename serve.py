#!/usr/bin/env python3
"""Static file server for the geosteeze front-end, with an optional CORS proxy.

Why a proxy? Imagery (tiles, WMS GetMap) loads as <img> elements and is not
subject to CORS, but GeoJSON and ArcGIS feature queries are fetched with
JavaScript and *are*. Many public feeds are CORS-enabled, but some are not.
Routing those fetches through ``/proxy?url=...`` lets you stream them straight
into the map locally without a download step.

Usage:
    python serve.py            # http://localhost:8000
    python serve.py --port 9000 --no-proxy

This is a development convenience server, not a production gateway. The proxy
refuses non-HTTP(S) URLs and blocks private/loopback hosts to limit SSRF.
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import urllib.parse
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"
USER_AGENT = "geosteeze-proxy/0.1"
MAX_BYTES = 64 * 1024 * 1024  # 64 MiB safety cap


def _is_blocked_host(host: str) -> bool:
    """Block loopback / private / link-local / reserved targets (basic SSRF guard)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    return False


class Handler(SimpleHTTPRequestHandler):
    proxy_enabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    # Silence the default noisy logging; keep one concise line.
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} - {fmt % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/runtime-config.js":
            return self._serve_runtime_config()
        if parsed.path == "/proxy":
            return self._serve_proxy(parsed)
        return super().do_GET()

    # ----------------------------------------------------------- runtime config
    def _serve_runtime_config(self):
        proxy_line = (
            'window.GEOSTEEZE.proxyUrl = "/proxy?url=";\n'
            if self.proxy_enabled else
            "/* CORS proxy disabled (--no-proxy) */\n"
        )
        body = ("// Injected by serve.py at request time.\n" + proxy_line).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -------------------------------------------------------------------- proxy
    def _serve_proxy(self, parsed):
        if not self.proxy_enabled:
            return self.send_error(403, "proxy disabled")
        qs = urllib.parse.parse_qs(parsed.query)
        target = (qs.get("url") or [""])[0]
        if not target:
            return self.send_error(400, "missing url parameter")
        tp = urllib.parse.urlparse(target)
        if tp.scheme not in ("http", "https") or not tp.hostname:
            return self.send_error(400, "only http(s) URLs are allowed")
        if _is_blocked_host(tp.hostname):
            return self.send_error(403, "target host is not allowed")

        req = urllib.request.Request(target, headers={"User-Agent": USER_AGENT,
                                                      "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=30) as upstream:
                data = upstream.read(MAX_BYTES + 1)
                ctype = upstream.headers.get("Content-Type", "application/octet-stream")
        except Exception as exc:  # noqa: BLE001
            return self.send_error(502, f"upstream fetch failed: {exc}")
        if len(data) > MAX_BYTES:
            return self.send_error(502, "upstream response too large")

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the geosteeze front-end.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-proxy", action="store_true", help="disable the CORS proxy")
    args = ap.parse_args()

    if not (WEB_DIR / "index.html").exists():
        print(f"! {WEB_DIR}/index.html not found", flush=True)
        return 1

    Handler.proxy_enabled = not args.no_proxy
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    proxy_state = "off" if args.no_proxy else "on (/proxy?url=)"
    print(f"geosteeze serving {WEB_DIR}")
    print(f"  → http://{args.host}:{args.port}/   (CORS proxy: {proxy_state})")
    print("  Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
