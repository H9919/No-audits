# services/dashboard_stats.py - Enhanced Dashboard Statistics
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

def get_dashboard_statistics() -> Dict:
    """Get comprehensive dashboard statistics"""
    stats = {
        "incidents": {"total": 0, "open": 0, "this_month": 0, "by_type": {}},
        "safety_concerns": {"total": 0, "open": 0, "this_month": 0, "by_type": {}},
        "capas": {"total": 0, "overdue": 0, "completed": 0, "by_priority": {}},
        "audits": {"scheduled": 0, "completed": 0, "avg_score": 0, "this_month": 0},
        "sds": {"total": 0, "updated_this_month": 0},
        "risk_assessments": {"high_risk": 0, "total": 0, "by_level": {}},
        "contractors": {"active": 0, "pending_orientation": 0},
        "trends": {
            "incidents_6_months": [],
            "risk_distribution": {},
            "top_hazard_types": []
        }
    }
    
    # Calculate date ranges
    now = datetime.now()
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    six_months_ago = now - timedelta(days=180)
    
    # Load and analyze incidents
    incidents_file = Path("data/incidents.json")
    if incidents_file.exists():
        incidents = json.loads(incidents_file.read_text())
        stats["incidents"]["total"] = len(incidents)
        
        for incident in incidents.values():
            created_date = datetime.fromtimestamp(incident.get("created_ts", 0))
            incident_type = incident.get("type", "other")
            
            # Count open incidents
            if incident.get("status") != "complete":
                stats["incidents"]["open"] += 1
            
            # Count this month incidents
            if created_date >= this_month_start:
                stats["incidents"]["this_month"] += 1
            
            # Count by type
            stats["incidents"]["by_type"][incident_type] = stats["incidents"]["by_type"].get(incident_type, 0) + 1
    
    # Load and analyze safety concerns
    concerns_file = Path("data/safety_concerns.json")
    if concerns_file.exists():
        concerns = json.loads(concerns_file.read_text())
        stats["safety_concerns"]["total"] = len(concerns)
        
        for concern in concerns.values():
            created_date = datetime.fromtimestamp(concern.get("created_date", 0))
            concern_type = concern.get("type", "concern")
            
            # Count open concerns
            if concern.get("status") in ["reported", "in_progress"]:
                stats["safety_concerns"]["open"] += 1
            
            # Count this month concerns
            if created_date >= this_month_start:
                stats["safety_concerns"]["this_month"] += 1
            
            # Count by type
            stats["safety_concerns"]["by_type"][concern_type] = stats["safety_concerns"]["by_type"].get(concern_type, 0) + 1
    
    # Load and analyze CAPAs
    capa_file = Path("data/capa.json")
    if capa_file.exists():
        capas = json.loads(capa_file.read_text())
        stats["capas"]["total"] = len(capas)
        
        today = datetime.now().date()
        for capa in capas.values():
            priority = capa.get("priority", "medium")
            stats["capas"]["by_priority"][priority] = stats["capas"]["by_priority"].get(priority, 0) + 1
            
            if capa.get("status") == "completed":
                stats["capas"]["completed"] += 1
            elif capa.get("status") in ["open", "in_progress"]:
                try:
                    due_date = datetime.fromisoformat(capa.get("due_date", "")).date()
                    if due_date < today:
                        stats["capas"]["overdue"] += 1
                except (ValueError, TypeError):
                    pass
    
    # Load and analyze audits
    audits_file = Path("data/audits.json")
    if audits_file.exists():
        audits = json.loads(audits_file.read_text())
        
        completed_audits = []
        for audit in audits.values():
            if audit.get("status") == "scheduled":
                stats["audits"]["scheduled"] += 1
            elif audit.get("status") == "completed":
                completed_audits.append(audit)
                completed_date = datetime.fromtimestamp(audit.get("completed_date", 0))
                if completed_date >= this_month_start:
                    stats["audits"]["this_month"] += 1
        
        stats["audits"]["completed"] = len(completed_audits)
        if completed_audits:
            avg_score = sum(audit.get("score", 0) for audit in completed_audits) / len(completed_audits)
            stats["audits"]["avg_score"] = round(avg_score, 1)
    
    # Load SDS statistics
    sds_file = Path("data/sds/index.json")
    if sds_file.exists():
        sds_index = json.loads(sds_file.read_text())
        stats["sds"]["total"] = len(sds_index)
        
        # Count recently updated SDS
        for sds in sds_index.values():
            created_date = datetime.fromtimestamp(sds.get("created_ts", 0))
            if created_date >= this_month_start:
                stats["sds"]["updated_this_month"] += 1
    
    # Load and analyze risk assessments
    risk_file = Path("data/risk_assessments.json")
    if risk_file.exists():
        risks = json.loads(risk_file.read_text())
        stats["risk_assessments"]["total"] = len(risks)
        
        for risk in risks.values():
            risk_level = risk.get("risk_level", "Low")
            stats["risk_assessments"]["by_level"][risk_level] = stats["risk_assessments"]["by_level"].get(risk_level, 0) + 1
            
            if risk_level in ["High", "Critical"]:
                stats["risk_assessments"]["high_risk"] += 1
    
    # Load contractor statistics
    contractors_file = Path("data/contractors.json")
    if contractors_file.exists():
        contractors = json.loads(contractors_file.read_text())
        
        for contractor in contractors.values():
            if contractor.get("status") == "approved":
                stats["contractors"]["active"] += 1
            elif contractor.get("status") == "pending_approval":
                stats["contractors"]["pending_orientation"] += 1
    
    # Generate trend data for charts
    stats["trends"] = generate_trend_data(six_months_ago, now)
    
    return stats

