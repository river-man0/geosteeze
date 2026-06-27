/* geosteeze — explore live geographic data endpoints on a Cesium globe. */
(function () {
  "use strict";

  const CFG = window.GEOSTEEZE;
  const CATEGORY_COLORS = {
    basemap: "#9aa7b4", imagery: "#5dade2", elevation: "#a47b5a",
    weather: "#48c9b0", hazards: "#e74c3c", environment: "#58d68d",
    boundaries: "#bb8fce", infrastructure: "#f5b041", oceans: "#5499c7",
    "live-events": "#ec7063", other: "#7f8c8d",
  };

  // active layer id -> { record, handle, type, layer? , dataSource? }
  const active = new Map();
  let catalog = null;
  let viewer = null;

  // ----------------------------------------------------------------- helpers
  const $ = (sel) => document.querySelector(sel);

  function proxied(url) {
    return CFG.proxyUrl ? CFG.proxyUrl + encodeURIComponent(url) : url;
  }

  function toast(msg, isError) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    el.classList.toggle("error", !!isError);
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), isError ? 6000 : 3500);
  }

  function rectFromBbox(bbox) {
    if (!bbox || bbox.length !== 4) return null;
    let [w, s, e, n] = bbox;
    w = Math.max(-180, w); e = Math.min(180, e);
    s = Math.max(-89, s); n = Math.min(89, n);
    if (e <= w || n <= s) return null;
    return Cesium.Rectangle.fromDegrees(w, s, e, n);
  }

  function flyToBbox(bbox) {
    const rect = rectFromBbox(bbox);
    if (rect) viewer.camera.flyTo({ destination: rect, duration: 1.2 });
  }

  // ------------------------------------------------------------- map set-up
  function initViewer() {
    if (CFG.cesiumIonToken) Cesium.Ion.defaultAccessToken = CFG.cesiumIonToken;
    else Cesium.Ion.defaultAccessToken = undefined;

    const osm = new Cesium.UrlTemplateImageryProvider({
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      maximumLevel: 19,
      credit: "© OpenStreetMap contributors",
    });

    viewer = new Cesium.Viewer("cesiumContainer", {
      baseLayer: new Cesium.ImageryLayer(osm),
      baseLayerPicker: false,
      geocoder: false,
      homeButton: true,
      sceneModePicker: true,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: true,
      infoBox: true,
      selectionIndicator: true,
    });
    viewer.scene.globe.enableLighting = false;
    viewer.cesiumWidget.creditContainer.style.fontSize = "11px";
  }

  // ------------------------------------------------- imagery provider builders
  function buildImageryProvider(rec) {
    switch (rec.type) {
      case "XYZ":
        return new Cesium.UrlTemplateImageryProvider({
          url: rec.url,
          maximumLevel: 19,
          credit: rec.attribution || "",
        });

      case "WMS":
        return new Cesium.WebMapServiceImageryProvider({
          url: rec.url,
          layers: rec.layer,
          parameters: { transparent: true, format: "image/png" },
          credit: rec.attribution || "",
        });

      case "WMTS": {
        const opts = {
          url: rec.url,
          layer: rec.layer,
          style: rec.style || "default",
          format: rec.tile_format || "image/png",
          tileMatrixSetID: rec.tile_matrix_set,
          credit: rec.attribution || "",
        };
        if (rec.tiling_scheme === "geographic") {
          opts.tilingScheme = new Cesium.GeographicTilingScheme();
        }
        if (rec.time_dimension) {
          opts.dimensions = { Time: CFG.defaultDate };
        }
        return new Cesium.WebMapTileServiceImageryProvider(opts);
      }

      case "ArcGISImageServer":
      case "ArcGISMapServer":
        // fromUrl is async; return the promise and resolve in addLayer.
        return Cesium.ArcGisMapServerImageryProvider.fromUrl(rec.url);
    }
    return null;
  }

  // ----------------------------------------------------- GeoJSON styling
  function styleGeoJson(ds, rec) {
    const color = Cesium.Color.fromCssColorString(
      CATEGORY_COLORS[rec.category] || CATEGORY_COLORS.other
    );
    ds.entities.values.forEach((ent) => {
      if (ent.billboard) {
        ent.billboard = undefined;
        ent.point = new Cesium.PointGraphics({
          color: color,
          pixelSize: 9,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 1.5,
        });
      }
      if (ent.polygon) {
        ent.polygon.material = color.withAlpha(0.45);
        ent.polygon.outline = true;
        ent.polygon.outlineColor = color;
      }
      if (ent.polyline) {
        ent.polyline.material = color;
        ent.polyline.width = 2;
      }
    });
  }

  // ------------------------------------------------------------- add / remove
  async function addLayer(rec) {
    if (active.has(rec.id)) {
      flyToActive(rec.id);
      return;
    }
    toast(`Loading “${rec.title}” …`);
    try {
      if (rec.type === "GeoJSON" || rec.type === "ArcGISFeatureServer") {
        await addVector(rec);
      } else {
        await addImagery(rec);
      }
      markAdded(rec.id, true);
      renderActive();
      toast(`Added “${rec.title}”.`);
    } catch (err) {
      console.error(err);
      toast(`Could not load “${rec.title}”: ${err.message || err}`, true);
    }
  }

  async function addImagery(rec) {
    let provider = buildImageryProvider(rec);
    if (!provider) throw new Error("unsupported imagery type");
    if (provider.then) provider = await provider; // ArcGIS fromUrl()
    const layer = viewer.imageryLayers.addImageryProvider(provider);
    layer.alpha = rec.type === "basemap" ? 1.0 : 0.92;
    active.set(rec.id, { record: rec, type: "imagery", layer });
    if (rec.bbox) flyToBbox(rec.bbox);
  }

  async function addVector(rec) {
    let url = rec.url;
    if (rec.type === "ArcGISFeatureServer") {
      const base = rec.url.replace(/\/+$/, "");
      url = `${base}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson&resultRecordCount=4000`;
    }
    const ds = await Cesium.GeoJsonDataSource.load(proxied(url), {
      clampToGround: true,
    });
    styleGeoJson(ds, rec);
    await viewer.dataSources.add(ds);
    active.set(rec.id, { record: rec, type: "vector", dataSource: ds });
    // Prefer flying to the data itself; fall back to the declared bbox.
    try {
      await viewer.flyTo(ds, { duration: 1.2 });
    } catch (_) {
      if (rec.bbox) flyToBbox(rec.bbox);
    }
  }

  function removeLayer(id) {
    const entry = active.get(id);
    if (!entry) return;
    if (entry.type === "imagery") viewer.imageryLayers.remove(entry.layer, true);
    else if (entry.type === "vector") viewer.dataSources.remove(entry.dataSource, true);
    active.delete(id);
    markAdded(id, false);
    renderActive();
  }

  function flyToActive(id) {
    const entry = active.get(id);
    if (!entry) return;
    if (entry.type === "vector") viewer.flyTo(entry.dataSource, { duration: 1.2 }).catch(() => {});
    else if (entry.record.bbox) flyToBbox(entry.record.bbox);
  }

  function setOpacity(id, value) {
    const entry = active.get(id);
    if (!entry) return;
    if (entry.type === "imagery") entry.layer.alpha = value;
    else if (entry.type === "vector") {
      entry.dataSource.entities.values.forEach((ent) => {
        if (ent.point) ent.point.color = ent.point.color.getValue().withAlpha(value);
        if (ent.polygon) {
          const c = ent.polygon.material.color.getValue();
          ent.polygon.material = c.withAlpha(value * 0.5);
        }
      });
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
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // --------------------------------------------------------------- bootstrap
  async function main() {
    initViewer();
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

    $("#search").addEventListener("input", renderCatalog);
    $("#live-only").addEventListener("change", renderCatalog);
    $("#clear-active").addEventListener("click", () => {
      [...active.keys()].forEach(removeLayer);
    });
  }

  function boot() {
    if (typeof Cesium === "undefined") {
      // Cesium.js (deferred) not ready yet; retry shortly.
      return setTimeout(boot, 60);
    }
    main();
  }
  document.addEventListener("DOMContentLoaded", boot);
})();
