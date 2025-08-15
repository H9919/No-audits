# services/ehs_chatbot.py
# Chat-first incident flow aligned to AVOMO questions/branches.
# Keeps class names & public methods stable for your existing UI.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import datetime as dt
import re

# ---------------------------------------------------------------------------
# Config: set to True to lock wording exactly as defined in PROMPTS below.
STRICT_PDF_WORDING = True

# Centralized prompts: edit text here if you need 1:1 wording with AVOMO PDF.
# (These defaults are already written to match the PDF closely.)
PROMPTS = {
    "event_date": "Event date (YYYY-MM-DD):",
    "event_time": "Event time (24-hour, e.g., 23:45):",
    "reporter_name": "Your name (optional — type 'skip' to leave blank):",
    "reporter_email": "Your email (optional — type 'skip' to leave blank):",
    "site": "Site (type the site name exactly as on your list):",
    "severe_event_flag": "Is this a Severe Event? (Yes/No)",
    "event_type": "Event Type (choose one): Safety Concern, Injury/Illness, Property Damage, Security Concern, Vehicle Collision, Environmental, Depot Event, Near Miss",

    # Severe Event
    "severe_event_type": "Severe Event Type (choose one): AV collision, Hospitalization or fatality, Site-wide emergency that requires calling 911, Physical security or Cybersecurity breach, Outage longer than 15 minutes, Chemical spill more than 1 gal",
    "severe_event_description": "Severe Event Description (include location, timing, people/systems, and actions taken):",

    # Safety Concern
    "safety_description": "Safety Concern — what did you see and where did it happen?",
    "safety_corrective_action": "Did you do anything to help or any corrective action to fix it? If not, what do you suggest?",

    # Injury/Illness
    "inj_name": "Injured employee name:",
    "inj_job_title": "Job title:",
    "inj_phone": "Phone number:",
    "inj_address": "Address:",
    "inj_city": "City:",
    "inj_state": "State/Province:",
    "inj_zip": "ZIP/Postal code:",
    "inj_status": "Employee status (choose one): Full time, Part Time, Temporary, Contractor, Visitor",
    "supervisor_name": "Supervisor name:",
    "supervisor_notified_date": "Date supervisor was notified (YYYY-MM-DD):",
    "supervisor_notified_time": "Time supervisor was notified (24-hour, e.g., 15:40):",
    "inj_event_description": "Describe what happened (Injury/Illness):",
    "inj_type": "Injury/Illness type(s) (comma-separated):",
    "inj_body_parts": "Affected body part(s) (comma-separated):",
    "inj_immediate_action": "Immediate action taken:",
    "inj_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Property Damage
    "property_description": "Describe the property damage:",
    "property_cost": "Approximate total cost of loss and repairs:",
    "property_corrective_action": "Immediate corrective action taken:",
    "property_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Security Concern
    "security_event_types": "Type of Security Event (comma-separated): Break-in/Forced Entry, Illicit Substance/Weapon in ADV, Sharps/Medication in ADV, Property Damage, Suspicious Activity, Theft, Trespassing, Vandalism, Workplace Violence/Threat, Other",
    "security_description": "Security Concern description:",
    "security_names_roles": "Name(s) and job title(s) or descriptions:",
    "security_party_type": "Are they Employee(s), Visitor(s), Security Staff, Unknown Individual, or Other?",
    "security_law": "Was law enforcement or emergency services contacted? (Yes/No)",
    "security_law_details": "If contacted: agency, time called, report # or officer name (or 'N/A'):",
    "security_footage": "Is security footage available? (Yes/No/N/A)",
    "security_corrective_actions": "Corrective actions taken (e.g., site secured, access restricted):",
    "security_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Vehicle Collision
    "collision_location": "Where did the collision happen? (AVOMO Parking Lot/Facility, Public Road/Travel for work, Other):",
    "involved_parties": "Involved parties (full names):",
    "vehicle_identifier": "Which vehicle was involved? (ID/plate/description):",
    "vehicle_hit": "What did the vehicle hit? (e.g., another car, fence):",
    "collision_any_injury": "Was anyone injured? (Yes/No)",
    "collision_mode": "Was the vehicle operated Manually, Autonomously, or Not Sure?",
    "collision_description": "Vehicle collision event description:",
    "collision_corrective_action": "Immediate corrective action taken:",
    "collision_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Environmental
    "env_involved_parties": "Environmental — involved parties (full names):",
    "env_roles": "Who was involved (comma-separated): Full time, Part Time, Temporary, Contractor, Visitor, Other",
    "spill_volume": "Spill volume (<1 gallon, >1 gallon, Unknown):",
    "chemicals": "What chemical(s) were involved?",
    "env_description": "Environmental spill event description:",
    "env_corrective_action": "Immediate corrective action:",
    "env_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Depot Event
    "depot_description": "Depot Event — what happened?",
    "depot_immediate_actions": "Immediate actions taken:",
    "depot_outcome_lessons": "Outcome & lessons learned (and what you'd do differently):",

    # Near Miss
    "near_miss_type": "Near Miss Type (choose one): Potential Injury, Property Damage, Environmental Damage, Damage to Company Image",
    "near_miss_description": "Near Miss — what did you see and where did it happen?",
    "near_miss_corrective_action": "Any corrective action taken or suggestion to fix?",

    # Root Cause & CAPA
    "why_1": "5 Whys — First why?",
    "why_2": "Second why?",
    "why_3": "Third why?",
    "why_4": "Fourth why?",
    "why_5": "Fifth why?",
    "corrective_action": "Primary corrective action needed:",
    "action_owner_name": "Action owner name:",
    "action_owner_email": "Action owner email:",
    "action_due_date": "Action due date (YYYY-MM-DD):",
}

