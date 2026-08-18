import os
import threading
import traceback
import uuid

from flask import Flask, jsonify, request, render_template, send_file

from config import DIRS, UPLOAD_DIR

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()


def new_job():
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "log": [], "outputs": None, "error": None}
    return job_id


def make_logger(job_id):
    def log(msg):
        with JOBS_LOCK:
            JOBS[job_id]["log"].append(str(msg))
    return log


def run_in_background(job_id, target, *args, **kwargs):
    def wrapper():
        log = make_logger(job_id)
        try:
            outputs = target(*args, log=log, **kwargs)
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["outputs"] = outputs
        except Exception as e:
            log(f"ERROR: {e}")
            log(traceback.format_exc())
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)
    t = threading.Thread(target=wrapper, daemon=True)
    t.start()


@app.route("/")
def index():
    return render_template("index.html")

VECTOR_PRIMARY_ORDER = [".gpkg", "geojson", ".json", ".shp"]

@app.route("/api/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no file recieved"}), 400

    # Give each upload its own folder so a shapefile's .shp/.shx/.dbf/.prj
    # sidecars land next to each other (GDAL needs them in the same dir).
    batch_dir = os.path.join(UPLOAD_DIR, uuid.uuid4().hex[:10])
    os.makedirs(batch_dir, exist_ok=True)

    saved = []
    for f in files:
        dest = os.path.join(batch_dir, f.filename)
        f.save(dest)
        saved.append((f.filename, dest))

         # Pick the file geopandas should actually be pointed at.
    primary = None
    for ext in VECTOR_PRIMARY_ORDER:
        match = next((p for n, p in saved if n.lower().endswith(ext)), None)
        if match:
            primary = match
            break
    if primary is None:
        primary = saved[0][1]  # e.g. a lone .csv

    required_shp_sidecars = {".shx", ".dbf"}
    if primary.lower().endswith(".shp"):
        present = {os.path.splitext(n)[1].lower() for n, _ in saved}
        missing = required_shp_sidecars - present
        if missing:
            return jsonify({
                "error": f"missing {', '.join(sorted(missing))} for the .shp "
                          f"you selected — pick the .shp together with its sidecar files"
            }), 400

    return jsonify({"path": primary, "name": os.path.basename(primary)})


@app.route("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        return jsonify(job)


@app.route("/api/download")
def download():
    path = request.args.get("path")
    if not path or not os.path.isfile(path):
        return jsonify({"error": "file not found"}), 404
    return send_file(path, as_attachment=True)


# ---------------------------------------------------------------- step 1
@app.route("/api/step/1", methods=["POST"])
def step1():
    from pipeline.step1_borough import assign_borough
    d = request.json
    out_path = os.path.join(DIRS["catch_py"], "zones_with_borough.gpkg")
    job_id = new_job()
    run_in_background(job_id, assign_borough, d["zones_path"], d["borough_path"], out_path)
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 2
@app.route("/api/step/2", methods=["POST"])
def step2():
    from pipeline.step2_buildings import run as step_run
    d = request.json
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["bbox"], d["zones_path"], d["landuse_type_csv"],
        DIRS["building_2022"],
        buildings_file=d.get("buildings_file") or None,
        landuse_file=d.get("landuse_file") or None,
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 3
@app.route("/api/step/3", methods=["POST"])
def step3():
    from pipeline.step3_poi_polygons import run as step_run
    d = request.json
    keys = [k.strip() for k in d.get("keys", "").split(",") if k.strip()]
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["bbox"], keys, d["zones_path"], d["jobtype_map_csv"],
        DIRS["poipoly"],
        poi_file=d.get("poi_file") or None,
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 4
@app.route("/api/step/4", methods=["POST"])
def step4():
    from pipeline.step4_poi_points import run as step_run
    d = request.json
    keys = [k.strip() for k in d["keys"].split(",") if k.strip()]
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["bbox"], keys, d["zones_path"], d["jobtype_map_csv"],
        DIRS["poi_points"],
        poi_file=d.get("poi_file") or None,
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 5
@app.route("/api/step/5", methods=["POST"])
def step5():
    from pipeline.step5_poi_area import run as step_run
    d = request.json
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["pois_all_gpkg"], d["points_percentage_csv"],
        d["polygons_percentage_csv"], DIRS["poi_all"],
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 6
@app.route("/api/step/6", methods=["POST"])
def step6():
    from pipeline.step6_poi_clean import run as step_run
    d = request.json
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["poi_points_gpkg"], d["poi_polygons_gpkg"],
        d["landuse_building_job_gpkg"], DIRS["poi_all"],
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 7
@app.route("/api/step/7", methods=["POST"])
def step7():
    from pipeline.step7_joblocation import run as step_run
    d = request.json
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["poi_points_final_gpkg"], d["poi_polygons_gpkg"],
        d["landuse_building_job_gpkg"], DIRS["joblocation"],
    )
    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------- step 8
@app.route("/api/step/8", methods=["POST"])
def step8():
    from pipeline.step8_jobattributes import run as step_run
    d = request.json
    job_id = new_job()
    run_in_background(
        job_id, step_run, d["joblocation_csv"], d["gemeinde_population_csv"],
        d["zone_attributes_csv"], DIRS["jobattribution"],
    )
    return jsonify({"job_id": job_id})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
