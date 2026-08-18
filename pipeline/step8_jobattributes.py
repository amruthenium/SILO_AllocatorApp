"""
Step 8: Generate jobAttributes — replaces TAZ_job_count.ipynb and add_attributes.py
"""
import os

import pandas as pd

from config import JOB_TYPE_LABELS


def _pivot_job_area(joblocation_csv, group_col):
    df = pd.read_csv(joblocation_csv)
    df["jobType"] = df["jobType"].map(lambda v: v if v in JOB_TYPE_LABELS else v)
    pivot = df.pivot_table(
        index=group_col, columns="jobType", values="job_percentage",
        aggfunc="sum", fill_value=0,
    )
    pivot.columns = [f"jobArea_{c}" for c in pivot.columns]
    return pivot.reset_index()


def run(joblocation_csv, gemeinde_population_csv, zone_attributes_csv, out_dir, log,
        gemeinde_col="gemeinde_ID"):
    log("Aggregating job area by TAZ zone...")
    by_zone = _pivot_job_area(joblocation_csv, "TAZ_ID")
    zone_xlsx = os.path.join(out_dir, "jobArea_by_zone.xlsx")
    by_zone.to_excel(zone_xlsx, index=False)
    log(f"  Wrote {zone_xlsx} ({len(by_zone)} zones)")

    log("Aggregating job area by gemeinde (municipality)...")
    by_gemeinde = _pivot_job_area(joblocation_csv, gemeinde_col)
    gemeinde_xlsx = os.path.join(out_dir, "jobArea_by_gemeinde.xlsx")
    by_gemeinde.to_excel(gemeinde_xlsx, index=False)
    log(f"  Wrote {gemeinde_xlsx} ({len(by_gemeinde)} municipalities)")

    log("Allocating municipality job population down to zones "
        "(pop_zone = pop_gemeinde * jobArea_zone / jobArea_gemeinde)...")
    zone_lookup = pd.read_csv(joblocation_csv)[["TAZ_ID", gemeinde_col]].drop_duplicates()
    by_zone_g = by_zone.merge(zone_lookup, on="TAZ_ID", how="left")

    pop = pd.read_csv(gemeinde_population_csv)  # columns: gemeinde_ID, jobPopulation_<type>...
    merged = by_zone_g.merge(by_gemeinde, on=gemeinde_col, suffixes=("_zone", "_gemeinde"))
    merged = merged.merge(pop, on=gemeinde_col, how="left")

    job_area_cols = [c for c in by_zone.columns if c.startswith("jobArea_")]
    for col in job_area_cols:
        jobtype = col.replace("jobArea_", "")
        zone_area_col = f"{col}_zone"
        gemeinde_area_col = f"{col}_gemeinde"
        pop_col = f"jobPopulation_{jobtype}"
        if pop_col not in merged.columns:
            log(f"  WARNING: no population column '{pop_col}' in "
                f"{os.path.basename(gemeinde_population_csv)} — skipping {jobtype}")
            continue
        ratio = merged[zone_area_col] / merged[gemeinde_area_col].replace(0, pd.NA)
        merged[f"jobPopulation_{jobtype}_zone"] = (merged[pop_col] * ratio).fillna(0)

    allocated_cols = ["TAZ_ID"] + [c for c in merged.columns if c.endswith("_zone") and c.startswith("jobPopulation_")]
    allocated = merged[allocated_cols]
    allocated_xlsx = os.path.join(out_dir, "job_by_zone_allocated.xlsx")
    allocated.to_excel(allocated_xlsx, index=False)
    log(f"  Wrote {allocated_xlsx}")

    log("Merging job population into the existing zone attributes table...")
    zone_attrs = pd.read_csv(zone_attributes_csv)
    final = zone_attrs.merge(allocated, on="TAZ_ID", how="left")
    final_csv = os.path.join(out_dir, "all_zone_with_jobs.csv")
    final.to_csv(final_csv, index=False)
    log(f"Wrote FINAL RESULT: {final_csv} ({len(final)} zones)")

    return {
        "jobArea_by_zone": zone_xlsx,
        "jobArea_by_gemeinde": gemeinde_xlsx,
        "job_by_zone_allocated": allocated_xlsx,
        "all_zone_with_jobs": final_csv,
    }
