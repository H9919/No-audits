# services/enhanced_ehs_chatbot.py
# Enhanced Chat-first incident flow with smart extraction and better UX
# Key improvements:
# - Multi-incident detection from initial description
# - Smart confirmation prompts with extracted data
# - Better button/dropdown UI hints
# - More intelligent field extraction

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set
import datetime as dt
import re
import json

# ---------------------------------------------------------------------------
# Config
STRICT_PDF_WORDING = True
MAX_FREEFORM_LEN = 4000

# ---------------------------------------------------------------------------
# Enhanced prompts with UI hints
PROMPTS: Dict[str, str] = {
    # Basic Info
    "event_type": "What type of event is this?",
    "when": "When did this happen?",
    "where": "Where did it happen? (site/facility and exact location)",
    "description": "Please describe what happened in detail. Include who was involved, what occurred, when it happened, and the sequence of events:",

    # Common follow-ups
    "immediate_actions": "What immediate actions were taken?",
    "witnesses": "List any witnesses (names and contact if known), or type 'None':",
    "enablon_confirm": "Was an Enablon report submitted?",

    # Injury/Illness
    "inj_name": "Injured/Ill Person — full name:",
    "inj_job_title": "Job title:",
    "inj_phone": "Phone number:",
    "inj_address": "Home address:",
    "inj_city": "City:",
    "inj_state": "State/Province:",
    "inj_zip": "ZIP/Postal code:",
    "inj_status": "Employee status:",
    "inj_dept": "Department (if applicable):",
    "inj_supervisor": "Supervisor name (if applicable):",
    "inj_body_part": "Body part affected:",
    "inj_injury_type": "Injury type:",
    "inj_severity": "Injury severity:",
    "inj_ppe": "PPE worn?",
    "inj_treatment": "Initial treatment given (if any):",
    "inj_law": "Was emergency service contacted?",
    "inj_law_details": "If contacted: agency, time called, report # / officer name (or 'N/A'):",

    # Vehicle
    "veh_driver": "Vehicle Incident — driver/operator name:",
    "veh_unit": "Vehicle or equipment involved (plate/unit/ID):",
    "veh_damage": "Describe vehicle/equipment damage (if any):",
    "veh_third_party": "Any third-party vehicle/person involved?",
    "veh_third_party_details": "If yes, provide details (name, contact, insurer, damage).",
    "veh_photos": "Are photos/videos attached?",

    # Environmental  
    "env_involved_parties": "Environmental — involved parties (full names):",
    "env_roles": "Who was involved:",
    "spill_volume": "Spill volume:",
    "chemicals": "What chemical(s) were involved?",
    "env_description": "Environmental spill event description:",
    "env_corrective_action": "Immediate corrective action:",
    "env_enablon_confirm": "Was an Enablon report submitted?",

    # Property Damage
    "property_description": "Describe the property damage:",
    "property_cost": "Approximate total cost of loss and repairs:",
    "property_corrective_action": "Immediate corrective action taken:",
    "property_enablon_confirm": "Was an Enablon report submitted?",

    # Security Concern
    "security_event_types": "Type of Security Event:",
    "security_description": "Security Concern description:",
    "security_names_roles": "Name(s) and job title(s) or descriptions:",
    "security_party_type": "Are they:",
    "security_law": "Was law enforcement or emergency services contacted?",
    "security_law_details": "If contacted: agency, time called, report # or officer name (or 'N/A'):",
    "security_footage": "Is security footage available?",
    "security_corrective_actions": "Corrective actions taken:",
    "security_enablon_confirm": "Was an Enablon report submitted?",

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
    "capa_due": "CAPA due date:",
}

