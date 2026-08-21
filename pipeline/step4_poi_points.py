"""Step 4: POI points — replaces catch_PY/node_all.py + QGIS point-in-polygon join."""
import os
from shlex import split

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
    jobtype_map = pd.read_csv(jobtype_map_csv)  # columns: osm_key, osm_value, jobType
    STANDARD_POI_KEYS = ["shop", "amenity", "office", "tourism", "leisure",
                             "building", "landuse"]
    fallback_keys = list(dict.fromkeys(list(keys or []) + STANDARD_POI_KEYS))
    fclass_col = next((c for c in ["fclass", "fclass_poi"] if c in joined.columns), None)
    
    if fclass_col:
            log(f"  Detected a single '{fclass_col}' column on the POI data (Geofabrik-style) "
                "— matching jobType by fclass")
            mapping = jobtype_map[["osm_value", "jobType"]].drop_duplicates()
            merged = joined.merge(mapping, left_on=fclass_col, right_on="osm_value", how="left")
    else:
            if "osm_key" in jobtype_map.columns:
                candidate_keys = jobtype_map["osm_key"].unique().tolist()
                log("Using multi-column ohsome-style matching via jobtype_mapping.csv's osm_key")
            else:
                candidate_keys = fallback_keys
                log("jobtype_mapping.csv has no osm_key column — scanning the OSM keys "
                    f"used for this fetch plus standard POI keys: {candidate_keys}")
    
            key_cols =[c for c in candidate_keys if c in joined.columns]
            if not key_cols:
                raise ValueError(
                    "Could not tell how to match jobtype_mapping.csv to your POI data -"
                    f"none of the expected OSM keys {candidate_keys} were found in the POI data"
                    f"({candidate_keys}  were found in the fetched POI data)"
                )
            log(f"Matching using columns: {key_cols}")
            merged = joined.copy()
            merged["_tag_value"] = None
            for k in key_cols:
                merged["_tag_value"] = merged["_tag_value"].fillna(merged[k])
            mapping = jobtype_map[["osm_value", "jobType"]].drop_duplicates()
            merged = merged.merge(mapping, left_on="_tag_value", right_on="osm_value", how="left")
    merged = merged.merge(jobtype_map, left_on="_tag_value", right_on="osm_value", how="left")
    with_jobtype = merged[merged["jobType"].notna()].copy()
    zone_counts = with_jobtype.groupby("TAZ_ID").size().reset_index(name="zone_poi_count")
    with_jobtype = with_jobtype.merge(zone_counts, on="TAZ_ID")
    with_jobtype["job_percentage"] = 1.0 / with_jobtype["zone_poi_count"]

    out_csv = os.path.join(out_dir, "Poi_percentage_all.csv")
    with_jobtype.drop(columns="geometry").to_csv(out_csv, index=False)
    log(f"  Wrote {out_csv} ({len(with_jobtype)} rows with jobType)")
    return {"Poi_percentage_all": out_csv, "Poi2022_TAZ": taz_csv}
