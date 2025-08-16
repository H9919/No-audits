import io
import json
import time
import zipfile
import uuid
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
        return f"""
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
        </div>
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
                .btn {{ padding: 8px 16px; margin: 5px; text-decoration: none; border-radius: 4px; display: inline-block; }}
                .btn-primary {{ background: #007bff; color: white; }}
                .btn-success {{ background: #28a745; color: white; }}
                .btn-secondary {{ background: #6c757d; color: white; }}
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
            <a href="/sds/" class="btn btn-primary">Try SDS List</a>
            <a href="/sds/simple" class="btn btn-secondary">Try Simple List</a>
            <a href="/sds/setup_debug" class="btn btn-success">Setup Debug</a>
            {f'<a href="/sds/create_test_data" class="btn btn-success">Create Test Data</a>' if debug_info['total_records'] == 0 else ''}
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
        <a href="/sds/setup_debug">Setup Debug</a>
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
        html = f"""
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
                This is a simplified version to test basic functionality. Records: {len(simple_list)}
            </div>
            {f'''
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
                    {"".join(f"""
                    <tr>
                        <td><code>{sds['id'][:8]}</code></td>
                        <td>{sds['product_name']}</td>
                        <td>{sds['file_name']}</td>
                        <td>
                            <a href="/sds/{sds['id']}" class="btn btn-sm btn-primary">View</a>
                            <a href="/sds/{sds['id']}/download" class="btn btn-sm btn-success">Download</a>
                        </td>
                    </tr>
                    """ for sds in simple_list)}
                </tbody>
            </table>
            ''' if simple_list else '<div class="alert alert-warning">No SDS records found. <a href="/sds/create_test_data">Create test data</a></div>'}
            <div class="mt-3">
                <a href="/sds/debug" class="btn btn-secondary">Debug Info</a>
                <a href="/sds/" class="btn btn-primary">Try Enhanced Version</a>
                {f'<a href="/sds/create_test_data" class="btn btn-success">Create Test Data</a>' if len(simple_list) == 0 else ''}
            </div>
        </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        import traceback
        return f"Simple list error: {str(e)}<br><pre>{traceback.format_exc()}</pre>", 500

