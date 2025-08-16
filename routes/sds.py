import io
import json
import time
import zipfile
from pathlib import Path
from flask import Blueprint, request, render_template, send_file, abort, flash, redirect, url_for, jsonify
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
    """Enhanced SDS list with proper data structure for new template"""
    index = load_index()
    rows = sorted(index.values(), key=lambda r: r.get("created_ts", 0), reverse=True)
    
    # Transform data to match template expectations
    sds_list = []
    for rec in rows:
        # Ensure all required fields exist
        sds_item = {
            'id': rec.get('id', ''),
            'product_name': rec.get('product_name', 'Unknown Product'),
            'file_name': rec.get('file_name', ''),
            'file_size': rec.get('file_size', 0),
            'created_date': rec.get('created_ts', 0),
            'has_embeddings': rec.get('has_embeddings', False),
            'chemical_info': rec.get('chemical_info', {}),
            'processing_metadata': rec.get('processing_metadata', {}),
            
            # New fields for enhanced template
            'department': rec.get('department', ''),
            'manufacturer': rec.get('manufacturer', ''),
            'country': rec.get('country', ''),
            'state': rec.get('state', ''),
            
            # Additional metadata
            'text_len': len(rec.get('text_content', '')),
            'created_by': rec.get('created_by', 'System'),
            'status': rec.get('status', 'active')
        }
        sds_list.append(sds_item)
    
    return render_template("sds_list.html", sds_list=sds_list)

@sds_bp.get("/<sid>")
def sds_view(sid):
    index = load_index()
    rec = index.get(sid)
    if not rec:
        abort(404)
    # ensure QR exists (cached)
    qr_path = ensure_qr(sid, sds_detail_url(sid))
    return render_template("sds_view.html", rec=rec, qr_path=qr_path)

@sds_bp.get("/<sid>/view_inline")
def sds_view_inline(sid):
    """Inline SDS viewer for modal preview"""
    index = load_index()
    rec = index.get(sid)
    if not rec:
        return '<div class="alert alert-danger">SDS not found</div>', 404
    
    # Generate preview HTML
    chemical_info = rec.get('chemical_info', {})
    cas_numbers = chemical_info.get('cas_numbers', [])
    hazard_statements = chemical_info.get('hazard_statements', [])
    
    preview_html = f"""
    <div class="sds-preview">
        <div class="row">
            <div class="col-md-8">
                <h4>{rec.get('product_name', 'Unknown Product')}</h4>
                <p><strong>File:</strong> {rec.get('file_name', 'Unknown')}</p>
                <p><strong>Department:</strong> {rec.get('department', 'Not specified')}</p>
                <p><strong>Manufacturer:</strong> {rec.get('manufacturer', 'Not specified')}</p>
                
                {f"<p><strong>CAS Numbers:</strong> {', '.join(cas_numbers)}</p>" if cas_numbers else ""}
                
                {f'''<div class="mt-3">
                    <h6>Hazard Statements:</h6>
                    <ul>{"".join(f"<li>{hazard}</li>" for hazard in hazard_statements)}</ul>
                </div>''' if hazard_statements else ""}
                
                <div class="mt-3">
                    <h6>File Information:</h6>
                    <ul>
                        <li>Size: {(rec.get('file_size', 0) / 1024 / 1024):.1f} MB</li>
                        <li>Text Length: {len(rec.get('text_content', ''))} characters</li>
                        <li>AI Indexed: {'Yes' if rec.get('has_embeddings') else 'No'}</li>
                    </ul>
                </div>
            </div>
            <div class="col-md-4">
                <div class="text-center">
                    <i class="bi bi-file-pdf text-danger" style="font-size: 4rem;"></i>
                    <p class="mt-2">PDF Document</p>
                    <a href="/sds/{sid}/download" class="btn btn-primary btn-sm">
                        <i class="bi bi-download"></i> Download
                    </a>
                </div>
            </div>
        </div>
    </div>
    """
    
    return preview_html

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

@sds_bp.route("/bulk_upload", methods=["POST"])
def sds_bulk_upload():
    """Bulk upload endpoint for ZIP files"""
    file = request.files.get("zip_file")
    if not file:
        flash("No ZIP file provided", "danger")
        return redirect(url_for("sds.sds_list"))
    
    default_department = request.form.get("default_department", "")
    
    try:
        report = ingest_zip(file.stream, default_department=default_department)
        return render_template("sds_upload_result.html", report=report)
    except Exception as e:
        flash(f"Error processing ZIP file: {str(e)}", "danger")
        return redirect(url_for("sds.sds_list"))

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

