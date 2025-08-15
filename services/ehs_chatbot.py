# services/ehs_chatbot.py
# Chat-first incident flow aligned to AVOMO/OSHA-style questions/branches.
# Exposes: SmartEHSChatbot, SmartIntentClassifier, five_whys_manager

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import datetime as dt
import re

# ---------------------------------------------------------------------------
# Config
STRICT_PDF_WORDING = True
MAX_FREEFORM_LEN = 4000

# ---------------------------------------------------------------------------
# Centralized prompts
PROMPTS: Dict[str, str] = {
    # Basic Info
    "event_type": "What type of event is this? (Injury/Illness, Vehicle, Environmental, Depot Event, Property Damage, Security Concern, Other)",
    "when": "When did this happen? (YYYY-MM-DD HH:MM, or 'unknown')",
    "where": "Where did it happen? (site/facility and exact location)",
    "description": "Please describe what happened in detail. Include who was involved, what occurred, when it happened, and the sequence of events:",

    # Common follow-ups
    "immediate_actions": "What immediate actions were taken?",
    "witnesses": "List any witnesses (names and contact if known), or type 'None':",
    "enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Injury/Illness
    "inj_name": "Injured/Ill Person — full name:",
    "inj_job_title": "Job title:",
    "inj_phone": "Phone number:",
    "inj_address": "Home address:",
    "inj_city": "City:",
    "inj_state": "State/Province:",
    "inj_zip": "ZIP/Postal code:",
    "inj_status": "Employee status (Full time, Part time, Temporary, Contractor, Visitor, Other):",
    "inj_dept": "Department (if applicable):",
    "inj_supervisor": "Supervisor name (if applicable):",
    "inj_body_part": "Body part affected:",
    "inj_injury_type": "Injury type (e.g., Laceration, Strain, Burn, etc.):",
    "inj_severity": "Injury severity (First Aid, Medical Treatment, Restricted Duty, Lost Time, Fatality):",
    "inj_ppe": "PPE worn? (Yes/No and what PPE):",
    "inj_treatment": "Initial treatment given (if any):",
    "inj_law": "Was emergency service contacted? (Yes/No)",
    "inj_law_details": "If contacted: agency, time called, report # / officer name (or 'N/A'):",

    # Vehicle
    "veh_driver": "Vehicle Incident — driver/operator name:",
    "veh_unit": "Vehicle or equipment involved (plate/unit/ID):",
    "veh_damage": "Describe vehicle/equipment damage (if any):",
    "veh_third_party": "Any third-party vehicle/person involved? (Yes/No)",
    "veh_third_party_details": "If yes, provide details (name, contact, insurer, damage).",
    "veh_photos": "Are photos/videos attached? (Yes/No)",

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

    # Property Damage
    "property_description": "Describe the property damage:",
    "property_cost": "Approximate total cost of loss and repairs:",
    "property_corrective_action": "Immediate corrective action taken:",
    "property_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Security Concern
    "security_event_types": "Type of Security Event (comma-separated): Theft, Trespassing, Vandalism, Workplace Violence/Threat, Other",
    "security_description": "Security Concern description:",
    "security_names_roles": "Name(s) and job title(s) or descriptions:",
    "security_party_type": "Are they Employee(s), Visitor(s), Security Staff, Unknown Individual, or Other?",
    "security_law": "Was law enforcement or emergency services contacted? (Yes/No)",
    "security_law_details": "If contacted: agency, time called, report # or officer name (or 'N/A'):",
    "security_footage": "Is security footage available? (Yes/No/N/A)",
    "security_corrective_actions": "Corrective actions taken (e.g., site secured, access restricted):",
    "security_enablon_confirm": "Was an Enablon report submitted? (Yes/No)",

    # Other
    "other_description": "Please describe the event:",
    "other_actions": "Immediate actions taken:",

    # 5 Whys + CAPA
    "why1": "Why 1?",
    "why2": "Why 2?",
    "why3": "Why 3?",
    "why4": "Why 4?",
    "why5": "Why 5?",
    "capa_action": "Corrective/Preventive Action (what will be done?):",
    "capa_owner": "CAPA owner (person responsible):",
    "capa_due": "CAPA due date (YYYY-MM-DD):",
}

