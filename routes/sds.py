# routes/sds.py - Fixed SDS Routes with Comprehensive Error Handling
import io
import json
import time
import zipfile
import uuid
import base64
import os
from pathlib import Path
from datetime import datetime, timedelta
from flask import Blueprint, request, render_template, send_file, abort, flash, redirect, url_for, jsonify, Response
from werkzeug.utils import secure_filename

# Enhanced import handling with fallbacks
print("🔄 Loading SDS services...")

# Import PIL and QR code with fallbacks
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
    print("✅ PIL (Pillow) available")
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ PIL (Pillow) not available - label generation disabled")

try:
    import qrcode
    QRCODE_AVAILABLE = True
    print("✅ QRCode library available")
except ImportError:
    QRCODE_AVAILABLE = False
    print("⚠️ QRCode library not available - QR generation disabled")

# Import SDS services with comprehensive fallbacks
SDS_SERVICES_AVAILABLE = False
load_index = None
save_index = None
sds_dir = None

try:
    from services.sds_ingest import load_index, save_index, sds_dir
    SDS_SERVICES_AVAILABLE = True
    print("✅ SDS ingest services available")
except ImportError as e:
    print(f"⚠️ SDS ingest services not available: {e}")
    print("🔧 Creating fallback functions...")
    
    # Create fallback storage system
    if os.environ.get('RENDER'):
        FALLBACK_SDS_DIR = Path("/tmp/sds_data")
    else:
        FALLBACK_SDS_DIR = Path("data/sds")
    
    FALLBACK_SDS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE = FALLBACK_SDS_DIR / "index.json"
    
    def load_index():
        """Fallback load_index function"""
        try:
            if INDEX_FILE.exists():
                with open(INDEX_FILE, 'r') as f:
                    data = json.load(f)
                print(f"📂 Loaded {len(data)} SDS records from fallback storage")
                return data
            else:
                print("📂 No existing index found, creating new one")
                return {}
        except Exception as e:
            print(f"❌ Error loading index: {e}")
            return {}
    
    def save_index(data):
        """Fallback save_index function"""
        try:
            with open(INDEX_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"💾 Saved {len(data)} SDS records to fallback storage")
            return True
        except Exception as e:
            print(f"❌ Error saving index: {e}")
            return False
    
    sds_dir = FALLBACK_SDS_DIR
    print(f"📁 Using fallback SDS directory: {sds_dir}")

# Try to import other SDS services with fallbacks
try:
    from services.sds_zip_ingest import ingest_zip
    ZIP_INGEST_AVAILABLE = True
    print("✅ ZIP ingest available")
except ImportError:
    ZIP_INGEST_AVAILABLE = False
    print("⚠️ ZIP ingest not available")
    
    def ingest_zip(zip_stream):
        return {"processed": 0, "ok": [], "skipped": [], "errors": ["ZIP ingest service not available"]}

try:
    from services.sds_chat import answer_question_for_sds
    CHAT_AVAILABLE = True
    print("✅ SDS chat available")
except ImportError:
    CHAT_AVAILABLE = False
    print("⚠️ SDS chat not available")
    
    def answer_question_for_sds(rec, question):
        return "AI chat service is not available. Please install required dependencies."

# Import utilities with fallbacks
try:
    from utils.uploads import is_allowed, save_upload
except ImportError:
    def is_allowed(filename, mimetype):
        return filename.lower().endswith('.pdf')
    
    def save_upload(file, filename):
        return filename

# Blueprint setup
sds_bp = Blueprint("sds", __name__, template_folder="../templates")

# Constants
ALLOWED_PDF = {".pdf"}
PDF_DIR = Path("data/pdf") if not os.environ.get('RENDER') else Path("/tmp/pdf")
QR_DIR = Path("static/qr") if not os.environ.get('RENDER') else Path("/tmp/qr")

# Ensure directories exist
try:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    QR_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Directories created: {PDF_DIR}, {QR_DIR}")
except Exception as e:
    print(f"⚠️ Could not create directories: {e}")

