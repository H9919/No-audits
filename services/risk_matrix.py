# services/risk_matrix.py - FIXED VERSION with pure logic only
"""
Enhanced risk assessment matrix and calculations for the EHS system.
This module contains only the core risk calculation logic and scales.
All Flask routes and chatbot code has been moved to appropriate modules.
"""

# Enhanced likelihood scale with more detailed descriptions
LIKELIHOOD_SCALE = {
    0: {
        "label": "Impossible", 
        "description": "The event cannot happen under current design or controls"
    },
    2: {
        "label": "Rare", 
        "description": "Extremely unlikely but theoretically possible (once in 10+ years)"
    },
    4: {
        "label": "Unlikely", 
        "description": "Could happen in exceptional cases (once every 5–10 years)"
    },
    6: {
        "label": "Possible", 
        "description": "Might occur occasionally under abnormal conditions (once every 1–5 years)"
    },
    8: {
        "label": "Likely", 
        "description": "Occurs regularly or has been documented (multiple times per year)"
    },
    10: {
        "label": "Almost Certain", 
        "description": "Expected to happen frequently (monthly or more)"
    }
}

# Enhanced severity scale by category
SEVERITY_SCALE = {
    "people": {
        0: "No injury or risk of harm",
        2: "First aid only; no lost time",
        4: "Medical treatment; lost time injury (LTI), no hospitalization",
        6: "Serious injury; hospitalization, restricted duty >3 days",
        8: "Permanent disability, amputation, serious head/spine injury",
        10: "Fatality or multiple severe injuries"
    },
    "environment": {
        0: "No release or environmental impact",
        2: "Minor release, fully contained, no reporting needed",
        4: "Moderate release, requires internal reporting",
        6: "Reportable spill; affects stormwater, air, or soil; TCEQ/EPA notification",
        8: "Major spill; spread beyond site boundary, public/environmental impact",
        10: "Catastrophic event; large-scale contamination or cleanup needed"
    },
    "cost": {
        0: "No damage or cost",
        2: "Minor damage; <$1,000",
        4: "$1,000–$10,000; minor repair to AEV or equipment",
        6: "$10,000–$100,000; significant repair or downtime",
        8: "Critical asset loss; one AEV out of service long-term",
        10: ">$100,000 damage or liability claim"
    },
    "reputation": {
        0: "No impact to reputation",
        2: "Internally noticed only; no client or public awareness",
        4: "AVOMO client concern raised; issue handled proactively",
        6: "Uber or Waymo formally logs concern, requires follow-up",
        8: "Incident reaches media or affects corporate partnerships",
        10: "Public crisis; loss of contract or long-term brand damage"
    },
    "legal": {
        0: "Fully compliant; no issue",
        2: "Minor internal policy deviation; corrected on site",
        4: "Potential OSHA or EPA non-compliance; not reportable yet",
        6: "Reportable violation; citation risk or official notice",
        8: "Fines or penalties issued; corrective action required",
        10: "Legal action, shutdown, or major lawsuit; significant regulatory breach"
    }
}

def calculate_risk_score(likelihood_score, severity_scores):
    """
    Calculate overall risk score using the enhanced ERC methodology.
    
    Args:
        likelihood_score (int): Likelihood score from 0-10
        severity_scores (dict): Dictionary of severity scores by category
        
    Returns:
        float: Overall risk score from 0-100
    """
    if not severity_scores:
        return 0.0
        
    # Use the maximum severity across all categories
    max_severity = max(severity_scores.values())
    
    # Risk Score = Likelihood × Maximum Severity
    return likelihood_score * max_severity

def get_risk_level(risk_score):
    """
    Determine risk level based on calculated risk score.
    
    Args:
        risk_score (float): Risk score from 0-100
        
    Returns:
        str: Risk level classification
    """
    if risk_score >= 80:
        return "Critical"
    elif risk_score >= 60:
        return "High" 
    elif risk_score >= 40:
        return "Medium"
    elif risk_score >= 20:
        return "Low"
    else:
        return "Very Low"

