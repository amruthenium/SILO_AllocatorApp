"""
Step 2: Buildings — replaces catch_PY/building_osm.py,
building_2022/merge_landuse_building.ipynb and building_2022/building_process.ipynb
"""
import os

import geopandas as gpd
import pandas as pd

from config import DIRS, TARGET_CRS,WGS84
from pipeline import geo_utils, ohsome_client


def run(bbox, zones_path, landuse_type_csv, out_dir, log,
        buildings_file=None, landuse_file=None):
    # 2.1 grab buildings + landuse via ohsome API, or load them from files
    # you supply yourself if the ohsome fetch isn't reachable.
    if buildings_file:
        log(f"Loading buildings from uploaded file: {os.path.basename(buildings_file)}")
        buildings = gpd.read_file(buildings_file)
        if buildings.crs is None:
            log("  No CRS found in file — assuming EPSG:4326 (WGS84).")
            buildings = buildings.set_crs(WGS84)
        log(f"  {len(buildings)} building features loaded")
    else:
        log("Fetching buildings from ohsome API...")
        buildings = ohsome_client.fetch_buildings(bbox)
        log(f"  {len(buildings)} building features")

    if landuse_file:
        log(f"Loading landuse from uploaded file: {os.path.basename(landuse_file)}")
        landuse = gpd.read_file(landuse_file)
        if landuse.crs is None:
            log("  No CRS found in file — assuming EPSG:4326 (WGS84).")
            landuse = landuse.set_crs(WGS84)
        log(f"  {len(landuse)} landuse features loaded")
    else:
        log("Fetching landuse from ohsome API...")
        landuse = ohsome_client.fetch_landuse(bbox)
        log(f"  {len(landuse)} landuse features")

    buildings_path = os.path.join(DIRS["catch_py"], "building_osm.gpkg")
    landuse_path = os.path.join(DIRS["catch_py"], "landuse_osm.gpkg")
    if len(buildings):
        buildings.to_file(buildings_path, driver="GPKG")
    if len(landuse):
        landuse.to_file(landuse_path, driver="GPKG")

    # 2.2 delete buildings overlapping landuse (QGIS difference)
    log("Removing buildings that overlap landuse polygons...")
    if len(buildings) and len(landuse):
        buildings_clean = geo_utils.difference(buildings, landuse, crs=TARGET_CRS)
    else:
        buildings_clean = buildings.to_crs(TARGET_CRS) if len(buildings) else buildings
    log(f"  {len(buildings_clean)} buildings remain after difference")

   # 2.3 merge landuse + building into one table. Each layer can label its
    # raw OSM-style tag value under a different column depending on where
    # the file came from — Geofabrik-style exports use fclass/type instead
    # of ohsome's landuse=/building= naming. Landuse's real category lives
    # in fclass; buildings' fclass is just the constant word "building", so
    # for buildings we need type instead (fclass as a last-resort fallback).
    log("Merging landuse and building layers...")
    landuse_c = landuse.to_crs(TARGET_CRS) if len(landuse) else landuse

    def _first_present(gdf, candidates):
        for c in candidates:
            if c in gdf.columns:
                return c
        return None

    landuse_tag_col = _first_present(landuse_c, ["landuse", "fclass", "type", "code"])
    log(f"  Using '{landuse_tag_col}' as the landuse layer's tag-value column")
    landuse_c = landuse_c.assign(
        raw_type_value=landuse_c[landuse_tag_col] if landuse_tag_col else None
    )

    building_tag_col = _first_present(buildings_clean, ["building", "type", "fclass", "code"])
    log(f"  Using '{building_tag_col}' as the building layer's tag-value column")
    buildings_clean = buildings_clean.assign(
        raw_type_value=buildings_clean[building_tag_col] if building_tag_col else None
    )

    combined = pd.concat(
        [landuse_c.assign(source="landuse"), buildings_clean.assign(source="building")],
        ignore_index=True,
    )
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=TARGET_CRS)
    combined["area_m2"] = combined.geometry.area
    combined_path = os.path.join(out_dir, "combined_landuse_building.gpkg")
    combined.to_file(combined_path, driver="GPKG")
    log(f"  Wrote {combined_path} ({len(combined)} rows)")

    # 2.4 filter by type using landuse_type.csv mapping (manually curated)
    log("Applying landuse_type.csv classification...")
    type_map = pd.read_csv(landuse_type_csv)
    # Expect columns: osm_value, type (1-10) [+ optional description].
    # Rename to names that can't collide with anything already present in
    # your source file (e.g. Geofabrik-style shapefiles already ship their
    # own "type"/"fclass" columns) — otherwise pandas silently suffixes
    # both to type_x/type_y on a name clash and "type" stops existing.
    type_map = type_map.rename(
        columns={"osm_value": "_map_osm_value", "type": "_map_job_type"}
    )
   
    merged = combined.merge(
        type_map, left_on="raw_type_value", right_on="_map_osm_value", how="left"
    )
    filtered = merged[merged["_map_job_type"].notna()].copy()
    filtered = filtered.drop(columns=["type"], errors="ignore").rename(
        columns={"_map_job_type": "type"}
    )
    filtered_csv = os.path.join(out_dir, "building_landuse2022.csv")
    filtered.drop(columns="geometry").to_csv(filtered_csv, index=False)
    log(f"  Wrote {filtered_csv} ({len(filtered)} classified rows)")

    # Report what landuse_type.csv is missing, ranked by how much area it
    # actually costs you — so you extend the mapping by impact, not by
    # scrolling through every unfamiliar tag value.
    unmatched = merged[merged["_map_job_type"].isna()].copy()
    if len(unmatched):
        unmatched["raw_type_value"] = unmatched["raw_type_value"].fillna("(no tag)")
        gap = (
            unmatched.groupby("raw_type_value")
            .agg(area_m2=("area_m2", "sum"), count=("raw_type_value", "size"))
            .sort_values("area_m2", ascending=False)
        )
        gap_csv = os.path.join(out_dir, "unclassified_landuse_values.csv")
        gap.reset_index().to_csv(gap_csv, index=False)
        total_gap_area = gap["area_m2"].sum()
        log(f"  {len(gap)} raw values unmatched in landuse_type.csv, covering "
            f"{total_gap_area:,.0f} m² across {len(unmatched)} features")
        log(f"  Full breakdown written to {gap_csv} — top 15 by area:")
        for value, row in gap.head(15).iterrows():
            log(f"    {value:<30s} {row['area_m2']:>12,.0f} m²  ({int(row['count'])} features)")
    else:
        log("  Every raw landuse/building value matched a row in landuse_type.csv.")

    # 2.5 add type(1-10), job percentage + area, spatial join to TAZ
    log("Computing area and job percentage per zone...")
    zones = gpd.read_file(zones_path)
    if zones.crs is None:
        raise ValueError(
            "TAZ zones file has no CRS defined — you likely selected the .shp "
            "without its .prj sidecar. Re-select ALL shapefile parts (.shp, "
            ".shx, .dbf, .prj) together and re-run this stage."
        )
    zones = zones.to_crs(TARGET_CRS)
    filtered_gdf = gpd.GeoDataFrame(filtered, geometry="geometry", crs=TARGET_CRS)
    filtered_gdf["area_m2"] = filtered_gdf.geometry.area
    joined = geo_utils.intersection_split(filtered_gdf, zones, zone_id_col="TAZ_ID")
    joined["area_m2"] = joined.geometry.area
    zone_type_area = joined.groupby(["TAZ_ID", "type"])["area_m2"].sum().reset_index()
    zone_total = joined.groupby("TAZ_ID")["area_m2"].sum().reset_index(name="zone_total_area")
    zone_type_area = zone_type_area.merge(zone_total, on="TAZ_ID")
    zone_type_area["job_percentage"] = (
        zone_type_area["area_m2"] / zone_type_area["zone_total_area"]
    )

    all_csv = os.path.join(out_dir, "building_landuse_all.csv")
    zone_type_area.to_csv(all_csv, index=False)
    log(f"  Wrote {all_csv}")

    job_gpkg = os.path.join(out_dir, "landuse_building_job2022.gpkg")
    joined.to_file(job_gpkg, driver="GPKG")
    log(f"  Wrote {job_gpkg}")

    outputs = {"building_landuse_all": all_csv, "landuse_building_job2022": job_gpkg}
    if len(unmatched):
        outputs["unclassified_landuse_values"] = gap_csv
    return outputs