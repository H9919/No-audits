import io
import zipfile
from pathlib import Path
from werkzeug.utils import secure_filename
from .sds_ingest import ingest_single_pdf

def ingest_zip(zip_stream) -> dict:
    """
    Returns a report { processed: int, ok: [ids], skipped: [names], errors: [str] }
    """
    report = {"processed": 0, "ok": [], "skipped": [], "errors": []}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_stream.read())) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = secure_filename(Path(info.filename).name)
                if not name.lower().endswith(".pdf"):
                    report["skipped"].append(name)
                    continue
                with z.open(info, "r") as f:
                    try:
                        rec = ingest_single_pdf(io.BytesIO(f.read()), filename=name)
                        report["ok"].append(rec["id"])
                        report["processed"] += 1
                    except Exception as e:
                        report["errors"].append(f"{name}: {e}")
    except zipfile.BadZipFile:
        report["errors"].append("Invalid ZIP file")
    return report

