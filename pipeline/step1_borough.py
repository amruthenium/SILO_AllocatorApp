"""Step 1: Borough — replaces add_borough_BBSR.ipynb"""
import geopandas as gpd

from config import TARGET_CRS


def assign_borough(zones_path, borough_path, out_path, log):
    log("Reading TAZ zones...")
    zones = gpd.read_file(zones_path)
    log(f"  {len(zones)} zones loaded, CRS={zones.crs}")

    log("Reading borough boundaries...")
    boroughs = gpd.read_file(borough_path)
    log(f"  {len(boroughs)} boroughs loaded, CRS={boroughs.crs}")

    zones = zones.to_crs(TARGET_CRS)
    boroughs = boroughs.to_crs(TARGET_CRS)

    log("Joining zone centroids to borough polygons...")
    centroids = zones.copy()
    centroids["geometry"] = centroids.geometry.centroid

    # Prefix every borough attribute column so it can never clash with a
    # column of the same name in the zones file (e.g. both having OBJECTID_1).
    borough_attrs = boroughs.rename(
        columns={c: f"borough_{c}" for c in boroughs.columns if c != "geometry"}
    )
    borough_col = [c for c in borough_attrs.columns if c != "geometry"]

    joined = gpd.sjoin(centroids, borough_attrs, how="left", predicate="within")
    zones = zones.merge(
        joined[["index_right"] + borough_col].reset_index()[["index"] + borough_col],
        left_index=True, right_on="index", how="left",
    ).drop(columns=["index"])

    zones.to_file(out_path, driver="GPKG")
    log(f"Wrote {out_path} ({len(zones)} zones with borough attributes).")
    return out_path