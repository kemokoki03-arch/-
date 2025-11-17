# -*- coding: utf-8 -*-
import os, uuid, threading, time, glob
from flask import Flask, render_template, request, jsonify, send_file, make_response
from flask_cors import CORS
import pandas as pd
from io import BytesIO, StringIO

from gcc_scraper import (
    run_job, JOBS, DEFAULT_KEYWORDS, GCC,
    state_path, load_state, save_state, UPLOADED_KEYWORDS, LOCK
)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = False
CORS(app)

# ---------------- Normalization helpers ----------------
def _to_float(v):
    try:
        return float(str(v).strip().replace(" ", "").replace(",", "."))
    except Exception:
        return None

def _pick_first(rec, keys):
    for k in keys:
        if k in rec and rec.get(k) not in (None, ""):
            return rec.get(k)
    return ""

def _norm_record(rec):
    # lat/lng (مع بدائل)
    lat = rec.get("lat")
    lng = rec.get("lng")
    if lat is None:
        lat = _pick_first(rec, ["latitude", "y", "lat_deg", "خط العرض"])
    if lng is None:
        lng = _pick_first(rec, ["lon", "longitude", "x", "long", "lng_deg", "خط الطول"])
    lat = _to_float(lat)
    lng = _to_float(lng)

    # name / service / country (مع بدائل)
    name = rec.get("name") or _pick_first(rec, ["اسم","title","place","label","business_name","store","poi_name"])
    service = rec.get("service") or _pick_first(rec, ["الخدمة","category","نوع الخدمة","type","class","classes","categories"])
    country = rec.get("country") or _pick_first(rec, ["الدولة","nation","country_name","country_code","cc"])

    out = dict(rec)
    if lat is not None: out["lat"] = lat
    if lng is not None: out["lng"] = lng
    if "name" not in out or not out["name"]: out["name"] = name
    if "service" not in out or not out["service"]: out["service"] = service
    if "country" not in out or not out["country"]: out["country"] = country
    return out
# -------------------------------------------------------

@app.route("/")
def index():
    countries = [{"code":k, "label":v["label"]} for k,v in GCC.items()]
    return render_template("index.html", countries=countries, defaults=",".join(DEFAULT_KEYWORDS))

@app.get("/meta")
def meta():
    return jsonify({
        "countries": [{"code":k, "label":v["label"]} for k,v in GCC.items()],
        "bounds": {k:v["bounds"] for k,v in GCC.items()}
    })

@app.post("/upload_keywords")
def upload_keywords():
    f = request.files.get("file")
    if not f: return jsonify({"error":"no file"}), 400
    text = f.read().decode("utf-8-sig", errors="ignore")
    rows = []
    for line in text.splitlines():
        v = line.strip().strip(",")
        if v: rows.append(v)
    UPLOADED_KEYWORDS.clear()
    UPLOADED_KEYWORDS.extend(rows)
    return jsonify({"ok":True, "count": len(rows)})

@app.post("/upload_areas_csv")
def upload_areas_csv():
    f = request.files.get("file")
    if not f: return jsonify({"error":"no file"}), 400
    data = f.read().decode("utf-8-sig", errors="ignore")
    return jsonify({"ok":True, "text": data, "count": len([x for x in data.splitlines() if x.strip()])})

