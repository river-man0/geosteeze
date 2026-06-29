"""Curated, hand-verified live endpoints.

These are well-known public services that stream straight into a web map with
no download step, chosen because they are reliably available and CORS-enabled.
They guarantee the globe is useful out of the box, even before you run the
catalog crawlers. Run the scraper to validate/refresh them and to discover
thousands more.

The focus here is deliberately **global imagery, Arctic sea ice, and Canadian
data** rather than US-centric feeds — every layer below was probed live before
being added (liveness, CORS, and an actual tile/GetMap render check).
"""

from __future__ import annotations

from typing import List

from ..models import Endpoint

GLOBE = [-180.0, -85.0, 180.0, 85.0]
ARCTIC = [-180.0, 50.0, 180.0, 90.0]
CANADA = [-141.0, 41.0, -52.0, 84.0]


def get_seed_endpoints() -> List[Endpoint]:
    seeds = [
        # ---------------------------------------------------------- basemaps
        Endpoint(
            title="OpenStreetMap Standard",
            type="XYZ", category="basemap",
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            source="seed", bbox=GLOBE,
            attribution="© OpenStreetMap contributors",
            description="Global street basemap rendered from OpenStreetMap data.",
        ),
        Endpoint(
            title="CARTO Dark Matter",
            type="XYZ", category="basemap",
            url="https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            source="seed", bbox=GLOBE,
            attribution="© OpenStreetMap contributors © CARTO",
            description="Muted dark basemap, an ideal low-glare backdrop for data overlays.",
        ),
        # ------------------------------------------------- global imagery
        Endpoint(
            title="Esri World Imagery",
            type="XYZ", category="imagery",
            url="https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            source="seed", bbox=GLOBE,
            attribution="Esri, Maxar, Earthstar Geographics",
            description="Global high-resolution satellite & aerial imagery basemap.",
        ),
        Endpoint(
            title="Sentinel-2 Cloudless (EOX)",
            type="WMS", category="imagery",
            url="https://tiles.maps.eox.at/wms",
            layer="s2cloudless",
            source="seed", bbox=GLOBE,
            tile_format="image/png",
            attribution="Sentinel-2 cloudless — https://s2maps.eu by EOX IT Services GmbH",
            description="Global cloud-free mosaic built from ESA Copernicus Sentinel-2 imagery.",
        ),
        Endpoint(
            title="NASA GIBS — Blue Marble (Shaded Relief + Bathymetry)",
            type="WMTS", category="imagery",
            url="https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi",
            layer="BlueMarble_ShadedRelief_Bathymetry",
            source="seed", bbox=GLOBE,
            tile_matrix_set="500m", tile_format="image/jpeg",
            style="default", tiling_scheme="geographic",
            attribution="NASA EOSDIS GIBS",
            description="Static true-colour land surface with shaded relief and ocean bathymetry.",
        ),
        Endpoint(
            title="NASA GIBS — MODIS Terra True Color (daily)",
            type="WMTS", category="imagery",
            url="https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi",
            layer="MODIS_Terra_CorrectedReflectance_TrueColor",
            source="seed", bbox=GLOBE,
            tile_matrix_set="250m", tile_format="image/jpeg",
            style="default", tiling_scheme="geographic", time_dimension=True,
            attribution="NASA EOSDIS GIBS",
            description="Daily global true-colour mosaic from MODIS on Terra. Time-aware.",
        ),
        Endpoint(
            title="NASA GIBS — MODIS Aqua True Color (daily)",
            type="WMTS", category="imagery",
            url="https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi",
            layer="MODIS_Aqua_CorrectedReflectance_TrueColor",
            source="seed", bbox=GLOBE,
            tile_matrix_set="250m", tile_format="image/jpeg",
            style="default", tiling_scheme="geographic", time_dimension=True,
            attribution="NASA EOSDIS GIBS",
            description="Daily global true-colour mosaic from MODIS on Aqua. Time-aware.",
        ),
        Endpoint(
            title="NASA GIBS — VIIRS/SNPP True Color (daily)",
            type="WMTS", category="imagery",
            url="https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi",
            layer="VIIRS_SNPP_CorrectedReflectance_TrueColor",
            source="seed", bbox=GLOBE,
            tile_matrix_set="250m", tile_format="image/jpeg",
            style="default", tiling_scheme="geographic", time_dimension=True,
            attribution="NASA EOSDIS GIBS",
            description="Daily global true-colour mosaic from VIIRS on Suomi-NPP. Time-aware.",
        ),
        # ----------------------------------------------- arctic sea ice
        Endpoint(
            title="NASA GIBS — AMSR2 Sea Ice Concentration (12 km, daily)",
            type="WMTS", category="oceans",
            url="https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi",
            layer="AMSRU2_Sea_Ice_Concentration_12km",
            source="seed", bbox=ARCTIC,
            tile_matrix_set="2km", tile_format="image/png",
            style="default", tiling_scheme="geographic", time_dimension=True,
            attribution="NASA EOSDIS GIBS / AMSR2 (JAXA)",
            description="Daily polar sea-ice concentration from AMSR2 — the Arctic (and Antarctic) ice extent. Time-aware.",
        ),
        # --------------------------------------- Canadian live weather
        Endpoint(
            title="Environment Canada GeoMet — Radar (1 km rain)",
            type="WMS", category="weather",
            url="https://geo.weather.gc.ca/geomet",
            layer="RADAR_1KM_RRAI",
            source="seed", bbox=CANADA,
            tile_format="image/png",
            attribution="Environment and Climate Change Canada — MSC GeoMet",
            description="Near-real-time 1 km national radar rain-rate composite over Canada.",
        ),
        Endpoint(
            title="Environment Canada GeoMet — Current Conditions",
            type="WMS", category="weather",
            url="https://geo.weather.gc.ca/geomet",
            layer="CURRENT_CONDITIONS",
            source="seed", bbox=CANADA,
            tile_format="image/png",
            attribution="Environment and Climate Change Canada — MSC GeoMet",
            description="Live surface weather observations from Canadian stations.",
        ),
        # ------------------------------------------ Canadian base data
        Endpoint(
            title="NRCan CanVec — Topographic Features",
            type="WMS", category="boundaries",
            url="https://maps.geogratis.gc.ca/wms/canvec_en",
            layer="canvec",
            source="seed", bbox=CANADA,
            tile_format="image/png",
            attribution="Natural Resources Canada — CanVec",
            description="National topographic base for Canada: hydrography, transport, relief and admin features.",
        ),
        # ------------------------------------------------------ oceans
        Endpoint(
            title="GEBCO Global Bathymetry (WMS)",
            type="WMS", category="oceans",
            url="https://wms.gebco.net/mapserv",
            layer="GEBCO_LATEST",
            source="seed", bbox=GLOBE,
            attribution="GEBCO Compilation Group",
            description="Global gridded bathymetry — the shape of the world's ocean floor.",
        ),
        # -------------------------------------------------- boundaries
        Endpoint(
            title="Natural Earth — Admin 0 Countries (GeoServer demo)",
            type="WMS", category="boundaries",
            url="https://ahocevar.com/geoserver/wms",
            layer="ne:ne_10m_admin_0_countries",
            source="seed", bbox=GLOBE,
            attribution="Natural Earth via ahocevar GeoServer",
            description="World country polygons from Natural Earth, served via a public GeoServer.",
        ),
        # ---------------------------------------- global live hazards
        Endpoint(
            title="USGS Earthquakes — past 24 hours",
            type="GeoJSON", category="hazards",
            url="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
            source="seed", bbox=GLOBE,
            attribution="USGS Earthquake Hazards Program",
            description="Every earthquake located worldwide in the last day. Updates ~every minute.",
        ),
        Endpoint(
            title="USGS Earthquakes — M2.5+ past 7 days",
            type="GeoJSON", category="hazards",
            url="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson",
            source="seed", bbox=GLOBE,
            attribution="USGS Earthquake Hazards Program",
            description="Magnitude 2.5+ earthquakes worldwide over the past week.",
        ),
    ]
    # Record the CRS each seed is drawn in on the Leaflet map. Every raster seed
    # renders in Web Mercator (XYZ tiles, WMS requested in EPSG:3857, and GIBS
    # via its epsg3857 REST endpoint); GeoJSON feeds are plotted from WGS84.
    for ep in seeds:
        ep.crs = "EPSG:4326" if ep.type == "GeoJSON" else "EPSG:3857"
    return seeds
