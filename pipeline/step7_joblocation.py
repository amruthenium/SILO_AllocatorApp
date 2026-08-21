"""Step 7: Generate jobLocation — replaces jobLocation/JobLocation_generate.py"""
import os

import geopandas as gpd
import pandas as pd

from config import TARGET_CRS
from pipeline import geo_utils


def run(poi_points_final_gpkg, poi_polygons_gpkg, landuse_building_job_gpkg, out_dir, log):
    log("Loading source layers...")
    points = gpd.read_file(poi_points_final_gpkg).to_crs(TARGET_CRS)
    polygons = gpd.read_file(poi_polygons_gpkg).to_crs(TARGET_CRS)
    buildings = gpd.read_file(landuse_building_job_gpkg).to_crs(TARGET_CRS)

    log("Computing centroids for polygon-based job elements...")
    polygons_c = geo_utils.centroid_xy(polygons, TARGET_CRS)
    buildings_c = geo_utils.centroid_xy(buildings, TARGET_CRS)

    #Drop points that are duplicated as polygons (e.g. a POI built from a
    # buildings+points join, where every polygon originated from a point
    # that's still separately present here) — keep the polygon version,
    # since it carries real building-footprint area instead of Stage 5's
    # averaged-area guess.
    def _find_id_col(gdf, candidates=("osm_id", "osm_id_poi")):
        return next((c for c in candidates if c in gdf.columns), None)

    points_id_col = _find_id_col(points_xy)
    polygons_id_col = _find_id_col(polygons_c)
    if points_id_col and polygons_id_col:
        dup_ids = set(polygons_c[polygons_id_col].astype(str))
        before = len(points_xy)
        points_xy = points_xy[~points_xy[points_id_col].astype(str).isin(dup_ids)]
        log(f"  Dropped {before - len(points_xy)} point rows already represented "
            f"as a polygon (avoiding double-counting the same POI)")
    else:
        log("  WARNING: couldn't find matching ID columns on points/polygons to "
            "de-duplicate — skipping de-dup, double-counting may still be present")

    log("Combining points, POI polygons and building/landuse job elements...")
    common_cols = ["x", "y", "TAZ_ID", "jobType", "job_percentage"]
    frames = []
    for name, gdf in [("poi_point", points_xy), ("poi_polygon", polygons_c),
                       ("building_landuse", buildings_c)]:
        cols_present = [c for c in common_cols if c in gdf.columns]
        f = gdf[cols_present].copy()
        f["source"] = name
        frames.append(f)
    combined = pd.concat(frames, ignore_index=True, sort=False)

    before = len(combined)
    combined = combined.dropna(subset=["x", "y"])
    log(f"  Dropped {before - len(combined)} rows without x,y")

    combined.insert(0, "job_id", range(1, len(combined) + 1))
    out_csv = os.path.join(out_dir, "jobLocation.csv")
    combined.to_csv(out_csv, index=False)
    log(f"Wrote {out_csv} ({len(combined)} job elements, crs={TARGET_CRS})")
    return {"jobLocation": out_csv}
