# services/incident_validator.py - Enhanced with better risk assessment and responsibility tracking
import json
import time
import re
from typing import Dict, Tuple, List, Optional
from pathlib import Path
from datetime import datetime

# Enhanced required category coverage by incident type
REQUIRED_BY_TYPE = {
    "injury": ["people", "legal"],
    "vehicle": ["people", "cost", "legal", "reputation"],
    "security": ["legal", "reputation", "cost"],
    "environmental": ["environment", "legal", "reputation"],
    "depot": ["people", "cost", "legal", "reputation"],
    "near_miss": ["people", "environment"],
    "property": ["cost", "legal"],
    "emergency": ["people", "environment", "cost", "legal", "reputation"],
    "other": ["people", "environment", "cost", "legal", "reputation"],
    # Multi-type incidents
    "injury+environmental": ["people", "environment", "legal", "reputation"],
    "injury+property": ["people", "cost", "legal"],
    "environmental+property": ["environment", "cost", "legal", "reputation"],
    "injury+environmental+property": ["people", "environment", "cost", "legal", "reputation"]
}

ALL_CATEGORIES = ["people", "environment", "cost", "legal", "reputation"]

class EnhancedIncidentScoring:
    """Enhanced incident scoring with detailed likelihood and severity assessment"""
    
    def __init__(self):
        self.severity_patterns = {
            "people": {
                "fatality": {
                    "keywords": ["death", "died", "fatal", "killed", "fatality", "deceased"],
                    "score": 10,
                    "description": "Fatality occurred"
                },
                "major_injury": {
                    "keywords": ["hospital", "admitted", "surgery", "severe", "serious", "broke", "broken", "fractured"],
                    "score": 8,
                    "description": "Serious injury requiring hospitalization"
                },
                "medical_treatment": {
                    "keywords": ["medical", "doctor", "clinic", "treatment", "emergency room", "stitches"],
                    "score": 6,
                    "description": "Medical treatment required"
                },
                "first_aid": {
                    "keywords": ["first aid", "band-aid", "minor", "superficial", "small cut"],
                    "score": 2,
                    "description": "First aid treatment only"
                }
            },
            "environment": {
                "catastrophic": {
                    "keywords": ["major spill", "widespread contamination", "ecosystem damage", "groundwater"],
                    "score": 10,
                    "description": "Catastrophic environmental impact"
                },
                "significant": {
                    "keywords": ["significant spill", "reportable", "EPA notification", "offsite impact"],
                    "score": 8,
                    "description": "Significant environmental impact"
                },
                "moderate": {
                    "keywords": ["moderate spill", "contained release", "cleanup required"],
                    "score": 6,
                    "description": "Moderate environmental impact"
                },
                "minor": {
                    "keywords": ["minor spill", "small release", "immediately cleaned", "liter"],
                    "score": 4,
                    "description": "Minor environmental impact"
                },
                "minimal": {
                    "keywords": ["contained", "no release", "prevented spill"],
                    "score": 2,
                    "description": "Minimal environmental impact"
                }
            },
            "cost": {
                "catastrophic": {
                    "keywords": ["million", "total loss", "extensive damage", "destroyed"],
                    "score": 10,
                    "description": "Catastrophic financial impact (>$1M)"
                },
                "major": {
                    "keywords": ["hundred thousand", "major repair", "significant cost", "expensive"],
                    "score": 8,
                    "description": "Major financial impact ($100K-$1M)"
                },
                "moderate": {
                    "keywords": ["ten thousand", "repair needed", "moderate cost"],
                    "score": 6,
                    "description": "Moderate financial impact ($10K-$100K)"
                },
                "minor": {
                    "keywords": ["thousand", "small repair", "minor damage"],
                    "score": 4,
                    "description": "Minor financial impact ($1K-$10K)"
                },
                "minimal": {
                    "keywords": ["cosmetic", "negligible", "under thousand"],
                    "score": 2,
                    "description": "Minimal financial impact (<$1K)"
                }
            }
        }
        
        self.likelihood_patterns = {
            "almost_certain": {
                "keywords": ["happens daily", "common occurrence", "frequent", "always", "regular"],
                "score": 10,
                "description": "Almost certain to recur (monthly or more)"
            },
            "likely": {
                "keywords": ["happens often", "likely", "probable", "occurs regularly"],
                "score": 8,
                "description": "Likely to recur (annually)"
            },
            "possible": {
                "keywords": ["could happen", "possible", "might occur", "sometimes"],
                "score": 6,
                "description": "Possible recurrence (every few years)"
            },
            "unlikely": {
                "keywords": ["rare", "unlikely", "infrequent", "seldom occurs"],
                "score": 4,
                "description": "Unlikely to recur (once per decade)"
            },
            "rare": {
                "keywords": ["very rare", "exceptional", "never seen before", "unprecedented"],
                "score": 2,
                "description": "Rare occurrence (once in career)"
            }
        }
    
    def assess_comprehensive_risk(self, incident_data: Dict) -> Dict:
        """Perform comprehensive risk assessment"""
        
        # Extract all text for analysis
        answers = incident_data.get("answers", {})
        chatbot_data = incident_data.get("chatbot_data", {})
        incident_types = incident_data.get("incident_types", [incident_data.get("type", "other")])
        
        # Combine all text sources
        all_text = " ".join([
            str(answers.get("people", "")),
            str(answers.get("environment", "")),
            str(answers.get("cost", "")),
            str(answers.get("legal", "")),
            str(answers.get("reputation", "")),
            str(chatbot_data.get("description", "")),
            " ".join([str(v) for v in chatbot_data.values() if isinstance(v, str)])
        ]).lower()
        
        # Assess likelihood
        likelihood_assessment = self._assess_likelihood(all_text, incident_types)
        
        # Assess severity for each category
        severity_assessments = {}
        for category in ALL_CATEGORIES:
            category_text = answers.get(category, "").lower()
            if category_text or category in ["people", "environment", "cost"]:  # Always assess key categories
                severity_assessments[category] = self._assess_severity(category, category_text, all_text)
        
        # Calculate overall risk score
        max_severity_score = max([s["score"] for s in severity_assessments.values()], default=0)
        risk_score = likelihood_assessment["score"] * max_severity_score / 10  # Normalize to 0-100
        
        # Determine risk level
        risk_level = self._get_risk_level(risk_score)
        
        # Generate risk matrix
        risk_matrix = self._generate_risk_matrix(likelihood_assessment, severity_assessments)
        
        return {
            "likelihood": likelihood_assessment,
            "severities": severity_assessments,
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "risk_matrix": risk_matrix,
            "recommendations": self._generate_recommendations(risk_level, incident_types, severity_assessments),
            "summary": self._generate_risk_summary(likelihood_assessment, severity_assessments, risk_level, risk_score)
        }
    
    def _assess_likelihood(self, text: str, incident_types: List[str]) -> Dict:
        """Assess likelihood of recurrence"""
        
        # Check for explicit likelihood indicators
        for level, config in self.likelihood_patterns.items():
            for keyword in config["keywords"]:
                if keyword in text:
                    return {
                        "level": level,
                        "score": config["score"],
                        "description": config["description"],
                        "basis": f"Based on text indicator: '{keyword}'"
                    }
        
        # Default likelihood based on incident type
        type_likelihood = {
            "injury": {"score": 6, "level": "possible", "description": "Possible recurrence (workplace injuries can recur)"},
            "near_miss": {"score": 8, "level": "likely", "description": "Likely recurrence (near misses indicate system weakness)"},
            "environmental": {"score": 4, "level": "unlikely", "description": "Unlikely recurrence (environmental incidents often isolated)"},
            "property": {"score": 4, "level": "unlikely", "description": "Unlikely recurrence (property damage often isolated)"},
            "vehicle": {"score": 6, "level": "possible", "description": "Possible recurrence (vehicle incidents depend on controls)"}
        }
        
        # For multiple incident types, use highest likelihood
        max_likelihood = 4  # Default
        primary_type = "other"
        
        for incident_type in incident_types:
            if incident_type in type_likelihood:
                if type_likelihood[incident_type]["score"] > max_likelihood:
                    max_likelihood = type_likelihood[incident_type]["score"]
                    primary_type = incident_type
        
        if primary_type in type_likelihood:
            config = type_likelihood[primary_type]
            return {
                "level": config["level"],
                "score": config["score"],
                "description": config["description"],
                "basis": f"Based on incident type: {primary_type}"
            }
        
        # Ultimate fallback
        return {
            "level": "possible",
            "score": 6,
            "description": "Possible recurrence (standard assessment)",
            "basis": "Default assessment"
        }
    
    def _assess_severity(self, category: str, category_text: str, full_text: str) -> Dict:
        """Assess severity for a specific category"""
        
        if category not in self.severity_patterns:
            return {
                "level": "moderate",
                "score": 4,
                "description": "Moderate impact",
                "basis": "Category not in assessment patterns"
            }
        
        # Check category-specific text first, then full text
        text_to_check = category_text if category_text.strip() else full_text
        
        patterns = self.severity_patterns[category]
        
        # Check from highest to lowest severity
        for level, config in sorted(patterns.items(), key=lambda x: x[1]["score"], reverse=True):
            for keyword in config["keywords"]:
                if keyword in text_to_check:
                    return {
                        "level": level,
                        "score": config["score"],
                        "description": config["description"],
                        "basis": f"Based on keyword: '{keyword}'"
                    }
        
        # If no keywords found but text exists, assess by length and content
        if text_to_check.strip():
            if len(text_to_check) > 100:
                return {
                    "level": "moderate",
                    "score": 4,
                    "description": "Moderate impact (detailed description provided)",
                    "basis": "Based on description length and detail"
                }
            else:
                return {
                    "level": "minor",
                    "score": 2,
                    "description": "Minor impact (limited description)",
                    "basis": "Based on limited description"
                }
        
        # No information available
        return {
            "level": "unknown",
            "score": 0,
            "description": "No information available",
            "basis": "No data provided for this category"
        }
    
    def _get_risk_level(self, risk_score: float) -> str:
        """Convert risk score to risk level"""
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
    
    def _generate_risk_matrix(self, likelihood: Dict, severities: Dict) -> Dict:
        """Generate risk matrix visualization data"""
        matrix = {
            "likelihood": {
                "score": likelihood["score"],
                "level": likelihood["level"],
                "description": likelihood["description"]
            },
            "severities": []
        }
        
        for category, severity in severities.items():
            if severity["score"] > 0:  # Only include categories with actual assessments
                matrix["severities"].append({
                    "category": category,
                    "score": severity["score"],
                    "level": severity["level"],
                    "description": severity["description"]
                })
        
        return matrix
    
    def _generate_recommendations(self, risk_level: str, incident_types: List[str], severities: Dict) -> List[str]:
        """Generate risk-based recommendations"""
        recommendations = []
        
        # Risk level based recommendations
        if risk_level in ["Critical", "High"]:
            recommendations.extend([
                "Immediate management notification required",
                "Stop work in affected area until hazards are controlled",
                "Conduct detailed investigation within 24 hours",
                "Implement immediate interim controls"
            ])
        elif risk_level == "Medium":
            recommendations.extend([
                "Investigate within 48 hours",
                "Review and update risk controls",
                "Consider additional training or procedures"
            ])
        else:
            recommendations.extend([
                "Document lessons learned",
                "Review existing controls for adequacy"
            ])
        
        # Incident type specific recommendations
        if "injury" in incident_types:
            recommendations.append("Review PPE requirements and usage")
            if any(s["score"] >= 6 for s in severities.values() if "people" in str(s)):
                recommendations.append("Consider OSHA reportability requirements")
        
        if "environmental" in incident_types:
            recommendations.append("Assess regulatory reporting requirements")
            recommendations.append("Review spill response procedures")
        
        if "property" in incident_types:
            recommendations.append("Assess insurance notification requirements")
            recommendations.append("Review equipment maintenance procedures")
        
        # Multiple incident type recommendations
        if len(incident_types) > 1:
            recommendations.append("Conduct comprehensive root cause analysis")
            recommendations.append("Review integrated management systems")
        
        return list(set(recommendations))  # Remove duplicates
    
    def _generate_risk_summary(self, likelihood: Dict, severities: Dict, risk_level: str, risk_score: float) -> str:
        """Generate comprehensive risk summary"""
        summary = f"**Overall Risk Level: {risk_level}** (Score: {risk_score}/100)\n\n"
        
        summary += f"**Likelihood of Recurrence:**\n"
        summary += f"• Level: {likelihood['level'].replace('_', ' ').title()} ({likelihood['score']}/10)\n"
        summary += f"• {likelihood['description']}\n"
        summary += f"• Basis: {likelihood['basis']}\n\n"
        
        summary += f"**Severity Assessment by Category:**\n"
        for category, severity in severities.items():
            if severity["score"] > 0:
                summary += f"• **{category.title()}:** {severity['level'].replace('_', ' ').title()} ({severity['score']}/10)\n"
                summary += f"  - {severity['description']}\n"
                summary += f"  - {severity['basis']}\n"
        
        return summary

