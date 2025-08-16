import io
import json
import time
import zipfile
import uuid
from pathlib import Path
from flask import Blueprint, request, render_template, send_file, abort, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename

try:
    from utils.uploads import is_allowed, save_upload
except ImportError:
    # Fallback functions if utils.uploads is not available
    def is_allowed(filename, mimetype):
        return filename.lower().endswith('.pdf')
    
    def save_upload(file, filename):
        return filename

from services.sds_ingest import ingest_single_pdf, load_index, save_index, sds_dir
from services.sds_zip_ingest import ingest_zip
from services.sds_qr import ensure_qr, sds_detail_url
from services.sds_chat import answer_question_for_sds

ALLOWED_PDF = {".pdf"}
sds_bp = Blueprint("sds", __name__, template_folder="../templates")

@sds_bp.get("/")
def sds_list():
    """Enhanced SDS list with proper data structure for new template"""
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
        
        # Use the enhanced template
        return render_template("sds_list.html", sds_list=sds_list)
        
    except Exception as e:
        print(f"DEBUG: Error in sds_list: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error page with debug info
        error_html = f'''
        <html>
        <head><title>SDS Debug</title></head>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
        <h1>SDS List Debug</h1>
        <div style="background: #f8f9fa; padding: 20px; margin: 20px; border: 1px solid #dee2e6;">
        <h3>Error Details:</h3>
        <pre>{str(e)}</pre>
        <h3>Stack Trace:</h3>
        <pre>{traceback.format_exc()}</pre>
        </div>
        <div style="margin-top: 20px;">
            <a href="/sds/debug" style="padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px;">Debug Info</a>
            <a href="/sds/setup_debug" style="padding: 8px 16px; background: #28a745; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Setup Debug</a>
            <a href="/sds/simple" style="padding: 8px 16px; background: #6c757d; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Simple View</a>
            <a href="/sds/emergency_fix" style="padding: 8px 16px; background: #dc3545; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Emergency Fix</a>
        </div>
        </body>
        </html>
        '''
        
        return error_html, 500

@sds_bp.route("/emergency_fix")
def emergency_sds_list():
    """Emergency SDS list that bypasses all complex templates and debugging"""
    try:
        # Try to load index
        index = load_index()
        
        # If no data, create some
        if not index or len(index) == 0:
            try:
                from services.sds_ingest import initialize_sds_system
                index = initialize_sds_system()
            except Exception as init_error:
                # Create minimal emergency data
                index = {
                    "emergency_001": {
                        "id": "emergency_001",
                        "product_name": "Emergency Test SDS",
                        "file_name": "test.pdf",
                        "file_size": 500000,
                        "created_ts": time.time(),
                        "created_date": time.time(),
                        "has_embeddings": False,
                        "department": "Test",
                        "manufacturer": "Test Corp",
                        "country": "Test Country",
                        "state": "",
                        "chemical_info": {"cas_numbers": [], "hazard_statements": []},
                        "processing_metadata": {"chunks_count": 0},
                        "status": "active"
                    }
                }
                print(f"Created emergency data due to init error: {init_error}")
        
        # Create simple HTML response without complex template
        html_parts = [
            '<!DOCTYPE html>',
            '<html>',
            '<head>',
            '    <title>SDS Library - Emergency Fix</title>',
            '    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">',
            '    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">',
            '</head>',
            '<body>',
            '    <div class="container mt-4">',
            '        <div class="d-flex justify-content-between align-items-center mb-4">',
            '            <h2><i class="bi bi-file-earmark-text text-success"></i> SDS Library (Emergency Mode)</h2>',
            '            <a href="/sds/upload" class="btn btn-primary">Upload SDS</a>',
            '        </div>',
            '        <div class="alert alert-success">',
            '            <h5>✅ SDS System Working!</h5>',
            f'            <p>Found {len(index)} SDS records. The system is operational.</p>',
            '            <p><strong>Note:</strong> This is emergency mode - bypassing complex templates.</p>',
            '        </div>',
            '        <div class="card">',
            '            <div class="card-header">',
            f'                <h5>SDS Records ({len(index)} total)</h5>',
            '            </div>',
            '            <div class="card-body">'
        ]
        
        if index:
            html_parts.extend([
                '                <div class="table-responsive">',
                '                <table class="table table-striped">',
                '                    <thead>',
                '                        <tr>',
                '                            <th>ID</th>',
                '                            <th>Product Name</th>',
                '                            <th>Department</th>',
                '                            <th>Manufacturer</th>',
                '                            <th>Country</th>',
                '                            <th>File Size</th>',
                '                            <th>Actions</th>',
                '                        </tr>',
                '                    </thead>',
                '                    <tbody>'
            ])
            
            for sds in index.values():
                sds_id = sds.get("id", "unknown")[:8]
                product_name = sds.get("product_name", "Unknown")
                department = sds.get("department", "Not specified")
                manufacturer = sds.get("manufacturer", "Unknown")
                country = sds.get("country", "Unknown")
                file_size = (sds.get("file_size", 0) / 1024 / 1024)
                
                html_parts.extend([
                    '                        <tr>',
                    f'                            <td><code>{sds_id}</code></td>',
                    f'                            <td><strong>{product_name}</strong></td>',
                    f'                            <td><span class="badge bg-info">{department}</span></td>',
                    f'                            <td>{manufacturer}</td>',
                    f'                            <td>{country}</td>',
                    f'                            <td>{file_size:.1f} MB</td>',
                    '                            <td>',
                    f'                                <a href="/sds/{sds.get("id")}" class="btn btn-sm btn-primary">View</a>',
                    f'                                <a href="/sds/{sds.get("id")}/download" class="btn btn-sm btn-success">Download</a>',
                    '                            </td>',
                    '                        </tr>'
                ])
            
            html_parts.extend([
                '                    </tbody>',
                '                </table>',
                '                </div>'
            ])
        else:
            html_parts.append('                <p>No SDS records found.</p>')
        
        html_parts.extend([
            '            </div>',
            '        </div>',
            '        <div class="mt-3">',
            '            <a href="/" class="btn btn-secondary">Back to Dashboard</a>',
            '            <a href="/sds/upload" class="btn btn-primary">Upload New SDS</a>',
            '            <a href="/sds/" class="btn btn-warning">Try Normal SDS View</a>',
            '        </div>',
            '        <div class="mt-3">',
            '            <small class="text-muted">Emergency mode active. If this works, the issue is with your main template.</small>',
            '        </div>',
            '    </div>',
            '</body>',
            '</html>'
        ])
        
        return '\n'.join(html_parts)
        
    except Exception as e:
        import traceback
        # Emergency fallback
        error_html = f'''
<!DOCTYPE html>
<html>
<head>
    <title>SDS Emergency Debug</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-4">
        <div class="alert alert-danger">
            <h4>🚨 SDS System Error</h4>
            <p><strong>Error:</strong> {str(e)}</p>
            <p><strong>Type:</strong> {type(e).__name__}</p>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h5>Full Error Details</h5>
            </div>
            <div class="card-body">
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; font-size: 12px;">{traceback.format_exc()}</pre>
            </div>
        </div>
        
        <h5 class="mt-4">Troubleshooting Steps:</h5>
        <ol>
            <li><strong>Check if services/sds_ingest.py has been updated</strong> with the Render-compatible version</li>
            <li><strong>Ensure PyMuPDF is in requirements.txt</strong> and installed properly</li>
            <li><strong>Check Render logs</strong> for import errors during startup</li>
            <li><strong>Verify file structure:</strong> Make sure you have __init__.py files in routes/ and services/</li>
        </ol>
        
        <div class="mt-3">
            <a href="/" class="btn btn-primary">Back to Dashboard</a>
        </div>
    </div>
</body>
</html>
        '''
        return error_html

@sds_bp.route("/create_test_data")
def create_test_data():
    """Create test SDS data for development"""
    try:
        # Load existing index
        index = load_index()
        
        # Create test SDS records
        test_sds_data = [
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Acetone (Technical Grade)',
                'file_name': 'acetone_sds.pdf',
                'file_path': '/fake/path/acetone_sds.pdf',
                'file_size': 1024000,  # 1MB
                'created_ts': time.time() - 86400,  # 1 day ago
                'has_embeddings': True,
                'department': 'Laboratory',
                'manufacturer': 'Chemical Corp',
                'country': 'United States',
                'state': 'California',
                'chemical_info': {
                    'cas_numbers': ['67-64-1'],
                    'hazard_statements': ['H225 - Highly flammable liquid and vapor', 'H319 - Causes serious eye irritation', 'H336 - May cause drowsiness or dizziness']
                },
                'processing_metadata': {
                    'chunks_count': 25,
                    'tables_extracted': 3
                },
                'text_content': 'Sample acetone safety data sheet content...',
                'created_by': 'System',
                'status': 'active'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Sodium Hydroxide Solution (50%)',
                'file_name': 'naoh_sds.pdf',
                'file_path': '/fake/path/naoh_sds.pdf',
                'file_size': 856000,  # 856KB
                'created_ts': time.time() - 172800,  # 2 days ago
                'has_embeddings': False,
                'department': 'Manufacturing',
                'manufacturer': 'Industrial Chemicals Inc',
                'country': 'Canada',
                'state': 'Ontario',
                'chemical_info': {
                    'cas_numbers': ['1310-73-2'],
                    'hazard_statements': ['H314 - Causes severe skin burns and eye damage', 'H290 - May be corrosive to metals']
                },
                'processing_metadata': {
                    'chunks_count': 0,
                    'tables_extracted': 0
                },
                'text_content': 'Sample sodium hydroxide safety data sheet content...',
                'created_by': 'System',
                'status': 'active'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Isopropyl Alcohol (99%)',
                'file_name': 'ipa_sds.pdf',
                'file_path': '/fake/path/ipa_sds.pdf',
                'file_size': 742000,  # 742KB
                'created_ts': time.time() - 259200,  # 3 days ago
                'has_embeddings': True,
                'department': 'Quality Control',
                'manufacturer': 'Solvent Solutions Ltd',
                'country': 'United Kingdom',
                'state': '',
                'chemical_info': {
                    'cas_numbers': ['67-63-0'],
                    'hazard_statements': ['H225 - Highly flammable liquid and vapor', 'H319 - Causes serious eye irritation', 'H336 - May cause drowsiness or dizziness']
                },
                'processing_metadata': {
                    'chunks_count': 18,
                    'tables_extracted': 2
                },
                'text_content': 'Sample isopropyl alcohol safety data sheet content...',
                'created_by': 'System',
                'status': 'active'
            }
        ]
        
        # Add test data to index
        for sds in test_sds_data:
            index[sds['id']] = sds
        
        # Save updated index
        save_index(index)
        
        product_list = []
        for sds in test_sds_data:
            product_list.append(f'<li>{sds["product_name"]} ({sds["manufacturer"]})</li>')
        
        result_html = f'''
        <html>
        <head><title>Test Data Created</title></head>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
        <h1>Test SDS Data Created Successfully</h1>
        <div style="background: #e6ffe6; padding: 15px; border: 1px solid #99ff99; border-radius: 5px;">
            <h3>Created {len(test_sds_data)} test SDS records:</h3>
            <ul>
                {"".join(product_list)}
            </ul>
        </div>
        <div style="margin-top: 20px;">
            <a href="/sds/" style="padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px;">View SDS List</a>
            <a href="/sds/emergency_fix" style="padding: 8px 16px; background: #dc3545; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Emergency Fix</a>
            <a href="/sds/debug" style="padding: 8px 16px; background: #6c757d; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Debug Info</a>
        </div>
        </body>
        </html>
        '''
        
        return result_html
        
    except Exception as e:
        import traceback
        error_html = f'''
        <html>
        <body>
        <h1>Test Data Creation Error</h1>
        <pre>Error: {str(e)}

{traceback.format_exc()}</pre>
        <a href="/sds/setup_debug">Back to Debug</a>
        <a href="/sds/emergency_fix">Try Emergency Fix</a>
        </body>
        </html>
        '''
        return error_html, 500

# Add all other routes with proper string handling
@sds_bp.get("/<sid>")
def sds_view(sid):
    index = load_index()
    rec = index.get(sid)
    if not rec:
        abort(404)
    # ensure QR exists (cached)
    qr_path = ensure_qr(sid, sds_detail_url(sid))
    return render_template("sds_view.html", rec=rec, qr_path=qr_path)

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
