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
    """Debug version - minimal data to identify the issue"""
    try:
        index = load_index()
        print(f"DEBUG: Loaded {len(index)} SDS records")
        
        # Get first record to inspect structure
        if index:
            first_key = next(iter(index))
            first_record = index[first_key]
            print(f"DEBUG: Sample record structure: {list(first_record.keys())}")
        
        rows = sorted(index.values(), key=lambda r: r.get("created_ts", 0), reverse=True)
        
        # Transform data with safe defaults
        sds_list = []
        for i, rec in enumerate(rows):
            try:
                # Basic required fields with safe defaults
                sds_item = {
                    'id': rec.get('id', f'sds_{i}'),
                    'product_name': rec.get('product_name', 'Unknown Product'),
                    'file_name': rec.get('file_name', 'unknown.pdf'),
                    'file_size': rec.get('file_size', 0),
                    'created_date': rec.get('created_ts', time.time()),
                    'has_embeddings': rec.get('has_embeddings', False),
                    
                    # Chemical info with safe defaults
                    'chemical_info': rec.get('chemical_info', {
                        'cas_numbers': [],
                        'hazard_statements': []
                    }),
                    
                    # Processing metadata with safe defaults
                    'processing_metadata': rec.get('processing_metadata', {
                        'chunks_count': 0,
                        'tables_extracted': 0
                    }),
                    
                    # New fields with safe defaults
                    'department': rec.get('department', ''),
                    'manufacturer': rec.get('manufacturer', ''),
                    'country': rec.get('country', ''),
                    'state': rec.get('state', ''),
                    
                    # Additional safe fields
                    'text_len': len(rec.get('text_content', '')),
                    'created_by': rec.get('created_by', 'System'),
                    'status': rec.get('status', 'active')
                }
                sds_list.append(sds_item)
                
            except Exception as e:
                print(f"DEBUG: Error processing record {i}: {e}")
                print(f"DEBUG: Problematic record: {rec}")
                continue
        
        print(f"DEBUG: Processed {len(sds_list)} records successfully")
        
        # Use the original simple template first
        return render_template("sds_list_simple.html", sds_list=sds_list)
        
    except Exception as e:
        print(f"DEBUG: Error in sds_list: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error page with debug info
        return f"""
        <html>
        <head><title>SDS Debug</title></head>
        <body>
        <h1>SDS List Debug</h1>
        <div style="background: #f8f9fa; padding: 20px; margin: 20px; border: 1px solid #dee2e6;">
        <h3>Error Details:</h3>
        <pre>{str(e)}</pre>
        <h3>Stack Trace:</h3>
        <pre>{traceback.format_exc()}</pre>
        </div>
        <a href="/sds/debug">Try Debug Version</a>
        </body>
        </html>
        """, 500

@sds_bp.get("/debug")
def sds_debug():
    """Debug endpoint to inspect data structure"""
    try:
        index = load_index()
        
        debug_info = {
            'total_records': len(index),
            'sample_keys': list(index.keys())[:3] if index else [],
            'sample_record': {}
        }
        
        if index:
            first_key = next(iter(index))
            sample_record = index[first_key]
            debug_info['sample_record'] = {
                'keys': list(sample_record.keys()),
                'id': sample_record.get('id'),
                'product_name': sample_record.get('product_name'),
                'has_chemical_info': 'chemical_info' in sample_record,
                'chemical_info_keys': list(sample_record.get('chemical_info', {}).keys()) if sample_record.get('chemical_info') else [],
                'file_size': sample_record.get('file_size'),
                'created_ts': sample_record.get('created_ts')
            }
        
        return f"""
        <html>
        <head>
            <title>SDS Debug Info</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                pre {{ background: #f8f9fa; padding: 15px; border: 1px solid #dee2e6; border-radius: 5px; }}
                .section {{ margin: 20px 0; }}
            </style>
        </head>
        <body>
        <h1>SDS Debug Information</h1>
        
        <div class="section">
            <h2>Index Status</h2>
            <p><strong>Total Records:</strong> {debug_info['total_records']}</p>
            <p><strong>Sample Keys:</strong> {', '.join(debug_info['sample_keys'])}</p>
        </div>
        
        <div class="section">
            <h2>Sample Record Structure</h2>
            <pre>{json.dumps(debug_info['sample_record'], indent=2)}</pre>
        </div>
        
        <div class="section">
            <h2>Actions</h2>
            <a href="/sds/">Try SDS List</a> |
            <a href="/sds/simple">Try Simple List</a>
        </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        return f"""
        <html>
        <body>
        <h1>Debug Error</h1>
        <pre>Error: {str(e)}\n\n{traceback.format_exc()}</pre>
        </body>
        </html>
        """, 500

@sds_bp.get("/simple")
def sds_simple():
    """Ultra-simple SDS list to test basic functionality"""
    try:
        index = load_index()
        
        # Minimal data structure
        simple_list = []
        for rec in index.values():
            simple_list.append({
                'id': rec.get('id', 'unknown'),
                'product_name': rec.get('product_name', 'Unknown'),
                'file_name': rec.get('file_name', 'unknown.pdf')
            })
        
        # Use inline template
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Simple SDS List</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
        <div class="container mt-4">
            <h2>Simple SDS List</h2>
            <div class="alert alert-info">
                This is a simplified version to test basic functionality.
            </div>
            <table class="table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Product Name</th>
                        <th>File Name</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for sds in simple_list:
            html += f"""
                    <tr>
                        <td><code>{sds['id'][:8]}</code></td>
                        <td>{sds['product_name']}</td>
                        <td>{sds['file_name']}</td>
                        <td>
                            <a href="/sds/{sds['id']}" class="btn btn-sm btn-primary">View</a>
                            <a href="/sds/{sds['id']}/download" class="btn btn-sm btn-success">Download</a>
                        </td>
                    </tr>
            """
        
        html += """
                </tbody>
            </table>
            <a href="/sds/debug" class="btn btn-secondary">Debug Info</a>
            <a href="/sds/" class="btn btn-primary">Try Enhanced Version</a>
        </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        import traceback
        return f"Simple list error: {str(e)}<br><pre>{traceback.format_exc()}</pre>", 500

# Keep all the other routes from the original file
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

# Simple API endpoint for testing
@sds_bp.route("/api/test")
def api_test():
    """Test API endpoint"""
    try:
        index = load_index()
        return jsonify({
            'status': 'ok',
            'total_sds': len(index),
            'message': 'SDS API is working'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
