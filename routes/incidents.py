import json
import time
from pathlib import Path
from flask import Blueprint, request, render_template, redirect, url_for, flash, send_file, abort
from services.incident_validator import REQUIRED_BY_TYPE, compute_completeness, validate_record
from services.pdf import build_incident_pdf
from services.capa_manager import CAPAManager

DATA_DIR = Path("data")
INCIDENTS_JSON = DATA_DIR / "incidents.json"
PDF_DIR = DATA_DIR / "pdf"

incidents_bp = Blueprint("incidents", __name__, template_folder="../templates")

def load_incidents():
    if INCIDENTS_JSON.exists():
        return json.loads(INCIDENTS_JSON.read_text())
    return {}

def save_incidents(obj):
    INCIDENTS_JSON.write_text(json.dumps(obj, indent=2))

@incidents_bp.get("/")
def list_incidents():
    items = load_incidents()
    rows = []
    for iid, rec in items.items():
        rows.append({
            "id": iid,
            "type": rec.get("type"),
            "created_ts": rec.get("created_ts"),
            "completeness": compute_completeness(rec),
            "status": rec.get("status", "draft"),
        })
    rows = sorted(rows, key=lambda r: r["created_ts"], reverse=True)
    return render_template("incidents_list.html", rows=rows, required_by_type=REQUIRED_BY_TYPE)

@incidents_bp.route("/new", methods=["GET", "POST"])
def new_incident():
    if request.method == "GET":
        return render_template("incident_new.html")
    data = {
        "id": str(int(time.time()*1000)),
        "type": request.form.get("type") or "other",
        "anonymous": bool(request.form.get("anonymous")),
        "facility_code": request.form.get("facility_code", ""),
        "region": request.form.get("region", ""),
        "location_lat": request.form.get("location_lat", ""),
        "location_lng": request.form.get("location_lng", ""),
        "location_text": request.form.get("location_text", ""),
        "answers": {
            "people": request.form.get("people") or "",
            "environment": request.form.get("environment") or "",
            "cost": request.form.get("cost") or "",
            "legal": request.form.get("legal") or "",
            "reputation": request.form.get("reputation") or "",
        },
        "created_ts": time.time(),
        "status": "draft"
    }
    items = load_incidents()
    items[data["id"]] = data
    save_incidents(items)
    flash("Incident created (draft). Continue filling it.", "success")
    return redirect(url_for("incidents.edit_incident", iid=data["id"]))

@incidents_bp.route("/<iid>/edit", methods=["GET", "POST"])
def edit_incident(iid):
    items = load_incidents()
    rec = items.get(iid)
    if not rec:
        flash("Incident not found", "danger")
        return redirect(url_for("incidents.list_incidents"))

    if request.method == "POST":
        rec["type"] = request.form.get("type") or rec["type"]
        rec["anonymous"] = bool(request.form.get("anonymous"))
        rec["facility_code"] = request.form.get("facility_code", rec.get("facility_code",""))
        rec["region"] = request.form.get("region", rec.get("region",""))
        rec["location_lat"] = request.form.get("location_lat", rec.get("location_lat",""))
        rec["location_lng"] = request.form.get("location_lng", rec.get("location_lng",""))
        rec["location_text"] = request.form.get("location_text", rec.get("location_text",""))
        for cat in ["people", "environment", "cost", "legal", "reputation"]:
            rec["answers"][cat] = request.form.get(cat) or rec["answers"].get(cat, "")
        ok, missing = validate_record(rec)
        rec["status"] = "complete" if ok else "incomplete"
        items[iid] = rec
        save_incidents(items)
        if ok:
            flash("Incident validated and marked complete ✔", "success")
        else:
            flash(f"Missing required categories for type {rec['type']}: {', '.join(missing)}", "warning")
        return redirect(url_for("incidents.edit_incident", iid=iid))

    completeness = compute_completeness(rec)
    ok, missing = validate_record(rec)
    return render_template(
        "incident_edit.html",
        rec=rec, completeness=completeness, ok=ok, missing=missing, required_by_type=REQUIRED_BY_TYPE
    )