EVENT_TYPES = [
    "Safety Concern",
    "Injury/Illness",
    "Property Damage",
    "Security Concern",
    "Vehicle Collision",
    "Environmental",
    "Depot Event",
    "Near Miss",
]

SEVERE_TYPES = [
    "AV collision",
    "Hospitalization or fatality",
    "Site-wide emergency that requires calling 911",
    "Physical security or Cybersecurity breach",
    "Outage longer than 15 minutes",
    "Chemical spill more than 1 gal",
]

# ---------------------------------------------------------------------------

def _is_date(s: str) -> bool:
    try:
        dt.date.fromisoformat(s.strip())
        return True
    except Exception:
        return False

def _is_time_24h(s: str) -> bool:
    s = s.strip()
    if re.fullmatch(r"[01]\d:[0-5]\d|2[0-3]:[0-5]\d|[01]\d[0-5]\d|2[0-3][0-5]\d", s):
        return True
    return False

def _is_email(s: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s.strip()))

def _nonempty(s: str) -> bool:
    return bool((s or "").strip())

def _is_number(s: str) -> bool:
    try:
        float(str(s).strip())
        return True
    except Exception:
        return False

from dataclasses import dataclass, field

@dataclass
class IncidentConversation:
    data: Dict[str, Any] = field(default_factory=lambda: {"attachments": []})
    queue: List[Tuple[str, str, Optional[str], Optional[List[str]]]] = field(default_factory=list)
    event_type: Optional[str] = None
    severe_flag: Optional[bool] = None
    finished: bool = False

