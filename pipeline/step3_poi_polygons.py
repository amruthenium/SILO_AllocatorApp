"""
Step 3: POI polygons — replaces catch_PY/PoiPoly_all.py and the QGIS
fix-geometries/intersection/export steps in the notes.
"""
import os

import pandas as pd

from config import DIRS, TARGET_CRS
from pipeline import geo_utils, ohsome_client


def run(bbox, keys, zones_path, jobtype_map_csv, out_dir, log):
    log("Fetching POI polygons from ohsome API...")
    poi = ohsome_client.fetch_poi_polygons(bbox, keys)
    log(f"  {len(poi)} POI polygon features")
    raw_path = os.path.join(DIRS["catch_py"], "poi_polygons_ohsome_new.gpkg")
    if len(poi):
        poi.to_file(raw_path, driver="GPKG")

    log("Fixing geometries and splitting polygons across zone boundaries...")
    zones = __import__("geopandas").read_file(zones_path).to_crs(TARGET_CRS)
    poi = poi.to_crs(TARGET_CRS) if len(poi) else poi
    extra_cols = [c for c in ["gemeinde_ID", "AGS"] if c in zones.columns]
    split = geo_utils.intersection_split(poi, zones, zone_id_col="TAZ_ID", extra_cols=extra_cols)
    log(f"  {len(split)} rows after intersection split")

    taz_csv = os.path.join(DIRS["poipoly"], "PoiPoly_TAZ.csv")
    split.drop(columns="geometry").to_csv(taz_csv, index=False)
    log(f"  Wrote {taz_csv}")

    log("Adding jobType and job percentage...")
    jobtype_map = pd.read_csv(jobtype_map_csv)  # columns: osm_key, osm_value, jobType
    key_cols = [c for c in jobtype_map["osm_key"].unique() if c in split.columns]
    merged = split.copy()
    merged["_tag_value"] = None
    for k in key_cols:
        merged["_tag_value"] = merged["_tag_value"].fillna(merged[k])
    merged = merged.merge(
        jobtype_map, left_on="_tag_value", right_on="osm_value", how="left"
    )
    with_jobtype = merged[merged["jobType"].notna()].copy()
    with_jobtype["area_m2"] = with_jobtype.geometry.area
    zone_totals = with_jobtype.groupby("TAZ_ID")["area_m2"].sum().reset_index(
        name="zone_poi_area"
    )
    with_jobtype = with_jobtype.merge(zone_totals, on="TAZ_ID")
    with_jobtype["job_percentage"] = with_jobtype["area_m2"] / with_jobtype["zone_poi_area"]

    out_csv = os.path.join(out_dir, "PoiPoly_percentage_all.csv")
    with_jobtype.drop(columns="geometry").to_csv(out_csv, index=False)
    log(f"  Wrote {out_csv} ({len(with_jobtype)} rows with jobType)")
    return {"PoiPoly_percentage_all": out_csv, "PoiPoly_TAZ": taz_csv}
