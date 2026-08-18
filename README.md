# Zone Attribution Pipeline — Web App

A local Flask app that automates the job-location/zone-attribute workflow
described in the original field notes, replacing the manual QGIS steps
with `geopandas` and the OSM downloads with the [ohsome API](https://api.ohsome.org).

```
notes step                         → this app
---------------------------------------------------------------
add_borough_BBSR.ipynb              Stage 1  Borough
building_osm.py + merge + process   Stage 2  Buildings & Landuse
PoiPoly_all.py + QGIS intersection  Stage 3  POI polygons
node_all.py + QGIS join             Stage 4  POI points
poi_area_towerchange.ipynb          Stage 5  POI point area
QGIS difference + Clean_poi_points  Stage 6  Clean POIs
JobLocation_generate.py             Stage 7  jobLocation
TAZ_job_count + add_attributes.py   Stage 8  jobAttributes (final)
```

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

geopandas pulls in GDAL/Fiona/PROJ — on Windows the easiest path is
`conda install -c conda-forge geopandas` instead of pip if you hit
binary wheel issues.

## Run

```bash
python app.py
```

Open **http://127.0.0.1:5050**. Each of the 8 stages is a card: upload the
inputs it needs, hit **Run**, and watch the console. When a stage finishes,
its outputs appear as download chips — the same files the notes describe
(`landuse_building_job2022.gpkg`, `jobLocation.csv`,
`all_zone_with_jobs.csv`, etc.), written into `data/<folder>/` mirroring
the original directory layout (`catch_PY`, `building_2022`, `PoiPoly`,
`poi_points`, `POI_all`, `jobLocation`, `jobAttribution`).

Run stages in order — each one consumes outputs from an earlier stage (you
can also feed it files produced outside this app, e.g. still export
`PoiPoly_TAZ.csv` from QGIS yourself and only automate the rest).

## What you need to supply

These are project-specific and aren't guessable from the notes alone —
templates are in `data/` as `*.SAMPLE.csv`, copy and edit them:

- **TAZ zones file** (Stages 1–4): polygon layer with a `TAZ_ID` column
  (and ideally `gemeinde_ID`/`AGS`), any format geopandas reads
  (`.gpkg`/`.shp`/`.geojson`).
- **`landuse_type.csv`** (Stage 2): maps raw OSM `landuse`/`building`
  values to your 1–10 type codes. See
  `data/building_2022/landuse_type.SAMPLE.csv`.
- **jobtype mapping csv** (Stages 3–4): maps OSM key/value pairs to a
  `jobType` label. See `data/PoiPoly/jobtype_mapping.SAMPLE.csv`.
- **`POIS_all.gpkg`** (Stage 5): a geopackage with `points` and `polygons`
  layers (matching the notes' `POI_all` folder).
- **Municipality population csv** (Stage 8): one row per municipality with
  columns like `jobPopulation_retail`, `jobPopulation_office`, etc.
- **Existing zone attributes csv** (Stage 8): the attribute table you're
  appending job counts onto — needs a `TAZ_ID` column to join on.

## Configuration

Edit `config.py` for:

- `TARGET_CRS` — working CRS for area/join calculations (defaults to
  `EPSG:31468`, Gauss-Krüger zone 4 — change this if your zones use a
  different projection).
- `OHSOME_BASE` / `OHSOME_TIME` — ohsome API endpoint and snapshot date.
- `JOB_TYPE_LABELS` / `FCLASS_REMAP` — the 1–10 job type labels and the
  observation-tower → communications-tower special case from Stage 5.

## Notes on fidelity to the original workflow

- QGIS "Fix geometries", "Intersection" and "Difference" tools are
  replaced with `buffer(0)` + `geopandas.overlay` in `pipeline/geo_utils.py`
  — behaviour is equivalent but not byte-identical to QGIS's GEOS build.
  If a run produces topology errors on your data, that's the first place
  to look.
- Stage 2's job-percentage formula (area share of each type within a
  zone) and Stage 8's population-allocation formula
  (`pop_zone = pop_gemeinde * jobArea_zone / jobArea_gemeinde`) are coded
  exactly as described in the notes — adjust `pipeline/step2_buildings.py`
  / `pipeline/step8_jobattributes.py` if your actual definition differs.
- The app runs each stage in a background thread and polls status client
  side — safe for the single-user local/desktop use this is designed for,
  not hardened for multi-user deployment (no auth, no queueing).
