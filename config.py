"""
Central configuration for the Zone Attribute pipeline.

Adjust OHSOME_BASE / TARGET_CRS / paths for your own setup. All paths are
relative to the project root and mirror the original folder layout described
in the workflow notes (catch_PY, building_2022, PoiPoly, poi_points, POI_all,
jobLocation, jobAttribution).
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
LOG_DIR = os.path.join(BASE_DIR, "logs")

DIRS = {
    "catch_py": os.path.join(DATA_DIR, "catch_PY"),
    "building_2022": os.path.join(DATA_DIR, "building_2022"),
    "poipoly": os.path.join(DATA_DIR, "PoiPoly"),
    "poi_points": os.path.join(DATA_DIR, "poi_points"),
    "poi_all": os.path.join(DATA_DIR, "POI_all"),
    "joblocation": os.path.join(DATA_DIR, "jobLocation"),
    "jobattribution": os.path.join(DATA_DIR, "jobAttribution"),
}

for d in list(DIRS.values()) + [UPLOAD_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

# Working CRS used throughout the pipeline for area/distance calculations.
# EPSG:31468 = DHDN / Gauss-Kruger zone 4 (matches the original TAZ data).
# Override per-run from the UI if your zones use a different CRS.
TARGET_CRS = "EPSG:31468"
WGS84 = "EPSG:4326"

# ohsome API (https://api.ohsome.org) — used to replace the manual
# "grab buildings/landuse/POIs via ohsome API" steps.
OHSOME_BASE = "https://api.ohsome.org/v1"
OHSOME_TIME = "2022-12-31"

# Job type classes 1-10, matching "based on the 2011 types" in the notes.
# Edit JOB_TYPE_LABELS / default percentages to match your landuse_type.csv.
JOB_TYPE_LABELS = {
    1: "retail",
    2: "office",
    3: "industry",
    4: "education",
    5: "health",
    6: "public_admin",
    7: "leisure_culture",
    8: "hospitality",
    9: "logistics",
    10: "other_services",
}

# Special-case fclass remap used in the POI area step.
FCLASS_REMAP = {
    "observation_tower": "communications_tower",
}
