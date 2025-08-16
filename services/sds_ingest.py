# services/sds_ingest.py - RENDER-COMPATIBLE VERSION
import io
import json
import time
import hashlib
import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import fitz  # PyMuPDF

# Import embeddings with proper fallback handling
try:
    from .embeddings import embed_texts, is_sbert_available, SBERT_AVAILABLE
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    print("⚠ Embeddings service not available - SDS will work without embeddings")
    EMBEDDINGS_AVAILABLE = False
    SBERT_AVAILABLE = False
    
    def is_sbert_available():
        return False

# RENDER-COMPATIBLE: Use /tmp directory on Render, local data directory otherwise
def get_sds_storage_path():
    """Get appropriate storage path for different environments"""
    if os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT'):
        # On Render or Railway, use /tmp for temporary storage
        return Path("/tmp/sds_data")
    else:
        # Local development
        return Path("data/sds")

sds_dir = get_sds_storage_path()
INDEX_JSON = sds_dir / "index.json"

# Global in-memory cache for ephemeral environments
_sds_index_cache = None
_cache_timestamp = 0
CACHE_EXPIRY = 300  # 5 minutes

def ensure_sds_directory():
    """Ensure SDS directory exists, create if needed"""
    try:
        sds_dir.mkdir(parents=True, exist_ok=True)
        (sds_dir / "files").mkdir(exist_ok=True)
        print(f"✓ SDS directory created: {sds_dir}")
        return True
    except Exception as e:
        print(f"Warning: Could not create SDS directory: {e}")
        return False

def load_index():
    """Load SDS index with in-memory caching for ephemeral filesystems"""
    global _sds_index_cache, _cache_timestamp
    
    current_time = time.time()
    
    # Return cached version if available and fresh
    if (_sds_index_cache is not None and 
        current_time - _cache_timestamp < CACHE_EXPIRY):
        return _sds_index_cache.copy()
    
    # Try to load from file
    ensure_sds_directory()
    
    if INDEX_JSON.exists():
        try:
            with open(INDEX_JSON, 'r') as f:
                data = json.load(f)
            _sds_index_cache = data
            _cache_timestamp = current_time
            print(f"✓ Loaded SDS index with {len(data)} records")
            return data.copy()
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load SDS index: {e}")
    
    # Return empty index if file doesn't exist or can't be loaded
    empty_index = {}
    _sds_index_cache = empty_index
    _cache_timestamp = current_time
    print("✓ Created new empty SDS index")
    return empty_index.copy()

def save_index(obj):
    """Save SDS index with error handling for ephemeral filesystems"""
    global _sds_index_cache, _cache_timestamp
    
    ensure_sds_directory()
    
    try:
        # Create backup if index exists
        if INDEX_JSON.exists():
            backup_path = INDEX_JSON.with_suffix('.json.backup')
            try:
                INDEX_JSON.replace(backup_path)
            except:
                pass  # Ignore backup errors
        
        # Write new index
        with open(INDEX_JSON, 'w') as f:
            json.dump(obj, f, indent=2)
        
        # Update cache
        _sds_index_cache = obj.copy()
        _cache_timestamp = time.time()
        
        print(f"✓ Saved SDS index with {len(obj)} records")
        return True
    except Exception as e:
        print(f"Warning: Could not save SDS index to file: {e}")
        # Still update cache even if file save fails
        _sds_index_cache = obj.copy()
        _cache_timestamp = time.time()
        print("✓ Updated in-memory cache")
        return False

def _sha256_bytes(b: bytes) -> str:
    """Calculate SHA256 hash of bytes"""
    return hashlib.sha256(b).hexdigest()

