"""Curated, hand-verified live endpoints.

These are well-known public services that stream straight into a web map with
no download step, chosen because they are reliably available and (mostly)
CORS-enabled. They guarantee the globe is useful out of the box, even before
you run the catalog crawlers. Run the scraper to validate/refresh them and to
discover thousands more.
"""

from __future__ import annotations

from typing import List

from ..models import Endpoint

GLOBE = [-180.0, -85.0, 180.0, 85.0]


def get_seed_endpoints() -> List[Endpoint]:
    return [
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
            title="CARTO Positron (light)",
            type="XYZ", category="basemap",
            url="https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
            source="seed", bbox=GLOBE,
            attribution="© OpenStreetMap contributors © CARTO",
            description="Minimal light basemap, good as a backdrop for data overlays.",
        ),
        Endpoint(
            title="Esri World Imagery",
            type="XYZ", category="imagery",
            url="https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            source="seed", bbox=GLOBE,
            attribution="Esri, Maxar, Earthstar Geographics",
            description="Global high-resolution satellite & aerial imagery basemap.",
        ),
        # ----------------------------------------------------------- imagery
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
            title="USGS National Map — Imagery Only",
            type="ArcGISMapServer", category="imagery",
            url="https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer",
            source="seed", bbox=[-180.0, -15.0, -50.0, 75.0],
            attribution="USGS The National Map",
            description="USGS orthoimagery basemap covering the United States.",
        ),
        # --------------------------------------------------------- elevation
        Endpoint(
            title="USGS National Map — Shaded Relief",
            type="ArcGISMapServer", category="elevation",
            url="https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer",
            source="seed", bbox=[-180.0, -15.0, -50.0, 75.0],
            attribution="USGS The National Map / 3DEP",
            description="Hillshade derived from the USGS 3DEP elevation program.",
        ),
        # ----------------------------------------------------------- weather
        Endpoint(
            title="Iowa State — NEXRAD Base Reflectance (US radar mosaic)",
            type="WMS", category="weather",
            url="https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q.cgi",
            layer="nexrad-n0q-900913",
            source="seed", bbox=[-126.0, 24.0, -66.0, 50.0],
            attribution="Iowa Environmental Mesonet, Iowa State University",
            description="Near-real-time NEXRAD base reflectance mosaic over the lower 48.",
        ),
        Endpoint(
            title="NWS Active Weather Alerts",
            type="GeoJSON", category="weather",
            url="https://api.weather.gov/alerts/active",
            source="seed", bbox=[-180.0, 15.0, -60.0, 72.0],
            attribution="NOAA / National Weather Service",
            description="Live US watches, warnings and advisories as GeoJSON. CORS-enabled.",
        ),
        # ----------------------------------------------------------- hazards
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
        Endpoint(
            title="NIFC — Current Wildfire Incident Locations (US)",
            type="ArcGISFeatureServer", category="hazards",
            url="https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0",
            source="seed", bbox=[-180.0, 15.0, -60.0, 72.0],
            attribution="National Interagency Fire Center (WFIGS)",
            description="Live US wildfire incident points from the Wildland Fire Interagency Geospatial Services.",
        ),
        # ------------------------------------------------------- boundaries
        Endpoint(
            title="Natural Earth — Admin 0 Countries (GeoServer demo)",
            type="WMS", category="boundaries",
            url="https://ahocevar.com/geoserver/wms",
            layer="ne:ne_10m_admin_0_countries",
            source="seed", bbox=GLOBE,
            attribution="Natural Earth via ahocevar GeoServer",
            description="World country polygons from Natural Earth, served via a public GeoServer.",
        ),
        Endpoint(
            title="US States (GeoServer demo)",
            type="WMS", category="boundaries",
            url="https://ahocevar.com/geoserver/wms",
            layer="topp:states",
            source="seed", bbox=[-124.7, 24.9, -66.9, 49.4],
            attribution="GeoServer demo data",
            description="Classic GeoServer demo layer of US state polygons with census attributes.",
        ),
        # ------------------------------------------------------------ oceans
        Endpoint(
            title="GEBCO Global Bathymetry (WMS)",
            type="WMS", category="oceans",
            url="https://wms.gebco.net/mapserv",
            layer="GEBCO_LATEST",
            source="seed", bbox=GLOBE,
            attribution="GEBCO Compilation Group",
            description="Global gridded bathymetry — the shape of the world's ocean floor.",
        ),
        # ------------------------------------------------------ live-events
        Endpoint(
            title="USGS Streamflow — current conditions (sites)",
            type="ArcGISFeatureServer", category="live-events",
            url="https://maps.waterdata.usgs.gov/arcgis/rest/services/nwism/temp/MapServer/0",
            source="seed", bbox=[-180.0, 15.0, -60.0, 72.0],
            attribution="USGS Water Data",
            description="USGS surface-water monitoring sites with current streamflow status.",
        ),
    ]