# ---------------------------------------------------------------------------
# Validators
def _is_yes_no(text: str) -> bool:
    return bool(re.fullmatch(r"(?:yes|no|y|n)\b", (text or "").strip().lower()))

def _nonempty(text: str) -> bool:
    return bool((text or "").strip())

def _len_ok(text: str) -> bool:
    return len(text or "") <= MAX_FREEFORM_LEN

# Accept YYYY-MM-DD, YYYY-MM-DD HH:MM / HH-MM, and 'unknown'
def _is_datetime(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.lower() == "unknown":
        return True
    # YYYY-MM-DD or with time (space/T, : or -)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}[:\-]\d{2})?", t):
        return False
    if len(t) > 10:
        t = re.sub(r"([ T]\d{2})-(\d{2})$", r"\1:\2", t)  # HH-MM -> HH:MM
    try:
        if len(t) == 10:
            dt.date.fromisoformat(t)
        else:
            dt.datetime.strptime(t.replace("T", " "), "%Y-%m-%d %H:%M")
        return True
    except Exception:
        return False

VALIDATORS: Dict[str, Tuple] = {
    "yesno": (_is_yes_no, "Please answer Yes or No."),
    "datetime": (_is_datetime, "Please provide a date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM) or 'unknown'."),
    "nonempty": (_nonempty, "This field is required."),
    "lenok": (_len_ok, f"Text too long (>{MAX_FREEFORM_LEN} chars)."),
}

# ---------------------------------------------------------------------------
# Conversation state
@dataclass
class Conversation:
    user_id: str
    queue: List[Tuple[str, str, Optional[str], Optional[List[str]]]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    event_type: Optional[str] = None
    finished: bool = False

_CONV: Dict[str, Conversation] = {}  # in-memory store

# ---------------------------------------------------------------------------
# Event type aliases + single-choice guard
_EVENT_ALIASES = {
    "Injury/Illness": ["injury/illness", "injury", "illness", "injuries"],
    "Vehicle": ["vehicle", "vehichle", "vechicle", "vehicule", "vehichal", "car", "truck", "forklift", "accident"],
    "Environmental": ["environmental", "environment", "spill", "spilled", "leak", "leaked"],
    "Depot Event": ["depot", "depot event"],
    "Property Damage": ["property", "property damage", "damage", "cost"],
    "Security Concern": ["security", "security concern", "theft", "trespass", "vandalism", "violence"],
    "Other": ["other"],
}

def _canonicalize_choice(text: str, options: List[str]) -> Tuple[Optional[str], Optional[str]]:
    raw = (text or "").strip().lower()
    if not raw:
        return None, "This field is required."
    parts = re.split(r"\s*(?:,|/|&|and)\s*", raw)
    hits: List[str] = []
    for p in parts:
        matched = False
        for o in options:
            if p == o.lower():
                hits.append(o); matched = True; break
        if matched:
            continue
        for canon, aliases in _EVENT_ALIASES.items():
            if canon in options and p in aliases:
                hits.append(canon); matched = True; break
    hits = list(dict.fromkeys(hits))  # unique, ordered
    if len(hits) > 1:
        return None, f"Please choose exactly one of: {', '.join(options)} (you mentioned multiple: {', '.join(hits)})."
    if len(hits) == 1:
        return hits[0], None
    return None, f"Please choose exactly one of: {', '.join(options)}"

# ---------------------------------------------------------------------------
# Heuristic extraction from first description
_EVENT_OPTIONS = [
    "Injury/Illness", "Vehicle", "Environmental", "Depot Event",
    "Property Damage", "Security Concern", "Other"
]

_LOCATION_KEYWORDS = [
    "garage", "warehouse", "workshop", "depot", "bay", "dock", "yard", "line",
    "assembly", "plant", "shop", "lab", "laboratory", "office", "parking"
]

def _extract_from_description(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    low = s.lower()
    found: Dict[str, Any] = {}

    # Event types by keyword votes
    votes = set()
    if re.search(r"\binjur|broke|fractur|hospital", low):
        votes.add("Injury/Illness")
    if re.search(r"\bvehicle|car|truck|forklift|accident|collision", low):
        votes.add("Vehicle")
    if re.search(r"\bspill|leak|spilled|leaked|oil\b", low):
        votes.add("Environmental")
    if re.search(r"\bdamage|cost\b", low):
        votes.add("Property Damage")
    if re.search(r"\bsecurity|trespass|theft|vandal", low):
        votes.add("Security Concern")

    if len(votes) == 1:
        found["event_type"] = list(votes)[0]
    elif len(votes) > 1:
        found["event_type_candidates"] = [v for v in _EVENT_OPTIONS if v in votes]

    # Location keyword (best effort)
    for kw in _LOCATION_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            found["where"] = kw.capitalize()
            break

    return found

# ---------------------------------------------------------------------------
# Queue helpers (prevent repeats)
def _skip_answered(convo: Conversation) -> None:
    while convo.queue and convo.queue[0][0] in convo.data:
        convo.queue.pop(0)

def _remove_from_queue(convo: Conversation, key: str) -> None:
    convo.queue = [item for item in convo.queue if item[0] != key]

def _dedupe_queue(convo: Conversation) -> None:
    seen = set(convo.data.keys())
    new_q: List[Tuple[str, str, Optional[str], Optional[List[str]]]] = []
    for item in convo.queue:
        if item[0] in seen:
            continue
        new_q.append(item)
    convo.queue = new_q

# ---------------------------------------------------------------------------
# SmartEHSChatbot
class SmartEHSChatbot:
    """
    Chat-first flow:
      1) Description → (extract & confirm)
      2) When (datetime picker hint)
      3) Where
      4) Event Type → branch (buttons)
      5) 5 Whys + CAPA
    """

    def __init__(self, logger=None):
        self.logger = logger
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
        self.analytics = None  # optional hook

    # ----------------- Public API -----------------
    def start_incident(self, user_id: str) -> Dict[str, Any]:
        convo = Conversation(user_id=user_id)
        _CONV[user_id] = convo
        basics = [
            ("description", PROMPTS["description"], "nonempty", None),
            ("when", PROMPTS["when"], "datetime", None),
            ("where", PROMPTS["where"], "nonempty", None),
            ("event_type", PROMPTS["event_type"], "nonempty", _EVENT_OPTIONS),
        ]
        convo.queue.extend(basics)
        return {
            "reply": f"🚨 Incident Report\n\n{PROMPTS['description']}",
            "next_expected": "description",
            "done": False,
            "ui": "textarea",
        }

    def process_message(self, text: str, user_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if user_id not in _CONV or _CONV[user_id].finished:
            return self.start_incident(user_id)

        convo = _CONV[user_id]
        text = (text or "").strip()

        _skip_answered(convo)
        if not convo.queue:
            return self._finalize(convo)

        field_key, prompt, validator, options = convo.queue[0]

        # -------- Validate current field (do NOT pop on failure) --------
        if validator:
            fn, msg = VALIDATORS.get(validator, (None, None))
            if fn and not fn(text):
                return self._make_prompt(field_key, f"⚠️ {msg or 'Invalid value.'}\n\n{prompt}", options, validator)

        if options and field_key != "event_type":
            t = (text or "").strip()
            if not any(t.lower() == o.lower() for o in (options or [])):
                if STRICT_PDF_WORDING:
                    return self._make_prompt(field_key, f"⚠️ Please choose exactly one of: {', '.join(options)}\n\n{prompt}", options, validator)

        if not _len_ok(text):
            return self._make_prompt(field_key, f"⚠️ {VALIDATORS['lenok'][1]}\n\n{prompt}", options, validator)

        # -------- Save value (with event_type canonicalization) --------
        value_to_save = text
        if options and field_key == "event_type":
            canon, emsg = _canonicalize_choice(text, options)
            if emsg:
                # Re-prompt with **buttons** for clarity
                return self._make_prompt(field_key, f"⚠️ {emsg}", options, validator)
            if canon:
                value_to_save = canon

        convo.data[field_key] = value_to_save
        convo.queue.pop(0)

        if self.analytics:
            try:
                self.analytics("capture", {"user_id": user_id, "field": field_key})
            except Exception:
                pass

        # -------- After capturing description: try to auto-fill and confirm --------
        auto_suggest: Dict[str, Any] = {}
        if field_key == "description":
            inferred = _extract_from_description(value_to_save)
            # If we confidently detected a location and it's not already set
            if "where" in inferred and "where" not in convo.data:
                convo.data["where"] = inferred["where"]
                _remove_from_queue(convo, "where")
                auto_suggest["where"] = inferred["where"]
            # If exactly one event type inferred
            if "event_type" in inferred and "event_type" not in convo.data:
                convo.data["event_type"] = inferred["event_type"]
                convo.event_type = inferred["event_type"]
                _remove_from_queue(convo, "event_type")
                auto_suggest["event_type"] = inferred["event_type"]
                # Enqueue branch immediately
                self._enqueue_branch(convo, inferred["event_type"])
            # If multiple candidates, reorder event_type options to show the likely ones first
            if "event_type_candidates" in inferred and not convo.event_type:
                # Leave the field in the queue but include suggested candidates for UI emphasis
                auto_suggest["event_type_candidates"] = inferred["event_type_candidates"]

        # Deduplicate and skip any answered fields after auto-fill
        _dedupe_queue(convo)
        _skip_answered(convo)

        # If we just captured event_type explicitly, enqueue branch
        if field_key == "event_type":
            et = convo.data["event_type"].strip()
            convo.event_type = et
            self._enqueue_branch(convo, et)
            _dedupe_queue(convo)
            _skip_answered(convo)

        # If queue empty, enqueue 5 Whys + CAPA before finalize
        if not convo.queue and not convo.finished:
            self._enqueue_root_cause_and_action(convo)

        if not convo.queue:
            return self._finalize(convo)

        # Prompt next
        next_key, next_prompt, next_validator, next_options = convo.queue[0]
        # If we have auto suggestions, prepend a short summary before the next prompt
        if auto_suggest:
            summary_lines = []
            if "where" in auto_suggest:
                summary_lines.append(f"• Inferred location: **{auto_suggest['where']}**")
            if "event_type" in auto_suggest:
                summary_lines.append(f"• Inferred event type: **{auto_suggest['event_type']}**")
            if "event_type_candidates" in auto_suggest:
                cands = ", ".join(auto_suggest["event_type_candidates"])
                summary_lines.append(f"• Likely event type(s): {cands}")
            preface = "I pre-filled a few details from your description. You can correct me if needed.\n\n" + "\n".join(summary_lines) + "\n\n"
            return self._make_prompt(next_key, preface + next_prompt, next_options, next_validator, suggestions=auto_suggest)

        return self._make_prompt(next_key, next_prompt, next_options, next_validator)

    # ----------------- Internals -----------------
    def _make_prompt(self, key: str, prompt: str, options: Optional[List[str]], validator: Optional[str], suggestions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"reply": prompt, "next_expected": key, "done": False}
        if options:
            payload["options"] = options  # your UI can render these as quick-reply buttons
            payload["ui"] = "buttons"
        if validator == "yesno":
            payload.setdefault("options", ["Yes", "No"])
            payload["ui"] = "buttons"
        if key == "when":
            payload["ui"] = "datetime"  # hint for date/time picker
        if suggestions:
            payload["suggested"] = suggestions  # to show pre-filled summary
        return payload

    def _enqueue_branch(self, convo: Conversation, event_type: str) -> None:
        et = (event_type or "").strip()
        prompts: List[Tuple[str, str, Optional[str], Optional[List[str]]]] = []

        if et == "Injury/Illness":
            prompts = [
                ("inj_name", PROMPTS["inj_name"], "nonempty", None),
                ("inj_job_title", PROMPTS["inj_job_title"], "nonempty", None),
                ("inj_phone", PROMPTS["inj_phone"], "nonempty", None),
                ("inj_address", PROMPTS["inj_address"], "nonempty", None),
                ("inj_city", PROMPTS["inj_city"], "nonempty", None),
                ("inj_state", PROMPTS["inj_state"], "nonempty", None),
                ("inj_zip", PROMPTS["inj_zip"], "nonempty", None),
                ("inj_status", PROMPTS["inj_status"], "nonempty", None),
                ("inj_dept", PROMPTS["inj_dept"], "nonempty", None),
                ("inj_supervisor", PROMPTS["inj_supervisor"], "nonempty", None),
                ("inj_body_part", PROMPTS["inj_body_part"], "nonempty", None),
                ("inj_injury_type", PROMPTS["inj_injury_type"], "nonempty", None),
                ("inj_severity", PROMPTS["inj_severity"], "nonempty", None),
                ("inj_ppe", PROMPTS["inj_ppe"], "nonempty", None),
                ("inj_treatment", PROMPTS["inj_treatment"], "nonempty", None),
                ("inj_law", PROMPTS["inj_law"], "yesno", None),
                ("inj_law_details", PROMPTS["inj_law_details"], "nonempty", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
                ("enablon_confirm", PROMPTS["enablon_confirm"], "yesno", None),
            ]

        elif et == "Vehicle":
            prompts = [
                ("veh_driver", PROMPTS["veh_driver"], "nonempty", None),
                ("veh_unit", PROMPTS["veh_unit"], "nonempty", None),
                ("veh_damage", PROMPTS["veh_damage"], "nonempty", None),
                ("veh_third_party", PROMPTS["veh_third_party"], "yesno", None),
                ("veh_third_party_details", PROMPTS["veh_third_party_details"], "nonempty", None),
                ("veh_photos", PROMPTS["veh_photos"], "yesno", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
                ("enablon_confirm", PROMPTS["enablon_confirm"], "yesno", None),
            ]

        elif et == "Environmental":
            prompts = [
                ("env_involved_parties", PROMPTS["env_involved_parties"], "nonempty", None),
                ("env_roles", PROMPTS["env_roles"], "nonempty", None),
                ("spill_volume", PROMPTS["spill_volume"], "nonempty", None),
                ("chemicals", PROMPTS["chemicals"], "nonempty", None),
                ("env_description", PROMPTS["env_description"], "nonempty", None),
                ("env_corrective_action", PROMPTS["env_corrective_action"], "nonempty", None),
                ("env_enablon_confirm", PROMPTS["env_enablon_confirm"], "yesno", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
            ]

        elif et == "Depot Event":
            prompts = [
                ("depot_description", PROMPTS["depot_description"], "nonempty", None),
                ("depot_immediate_actions", PROMPTS["depot_immediate_actions"], "nonempty", None),
                ("depot_outcome_lessons", PROMPTS["depot_outcome_lessons"], "nonempty", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
                ("enablon_confirm", PROMPTS["enablon_confirm"], "yesno", None),
            ]

        elif et == "Property Damage":
            prompts = [
                ("property_description", PROMPTS["property_description"], "nonempty", None),
                ("property_cost", PROMPTS["property_cost"], "nonempty", None),
                ("property_corrective_action", PROMPTS["property_corrective_action"], "nonempty", None),
                ("property_enablon_confirm", PROMPTS["property_enablon_confirm"], "yesno", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
            ]

        elif et == "Security Concern":
            prompts = [
                ("security_event_types", PROMPTS["security_event_types"], "nonempty", None),
                ("security_description", PROMPTS["security_description"], "nonempty", None),
                ("security_names_roles", PROMPTS["security_names_roles"], "nonempty", None),
                ("security_party_type", PROMPTS["security_party_type"], "nonempty", None),
                ("security_law", PROMPTS["security_law"], "yesno", None),
                ("security_law_details", PROMPTS["security_law_details"], "nonempty", None),
                ("security_footage", PROMPTS["security_footage"], "nonempty", None),
                ("security_corrective_actions", PROMPTS["security_corrective_actions"], "nonempty", None),
                ("security_enablon_confirm", PROMPTS["security_enablon_confirm"], "yesno", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
            ]

        else:  # Other
            prompts = [
                ("other_description", PROMPTS["other_description"], "nonempty", None),
                ("other_actions", PROMPTS["other_actions"], "nonempty", None),
                ("immediate_actions", PROMPTS["immediate_actions"], "nonempty", None),
                ("witnesses", PROMPTS["witnesses"], "nonempty", None),
                ("enablon_confirm", PROMPTS["enablon_confirm"], "yesno", None),
            ]

        convo.queue.extend(prompts)

    def _enqueue_root_cause_and_action(self, convo: Conversation) -> None:
        rc = [
            ("why1", PROMPTS["why1"], "nonempty", None),
            ("why2", PROMPTS["why2"], "nonempty", None),
            ("why3", PROMPTS["why3"], "nonempty", None),
            ("why4", PROMPTS["why4"], "nonempty", None),
            ("why5", PROMPTS["why5"], "nonempty", None),
            ("capa_action", PROMPTS["capa_action"], "nonempty", None),
            ("capa_owner", PROMPTS["capa_owner"], "nonempty", None),
            ("capa_due", PROMPTS["capa_due"], "nonempty", None),
        ]
        convo.queue.extend(rc)

    def _finalize(self, convo: Conversation) -> Dict[str, Any]:
        try:
            if self.severity_scorer:
                convo.data["computed_severity"] = self.severity_scorer.score(convo.data)
            if self.likelihood_scorer:
                convo.data["computed_likelihood"] = self.likelihood_scorer.score(convo.data)
        except Exception:
            pass

        convo.finished = True
        payload = {
            "ok": True,
            "message": "✅ Incident captured. You can review and submit.",
            "data": dict(convo.data),
            "event_type": convo.event_type,
            "completed": True,
        }
        return {
            "reply": "Thanks. All required info captured. Do you want to submit now?",
            "done": True,
            "result": payload,
        }

# ---------------------------------------------------------------------------
# Backward-compat: SmartIntentClassifier
class SmartIntentClassifier:
    _INTENTS = [
        ("Report incident", r"\breport( an)? incident\b|\bincident report\b|\bstart .*incident\b"),
        ("Safety concern", r"\bsafety concern\b|\bnear miss\b|\bunsafe\b"),
        ("Find SDS", r"\b(find )?sds\b|\bsafety data sheet\b"),
        ("Risk assessment", r"\brisk assessment\b|\berc\b|\blikelihood\b"),
        ("What's urgent?", r"\burgent\b|\bpriority\b|\boverdue\b"),
        ("Help with this page", r"\btour\b|\bgetting started\b|\bguide\b|\bonboard\b"),
    ]
    def quick_intent(self, text: str) -> str:
        t = (text or "").lower().strip()
        for label, pattern in self._INTENTS:
            if re.search(pattern, t):
                return label
        return "Unknown"
    def classify_intent(self, text: str) -> Tuple[str, float]:
        t = (text or "").lower().strip()
        for label, pattern in self._INTENTS:
            if re.search(pattern, t):
                return label, 0.95
        return "Unknown", 0.0

# ---------------------------------------------------------------------------
# Backward-compat: five_whys_manager
class _FiveWhysManager:
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
    def start(self, user_id: str, problem: str):
        self._sessions[user_id] = {"problem": problem or "", "whys": []}
    def answer(self, user_id: str, answer: str):
        sess = self._sessions.setdefault(user_id, {"problem": "", "whys": []})
        if answer:
            sess["whys"].append(answer.strip())
        return sess
    def is_complete(self, user_id: str) -> bool:
        sess = self._sessions.get(user_id)
        return bool(sess and len(sess.get("whys", [])) >= 5)
    def get(self, user_id: str):
        return self._sessions.get(user_id)

five_whys_manager = _FiveWhysManager()