@sds_bp.get("/")
def sds_list():
    """Enhanced SDS list with comprehensive error handling"""
    try:
        print("🔄 Loading SDS list...")
        
        # Test if load_index function is available
        if not load_index:
            raise Exception("SDS services not properly initialized")
        
        index = load_index()
        print(f"📊 Loaded {len(index)} SDS records")
        
        # If no data exists, create some sample data
        if len(index) == 0:
            print("📝 No SDS data found, creating sample data...")
            index = create_sample_sds_data()
            save_index(index)
        
        # Transform data for enhanced template
        sds_list = []
        for i, (sds_id, rec) in enumerate(index.items()):
            try:
                # Calculate additional smart fields
                created_date = rec.get('created_ts', time.time())
                age_days = (time.time() - created_date) / (24 * 60 * 60)
                
                sds_item = {
                    'id': sds_id,
                    'product_name': rec.get('product_name', 'Unknown Product'),
                    'file_name': rec.get('file_name', 'unknown.pdf'),
                    'file_size': rec.get('file_size', 0),
                    'created_date': created_date,
                    'created_ts': created_date,
                    'has_embeddings': rec.get('has_embeddings', False),
                    
                    # Enhanced fields
                    'department': rec.get('department', ''),
                    'manufacturer': rec.get('manufacturer', ''),
                    'country': rec.get('country', ''),
                    'state': rec.get('state', ''),
                    'chemical_info': rec.get('chemical_info', {
                        'cas_numbers': [],
                        'hazard_statements': []
                    }),
                    'processing_metadata': rec.get('processing_metadata', {
                        'chunks_count': 0,
                        'tables_extracted': 0
                    }),
                    
                    # Smart calculated fields
                    'text_len': len(rec.get('text_content', '')),
                    'created_by': rec.get('created_by', 'System'),
                    'status': rec.get('status', 'active'),
                    'age_days': age_days,
                    'is_new': age_days <= 7,
                    'is_outdated': age_days > (2 * 365),  # > 2 years
                    'hazard_level': calculate_hazard_level(rec),
                    'estimated_pages': estimate_page_count(rec)
                }
                
                sds_list.append(sds_item)
                
            except Exception as e:
                print(f"⚠️ Error processing SDS record {i}: {e}")
                continue
        
        print(f"✅ Processed {len(sds_list)} SDS records successfully")
        
        # Use the enhanced template
        return render_template("sds_list.html", sds_list=sds_list)
        
    except Exception as e:
        print(f"❌ Error in sds_list: {e}")
        import traceback
        traceback.print_exc()
        
        # Return emergency fallback instead of redirect to avoid loops
        return emergency_sds_response(str(e))