@incidents_bp.get("/<iid>/pdf")
def download_incident_pdf(iid):
    items = load_incidents()
    rec = items.get(iid)
    if not rec:
        abort(404)
    completeness = compute_completeness(rec)
    ok, missing = validate_record(rec)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PDF_DIR / f"incident-{iid}.pdf"
    build_incident_pdf(rec, completeness, ok, missing, str(out_path))
    return send_file(out_path, as_attachment=True, download_name=f"incident-{iid}.pdf")


@incidents_bp.route("/<iid>/capa", methods=["GET", "POST"])
def incident_capa(iid):
    items = load_incidents()
    rec = items.get(iid)
    if not rec:
        flash("Incident not found", "danger")
        return redirect(url_for("incidents.list_incidents"))

    mgr = CAPAManager()

    if request.method == "POST":
        # Collect chosen actions (checkboxes) + optional custom action
        chosen = request.form.getlist("actions")
        custom = (request.form.get("custom_action") or "").strip()
        if custom:
            chosen.append(custom)
        rec.setdefault("capa", {})
        rec["capa"]["chosen"] = chosen
        rec["capa"]["confirmed_by"] = request.form.get("confirmed_by", "")
        rec["capa"]["confirmed_ts"] = time.time()
        items[iid] = rec
        save_incidents(items)
        flash("Corrective actions saved.", "success")
        return redirect(url_for("incidents.edit_incident", iid=iid))

    # GET: build suggestions description from answers & type
    answers = rec.get("answers", {})
    desc_parts = [rec.get("type",""), answers.get("people",""), answers.get("environment",""),
                  answers.get("cost",""), answers.get("legal",""), answers.get("reputation","")]
    desc = " ".join([p for p in desc_parts if p]).strip() or "General workplace safety issue"
    res = mgr.suggest_corrective_actions(desc)

    # Store last suggestions for traceability
    rec.setdefault("capa", {})
    rec["capa"]["suggested"] = res.get("actions", [])
    rec["capa"]["confidence"] = res.get("confidence", 0.0)
    rec["capa"]["rationale"] = res.get("rationale", "")
    items[iid] = rec
    save_incidents(items)

    return render_template("incident_capa.html", rec=rec, suggestions=res.get("actions", []),
                           confidence=res.get("confidence", 0.0), rationale=res.get("rationale",""))


@incidents_bp.route("/<iid>/capa/status", methods=["POST"])
def incident_capa_status(iid):
    items = load_incidents()
    rec = items.get(iid)
    if not rec:
        flash("Incident not found", "danger")
        return redirect(url_for("incidents.list_incidents"))
    status = request.form.get("status","").strip()
    comment = request.form.get("comment","").strip()
    assignee = request.form.get("assignee","").strip()
    due_date = request.form.get("due_date","").strip()
    priority = request.form.get("priority","").strip() or "medium"

    # ensure CAPA exists in CAPA manager
    mgr = CAPAManager()
    capa_id = rec.get("capa",{}).get("capa_id")
    if not capa_id:
        # create a CAPA linked to this incident
        title = f"CAPA for Incident {iid}"
        description = (rec.get("answers",{}).get("people","") or rec.get("answers",{}).get("environment","") or "").strip()
        capa_id = mgr.create_capa({
            "title": title,
            "description": description,
            "type": "corrective",
            "source": "incident",
            "source_id": iid,
            "assignee": assignee,
            "due_date": due_date,
            "priority": priority
        })
        rec.setdefault("capa", {})["capa_id"] = capa_id
        items[iid] = rec
        save_incidents(items)

    # update status
    mgr.update_capa(capa_id, {
        "status": status or "open",
        "comment": comment,
        "updated_by": request.form.get("updated_by",""),
        "assignee": assignee,
        "due_date": due_date,
        "priority": priority
    })
    flash("CAPA status updated", "success")
    return redirect(url_for("incidents.edit_incident", iid=iid))