def _extract_page_texts(pdf_bytes: bytes):
    """Return list of page texts"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text() or "")
        doc.close()
        return pages
    except Exception:
        return []

def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF with error handling"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        
        for page in doc:
            try:
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(page_text)
            except Exception as e:
                print(f"Warning: Failed to extract text from page: {e}")
                continue
        
        doc.close()
        return "\n".join(text_parts)
        
    except Exception as e:
        print(f"ERROR: Failed to extract text from PDF: {e}")
        return ""

def _extract_tables_from_pdf(pdf_bytes: bytes) -> List[Dict]:
    """Extract tables from PDF with error handling"""
    tables = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num, page in enumerate(doc):
            try:
                # Try to find tables using PyMuPDF
                tables_on_page = page.find_tables()
                for table in tables_on_page:
                    table_data = {
                        'page': page_num + 1,
                        'bbox': table.bbox,
                        'data': table.extract()
                    }
                    tables.append(table_data)
            except Exception as e:
                print(f"Warning: Failed to extract tables from page {page_num + 1}: {e}")
                continue
        
        doc.close()
        return tables
        
    except Exception as e:
        print(f"ERROR: Failed to extract tables from PDF: {e}")
        return []

def _extract_images_from_pdf(pdf_bytes: bytes) -> List[Dict]:
    """Extract images from PDF with metadata"""
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num, page in enumerate(doc):
            try:
                image_list = page.get_images()
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        
                        image_data = {
                            'page': page_num + 1,
                            'index': img_index,
                            'ext': base_image['ext'],
                            'width': base_image['width'],
                            'height': base_image['height'],
                            'size': len(base_image['image'])
                        }
                        images.append(image_data)
                    except Exception as e:
                        print(f"Warning: Failed to extract image {img_index} from page {page_num + 1}: {e}")
                        continue
            except Exception as e:
                print(f"Warning: Failed to get images from page {page_num + 1}: {e}")
                continue
        
        doc.close()
        return images
        
    except Exception as e:
        print(f"ERROR: Failed to extract images from PDF: {e}")
        return []

def _guess_product_name(text: str, filename: str = "") -> str:
    """Guess product name from text content and filename with enhanced patterns"""
    if not text:
        # Fallback to filename
        if filename:
            name = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
            return ' '.join(word.capitalize() for word in name.split())
        return "Unknown Product"
    
    lines = text.split('\n')[:30]  # Check first 30 lines
    
    # Enhanced product name patterns
    patterns = [
        r'product\s+name[:\s]*([^\n\r]+)',
        r'trade\s+name[:\s]*([^\n\r]+)',
        r'chemical\s+name[:\s]*([^\n\r]+)', 
        r'product[:\s]*([^\n\r]+)',
        r'material[:\s]*([^\n\r]+)',
        r'substance[:\s]*([^\n\r]+)',
        r'identification[:\s]*([^\n\r]+)',
        r'product\s+identifier[:\s]*([^\n\r]+)'
    ]
    
    for pattern in patterns:
        for line in lines:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                product_name = match.group(1).strip()
                cleaned = _clean_product_name(product_name)
                if 3 < len(cleaned) < 100 and not _is_generic_text(cleaned):
                    return cleaned
    
    # Look for chemical identifiers and names near them
    cas_pattern = r'CAS[#\s\-]*(\d{2,7}-\d{2}-\d)'
    for i, line in enumerate(lines):
        cas_match = re.search(cas_pattern, line, re.IGNORECASE)
        if cas_match:
            # Look for chemical name in nearby lines
            for j in range(max(0, i-2), min(len(lines), i+3)):
                potential_name = lines[j].strip()
                if (cas_match.group(1) not in potential_name and 
                    5 < len(potential_name) < 80 and
                    not _is_generic_text(potential_name)):
                    cleaned = _clean_product_name(potential_name)
                    if cleaned != "Unknown Product":
                        return cleaned
    
    # Look for meaningful lines that could be product names
    for line in lines:
        line = line.strip()
        if (10 < len(line) < 100 and 
            not _is_generic_text(line) and
            not re.search(r'page|section|\d+\.\d+|safety|data|sheet', line, re.IGNORECASE)):
            cleaned = _clean_product_name(line)
            if cleaned != "Unknown Product":
                return cleaned
    
    # Final fallback to filename
    if filename:
        name = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
        return ' '.join(word.capitalize() for word in name.split())
    
    return "Unknown Product"

def _clean_product_name(raw_name: str) -> str:
    """Clean and normalize product name"""
    if not raw_name:
        return "Unknown Product"
    
    clean_name = raw_name.strip()
    
    # Remove SDS-specific terms
    sds_terms = [
        "safety data sheet", "sds", "msds", "material safety data sheet",
        "product data sheet", "safety datasheet", "product information sheet"
    ]
    
    for term in sds_terms:
        clean_name = re.sub(re.escape(term), "", clean_name, flags=re.IGNORECASE)
    
    # Remove version numbers and dates
    clean_name = re.sub(r'version\s+\d+(\.\d+)*', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'rev\s+\d+', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', clean_name)
    clean_name = re.sub(r'\d{4}-\d{2}-\d{2}', '', clean_name)
    
    # Remove common prefixes/suffixes
    prefixes_suffixes = [
        "section 1", "identification", "product identifier",
        "trade name", "chemical name", "substance name"
    ]
    
    for term in prefixes_suffixes:
        clean_name = re.sub(re.escape(term), "", clean_name, flags=re.IGNORECASE)
    
    # Remove extra whitespace and punctuation
    clean_name = re.sub(r'[:\-_]+', ' ', clean_name)
    clean_name = ' '.join(clean_name.split())
    
    # If nothing meaningful left, return default
    if len(clean_name) < 2 or _is_generic_text(clean_name):
        return "Unknown Product"
    
    return clean_name.title()

def _is_generic_text(text: str) -> bool:
    """Check if text is too generic to be a product name"""
    generic_terms = [
        "product", "chemical", "substance", "material", "solution",
        "mixture", "compound", "agent", "formula", "preparation",
        "identification", "name", "title", "header", "section"
    ]
    
    text_lower = text.lower()
    return any(term in text_lower for term in generic_terms) and len(text.split()) < 3

def _extract_chemical_info(text: str) -> Dict:
    """Extract chemical information from SDS text"""
    info = {
        'cas_numbers': [],
        'hazard_statements': [],
        'ghs_classifications': [],
        'signal_words': [],
        'precautionary_statements': []
    }
    
    # CAS number extraction
    cas_pattern = r'CAS[#\s\-]*(\d{2,7}-\d{2}-\d)'
    labeled = re.findall(r'CAS(?:\s+Number)?[:#]?\s*(\d{2,7}-\d{2}-\d)', text, re.IGNORECASE)
    general = re.findall(r'\b(\d{2,7}-\d{2}-\d)\b', text)
    info['cas_numbers'] = sorted(set(labeled) | set(general))
    
    # Hazard statements (H-codes)
    h_pattern = r'H(\d{3})[:\s]*([^\n\r]+)'
    h_matches = re.findall(h_pattern, text, re.IGNORECASE)
    info['hazard_statements'] = [f"H{code}: {desc.strip()}" for code, desc in h_matches]
    
    # Signal words
    signal_pattern = r'\b(DANGER|WARNING)\b'
    info['signal_words'] = list(set(re.findall(signal_pattern, text, re.IGNORECASE)))
    
    # Precautionary statements (P-codes)
    p_pattern = r'P(\d{3})[:\s]*([^\n\r]+)'
    p_matches = re.findall(p_pattern, text, re.IGNORECASE)
    info['precautionary_statements'] = [f"P{code}: {desc.strip()}" for code, desc in p_matches]
    
    return info

def _chunk_text(text: str, size: int = 1000, overlap: int = 100) -> List[str]:
    """Chunk text into overlapping segments for embeddings"""
    if not text or len(text) < size:
        return [text] if text else []
    
    chunks = []
    i = 0
    
    while i < len(text):
        end = min(i + size, len(text))
        
        # Try to break at sentence boundaries
        if end < len(text):
            # Look for sentence endings within last 200 chars
            search_start = max(end - 200, i)
            for pattern in ['. ', '.\n', '?\n', '!\n', '.\r\n']:
                pos = text.rfind(pattern, search_start, end)
                if pos > i:
                    end = pos + len(pattern)
                    break
        
        chunk = text[i:end].strip()
        if chunk:
            chunks.append(chunk)
        
        i = end - overlap
        if i >= len(text):
            break
    
    return chunks[:50]  # Limit to 50 chunks

def ingest_single_pdf(file_stream, filename: str = "upload.pdf") -> Dict:
    """Ingest single PDF with enhanced error handling for Render deployment"""
    try:
        # Read file
        raw = file_stream.read()
        file_hash = _sha256_bytes(raw)
        
        # Check for existing file
        index = load_index()
        for rec in index.values():
            if rec.get("file_hash") == file_hash:
                print(f"File already exists: {filename}")
                return rec
        
        # Extract text
        text = _extract_text_from_pdf(raw)
        if not text:
            print(f"Warning: No text extracted from {filename}")
        
        # Extract additional content
        tables = _extract_tables_from_pdf(raw)
        images = _extract_images_from_pdf(raw)
        chemical_info = _extract_chemical_info(text)
        
        # Guess product name
        product_name = _guess_product_name(text, filename)
        print(f"Detected product: {product_name}")
        
        # RENDER MODIFICATION: Handle file saving with fallback
        file_path = "/tmp/file_not_saved"  # Default fallback
        file_size = len(raw)
        
        try:
            # Try to save file to temp directory
            out_name = f"{file_hash[:16]}-{filename}"
            temp_path = sds_dir / "files" / out_name
            
            if ensure_sds_directory():
                (sds_dir / "files").mkdir(exist_ok=True)
                with open(temp_path, "wb") as f:
                    f.write(raw)
                file_path = str(temp_path)
                print(f"✓ File saved to: {file_path}")
            else:
                print("⚠ Could not save file, using in-memory processing only")
        except Exception as e:
            print(f"⚠ Failed to save file: {e}")
        
        # Create chunks
        chunks = _chunk_text(text)
        print(f"Created {len(chunks)} text chunks")
        
        # Generate embeddings if available
        embeddings = []
        has_embeddings = False
        
        if EMBEDDINGS_AVAILABLE and chunks:
            try:
                if is_sbert_available():
                    from .embeddings import embed_texts
                    embeddings = embed_texts(chunks).tolist()
                    has_embeddings = True
                    print(f"✓ Generated {len(embeddings)} embeddings")
                else:
                    print("ℹ SBERT not available - SDS will work without semantic search")
            except Exception as e:
                print(f"⚠ Failed to generate embeddings: {e}")
                embeddings = []
                has_embeddings = False
        else:
            print("ℹ Embeddings not available - SDS will work without semantic search")
        
        # Create comprehensive record with all required fields for templates
        sid = file_hash[:12]
        record = {
            "id": sid,
            "file_path": file_path,
            "file_name": filename,
            "file_hash": file_hash,
            "file_size": file_size,
            "product_name": product_name,
            "created_ts": time.time(),
            "text_len": len(text),
            "text_content": text,  # Store full text for Render
            "chunks": chunks,
            "embeddings": embeddings,
            "has_embeddings": has_embeddings,
            "tables": tables,
            "images": images,
            "page_texts": _extract_page_texts(raw),
            "chemical_info": chemical_info,
            "processing_metadata": {
                "chunks_count": len(chunks),
                "embeddings_generated": has_embeddings,
                "embeddings_count": len(embeddings),
                "tables_extracted": len(tables),
                "images_extracted": len(images),
                "cas_numbers_found": len(chemical_info.get('cas_numbers', [])),
                "hazard_statements_found": len(chemical_info.get('hazard_statements', [])),
                "processing_time": time.time(),
                "text_extraction_successful": bool(text),
                "filename_original": filename,
                "render_compatible": True
            },
            # Additional required fields for template compatibility
            "department": "",
            "manufacturer": "",
            "country": "",
            "state": "",
            "created_by": "System",
            "status": "active",
            "created_date": time.time()  # For template compatibility
        }
        
        # Update index
        index[sid] = record
        save_success = save_index(index)
        
        if save_success:
            print(f"✓ SDS ingested successfully: {sid}")
        else:
            print(f"⚠ SDS processed but saved to memory only: {sid}")
        
        return record
        
    except Exception as e:
        print(f"ERROR: Failed to ingest PDF {filename}: {e}")
        raise

# Render-specific helper functions
def create_sample_sds_data():
    """Create sample SDS data for Render deployment"""
    current_time = time.time()
    
    sample_data = {
        "sample_001": {
            "id": "sample_001",
            "file_path": "/tmp/sample_acetone_sds.pdf",
            "file_name": "acetone_sds.pdf",
            "file_hash": "sample_hash_acetone_123",
            "file_size": 1024000,
            "product_name": "Acetone (Technical Grade)",
            "created_ts": current_time - 86400,  # 1 day ago
            "created_date": current_time - 86400,
            "text_len": 1500,
            "text_content": "Sample SDS content for Acetone - highly flammable liquid...",
            "chunks": ["Acetone safety information...", "Storage and handling..."],
            "embeddings": [],
            "has_embeddings": False,
            "tables": [],
            "images": [],
            "page_texts": ["Page 1 content", "Page 2 content"],
            "chemical_info": {
                "cas_numbers": ["67-64-1"],
                "hazard_statements": ["H225 - Highly flammable liquid and vapor", "H319 - Causes serious eye irritation"],
                "signal_words": ["DANGER"],
                "ghs_classifications": [],
                "precautionary_statements": []
            },
            "processing_metadata": {
                "chunks_count": 2,
                "embeddings_generated": False,
                "embeddings_count": 0,
                "tables_extracted": 0,
                "images_extracted": 0,
                "cas_numbers_found": 1,
                "hazard_statements_found": 2,
                "processing_time": current_time,
                "text_extraction_successful": True,
                "filename_original": "acetone_sds.pdf",
                "render_compatible": True
            },
            "department": "Laboratory",
            "manufacturer": "Chemical Corp",
            "country": "United States",
            "state": "California",
            "created_by": "System",
            "status": "active"
        },
        "sample_002": {
            "id": "sample_002",
            "file_path": "/tmp/sample_naoh_sds.pdf",
            "file_name": "sodium_hydroxide_sds.pdf",
            "file_hash": "sample_hash_naoh_456",
            "file_size": 856000,
            "product_name": "Sodium Hydroxide Solution (50%)",
            "created_ts": current_time - 172800,  # 2 days ago
            "created_date": current_time - 172800,
            "text_len": 1200,
            "text_content": "Sample SDS content for Sodium Hydroxide - corrosive substance...",
            "chunks": ["Sodium hydroxide properties...", "Emergency procedures..."],
            "embeddings": [],
            "has_embeddings": False,
            "tables": [],
            "images": [],
            "page_texts": ["Page 1 content", "Page 2 content"],
            "chemical_info": {
                "cas_numbers": ["1310-73-2"],
                "hazard_statements": ["H314 - Causes severe skin burns and eye damage"],
                "signal_words": ["DANGER"],
                "ghs_classifications": [],
                "precautionary_statements": []
            },
            "processing_metadata": {
                "chunks_count": 2,
                "embeddings_generated": False,
                "embeddings_count": 0,
                "tables_extracted": 0,
                "images_extracted": 0,
                "cas_numbers_found": 1,
                "hazard_statements_found": 1,
                "processing_time": current_time,
                "text_extraction_successful": True,
                "filename_original": "sodium_hydroxide_sds.pdf",
                "render_compatible": True
            },
            "department": "Manufacturing",
            "manufacturer": "Industrial Chemicals Inc",
            "country": "Canada",
            "state": "Ontario",
            "created_by": "System",
            "status": "active"
        },
        "sample_003": {
            "id": "sample_003",
            "file_path": "/tmp/sample_ipa_sds.pdf",
            "file_name": "isopropyl_alcohol_sds.pdf",
            "file_hash": "sample_hash_ipa_789",
            "file_size": 742000,
            "product_name": "Isopropyl Alcohol (99%)",
            "created_ts": current_time - 259200,  # 3 days ago
            "created_date": current_time - 259200,
            "text_len": 1350,
            "text_content": "Sample SDS content for Isopropyl Alcohol - flammable liquid...",
            "chunks": ["Isopropyl alcohol information...", "Safety precautions..."],
            "embeddings": [],
            "has_embeddings": True,  # One with embeddings
            "tables": [],
            "images": [],
            "page_texts": ["Page 1 content", "Page 2 content"],
            "chemical_info": {
                "cas_numbers": ["67-63-0"],
                "hazard_statements": ["H225 - Highly flammable liquid and vapor", "H319 - Causes serious eye irritation"],
                "signal_words": ["DANGER"],
                "ghs_classifications": [],
                "precautionary_statements": []
            },
            "processing_metadata": {
                "chunks_count": 2,
                "embeddings_generated": True,
                "embeddings_count": 2,
                "tables_extracted": 0,
                "images_extracted": 0,
                "cas_numbers_found": 1,
                "hazard_statements_found": 2,
                "processing_time": current_time,
                "text_extraction_successful": True,
                "filename_original": "isopropyl_alcohol_sds.pdf",
                "render_compatible": True
            },
            "department": "Quality Control",
            "manufacturer": "Solvent Solutions Ltd",
            "country": "United Kingdom",
            "state": "",
            "created_by": "System",
            "status": "active"
        }
    }
    
    success = save_index(sample_data)
    return sample_data, success

def initialize_sds_system():
    """Initialize SDS system for Render"""
    print("🚀 Initializing SDS system for Render deployment...")
    
    # Ensure directory structure
    success = ensure_sds_directory()
    if not success:
        print("⚠ Could not create full directory structure, using memory-only mode")
    
    # Create sample data
    try:
        current_index = load_index()
        if not current_index or len(current_index) == 0:
            # Create sample data for demonstration
            print("📝 Creating sample SDS data...")
            sample_data, save_success = create_sample_sds_data()
            if save_success:
                print("✅ Sample SDS data created and saved")
            else:
                print("⚠ Sample data created in memory only")
            return sample_data
        else:
            print(f"✅ Existing index loaded with {len(current_index)} records")
            return current_index
        
    except Exception as e:
        print(f"❌ Failed to initialize SDS system: {e}")
        # Return minimal working data even if initialization fails
        return {
            "emergency_sample": {
                "id": "emergency_sample",
                "product_name": "Emergency Demo SDS",
                "file_name": "demo.pdf",
                "file_size": 500000,
                "created_ts": time.time(),
                "created_date": time.time(),
                "has_embeddings": False,
                "department": "Demo",
                "manufacturer": "Demo Corp",
                "country": "Demo Country",
                "state": "",
                "chemical_info": {"cas_numbers": [], "hazard_statements": []},
                "processing_metadata": {"chunks_count": 0},
                "status": "active"
            }
        }