def compute_completeness(rec: Dict) -> int:
    """Enhanced completeness calculation"""
    answers = rec.get("answers", {})
    chatbot_data = rec.get("chatbot_data", {})
    
    # Basic field completion (30% weight)
    filled_categories = sum(1 for c in ALL_CATEGORIES if (answers.get(c) or "").strip())
    basic_score = (filled_categories / len(ALL_CATEGORIES)) * 30
    
    # Required category completion (40% weight)
    incident_type = (rec.get("type") or "other").lower().replace(" ", "_")
    required = REQUIRED_BY_TYPE.get(incident_type, ALL_CATEGORIES)
    required_filled = sum(1 for c in required if (answers.get(c) or "").strip())
    required_score = (required_filled / len(required)) * 40 if required else 0
    
    # Enhanced metadata completion (30% weight)
    metadata_fields = ["location", "timestamp", "reporter", "responsible_person"]
    metadata_filled = 0
    
    # Check chatbot data for additional fields
    if chatbot_data.get("location"):
        metadata_filled += 1
    if chatbot_data.get("responsible_person"):
        metadata_filled += 1
    if rec.get("created_ts"):
        metadata_filled += 1
    if chatbot_data.get("injured_person") or chatbot_data.get("people_involved"):
        metadata_filled += 1
    
    metadata_score = (metadata_filled / len(metadata_fields)) * 30
    
    return min(100, int(basic_score + required_score + metadata_score))

