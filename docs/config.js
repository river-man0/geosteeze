// geosteeze front-end configuration.
// Edit these values to taste. `runtime-config.js` (served by serve.py) can
// override any of them at load time — e.g. to enable the local CORS proxy.
window.GEOSTEEZE = {
  // Optional Cesium Ion access token. Leave blank to run fully Ion-free
  // (OpenStreetMap base layer, ellipsoid terrain). Provide a token from
  // https://cesium.com/ion/ to unlock world terrain and premium basemaps.
  cesiumIonToken: "",

  // Where to load the compiled catalog from.
  catalogUrl: "catalog.json",

  // CORS proxy prefix for fetch-based data (GeoJSON / ArcGIS feature queries).
  // Empty string = fetch directly. serve.py sets this to "/proxy?url=".
  proxyUrl: "",

  // Default date for time-aware WMTS layers (e.g. NASA GIBS daily imagery).
  defaultDate: "2023-08-01",

  // Cesium version loaded from the CDN.
  cesiumVersion: "1.119",
};
