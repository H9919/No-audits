
from services.pdf import build_incident_pdf
import os, tempfile, time

def test_capa_pdf_smoke():
    rec = {
        "id": "test123",
        "type": "injury",
        "created_ts": time.time(),
        "answers": {},
        "capa": {"chosen": ["Update SOP and train staff"], "confidence": 0.8, "rationale": "semantic", "confirmed_by": "Supervisor"}
    }
    out_path = os.path.join(tempfile.gettempdir(), "incident_capa_test.pdf")
    path = build_incident_pdf(rec, completeness=100, ok=True, missing=[], out_path=out_path)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 500
