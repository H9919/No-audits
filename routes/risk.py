# routes/risk.py - Enhanced risk management
import json
import time
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify
from services.risk_matrix import LIKELIHOOD_SCALE, SEVERITY_SCALE, calculate_risk_score, get_risk_level

risk_bp = Blueprint("risk", __name__)

@risk_bp.route("/assess", methods=["GET", "POST"])
def risk_assessment():
    """Conduct risk assessment"""
    if request.method == "GET":
        return render_template("risk_assessment.html", 
                             likelihood_scale=LIKELIHOOD_SCALE,
                             severity_scale=SEVERITY_SCALE)
    
    # Process assessment
    likelihood = int(request.form.get("likelihood", 0))
    severity_scores = {}
    
    for category in SEVERITY_SCALE.keys():
        severity_scores[category] = int(request.form.get(f"severity_{category}", 0))
    
    risk_score = calculate_risk_score(likelihood, severity_scores)
    risk_level = get_risk_level(risk_score)
    
    risk_data = {
        "id": str(int(time.time() * 1000)),
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "likelihood": likelihood,
        "severity_scores": severity_scores,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "created_date": time.time(),
        "created_by": request.form.get("created_by", "Current User"),
        "status": "active"
    }
    
    save_risk_assessment(risk_data)
    flash(f"Risk assessment completed. Risk Level: {risk_level} (Score: {risk_score})", "info")
    
    return render_template("risk_result.html", 
                         risk_data=risk_data,
                         likelihood_scale=LIKELIHOOD_SCALE,
                         severity_scale=SEVERITY_SCALE)

@risk_bp.route("/register")
def risk_register():
    """View risk register"""
    risks = load_risk_assessments()
    risk_list = sorted(risks.values(), key=lambda x: x.get("created_date", 0), reverse=True)
    
    # Calculate statistics
    stats = {
        "total": len(risk_list),
        "critical": len([r for r in risk_list if r.get("risk_level") == "Critical"]),
        "high": len([r for r in risk_list if r.get("risk_level") == "High"]),
        "medium": len([r for r in risk_list if r.get("risk_level") == "Medium"]),
        "low": len([r for r in risk_list if r.get("risk_level") in ["Low", "Very Low"]])
    }
    
    return render_template("risk_register.html", risks=risk_list, stats=stats)

@risk_bp.route("/<risk_id>")
def risk_detail(risk_id):
    """View risk assessment details"""
    risks = load_risk_assessments()
    risk = risks.get(risk_id)
    if not risk:
        flash("Risk assessment not found", "error")
        return redirect(url_for("risk.risk_register"))
    return render_template("risk_detail.html", risk=risk)

def save_risk_assessment(risk_data):
    """Save risk assessment to file"""
    data_dir = Path("data")
    risk_file = data_dir / "risk_assessments.json"
    
    if risk_file.exists():
        risks = json.loads(risk_file.read_text())
    else:
        risks = {}
    
    risks[risk_data["id"]] = risk_data
    
    data_dir.mkdir(exist_ok=True)
    risk_file.write_text(json.dumps(risks, indent=2))

def load_risk_assessments():
    """Load risk assessments from file"""
    risk_file = Path("data/risk_assessments.json")
    if risk_file.exists():
        try:
            return json.loads(risk_file.read_text())
        except:
            return {}
    return {}
