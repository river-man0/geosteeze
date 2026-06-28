/* geosteeze — explore live geographic data endpoints on a Leaflet web map. */
(function () {
  "use strict";

  const CFG = window.GEOSTEEZE;
  const MOBILE = "(max-width: 760px)";
  const CATEGORY_COLORS = {
    basemap: "#9aa7b4", imagery: "#5dade2", elevation: "#a47b5a",
    weather: "#48c9b0", hazards: "#e74c3c", environment: "#58d68d",
    boundaries: "#bb8fce", infrastructure: "#f5b041", oceans: "#5499c7",
    "live-events": "#ec7063", other: "#7f8c8d",
  };

  // active layer id -> { record, kind: "tile"|"vector", layer }
  const active = new Map();
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

    // Keep Leaflet's internal size in sync with the responsive layout.
    window.addEventListener("resize", () => map.invalidateSize());
  }

  // --------------------------------------------------- raster layer builders
  function buildTileLayer(rec) {
    const opacity = 0.92;
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

      case "ArcGISMapServer":
        // dynamicMapLayer uses the export endpoint, so it works for both
        // cached and dynamic MapServers regardless of tiling scheme.
        return L.esri.dynamicMapLayer({
          url: rec.url, opacity, attribution: rec.attribution || "",
        });

      case "ArcGISImageServer":
        return L.esri.imageMapLayer({
          url: rec.url, opacity, attribution: rec.attribution || "",
        });
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

  // ------------------------------------------------------------- add / remove
  async function addLayer(rec) {
    if (active.has(rec.id)) {
      flyToActive(rec.id);
      closeSidebarMobile();
      return;
    }
    toast(`Loading “${rec.title}” …`);
    try {
      if (rec.type === "GeoJSON") await addGeoJson(rec);
      else if (rec.type === "ArcGISFeatureServer") addFeatureLayer(rec);
      else addRaster(rec);
      markAdded(rec.id, true);
      renderActive();
      toast(`Added “${rec.title}”.`);
      closeSidebarMobile();
    } catch (err) {
      console.error(err);
      toast(`Could not load “${rec.title}”: ${err.message || err}`, true);
    }
  }

  function addRaster(rec) {
    const layer = buildTileLayer(rec);
    if (!layer) throw new Error("unsupported layer type: " + rec.type);
    layer.addTo(map);
    active.set(rec.id, { record: rec, kind: "tile", layer });
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
    active.set(rec.id, { record: rec, kind: "vector", layer });
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
    active.set(rec.id, { record: rec, kind: "vector", layer });
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
    markAdded(id, false);
    renderActive();
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

  function renderCatalog() {
    const ul = $("#catalog");
    const q = $("#search").value.trim().toLowerCase();
    const liveOnly = $("#live-only").checked;
    const cats = activeCategories();

    const items = catalog.endpoints.filter((rec) => {
      if (liveOnly && !rec.live) return false;
      if (cats.size && !cats.has(rec.category)) return false;
      if (q) {
        const hay = `${rec.title} ${rec.description} ${rec.category} ${rec.type} ${rec.attribution}`.toLowerCase();
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
      li.innerHTML = `
        <div class="row1">
          <span class="dot ${dotClass(rec)}" title="${rec.live ? "validated live" : rec.checked_at ? "failed last check" : "not yet validated"}"></span>
          <span class="title">${escapeHtml(rec.title)}</span>
        </div>
        ${rec.description ? `<div class="desc">${escapeHtml(rec.description)}</div>` : ""}
        <div class="meta">
          <span class="badge type">${rec.type}</span>
          <span class="badge">${rec.category}</span>
          ${rec.cors === false ? '<span class="badge" title="server may block browser fetches">no-CORS</span>' : ""}
          ${rec.latency_ms != null ? `<span class="badge">${rec.latency_ms} ms</span>` : ""}
        </div>`;
      li.addEventListener("click", () => addLayer(rec));
      ul.appendChild(li);
    }
  }

  function markAdded(id, added) {
    const li = document.querySelector(`.layer[data-id="${id}"]`);
    if (li) li.classList.toggle("added", added);
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

  // ------------------------------------------------------- UI: active panel
  function renderActive() {
    const panel = $("#active-panel");
    const list = $("#active-list");
    panel.classList.toggle("hidden", active.size === 0);
    list.innerHTML = "";
    for (const [id, entry] of active) {
      const rec = entry.record;
      const li = document.createElement("li");
      li.className = "active-item";
      li.innerHTML = `
        <div class="ai-top">
          <span class="dot ${dotClass(rec)}"></span>
          <span class="ai-title" title="${escapeHtml(rec.title)}">${escapeHtml(rec.title)}</span>
          <button data-act="fly" title="Zoom to layer">⊕</button>
          <button data-act="remove" title="Remove">✕</button>
        </div>
        <input type="range" min="0" max="1" step="0.05" value="0.92" />`;
      li.querySelector('[data-act="remove"]').addEventListener("click", () => removeLayer(id));
      li.querySelector('[data-act="fly"]').addEventListener("click", () => flyToActive(id));
      li.querySelector("input").addEventListener("input", (e) =>
        setOpacity(id, parseFloat(e.target.value))
      );
      list.appendChild(li);
    }
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // ----------------------------------------------------- UI: responsive drawer
  function toggleSidebar(force) {
    const sb = $("#sidebar");
    const open = force != null ? force : !sb.classList.contains("open");
    sb.classList.toggle("open", open);
    $("#backdrop").classList.toggle("show", open);
    $("#menu-toggle").setAttribute("aria-expanded", String(open));
  }
  function closeSidebarMobile() {
    if (isMobile()) toggleSidebar(false);
  }

  function wireUi() {
    $("#search").addEventListener("input", renderCatalog);
    $("#live-only").addEventListener("change", renderCatalog);
    $("#clear-active").addEventListener("click", () => {
      [...active.keys()].forEach(removeLayer);
    });
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
      // Leaflet / esri-leaflet (deferred) not ready yet; retry shortly.
      return setTimeout(boot, 60);
    }
    main();
  }
  document.addEventListener("DOMContentLoaded", boot);
})();
