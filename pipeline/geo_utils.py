"""
Geopandas equivalents of the manual QGIS steps mentioned in the workflow
notes: "fix geometries", "toolbox intersection", "difference".
"""
import geopandas as gpd
import pandas as pd


def fix_geometries(gdf):
    """Equivalent of QGIS 'Fix geometries'."""
    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].buffer(0)
    gdf = gdf[~gdf["geometry"].is_empty & gdf["geometry"].notna()]
    return gdf


def difference(gdf_a, gdf_b, crs=None):
    """Equivalent of QGIS 'Difference': parts of A not overlapping B."""
    gdf_a = fix_geometries(gdf_a)
    gdf_b = fix_geometries(gdf_b)
    if crs:
        gdf_a = gdf_a.to_crs(crs)
        gdf_b = gdf_b.to_crs(crs)
    elif gdf_a.crs != gdf_b.crs:
        gdf_b = gdf_b.to_crs(gdf_a.crs)
    return gpd.overlay(gdf_a, gdf_b, how="difference", keep_geom_type=False)


def intersection_split(gdf, zones, zone_id_col="TAZ_ID", extra_cols=None):
    """
    Equivalent of QGIS 'Intersection' used to split polygons crossing more
    than one zone, then tag each fragment with the zone id (+ optional
    extra columns like gemeinde_ID/AGS).
    """
    gdf = fix_geometries(gdf)
    zones = fix_geometries(zones)
    if gdf.crs != zones.crs:
        zones = zones.to_crs(gdf.crs)
    cols = [zone_id_col] + (extra_cols or []) + ["geometry"]
    out = gpd.overlay(gdf, zones[cols], how="intersection", keep_geom_type=False)
    return out


def spatial_join_point_in_polygon(points, zones, zone_id_col="TAZ_ID", extra_cols=None):
    """Point-in-polygon join used for POI points (no splitting needed)."""
    if points.crs != zones.crs:
        zones = zones.to_crs(points.crs)
    cols = [zone_id_col] + (extra_cols or []) + ["geometry"]
    joined = gpd.sjoin(points, zones[cols], how="left", predicate="within")
    joined = joined.drop(columns=[c for c in joined.columns if c == "index_right"])
    return joined


def centroid_xy(gdf, crs, x_col="x", y_col="y"):
    gdf = gdf.copy()
    gdf = gdf.to_crs(crs)
    cent = gdf.geometry.centroid
    gdf[x_col] = cent.x
    gdf[y_col] = cent.y
    return gdf


def remove_overlapping(target, remove_against, crs=None):
    """
    Delete elements in `target` that overlap `remove_against` (used for
    the POI vs. landuse/building cleanup step). Works for points or
    polygons via spatial predicate rather than geometric difference, which
    is what you want when you're deleting whole *rows*, not clipping shapes.
    """
    target = target.copy()
    ref = fix_geometries(remove_against)
    if crs:
        target = target.to_crs(crs)
        ref = ref.to_crs(crs)
    elif target.crs != ref.crs:
        ref = ref.to_crs(target.crs)
    hit = gpd.sjoin(target, ref[["geometry"]], how="left", predicate="intersects")
    keep_mask = hit["index_right"].isna()
    # sjoin can duplicate rows when multiple matches occur; collapse back
    keep_mask = keep_mask.groupby(level=0).all()
    return target.loc[keep_mask[keep_mask].index]