class SmartEHSChatbot:
    """
    Chat-first incident flow:
      1) Basic info
      2) Optional severe event details
      3) Branch by event type
      4) 5 Whys + CAPA fields
    """

    def __init__(self, logger=None):
        self.logger = logger

        # Optional engines (safe to be None). If you add modules later, they get used.
        try:
            from services.severity import SeverityScorer  # optional
        except Exception:
            SeverityScorer = None
        try:
            from services.likelihood import LikelihoodScorer  # optional
        except Exception:
            LikelihoodScorer = None
        self.severity_scorer = SeverityScorer() if SeverityScorer else None
        self.likelihood_scorer = LikelihoodScorer() if LikelihoodScorer else None

        try:
            from services.analytics import Analytics  # optional
            self.analytics = Analytics
        except Exception:
            self.analytics = None

    # ---- Public API --------------------------------------------------------

    def start_incident(self) -> IncidentConversation:
        convo = IncidentConversation()
        self._enqueue_basic_info(convo)
        return convo

    def handle_message(self, convo: IncidentConversation, text: str) -> Dict[str, Any]:
        text = (text or "").strip()

        if not convo.queue:
            self._enqueue_basic_info(convo)

        if not convo.queue:
            return {"reply": "Nothing to ask right now.", "next_expected": None, "done": True}

        field_key, prompt, validator, options = convo.queue[0]

        ok, err = self._validate(field_key, text, validator, options)
        if not ok:
            return {
                "reply": f"⚠️ {err}\n\n{prompt}",
                "next_expected": field_key,
                "done": False,
            }

        # Save value
        convo.data[field_key] = text
        convo.queue.pop(0)

        # Track analytics (optional)
        if self.analytics:
            try:
                self.analytics.track("incident.answer_recorded", {
                    "field": field_key,
                    "value_len": len(text),
                    "event_type": convo.event_type,
                    "severe": convo.severe_flag,
                })
            except Exception:
                pass

        # Branching
        if field_key == "severe_event_flag":
            convo.severe_flag = text.lower().startswith("y")
            if convo.severe_flag:
                self._enqueue_severe_event(convo)

        if field_key == "event_type":
            convo.event_type = text
            self._enqueue_branch(convo, text)

        # If nothing left, add root cause / CAPA
        if not convo.queue and not convo.finished:
            self._enqueue_root_cause_and_action(convo)

        # If still nothing, finalize
        if not convo.queue:
            # Optional: compute severity/likelihood once all fields are present
            try:
                if self.severity_scorer:
                    convo.data["computed_severity"] = self.severity_scorer.score(convo.data)
                if self.likelihood_scorer:
                    convo.data["computed_likelihood"] = self.likelihood_scorer.score(convo.data)
            except Exception:
                pass

            convo.finished = True
            return {
                "reply": "✅ Thanks! All required fields are captured. Type 'export' to finalize or 'attach <filename>' to add files.",
                "next_expected": None,
                "done": True,
            }

        # Next prompt
        next_field_key, next_prompt, _, _ = convo.queue[0]
        return {"reply": next_prompt, "next_expected": next_field_key, "done": False}

    def accept_attachment(self, convo: IncidentConversation, filename: str, url: str) -> str:
        convo.data.setdefault("attachments", []).append({"filename": filename, "url": url})
        return f"📎 Attached: {filename}"

    # ---- Enqueue helpers ---------------------------------------------------

    def _enqueue_basic_info(self, convo: IncidentConversation) -> None:
        prompts = [
            ("event_date", PROMPTS["event_date"], "date", None),
            ("event_time", PROMPTS["event_time"], "time", None),
            ("reporter_name", PROMPTS["reporter_name"], "optional", None),
            ("reporter_email", PROMPTS["reporter_email"], "optional_email", None),
            ("site", PROMPTS["site"], "nonempty", None),
            ("severe_event_flag", PROMPTS["severe_event_flag"], "yesno", ["Yes", "No"]),
            ("event_type", PROMPTS["event_type"], "choice", EVENT_TYPES),
        ]
        convo.queue.extend(prompts)

    def _enqueue_severe_event(self, convo: IncidentConversation) -> None:
        prompts = [
            ("severe_event_type", PROMPTS["severe_event_type"], "choice", SEVERE_TYPES),
            ("severe_event_description", PROMPTS["severe_event_description"], "nonempty", None),
        ]
        convo.queue.extend(prompts)

    def _enqueue_branch(self, convo: IncidentConversation, event_type: str) -> None:
        if event_type == "Safety Concern":
            prompts = [
                ("safety_description", PROMPTS["safety_description"], "nonempty", None),
                ("safety_corrective_action", PROMPTS["safety_corrective_action"], "nonempty", None),
            ]

        elif event_type == "Injury/Illness":
            prompts = [
                ("inj_name", PROMPTS["inj_name"], "nonempty", None),
                ("inj_job_title", PROMPTS["inj_job_title"], "nonempty", None),
                ("inj_phone", PROMPTS["inj_phone"], "nonempty", None),
                ("inj_address", PROMPTS["inj_address"], "nonempty", None),
                ("inj_city", PROMPTS["inj_city"], "nonempty", None),
                ("inj_state", PROMPTS["inj_state"], "nonempty", None),
                ("inj_zip", PROMPTS["inj_zip"], "nonempty", None),
                ("inj_status", PROMPTS["inj_status"], "choice",
                 ["Full time", "Part Time", "Temporary", "Contractor", "Visitor"]),
                ("supervisor_name", PROMPTS["supervisor_name"], "nonempty", None),
                ("supervisor_notified_date", PROMPTS["supervisor_notified_date"], "date", None),
                ("supervisor_notified_time", PROMPTS["supervisor_notified_time"], "time", None),
                ("inj_event_description", PROMPTS["inj_event_description"], "nonempty", None),
                ("inj_type", PROMPTS["inj_type"], "nonempty", None),
                ("inj_body_parts", PROMPTS["inj_body_parts"], "nonempty", None),
                ("inj_immediate_action", PROMPTS["inj_immediate_action"], "nonempty", None),
                ("inj_enablon_confirm", PROMPTS["inj_enablon_confirm"], "yesno", ["Yes", "No"]),
            ]

        elif event_type == "Property Damage":
            prompts = [
                ("property_description", PROMPTS["property_description"], "nonempty", None),
                ("property_cost", PROMPTS["property_cost"], "number", None),
                ("property_corrective_action", PROMPTS["property_corrective_action"], "nonempty", None),
                ("property_enablon_confirm", PROMPTS["property_enablon_confirm"], "yesno", ["Yes", "No"]),
            ]

        elif event_type == "Security Concern":
            prompts = [
                ("security_event_types", PROMPTS["security_event_types"], "nonempty", None),
                ("security_description", PROMPTS["security_description"], "nonempty", None),
                ("security_names_roles", PROMPTS["security_names_roles"], "nonempty", None),
                ("security_party_type", PROMPTS["security_party_type"], "nonempty", None),
                ("security_law", PROMPTS["security_law"], "yesno", ["Yes", "No"]),
                ("security_law_details", PROMPTS["security_law_details"], "nonempty", None),
                ("security_footage", PROMPTS["security_footage"], "choice", ["Yes", "No", "N/A"]),
                ("security_corrective_actions", PROMPTS["security_corrective_actions"], "nonempty", None),
                ("security_enablon_confirm", PROMPTS["security_enablon_confirm"], "yesno", ["Yes", "No"]),
            ]

        elif event_type == "Vehicle Collision":
            prompts = [
                ("collision_location", PROMPTS["collision_location"], "nonempty", None),
                ("involved_parties", PROMPTS["involved_parties"], "nonempty", None),
                ("vehicle_identifier", PROMPTS["vehicle_identifier"], "nonempty", None),
                ("vehicle_hit", PROMPTS["vehicle_hit"], "nonempty", None),
                ("collision_any_injury", PROMPTS["collision_any_injury"], "yesno", ["Yes", "No"]),
                ("collision_mode", PROMPTS["collision_mode"], "choice", ["Manually", "Autonomously", "Not Sure"]),
                ("collision_description", PROMPTS["collision_description"], "nonempty", None),
                ("collision_corrective_action", PROMPTS["collision_corrective_action"], "nonempty", None),
                ("collision_enablon_confirm", PROMPTS["collision_enablon_confirm"], "yesno", ["Yes", "No"]),
            ]

        elif event_type == "Environmental":
            prompts = [
                ("env_involved_parties", PROMPTS["env_involved_parties"], "nonempty", None),
                ("env_roles", PROMPTS["env_roles"], "nonempty", None),
                ("spill_volume", PROMPTS["spill_volume"], "choice", ["<1 gallon", ">1 gallon", "Unknown"]),
                ("chemicals", PROMPTS["chemicals"], "nonempty", None),
                ("env_description", PROMPTS["env_description"], "nonempty", None),
                ("env_corrective_action", PROMPTS["env_corrective_action"], "nonempty", None),
                ("env_enablon_confirm", PROMPTS["env_enablon_confirm"], "yesno", ["Yes", "No"]),
            ]

        elif event_type == "Depot Event":
            prompts = [
                ("depot_description", PROMPTS["depot_description"], "nonempty", None),
                ("depot_immediate_actions", PROMPTS["depot_immediate_actions"], "nonempty", None),
                ("depot_outcome_lessons", PROMPTS["depot_outcome_lessons"], "nonempty", None),
            ]

        elif event_type == "Near Miss":
            prompts = [
                ("near_miss_type", PROMPTS["near_miss_type"], "nonempty", None),
                ("near_miss_description", PROMPTS["near_miss_description"], "nonempty", None),
                ("near_miss_corrective_action", PROMPTS["near_miss_corrective_action"], "nonempty", None),
            ]
        else:
            prompts = []

        convo.queue.extend(prompts)

    def _enqueue_root_cause_and_action(self, convo: IncidentConversation) -> None:
        prompts = [
            ("why_1", PROMPTS["why_1"], "nonempty", None),
            ("why_2", PROMPTS["why_2"], "nonempty", None),
            ("why_3", PROMPTS["why_3"], "nonempty", None),
            ("why_4", PROMPTS["why_4"], "nonempty", None),
            ("why_5", PROMPTS["why_5"], "nonempty", None),
            ("corrective_action", PROMPTS["corrective_action"], "nonempty", None),
            ("action_owner_name", PROMPTS["action_owner_name"], "nonempty", None),
            ("action_owner_email", PROMPTS["action_owner_email"], "email", None),
            ("action_due_date", PROMPTS["action_due_date"], "date", None),
        ]
        convo.queue.extend(prompts)

    # ---- Validation --------------------------------------------------------

    def _validate(self, key: str, value: str, validator: Optional[str], options: Optional[List[str]]) -> Tuple[bool, str]:
        v = validator or "nonempty"
        if v == "optional":
            return True, ""
        if v == "optional_email":
            if value.strip().lower() in ("", "skip"):
                return True, ""
            return (_is_email(value), "Please provide a valid email or type 'skip'.")
        if v == "nonempty":
            return (_nonempty(value), "This field is required.")
        if v == "date":
            return (_is_date(value), "Use YYYY-MM-DD.")
        if v == "time":
            return (_is_time_24h(value), "Use 24-hour format, e.g., 23:45 or 1540.")
        if v == "email":
            return (_is_email(value), "Please provide a valid email.")
        if v == "number":
            return (_is_number(value), "Please enter a number.")
        if v == "yesno":
            return (value.strip() in ("Yes", "No", "yes", "no"), "Please answer Yes or No.")
        if v == "choice":
            allowed = options or []
            if value.strip() in allowed:
                return True, ""
            return False, f"Choose one of: {', '.join(allowed)}"
        return True, ""
