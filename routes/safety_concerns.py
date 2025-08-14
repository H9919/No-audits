# routes/safety_concerns.py - Enhanced with API endpoints for dynamic tables
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify

safety_concerns_bp = Blueprint("safety_concerns", __name__)

DATA_DIR = Path("data")
CONCERNS_FILE = DATA_DIR / "safety_concerns.json"

def load_safety_concerns():
    """Load safety concerns from JSON file"""
    if CONCERNS_FILE.exists():
        try:
            return json.loads(CONCERNS_FILE.read_text())
        except:
            return {}
    return {}

def save_safety_concerns(concerns):
    """Save safety concerns dictionary to file"""
    DATA_DIR.mkdir(exist_ok=True)
    CONCERNS_FILE.write_text(json.dumps(concerns, indent=2))

def save_safety_concern(concern_data):
    """Save safety concern to JSON file"""
    concerns = load_safety_concerns()
    concerns[concern_data["id"]] = concern_data
    save_safety_concerns(concerns)

def determine_priority(hazard_type, risk_level):
    """Determine priority based on hazard type and risk level"""
    high_risk_hazards = ["electrical", "chemical", "fall_from_height", "machinery"]
    
    if hazard_type in high_risk_hazards or risk_level == "high":
        return "high"
    elif risk_level == "medium":
        return "medium"
    else:
        return "low"

def calculate_stats(concerns_list):
    """Calculate statistics for safety concerns"""
    if not concerns_list:
        return {
            "total": 0,
            "open": 0,
            "resolved": 0,
            "this_month": 0
        }
    
    total = len(concerns_list)
    open_count = len([c for c in concerns_list if c.get("status") in ["reported", "investigating"]])
    resolved_count = len([c for c in concerns_list if c.get("status") == "resolved"])
    
    # Calculate this month
    thirty_days_ago = time.time() - (30 * 24 * 60 * 60)
    this_month = len([c for c in concerns_list if c.get("created_date", 0) > thirty_days_ago])
    
    return {
        "total": total,
        "open": open_count,
        "resolved": resolved_count,
        "this_month": this_month
    }

@safety_concerns_bp.route("/")
def concerns_list():
    """List all safety concerns with enhanced stats"""
    concerns = load_safety_concerns()
    concern_list = sorted(concerns.values(), key=lambda x: x.get("created_date", 0), reverse=True)
    stats = calculate_stats(concern_list)
    
    return render_template("safety_concerns_list.html", 
                         concerns=concern_list, 
                         stats=stats)

@safety_concerns_bp.route("/api/list")
def api_concerns_list():
    """API endpoint for safety concerns list with filtering"""
    concerns = load_safety_concerns()
    concern_list = list(concerns.values())
    
    # Apply filters from query parameters
    filters = {
        "status": request.args.get("status"),
        "priority": request.args.get("priority"),
        "hazard_type": request.args.get("hazard_type"),
        "type": request.args.get("type"),
        "anonymous": request.args.get("anonymous"),
        "assigned_to": request.args.get("assigned_to"),
        "location": request.args.get("location")
    }
    
    # Date range filters
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    
    filtered_concerns = []
    for concern in concern_list:
        # Apply basic filters
        include = True
        for key, value in filters.items():
            if value and key in concern:
                if key == "anonymous":
                    # Special handling for boolean
                    filter_value = value.lower() == "true"
                    if concern.get(key) != filter_value:
                        include = False
                        break
                elif str(concern.get(key, "")).lower() != value.lower():
                    include = False
                    break
        
        # Apply date range filter
        if include and (date_from or date_to):
            concern_date = concern.get("created_date", 0)
            if isinstance(concern_date, (int, float)):
                concern_datetime = datetime.fromtimestamp(concern_date)
            else:
                try:
                    concern_datetime = datetime.fromisoformat(str(concern_date))
                except:
                    concern_datetime = datetime.now()
            
            if date_from:
                from_date = datetime.fromisoformat(date_from)
                if concern_datetime < from_date:
                    include = False
            
            if date_to and include:
                to_date = datetime.fromisoformat(date_to)
                if concern_datetime > to_date:
                    include = False
        
        if include:
            filtered_concerns.append(concern)
    
    # Sort by created_date descending
    filtered_concerns.sort(key=lambda x: x.get("created_date", 0), reverse=True)
    
    return jsonify({
        "count": len(filtered_concerns),
        "items": filtered_concerns,
        "stats": calculate_stats(filtered_concerns)
    })

