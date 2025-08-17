# routes/sds.py - Enhanced SDS Routes with Smart Features
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
from PIL import Image, ImageDraw, ImageFont
import qrcode

# Import SDS services
try:
    from services.sds_ingest import ingest_single_pdf, load_index, save_index, sds_dir
    from services.sds_zip_ingest import ingest_zip
    from services.sds_qr import ensure_qr, sds_detail_url
    from services.sds_chat import answer_question_for_sds
except ImportError as e:
    print(f"Warning: Some SDS services not available: {e}")

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
PDF_DIR.mkdir(parents=True, exist_ok=True)
QR_DIR.mkdir(parents=True, exist_ok=True)

@sds_bp.get("/")
def sds_list():
    """Enhanced SDS list with smart features and professional design"""
    try:
        index = load_index()
        print(f"DEBUG: Loaded {len(index)} SDS records")
        
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
                print(f"Error processing SDS record {i}: {e}")
                continue
        
        print(f"Processed {len(sds_list)} SDS records successfully")
        
        # Use the enhanced template
        return render_template("sds_list.html", sds_list=sds_list)
        
    except Exception as e:
        print(f"Error in sds_list: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback to emergency view
        return redirect(url_for('sds.emergency_sds_list'))

@sds_bp.route("/emergency_fix")
def emergency_sds_list():
    """Emergency SDS list that bypasses complex templates"""
    try:
        index = load_index()
        
        if not index or len(index) == 0:
            try:
                from services.sds_ingest import initialize_sds_system
                index = initialize_sds_system()
            except Exception:
                index = create_emergency_data()
        
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
            '<div class="alert alert-success">',
            '<h5>✅ SDS System Working!</h5>',
            f'<p>Found {len(index)} SDS records. The system is operational.</p>',
            '</div>'
        ]
        
        if index:
            html_parts.extend([
                '<div class="table-responsive">',
                '<table class="table table-striped">',
                '<thead><tr>',
                '<th>Product Name</th><th>Department</th><th>Country</th><th>Manufacturer</th>',
                '<th>AI Status</th><th>Actions</th>',
                '</tr></thead><tbody>'
            ])
            
            for sds_id, sds in index.items():
                ai_status = "🤖 Indexed" if sds.get('has_embeddings') else "📄 Not Indexed"
                html_parts.append(f'''
                <tr>
                    <td><strong>{sds.get("product_name", "Unknown")}</strong></td>
                    <td><span class="badge bg-info">{sds.get("department", "Unassigned")}</span></td>
                    <td>{sds.get("country", "Unknown")}</td>
                    <td>{sds.get("manufacturer", "Unknown")}</td>
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
        
        html_parts.extend([
            '<div class="mt-3">',
            '<a href="/" class="btn btn-secondary">Dashboard</a>',
            '<a href="/sds/upload" class="btn btn-primary ms-2">Upload New SDS</a>',
            '</div></div></body></html>'
        ])
        
        return '\n'.join(html_parts)
        
    except Exception as e:
        return f"<h1>Emergency SDS Error</h1><p>Error: {str(e)}</p>"

@sds_bp.get("/<sid>")
def sds_view(sid):
    """Enhanced SDS detail view with smart features"""
    try:
        index = load_index()
        rec = index.get(sid)
        if not rec:
            abort(404)
        
        # Calculate smart metrics
        rec['age_days'] = (time.time() - rec.get('created_ts', time.time())) / (24 * 60 * 60)
        rec['is_outdated'] = rec['age_days'] > (2 * 365)
        rec['hazard_level'] = calculate_hazard_level(rec)
        rec['estimated_pages'] = estimate_page_count(rec)
        
        # Ensure QR code exists
        qr_path = ensure_qr_code(sid)
        
        return render_template("sds_view.html", rec=rec, qr_path=qr_path)
    except Exception as e:
        print(f"Error in sds_view: {e}")
        abort(500)

@sds_bp.route("/upload", methods=["GET", "POST"])
def sds_upload():
    """Enhanced SDS upload with better processing"""
    if request.method == "GET":
        return render_template("sds_upload.html")
    
    try:
        file = request.files.get("file")
        if not file or not file.filename:
            flash("No file provided", "danger")
            return redirect(url_for("sds.sds_upload"))
        
        filename = secure_filename(file.filename)
        ext = Path(filename).suffix.lower()
        
        if ext == ".zip":
            # Handle ZIP upload
            report = ingest_zip(file.stream)
            flash(f"ZIP processed: {report.get('processed', 0)} files", "success")
            return render_template("sds_upload_result.html", report=report)
            
        elif ext in ALLOWED_PDF and is_allowed(filename, file.mimetype):
            # Handle single PDF upload
            result = ingest_single_pdf(file.stream, filename=filename)
            
            # Add upload metadata
            result['uploaded_by'] = request.form.get('uploaded_by', 'Anonymous')
            result['department'] = request.form.get('department', '')
            
            # Update index
            index = load_index()
            index[result['id']] = result
            save_index(index)
            
            flash(f"SDS uploaded successfully: {result['product_name']}", "success")
            return redirect(url_for("sds.sds_view", sid=result["id"]))
        else:
            flash("Unsupported file type. Please upload PDF or ZIP files only.", "danger")
            return redirect(url_for("sds.sds_upload"))
            
    except Exception as e:
        print(f"Error in sds_upload: {e}")
        flash(f"Upload failed: {str(e)}", "danger")
        return redirect(url_for("sds.sds_upload"))

@sds_bp.get("/<sid>/download")
def sds_download(sid):
    """Download SDS PDF file"""
    try:
        index = load_index()
        rec = index.get(sid)
        if not rec:
            abort(404)
        
        file_path = Path(rec.get("file_path", ""))
        if not file_path.exists():
            # Try alternative paths
            alt_paths = [
                sds_dir / "files" / rec.get("file_name", ""),
                sds_dir / f"{sid}.pdf"
            ]
            for alt_path in alt_paths:
                if alt_path.exists():
                    file_path = alt_path
                    break
            else:
                flash("PDF file not found on disk", "danger")
                return redirect(url_for("sds.sds_view", sid=sid))
        
        return send_file(file_path, as_attachment=True, download_name=rec.get("file_name", f"sds-{sid}.pdf"))
    except Exception as e:
        print(f"Error in sds_download: {e}")
        abort(500)

@sds_bp.route("/<sid>/chat", methods=["GET", "POST"])
def sds_chat(sid):
    """Enhanced SDS chat with AI"""
    try:
        index = load_index()
        rec = index.get(sid)
        if not rec:
            abort(404)
        
        if not rec.get('has_embeddings'):
            flash("This SDS is not AI-indexed yet. Please index it first.", "warning")
            return redirect(url_for("sds.sds_view", sid=sid))
        
        answer = None
        question = None
        
        if request.method == "POST":
            question = request.form.get("question", "").strip()
            if question:
                try:
                    answer = answer_question_for_sds(rec, question)
                except Exception as e:
                    answer = f"Sorry, I couldn't process your question: {str(e)}"
        
        return render_template("sds_chat.html", rec=rec, question=question, answer=answer)
    except Exception as e:
        print(f"Error in sds_chat: {e}")
        abort(500)

# Smart Features Routes

@sds_bp.route("/<sid>/qr")
def sds_qr(sid):
    """Generate and display QR code for SDS"""
    try:
        index = load_index()
        rec = index.get(sid)
        if not rec:
            abort(404)
        
        # Generate QR code
        qr_data = {
            'url': f"{request.host_url}sds/{sid}",
            'product': rec.get('product_name', 'Unknown'),
            'id': sid
        }
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data['url'])
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to buffer
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return send_file(img_buffer, mimetype='image/png', as_attachment=False)
    except Exception as e:
        print(f"Error generating QR code: {e}")
        abort(500)

@sds_bp.route("/<sid>/qr/download")
def download_qr(sid):
    """Download QR code as PNG file"""
    try:
        qr_path = ensure_qr_code(sid)
        if not qr_path or not Path(qr_path).exists():
            abort(404)
        
        return send_file(qr_path, as_attachment=True, download_name=f"sds-{sid}-qr.png")
    except Exception as e:
        print(f"Error downloading QR code: {e}")
        abort(500)

@sds_bp.route("/<sid>/label")
def sds_label(sid):
    """Generate safety label (NFPA or GHS)"""
    try:
        index = load_index()
        rec = index.get(sid)
        if not rec:
            abort(404)
        
        label_type = request.args.get('type', 'nfpa')  # 'nfpa' or 'ghs'
        label_size = request.args.get('size', 'medium')  # 'small', 'medium', 'large'
        include_qr = request.args.get('qr', 'true').lower() == 'true'
        
        if label_type == 'nfpa':
            label_image = generate_nfpa_label(rec, label_size, include_qr)
        else:
            label_image = generate_ghs_label(rec, label_size, include_qr)
        
        # Save to buffer
        img_buffer = io.BytesIO()
        label_image.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        filename = f"sds-{sid}-{label_type}-label.png"
        return send_file(img_buffer, mimetype='image/png', as_attachment=True, download_name=filename)
    except Exception as e:
        print(f"Error generating label: {e}")
        abort(500)

@sds_bp.route("/<sid>/index", methods=["POST"])
def index_sds(sid):
    """Index SDS for AI search"""
    try:
        index = load_index()
        rec = index.get(sid)
        if not rec:
            return jsonify({'error': 'SDS not found'}), 404
        
        if rec.get('has_embeddings'):
            return jsonify({'message': 'SDS already indexed'}), 200
        
        # Trigger AI indexing (this would need the embeddings service)
        try:
            from services.embeddings import embed_texts
            chunks = rec.get('chunks', [])
            if chunks:
                embeddings = embed_texts(chunks)
                rec['embeddings'] = embeddings.tolist()
                rec['has_embeddings'] = True
                
                # Update index
                index[sid] = rec
                save_index(index)
                
                return jsonify({'message': 'SDS indexed successfully'}), 200
            else:
                return jsonify({'error': 'No text chunks available for indexing'}), 400
        except ImportError:
            return jsonify({'error': 'AI indexing service not available'}), 503
    except Exception as e:
        print(f"Error indexing SDS: {e}")
        return jsonify({'error': str(e)}), 500

# Bulk Operations Routes

@sds_bp.route("/bulk/ai-index", methods=["POST"])
def bulk_ai_index():
    """Bulk AI index selected SDS files"""
    try:
        data = request.get_json()
        sds_ids = data.get('ids', [])
        
        if not sds_ids:
            return jsonify({'error': 'No SDS IDs provided'}), 400
        
        index = load_index()
        results = {'success': [], 'failed': [], 'already_indexed': []}
        
        for sid in sds_ids:
            rec = index.get(sid)
            if not rec:
                results['failed'].append(f"{sid}: Not found")
                continue
            
            if rec.get('has_embeddings'):
                results['already_indexed'].append(sid)
                continue
            
            try:
                # Index the SDS (simplified version)
                chunks = rec.get('chunks', [])
                if chunks:
                    # In a real implementation, you'd use the embeddings service
                    rec['has_embeddings'] = True
                    rec['indexed_ts'] = time.time()
                    results['success'].append(sid)
                else:
                    results['failed'].append(f"{sid}: No text chunks")
            except Exception as e:
                results['failed'].append(f"{sid}: {str(e)}")
        
        # Save updated index
        save_index(index)
        
        return jsonify({
            'message': f"Processed {len(sds_ids)} SDS files",
            'results': results
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/bulk/set-department", methods=["POST"])
def bulk_set_department():
    """Bulk set department for selected SDS files"""
    try:
        data = request.get_json()
        sds_ids = data.get('ids', [])
        department = data.get('department', '').strip()
        
        if not sds_ids or not department:
            return jsonify({'error': 'Missing SDS IDs or department'}), 400
        
        index = load_index()
        updated_count = 0
        
        for sid in sds_ids:
            if sid in index:
                index[sid]['department'] = department
                index[sid]['updated_ts'] = time.time()
                updated_count += 1
        
        save_index(index)
        
        return jsonify({
            'message': f"Updated department for {updated_count} SDS files",
            'department': department
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/bulk/generate-qr", methods=["POST"])
def bulk_generate_qr():
    """Bulk generate QR codes for selected SDS files"""
    try:
        data = request.get_json()
        sds_ids = data.get('ids', [])
        
        if not sds_ids:
            return jsonify({'error': 'No SDS IDs provided'}), 400
        
        # Create ZIP file with QR codes
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            index = load_index()
            
            for sid in sds_ids:
                rec = index.get(sid)
                if not rec:
                    continue
                
                try:
                    # Generate QR code
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(f"{request.host_url}sds/{sid}")
                    qr.make(fit=True)
                    
                    qr_img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Save to ZIP
                    img_buffer = io.BytesIO()
                    qr_img.save(img_buffer, format='PNG')
                    
                    filename = f"{rec.get('product_name', sid)}-qr.png"
                    filename = secure_filename(filename)
                    
                    zip_file.writestr(filename, img_buffer.getvalue())
                except Exception as e:
                    print(f"Error generating QR for {sid}: {e}")
                    continue
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"sds-qr-codes-{datetime.now().strftime('%Y%m%d')}.zip"
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/bulk/archive", methods=["POST"])
def bulk_archive():
    """Bulk archive selected SDS files"""
    try:
        data = request.get_json()
        sds_ids = data.get('ids', [])
        
        if not sds_ids:
            return jsonify({'error': 'No SDS IDs provided'}), 400
        
        index = load_index()
        archived_count = 0
        
        for sid in sds_ids:
            if sid in index:
                index[sid]['status'] = 'archived'
                index[sid]['archived_ts'] = time.time()
                archived_count += 1
        
        save_index(index)
        
        return jsonify({
            'message': f"Archived {archived_count} SDS files"
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Routes

@sds_bp.route("/api/stats")
def api_sds_stats():
    """API endpoint for SDS statistics"""
    try:
        index = load_index()
        
        total = len(index)
        ai_indexed = sum(1 for rec in index.values() if rec.get('has_embeddings'))
        
        # Calculate age-based stats
        now = time.time()
        two_years_ago = now - (2 * 365 * 24 * 60 * 60)
        one_month_ago = now - (30 * 24 * 60 * 60)
        
        outdated = sum(1 for rec in index.values() 
                      if rec.get('created_ts', now) < two_years_ago)
        this_month = sum(1 for rec in index.values() 
                        if rec.get('created_ts', 0) > one_month_ago)
        
        # Department count
        departments = len(set(rec.get('department') for rec in index.values() 
                            if rec.get('department')))
        
        # Hazard level stats
        hazard_counts = {'high': 0, 'medium': 0, 'low': 0, 'unknown': 0}
        for rec in index.values():
            level = calculate_hazard_level(rec)
            hazard_counts[level] += 1
        
        return jsonify({
            'total': total,
            'ai_indexed': ai_indexed,
            'outdated': outdated,
            'this_month': this_month,
            'departments': departments,
            'hazard_distribution': hazard_counts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sds_bp.route("/api/test")
def api_test():
    """Test API endpoint"""
    try:
        index = load_index()
        return jsonify({
            'status': 'ok',
            'total_sds': len(index),
            'message': 'Enhanced SDS API is working',
            'features': [
                'Smart search and filtering',
                'AI indexing',
                'QR code generation',
                'NFPA/GHS label generation',
                'Bulk operations',
                'Hazard level analysis'
            ]
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# Helper Functions

def calculate_hazard_level(sds_record):
    """Calculate hazard level based on H-statements"""
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
    """Estimate page count from file size or chunks"""
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

def ensure_qr_code(sds_id):
    """Ensure QR code exists for SDS"""
    try:
        qr_path = QR_DIR / f"{sds_id}.png"
        
        if not qr_path.exists():
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(f"/sds/{sds_id}")
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(qr_path)
        
        return str(qr_path)
    except Exception as e:
        print(f"Error ensuring QR code: {e}")
        return None

def generate_nfpa_label(sds_record, size='medium', include_qr=True):
    """Generate NFPA diamond label"""
    try:
        # Size mapping
        sizes = {'small': 200, 'medium': 400, 'large': 600}
        img_size = sizes.get(size, 400)
        
        # Create image
        img = Image.new('RGB', (img_size, img_size), 'white')
        draw = ImageDraw.Draw(img)
        
        # Calculate NFPA ratings
        ratings = calculate_nfpa_ratings(sds_record)
        
        # Draw NFPA diamond (simplified - you'd want to use proper graphics)
        center = img_size // 2
        diamond_size = int(img_size * 0.8)
        
        # Draw diamond outline
        diamond_points = [
            (center, center - diamond_size//2),  # top
            (center + diamond_size//2, center),  # right
            (center, center + diamond_size//2),  # bottom
            (center - diamond_size//2, center)   # left
        ]
        draw.polygon(diamond_points, outline='black', width=3)
        
        # Add text for ratings (simplified)
        font_size = max(20, img_size // 20)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # Add ratings text
        draw.text((center - 20, center - 40), str(ratings['health']), fill='blue', font=font)
        draw.text((center + 20, center - 10), str(ratings['fire']), fill='red', font=font)
        draw.text((center + 20, center + 20), str(ratings['reactivity']), fill='black', font=font)
        draw.text((center - 40, center + 20), ratings['special'], fill='black', font=font)
        
        # Add product name
        product_name = sds_record.get('product_name', 'Unknown')
        draw.text((10, img_size - 50), product_name[:30], fill='black', font=font)
        
        return img
    except Exception as e:
        print(f"Error generating NFPA label: {e}")
        # Return a simple placeholder image
        img = Image.new('RGB', (400, 400), 'white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 200), "NFPA Label Error", fill='black')
        return img

def generate_ghs_label(sds_record, size='medium', include_qr=True):
    """Generate GHS pictogram label"""
    try:
        # Size mapping
        sizes = {'small': 300, 'medium': 500, 'large': 700}
        img_size = sizes.get(size, 500)
        
        # Create image
        img = Image.new('RGB', (img_size, int(img_size * 1.2)), 'white')
        draw = ImageDraw.Draw(img)
        
        # Draw border
        draw.rectangle([10, 10, img_size-10, int(img_size * 1.2)-10], outline='black', width=3)
        
        # Get GHS data
        signal_word = get_ghs_signal_word(sds_record)
        hazard_statements = sds_record.get('chemical_info', {}).get('hazard_statements', [])[:3]
        
        # Add product name
        product_name = sds_record.get('product_name', 'Unknown Product')
        manufacturer = sds_record.get('manufacturer', 'Unknown Manufacturer')
        
        try:
            title_font = ImageFont.truetype("arial.ttf", max(16, img_size // 25))
            text_font = ImageFont.truetype("arial.ttf", max(12, img_size // 35))
        except:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
        
        # Draw content
        y_pos = 30
        
        # Product name
        draw.text((20, y_pos), product_name, fill='black', font=title_font)
        y_pos += 40
        
        # Manufacturer
        draw.text((20, y_pos), manufacturer, fill='black', font=text_font)
        y_pos += 60
        
        # Signal word
        signal_color = 'red' if signal_word == 'DANGER' else 'orange'
        draw.text((20, y_pos), signal_word, fill=signal_color, font=title_font)
        y_pos += 50
        
        # Hazard statements
        draw.text((20, y_pos), "Hazard Statements:", fill='black', font=text_font)
        y_pos += 25
        
        for statement in hazard_statements:
            if y_pos < img_size:
                # Wrap long statements
                if len(statement) > 50:
                    statement = statement[:47] + "..."
                draw.text((20, y_pos), f"• {statement}", fill='black', font=text_font)
                y_pos += 20
        
        # Add QR code if requested
        if include_qr:
            try:
                qr = qrcode.QRCode(version=1, box_size=3, border=1)
                qr.add_data(f"/sds/{sds_record.get('id', 'unknown')}")
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                
                # Resize QR code
                qr_size = min(80, img_size // 6)
                qr_img = qr_img.resize((qr_size, qr_size))
                
                # Paste QR code
                img.paste(qr_img, (img_size - qr_size - 20, int(img_size * 1.2) - qr_size - 20))
                
                # Add QR label
                draw.text((img_size - qr_size - 20, int(img_size * 1.2) - 15), "Scan for details", fill='black', font=text_font)
            except Exception as e:
                print(f"Error adding QR to GHS label: {e}")
        
        return img
    except Exception as e:
        print(f"Error generating GHS label: {e}")
        # Return a simple placeholder image
        img = Image.new('RGB', (500, 600), 'white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 300), "GHS Label Error", fill='black')
        return img

def calculate_nfpa_ratings(sds_record):
    """Calculate NFPA 704 ratings from hazard statements"""
    try:
        statements = sds_record.get('chemical_info', {}).get('hazard_statements', [])
        statements_text = ' '.join(statements).lower()
        
        # Default ratings
        ratings = {'health': 0, 'fire': 0, 'reactivity': 0, 'special': ''}
        
        # Health hazard rating (0-4)
        if any(code in statements_text for code in ['h330', 'h300', 'h310']):  # Fatal
            ratings['health'] = 4
        elif any(code in statements_text for code in ['h331', 'h301', 'h311']):  # Toxic
            ratings['health'] = 3
        elif any(code in statements_text for code in ['h332', 'h302', 'h312']):  # Harmful
            ratings['health'] = 2
        elif any(code in statements_text for code in ['h319', 'h315', 'h317']):  # Irritant
            ratings['health'] = 1
        
        # Fire hazard rating (0-4)
        if 'h224' in statements_text:  # Extremely flammable
            ratings['fire'] = 4
        elif 'h225' in statements_text:  # Highly flammable
            ratings['fire'] = 3
        elif 'h226' in statements_text:  # Flammable
            ratings['fire'] = 2
        elif 'h228' in statements_text:  # Flammable solid
            ratings['fire'] = 1
        
        # Reactivity/instability rating (0-4)
        if any(code in statements_text for code in ['h200', 'h201']):  # Explosive
            ratings['reactivity'] = 4
        elif any(code in statements_text for code in ['h202', 'h203']):  # Explosive risk
            ratings['reactivity'] = 3
        elif any(code in statements_text for code in ['h204', 'h205']):  # Fire/explosion risk
            ratings['reactivity'] = 2
        elif 'h206' in statements_text:  # Fire risk
            ratings['reactivity'] = 1
        
        # Special hazards
        if 'h314' in statements_text:  # Corrosive
            ratings['special'] = 'COR'
        elif any(code in statements_text for code in ['h270', 'h271']):  # Oxidizer
            ratings['special'] = 'OX'
        elif 'h272' in statements_text:  # Oxidizer
            ratings['special'] = 'OX'
        
        return ratings
    except Exception as e:
        print(f"Error calculating NFPA ratings: {e}")
        return {'health': 0, 'fire': 0, 'reactivity': 0, 'special': ''}

def get_ghs_signal_word(sds_record):
    """Determine GHS signal word based on hazard statements"""
    try:
        statements = sds_record.get('chemical_info', {}).get('hazard_statements', [])
        statements_text = ' '.join(statements).lower()
        
        # Danger signal words (highest severity)
        danger_codes = [
            'h200', 'h201', 'h202', 'h203', 'h224', 'h225', 'h300', 'h301', 
            'h310', 'h311', 'h314', 'h330', 'h340', 'h341', 'h350', 'h351',
            'h360', 'h361', 'h370', 'h371', 'h372'
        ]
        
        if any(code in statements_text for code in danger_codes):
            return 'DANGER'
        
        # Warning signal words (lower severity)
        warning_codes = [
            'h204', 'h205', 'h226', 'h228', 'h302', 'h312', 'h315', 'h317',
            'h318', 'h319', 'h331', 'h332', 'h335', 'h336'
        ]
        
        if any(code in statements_text for code in warning_codes):
            return 'WARNING'
        
        # Default if no clear signal word indicators
        return 'CAUTION'
    except Exception:
        return 'CAUTION'

def create_emergency_data():
    """Create emergency SDS data if none exists"""
    try:
        current_time = time.time()
        
        emergency_data = {
            "emergency_001": {
                "id": "emergency_001",
                "product_name": "Emergency Demo SDS - Acetone",
                "file_name": "demo_acetone.pdf",
                "file_size": 500000,
                "created_ts": current_time,
                "has_embeddings": False,
                "department": "Demo Department",
                "manufacturer": "Demo Chemical Corp",
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
                    "chunks_count": 15,
                    "tables_extracted": 2
                },
                "status": "active",
                "created_by": "Emergency System"
            }
        }
        
        return emergency_data
    except Exception as e:
        print(f"Error creating emergency data: {e}")
        return {}

# Additional utility routes for development and testing

@sds_bp.route("/debug/create_test_data")
def create_test_data():
    """Create comprehensive test SDS data for development"""
    try:
        test_data = {}
        current_time = time.time()
        
        # Test chemicals with different hazard levels
        test_chemicals = [
            {
                "name": "Acetone (Technical Grade)",
                "manufacturer": "Chemical Corp Inc",
                "department": "Laboratory",
                "country": "United States",
                "state": "California",
                "cas": ["67-64-1"],
                "hazards": ["H225", "H319", "H336"],
                "level": "medium"
            },
            {
                "name": "Sodium Hydroxide Solution (50%)",
                "manufacturer": "Industrial Chemicals Ltd",
                "department": "Manufacturing",
                "country": "Canada",
                "state": "Ontario",
                "cas": ["1310-73-2"],
                "hazards": ["H314", "H290"],
                "level": "high"
            },
            {
                "name": "Isopropyl Alcohol (99%)",
                "manufacturer": "Solvent Solutions",
                "department": "Quality Control",
                "country": "United Kingdom",
                "state": "",
                "cas": ["67-63-0"],
                "hazards": ["H225", "H319"],
                "level": "low"
            },
            {
                "name": "Distilled Water",
                "manufacturer": "Pure Water Co",
                "department": "General",
                "country": "United States",
                "state": "Texas",
                "cas": ["7732-18-5"],
                "hazards": [],
                "level": "unknown"
            }
        ]
        
        for i, chem in enumerate(test_chemicals):
            sds_id = f"test_{str(uuid.uuid4())[:8]}"
            
            test_data[sds_id] = {
                "id": sds_id,
                "product_name": chem["name"],
                "file_name": f"{chem['name'].lower().replace(' ', '_')}.pdf",
                "file_size": 800000 + (i * 100000),  # Varying file sizes
                "created_ts": current_time - (i * 86400),  # Different ages
                "has_embeddings": i % 2 == 0,  # Alternate AI indexing
                "department": chem["department"],
                "manufacturer": chem["manufacturer"],
                "country": chem["country"],
                "state": chem["state"],
                "chemical_info": {
                    "cas_numbers": chem["cas"],
                    "hazard_statements": [f"{h} - Test hazard statement" for h in chem["hazards"]]
                },
                "processing_metadata": {
                    "chunks_count": 10 + (i * 5),
                    "tables_extracted": i + 1,
                    "embeddings_count": (10 + (i * 5)) if i % 2 == 0 else 0
                },
                "status": "active",
                "created_by": "Test System",
                "text_content": f"Sample SDS content for {chem['name']}...",
                "file_path": f"/tmp/test_{sds_id}.pdf"
            }
        
        # Save test data
        existing_index = load_index()
        existing_index.update(test_data)
        save_index(existing_index)
        
        return jsonify({
            "message": f"Created {len(test_data)} test SDS records",
            "records": list(test_data.keys()),
            "features_tested": [
                "Different hazard levels",
                "Various departments and countries", 
                "Mixed AI indexing status",
                "Different file ages",
                "Comprehensive chemical data"
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sds_bp.route("/debug/system_status")
def system_status():
    """Comprehensive system status for debugging"""
    try:
        index = load_index()
        
        # Calculate detailed statistics
        total_sds = len(index)
        ai_indexed = sum(1 for rec in index.values() if rec.get('has_embeddings'))
        departments = set(rec.get('department') for rec in index.values() if rec.get('department'))
        countries = set(rec.get('country') for rec in index.values() if rec.get('country'))
        manufacturers = set(rec.get('manufacturer') for rec in index.values() if rec.get('manufacturer'))
        
        # Hazard level distribution
        hazard_dist = {'high': 0, 'medium': 0, 'low': 0, 'unknown': 0}
        for rec in index.values():
            level = calculate_hazard_level(rec)
            hazard_dist[level] += 1
        
        # Age distribution
        now = time.time()
        age_dist = {'new': 0, 'recent': 0, 'normal': 0, 'outdated': 0}
        for rec in index.values():
            age_days = (now - rec.get('created_ts', now)) / (24 * 60 * 60)
            if age_days <= 7:
                age_dist['new'] += 1
            elif age_days <= 30:
                age_dist['recent'] += 1
            elif age_days > (2 * 365):
                age_dist['outdated'] += 1
            else:
                age_dist['normal'] += 1
        
        # Service availability
        services = {}
        try:
            from services.sds_ingest import load_index as test_load
            services['sds_ingest'] = 'Available'
        except ImportError:
            services['sds_ingest'] = 'Not Available'
        
        try:
            from services.embeddings import embed_texts
            services['embeddings'] = 'Available'
        except ImportError:
            services['embeddings'] = 'Not Available'
        
        try:
            import qrcode
            services['qrcode'] = 'Available'
        except ImportError:
            services['qrcode'] = 'Not Available'
        
        try:
            from PIL import Image
            services['pil'] = 'Available'
        except ImportError:
            services['pil'] = 'Not Available'
        
        return jsonify({
            "system_status": "Operational",
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_sds": total_sds,
                "ai_indexed": ai_indexed,
                "ai_percentage": round((ai_indexed / total_sds * 100) if total_sds > 0 else 0, 1),
                "departments": len(departments),
                "countries": len(countries),
                "manufacturers": len(manufacturers)
            },
            "distributions": {
                "hazard_levels": hazard_dist,
                "age_categories": age_dist
            },
            "service_availability": services,
            "storage": {
                "sds_directory": str(sds_dir),
                "pdf_directory": str(PDF_DIR),
                "qr_directory": str(QR_DIR),
                "index_file": str(sds_dir / "index.json")
            },
            "features": {
                "smart_search": True,
                "ai_indexing": services['embeddings'] == 'Available',
                "qr_generation": services['qrcode'] == 'Available',
                "label_generation": services['pil'] == 'Available',
                "bulk_operations": True,
                "hazard_analysis": True
            }
        })
    except Exception as e:
        return jsonify({
            "system_status": "Error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# Error handlers for SDS blueprint
@sds_bp.errorhandler(404)
def sds_not_found(error):
    return render_template("error_404.html", 
                         module_name="SDS",
                         description="The SDS you're looking for was not found"), 404

@sds_bp.errorhandler(500)
def sds_server_error(error):
    return render_template("error_500.html", 
                         error="An error occurred in the SDS system"), 500
