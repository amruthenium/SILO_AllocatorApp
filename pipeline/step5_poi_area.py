"""
Step 5: POIPoints Area calculation — replaces POI_all/poi_area_towerchange.ipynb
"""
import os

import geopandas as gpd
import pandas as pd

from config import DIRS, FCLASS_REMAP, TARGET_CRS

def _detect_layers(gpkg_path, log):
    """Autodetect the points and polygons layers in a GPKG file, if possible."""
    info = gpd.list_layers(gpkg_path)
    log(f"Detected layers in {os.path.basename(gpkg_path)}: {info}"
        f"{list(zip(info['name'], info['geometry_type']))}")

    points_layer = None
    polygons_layer = None
    for _, row in info.iterrows():
        gtype = str(row["geometry_type"] or "").lower()
        if "point" in gtype and points_layer is None:
            points_layer = row["name"]
        elif "polygon" in gtype and polygons_layer is None:
            polygons_layer = row["name"]

    if points_layer is None or polygons_layer is None:
        raise ValueError(
            f"Could not autodetect points and polygons layers in {gpkg_path} — "
            f"{os.path.basename(gpkg_path)} has layers: {info['name'].tolist()}, geometry types: {info['geometry_type'].tolist()}. "
            f"found: {info}"
        )
    log(f"Using '{points_layer}' as points layer, '{polygons_layer}' as polygons layer")
    return points_layer, polygons_layer

def _prepare_layer(gpkg_path, layer, percentage_csv, log):
    gdf = gpd.read_file(gpkg_path, layer=layer) 
    perc = pd.read_csv(percentage_csv)
    id_col = next(
        (c for c in ["osm_id", "osm_id_poi"] if c in gdf.columns and c in perc.columns),
        None
    )
    if id_col is None:
        raise ValueError(
            f"Could not find a common ID column between {gpkg_path} layer '{layer}' "
            f"and {percentage_csv}. Found columns in GPKG: {gdf.columns.tolist()}, "
            f"found columns in CSV: {perc.columns.tolist()}"
        )
    log(f" Joining layer '{layer}' from {gpkg_path} with {percentage_csv} on ID column '{id_col}'")
    gdf[id_col] = gdf[id_col].astype(str)
    perc[id_col] = perc[id_col].astype(str)
    log(f"  percentage csv columns available: {list(perc.columns)}")
    extra_cols = [c for c in ["TAZ_ID"] if c in perc.columns]
    log(f"  pulling extra columns into geometry layer: {extra_cols}")
    merge_cols = [id_col] + extra_cols + ["jobType", "job_percentage"]
    gdf = gdf.merge(perc[merge_cols], on=id_col, how="inner")
    log(f"  columns after merge: {list(gdf.columns)}")
    return gdf.to_crs(TARGET_CRS)

def _fclass_column(gdf):
    return next((c for c in ["fclass", "fclass_poi"] if c in gdf.columns), None)

def run(pois_all_gpkg, points_percentage_csv, polygons_percentage_csv, out_dir, log):
    points_layer, polygons_layer = _detect_layers(pois_all_gpkg, log)

    log("Loading + filtering POI points and polygons by percentage tables...")
    points = _prepare_layer(pois_all_gpkg, points_layer, points_percentage_csv, log)
    polygons = _prepare_layer(pois_all_gpkg, polygons_layer, polygons_percentage_csv, log)
    log(f"  {len(points)} points, {len(polygons)} polygons")


    points_fclass_col = _fclass_column(points)
    polygons_fclass_col = _fclass_column(polygons)
    if not points_fclass_col or not polygons_fclass_col:
            raise ValueError(
                f"Could not find a fclass column in points or polygons. "
                f"Points columns: {points.columns.tolist()}, "
                f"Polygons columns: {polygons.columns.tolist()}"
            )
    # Special case: use communications_tower for area assignment, keep
    # original fclass for everything else.
    
    points["fclass_for_area"] = points[points_fclass_col].replace(FCLASS_REMAP)
    polygons["fclass_for_area"] = polygons[polygons_fclass_col].replace(FCLASS_REMAP)
    polygons["area_m2"] = polygons.geometry.area

    log("Computing average polygon area by TAZ + fclass...")
    avg_by_taz = (
        polygons.groupby(["TAZ_ID", "fclass_for_area"])["area_m2"].mean().reset_index()
        .rename(columns={"area_m2": "avg_area_taz"})
    )
    ags_col = next((c for c in ["AGS", "gemeinde_ID"] if c in polygons.columns), None)
    if ags_col:
        log("Computing average polygon area by AGS/gemeinde + fclass...")
        avg_by_ags = (
            polygons.groupby([ags_col, "fclass_for_area"])["area_m2"].mean().reset_index()
            .rename(columns={"area_m2": "avg_area_ags"})
        )
    else:
        log("No AGS/gemeinde_ID column found — skipping the municipality-level "
            "averaging tier (falling straight from TAZ average to global average).")
        avg_by_ags = None
    log("Computing global average area by fclass...")
    avg_global = (
        polygons.groupby("fclass_for_area")["area_m2"].mean().reset_index()
        .rename(columns={"area_m2": "avg_area_global"})
    )

    points = points.merge(avg_by_taz, on=["TAZ_ID", "fclass_for_area"], how="left")
    if avg_by_ags is not None:
        points_ags_col = next((c for c in ["AGS", "gemeinde_ID"] if c in points.columns), None)
        points = points.merge(
            avg_by_ags, left_on=[points_ags_col, "fclass_for_area"],
            right_on=[ags_col, "fclass_for_area"], how="left",
        )
    else:
        points["avg_area_ags"] = pd.NA
    points = points.merge(avg_global, on="fclass_for_area", how="left")

    points["area_m2"] = (
        points["avg_area_taz"]
        .fillna(points["avg_area_ags"])
        .fillna(points["avg_area_global"])
    )
    missing = points["area_m2"].isna().sum()
    if missing:
        log(f"  WARNING: {missing} points still missing area after all fallbacks")

    out_path = os.path.join(out_dir, "poi_points_with_area_no_missing.gpkg")
    points.drop(columns=[c for c in ["avg_area_taz", "avg_area_ags", "avg_area_global"]
                         if c in points.columns]).to_file(out_path, driver="GPKG")
    log(f"Wrote {out_path} ({len(points)} points, {missing} still missing)")
    return {"poi_points_with_area_no_missing": out_path}