def validate_record(rec: Dict) -> Tuple[bool, List[str], List[str]]:
    """Enhanced validation with detailed feedback"""
    incident_type = (rec.get("type") or "other").lower().replace(" ", "_")
    required = REQUIRED_BY_TYPE.get(incident_type, REQUIRED_BY_TYPE["other"])
    answers = rec.get("answers", {})
    chatbot_data = rec.get("chatbot_data", {})
    
    missing = []
    warnings = []
    
    # Check required categories
    for category in required:
        content = (answers.get(category) or "").strip()
        if not content:
            missing.append(category)
        elif len(content) < 10:
            warnings.append(f"{category} (needs more detail)")
    
    # Check for enhanced requirements
    if incident_type == "injury":
        if not chatbot_data.get("injured_person") and not chatbot_data.get("people_involved"):
            warnings.append("injured person name (for proper documentation)")
        if not chatbot_data.get("severity"):
            warnings.append("injury severity assessment")
    
    if "environmental" in incident_type:
        if not chatbot_data.get("chemical_name"):
            warnings.append("chemical/substance identification")
        if not chatbot_data.get("containment"):
            warnings.append("containment measures taken")
    
    # Check for responsible person
    if not chatbot_data.get("responsible_person"):
        warnings.append("responsible person for follow-up")
    
    is_valid = len(missing) == 0
    return is_valid, missing, warnings