# ------------------ upload_csv: add uploaded CSV rows ------------------
@app.post("/upload_csv")
def upload_csv():
    """
    POST multipart/form-data:
      - file: CSV file
      - optional form field job_id: attach rows to this job's data
    Returns:
      {"ok": True, "count": N, "features": FeatureCollection, "csv_path": path, "job_id": "...", "job_rows": M}
    """
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400

    job_id = request.form.get("job_id") or None

    # read bytes
    try:
        content = f.read()
    except Exception as e:
        return jsonify({"error": "failed to read file", "detail": str(e)}), 400

    # parse CSV robustly
    try:
        try:
            s = content.decode("utf-8-sig")
        except Exception:
            s = content.decode("utf-8", errors="ignore")
        df = pd.read_csv(StringIO(s))
    except Exception:
        try:
            df = pd.read_csv(BytesIO(content))
        except Exception as e:
            return jsonify({"error": "pandas could not parse CSV", "detail": str(e)}), 400

    if df.empty:
        return jsonify({"error": "empty csv"}), 400

    # detect lat/lng columns (case-insensitive + Arabic)
    cols_map = {str(c).lower(): c for c in df.columns}
    lat_col = None
    lng_col = None
    for candidate in ("lat", "latitude", "y", "latt", "lat_deg", "خط العرض"):
        if candidate.lower() in cols_map:
            lat_col = cols_map[candidate.lower()]; break
    for candidate in ("lng", "lon", "longitude", "x", "long", "lng_deg", "خط الطول"):
        if candidate.lower() in cols_map:
            lng_col = cols_map[candidate.lower()]; break

    if lat_col is None or lng_col is None:
        # substring matching
        for c in df.columns:
            cl = str(c).lower()
            if lat_col is None and ("lat" in cl or "العرض" in cl):
                lat_col = c
            if lng_col is None and ("lon" in cl or "lng" in cl or "long" in cl or "الطول" in cl):
                lng_col = c

    if lat_col is None or lng_col is None:
        return jsonify({"error": "could not detect latitude/longitude columns", "columns": list(df.columns)}), 400

    # helper to parse floats with Arabic comma
    def _to_float_maybe(v):
        if v is None: return None
        try:
            return float(str(v).strip().replace(" ", "").replace(",", "."))
        except Exception:
            return None

    # normalize rows + build GeoJSON
    rows_to_add = []
    features = []
    added = 0
    for _, row in df.iterrows():
        la = _to_float_maybe(row[lat_col])
        lo = _to_float_maybe(row[lng_col])
        if la is None or lo is None:
            continue
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            continue

        rec = {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
        rec["lat"] = float(la)
        rec["lng"] = float(lo)
        rows_to_add.append(rec)
        props = {k: v for k, v in rec.items() if k not in ("lat", "lng")}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [rec["lng"], rec["lat"]]},
            "properties": props
        })
        added += 1

    if added == 0:
        return jsonify({"error": "no valid lat/lng rows found"}), 400

    # save cleaned CSV to disk
    try:
        safe_name = f"uploaded_{int(time.time())}_{uuid.uuid4().hex[:6]}.csv"
        out_path = os.path.join(os.getcwd(), safe_name)
        try:
            out_df = pd.DataFrame(rows_to_add)
            out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        except Exception:
            open(out_path, "wb").write(content)
    except Exception:
        out_path = None

    job_rows = None

    # simple dedup key
    def _row_key(r):
        return f'{str(r.get("name",""))}|{str(r.get("lat",""))}|{str(r.get("lng",""))}'

    # ADD: precompute keys once for faster dedup
    pre_keys = [_row_key(r) for r in rows_to_add]

    # attach rows into JOBS with thread safety
    with LOCK:
        # hydrate job from state if needed
        if job_id and job_id not in JOBS:
            st = load_state(job_id)
            if st: JOBS[job_id] = st

        if job_id and job_id in JOBS:
            JOBS[job_id].setdefault("data", JOBS[job_id].get("data", []))
            existing_keys = {_row_key(r) for r in JOBS[job_id]["data"]}

            deduped = []
            for r, k in zip(rows_to_add, pre_keys):
                if k not in existing_keys:
                    deduped.append(r)
                    existing_keys.add(k)

            JOBS[job_id]["data"].extend(deduped)
            JOBS[job_id]["rows"] = len(JOBS[job_id]["data"])
            job_rows = JOBS[job_id]["rows"]

            # write merged CSV + save state
            try:
                csv_job = JOBS[job_id].get("csv")
                if csv_job:
                    pd.DataFrame(JOBS[job_id]["data"]).to_csv(csv_job, index=False, encoding="utf-8-sig")
            except Exception:
                pass
            try:
                dp = JOBS[job_id].get("done_points")
                if isinstance(dp, set):
                    JOBS[job_id]["done_points"] = list(dp)
                save_state(job_id)
                if isinstance(JOBS[job_id].get("done_points"), list):
                    JOBS[job_id]["done_points"] = set(JOBS[job_id]["done_points"])
            except Exception:
                pass
        else:
            up_key = "_uploaded_data_"
            JOBS.setdefault(up_key, {})
            JOBS[up_key].setdefault("data", [])
            existing_keys = {_row_key(r) for r in JOBS[up_key]["data"]}

            deduped = []
            for r, k in zip(rows_to_add, pre_keys):
                if k not in existing_keys:
                    deduped.append(r)
                    existing_keys.add(k)

            JOBS[up_key]["data"].extend(deduped)
            JOBS[up_key]["rows"] = len(JOBS[up_key]["data"])
            job_id = job_id or up_key  # علشان الواجهة تعرف ترجع الـ id في الرد

    return jsonify({
        "ok": True,
        "count": added,
        "features": { "type":"FeatureCollection", "features": features },
        "csv_path": out_path,
        "job_id": job_id,
        "job_rows": job_rows
    })

