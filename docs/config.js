// geosteeze front-end configuration.
// Edit these values to taste. `runtime-config.js` (served by serve.py) can
// override any of them at load time — e.g. to enable the local CORS proxy.
window.GEOSTEEZE = {
  // Where to load the compiled catalog from.
  catalogUrl: "catalog.json",

  // CORS proxy prefix for fetch-based data (GeoJSON / ArcGIS feature queries).
  // Empty string = fetch directly. serve.py sets this to "/proxy?url=".
  proxyUrl: "",

  // Default date for time-aware WMTS layers (e.g. NASA GIBS daily imagery).
  defaultDate: "2023-08-01",

  // Dark basemap tile template. CARTO "dark_all" gives a muted, low-glare
  // backdrop that lets data layers read clearly. Swap to any {z}/{x}/{y} URL.
  basemapUrl: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
  basemapSubdomains: "abcd",
  basemapAttribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
    '&copy; <a href="https://carto.com/attributions">CARTO</a>',
};
