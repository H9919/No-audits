import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

class CAPAManager:
    def __init__(self):
        self.data_dir = Path("data")
        self.capa_file = self.data_dir / "capa.json"
        
    def load_capas(self) -> Dict:
        if self.capa_file.exists():
            return json.loads(self.capa_file.read_text())
        return {}
    
    def save_capas(self, capas: Dict):
        self.data_dir.mkdir(exist_ok=True)
        self.capa_file.write_text(json.dumps(capas, indent=2))
    
    def create_capa(self, data: Dict) -> str:
        capas = self.load_capas()
        capa_id = str(int(time.time() * 1000))
        
        capa = {
            "id": capa_id,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "type": data.get("type", "corrective"),  # corrective, preventive
            "source": data.get("source", "manual"),  # manual, incident, audit, risk
            "source_id": data.get("source_id"),
            "assignee": data.get("assignee", ""),
            "due_date": data.get("due_date", ""),
            "priority": data.get("priority", "medium"),  # low, medium, high, critical
            "status": "open",
            "created_date": datetime.now().isoformat(),
            "created_by": data.get("created_by", ""),
            "updates": [],
            "risk_level": data.get("risk_level", "medium"),
            "effectiveness_review_required": True,
            "verification_evidence": [],
            "root_cause": data.get("root_cause", ""),
            "implementation_plan": data.get("implementation_plan", "")
        }
        
        capas[capa_id] = capa
        self.save_capas(capas)
        return capa_id
    
    def update_capa(self, capa_id: str, update_data: Dict) -> bool:
        capas = self.load_capas()
        if capa_id not in capas:
            return False
            
        capa = capas[capa_id]
        
        # Add update to history
        update = {
            "timestamp": datetime.now().isoformat(),
            "user": update_data.get("updated_by", ""),
            "comment": update_data.get("comment", ""),
            "status_change": update_data.get("status") != capa.get("status"),
            "old_status": capa.get("status"),
            "new_status": update_data.get("status"),
            "fields_changed": []
        }
        
        # Track field changes
        for key, value in update_data.items():
            if key in ["status", "assignee", "due_date", "priority"] and capa.get(key) != value:
                update["fields_changed"].append({
                    "field": key,
                    "old_value": capa.get(key),
                    "new_value": value
                })
                capa[key] = value
        
        capa["updates"].append(update)
        
        # Auto-close if completed
        if update_data.get("status") == "completed":
            capa["completion_date"] = datetime.now().isoformat()
            capa["completed_by"] = update_data.get("updated_by", "")
            
        capas[capa_id] = capa
        self.save_capas(capas)
        return True
    
    def get_overdue_capas(self) -> List[Dict]:
        capas = self.load_capas()
        overdue = []
        today = datetime.now().date()
        
        for capa in capas.values():
            if capa["status"] in ["open", "in_progress"]:
                try:
                    due_date = datetime.fromisoformat(capa["due_date"]).date()
                    if due_date < today:
                        days_overdue = (today - due_date).days
                        capa["days_overdue"] = days_overdue
                        overdue.append(capa)
                except (ValueError, TypeError):
                    continue
                    
        return sorted(overdue, key=lambda x: x.get("days_overdue", 0), reverse=True)
    
    def get_capas_by_source(self, source_type: str, source_id: str) -> List[Dict]:
        """Get CAPAs linked to a specific source (incident, audit, etc.)"""
        capas = self.load_capas()
        return [capa for capa in capas.values() 
                if capa.get("source") == source_type and capa.get("source_id") == source_id]
    
    def get_capa_statistics(self) -> Dict:
        """Get CAPA statistics for dashboard"""
        capas = self.load_capas()
        stats = {
            "total": len(capas),
            "open": 0,
            "in_progress": 0,
            "completed": 0,
            "overdue": 0,
            "by_priority": {"low": 0, "medium": 0, "high": 0, "critical": 0},
            "by_type": {"corrective": 0, "preventive": 0},
            "by_source": {}
        }
        
        today = datetime.now().date()
        for capa in capas.values():
            status = capa.get("status", "open")
            priority = capa.get("priority", "medium")
            capa_type = capa.get("type", "corrective")
            source = capa.get("source", "manual")
            
            # Count by status
            if status in stats:
                stats[status] += 1
            
            # Count by priority
            if priority in stats["by_priority"]:
                stats["by_priority"][priority] += 1
            
            # Count by type
            if capa_type in stats["by_type"]:
                stats["by_type"][capa_type] += 1
            
            # Count by source
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
            
            # Count overdue
            if status in ["open", "in_progress"]:
                try:
                    due_date = datetime.fromisoformat(capa.get("due_date", "")).date()
                    if due_date < today:
                        stats["overdue"] += 1
                except (ValueError, TypeError):
                    pass
        
        return stats


    def suggest_corrective_actions(self, description: str) -> dict:
        """
        Return semantic/fallback CAPA suggestions with confidence and rationale.
        """
        from .embeddings import SBERT_AVAILABLE, embed_query, embed_texts, cosine_sim
        templates = [
            "Conduct toolbox talk on hazard",
            "Add machine guarding and interlocks",
            "Update SOP and train staff",
            "Improve housekeeping and 5S",
            "Install spill containment kits",
            "Implement lockout/tagout procedure",
            "Schedule preventive maintenance",
            "Add PPE requirement and checks",
        ]
        try:
            if SBERT_AVAILABLE:
                qv = embed_query(description)
                tv = embed_texts(templates)
                import numpy as np
                sims = [float(cosine_sim(qv, v)) for v in tv]
                ranked = sorted(zip(templates, sims), key=lambda x: x[1], reverse=True)[:3]
                actions = [t for t,_ in ranked]
                conf = min(0.95, max(sims))
                rationale = "semantic"
            else:
                # simple keyword fallback
                d = (description or "").lower()
                actions = []
                if any(k in d for k in ["spill","leak","chemical"]):
                    actions.append("Install spill containment kits")
                if any(k in d for k in ["unguarded","guard","pinch","machine"]):
                    actions.append("Add machine guarding and interlocks")
                if any(k in d for k in ["procedure","process","sop","training"]):
                    actions.append("Update SOP and train staff")
                if not actions:
                    actions = ["Conduct toolbox talk on hazard"]
                conf = 0.5
                rationale = "keywords"
            return {"actions": actions, "confidence": round(conf,2), "rationale": rationale}
        except Exception:
            return {"actions": ["Conduct toolbox talk on hazard"], "confidence": 0.4, "rationale": "fallback"}