def generate_enhanced_scoring_and_recommendations(incident_data: Dict) -> Dict:
    """Generate comprehensive scoring and recommendations"""
    
    # Initialize enhanced scorer
    scorer = EnhancedIncidentScoring()
    
    # Perform comprehensive risk assessment
    risk_assessment = scorer.assess_comprehensive_risk(incident_data)
    
    # Calculate completeness
    completeness = compute_completeness(incident_data)
    
    # Validate record
    is_valid, missing, warnings = validate_record(incident_data)
    
    # Generate automatic CAPA suggestions based on risk
    capa_suggestions = generate_risk_based_capas(risk_assessment, incident_data)
    
    return {
        "risk_assessment": risk_assessment,
        "completeness": completeness,
        "validation": {
            "is_valid": is_valid,
            "missing": missing,
            "warnings": warnings
        },
        "capa_suggestions": capa_suggestions,
        "recommendations": risk_assessment["recommendations"]
    }

def generate_risk_based_capas(risk_assessment: Dict, incident_data: Dict) -> List[Dict]:
    """Generate CAPA suggestions based on risk assessment"""
    suggestions = []
    
    risk_level = risk_assessment["risk_level"]
    incident_types = incident_data.get("incident_types", [incident_data.get("type", "other")])
    severities = risk_assessment["severities"]
    
    # High priority CAPAs for high-risk incidents
    if risk_level in ["Critical", "High"]:
        suggestions.append({
            "title": "Immediate Risk Control Review",
            "description": "Comprehensive review and enhancement of risk controls",
            "type": "corrective",
            "priority": "critical" if risk_level == "Critical" else "high",
            "due_days": 7 if risk_level == "Critical" else 14
        })
    
    # Incident type specific CAPAs
    if "injury" in incident_types:
        if severities.get("people", {}).get("score", 0) >= 6:
            suggestions.append({
                "title": "Enhanced Safety Training Program",
                "description": "Develop and implement enhanced safety training for affected work area",
                "type": "preventive",
                "priority": "high",
                "due_days": 30
            })
    
    if "environmental" in incident_types:
        suggestions.append({
            "title": "Spill Prevention and Response Review",
            "description": "Review and update spill prevention measures and response procedures",
            "type": "corrective",
            "priority": "medium",
            "due_days": 21
        })
    
    if len(incident_types) > 1:
        suggestions.append({
            "title": "Integrated Safety Management Review",
            "description": "Comprehensive review of integrated safety management systems",
            "type": "preventive",
            "priority": "high",
            "due_days": 45
        })
    
    return suggestions