@app.get("/rows/uploaded.json")
def rows_uploaded():
    up = JOBS.get("_uploaded_data_", {}) or {}
    return jsonify(up.get("data", []))

# ---------------- Features GeoJSON (with CSV fallback) ----------------
@app.get("/features/<job_id>.geojson")
def features_geojson(job_id):
    job = JOBS.get(job_id) or load_state(job_id)
    if not job:
        return jsonify({"type":"FeatureCollection","features":[]})

    data = job.get("data", [])
    if not data:
        csv_path = job.get("csv")
        if csv_path and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            try:
                df = pd.read_csv(csv_path)
                data = df.to_dict(orient="records")
                with LOCK:
                    JOBS[job_id] = job
                    JOBS[job_id]["data"] = data
                    JOBS[job_id]["rows"] = len(data)
                    dp = JOBS[job_id].get("done_points")
                    if isinstance(dp, set): JOBS[job_id]["done_points"] = list(dp)
                    save_state(job_id)
                    if isinstance(JOBS[job_id].get("done_points"), list):
                        JOBS[job_id]["done_points"] = set(JOBS[job_id]["done_points"])
            except Exception:
                data = []

    feats = []
    for r in data:
        nr = _norm_record(r)
        lat = nr.get("lat"); lng = nr.get("lng")
        if lat is None or lng is None:
            continue
        props = {k:v for k,v in nr.items() if k not in ("lat","lng")}
        feats.append({
            "type":"Feature",
            "geometry":{"type":"Point","coordinates":[lng, lat]},
            "properties": props
        })
    return jsonify({"type":"FeatureCollection","features":feats})

# ---------------- Start/Pause/Resume ----------------
@app.post("/start")
def start():
    data = request.get_json(force=True)
    country   = data.get("country","UAE")
    keywords  = [k.strip() for k in str(data.get("keywords","")).split(",") if k.strip()]
    areas_txt = data.get("areas_text","")
    areas_csv = data.get("areas_csv_text","")
    if not keywords: keywords = DEFAULT_KEYWORDS
    step     = float(data.get("step", 0.25))
    headless = bool(data.get("headless", True))
    aggressive = bool(data.get("aggressive", False))
    workers  = int(data.get("workers", 3))
    zoom     = int(data.get("zoom", 15))
    show_tiles = bool(data.get("show_tiles", False))

    # ADD: optional limits for speed/quotas
    max_rows = int(data.get("max_rows", 0))             # 0 = no cap
    expected_total = int(data.get("expected_total", 0)) # for UI progress only

    job_id = data.get("job_id") or str(uuid.uuid4())[:8]
    out_csv = os.path.join(os.getcwd(), f"results_{country}_{job_id}.csv")

    # resume existing
    existing = load_state(job_id)
    if existing:
        JOBS[job_id] = existing
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["command"] = ""
        JOBS[job_id]["country"] = country
        JOBS[job_id]["keywords"] = keywords or existing.get("keywords", DEFAULT_KEYWORDS)
        JOBS[job_id]["step"] = step
        JOBS[job_id]["aggressive"] = aggressive
        JOBS[job_id]["workers"] = workers
        JOBS[job_id]["zoom"] = zoom
        JOBS[job_id]["show_tiles"] = show_tiles
        JOBS[job_id]["csv"] = existing.get("csv") or out_csv
        dp = JOBS[job_id].get("done_points", set())
        if isinstance(dp, list): dp = set(dp)
        JOBS[job_id]["done_points"] = dp

        # ADD: carry or set new caps
        JOBS[job_id]["max_rows"] = max_rows or existing.get("max_rows", 0)
        JOBS[job_id]["expected_total"] = expected_total or existing.get("expected_total", 0)
    else:
        # create empty state file if missing
        if not os.path.exists(state_path(job_id)):
            with open(state_path(job_id), "w", encoding="utf-8") as f: f.write("{}")
        # init
        JOBS[job_id] = {
            "status":"running","progress":0,"total":1,"rows":0,"csv":out_csv,
            "data":[], "country":country, "keywords":keywords, "step":step,
            "command":"", "aggressive":aggressive, "workers":workers, "zoom":zoom,
            "done_points": set(), "admin_sweep": True, "show_tiles": show_tiles,
            # ADD
            "max_rows": max_rows, "expected_total": expected_total
        }

    save_state(job_id)

    t = threading.Thread(
        target=run_job,
        args=(job_id, country, keywords, step, headless, JOBS[job_id]["csv"], areas_csv, areas_txt, aggressive, workers, zoom),
        daemon=True
    )
    t.start()
    return jsonify({"job_id": job_id, "country": country})

