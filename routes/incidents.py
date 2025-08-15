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



# assume these utilities already exist in your project
# from services.storage import load_incidents, save_incidents
# from services.incident_validator import normalize_incident_type, validate_record

@incidents_bp.route("/new", methods=["GET", "POST"])
def new_incident():
    if request.method == "GET":
        return render_template("incident_new.html")

    # Build the incident record from the AVOMO form fields
    from services.incident_validator import normalize_incident_type, validate_record
    from services.storage import load_incidents, save_incidents

    data = {
        "id": str(int(time.time()*1000)),
        "created_ts": time.time(),
        "status": "draft",

        # Basic (Q1–Q5)
        "event_date": request.form.get("event_date","").strip(),
        "event_time": request.form.get("event_time","").strip(),
        "reporter_name": request.form.get("reporter_name","").strip(),
        "reporter_email": request.form.get("reporter_email","").strip(),
        "site": request.form.get("site","").strip(),

        # Q6–Q9
        "severe_event_flag": (request.form.get("severe_event_flag") or "").strip().lower(),  # 'yes' or 'no'
        "event_type": (request.form.get("event_type") or "").strip(),
        "severe_event_type": request.form.get("severe_event_type","").strip(),
        "severe_event_description": request.form.get("severe_event_description","").strip(),

        # Safety Concern (Q10–Q11)
        "safety_description": request.form.get("safety_description","").strip(),
        "safety_corrective_action": request.form.get("safety_corrective_action","").strip(),

        # Injury/Illness (Q12–Q27)
        "inj_name": request.form.get("inj_name","").strip(),
        "inj_job_title": request.form.get("inj_job_title","").strip(),
        "inj_phone": request.form.get("inj_phone","").strip(),
        "inj_address": request.form.get("inj_address","").strip(),
        "inj_city": request.form.get("inj_city","").strip(),
        "inj_state": request.form.get("inj_state","").strip(),
        "inj_zip": request.form.get("inj_zip","").strip(),
        "inj_status": request.form.get("inj_status","").strip(),
        "supervisor_name": request.form.get("supervisor_name","").strip(),
        "supervisor_notified_date": request.form.get("supervisor_notified_date","").strip(),
        "supervisor_notified_time": request.form.get("supervisor_notified_time","").strip(),
        "inj_event_description": request.form.get("inj_event_description","").strip(),
        "inj_type": request.form.get("inj_type","").strip(),
        "inj_body_parts": ", ".join(request.form.getlist("inj_body_parts")),
        "inj_immediate_action": request.form.get("inj_immediate_action","").strip(),
        "inj_enablon_confirm": request.form.get("inj_enablon_confirm","").strip(),

        # Property Damage (Q28–Q31)
        "prop_description": request.form.get("prop_description","").strip(),
        "prop_cost": request.form.get("prop_cost","").strip(),
        "prop_corrective_action": request.form.get("prop_corrective_action","").strip(),
        "prop_enablon_confirm": request.form.get("prop_enablon_confirm","").strip(),

        # Security Concern (Q32–Q40)
        "sec_types": "; ".join(request.form.getlist("sec_types")),
        "sec_description": request.form.get("sec_description","").strip(),
        "sec_names": request.form.get("sec_names","").strip(),
        "sec_are_they": request.form.get("sec_are_they","").strip(),
        "sec_law": request.form.get("sec_law","").strip(),
        "sec_agency_details": request.form.get("sec_agency_details","").strip(),
        "sec_footage": request.form.get("sec_footage","").strip(),
        "sec_corrective_action": request.form.get("sec_corrective_action","").strip(),
        "sec_enablon_confirm": request.form.get("sec_enablon_confirm","").strip(),

        # Vehicle Collision (Q41–Q49)
        "collision_location": request.form.get("collision_location","").strip(),
        "involved_parties": request.form.get("involved_parties","").strip(),
        "vehicle_identifier": request.form.get("vehicle_identifier","").strip(),
        "vehicle_hit": request.form.get("vehicle_hit","").strip(),
        "collision_any_injury": request.form.get("collision_any_injury","").strip(),
        "collision_mode": request.form.get("collision_mode","").strip(),
        "collision_description": request.form.get("collision_description","").strip(),
        "collision_corrective_action": request.form.get("collision_corrective_action","").strip(),
        "collision_enablon_confirm": request.form.get("collision_enablon_confirm","").strip(),

        # Environmental (Q50–Q56)
        "env_involved_parties": request.form.get("env_involved_parties","").strip(),
        "env_roles": "; ".join(request.form.getlist("env_roles")),
        "spill_volume": request.form.get("spill_volume","").strip(),
        "chemicals": request.form.get("chemicals","").strip(),
        "env_description": request.form.get("env_description","").strip(),
        "env_corrective_action": request.form.get("env_corrective_action","").strip(),
        "env_enablon_confirm": request.form.get("env_enablon_confirm","").strip(),

        # Depot (Q57–Q59)
        "depot_description": request.form.get("depot_description","").strip(),
        "depot_actions": request.form.get("depot_actions","").strip(),
        "depot_outcome": request.form.get("depot_outcome","").strip(),

        # Near Miss (Q60–Q62)
        "near_type": request.form.get("near_type","").strip(),
        "near_description": request.form.get("near_description","").strip(),
        "near_corrective_action": request.form.get("near_corrective_action","").strip(),

        # Root Cause + CAPA (Q63–Q71)
        "why1": request.form.get("why1","").strip(),
        "why2": request.form.get("why2","").strip(),
        "why3": request.form.get("why3","").strip(),
        "why4": request.form.get("why4","").strip(),
        "why5": request.form.get("why5","").strip(),
        "capa_action": request.form.get("capa_action","").strip(),
        "capa_owner": request.form.get("capa_owner","").strip(),
        "capa_owner_email": request.form.get("capa_owner_email","").strip(),
        "capa_due": request.form.get("capa_due","").strip(),

        # Back-compat bucket for dashboards
        "answers": {
            "people": request.form.get("people") or "",
            "environment": request.form.get("environment") or "",
            "cost": request.form.get("cost") or "",
            "legal": request.form.get("legal") or "",
            "reputation": request.form.get("reputation") or "",
        },
    }

    # Canonical type normalization
    data["type"] = normalize_incident_type({"event_type": data.get("event_type","")})

    items = load_incidents()
    items[data["id"]] = data
    save_incidents(items)

    ok, missing = validate_record(data)
    data["status"] = "complete" if ok else "incomplete"
    items[data["id"]] = data
    save_incidents(items)

    flash("Incident created and validated ✔" if ok else f"Incident saved. Missing required fields: {', '.join(missing)}",
          "success" if ok else "warning")
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