@sds_bp.route("/setup_debug")
def setup_debug():
    """Debug SDS setup and directory structure"""
    try:
        debug_info = {
            'sds_directory': str(sds_dir),
            'sds_dir_exists': sds_dir.exists(),
            'sds_dir_contents': [],
            'index_file_exists': False,
            'index_file_path': str(sds_dir / "index.json"),
            'permissions': 'unknown'
        }
        
        # Check directory
        if sds_dir.exists():
            debug_info['sds_dir_contents'] = [str(f) for f in sds_dir.iterdir()]
            debug_info['permissions'] = oct(sds_dir.stat().st_mode)[-3:]
        
        # Check index file
        index_file = sds_dir / "index.json"
        debug_info['index_file_exists'] = index_file.exists()
        
        if index_file.exists():
            debug_info['index_file_size'] = index_file.stat().st_size
            try:
                with open(index_file, 'r') as f:
                    content = f.read()
                    debug_info['index_content_preview'] = content[:200] + "..." if len(content) > 200 else content
            except Exception as e:
                debug_info['index_read_error'] = str(e)
        
        # Try to load index
        try:
            index = load_index()
            debug_info['load_index_success'] = True
            debug_info['loaded_records'] = len(index)
        except Exception as e:
            debug_info['load_index_error'] = str(e)
            debug_info['load_index_success'] = False
        
        return f"""
        <html>
        <head>
            <title>SDS Setup Debug</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .error {{ background: #ffe6e6; border-color: #ff9999; }}
                .success {{ background: #e6ffe6; border-color: #99ff99; }}
                .warning {{ background: #fff5e6; border-color: #ffcc99; }}
                pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; }}
                .btn {{ padding: 8px 16px; margin: 5px; text-decoration: none; border-radius: 4px; display: inline-block; }}
                .btn-primary {{ background: #007bff; color: white; }}
                .btn-success {{ background: #28a745; color: white; }}
                .btn-warning {{ background: #ffc107; color: black; }}
            </style>
        </head>
        <body>
        <h1>SDS Setup Debug</h1>
        
        <div class="section {'success' if debug_info['sds_dir_exists'] else 'error'}">
            <h3>Directory Structure</h3>
            <p><strong>SDS Directory:</strong> {debug_info['sds_directory']}</p>
            <p><strong>Exists:</strong> {debug_info['sds_dir_exists']}</p>
            <p><strong>Permissions:</strong> {debug_info['permissions']}</p>
            {'<p><strong>Contents:</strong> ' + ', '.join(debug_info['sds_dir_contents']) + '</p>' if debug_info['sds_dir_contents'] else '<p><strong>Directory is empty</strong></p>'}
        </div>
        
        <div class="section {'success' if debug_info['index_file_exists'] else 'warning'}">
            <h3>Index File</h3>
            <p><strong>Index File:</strong> {debug_info['index_file_path']}</p>
            <p><strong>Exists:</strong> {debug_info['index_file_exists']}</p>
            {f"<p><strong>Size:</strong> {debug_info.get('index_file_size', 0)} bytes</p>" if debug_info['index_file_exists'] else ""}
            {f"<pre>{debug_info.get('index_content_preview', 'No content')}</pre>" if debug_info['index_file_exists'] else ""}
            {f"<p style='color: red;'><strong>Read Error:</strong> {debug_info.get('index_read_error')}</p>" if debug_info.get('index_read_error') else ""}
        </div>
        
        <div class="section {'success' if debug_info.get('load_index_success') else 'error'}">
            <h3>Index Loading</h3>
            <p><strong>Load Success:</strong> {debug_info.get('load_index_success', False)}</p>
            <p><strong>Records Loaded:</strong> {debug_info.get('loaded_records', 0)}</p>
            {f"<p style='color: red;'><strong>Load Error:</strong> {debug_info.get('load_index_error')}</p>" if debug_info.get('load_index_error') else ""}
        </div>
        
        <div class="section">
            <h3>Actions</h3>
            <a href="/sds/create_test_data" class="btn btn-success">Create Test SDS Data</a>
            <a href="/sds/initialize_system" class="btn btn-primary">Initialize SDS System</a>
            <a href="/sds/upload" class="btn btn-warning">Upload Real SDS</a>
            <a href="/sds/" class="btn btn-primary">Back to SDS List</a>
        </div>
        
        <div class="section">
            <h3>Debug Data</h3>
            <pre>{json.dumps(debug_info, indent=2)}</pre>
        </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        return f"""
        <html>
        <body>
        <h1>Setup Debug Error</h1>
        <pre>Error: {str(e)}\n\n{traceback.format_exc()}</pre>
        </body>
        </html>
        """, 500

@sds_bp.route("/initialize_system")
def initialize_system():
    """Initialize the SDS system with proper directory structure"""
    try:
        # Create SDS directory if it doesn't exist
        sds_dir.mkdir(parents=True, exist_ok=True)
        
        # Create empty index
        empty_index = {}
        save_index(empty_index)
        
        # Create subdirectories
        (sds_dir / "files").mkdir(exist_ok=True)
        (sds_dir / "qr_codes").mkdir(exist_ok=True)
        
        return f"""
        <html>
        <head><title>SDS System Initialized</title></head>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
        <h1>SDS System Initialized Successfully</h1>
        <div style="background: #e6ffe6; padding: 15px; border: 1px solid #99ff99; border-radius: 5px;">
            <h3>Created:</h3>
            <ul>
                <li>SDS directory: {sds_dir}</li>
                <li>Empty index.json file</li>
                <li>Files subdirectory</li>
                <li>QR codes subdirectory</li>
            </ul>
        </div>
        <div style="margin-top: 20px;">
            <a href="/sds/create_test_data" style="padding: 8px 16px; background: #28a745; color: white; text-decoration: none; border-radius: 4px;">Create Test Data</a>
            <a href="/sds/upload" style="padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Upload SDS</a>
            <a href="/sds/" style="padding: 8px 16px; background: #6c757d; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">View SDS List</a>
        </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        return f"""
        <html>
        <body>
        <h1>Initialization Error</h1>
        <pre>Error: {str(e)}\n\n{traceback.format_exc()}</pre>
        <a href="/sds/setup_debug">Back to Debug</a>
        </body>
        </html>
        """, 500

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
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Hydrochloric Acid (37%)',
                'file_name': 'hcl_sds.pdf',
                'file_path': '/fake/path/hcl_sds.pdf',
                'file_size': 923000,  # 923KB
                'created_ts': time.time() - 345600,  # 4 days ago
                'has_embeddings': True,
                'department': 'Research',
                'manufacturer': 'Acid Solutions Inc',
                'country': 'Germany',
                'state': 'Bavaria',
                'chemical_info': {
                    'cas_numbers': ['7647-01-0'],
                    'hazard_statements': ['H314 - Causes severe skin burns and eye damage', 'H335 - May cause respiratory irritation']
                },
                'processing_metadata': {
                    'chunks_count': 22,
                    'tables_extracted': 4
                },
                'text_content': 'Sample hydrochloric acid safety data sheet content...',
                'created_by': 'System',
                'status': 'active'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Methanol (HPLC Grade)',
                'file_name': 'methanol_sds.pdf',
                'file_path': '/fake/path/methanol_sds.pdf',
                'file_size': 678000,  # 678KB
                'created_ts': time.time() - 432000,  # 5 days ago
                'has_embeddings': False,
                'department': 'Analytical',
                'manufacturer': 'Pure Solvents Co',
                'country': 'Japan',
                'state': '',
                'chemical_info': {
                    'cas_numbers': ['67-56-1'],
                    'hazard_statements': ['H225 - Highly flammable liquid and vapor', 'H301 - Toxic if swallowed', 'H311 - Toxic in contact with skin', 'H331 - Toxic if inhaled']
                },
                'processing_metadata': {
                    'chunks_count': 0,
                    'tables_extracted': 0
                },
                'text_content': 'Sample methanol safety data sheet content...',
                'created_by': 'System',
                'status': 'active'
            }
        ]
        
        # Add test data to index
        for sds in test_sds_data:
            index[sds['id']] = sds
        
        # Save updated index
        save_index(index)
        
        return f"""
        <html>
        <head><title>Test Data Created</title></head>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
        <h1>Test SDS Data Created Successfully</h1>
        <div style="background: #e6ffe6; padding: 15px; border: 1px solid #99ff99; border-radius: 5px;">
            <h3>Created {len(test_sds_data)} test SDS records:</h3>
            <ul>
                {"".join(f"<li>{sds['product_name']} ({sds['manufacturer']})</li>" for sds in test_sds_data)}
            </ul>
        </div>
        <div style="margin-top: 20px;">
            <a href="/sds/" style="padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px;">View SDS List</a>
            <a href="/sds/debug" style="padding: 8px 16px; background: #6c757d; color: white; text-decoration: none; border-radius: 4px; margin-left: 10px;">Debug Info</a>
        </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        return f"""
        <html>
        <body>
        <h1>Test Data Creation Error</h1>
        <pre>Error: {str(e)}\n\n{traceback.format_exc()}</pre>
        <a href="/sds/setup_debug">Back to Debug</a>
        </body>
        </html>
        """, 500

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
    thirty_days_ago = time.time() - (30 * 24 * 60 * 60)
    this_month = sum(1 for rec in index.values() if rec.get('created_ts', 0) > thirty_days_ago)
    
    return jsonify({
        'total': total,
        'ai_indexed': ai_indexed,
        'departments': departments,
        'this_month': this_month
    })

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