@app.post("/pause/<job_id>")
def pause(job_id):
    job = JOBS.get(job_id) or load_state(job_id)
    if not job: return jsonify({"error":"job not found"}), 404
    JOBS[job_id] = job; JOBS[job_id]["command"] = "pause"; JOBS[job_id]["status"] = "paused"
    save_state(job_id)
    return jsonify({"ok":True})

@app.post("/resume/<job_id>")
def resume(job_id):
    st = load_state(job_id)
    if not st: return jsonify({"error":"no state"}), 404
    country = st.get("country","UAE")
    keywords = st.get("keywords") or DEFAULT_KEYWORDS
    step = st.get("step", 0.25)
    headless = True
    aggressive = st.get("aggressive", False)
    workers = st.get("workers", 1)
    zoom = st.get("zoom", 15)
    out_csv = st.get("csv") or os.path.join(os.getcwd(), f"results_{country}_{job_id}.csv")
    t = threading.Thread(
        target=run_job,
        args=(job_id, country, keywords, step, headless, out_csv, "", st.get("areas",""), aggressive, workers, zoom),
        daemon=True
    )
    t.start()
    return jsonify({"ok":True, "job_id": job_id})

# ---------------- Adjust caps on the fly ----------------
@app.post("/set_expected")
def set_expected():
    data = request.get_json(force=True)
    job_id = data.get("job_id")
    if not job_id:
        return jsonify({"ok": False, "error":"missing job_id"}), 400
    expected = int(data.get("expected_total", 0))
    cap = int(data.get("max_rows", 0))
    with LOCK:
        job = JOBS.get(job_id) or load_state(job_id)
        if not job:
            return jsonify({"ok": False, "error":"job not found"}), 404
        job["expected_total"] = expected
        job["max_rows"] = cap
        JOBS[job_id] = job
        save_state(job_id)
    return jsonify({"ok": True, "expected_total": expected, "max_rows": cap})

