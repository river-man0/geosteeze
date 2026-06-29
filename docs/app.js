/* geosteeze — explore live geographic data endpoints on a Leaflet web map. */
(function () {
  "use strict";

  const CFG = window.GEOSTEEZE;
  const MOBILE = "(max-width: 760px)";
  const DEFAULT_OPACITY = 0.92;
  const CATEGORY_COLORS = {
    basemap: "#9aa7b4", imagery: "#5dade2", elevation: "#a47b5a",
    weather: "#48c9b0", hazards: "#e74c3c", environment: "#58d68d",
    boundaries: "#bb8fce", infrastructure: "#f5b041", oceans: "#5499c7",
    "live-events": "#ec7063", other: "#7f8c8d",
  };

  // active layer id -> { record, kind: "tile"|"vector", layer, opacity }
  const active = new Map();
  const arcgisMeta = new Map(); // url -> { exportable, cached, mercator, wkid }
  let catalog = null;
  let map = null;

  // ----------------------------------------------------------------- helpers
  const $ = (sel) => document.querySelector(sel);
  const isMobile = () => window.matchMedia(MOBILE).matches;

  function proxied(url) {
    return CFG.proxyUrl ? CFG.proxyUrl + encodeURIComponent(url) : url;
  }
  function colorFor(rec) {
    return CATEGORY_COLORS[rec.category] || CATEGORY_COLORS.other;
  }
  // Compact "host + path" form of an endpoint URL for display in a row.
  function shortUrl(url) {
    try {
      const u = new URL(url);
      let path = decodeURIComponent(u.pathname).replace(/\/$/, "");
      if (path.length > 38) path = path.slice(0, 18) + "…" + path.slice(-18);
      return u.host + path;
    } catch (_) {
      return url.length > 56 ? url.slice(0, 55) + "…" : url;
    }
  }
  function isMercator(wkid) {
    return [3857, 102100, 102113, 900913].includes(Number(wkid));
  }

  function toast(msg, isError) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    el.classList.toggle("error", !!isError);
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), isError ? 6000 : 3500);
  }

  function flyToBbox(bbox) {
    if (!bbox || bbox.length !== 4) return;
    let [w, s, e, n] = bbox;
    w = Math.max(-180, w); e = Math.min(180, e);
    s = Math.max(-85, s); n = Math.min(85, n);
    if (e <= w || n <= s) return;
    map.flyToBounds([[s, w], [n, e]], { maxZoom: 9, duration: 1.0, padding: [24, 24] });
  }

  // ------------------------------------------------------------- map set-up
  function initMap() {
    map = L.map("map", {
      center: [20, 0],
      zoom: 2,
      minZoom: 2,
      worldCopyJump: true,
      zoomControl: false,
      attributionControl: true,
    });
    L.control.zoom({ position: "topright" }).addTo(map);
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(map);

    L.tileLayer(CFG.basemapUrl, {
      subdomains: CFG.basemapSubdomains || "abc",
      attribution: CFG.basemapAttribution || "",
      maxZoom: 20,
    }).addTo(map);

    window.addEventListener("resize", () => map.invalidateSize());
  }

  // --------------------------------------------------- raster layer builders
  // XYZ / WMS / WMTS only. ArcGIS services are handled by addArcGisLayer,
  // which inspects service metadata to pick the right reprojection strategy.
  function buildTileLayer(rec, opacity) {
    switch (rec.type) {
      case "XYZ":
        return L.tileLayer(rec.url, {
          opacity, maxZoom: 22, maxNativeZoom: 19,
          attribution: rec.attribution || "", crossOrigin: true,
        });
      case "WMS":
        return L.tileLayer.wms(rec.url, {
          layers: rec.layer || "",
          format: rec.tile_format || "image/png",
          transparent: true,
          opacity,
          attribution: rec.attribution || "",
          crossOrigin: true,
        });
      case "WMTS":
        return buildWmtsLayer(rec, opacity);
    }
    return null;
  }

  // WMTS in a web-mercator map. NASA GIBS publishes a mercator REST endpoint
  // that aligns with Leaflet; everything else falls back to a KVP GetTile URL.
  function buildWmtsLayer(rec, opacity) {
    let host = "";
    try { host = new URL(rec.url).host; } catch (_) { /* relative */ }
    const ext = /jpe?g/i.test(rec.tile_format || "") ? "jpg" : "png";

    if (host.endsWith("gibs.earthdata.nasa.gov") && rec.tiling_scheme === "geographic") {
      const levels = {
        "15.625m": 13, "31.25m": 12, "62.5m": 11, "125m": 10,
        "250m": 9, "500m": 8, "1km": 7, "2km": 6,
      };
      const level = levels[rec.tile_matrix_set] || 8;
      const tms = "GoogleMapsCompatible_Level" + level;
      const time = rec.time_dimension ? "/" + (CFG.defaultDate || "default") : "";
      const url =
        `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${rec.layer}` +
        `/default${time}/${tms}/{z}/{y}/{x}.${ext}`;
      return L.tileLayer(url, {
        opacity, maxNativeZoom: level, maxZoom: 22,
        attribution: rec.attribution || "NASA GIBS", crossOrigin: true,
      });
    }

    // The generic path draws tiles directly onto the Web-Mercator map, so a
    // non-3857 matrix set (geographic or a regional projection) would misalign.
    if (rec.tiling_scheme && rec.tiling_scheme !== "web-mercator") {
      throw new Error(
        `WMTS cache is ${rec.crs || rec.tiling_scheme}; can't reproject on a 2D web map`
      );
    }

    const sep = rec.url.includes("?") ? "&" : "?";
    const params = [
      "SERVICE=WMTS", "REQUEST=GetTile", "VERSION=1.0.0",
      "LAYER=" + encodeURIComponent(rec.layer || ""),
      "STYLE=" + encodeURIComponent(rec.style || "default"),
      "TILEMATRIXSET=" + encodeURIComponent(rec.tile_matrix_set || ""),
      "FORMAT=" + encodeURIComponent(rec.tile_format || "image/png"),
      "TILEMATRIX={z}", "TILEROW={y}", "TILECOL={x}",
    ];
    if (rec.time_dimension && CFG.defaultDate) {
      params.push("TIME=" + encodeURIComponent(CFG.defaultDate));
    }
    return L.tileLayer(rec.url + sep + params.join("&"), {
      opacity, maxZoom: 22, attribution: rec.attribution || "", crossOrigin: true,
    });
  }

  // ---------------------------------------------------- ArcGIS reprojection
  // A Leaflet map is single-CRS (EPSG:3857). ArcGIS can reproject server-side
  // via the export endpoint, but cache-only ("TilesOnly") services cannot —
  // those only align if their cache is already Web Mercator.
  async function fetchArcGisMeta(url) {
    if (arcgisMeta.has(url)) return arcgisMeta.get(url);
    const sep = url.includes("?") ? "&" : "?";
    const res = await fetch(proxied(url + sep + "f=json"), { cache: "force-cache" });
    if (!res.ok) throw new Error(`service metadata HTTP ${res.status}`);
    const d = await res.json();
    const cap = d.capabilities || "";
    const tileInfo = d.tileInfo;
    const sr = (tileInfo && tileInfo.spatialReference) || d.spatialReference || {};
    const wkid = sr.latestWkid || sr.wkid || null;
    const tilesOnly = /TilesOnly/i.test(cap);
    const meta = {
      cached: !!d.singleFusedMapCache || !!tileInfo,
      exportable: !tilesOnly && /(^|,)\s*(Map|Image)\s*(,|$)/i.test(cap),
      mercator: isMercator(wkid),
      wkid,
    };
    arcgisMeta.set(url, meta);
    return meta;
  }

  async function addArcGisLayer(rec) {
    const opacity = DEFAULT_OPACITY;
    const attribution = rec.attribution || "";
    const isImage = rec.type === "ArcGISImageServer";
    const meta = await fetchArcGisMeta(rec.url);

    let layer;
    if (meta.exportable) {
      // Server reprojects the export image into the map's CRS — works for any
      // source projection.
      layer = isImage
        ? L.esri.imageMapLayer({ url: rec.url, opacity, attribution })
        : L.esri.dynamicMapLayer({ url: rec.url, opacity, attribution });
    } else if (meta.cached && meta.mercator) {
      // Pre-rendered Web Mercator tiles align directly.
      layer = L.esri.tiledMapLayer({ url: rec.url, opacity, attribution });
    } else {
      throw new Error(
        `tile-only cache in EPSG:${meta.wkid || "?"} can't be reprojected on a 2D map`
      );
    }
    layer.addTo(map);
    active.set(rec.id, { record: rec, kind: "tile", layer, opacity });
    if (rec.bbox) flyToBbox(rec.bbox);
  }

  // ----------------------------------------------------- vector layer helpers
  function pointStyle(color) {
    return {
      radius: 6, color: "#ffffff", weight: 1.4,
      fillColor: color, fillOpacity: 0.9, opacity: 1,
    };
  }
  function vectorStyle(color) {
    return { color, weight: 2, opacity: 1, fillColor: color, fillOpacity: 0.45 };
  }
  function bindPopup(feature, layer) {
    const p = feature.properties || {};
    const name = p.title || p.name || p.NAME || p.headline || p.event || p.place || "";
    const rows = Object.keys(p).slice(0, 8)
      .map((k) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(p[k])}</td></tr>`)
      .join("");
    layer.bindPopup(
      (name ? `<strong>${escapeHtml(name)}</strong>` : "") +
      (rows ? `<table class="popup">${rows}</table>` : "(no attributes)")
    );
  }

  // ------------------------------------------------------------- toggle / add
  function toggleLayer(rec) {
    if (active.has(rec.id)) removeLayer(rec.id);
    else addLayer(rec);
  }

  async function addLayer(rec) {
    toast(`Loading “${rec.title}” …`);
    try {
      if (rec.type === "GeoJSON") await addGeoJson(rec);
      else if (rec.type === "ArcGISFeatureServer") addFeatureLayer(rec);
      else if (rec.type === "ArcGISMapServer" || rec.type === "ArcGISImageServer") await addArcGisLayer(rec);
      else addRaster(rec);
      updateRow(rec.id);
      toast(`Added “${rec.title}”.`);
    } catch (err) {
      console.error(err);
      active.delete(rec.id);
      updateRow(rec.id);
      toast(`Could not load “${rec.title}”: ${err.message || err}`, true);
    }
  }

  function addRaster(rec) {
    const layer = buildTileLayer(rec, DEFAULT_OPACITY);
    if (!layer) throw new Error("unsupported layer type: " + rec.type);
    layer.addTo(map);
    active.set(rec.id, { record: rec, kind: "tile", layer, opacity: DEFAULT_OPACITY });
    if (rec.bbox) flyToBbox(rec.bbox);
  }

  function addFeatureLayer(rec) {
    const color = colorFor(rec);
    const layer = L.esri.featureLayer({
      url: rec.url,
      pointToLayer: (_gj, latlng) => L.circleMarker(latlng, pointStyle(color)),
      style: () => vectorStyle(color),
      onEachFeature: bindPopup,
    });
    layer.on("requesterror", (e) =>
      toast(`“${rec.title}”: feature request failed (${e.message || "error"})`, true)
    );
    layer.addTo(map);
    active.set(rec.id, { record: rec, kind: "vector", layer, opacity: 1 });
    if (rec.bbox) flyToBbox(rec.bbox);
  }

  async function addGeoJson(rec) {
    const res = await fetch(proxied(rec.url), { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const color = colorFor(rec);
    const layer = L.geoJSON(data, {
      pointToLayer: (_gj, latlng) => L.circleMarker(latlng, pointStyle(color)),
      style: () => vectorStyle(color),
      onEachFeature: bindPopup,
    }).addTo(map);
    active.set(rec.id, { record: rec, kind: "vector", layer, opacity: 1 });
    try {
      map.flyToBounds(layer.getBounds(), { maxZoom: 8, duration: 1.2, padding: [24, 24] });
    } catch (_) {
      if (rec.bbox) flyToBbox(rec.bbox);
    }
  }

  function removeLayer(id) {
    const entry = active.get(id);
    if (!entry) return;
    map.removeLayer(entry.layer);
    active.delete(id);
    updateRow(id);
  }

  function flyToActive(id) {
    const entry = active.get(id);
    if (!entry) return;
    if (entry.kind === "vector" && entry.layer.getBounds) {
      try { map.flyToBounds(entry.layer.getBounds(), { maxZoom: 8, duration: 1.2 }); return; }
      catch (_) { /* fall through to bbox */ }
    }
    if (entry.record.bbox) flyToBbox(entry.record.bbox);
  }

  function setOpacity(id, value) {
    const entry = active.get(id);
    if (!entry) return;
    entry.opacity = value;
    if (entry.kind === "tile") {
      entry.layer.setOpacity(value);
    } else if (entry.layer.setStyle) {
      entry.layer.setStyle({ opacity: value, fillOpacity: value * 0.5 });
    }
  }

  // ------------------------------------------------------------- UI: catalog
  function dotClass(rec) {
    if (rec.checked_at == null) return "unknown";
    return rec.live ? "live" : "dead";
  }

  // Builds the inner HTML of a single catalog row, including the inline
  // opacity slider when the layer is currently active.
  function rowHtml(rec) {
    const entry = active.get(rec.id);
    const dotTitle = rec.live ? "validated live" : rec.checked_at ? "failed last check" : "not yet validated";
    let controls = "";
    if (entry) {
      controls = `
        <div class="layer-controls">
          <input type="range" class="opacity" min="0" max="1" step="0.05" value="${entry.opacity}" aria-label="Layer opacity" />
          <button type="button" class="zoom-btn" title="Zoom to layer">⊕</button>
        </div>`;
    }
    return `
      <div class="row-main">
        <div class="row1">
          <span class="dot ${dotClass(rec)}" title="${dotTitle}"></span>
          <span class="title">${escapeHtml(rec.title)}</span>
          <span class="check" aria-hidden="true">${entry ? "✓" : ""}</span>
        </div>
        ${rec.description ? `<div class="desc">${escapeHtml(rec.description)}</div>` : ""}
        <div class="meta">
          <span class="badge type">${rec.type}</span>
          <span class="badge">${rec.category}</span>
          ${rec.crs ? `<span class="badge crs" title="projection drawn on the map">${escapeHtml(rec.crs)}</span>` : ""}
          ${rec.cors === false ? '<span class="badge" title="server may block browser fetches">no-CORS</span>' : ""}
          ${rec.latency_ms != null ? `<span class="badge">${rec.latency_ms} ms</span>` : ""}
        </div>
        <div class="endpoint">
          <a class="url" href="${escapeHtml(rec.url)}" target="_blank" rel="noopener noreferrer"
             title="${escapeHtml(rec.url)}">${escapeHtml(shortUrl(rec.url))}</a>
          ${rec.layer ? `<span class="layer-name" title="layer / identifier">${escapeHtml(rec.layer)}</span>` : ""}
          <button type="button" class="copy-url" title="Copy endpoint URL" aria-label="Copy endpoint URL">⧉</button>
        </div>
      </div>${controls}`;
  }

  function wireRow(li, rec) {
    li.querySelector(".row-main").addEventListener("click", () => toggleLayer(rec));
    const slider = li.querySelector(".opacity");
    if (slider) {
      slider.addEventListener("input", (e) => setOpacity(rec.id, parseFloat(e.target.value)));
      slider.addEventListener("click", (e) => e.stopPropagation());
    }
    const zoom = li.querySelector(".zoom-btn");
    if (zoom) {
      zoom.addEventListener("click", (e) => { e.stopPropagation(); flyToActive(rec.id); });
    }
    // The endpoint link/copy control must not toggle the layer.
    const link = li.querySelector(".url");
    if (link) link.addEventListener("click", (e) => e.stopPropagation());
    const copy = li.querySelector(".copy-url");
    if (copy) {
      copy.addEventListener("click", (e) => {
        e.stopPropagation();
        const done = () => toast("Endpoint URL copied.");
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(rec.url).then(done, () => toast("Copy failed.", true));
        } else {
          const ta = document.createElement("textarea");
          ta.value = rec.url; document.body.appendChild(ta); ta.select();
          try { document.execCommand("copy"); done(); } catch (_) { toast("Copy failed.", true); }
          document.body.removeChild(ta);
        }
      });
    }
  }

  function updateRow(id) {
    const li = document.querySelector(`.layer[data-id="${id}"]`);
    if (!li) return;
    const rec = catalog.endpoints.find((r) => r.id === id);
    li.classList.toggle("added", active.has(id));
    li.innerHTML = rowHtml(rec);
    wireRow(li, rec);
  }

  function renderCatalog() {
    const ul = $("#catalog");
    const q = $("#search").value.trim().toLowerCase();
    const liveOnly = $("#live-only").checked;
    const cats = activeCategories();

    const items = catalog.endpoints.filter((rec) => {
      if (liveOnly && !rec.live) return false;
      if (cats.size && !cats.has(rec.category)) return false;
      if (q) {
        const hay = `${rec.title} ${rec.description} ${rec.category} ${rec.type} ${rec.attribution} ${rec.url} ${rec.layer || ""} ${rec.crs || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    ul.innerHTML = "";
    if (!items.length) {
      ul.innerHTML = '<li class="empty">No matching layers.</li>';
      return;
    }
    for (const rec of items) {
      const li = document.createElement("li");
      li.className = "layer" + (active.has(rec.id) ? " added" : "");
      li.dataset.id = rec.id;
      li.innerHTML = rowHtml(rec);
      wireRow(li, rec);
      ul.appendChild(li);
    }
  }

  // ------------------------------------------------------------- UI: filters
  function buildFilters() {
    const wrap = $("#filters");
    const cats = catalog.stats.by_category;
    wrap.innerHTML = "";
    Object.keys(cats).sort().forEach((cat) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.dataset.cat = cat;
      chip.textContent = `${cat} (${cats[cat]})`;
      chip.addEventListener("click", () => {
        chip.classList.toggle("active");
        renderCatalog();
      });
      wrap.appendChild(chip);
    });
  }

  function activeCategories() {
    return new Set(
      [...document.querySelectorAll(".chip.active")].map((c) => c.dataset.cat)
    );
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // ----------------------------------------------------- UI: responsive sheet
  function toggleSidebar(force) {
    const sb = $("#sidebar");
    const open = force != null ? force : !sb.classList.contains("open");
    sb.classList.toggle("open", open);
    $("#backdrop").classList.toggle("show", open);
    $("#menu-toggle").setAttribute("aria-expanded", String(open));
  }

  function wireUi() {
    $("#search").addEventListener("input", renderCatalog);
    $("#live-only").addEventListener("change", renderCatalog);
    $("#menu-toggle").addEventListener("click", () => toggleSidebar());
    $("#sidebar-close").addEventListener("click", () => toggleSidebar(false));
    $("#backdrop").addEventListener("click", () => toggleSidebar(false));
  }

  // --------------------------------------------------------------- bootstrap
  async function main() {
    initMap();
    wireUi();
    try {
      const res = await fetch(CFG.catalogUrl, { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      catalog = await res.json();
    } catch (err) {
      toast(`Failed to load catalog (${CFG.catalogUrl}): ${err.message}`, true);
      $("#catalog").innerHTML = '<li class="empty">Could not load catalog.json. Run the scraper, then serve this folder.</li>';
      return;
    }

    const s = catalog.stats;
    $("#catalog-meta").innerHTML =
      `<strong>${s.total}</strong> endpoints · <strong>${s.live}</strong> validated live` +
      (catalog.generated_at ? `<br>generated ${catalog.generated_at.replace("T", " ").replace("+00:00", " UTC")}` : "");

    buildFilters();
    renderCatalog();
  }

  function boot() {
    if (typeof L === "undefined" || !L.esri) {
      return setTimeout(boot, 60);
    }
    main();
  }
  document.addEventListener("DOMContentLoaded", boot);
})();
