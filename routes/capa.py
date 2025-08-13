import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify
from services.capa_manager import CAPAManager

capa_bp = Blueprint("capa", __name__)
capa_manager = CAPAManager()

@capa_bp.route("/")
def capa_list():
    capas = capa_manager.load_capas()
    capa_list = sorted(capas.values(), key=lambda x: x.get("created_date", ""), reverse=True)
    return render_template("capa_list.html", capas=capa_list)

@capa_bp.route("/new", methods=["GET", "POST"])
def new_capa():
    if request.method == "GET":
        # Check if linked to another entity
        source = request.args.get("source")
        source_id = request.args.get("source_id")
        return render_template("capa_new.html", source=source, source_id=source_id)
    
    capa_data = {
        "title": request.form.get("title"),
        "description": request.form.get("description"),
        "type": request.form.get("type"),
        "assignee": request.form.get("assignee"),
        "due_date": request.form.get("due_date"),
        "priority": request.form.get("priority"),
        "created_by": request.form.get("created_by", "Current User"),
        "source": request.form.get("source", "manual"),
        "source_id": request.form.get("source_id"),
        "root_cause": request.form.get("root_cause", ""),
        "implementation_plan": request.form.get("implementation_plan", "")
    }
    
    capa_id = capa_manager.create_capa(capa_data)
    flash(f"CAPA {capa_id} created successfully", "success")
    return redirect(url_for("capa.capa_detail", capa_id=capa_id))

@capa_bp.route("/<capa_id>")
def capa_detail(capa_id):
    capas = capa_manager.load_capas()
    capa = capas.get(capa_id)
    if not capa:
        flash("CAPA not found", "error")
        return redirect(url_for("capa.capa_list"))
    return render_template("capa_detail.html", capa=capa)

@capa_bp.route("/<capa_id>/update", methods=["POST"])
def update_capa(capa_id):
    update_data = {
        "status": request.form.get("status"),
        "comment": request.form.get("comment"),
        "updated_by": request.form.get("updated_by", "Current User"),
        "assignee": request.form.get("assignee"),
        "due_date": request.form.get("due_date"),
        "priority": request.form.get("priority")
    }
    
    if capa_manager.update_capa(capa_id, update_data):
        flash("CAPA updated successfully", "success")
    else:
        flash("Failed to update CAPA", "error")
    
    return redirect(url_for("capa.capa_detail", capa_id=capa_id))

@capa_bp.route("/dashboard")
def capa_dashboard():
    stats = capa_manager.get_capa_statistics()
    overdue = capa_manager.get_overdue_capas()
    
    return render_template("capa_dashboard.html", stats=stats, overdue=overdue)

@capa_bp.route("/assigned")
def assigned_capas():
    """View CAPAs assigned to current user"""
    # In a real system, you'd filter by actual user
    current_user = request.args.get("user", "Current User")
    capas = capa_manager.load_capas()
    
    assigned = [capa for capa in capas.values() 
                if capa.get("assignee") == current_user and capa.get("status") != "completed"]
    
    return render_template("capa_assigned.html", capas=assigned, user=current_user)

@capa_bp.route("/api/stats")
def api_capa_stats():
    """API endpoint for CAPA statistics"""
    try:
        stats = capa_manager.get_capa_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@capa_bp.get("/api/list")
def api_capa_list():
    """List CAPAs with optional filters: status, source, assignee"""
    filters = {
        "status": request.args.get("status"),
        "source": request.args.get("source"),
        "assignee": request.args.get("assignee")
    }
    capas = capa_manager.load_capas()
    out = []
    for c in capas.values():
        ok = True
        for k,v in filters.items():
            if v and str(c.get(k,"")).lower() != v.lower():
                ok = False; break
        if ok:
            out.append(c)
    # sort by created_date desc
    out = sorted(out, key=lambda x: x.get("created_date",""), reverse=True)
    return jsonify({"count": len(out), "items": out})