def generate_trend_data(start_date: datetime, end_date: datetime) -> Dict:
    """Generate trend data for dashboard charts"""
    trends = {
        "incidents_6_months": [],
        "risk_distribution": {"Low": 0, "Medium": 0, "High": 0, "Critical": 0},
        "top_hazard_types": []
    }
    
    # Generate monthly incident data for the last 6 months
    current_date = start_date
    while current_date <= end_date:
        month_start = current_date.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        
        month_incidents = count_incidents_in_period(month_start, next_month)
        trends["incidents_6_months"].append({
            "month": month_start.strftime("%b"),
            "incidents": month_incidents["total"],
            "near_misses": month_incidents["near_miss"]
        })
        
        current_date = next_month
    
    # Get risk distribution from current assessments
    risk_file = Path("data/risk_assessments.json")
    if risk_file.exists():
        risks = json.loads(risk_file.read_text())
        for risk in risks.values():
            level = risk.get("risk_level", "Low")
            trends["risk_distribution"][level] = trends["risk_distribution"].get(level, 0) + 1
    
    # Get top hazard types from safety concerns
    concerns_file = Path("data/safety_concerns.json")
    if concerns_file.exists():
        concerns = json.loads(concerns_file.read_text())
        hazard_counts = {}
        
        for concern in concerns.values():
            hazard_type = concern.get("hazard_type", "other")
            if hazard_type:
                hazard_counts[hazard_type] = hazard_counts.get(hazard_type, 0) + 1
        
        # Sort and get top 5
        trends["top_hazard_types"] = sorted(
            hazard_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
    
    return trends

def count_incidents_in_period(start_date: datetime, end_date: datetime) -> Dict:
    """Count incidents in a specific time period"""
    counts = {"total": 0, "near_miss": 0}
    
    incidents_file = Path("data/incidents.json")
    if incidents_file.exists():
        incidents = json.loads(incidents_file.read_text())
        
        for incident in incidents.values():
            created_date = datetime.fromtimestamp(incident.get("created_ts", 0))
            if start_date <= created_date < end_date:
                counts["total"] += 1
                if incident.get("type") == "near_miss":
                    counts["near_miss"] += 1
    
    return counts

def get_recent_activity() -> Dict:
    """Get recent activity across all modules for dashboard feed"""
    activities = []
    
    # Recent incidents
    incidents_file = Path("data/incidents.json")
    if incidents_file.exists():
        incidents = json.loads(incidents_file.read_text())
        for incident in list(incidents.values())[-5:]:  # Last 5 incidents
            created_date = datetime.fromtimestamp(incident.get("created_ts", 0))
            activities.append({
                "type": "Incident",
                "description": f"{incident.get('type', 'Unknown')} incident reported",
                "time_ago": get_time_ago(created_date),
                "priority": get_incident_priority(incident),
                "url": f"/incidents/{incident['id']}/edit",
                "timestamp": incident.get("created_ts", 0)
            })
    
    # Recent safety concerns
    concerns_file = Path("data/safety_concerns.json")
    if concerns_file.exists():
        concerns = json.loads(concerns_file.read_text())
        for concern in list(concerns.values())[-5:]:  # Last 5 concerns
            created_date = datetime.fromtimestamp(concern.get("created_date", 0))
            activities.append({
                "type": "Safety Concern",
                "description": concern.get("title", "Safety concern submitted"),
                "time_ago": get_time_ago(created_date),
                "priority": concern.get("risk_level"),
                "url": f"/safety-concerns/{concern['id']}",
                "timestamp": concern.get("created_date", 0)
            })
    
    # Recent CAPAs
    capa_file = Path("data/capa.json")
    if capa_file.exists():
        capas = json.loads(capa_file.read_text())
        for capa in list(capas.values())[-5:]:  # Last 5 CAPAs
            created_date = datetime.fromisoformat(capa.get("created_date", ""))
            activities.append({
                "type": "CAPA",
                "description": f"CAPA created: {capa.get('title', 'Unknown')[:50]}",
                "time_ago": get_time_ago(created_date),
                "priority": capa.get("priority"),
                "url": f"/capa/{capa['id']}",
                "timestamp": created_date.timestamp()
            })
    
    # Recent audits
    audits_file = Path("data/audits.json")
    if audits_file.exists():
        audits = json.loads(audits_file.read_text())
        for audit in list(audits.values())[-5:]:  # Last 5 audits
            created_date = datetime.fromtimestamp(audit.get("created_date", 0))
            status_desc = "completed" if audit.get("status") == "completed" else "scheduled"
            activities.append({
                "type": "Audit",
                "description": f"Audit {status_desc}: {audit.get('title', 'Unknown')}",
                "time_ago": get_time_ago(created_date),
                "priority": None,
                "url": f"/audits/{audit['id']}",
                "timestamp": audit.get("created_date", 0)
            })
    
    # Sort by timestamp and return most recent
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {"activities": activities[:10]}  # Return top 10 most recent

def get_time_ago(date: datetime) -> str:
    """Get human-readable time ago string"""
    now = datetime.now()
    if isinstance(date, str):
        date = datetime.fromisoformat(date.replace('Z', '+00:00'))
    
    diff = now - date
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

def get_incident_priority(incident: Dict) -> str:
    """Determine incident priority based on type and status"""
    incident_type = incident.get("type", "").lower()
    status = incident.get("status", "")
    
    if incident_type in ["injury", "emergency"]:
        return "high"
    elif incident_type in ["environmental", "security"]:
        return "medium"
    elif status == "incomplete":
        return "medium"
    
    return None

# services/notification_manager.py - Enhanced SLA and Alert Management
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

class NotificationManager:
    def __init__(self):
        self.data_dir = Path("data")
        self.notifications_file = self.data_dir / "notifications.json"
        
        # SLA definitions (in days unless specified)
        self.sla_rules = {
            "incidents": {
                "injury": 7,
                "environmental": 5,
                "security": 3,
                "emergency": 1,
                "vehicle": 7,
                "other": 10
            },
            "safety_concerns": {
                "initial_response_hours": 24,
                "triage_days": 3,
                "resolution_days": 30
            },
            "capas": {
                "standard_days": 30,
                "high_priority_days": 14,
                "critical_days": 7
            },
            "audits": {
                "response_to_findings_days": 14,
                "capa_generation_days": 7
            }
        }
    
    def check_sla_violations(self) -> List[Dict]:
        """Check for SLA violations across all modules"""
        violations = []
        
        # Check different module SLAs
        violations.extend(self._check_incident_sla())
        violations.extend(self._check_safety_concern_sla())
        violations.extend(self._check_capa_sla())
        violations.extend(self._check_audit_sla())
        
        # Sort by severity (days overdue)
        violations.sort(key=lambda x: x.get("days_overdue", x.get("hours_overdue", 0)), reverse=True)
        
        return violations
    
    def _check_incident_sla(self) -> List[Dict]:
        """Check incident investigation SLA violations"""
        violations = []
        incidents_file = self.data_dir / "incidents.json"
        
        if not incidents_file.exists():
            return violations
            
        incidents = json.loads(incidents_file.read_text())
        now = datetime.now()
        
        for incident in incidents.values():
            if incident.get("status") != "complete":
                created_date = datetime.fromtimestamp(incident.get("created_ts", 0))
                incident_type = incident.get("type", "other")
                sla_days = self.sla_rules["incidents"].get(incident_type, 10)
                sla_deadline = created_date + timedelta(days=sla_days)
                
                if now > sla_deadline:
                    days_overdue = (now - sla_deadline).days
                    violations.append({
                        "type": "Incident Investigation Overdue",
                        "id": incident["id"],
                        "title": f"{incident_type.title()} incident investigation",
                        "incident_type": incident_type,
                        "days_overdue": days_overdue,
                        "priority": "critical" if days_overdue > 7 else "high",
                        "url": f"/incidents/{incident['id']}/edit",
                        "assignee": "Investigation Team"
                    })
        
        return violations
    
    def _check_safety_concern_sla(self) -> List[Dict]:
        """Check safety concern response SLA"""
        violations = []
        concerns_file = self.data_dir / "safety_concerns.json"
        
        if not concerns_file.exists():
            return violations
            
        concerns = json.loads(concerns_file.read_text())
        now = datetime.now()
        
        for concern in concerns.values():
            created_date = datetime.fromtimestamp(concern.get("created_date", 0))
            status = concern.get("status", "")
            
            # Check 24-hour initial response SLA
            if status == "reported":
                response_deadline = created_date + timedelta(hours=24)
                if now > response_deadline:
                    hours_overdue = int((now - response_deadline).total_seconds() / 3600)
                    violations.append({
                        "type": "Safety Concern - No Initial Response",
                        "id": concern["id"],
                        "title": concern.get("title", "Safety concern"),
                        "hours_overdue": hours_overdue,
                        "priority": "high",
                        "url": f"/safety-concerns/{concern['id']}",
                        "assignee": concern.get("assigned_to", "Unassigned")
                    })
            
            # Check 3-day triage SLA
            elif status in ["reported", "acknowledged"]:
                triage_deadline = created_date + timedelta(days=3)
                if now > triage_deadline:
                    days_overdue = (now - triage_deadline).days
                    violations.append({
                        "type": "Safety Concern - Triage Overdue",
                        "id": concern["id"],
                        "title": concern.get("title", "Safety concern"),
                        "days_overdue": days_overdue,
                        "priority": "medium",
                        "url": f"/safety-concerns/{concern['id']}",
                        "assignee": concern.get("assigned_to", "Unassigned")
                    })
        
        return violations
    
    def _check_capa_sla(self) -> List[Dict]:
        """Check CAPA completion SLA violations"""
        violations = []
        capa_file = self.data_dir / "capa.json"
        
        if not capa_file.exists():
            return violations
            
        capas = json.loads(capa_file.read_text())
        today = datetime.now().date()
        
        for capa in capas.values():
            if capa.get("status") in ["open", "in_progress"]:
                try:
                    due_date = datetime.fromisoformat(capa.get("due_date", "")).date()
                    if due_date < today:
                        days_overdue = (today - due_date).days
                        
                        # Determine severity based on priority and days overdue
                        priority = capa.get("priority", "medium")
                        if priority == "critical" or days_overdue > 14:
                            severity = "critical"
                        elif priority == "high" or days_overdue > 7:
                            severity = "high"
                        else:
                            severity = "medium"
                        
                        violations.append({
                            "type": "CAPA Overdue",
                            "id": capa["id"],
                            "title": capa.get("title", "CAPA"),
                            "assignee": capa.get("assignee", "Unassigned"),
                            "days_overdue": days_overdue,
                            "priority": severity,
                            "capa_priority": priority,
                            "url": f"/capa/{capa['id']}"
                        })
                except (ValueError, TypeError):
                    # Invalid date format
                    violations.append({
                        "type": "CAPA - Invalid Due Date",
                        "id": capa["id"],
                        "title": capa.get("title", "CAPA"),
                        "priority": "medium",
                        "url": f"/capa/{capa['id']}",
                        "assignee": capa.get("assignee", "Unassigned")
                    })
        
        return violations
    
    def _check_audit_sla(self) -> List[Dict]:
        """Check audit follow-up SLA violations"""
        violations = []
        audits_file = self.data_dir / "audits.json"
        
        if not audits_file.exists():
            return violations
            
        audits = json.loads(audits_file.read_text())
        now = datetime.now()
        
        for audit in audits.values():
            if audit.get("status") == "completed" and audit.get("findings"):
                completed_date = datetime.fromtimestamp(audit.get("completed_date", 0))
                
                # Check if CAPAs were generated for findings within 7 days
                capa_deadline = completed_date + timedelta(days=7)
                if now > capa_deadline:
                    # Check if CAPAs exist for this audit
                    linked_capas = self._get_capas_for_audit(audit["id"])
                    if not linked_capas:
                        days_overdue = (now - capa_deadline).days
                        violations.append({
                            "type": "Audit - Missing CAPAs",
                            "id": audit["id"],
                            "title": f"CAPAs not generated for audit: {audit.get('title', 'Unknown')}",
                            "days_overdue": days_overdue,
                            "priority": "high",
                            "url": f"/audits/{audit['id']}",
                            "finding_count": len(audit.get("findings", []))
                        })
        
        return violations
    
    def _get_capas_for_audit(self, audit_id: str) -> List[Dict]:
        """Get CAPAs linked to a specific audit"""
        capa_file = self.data_dir / "capa.json"
        if not capa_file.exists():
            return []
            
        capas = json.loads(capa_file.read_text())
        return [capa for capa in capas.values() 
                if capa.get("source") == "audit" and capa.get("source_id") == audit_id]
    
    def send_notifications(self, violations: List[Dict]) -> Dict:
        """Process and log notifications for SLA violations"""
        if not violations:
            return {"status": "no_violations", "count": 0}
        
        notification_data = {
            "timestamp": datetime.now().isoformat(),
            "violation_count": len(violations),
            "violations": violations,
            "summary": self._generate_notification_summary(violations)
        }
        
        # Save notification history
        self._save_notification_history(notification_data)
        
        # In a real implementation, this would send emails/Slack messages
        return {
            "status": "notifications_sent",
            "count": len(violations),
            "summary": notification_data["summary"]
        }
    
    def _generate_notification_summary(self, violations: List[Dict]) -> Dict:
        """Generate summary statistics for notifications"""
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "by_type": {},
            "most_overdue": None
        }
        
        max_overdue = 0
        for violation in violations:
            priority = violation.get("priority", "medium")
            summary[priority] = summary.get(priority, 0) + 1
            
            violation_type = violation.get("type", "unknown")
            summary["by_type"][violation_type] = summary["by_type"].get(violation_type, 0) + 1
            
            days_overdue = violation.get("days_overdue", 0)
            if days_overdue > max_overdue:
                max_overdue = days_overdue
                summary["most_overdue"] = violation
        
        return summary
    
    def _save_notification_history(self, notification_data: Dict):
        """Save notification to history file"""
        self.data_dir.mkdir(exist_ok=True)
        
        # Load existing notifications
        if self.notifications_file.exists():
            notifications = json.loads(self.notifications_file.read_text())
        else:
            notifications = []
        
        notifications.append(notification_data)
        
        # Keep only last 100 notifications
        notifications = notifications[-100:]
        
        self.notifications_file.write_text(json.dumps(notifications, indent=2))
    
    def get_notification_history(self, days: int = 7) -> List[Dict]:
        """Get notification history for the last N days"""
        if not self.notifications_file.exists():
            return []
        
        notifications = json.loads(self.notifications_file.read_text())
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_notifications = []
        for notification in notifications:
            notification_date = datetime.fromisoformat(notification["timestamp"])
            if notification_date >= cutoff_date:
                recent_notifications.append(notification)
        
        return recent_notifications
