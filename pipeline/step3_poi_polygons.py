"""
Step 3: POI polygons — replaces catch_PY/PoiPoly_all.py and the QGIS
fix-geometries/intersection/export steps in the notes.
"""
import os

import pandas as pd
import geopandas as gpd

from config import DIRS, TARGET_CRS, WGS84
from pipeline import geo_utils


def run(bbox, keys, zones_path, jobtype_map_csv, out_dir, log, poi_file=None):
 if poi_file:
    log(f"Loading POI polygons from uploaded file:  {os.path.basename(poi_file)}")
    poi = gpd.read_file(poi_file)
    log(f"  {len(poi)} POI polygon features loaded, CRS={poi.crs}")
    raw_path = os.path.join(DIRS["catch_py"], "poi_polygons_geofabrik_new.gpkg")
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
    STANDARD_POI_KEYS = ["shop", "amenity", "office", "tourism", "leisure",
                         "building", "landuse"]
    fallback_keys = list(dict.fromkeys(list(keys or []) + STANDARD_POI_KEYS))
    fclass_col = next((c for c in ["fclass", "fclass_poi"] if c in split.columns), None)

    if fclass_col in split.columns:
        log(f"  Detected a single '{fclass_col}' column on the POI data (Geofabrik-style) "
            "— matching jobType by fclass")
        mapping = jobtype_map[["osm_value", "jobType"]].drop_duplicates()
        merged = split.merge(mapping, left_on=fclass_col, right_on="osm_value", how="left")
    else:
        if "osm_key" in jobtype_map.columns:
            candidate_keys = jobtype_map["osm_key"].unique().tolist()
            log("Using multi-column ohsome-style matching via jobtype_mapping.csv's osm_key")
        else:
            candidate_keys = fallback_keys
            log("jobtype_mapping.csv has no osm_key column — scanning the OSM keys "
                f"used for this fetch plus standard POI keys: {candidate_keys}")

        key_cols =[c for c in candidate_keys if c in split.columns]
        if not key_cols:
            raise ValueError(
                "Could not tell how to match jobtype_mapping.csv to your POI data -"
                f"none of the expected OSM keys {candidate_keys} were found in the POI data"
                f"({candidate_keys}  were found in the fetched POI data)"
            )
        log(f"Matching using columns: {key_cols}")
        merged = split.copy()
        merged["_tag_value"] = None
        for k in key_cols:
            merged["_tag_value"] = merged["_tag_value"].fillna(merged[k])
        mapping = jobtype_map[["osm_value", "jobType"]].drop_duplicates()
        merged = merged.merge(mapping, left_on="_tag_value", right_on="osm_value", how="left")
    
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