def emergency_sds_response(error_message):
    """Generate emergency SDS response with error details"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SDS Library - System Error</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-4">
            <div class="alert alert-danger">
                <h4><i class="bi bi-exclamation-triangle"></i> SDS System Error</h4>
                <p><strong>Error:</strong> {error_message}</p>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <h5>🔧 Troubleshooting Steps</h5>
                </div>
                <div class="card-body">
                    <h6>1. Install Missing Dependencies</h6>
                    <p>Run these commands to install required packages:</p>
                    <pre class="bg-light p-2 rounded">
pip install PyMuPDF==1.24.10
pip install qrcode[pil]==7.4.2  
pip install Pillow==10.4.0</pre>
                    
                    <h6>2. Check File Structure</h6>
                    <p>Ensure these files exist:</p>
                    <ul>
                        <li><code>services/__init__.py</code></li>
                        <li><code>services/sds_ingest.py</code></li>
                        <li><code>routes/__init__.py</code></li>
                        <li><code>routes/sds.py</code></li>
                    </ul>
                    
                    <h6>3. Try Emergency Actions</h6>
                    <div class="d-grid gap-2 d-md-flex">
                        <a href="/sds/emergency_fix" class="btn btn-warning">Emergency Mode</a>
                        <a href="/sds/debug/system_status" class="btn btn-info">System Status</a>
                        <a href="/sds/debug/create_test_data" class="btn btn-success">Create Test Data</a>
                        <a href="/" class="btn btn-secondary">Back to Dashboard</a>
                    </div>
                </div>
            </div>
            
            <div class="card mt-3">
                <div class="card-header">
                    <h6>📋 System Status</h6>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-4">
                            <h6>Services Status</h6>
                            <ul class="list-unstyled">
                                <li>{'✅' if load_index else '❌'} SDS Storage</li>
                                <li>{'✅' if ZIP_INGEST_AVAILABLE else '❌'} ZIP Processing</li>
                                <li>{'✅' if CHAT_AVAILABLE else '❌'} AI Chat</li>
                                <li>{'✅' if QRCODE_AVAILABLE else '❌'} QR Codes</li>
                                <li>{'✅' if PIL_AVAILABLE else '❌'} Label Generation</li>
                            </ul>
                        </div>
                        <div class="col-md-4">
                            <h6>Environment</h6>
                            <ul class="list-unstyled">
                                <li><strong>Platform:</strong> {'Render' if os.environ.get('RENDER') else 'Local'}</li>
                                <li><strong>Storage:</strong> {sds_dir if sds_dir else 'Not configured'}</li>
                                <li><strong>Python:</strong> Available</li>
                            </ul>
                        </div>
                        <div class="col-md-4">
                            <h6>Quick Actions</h6>
                            <div class="d-grid gap-2">
                                <button class="btn btn-sm btn-primary" onclick="location.reload()">Retry</button>
                                <a href="/debug/routes" class="btn btn-sm btn-secondary">Check Routes</a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@sds_bp.route("/emergency_fix")
def emergency_sds_list():
    """Emergency SDS list that works without complex dependencies"""
    try:
        print("🚨 Emergency SDS mode activated")
        
        # Try to load data, create sample if none exists
        try:
            index = load_index() if load_index else {}
        except:
            index = {}
        
        if len(index) == 0:
            print("📝 Creating emergency sample data...")
            index = create_sample_sds_data()
            if save_index:
                save_index(index)
        
        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<title>SDS Library - Emergency Mode</title>',
            '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">',
            '<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">',
            '</head><body>',
            '<div class="container mt-4">',
            '<div class="d-flex justify-content-between align-items-center mb-4">',
            '<h2><i class="bi bi-file-earmark-text text-success"></i> SDS Library (Emergency Mode)</h2>',
            '<a href="/sds/upload" class="btn btn-primary">Upload SDS</a>',
            '</div>',
            '<div class="alert alert-warning">',
            '<h5><i class="bi bi-exclamation-triangle"></i> Emergency Mode Active</h5>',
            f'<p>Found {len(index)} SDS records. Some features may be limited.</p>',
            '<p><strong>To enable all features:</strong> Install PyMuPDF, qrcode, and Pillow packages.</p>',
            '</div>'
        ]
        
        if index:
            html_parts.extend([
                '<div class="table-responsive">',
                '<table class="table table-striped">',
                '<thead><tr>',
                '<th>ID</th><th>Product Name</th><th>Department</th><th>Country</th>',
                '<th>Manufacturer</th><th>AI Status</th><th>Actions</th>',
                '</tr></thead><tbody>'
            ])
            
            for sds_id, sds in index.items():
                ai_status = "🤖 Indexed" if sds.get('has_embeddings') else "📄 Not Indexed"
                product_name = sds.get("product_name", "Unknown")[:40]
                department = sds.get("department", "Unassigned")
                country = sds.get("country", "Unknown")
                manufacturer = sds.get("manufacturer", "Unknown")[:30]
                
                html_parts.append(f'''
                <tr>
                    <td><code>{sds_id[:8]}</code></td>
                    <td><strong>{product_name}</strong></td>
                    <td><span class="badge bg-info">{department}</span></td>
                    <td>{country}</td>
                    <td>{manufacturer}</td>
                    <td>{ai_status}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <a href="/sds/{sds_id}" class="btn btn-outline-primary">View</a>
                            <a href="/sds/{sds_id}/download" class="btn btn-outline-success">Download</a>
                            {"<a href='/sds/" + sds_id + "/chat' class='btn btn-outline-info'>Chat</a>" if sds.get('has_embeddings') else ""}
                        </div>
                    </td>
                </tr>
                ''')
            
            html_parts.extend(['</tbody></table></div>'])
        else:
            html_parts.append('<div class="alert alert-info">No SDS records found. <a href="/sds/upload">Upload your first SDS</a>.</div>')
        
        html_parts.extend([
            '<div class="mt-3">',
            '<a href="/" class="btn btn-secondary">Dashboard</a>',
            '<a href="/sds/upload" class="btn btn-primary ms-2">Upload New SDS</a>',
            '<a href="/sds/" class="btn btn-warning ms-2">Try Full Mode</a>',
            '</div>',
            '<div class="mt-3">',
            '<small class="text-muted">Emergency Mode: Limited functionality. Install dependencies for full features.</small>',
            '</div>',
            '</div></body></html>'
        ])
        
        return '\n'.join(html_parts)
        
    except Exception as e:
        return f"""
        <html><body>
        <div class="container mt-4">
        <h1>🚨 Critical SDS Error</h1>
        <div class="alert alert-danger">
        <p><strong>Error:</strong> {str(e)}</p>
        <p><strong>Solution:</strong> Install required dependencies:</p>
        <pre>pip install PyMuPDF==1.24.10 qrcode[pil]==7.4.2 Pillow==10.4.0</pre>
        </div>
        <a href="/" class="btn btn-primary">Back to Dashboard</a>
        </div>
        </body></html>
        """

def create_sample_sds_data():
    """Create sample SDS data that works without dependencies"""
    current_time = time.time()
    
    sample_data = {
        "demo_001": {
            "id": "demo_001",
            "product_name": "Acetone (Technical Grade)",
            "file_name": "acetone_sds.pdf",
            "file_size": 1024000,
            "created_ts": current_time - 86400,  # 1 day ago
            "has_embeddings": True,
            "department": "Laboratory",
            "manufacturer": "Chemical Corp Inc",
            "country": "United States",
            "state": "California",
            "chemical_info": {
                "cas_numbers": ["67-64-1"],
                "hazard_statements": [
                    "H225 - Highly flammable liquid and vapor",
                    "H319 - Causes serious eye irritation",
                    "H336 - May cause drowsiness or dizziness"
                ]
            },
            "processing_metadata": {
                "chunks_count": 25,
                "tables_extracted": 3
            },
            "status": "active",
            "created_by": "Demo System",
            "text_content": "Sample acetone safety data sheet content..."
        },
        "demo_002": {
            "id": "demo_002",
            "product_name": "Sodium Hydroxide Solution (50%)",
            "file_name": "naoh_sds.pdf",
            "file_size": 856000,
            "created_ts": current_time - 172800,  # 2 days ago
            "has_embeddings": False,
            "department": "Manufacturing",
            "manufacturer": "Industrial Chemicals Ltd",
            "country": "Canada",
            "state": "Ontario",
            "chemical_info": {
                "cas_numbers": ["1310-73-2"],
                "hazard_statements": [
                    "H314 - Causes severe skin burns and eye damage",
                    "H290 - May be corrosive to metals"
                ]
            },
            "processing_metadata": {
                "chunks_count": 18,
                "tables_extracted": 2
            },
            "status": "active",
            "created_by": "Demo System",
            "text_content": "Sample sodium hydroxide safety data sheet content..."
        },
        "demo_003": {
            "id": "demo_003",
            "product_name": "Isopropyl Alcohol (99%)",
            "file_name": "ipa_sds.pdf",
            "file_size": 742000,
            "created_ts": current_time - 259200,  # 3 days ago
            "has_embeddings": True,
            "department": "Quality Control",
            "manufacturer": "Solvent Solutions",
            "country": "United Kingdom",
            "state": "",
            "chemical_info": {
                "cas_numbers": ["67-63-0"],
                "hazard_statements": [
                    "H225 - Highly flammable liquid and vapor",
                    "H319 - Causes serious eye irritation"
                ]
            },
            "processing_metadata": {
                "chunks_count": 20,
                "tables_extracted": 1
            },
            "status": "active",
            "created_by": "Demo System",
            "text_content": "Sample isopropyl alcohol safety data sheet content..."
        }
    }
    
    print(f"📝 Created {len(sample_data)} sample SDS records")
    return sample_data

# Helper functions that work without dependencies
def calculate_hazard_level(sds_record):
    """Calculate hazard level based on H-statements (dependency-free)"""
    try:
        statements = sds_record.get('chemical_info', {}).get('hazard_statements', [])
        if not statements:
            return 'unknown'
        
        statements_text = ' '.join(statements).lower()
        
        # High risk H-codes
        high_risk = ['h300', 'h301', 'h310', 'h311', 'h330', 'h340', 'h350', 'h360', 'h370', 'h372']
        if any(code in statements_text for code in high_risk):
            return 'high'
        
        # Medium risk H-codes
        medium_risk = ['h302', 'h312', 'h315', 'h317', 'h318', 'h319', 'h331', 'h335']
        if any(code in statements_text for code in medium_risk):
            return 'medium'
        
        # If has any H-codes but not high/medium risk
        if 'h2' in statements_text or 'h3' in statements_text or 'h4' in statements_text:
            return 'low'
        
        return 'unknown'
    except Exception:
        return 'unknown'

def estimate_page_count(sds_record):
    """Estimate page count from file size or chunks (dependency-free)"""
    try:
        chunks = sds_record.get('processing_metadata', {}).get('chunks_count', 0)
        if chunks:
            return max(1, chunks // 3)  # Rough estimate: 3 chunks per page
        
        file_size = sds_record.get('file_size', 0)
        if file_size:
            return max(1, file_size // 100000)  # ~100KB per page
        
        return 1
    except Exception:
        return 1

# Basic routes that work without full dependencies
@sds_bp.get("/<sid>")
def sds_view(sid):
    """Basic SDS view that works without dependencies"""
    try:
        if not load_index:
            return emergency_sds_response("SDS services not available")
        
        index = load_index()
        rec = index.get(sid)
        if not rec:
            abort(404)
        
        # Calculate basic metrics
        rec['age_days'] = (time.time() - rec.get('created_ts', time.time())) / (24 * 60 * 60)
        rec['is_outdated'] = rec['age_days'] > (2 * 365)
        rec['hazard_level'] = calculate_hazard_level(rec)
        rec['estimated_pages'] = estimate_page_count(rec)
        
        return render_template("sds_view.html", rec=rec, qr_path=None)
    except Exception as e:
        print(f"Error in sds_view: {e}")
        return emergency_sds_response(str(e))

@sds_bp.route("/upload", methods=["GET", "POST"])
def sds_upload():
    """Basic SDS upload (limited without dependencies)"""
    if request.method == "GET":
        return render_template("sds_upload.html")
    
    # Without full dependencies, just show a message
    flash("SDS upload requires additional dependencies. Please install PyMuPDF.", "warning")
    return redirect(url_for("sds.emergency_sds_list"))

# Debug and status routes
@sds_bp.route("/debug/system_status")
def system_status():
    """System status endpoint"""
    try:
        index = load_index() if load_index else {}
        
        return jsonify({
            "system_status": "Operational" if load_index else "Limited",
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_sds": len(index),
                "services_available": {
                    "storage": bool(load_index),
                    "zip_ingest": ZIP_INGEST_AVAILABLE,
                    "ai_chat": CHAT_AVAILABLE,
                    "qr_codes": QRCODE_AVAILABLE,
                    "label_generation": PIL_AVAILABLE
                }
            },
            "dependencies": {
                "pymupdf": "Not Available" if not SDS_SERVICES_AVAILABLE else "Available",
                "qrcode": "Available" if QRCODE_AVAILABLE else "Not Available",
                "pil": "Available" if PIL_AVAILABLE else "Not Available"
            },
            "storage": {
                "sds_directory": str(sds_dir) if sds_dir else "Not configured",
                "pdf_directory": str(PDF_DIR),
                "qr_directory": str(QR_DIR)
            }
        })
    except Exception as e:
        return jsonify({
            "system_status": "Error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@sds_bp.route("/debug/create_test_data")
def create_test_data():
    """Create test data for development"""
    try:
        if not load_index or not save_index:
            return jsonify({"error": "Storage functions not available"}), 500
        
        test_data = create_sample_sds_data()
        existing_index = load_index()
        existing_index.update(test_data)
        save_index(existing_index)
        
        return jsonify({
            "message": f"Created {len(test_data)} test SDS records",
            "records": list(test_data.keys())
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API endpoint
@sds_bp.route("/api/test")
def api_test():
    """Test API endpoint"""
    return jsonify({
        'status': 'ok' if load_index else 'limited',
        'message': 'SDS API is working',
        'services': {
            'storage': bool(load_index),
            'zip_ingest': ZIP_INGEST_AVAILABLE,
            'ai_chat': CHAT_AVAILABLE,
            'qr_codes': QRCODE_AVAILABLE,
            'label_generation': PIL_AVAILABLE
        }
    })

print("✅ SDS routes loaded with comprehensive error handling")