# Enhanced options mapping with UI hints
FIELD_OPTIONS: Dict[str, Dict[str, Any]] = {
    "event_type": {
        "options": ["Injury/Illness", "Vehicle", "Environmental", "Depot Event", "Property Damage", "Security Concern", "Other"],
        "ui": "buttons"
    },
    "inj_status": {
        "options": ["Full time", "Part time", "Temporary", "Contractor", "Visitor", "Other"],
        "ui": "buttons"
    },
    "inj_injury_type": {
        "options": [
            "Cut, Laceration, or Puncture", "Burn", "Fracture", "Bruise/Contusion", 
            "Sprain or Strain", "Dislocation", "Crush Injury", "Other"
        ],
        "ui": "dropdown"
    },
    "inj_body_part": {
        "options": [
            "Head/Scalp", "Eyes", "Neck", "Shoulders", "Back", "Arms", 
            "Hands/Fingers", "Torso/Chest", "Legs", "Feet/Toes", "Other"
        ],
        "ui": "dropdown"
    },
    "inj_severity": {
        "options": ["First Aid", "Medical Treatment", "Restricted Duty", "Lost Time", "Fatality"],
        "ui": "buttons"
    },
    "spill_volume": {
        "options": ["<1 gallon", ">1 gallon", "Unknown"],
        "ui": "buttons"
    },
    "env_roles": {
        "options": ["Full time", "Part Time", "Temporary", "Contractor", "Visitor", "Other"],
        "ui": "buttons",
        "multi_select": True
    },
    "security_event_types": {
        "options": ["Theft", "Trespassing", "Vandalism", "Workplace Violence/Threat", "Other"],
        "ui": "buttons",
        "multi_select": True
    },
    "security_party_type": {
        "options": ["Employee(s)", "Visitor(s)", "Security Staff", "Unknown Individual", "Other"],
        "ui": "buttons"
    },
    "security_footage": {
        "options": ["Yes", "No", "N/A"],
        "ui": "buttons"
    },
    "enablon_confirm": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "env_enablon_confirm": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "property_enablon_confirm": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "security_enablon_confirm": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "inj_ppe": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "inj_law": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "veh_third_party": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "veh_photos": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "security_law": {
        "options": ["Yes", "No"],
        "ui": "buttons"
    },
    "when": {
        "ui": "datetime"
    },
    "capa_due": {
        "ui": "date"
    }
}

# ---------------------------------------------------------------------------
# Enhanced validators
def _is_yes_no(text: str) -> bool:
    return bool(re.fullmatch(r"(?:yes|no|y|n)\b", (text or "").strip().lower()))

def _nonempty(text: str) -> bool:
    return bool((text or "").strip())

def _len_ok(text: str) -> bool:
    return len(text or "") <= MAX_FREEFORM_LEN

def _is_datetime(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.lower() == "unknown":
        return True
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}[:\-]\d{2})?", t):
        return False
    if len(t) > 10:
        t = re.sub(r"([ T]\d{2})-(\d{2})$", r"\1:\2", t)
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
# Enhanced data structures
@dataclass
class ExtractedIncident:
    """Represents an incident extracted from description"""
    type: str
    people: List[str] = field(default_factory=list)
    injuries: List[str] = field(default_factory=list) 
    body_parts: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    chemicals: List[str] = field(default_factory=list)
    costs: List[str] = field(default_factory=list)
    confidence: float = 0.0