def get_risk_color(risk_level):
    """
    Get color code for risk level visualization.
    
    Args:
        risk_level (str): Risk level from get_risk_level()
        
    Returns:
        str: Bootstrap color class
    """
    color_map = {
        "Critical": "danger",
        "High": "warning",
        "Medium": "info", 
        "Low": "success",
        "Very Low": "light"
    }
    return color_map.get(risk_level, "secondary")

def get_recommended_actions(risk_level):
    """
    Get recommended actions based on risk level.
    
    Args:
        risk_level (str): Risk level classification
        
    Returns:
        list: List of recommended action strings
    """
    action_map = {
        "Critical": [
            "Immediate management notification required",
            "Stop work until controls implemented",
            "Emergency response may be required",
            "Senior leadership involvement necessary"
        ],
        "High": [
            "Management notification within 24 hours",
            "Implement additional controls immediately",
            "Review and enhance existing procedures",
            "Consider stopping affected operations"
        ],
        "Medium": [
            "Management awareness required",
            "Review existing controls",
            "Implement improvements within reasonable timeframe",
            "Monitor effectiveness of controls"
        ],
        "Low": [
            "Document in risk register",
            "Review controls periodically",
            "Monitor for changes in conditions"
        ],
        "Very Low": [
            "Document assessment",
            "Periodic review as part of routine assessment"
        ]
    }
    return action_map.get(risk_level, [])

def validate_severity_scores(severity_scores):
    """
    Validate that severity scores are within acceptable ranges.
    
    Args:
        severity_scores (dict): Dictionary of severity scores
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    errors = []
    
    if not isinstance(severity_scores, dict):
        return False, ["Severity scores must be a dictionary"]
    
    valid_categories = set(SEVERITY_SCALE.keys())
    for category, score in severity_scores.items():
        if category not in valid_categories:
            errors.append(f"Invalid category: {category}")
            continue
            
        if not isinstance(score, (int, float)):
            errors.append(f"Score for {category} must be numeric")
            continue
            
        if not (0 <= score <= 10):
            errors.append(f"Score for {category} must be between 0 and 10")
    
    return len(errors) == 0, errors

def validate_likelihood_score(likelihood_score):
    """
    Validate likelihood score.
    
    Args:
        likelihood_score: Likelihood score to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(likelihood_score, (int, float)):
        return False, "Likelihood score must be numeric"
    
    if not (0 <= likelihood_score <= 10):
        return False, "Likelihood score must be between 0 and 10"
    
    return True, None

def get_severity_description(category, score):
    """
    Get description for a specific severity score.
    
    Args:
        category (str): Severity category
        score (int): Severity score
        
    Returns:
        str: Description of the severity level
    """
    if category not in SEVERITY_SCALE:
        return "Unknown category"
    
    category_scale = SEVERITY_SCALE[category]
    
    # Find the closest score in the scale
    available_scores = sorted(category_scale.keys())
    closest_score = min(available_scores, key=lambda x: abs(x - score))
    
    return category_scale[closest_score]

def get_likelihood_description(score):
    """
    Get description for a likelihood score.
    
    Args:
        score (int): Likelihood score
        
    Returns:
        str: Description of the likelihood level
    """
    available_scores = sorted(LIKELIHOOD_SCALE.keys())
    closest_score = min(available_scores, key=lambda x: abs(x - score))
    
    return LIKELIHOOD_SCALE[closest_score]["description"]

def calculate_detailed_risk_assessment(likelihood_score, severity_scores):
    """
    Calculate a comprehensive risk assessment with detailed breakdown.
    
    Args:
        likelihood_score (int): Likelihood score 0-10
        severity_scores (dict): Dictionary of severity scores by category
        
    Returns:
        dict: Detailed risk assessment results
    """
    # Validate inputs
    likelihood_valid, likelihood_error = validate_likelihood_score(likelihood_score)
    severity_valid, severity_errors = validate_severity_scores(severity_scores)
    
    if not likelihood_valid or not severity_valid:
        return {
            "valid": False,
            "errors": [likelihood_error] if likelihood_error else [] + severity_errors
        }
    
    # Calculate risk score
    risk_score = calculate_risk_score(likelihood_score, severity_scores)
    risk_level = get_risk_level(risk_score)
    
    # Build detailed assessment
    assessment = {
        "valid": True,
        "likelihood": {
            "score": likelihood_score,
            "description": get_likelihood_description(likelihood_score)
        },
        "severity_breakdown": {},
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_color": get_risk_color(risk_level),
        "recommended_actions": get_recommended_actions(risk_level),
        "max_severity_category": None,
        "max_severity_score": 0
    }
    
    # Process severity scores
    max_severity = 0
    max_category = None
    
    for category, score in severity_scores.items():
        assessment["severity_breakdown"][category] = {
            "score": score,
            "description": get_severity_description(category, score)
        }
        
        if score > max_severity:
            max_severity = score
            max_category = category
    
    assessment["max_severity_category"] = max_category
    assessment["max_severity_score"] = max_severity
    
    return assessment

