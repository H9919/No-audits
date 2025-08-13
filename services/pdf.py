from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime

def build_incident_pdf(rec: dict, completeness: int, ok: bool, missing: list, out_path: str):
    doc = SimpleDocTemplate(out_path, pagesize=LETTER, leftMargin=0.75*inch, rightMargin=0.75*inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Incident Report</b>", styles["Title"]))
    # Anonymity banner
    if rec.get("anonymous"):
        story.append(Paragraph("<font color=\"#ef4444\"><b>Anonymous Reporter</b></font>", styles["Heading2"]))
        story.append(Spacer(1, 0.1*inch))

    story.append(Spacer(1, 0.2*inch))
    if not rec.get("anonymous") and rec.get("reporter"):
        story.append(Paragraph(f"<b>Reporter:</b> {rec.get('reporter')}", styles["BodyText"]))
        story.append(Spacer(1, 0.1*inch))


    meta_table = Table([
        ["Incident ID", rec.get("id","")],
        ["Incident Type", rec.get("type","")],
        ["Created", datetime.utcfromtimestamp(rec.get("created_ts",0)).strftime("%Y-%m-%d %H:%M UTC")],
        ["Completeness", f"{completeness}%"],
        ["Validation", "Valid ✔" if ok else f"Missing: {', '.join(missing) or '-'}"],
        ["Status", rec.get("status","draft")],
    ], colWidths=[1.5*inch, 4.5*inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1), colors.lightgrey),
        ("BOX",(0,0),(-1,-1), 0.5, colors.black),
        ("INNERGRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.25*inch))

    answers = rec.get("answers", {})
    for cat in ["people","environment","cost","legal","reputation"]:
        story.append(Paragraph(f"<b>{cat.capitalize()}</b>", styles["Heading3"]))
        text = answers.get(cat,"").strip() or "—"
        story.append(Paragraph(text.replace("\n","<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 0.15*inch))

    doc.build(story)
    return out_path

    # 5 Whys (if available)
    whys = rec.get("root_cause_whys") or []
    if whys:
        story.append(Paragraph("<b>Root Cause (5 Whys)</b>", styles["Heading2"]))
        for i, wa in enumerate(whys, start=1):
            story.append(Paragraph(f"Why {i}: {wa.get('a','')}", styles["BodyText"]))
        story.append(Spacer(1, 0.15*inch))


    # Corrective Actions (if available)
    capa = rec.get("capa") or {}
    chosen = capa.get("chosen") or []
    if chosen:
        story.append(Paragraph("<b>Corrective Actions</b>", styles["Heading2"]))
        for a in chosen:
            story.append(Paragraph(f"- {a}", styles["BodyText"]))
        meta = []
        if capa.get("confidence") is not None:
            meta.append(f"Confidence: {capa.get('confidence')} ({capa.get('rationale','')})")
        if capa.get("confirmed_by"):
            meta.append(f"Confirmed By: {capa.get('confirmed_by')}")
        if meta:
            story.append(Paragraph(", ".join(meta), styles["BodyText"]))
        story.append(Spacer(1, 0.15*inch))