@dataclass
class Conversation:
    user_id: str
    queue: List[Tuple[str, str, Optional[str], Optional[List[str]]]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    event_type: Optional[str] = None
    extracted_incidents: List[ExtractedIncident] = field(default_factory=list)
    pending_confirmations: Dict[str, Any] = field(default_factory=dict)
    finished: bool = False

_CONV: Dict[str, Conversation] = {}

# ---------------------------------------------------------------------------
# Enhanced extraction engine
class IncidentExtractor:
    """Smart extraction of incident details from natural language descriptions"""
    
    def __init__(self):
        # Name patterns
        self.name_patterns = [
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',  # John Smith
            r'\b(?:worker|employee|engineer|technician|operator)\s+([A-Z][a-z]+)\b',  # worker john
        ]
        
        # Location keywords
        self.location_keywords = [
            "garage", "warehouse", "workshop", "depot", "bay", "dock", "yard", "line",
            "assembly", "plant", "shop", "lab", "laboratory", "office", "parking",
            "atlanta", "austin", "plymouth", "manheim", "stassney"
        ]
        
        # Chemical/substance patterns
        self.chemical_patterns = [
            r'\b(oil|gasoline|diesel|hydraulic\s+fluid|coolant|brake\s+fluid)\b',
            r'\b(battery\s+acid|chemicals?|lubricants?)\b'
        ]
        
        # Cost patterns
        self.cost_patterns = [
            r'\$?\b(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?|usd|\$)?\b',
            r'\bcost(?:ing)?\s+\$?(\d+(?:,\d+)*)\b'
        ]
        
        # Body part mapping
        self.body_part_keywords = {
            "hand": ["hand", "hands", "finger", "fingers", "wrist", "wrists"],
            "leg": ["leg", "legs", "knee", "knees", "ankle", "ankles", "foot", "feet"],
            "back": ["back", "spine", "lower back", "upper back"],
            "head": ["head", "skull", "face", "forehead"],
            "arm": ["arm", "arms", "elbow", "elbows", "shoulder", "shoulders"],
            "eye": ["eye", "eyes"],
            "neck": ["neck"],
            "chest": ["chest", "torso", "ribs"]
        }
        
        # Injury type keywords
        self.injury_keywords = {
            "fracture": ["broke", "broken", "fracture", "fractured", "break"],
            "cut": ["cut", "laceration", "slice", "sliced"],
            "burn": ["burn", "burned", "burnt", "scalded"],
            "sprain": ["sprain", "twisted", "strain", "strained"],
            "bruise": ["bruise", "bruised", "contusion"]
        }

    def extract_incidents(self, description: str) -> List[ExtractedIncident]:
        """Extract multiple incidents from a description"""
        text = description.lower()
        incidents = []
        
        # Detect incident types
        incident_types = self._detect_incident_types(text)
        
        for incident_type in incident_types:
            incident = ExtractedIncident(type=incident_type)
            incident.people = self._extract_people(description)
            incident.locations = self._extract_locations(text)
            
            if incident_type == "Injury/Illness":
                incident.injuries = self._extract_injuries(text)
                incident.body_parts = self._extract_body_parts(text)
            elif incident_type == "Environmental":
                incident.chemicals = self._extract_chemicals(text)
            elif incident_type in ["Property Damage", "Vehicle"]:
                incident.costs = self._extract_costs(text)
                
            incident.confidence = self._calculate_confidence(incident, text)
            incidents.append(incident)
            
        return incidents

    def _detect_incident_types(self, text: str) -> List[str]:
        """Detect what types of incidents occurred"""
        types = []
        
        # Injury indicators
        injury_indicators = [
            "broke", "broken", "injured", "hurt", "hospital", "fracture", 
            "sprain", "cut", "burn", "pain", "bleeding"
        ]
        if any(indicator in text for indicator in injury_indicators):
            types.append("Injury/Illness")
            
        # Spill/Environmental indicators  
        env_indicators = ["spill", "spilled", "leak", "leaked", "oil", "chemical"]
        if any(indicator in text for indicator in env_indicators):
            types.append("Environmental")
            
        # Vehicle indicators
        vehicle_indicators = ["car", "vehicle", "truck", "collision", "accident", "crash"]
        if any(indicator in text for indicator in vehicle_indicators):
            types.append("Vehicle")
            
        # Property damage indicators
        damage_indicators = ["damage", "cost", "repair", "broken equipment", "property"]
        if any(indicator in text for indicator in damage_indicators):
            types.append("Property Damage")
            
        return types or ["Other"]

    def _extract_people(self, text: str) -> List[str]:
        """Extract people names from text"""
        people = []
        
        # Look for name patterns
        for pattern in self.name_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                name = match.group(1) if match.lastindex else match.group(0)
                if len(name) > 2 and name.lower() not in ["the", "and", "for", "with"]:
                    people.append(name.title())
                    
        return list(set(people))  # Remove duplicates

    def _extract_locations(self, text: str) -> List[str]:
        """Extract location information"""
        locations = []
        for keyword in self.location_keywords:
            if keyword in text:
                locations.append(keyword.title())
        return locations

    def _extract_chemicals(self, text: str) -> List[str]:
        """Extract chemical/substance information"""
        chemicals = []
        for pattern in self.chemical_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            chemicals.extend([match.group(0) for match in matches])
        return list(set(chemicals))

    def _extract_costs(self, text: str) -> List[str]:
        """Extract cost information"""
        costs = []
        for pattern in self.cost_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            costs.extend([match.group(0) for match in matches])
        return costs

    def _extract_body_parts(self, text: str) -> List[str]:
        """Extract body parts mentioned"""
        body_parts = []
        for canonical, keywords in self.body_part_keywords.items():
            if any(keyword in text for keyword in keywords):
                body_parts.append(canonical)
        return body_parts

    def _extract_injuries(self, text: str) -> List[str]:
        """Extract injury types"""
        injuries = []
        for canonical, keywords in self.injury_keywords.items():
            if any(keyword in text for keyword in keywords):
                injuries.append(canonical)
        return injuries

    def _calculate_confidence(self, incident: ExtractedIncident, text: str) -> float:
        """Calculate confidence score for extracted incident"""
        score = 0.0
        
        # Base score for incident type detection
        score += 0.3
        
        # Additional points for extracted details
        if incident.people:
            score += 0.2
        if incident.locations:
            score += 0.1
        if incident.injuries or incident.chemicals or incident.costs:
            score += 0.2
            
        # Bonus for multiple indicators
        if len(incident.people) > 1:
            score += 0.1
        if len(incident.body_parts) > 0:
            score += 0.1
            
        return min(score, 1.0)

# ---------------------------------------------------------------------------
# Enhanced Smart EHS Chatbot
class EnhancedSmartEHSChatbot:
    """
    Enhanced chat-first flow with:
    - Smart multi-incident detection
    - Confirmation of extracted data
    - Better UI hints for forms
    - Intelligent field ordering
    """

    def __init__(self, logger=None):
        self.logger = logger
        self.extractor = IncidentExtractor()
        self.analytics = None

    def start_incident(self, user_id: str) -> Dict[str, Any]:
        """Start a new incident report"""
        convo = Conversation(user_id=user_id)
        _CONV[user_id] = convo
        
        return {
            "reply": f"🚨 **Incident Report**\n\n{PROMPTS['description']}",
            "next_expected": "description",
            "done": False,
            "ui": "textarea",
            "placeholder": "Describe what happened, who was involved, when and where it occurred..."
        }

    def process_message(self, text: str, user_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process user message and return next prompt or confirmation"""
        if user_id not in _CONV or _CONV[user_id].finished:
            return self.start_incident(user_id)

        convo = _CONV[user_id]
        text = (text or "").strip()

        # Handle initial description with smart extraction
        if not convo.data and not convo.queue:
            return self._process_initial_description(convo, text)

        # Handle pending confirmations first
        if convo.pending_confirmations:
            return self._process_confirmations(convo, text)

        # Regular field processing
        return self._process_regular_field(convo, text)

    def _process_initial_description(self, convo: Conversation, text: str) -> Dict[str, Any]:
        """Process initial description with smart extraction and confirmation"""
        if not _nonempty(text) or not _len_ok(text):
            return {
                "reply": "⚠️ Please provide a description of what happened.",
                "next_expected": "description",
                "done": False,
                "ui": "textarea"
            }

        # Save description
        convo.data["description"] = text
        
        # Extract incidents
        incidents = self.extractor.extract_incidents(text)
        convo.extracted_incidents = incidents
        
        # Build confirmation message
        return self._build_confirmation_message(convo, incidents)

    def _build_confirmation_message(self, convo: Conversation, incidents: List[ExtractedIncident]) -> Dict[str, Any]:
        """Build smart confirmation message based on extracted data"""
        
        if not incidents:
            # No extraction possible, proceed with basic flow
            return self._setup_basic_flow(convo)
            
        # Sort incidents by confidence
        incidents.sort(key=lambda x: x.confidence, reverse=True)
        primary_incident = incidents[0]
        
        # Build confirmation message
        confirmations = []
        confirmation_data = {}
        
        # Event type confirmation
        if primary_incident.confidence > 0.5:
            confirmations.append(f"📋 **Event Type**: {primary_incident.type}")
            confirmation_data["event_type"] = primary_incident.type
            
        # People involved
        if primary_incident.people:
            people_str = ", ".join(primary_incident.people)
            confirmations.append(f"👥 **People Involved**: {people_str}")
            confirmation_data["people"] = primary_incident.people
            
        # Location
        if primary_incident.locations:
            location_str = ", ".join(primary_incident.locations)
            confirmations.append(f"📍 **Location**: {location_str}")
            confirmation_data["where"] = location_str
            
        # Injury-specific details
        if primary_incident.type == "Injury/Illness":
            if primary_incident.body_parts:
                body_str = ", ".join(primary_incident.body_parts)
                confirmations.append(f"🦴 **Body Parts**: {body_str}")
                confirmation_data["body_parts"] = primary_incident.body_parts
                
            if primary_incident.injuries:
                injury_str = ", ".join(primary_incident.injuries)
                confirmations.append(f"🏥 **Injury Type**: {injury_str}")
                confirmation_data["injuries"] = primary_incident.injuries
                
        # Environmental details
        elif primary_incident.type == "Environmental":
            if primary_incident.chemicals:
                chem_str = ", ".join(primary_incident.chemicals)
                confirmations.append(f"⚗️ **Chemicals**: {chem_str}")
                confirmation_data["chemicals"] = chem_str
                
        # Cost information
        if primary_incident.costs:
            cost_str = ", ".join(primary_incident.costs)
            confirmations.append(f"💰 **Estimated Cost**: {cost_str}")
            confirmation_data["costs"] = cost_str

        # Detect multiple incidents
        multiple_incidents = len(incidents) > 1 or len(primary_incident.people) > 1
        
        if confirmations:
            convo.pending_confirmations = confirmation_data
            
            conf_text = "\n".join(confirmations)
            
            if multiple_incidents:
                message = f"🤖 **I detected multiple incidents from your description:**\n\n{conf_text}\n\n⚠️ **Note**: This appears to involve multiple people/events. After confirming these details, I'll help you create separate reports for each incident.\n\n**Are these details correct?**"
            else:
                message = f"🤖 **I extracted these details from your description:**\n\n{conf_text}\n\n**Are these details correct?**"
                
            return {
                "reply": message,
                "next_expected": "confirmation",
                "done": False,
                "ui": "buttons",
                "options": ["Yes, correct", "Some corrections needed", "Start over"],
                "extracted_data": confirmation_data
            }
        else:
            return self._setup_basic_flow(convo)

    def _process_confirmations(self, convo: Conversation, text: str) -> Dict[str, Any]:
        """Process confirmation responses"""
        response = text.lower().strip()
        
        if response in ["yes", "yes, correct", "correct", "y"]:
            # Apply confirmed data
            for key, value in convo.pending_confirmations.items():
                if key == "event_type":
                    convo.data[key] = value
                    convo.event_type = value
                elif key == "people":
                    # Set primary person for injury reports
                    if value and convo.event_type == "Injury/Illness":
                        convo.data["inj_name"] = value[0]
                elif key == "where":
                    convo.data[key] = value
                elif key == "body_parts":
                    if value:
                        convo.data["inj_body_part"] = value[0]
                elif key == "injuries":
                    if value:
                        convo.data["inj_injury_type"] = value[0].title()
                elif key == "chemicals":
                    convo.data["chemicals"] = value
                elif key == "costs":
                    convo.data["property_cost"] = value[0] if value else ""
                    
            convo.pending_confirmations = {}
            
            # Set up queue based on confirmed event type
            return self._setup_targeted_flow(convo)
            
        elif response in ["some corrections needed", "corrections", "no", "n"]:
            convo.pending_confirmations = {}
            return self._setup_basic_flow(convo)
            
        elif response in ["start over", "restart"]:
            convo.data = {"description": convo.data.get("description", "")}
            convo.pending_confirmations = {}
            convo.extracted_incidents = []
            return self._setup_basic_flow(convo)
        else:
            return {
                "reply": "Please choose one of the options:",
                "next_expected": "confirmation", 
                "done": False,
                "ui": "buttons",
                "options": ["Yes, correct", "Some corrections needed", "Start over"]
            }

    def _setup_basic_flow(self, convo: Conversation) -> Dict[str, Any]:
        """Setup basic question flow"""
        basics = [
            ("when", PROMPTS["when"], "datetime", None),
            ("where", PROMPTS["where"], "nonempty", None),
            ("event_type", PROMPTS["event_type"], "nonempty", None),
        ]
        convo.queue.extend(basics)
        return self._next_prompt(convo)

    def _setup_targeted_flow(self, convo: Conversation) -> Dict[str, Any]:
        """Setup targeted flow based on confirmed event type"""
        # Add remaining basic info if not already captured
        if "when" not in convo.data:
            convo.queue.append(("when", PROMPTS["when"], "datetime", None))
        if "where" not in convo.data:
            convo.queue.append(("where", PROMPTS["where"], "nonempty", None))
            
        # Add event-specific questions
        if convo.event_type:
            self._enqueue_branch(convo, convo.event_type)
            
        return self._next_prompt(convo)

    def _process_regular_field(self, convo: Conversation, text: str) -> Dict[str, Any]:
        """Process regular form fields"""
        if not convo.queue:
            return self._finalize_or_continue(convo)

        field_key, prompt, validator, _ = convo.queue[0]
        
        # Validate field
        if not self._validate_field(field_key, text, validator):
            return self._make_error_prompt(field_key, prompt, validator)
            
        # Save value
        convo.data[field_key] = self._process_field_value(field_key, text)
        convo.queue.pop(0)
        
        # Handle event type selection
        if field_key == "event_type":
            convo.event_type = convo.data[field_key]
            self._enqueue_branch(convo, convo.event_type)
            
        return self._next_prompt(convo)

    def _validate_field(self, field_key: str, text: str, validator: Optional[str]) -> bool:
        """Validate field input"""
        if not _len_ok(text):
            return False
            
        if validator:
            fn, _ = VALIDATORS.get(validator, (None, None))
            if fn and not fn(text):
                return False
                
        # Special validation for choice fields
        field_config = FIELD_OPTIONS.get(field_key, {})
        options = field_config.get("options")
        if options and not field_config.get("multi_select", False):
            if not any(text.lower().strip() == opt.lower() for opt in options):
                return False
                
        return True

    def _process_field_value(self, field_key: str, text: str) -> str:
        """Process and normalize field values"""
        # Handle multi-select fields
        field_config = FIELD_OPTIONS.get(field_key, {})
        if field_config.get("multi_select", False):
            # Parse comma-separated values
            values = [v.strip() for v in text.split(",")]
            options = field_config.get("options", [])
            matched = []
            for val in values:
                for opt in options:
                    if val.lower() == opt.lower():
                        matched.append(opt)
                        break
            return ", ".join(matched) if matched else text
            
        return text.strip()

    def _make_error_prompt(self, field_key: str, prompt: str, validator: Optional[str]) -> Dict[str, Any]:
        """Create error prompt for invalid input"""
        field_config = FIELD_OPTIONS.get(field_key, {})
        options = field_config.get("options")
        
        if validator:
            _, msg = VALIDATORS.get(validator, (None, "Invalid input."))
            error_msg = f"⚠️ {msg}\n\n{prompt}"
        elif options:
            error_msg = f"⚠️ Please choose from: {', '.join(options)}\n\n{prompt}"
        else:
            error_msg = f"⚠️ Invalid input.\n\n{prompt}"
            
        return self._make_prompt(field_key, error_msg)

    def _next_prompt(self, convo: Conversation) -> Dict[str, Any]:
        """Get next prompt in queue"""
        if not convo.queue:
            return self._finalize_or_continue(convo)
            
        field_key, prompt, validator, _ = convo.queue[0]
        return self._make_prompt(field_key, prompt)

    def _make_prompt(self, field_key: str, prompt: str) -> Dict[str, Any]:
        """Create prompt with appropriate UI hints"""
        field_config = FIELD_OPTIONS.get(field_key, {})
        
        payload = {
            "reply": prompt,
            "next_expected": field_key,
            "done": False
        }
        
        # Add UI configuration
        ui_type = field_config.get("ui", "text")
        payload["ui"] = ui_type
        
        if field_config.get("options"):
            payload["options"] = field_config["options"]
            
        if field_config.get("multi_select"):
            payload["multi_select"] = True
            payload["helper_text"] = "You can select multiple options (comma-separated)"
            
        # Special handling for specific field types
        if field_key == "when":
            payload["placeholder"] = "YYYY-MM-DD or YYYY-MM-DD HH:MM"
            payload["helper_text"] = "Use date picker or type manually. You can also type 'unknown'"
        elif field_key == "capa_due":
            payload["placeholder"] = "YYYY-MM-DD"
            payload["helper_text"] = "Select due date for corrective action"
        elif field_key in ["inj_phone", "phone"]:
            payload["placeholder"] = "555-123-4567"
        elif field_key in ["inj_zip", "zip"]:
            payload["placeholder"] = "12345"
            
        return payload

    def _enqueue_branch(self, convo: Conversation, event_type: str) -> None:
        """Enqueue event-type specific questions"""
        et = (event_type or "").strip()
        prompts = []

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
                ("inj_ppe", PROMPTS["inj_ppe"], "yesno", None),
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

        # Filter out already answered questions
        filtered_prompts = []
        for prompt_tuple in prompts:
            field_key = prompt_tuple[0]
            if field_key not in convo.data:
                filtered_prompts.append(prompt_tuple)
                
        convo.queue.extend(filtered_prompts)

    def _finalize_or_continue(self, convo: Conversation) -> Dict[str, Any]:
        """Check if we need 5 Whys or can finalize"""
        # Check if we need to add 5 Whys + CAPA
        has_root_cause = any(key.startswith("why") for key in convo.data.keys())
        
        if not has_root_cause and not convo.finished:
            self._enqueue_root_cause_and_action(convo)
            return self._next_prompt(convo)
            
        return self._finalize(convo)

    def _enqueue_root_cause_and_action(self, convo: Conversation) -> None:
        """Add 5 Whys and CAPA questions"""
        rc_prompts = [
            ("why1", "🔍 **Root Cause Analysis (5 Whys)**\n\n" + PROMPTS["why1"], "nonempty", None),
            ("why2", PROMPTS["why2"], "nonempty", None),
            ("why3", PROMPTS["why3"], "nonempty", None),
            ("why4", PROMPTS["why4"], "nonempty", None),
            ("why5", PROMPTS["why5"], "nonempty", None),
            ("capa_action", "📋 **Corrective & Preventive Actions**\n\n" + PROMPTS["capa_action"], "nonempty", None),
            ("capa_owner", PROMPTS["capa_owner"], "nonempty", None),
            ("capa_due", PROMPTS["capa_due"], "nonempty", None),
        ]
        convo.queue.extend(rc_prompts)

    def _finalize(self, convo: Conversation) -> Dict[str, Any]:
        """Finalize the incident report"""
        convo.finished = True
        
        # Generate summary
        summary_lines = []
        if convo.event_type:
            summary_lines.append(f"**Event Type**: {convo.event_type}")
        if "when" in convo.data:
            summary_lines.append(f"**Date/Time**: {convo.data['when']}")
        if "where" in convo.data:
            summary_lines.append(f"**Location**: {convo.data['where']}")
            
        # Add key people
        if convo.event_type == "Injury/Illness" and "inj_name" in convo.data:
            summary_lines.append(f"**Injured Person**: {convo.data['inj_name']}")
        elif "veh_driver" in convo.data:
            summary_lines.append(f"**Driver**: {convo.data['veh_driver']}")
            
        summary = "\n".join(summary_lines)
        
        payload = {
            "ok": True,
            "message": "✅ Incident report completed successfully!",
            "data": dict(convo.data),
            "event_type": convo.event_type,
            "completed": True,
            "summary": summary
        }

        return {
            "reply": f"✅ **Incident Report Complete!**\n\n{summary}\n\n📄 Your report has been captured and is ready for review. Do you want to submit it now or create another report?",
            "done": True,
            "result": payload,
            "ui": "buttons",
            "options": ["Submit Report", "Create Another Report", "Review & Edit"]
        }

# ---------------------------------------------------------------------------
# Enhanced Utilities for Multi-Incident Handling

class MultiIncidentManager:
    """Manages cases where multiple incidents are detected"""
    
    def __init__(self, chatbot: EnhancedSmartEHSChatbot):
        self.chatbot = chatbot
        self.pending_incidents: Dict[str, List[ExtractedIncident]] = {}
        
    def create_separate_reports(self, user_id: str, incidents: List[ExtractedIncident]) -> Dict[str, Any]:
        """Guide user through creating separate reports for each incident"""
        self.pending_incidents[user_id] = incidents
        
        incident_list = []
        for i, incident in enumerate(incidents, 1):
            people_str = ", ".join(incident.people) if incident.people else "Unknown person"
            incident_list.append(f"{i}. **{incident.type}** involving {people_str}")
            
        return {
            "reply": f"🔄 **Multiple Incidents Detected**\n\nI found {len(incidents)} separate incidents:\n\n" + 
                    "\n".join(incident_list) + 
                    f"\n\n📝 Let's create a separate report for each incident. Which one would you like to start with?",
            "options": [f"Incident {i+1}" for i in range(len(incidents))] + ["Combine into one report"],
            "ui": "buttons",
            "multi_incident": True
        }

# ---------------------------------------------------------------------------
# Enhanced Intent Classifier with Better Pattern Recognition

class EnhancedIntentClassifier:
    """Enhanced intent classification with better pattern matching"""
    
    def __init__(self):
        self._intents = [
            ("Report incident", r"\b(?:report|file|submit|create).*incident\b|\bincident report\b|\bstart.*(?:incident|report)\b"),
            ("Report injury", r"\b(?:injury|injured|hurt|accident|medical)\b.*\breport\b|\breport.*(?:injury|accident)\b"),
            ("Report spill", r"\b(?:spill|leak|environmental)\b.*\breport\b|\breport.*(?:spill|leak)\b"),
            ("Safety concern", r"\bsafety concern\b|\bnear miss\b|\bunsafe\b|\bhazard\b"),
            ("Emergency", r"\bemergency\b|\burgent\b|\bimmediate\b|\b911\b|\bhospital\b"),
            ("Find SDS", r"\b(?:find\s+)?sds\b|\bsafety data sheet\b|\bmaterial.*safety\b"),
            ("Risk assessment", r"\brisk assessment\b|\berc\b|\blikelihood\b|\brisk\s+analysis\b"),
            ("What's urgent?", r"\burgent\b|\bpriority\b|\boverdue\b|\bpending\b"),
            ("Help", r"\bhelp\b|\bguide\b|\bhow\s+to\b|\binstructions\b|\btour\b"),
        ]
        
    def classify_intent(self, text: str) -> Tuple[str, float]:
        """Classify user intent with confidence score"""
        text_lower = (text or "").lower().strip()
        
        for label, pattern in self._intents:
            if re.search(pattern, text_lower):
                # Calculate confidence based on pattern match strength
                matches = len(re.findall(pattern, text_lower))
                confidence = min(0.7 + (matches * 0.1), 0.95)
                return label, confidence
                
        return "Unknown", 0.0
        
    def quick_intent(self, text: str) -> str:
        """Quick intent classification without confidence"""
        intent, _ = self.classify_intent(text)
        return intent

# ---------------------------------------------------------------------------
# Enhanced Five Whys Manager with Better Guidance

class EnhancedFiveWhysManager:
    """Enhanced 5 Whys process with better guidance and validation"""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
    def start(self, user_id: str, problem: str) -> Dict[str, Any]:
        """Start 5 Whys analysis"""
        self._sessions[user_id] = {
            "problem": problem or "",
            "whys": [],
            "current_why": 1
        }
        
        return {
            "reply": f"🔍 **Root Cause Analysis - 5 Whys Method**\n\n"
                    f"**Problem**: {problem}\n\n"
                    f"Let's dig deeper to find the root cause. For each 'Why' question, "
                    f"think about what directly caused the previous answer.\n\n"
                    f"**Why 1**: Why did this problem occur?",
            "ui": "textarea",
            "helper_text": "Be specific and focus on direct causes, not blame"
        }
        
    def answer(self, user_id: str, answer: str) -> Dict[str, Any]:
        """Process why answer and continue or finish"""
        session = self._sessions.get(user_id)
        if not session:
            return {"error": "No active 5 Whys session"}
            
        if not answer.strip():
            current_why = session["current_why"]
            return {
                "reply": f"⚠️ Please provide an answer to Why {current_why}:",
                "ui": "textarea"
            }
            
        session["whys"].append(answer.strip())
        session["current_why"] += 1
        
        if len(session["whys"]) >= 5:
            return self._complete_analysis(user_id)
        else:
            current_why = session["current_why"]
            previous_answer = session["whys"][-1]
            
            return {
                "reply": f"**Why {current_why}**: Why {previous_answer.lower()}?",
                "ui": "textarea", 
                "helper_text": f"Continue digging deeper - {6 - current_why} more to go"
            }
            
    def _complete_analysis(self, user_id: str) -> Dict[str, Any]:
        """Complete the 5 Whys analysis"""
        session = self._sessions.get(user_id)
        if not session:
            return {"error": "Session not found"}
            
        whys_summary = []
        for i, why in enumerate(session["whys"], 1):
            whys_summary.append(f"**Why {i}**: {why}")
            
        return {
            "reply": f"✅ **Root Cause Analysis Complete**\n\n" + 
                    "\n".join(whys_summary) + 
                    f"\n\n🎯 **Root Cause**: {session['whys'][-1]}\n\n" +
                    "Now let's define corrective actions to prevent this from happening again.",
            "analysis_complete": True,
            "root_cause": session["whys"][-1],
            "all_whys": session["whys"]
        }
        
    def is_complete(self, user_id: str) -> bool:
        """Check if 5 Whys is complete"""
        session = self._sessions.get(user_id)
        return bool(session and len(session.get("whys", [])) >= 5)
        
    def get(self, user_id: str):
        """Get current session"""
        return self._sessions.get(user_id)

# ---------------------------------------------------------------------------
# Export enhanced classes
five_whys_manager = EnhancedFiveWhysManager()
SmartEHSChatbot = EnhancedSmartEHSChatbot  # Backward compatibility
SmartIntentClassifier = EnhancedIntentClassifier