def get_risk_matrix_grid():
    """
    Generate a risk matrix grid for visualization.
    
    Returns:
        dict: Matrix data for UI rendering
    """
    likelihood_levels = sorted(LIKELIHOOD_SCALE.keys())
    severity_levels = list(range(0, 11, 2))  # 0, 2, 4, 6, 8, 10
    
    matrix_grid = []
    
    for likelihood in likelihood_levels:
        row = []
        for severity in severity_levels:
            risk_score = calculate_risk_score(likelihood, {"example": severity})
            risk_level = get_risk_level(risk_score)
            
            cell = {
                "likelihood": likelihood,
                "severity": severity,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "color": get_risk_color(risk_level)
            }
            row.append(cell)
        matrix_grid.append(row)
    
    return {
        "grid": matrix_grid,
        "likelihood_labels": [LIKELIHOOD_SCALE[l]["label"] for l in likelihood_levels],
        "severity_labels": [str(s) for s in severity_levels]
    }


# --- Hybrid likelihood estimation (semantic + keywords) ---
import os
from .embeddings import embed_query, embed_texts, SBERT_AVAILABLE

KEYWORD_WEIGHTS = {
    "often": 0.9, "frequent": 0.9, "frequently": 0.9, "weekly": 0.8, "monthly": 0.6,
    "sometimes": 0.5, "rarely": 0.3, "once": 0.2, "first time": 0.1, "never": 0.0,
    "recurring": 0.8, "happens": 0.7, "trend": 0.7, "pattern": 0.6
}

def estimate_likelihood_from_text(text: str) -> dict:
    """
    Returns {'score': int 0..10, 'level': str, 'confidence': float 0..1, 'basis': str, 'description': str}
    """
    text_l = (text or "").lower()
    # Keyword heuristic
    kw_score = 0.0
    for k, w in KEYWORD_WEIGHTS.items():
        if k in text_l:
            kw_score = max(kw_score, w*10)
    # Semantic (optional)
    sem_score = 0.0
    sem_conf = 0.0
    if os.environ.get('ENABLE_SBERT','false').lower() == 'true' and SBERT_AVAILABLE:
        labels = [
            "almost impossible", "rare", "unlikely", "possible", "likely", "frequent", "almost certain"
        ]
        label_vecs = embed_texts(labels)
        q = embed_query(text)
        # simple nearest label index → map to score
        best = -1.0; idx = 0
        for i, lv in enumerate(label_vecs):
            import numpy as np
            sc = float(np.dot(q, lv)/(np.linalg.norm(q)*np.linalg.norm(lv) + 1e-9))
            if sc > best:
                best, idx = sc, i
        # map idx (0..6) to 0..10
        sem_score = int(round((idx/6.0)*10))
        sem_conf = max(0.4, min(0.95, (best+1)/2))  # cosine [-1,1]→ [0,1]
    # Combine
    parts = [s for s in [kw_score, sem_score] if s>0]
    if parts:
        combined = max(parts) if len(parts)==1 else int(round(0.5*kw_score + 0.5*sem_score))
        conf = 0.7 if sem_conf==0 else (0.5 + 0.5*sem_conf)
    else:
        combined = 3
        conf = 0.4
    # Clamp 0..10
    combined = max(0, min(10, int(combined)))
    level = get_likelihood_description(combined)
    return {
        "score": combined,
        "level": level,
        "confidence": round(conf,2),
        "basis": "semantic+keywords" if sem_conf>0 else "keywords",
        "description": LIKELIHOOD_SCALE.get(combined, {}).get("description","")
    }