@safety_concerns_bp.route("/api/stats")
def api_concerns_stats():
    """API endpoint for safety concerns statistics"""
    try:
        concerns = load_safety_concerns()
        concern_list = list(concerns.values())
        stats = calculate_stats(concern_list)
        
        # Add additional analytics
        stats.update({
            "by_type": {},
            "by_priority": {},
            "by_hazard_type": {},
            "by_status": {},
            "trends": get_trend_data(concern_list)
        })
        
        # Calculate distributions
        for concern in concern_list:
            # By type
            concern_type = concern.get("type", "unknown")
            stats["by_type"][concern_type] = stats["by_type"].get(concern_type, 0) + 1
            
            # By priority
            priority = concern.get("priority", "medium")
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
            
            # By hazard type
            hazard_type = concern.get("hazard_type", "other")
            stats["by_hazard_type"][hazard_type] = stats["by_hazard_type"].get(hazard_type, 0) + 1
            
            # By status
            status = concern.get("status", "reported")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_trend_data(concerns_list):
    """Generate trend data for the last 6 months"""
    trends = []
    now = datetime.now()
    
    for i in range(6):
        # Calculate month start and end
        month_start = (now.replace(day=1) - timedelta(days=i*30)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_concerns = 0
        for concern in concerns_list:
            concern_date = concern.get("created_date", 0)
            if isinstance(concern_date, (int, float)):
                concern_datetime = datetime.fromtimestamp(concern_date)
            else:
                try:
                    concern_datetime = datetime.fromisoformat(str(concern_date))
                except:
                    continue
            
            if month_start <= concern_datetime <= month_end:
                month_concerns += 1
        
        trends.append({
            "month": month_start.strftime("%b %Y"),
            "count": month_concerns
        })
    
    return list(reversed(trends))  # Most recent first

@safety_concerns_bp.route("/new", methods=["GET", "POST"])
def new_concern():
    """Create new safety concern"""
    if request.method == "GET":
        concern_type = request.args.get("type", "concern")
        anonymous = request.args.get("anonymous", "false").lower() == "true"
        return render_template("safety_concern_new.html", 
                             concern_type=concern_type, 
                             anonymous=anonymous)
    
    # Process form submission
    concern_data = {
        "id": str(int(time.time() * 1000)),
        "type": request.form.get("type", "concern"),
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "location": request.form.get("location", ""),
        "hazard_type": request.form.get("hazard_type", ""),
        "immediate_action": request.form.get("immediate_action", ""),
        "anonymous": request.form.get("anonymous") == "on",
        "reporter": "" if request.form.get("anonymous") == "on" else request.form.get("reporter", ""),
        "created_date": time.time(),
        "status": "reported",
        "assigned_to": "",
        "risk_level": request.form.get("risk_level", "medium"),
        "priority": determine_priority(request.form.get("hazard_type", ""), request.form.get("risk_level", "medium")),
        "updates": []
    }
    
    save_safety_concern(concern_data)
    
    if concern_data["anonymous"]:
        flash("Anonymous safety concern submitted successfully. Thank you for speaking up!", "success")
        return redirect(url_for("safety_concerns.concerns_list"))
    else:
        flash("Safety concern submitted successfully. Thank you for speaking up!", "success")
        return redirect(url_for("safety_concerns.concern_detail", concern_id=concern_data["id"]))

@safety_concerns_bp.route("/<concern_id>")
def concern_detail(concern_id):
    """View safety concern details"""
    concerns = load_safety_concerns()
    concern = concerns.get(concern_id)
    if not concern:
        flash("Safety concern not found", "error")
        return redirect(url_for("safety_concerns.concerns_list"))
    
    return render_template("safety_concern_detail.html", concern=concern)

@safety_concerns_bp.route("/<concern_id>/update", methods=["POST"])
def update_concern(concern_id):
    """Update safety concern"""
    concerns = load_safety_concerns()
    concern = concerns.get(concern_id)
    
    if not concern:
        if request.is_json or request.headers.get('Content-Type') == 'application/json':
            return jsonify({"error": "Safety concern not found"}), 404
        flash("Safety concern not found", "error")
        return redirect(url_for("safety_concerns.concerns_list"))
    
    # Add update to history
    update = {
        "timestamp": time.time(),
        "user": request.form.get("updated_by", "System"),
        "comment": request.form.get("comment", ""),
        "status_change": request.form.get("status") != concern.get("status"),
        "old_status": concern.get("status"),
        "new_status": request.form.get("status")
    }
    
    if "updates" not in concern:
        concern["updates"] = []
    concern["updates"].append(update)
    
    # Update fields
    if request.form.get("status"):
        concern["status"] = request.form.get("status")
    if request.form.get("assigned_to"):
        concern["assigned_to"] = request.form.get("assigned_to")
    if request.form.get("priority"):
        concern["priority"] = request.form.get("priority")
    
    concerns[concern_id] = concern
    save_safety_concerns(concerns)
    
    if request.is_json or request.headers.get('Content-Type') == 'application/json':
        return jsonify({"success": True, "message": "Safety concern updated successfully"})
    
    flash("Safety concern updated successfully", "success")
    return redirect(url_for("safety_concerns.concern_detail", concern_id=concern_id))

@safety_concerns_bp.route("/<concern_id>/assign", methods=["POST"])
def assign_concern(concern_id):
    """Assign safety concern to investigator"""
    concerns = load_safety_concerns()
    concern = concerns.get(concern_id)
    
    if not concern:
        return jsonify({"error": "Safety concern not found"}), 404
    
    assignee = request.form.get("assignee") or request.json.get("assignee")
    if not assignee:
        return jsonify({"error": "Assignee is required"}), 400
    
    # Update concern
    concern["assigned_to"] = assignee
    concern["status"] = "investigating"
    
    # Add update record
    update = {
        "timestamp": time.time(),
        "user": request.form.get("updated_by", "System"),
        "comment": f"Assigned to {assignee} for investigation",
        "status_change": True,
        "old_status": concern.get("status", "reported"),
        "new_status": "investigating"
    }
    
    if "updates" not in concern:
        concern["updates"] = []
    concern["updates"].append(update)
    
    concerns[concern_id] = concern
    save_safety_concerns(concerns)
    
    return jsonify({"success": True, "message": f"Safety concern assigned to {assignee}"})

@safety_concerns_bp.route("/<concern_id>/escalate", methods=["POST"])
def escalate_concern(concern_id):
    """Escalate safety concern"""
    concerns = load_safety_concerns()
    concern = concerns.get(concern_id)
    
    if not concern:
        return jsonify({"error": "Safety concern not found"}), 404
    
    # Update priority to high
    old_priority = concern.get("priority", "medium")
    concern["priority"] = "high"
    
    # Add update record
    update = {
        "timestamp": time.time(),
        "user": request.form.get("updated_by", "System"),
        "comment": f"Safety concern escalated to management (priority changed from {old_priority} to high)",
        "status_change": False,
        "priority_change": True,
        "old_priority": old_priority,
        "new_priority": "high"
    }
    
    if "updates" not in concern:
        concern["updates"] = []
    concern["updates"].append(update)
    
    concerns[concern_id] = concern
    save_safety_concerns(concerns)
    
    return jsonify({"success": True, "message": "Safety concern escalated to management"})

@safety_concerns_bp.route("/bulk/update", methods=["POST"])
def bulk_update_concerns():
    """Bulk update multiple safety concerns"""
    data = request.get_json()
    concern_ids = data.get("concern_ids", [])
    updates = data.get("updates", {})
    
    if not concern_ids or not updates:
        return jsonify({"error": "concern_ids and updates are required"}), 400
    
    concerns = load_safety_concerns()
    updated_count = 0
    
    for concern_id in concern_ids:
        if concern_id in concerns:
            concern = concerns[concern_id]
            
            # Create update record
            update_record = {
                "timestamp": time.time(),
                "user": updates.get("updated_by", "System"),
                "comment": updates.get("comment", "Bulk update"),
                "bulk_update": True
            }
            
            # Apply updates
            for key, value in updates.items():
                if key not in ["updated_by", "comment"] and key in concern:
                    if concern[key] != value:
                        update_record[f"old_{key}"] = concern[key]
                        update_record[f"new_{key}"] = value
                        concern[key] = value
            
            if "updates" not in concern:
                concern["updates"] = []
            concern["updates"].append(update_record)
            
            concerns[concern_id] = concern
            updated_count += 1
    
    save_safety_concerns(concerns)
    
    return jsonify({
        "success": True,
        "message": f"Successfully updated {updated_count} safety concerns"
    })

@safety_concerns_bp.route("/export")
def export_concerns():
    """Export safety concerns to CSV"""
    import csv
    import io
    from flask import make_response
    
    concerns = load_safety_concerns()
    concern_list = sorted(concerns.values(), key=lambda x: x.get("created_date", 0), reverse=True)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    headers = [
        "ID", "Title", "Type", "Status", "Priority", "Hazard Type",
        "Location", "Reporter", "Anonymous", "Assigned To", "Created Date",
        "Description", "Immediate Action"
    ]
    writer.writerow(headers)
    
    # Write data
    for concern in concern_list:
        created_date = ""
        if concern.get("created_date"):
            try:
                created_date = datetime.fromtimestamp(concern["created_date"]).strftime("%Y-%m-%d %H:%M:%S")
            except:
                created_date = str(concern["created_date"])
        
        row = [
            concern.get("id", ""),
            concern.get("title", ""),
            concern.get("type", ""),
            concern.get("status", ""),
            concern.get("priority", ""),
            concern.get("hazard_type", ""),
            concern.get("location", ""),
            concern.get("reporter", "") if not concern.get("anonymous") else "Anonymous",
            "Yes" if concern.get("anonymous") else "No",
            concern.get("assigned_to", ""),
            created_date,
            concern.get("description", ""),
            concern.get("immediate_action", "")
        ]
        writer.writerow(row)
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=safety_concerns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response
