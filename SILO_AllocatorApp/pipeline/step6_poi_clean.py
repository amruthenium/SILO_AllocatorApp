"""
Step 6: PoiPoints and PoiPolygons clean — replaces the QGIS difference step
and POI_all/Clean_poi_points.py
"""
import os

import geopandas as gpd

from config import TARGET_CRS
from pipeline import geo_utils


def run(poi_points_gpkg, poi_polygons_gpkg, landuse_building_job_gpkg, out_dir, log,
        fclass_col="fclass"):
    log("Loading layers...")
    points = gpd.read_file(poi_points_gpkg).to_crs(TARGET_CRS)
    polygons = gpd.read_file(poi_polygons_gpkg).to_crs(TARGET_CRS)
    landuse_building = gpd.read_file(landuse_building_job_gpkg).to_crs(TARGET_CRS)
    log(f"  {len(points)} points, {len(polygons)} polygons, "
        f"{len(landuse_building)} landuse/building reference features")

    log("Removing POI polygons overlapping landuse/building...")
    poly_clean = geo_utils.remove_overlapping(polygons, landuse_building, crs=TARGET_CRS)
    poly_path = os.path.join(out_dir, "POI_cleaned_polygon.gpkg")
    poly_clean.to_file(poly_path, driver="GPKG")
    log(f"  Wrote {poly_path} ({len(poly_clean)} of {len(polygons)} kept)")

    log("Removing POI points overlapping landuse/building...")
    pts_clean = geo_utils.remove_overlapping(points, landuse_building, crs=TARGET_CRS)
    pts_path = os.path.join(out_dir, "POI_cleaned_point.gpkg")
    pts_clean.to_file(pts_path, driver="GPKG")
    log(f"  Wrote {pts_path} ({len(pts_clean)} of {len(points)} kept)")

    log("Dropping points that fall inside a polygon of the same fclass...")
    if fclass_col in pts_clean.columns and fclass_col in poly_clean.columns:
        joined = gpd.sjoin(pts_clean, poly_clean[[fclass_col, "geometry"]],
                            how="left", predicate="within", lsuffix="pt", rsuffix="poly")
        same_class = joined[f"{fclass_col}_pt"] == joined[f"{fclass_col}_poly"]
        drop_index = joined.loc[same_class.fillna(False)].index
        final_points = pts_clean.drop(index=drop_index.unique())
    else:
        log("  fclass column missing on one layer — skipping same-class filter")
        final_points = pts_clean
    log(f"  {len(final_points)} points remain after same-class filter")

    log("Dropping duplicate rows left over from fix-geometries with no geometry...")
    final_points = final_points[final_points.geometry.notna() & ~final_points.geometry.is_empty]
    final_points = final_points.drop_duplicates(
        subset=[c for c in final_points.columns if c != "geometry"]
    )

    final_path = os.path.join(out_dir, "poi_points_final_cleaned.gpkg")
    final_points.to_file(final_path, driver="GPKG")
    log(f"Wrote {final_path} ({len(final_points)} points)")
    return {
        "POI_cleaned_polygon": poly_path,
        "POI_cleaned_point": pts_path,
        "poi_points_final_cleaned": final_path,
    }
