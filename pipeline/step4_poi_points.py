"""Step 4: POI points — replaces catch_PY/node_all.py + QGIS point-in-polygon join."""
import os

import geopandas as gpd
import pandas as pd

from config import DIRS, TARGET_CRS
from pipeline import geo_utils

def run(bbox, keys, zones_path, jobtype_map_csv, out_dir, log, poi_file=None):
    if poi_file:
        log(f"Loading POI polygons from uploaded file:  {os.path.basename(poi_file)}")
        poi = gpd.read_file(poi_file)
        log(f"  {len(poi)} POI polygon features loaded, CRS={poi.crs}")
        raw_path = os.path.join(DIRS["catch_py"], "poi_polygons_geofabrik_new.gpkg")
        if len(poi):
            poi.to_file(raw_path, driver="GPKG")

    log("Joining TAZ_ID / gemeinde_ID to each point...")
    zones = gpd.read_file(zones_path).to_crs(TARGET_CRS)
    poi = poi.to_crs(TARGET_CRS) if len(poi) else poi
    extra_cols = [c for c in ["gemeinde_ID", "AGS"] if c in zones.columns]
    joined = geo_utils.spatial_join_point_in_polygon(
        poi, zones, zone_id_col="TAZ_ID", extra_cols=extra_cols
    )

    taz_csv = os.path.join(DIRS["poi_points"], "Poi2022_TAZ.csv")
    joined.drop(columns="geometry").to_csv(taz_csv, index=False)
    log(f"  Wrote {taz_csv}")

    log("Adding jobType and job percentage...")
    jobtype_map = pd.read_csv(jobtype_map_csv)
    key_cols = [c for c in jobtype_map["osm_key"].unique() if c in joined.columns]
    merged = joined.copy()
    merged["_tag_value"] = None
    for k in key_cols:
        merged["_tag_value"] = merged["_tag_value"].fillna(merged[k])
    merged = merged.merge(jobtype_map, left_on="_tag_value", right_on="osm_value", how="left")
    with_jobtype = merged[merged["jobType"].notna()].copy()
    zone_counts = with_jobtype.groupby("TAZ_ID").size().reset_index(name="zone_poi_count")
    with_jobtype = with_jobtype.merge(zone_counts, on="TAZ_ID")
    with_jobtype["job_percentage"] = 1.0 / with_jobtype["zone_poi_count"]

    out_csv = os.path.join(out_dir, "Poi_percentage_all.csv")
    with_jobtype.drop(columns="geometry").to_csv(out_csv, index=False)
    log(f"  Wrote {out_csv} ({len(with_jobtype)} rows with jobType)")
    return {"Poi_percentage_all": out_csv, "Poi2022_TAZ": taz_csv}
