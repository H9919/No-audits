import io
import json
import time
import zipfile
from pathlib import Path
from flask import Blueprint, request, render_template, send_file, abort, flash, redirect, url_for
from werkzeug.utils import secure_filename
from utils.uploads import is_allowed, save_upload

from services.sds_ingest import ingest_single_pdf, load_index, save_index, sds_dir
from services.sds_zip_ingest import ingest_zip
from services.sds_qr import ensure_qr, sds_detail_url
from services.sds_chat import answer_question_for_sds

ALLOWED_PDF = {".pdf"}
sds_bp = Blueprint("sds", __name__, template_folder="../templates")

@sds_bp.get("/")
def sds_list():
    index = load_index()
    rows = sorted(index.values(), key=lambda r: r.get("created_ts", 0), reverse=True)
    return render_template("sds_list.html", rows=rows)

@sds_bp.get("/<sid>")
def sds_view(sid):
    index = load_index()
    rec = index.get(sid)
    if not rec:
        abort(404)
    # ensure QR exists (cached)
    qr_path = ensure_qr(sid, sds_detail_url(sid))
    return render_template("sds_view.html", rec=rec, qr_path=qr_path)

@sds_bp.get("/<sid>/download")
def sds_download(sid):
    index = load_index()
    rec = index.get(sid)
    if not rec:
        abort(404)
    fpath = Path(rec["file_path"])
    if not fpath.exists():
        abort(404)
    return send_file(fpath, as_attachment=True, download_name=fpath.name)

@sds_bp.get("/<sid>/qr")
def sds_qr_png(sid):
    # Stream QR PNG (already cached by ensure_qr)
    qr_path = ensure_qr(sid, sds_detail_url(sid))
    if not Path(qr_path).exists():
        abort(404)
    return send_file(qr_path, mimetype="image/png")

@sds_bp.route("/upload", methods=["GET", "POST"])
def sds_upload():
    if request.method == "GET":
        return render_template("sds_upload.html")
    file = request.files.get("file")
    if not file:
        flash("No file provided", "danger")
        return redirect(url_for("sds.sds_upload"))
    name = secure_filename(file.filename or "")
    ext = Path(name).suffix.lower()
    if ext == ".zip":
        report = ingest_zip(file.stream)
        return render_template("sds_upload_result.html", report=report)
    elif ext in ALLOWED_PDF and is_allowed(name, file.mimetype):
        out = ingest_single_pdf(file.stream, filename=name)
        flash(f"Uploaded: {out['product_name']} (ID: {out['id']})", "success")
        return redirect(url_for("sds.sds_view", sid=out["id"]))
    else:
        flash("Unsupported file type. Upload a PDF or a ZIP.", "danger")
        return redirect(url_for("sds.sds_upload"))

@sds_bp.route("/<sid>/chat", methods=["GET", "POST"])
def sds_chat(sid):
    index = load_index()
    rec = index.get(sid)
    if not rec:
        abort(404)

    answer = None
    question = None
    if request.method == "POST":
        question = (request.form.get("question") or "").strip()
        if question:
            answer = answer_question_for_sds(rec, question)

    return render_template("sds_chat.html", rec=rec, question=question, answer=answer)



@sds_bp.route("/<sid>/label")
def sds_label(sid):
    index = load_index()
    rec = index.get(sid)
    if not rec:
        abort(404)
    # Simple HTML label; a PDF converter can be plugged later.
    html = f"""
    <html><head><meta charset='utf-8'><title>GHS/NFPA Label</title></head>
    <body style='font-family: sans-serif;'>
      <h3>Label: {rec.get('product_name','Product')}</h3>
      <p><b>File:</b> {rec.get('file_name')}</p>
      <p><b>CAS:</b> {', '.join(rec.get('chemical_info',{}).get('cas_numbers', [])) or '—'}</p>
      <p><b>Hazards:</b> {', '.join(rec.get('chemical_info',{}).get('hazard_statements', [])) or '—'}</p>
      <hr/>
      <p style='font-size:12px;color:#666;'>Printable label (HTML). Use print dialog to save as PDF.</p>
    </body></html>
    """
    return html
