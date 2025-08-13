
from services.pdf import build_incident_pdf
import os, tempfile

def test_pdf_anonymous_smoke():
    rec = {"id":"1","type":"injury","created_ts":0,"anonymous": True,"answers":{}}
    path = os.path.join(tempfile.gettempdir(),"x.pdf")
    out = build_incident_pdf(rec, completeness=0, ok=True, missing=[], out_path=path)
    assert os.path.exists(out)
