# services/incident_validator.py
# Completeness & validation helpers for incidents.
# Includes AVOMO -> canonical type mapping so your validator keeps working
# when the chatbot uses AVOMO event labels.

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

# ---- Optional risk/scoring hooks (safe if missing) ------------------------
try:
    # Expect these in your codebase. If not present, we degrade gracefully.
    from services.risk_matrix import (
        calculate_risk_score,    # def calculate_risk_score(severity:int, likelihood:int)->int
        get_risk_level,          # def get_risk_level(score:int)->str
        SEVERITY_SCALE,          # e.g., {"Minor":1,...}
        LIKELIHOOD_SCALE,        # e.g., {"Rare":1,...}
    )
except Exception:
    calculate_risk_score = None
    get_risk_level = None
    SEVERITY_SCALE = {"Minor": 1, "Moderate": 2, "Major": 3, "Critical": 4}
    LIKELIHOOD_SCALE = {"Rare": 1, "Unlikely": 2, "Possible": 3, "Likely": 4}

# ----------------------------------------------------------------------------
# Canonical incident types used by validator & dashboards.
# (These may exist in your project already—keeping them here for completeness.)
CANONICAL_TYPES = [
    "injury",
    "vehicle",
    "environmental",
    "property",
    "security",
    "depot",
    "near_miss",
    "emergency",
    "other",
]

# Map AVOMO event names (exact labels the chatbot collects) → canonical keys.
AVOMO_EVENT_MAP: Dict[str, str] = {
    "safety concern": "other",         # or "near_miss" if you prefer
    "injury/illness": "injury",
    "property damage": "property",
    "security concern": "security",
    "vehicle collision": "vehicle",
    "environmental": "environmental",
    "depot event": "depot",
    "near miss": "near_miss",
    "emergency": "emergency",
}

# Fields required per canonical type for "completeness" (adjust freely).
# NOTE: These are *validation* keys, not the exact chat prompts.
REQUIRED_BY_TYPE: Dict[str, List[str]] = {
    "injury": [
        "inj_name", "inj_job_title", "inj_phone", "inj_address",
        "inj_city", "inj_state", "inj_zip", "inj_status",
        "supervisor_name", "supervisor_notified_date", "supervisor_notified_time",
        "inj_event_description", "inj_type", "inj_body_parts", "inj_immediate_action",
        "inj_enablon_confirm"
    ],
    "vehicle": [
        "collision_location", "involved_parties", "vehicle_identifier", "vehicle_hit",
        "collision_any_injury", "collision_mode", "collision_description",
        "collision_corrective_action", "collision_enablon_confirm"
    ],
    "environmental": [
        "env_involved_parties", "env_roles", "spill_volume", "chemicals",
        "env_description", "env_corrective_action", "env_enablon_confirm"
    ],
    "property": [
        "property_description", "property_cost", "property_corrective_action",
        "property_enablon_confirm"
    ],
    "security": [
        "security_event_types", "security_description", "security_names_roles",
        "security_party_type", "security_law", "security_law_details",
        "security_footage", "security_corrective_actions", "security_enablon_confirm"
    ],
    "depot": [
        "depot_description", "depot_immediate_actions", "depot_outcome_lessons"
    ],
    "near_miss": [
        "near_miss_type", "near_miss_description", "near_miss_corrective_action"
    ],
    "emergency": [
        # add if you have separate emergency flow/fields
    ],
    "other": [
        # lightweight catch-all (e.g., safety concern)
        "safety_description", "safety_corrective_action"
    ]
}

# If a record is marked severe, require these too.
REQUIRED_IF_SEVERE: List[str] = [
    "severe_event_type",
    "severe_event_description",
]

# Baseline required fields (shared across all incidents) – keep modest.
BASE_REQUIRED: List[str] = [
    "event_date",
    "event_time",
    "site",
    "event_type",
    "severe_event_flag",
]

