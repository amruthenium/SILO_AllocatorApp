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


def _prepare_layer(gpkg_path, layer, percentage_csv, id_col="osm_id"):
    gdf = gpd.read_file(gpkg_path, layer=layer) if layer else gpd.read_file(gpkg_path)
    perc = pd.read_csv(percentage_csv)
    gdf = gdf.merge(perc[[id_col, "jobType", "job_percentage"]], on=id_col, how="inner")
    return gdf.to_crs(TARGET_CRS)

def run(pois_all_gpkg, points_percentage_csv, polygons_percentage_csv, out_dir, log,
        points_layer="points", polygons_layer="polygons", fclass_col="fclass"):
    log("Loading + filtering POI points and polygons by percentage tables...")
    points = {os.path.basename(pois_all_gpkg): _prepare_layer(pois_all_gpkg, points_layer, points_percentage_csv)}
    #points = _prepare_layer(pois_all_gpkg, points_layer, points_percentage_csv)
    polygons = {os.path.basename(pois_all_gpkg):_prepare_layer(pois_all_gpkg, polygons_layer, polygons_percentage_csv)}
    log(f"  {len(points)} points, {len(polygons)} polygons")

    # Special case: use communications_tower for area assignment, keep
    # original fclass for everything else.
    points["fclass_for_area"] = points[fclass_col].replace(FCLASS_REMAP)
    polygons["fclass_for_area"] = polygons[fclass_col].replace(FCLASS_REMAP)

    polygons["area_m2"] = polygons.geometry.area

    log("Computing average polygon area by TAZ + fclass...")
    avg_by_taz = (
        polygons.groupby(["TAZ_ID", "fclass_for_area"])["area_m2"].mean().reset_index()
        .rename(columns={"area_m2": "avg_area_taz"})
    )
    log("Computing average polygon area by AGS/gemeinde + fclass...")
    ags_col = "AGS" if "AGS" in polygons.columns else "gemeinde_ID"
    avg_by_ags = (
        polygons.groupby([ags_col, "fclass_for_area"])["area_m2"].mean().reset_index()
        .rename(columns={"area_m2": "avg_area_ags"})
    )
    log("Computing global average area by fclass...")
    avg_global = (
        polygons.groupby("fclass_for_area")["area_m2"].mean().reset_index()
        .rename(columns={"area_m2": "avg_area_global"})
    )

    points = points.merge(avg_by_taz, on=["TAZ_ID", "fclass_for_area"], how="left")
    points_ags_col = "AGS" if "AGS" in points.columns else "gemeinde_ID"
    points = points.merge(
        avg_by_ags, left_on=[points_ags_col, "fclass_for_area"],
        right_on=[ags_col, "fclass_for_area"], how="left",
    )
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
