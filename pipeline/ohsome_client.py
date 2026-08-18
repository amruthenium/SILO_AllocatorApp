"""
Thin wrapper around the ohsome API (https://api.ohsome.org) elements/geometry
endpoint. Replaces the manual `catch_PY/building_osm.py`, `PoiPoly_all.py`
and `node_all.py` scripts referenced in the workflow notes.
"""
import geopandas as gpd
import requests

from config import OHSOME_BASE, OHSOME_TIME, WGS84


def fetch_elements(bbox, osm_filter, time=OHSOME_TIME, clip_geometry=True):
    """
    bbox: "west,south,east,north" in WGS84
    osm_filter: an ohsome filter expression, e.g. "building=* and geometry:polygon"
    Returns a GeoDataFrame in EPSG:4326.
    """
    url = f"{OHSOME_BASE}/elements/geometry"
    params = {
        "bboxes": bbox,
        "filter": osm_filter,
        "time": time,
        "properties": "tags,metadata",
        "clipGeometry": str(clip_geometry).lower(),
    }
    headers = {"User-Agent": "zoneattr-pipeline/1.0 (research use)"}
    resp = requests.post(url, data=params, headers=headers, timeout=300)
    resp.raise_for_status()
    gj = resp.json()
    features = gj.get("features", [])
    if not features:
        return gpd.GeoDataFrame(columns=["osm_id", "geometry"], geometry="geometry", crs=WGS84)

    gdf = gpd.GeoDataFrame.from_features(features, crs=WGS84)
    # ohsome returns @osmId / tags-as-dict; normalize to flat columns like the
    # original OSM exports (osm_id, fclass, name, ...).
    if "@osmId" in gdf.columns:
        gdf["osm_id"] = gdf["@osmId"].str.replace(r"^\D+", "", regex=True)
    tag_cols = set()
    if "@other_tags" in gdf.columns:
        pass
    # Flatten tags dict (ohsome puts feature tags at top-level "tags" or as
    # individual properties depending on API version) into columns.
    if "tags" in gdf.columns:
        tags_df = gdf["tags"].apply(lambda t: t if isinstance(t, dict) else {})
        tags_expanded = gpd.pd.json_normalize(tags_df)
        for c in tags_expanded.columns:
            gdf[c] = tags_expanded[c].values
    return gdf


def fetch_buildings(bbox, time=OHSOME_TIME):
    return fetch_elements(bbox, "building=* and geometry:polygon", time=time)


def fetch_landuse(bbox, time=OHSOME_TIME):
    return fetch_elements(bbox, "landuse=* and geometry:polygon", time=time)


def fetch_poi_polygons(bbox, keys, time=OHSOME_TIME):
    """keys: list like ['shop','amenity','office','tourism','leisure']"""
    filt = " or ".join(f"{k}=*" for k in keys)
    return fetch_elements(bbox, f"({filt}) and geometry:polygon", time=time)


def fetch_poi_points(bbox, keys, time=OHSOME_TIME):
    filt = " or ".join(f"{k}=*" for k in keys)
    return fetch_elements(bbox, f"({filt}) and geometry:point", time=time)