# ----------------------------------------------------------------------------
def _get(rec: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safe getter that tries multiple keys including nested 'chatbot_data'."""
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    # try nested chatbot_data
    cbd = rec.get("chatbot_data") or {}
    for k in keys:
        if k in cbd and cbd[k] not in (None, ""):
            return cbd[k]
    return default

def normalize_incident_type(rec: Dict[str, Any]) -> str:
    """
    Normalize to canonical type using AVOMO_EVENT_MAP.
    Accepts values from `type`, `event_type`, or nested `chatbot_data.event_type`.
    """
    raw_type = (
        _get(rec, "type")
        or _get(rec, "event_type")
        or "other"
    )
    s = str(raw_type).strip().lower()
    mapped = AVOMO_EVENT_MAP.get(s, s).replace(" ", "_")
    if mapped not in CANONICAL_TYPES:
        return "other"
    return mapped

def _is_truthy_yes(val: Any) -> bool:
    return str(val).strip().lower().startswith("y")

# ----------------------------------------------------------------------------
def get_required_fields_for_type(rec: Dict[str, Any]) -> List[str]:
    """Compute required fields for this record (base + by-type + severe-conditional)."""
    req = list(BASE_REQUIRED)
    inc_type = normalize_incident_type(rec)
    req += REQUIRED_BY_TYPE.get(inc_type, [])
    if _is_truthy_yes(_get(rec, "severe_event_flag", default="no")):
        req += REQUIRED_IF_SEVERE
    # Remove duplicates while preserving order
    seen = set()
    out: List[str] = []
    for k in req:
        if k not in seen:
            out.append(k); seen.add(k)
    return out

def validate_record(rec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Returns (is_valid, missing_fields_list).
    An incident is 'valid' when all required fields are present and non-empty.
    """
    required = get_required_fields_for_type(rec)
    missing: List[str] = []
    for key in required:
        val = _get(rec, key)
        if val in (None, ""):
            missing.append(key)
    return (len(missing) == 0, missing)

def compute_completeness(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a dict with % completeness, missing fields, and normalized type.
    Example:
      {
        "type": "vehicle",
        "required_count": 12,
        "present_count": 9,
        "missing": ["vehicle_hit", "collision_mode", "collision_enablon_confirm"],
        "percent": 75.0
      }
    """
    required = get_required_fields_for_type(rec)
    present_count = 0
    missing: List[str] = []
    for key in required:
        val = _get(rec, key)
        if val in (None, ""):
            missing.append(key)
        else:
            present_count += 1
    total = len(required) if required else 1
    percent = round((present_count / total) * 100.0, 2)
    return {
        "type": normalize_incident_type(rec),
        "required_count": total,
        "present_count": present_count,
        "missing": missing,
        "percent": percent,
    }

# ----------------------------------------------------------------------------
# Optional: a compact scoring helper that uses your risk_matrix if available.
class EnhancedIncidentScoring:
    """
    Example scorer. If your project already has a richer class, keep that one.
    This version:
      - accepts either numeric severity/likelihood or label keys that exist in
        SEVERITY_SCALE / LIKELIHOOD_SCALE
      - falls back to a conservative mid score if nothing is set
    """
    DEFAULT_SEVERITY = "Moderate"
    DEFAULT_LIKELIHOOD = "Possible"

    def _resolve_scale_value(self, scale: Dict[str, int], val: Any, default_key: str) -> int:
        if isinstance(val, (int, float)):
            return int(val)
        s = str(val or "").strip()
        if s in scale:
            return int(scale[s])
        return int(scale.get(default_key, 2))

    def score(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        sev_val = _get(rec, "severity", default=self.DEFAULT_SEVERITY)
        lik_val = _get(rec, "likelihood", default=self.DEFAULT_LIKELIHOOD)

        sev_num = self._resolve_scale_value(SEVERITY_SCALE, sev_val, self.DEFAULT_SEVERITY)
        lik_num = self._resolve_scale_value(LIKELIHOOD_SCALE, lik_val, self.DEFAULT_LIKELIHOOD)

        if calculate_risk_score:
            total = int(calculate_risk_score(sev_num, lik_num))
        else:
            total = int(sev_num * lik_num)  # simple fallback

        level = get_risk_level(total) if get_risk_level else (
            "Low" if total <= 3 else "Medium" if total <= 8 else "High"
        )

        return {
            "severity_numeric": sev_num,
            "likelihood_numeric": lik_num,
            "risk_score": total,
            "risk_level": level,
        }

# ----------------------------------------------------------------------------
# Convenience: top-level API that many routes call.

def evaluate_incident(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    One-shot evaluation: validation + completeness + (optional) risk scoring.
    """
    valid, missing = validate_record(rec)
    comp = compute_completeness(rec)

    # Attach scoring if available
    try:
        scorer = EnhancedIncidentScoring()
        scoring = scorer.score(rec)
    except Exception:
        scoring = {}

    return {
        "valid": valid,
        "missing": missing,
        "completeness": comp,
        "scoring": scoring,
        "type": comp["type"],
    }