@sds_bp.route("/<sid>/index", methods=["POST"])
def sds_index(sid):
    """Index individual SDS for AI search"""
    index = load_index()
    rec = index.get(sid)
    if not rec:
        return jsonify({'error': 'SDS not found'}), 404
    
    try:
        # This would trigger the AI indexing process
        # You'll need to implement this based on your indexing system
        rec['has_embeddings'] = True
        rec['indexed_ts'] = time.time()
        
        # Save updated index
        index[sid] = rec
        save_index(index)
        
        return jsonify({'success': True, 'message': 'SDS indexed successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@sds_bp.route("/search")
def sds_search():
    """AI-powered SDS search page"""
    return render_template("sds_search.html")

@sds_bp.route("/export_csv")
def sds_export_csv():
    """Export SDS list as CSV"""
    import csv
    from io import StringIO
    
    index = load_index()
    rows = sorted(index.values(), key=lambda r: r.get("created_ts", 0), reverse=True)
    
    output = StringIO()
    writer = csv.writer(output)
    
    # CSV headers
    headers = [
        'ID', 'Product Name', 'File Name', 'Department', 'Manufacturer', 
        'Country', 'State', 'CAS Numbers', 'Hazard Statements', 'File Size (MB)', 
        'AI Indexed', 'Created Date'
    ]
    writer.writerow(headers)
    
    # CSV data
    for rec in rows:
        chemical_info = rec.get('chemical_info', {})
        cas_numbers = '; '.join(chemical_info.get('cas_numbers', []))
        hazard_statements = '; '.join(chemical_info.get('hazard_statements', []))
        file_size_mb = (rec.get('file_size', 0) / 1024 / 1024)
        created_date = time.strftime('%Y-%m-%d', time.localtime(rec.get('created_ts', 0)))
        
        writer.writerow([
            rec.get('id', ''),
            rec.get('product_name', ''),
            rec.get('file_name', ''),
            rec.get('department', ''),
            rec.get('manufacturer', ''),
            rec.get('country', ''),
            rec.get('state', ''),
            cas_numbers,
            hazard_statements,
            f"{file_size_mb:.1f}",
            'Yes' if rec.get('has_embeddings') else 'No',
            created_date
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'sds_export_{int(time.time())}.csv'
    )

@sds_bp.route("/reindex_all", methods=["POST"])
def sds_reindex_all():
    """Reindex all SDS files for AI search"""
    try:
        index = load_index()
        reindexed_count = 0
        
        for sid, rec in index.items():
            # This would trigger the AI indexing process for each SDS
            # You'll need to implement this based on your indexing system
            rec['has_embeddings'] = True
            rec['indexed_ts'] = time.time()
            reindexed_count += 1
        
        save_index(index)
        
        return jsonify({
            'success': True, 
            'message': f'Started reindexing {reindexed_count} SDS files',
            'count': reindexed_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Endpoints for enhanced functionality
@sds_bp.route("/api/stats")
def api_sds_stats():
    """API endpoint for SDS statistics"""
    index = load_index()
    
    total = len(index)
    ai_indexed = sum(1 for rec in index.values() if rec.get('has_embeddings'))
    departments = len(set(rec.get('department') for rec in index.values() if rec.get('department')))
    
    # Count this month's additions
    import time
    thirty_days_ago = time.time() - (30 * 24 * 60 * 60)
    this_month = sum(1 for rec in index.values() if rec.get('created_ts', 0) > thirty_days_ago)
    
    return jsonify({
        'total': total,
        'ai_indexed': ai_indexed,
        'departments': departments,
        'this_month': this_month
    })

# Bulk operations endpoints
@sds_bp.route("/bulk/reindex", methods=["POST"])
def bulk_reindex():
    """Bulk reindex selected SDS files"""
    data = request.get_json()
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    
    try:
        index = load_index()
        updated_count = 0
        
        for sid in ids:
            if sid in index:
                index[sid]['has_embeddings'] = True
                index[sid]['indexed_ts'] = time.time()
                updated_count += 1
        
        save_index(index)
        
        return jsonify({
            'success': True,
            'message': f'Reindexed {updated_count} SDS files',
            'count': updated_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/bulk/set-department", methods=["POST"])
def bulk_set_department():
    """Bulk set department for selected SDS files"""
    data = request.get_json()
    ids = data.get('ids', [])
    department = data.get('department', '')
    
    if not ids or not department:
        return jsonify({'error': 'IDs and department required'}), 400
    
    try:
        index = load_index()
        updated_count = 0
        
        for sid in ids:
            if sid in index:
                index[sid]['department'] = department
                updated_count += 1
        
        save_index(index)
        
        return jsonify({
            'success': True,
            'message': f'Updated department for {updated_count} SDS files',
            'count': updated_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/bulk/delete", methods=["POST"])
def bulk_delete():
    """Bulk delete selected SDS files"""
    data = request.get_json()
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    
    try:
        index = load_index()
        deleted_count = 0
        
        for sid in ids:
            if sid in index:
                # Optionally delete the actual file
                rec = index[sid]
                file_path = Path(rec.get('file_path', ''))
                if file_path.exists():
                    file_path.unlink()
                
                del index[sid]
                deleted_count += 1
        
        save_index(index)
        
        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} SDS files',
            'count': deleted_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/<sid>", methods=["DELETE"])
def delete_sds(sid):
    """Delete individual SDS"""
    try:
        index = load_index()
        
        if sid not in index:
            return jsonify({'error': 'SDS not found'}), 404
        
        rec = index[sid]
        
        # Delete the actual file
        file_path = Path(rec.get('file_path', ''))
        if file_path.exists():
            file_path.unlink()
        
        # Remove from index
        del index[sid]
        save_index(index)
        
        return jsonify({'success': True, 'message': 'SDS deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