# ---------------- Progress ----------------
@app.get("/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id) or load_state(job_id)
    if not job:
        return jsonify({"status":"not_found","progress":0,"total":0,"percent":0,"rows":0,"grand_rows":0}), 200

    total = int(job.get("total", 1))
    done_points = job.get("done_points")
    if isinstance(done_points, list):
        done_points = set(done_points)

    prog = len(done_points) if isinstance(done_points, set) else int(job.get("progress", 0))
    pct = int((prog/total)*100) if total>0 else 0
    rows_now = int(job.get("rows",0))
    grand_rows = rows_now

    return jsonify({
        "status": job.get("status"),
        "progress": prog,
        "total": total,
        "percent": pct,
        "rows": rows_now,
        "grand_rows": grand_rows
    })

# ---------------- Rows JSON (with CSV fallback + normalization) ----------------
@app.get("/rows/<job_id>.json")
def rows(job_id):
    job = JOBS.get(job_id) or load_state(job_id)
    if not job:
        return jsonify([])

    data = job.get("data", [])
    if (not data) or (isinstance(data, list) and len(data) == 0):
        csv_path = job.get("csv")
        if csv_path and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            try:
                df = pd.read_csv(csv_path)
                data = df.to_dict(orient="records")
                with LOCK:
                    JOBS[job_id] = job
                    JOBS[job_id]["data"] = data
                    JOBS[job_id]["rows"] = len(data)
                    dp = JOBS[job_id].get("done_points")
                    if isinstance(dp, set):
                        JOBS[job_id]["done_points"] = list(dp)
                    save_state(job_id)
                    if isinstance(JOBS[job_id].get("done_points"), list):
                        JOBS[job_id]["done_points"] = set(JOBS[job_id]["done_points"])
            except Exception:
                pass

    # normalize & filter invalid coords
    normalized = []
    for rec in (data or []):
        nr = _norm_record(rec)
        if nr.get("lat") is None or nr.get("lng") is None:
            continue
        normalized.append(nr)

    return jsonify(normalized)

# ---------------- Download ----------------
@app.route("/download/<job_id>.<ext>", methods=["GET", "HEAD"])
def download(job_id, ext):
    job = JOBS.get(job_id) or load_state(job_id)
    if not job: return jsonify({"error":"job not found"}), 404
    csv_path = job.get("csv")
    if not csv_path or not os.path.exists(csv_path):
        return jsonify({"error":"file not ready"}), 404

    # empty but created
    if os.path.getsize(csv_path) == 0 and ext in ("csv","xlsx","txt"):
        return jsonify({"error":"file is empty (still running?)"}), 409

    if request.method == "HEAD":
        return ("", 204)

    if ext == "csv":
        resp = make_response(send_file(csv_path, as_attachment=True, download_name=os.path.basename(csv_path)))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    df = pd.read_csv(csv_path) if os.path.getsize(csv_path)>0 else pd.DataFrame()
    if ext == "xlsx":
        xlsx_path = csv_path.replace(".csv",".xlsx")
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
            df.to_excel(xw, index=False)
        resp = make_response(send_file(xlsx_path, as_attachment=True, download_name=os.path.basename(xlsx_path)))
        resp.headers["Cache-Control"] = "no-store"
        return resp
    elif ext == "txt":
        txt_path = csv_path.replace(".csv",".txt")
        if not df.empty:
            lines = [f'{r.get("country","")}\t{r.get("service","")}\t{r.get("name","")}\t{r.get("lat","")}\t{r.get("lng","")}' for _,r in df.iterrows()]
            open(txt_path,"w",encoding="utf-8").write("\n".join(lines))
        else:
            open(txt_path,"w",encoding="utf-8").write("")
        resp = make_response(send_file(txt_path, as_attachment=True, download_name=os.path.basename(txt_path)))
        resp.headers["Cache-Control"] = "no-store"
        return resp
    else:
        return jsonify({"error":"unsupported format"}), 400

# ---- Control CPU (used by scraper) ----
@app.post("/cpu_target")
def set_cpu_target():
    try:
        body = request.get_json(force=True)
        target = int(body.get("cpu_target", 75))
    except Exception:
        return jsonify({"ok": False, "error": "bad value"}), 400
    JOBS["_cpu_target_"] = target
    os.environ["CPU_TARGET"] = str(target)
    return jsonify({"ok": True, "cpu_target": target})

# ---- Optional: auto-resume on boot if env AUTO_RESUME=1 ----
def _auto_resume_on_boot():
    if os.getenv("AUTO_RESUME", "0") != "1":
        return
    states = glob.glob(os.path.join(os.getcwd(), "state_*.json"))
    for p in states:
        try:
            job_id = os.path.basename(p).replace("state_","").replace(".json","")
            st = load_state(job_id)
            if not st: continue
            # ما نكملش لو done
            if st.get("status") in ("done","done_cap"):
                continue
            country = st.get("country","UAE")
            keywords = st.get("keywords") or DEFAULT_KEYWORDS
            step = float(st.get("step", 0.25))
            headless = True
            aggressive = bool(st.get("aggressive", False))
            workers = int(st.get("workers", 1))
            zoom = int(st.get("zoom", 15))
            out_csv = st.get("csv") or os.path.join(os.getcwd(), f"results_{country}_{job_id}.csv")
            t = threading.Thread(
                target=run_job,
                args=(job_id, country, keywords, step, headless, out_csv, "", st.get("areas",""), aggressive, workers, zoom),
                daemon=True
            )
            t.start()
        except Exception:
            pass

_auto_resume_on_boot()

if __name__ == "__main__":
    # لا Debug ولا Reloader (علشان مايفقدش الذاكرة ولا يعمل 404)
    os.environ.pop("FLASK_DEBUG", None)
    os.environ.pop("FLASK_ENV", None)
    # نقرأ البورت من متغيّر البيئة (مثلاً Railway) أو 5000 لو مش موجود
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
