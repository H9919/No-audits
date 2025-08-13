# services/sds_ingest.py - FIXED VERSION with proper JSON structure completion
import io
import json
import time
import hashlib
import re
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

DATA_DIR = Path("data")
sds_dir = DATA_DIR / "sds"
INDEX_JSON = sds_dir / "index.json"

def load_index():
    """Load SDS index with error handling"""
    sds_dir.mkdir(parents=True, exist_ok=True)
    if INDEX_JSON.exists():
        try:
            return json.loads(INDEX_JSON.read_text())
        except json.JSONDecodeError:
            print("Warning: Corrupted SDS index, creating new one")
            return {}
    return {}

def save_index(obj):
    """Save SDS index with backup"""
    sds_dir.mkdir(parents=True, exist_ok=True)
    
    # Create backup if index exists
    if INDEX_JSON.exists():
        backup_path = INDEX_JSON.with_suffix('.json.backup')
        try:
            INDEX_JSON.replace(backup_path)
        except:
            pass  # Ignore backup errors
    
    INDEX_JSON.write_text(json.dumps(obj, indent=2))

def _sha256_bytes(b: bytes) -> str:
    """Calculate SHA256 hash of bytes"""
    return hashlib.sha256(b).hexdigest()


def _extract_page_texts(pdf_bytes: bytes):
    """Return list of page texts"""
    try:
        import fitz
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
    """Ingest single PDF with enhanced error handling and optional embeddings"""
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
        
        # Save file
        out_name = f"{file_hash[:16]}-{filename}"
        out_path = sds_dir / out_name
        
        try:
            with open(out_path, "wb") as f:
                f.write(raw)
        except Exception as e:
            print(f"ERROR: Failed to save file {out_path}: {e}")
            raise
        
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
        
        # Create comprehensive record - FIXED: properly structured with complete data
        sid = file_hash[:12]
        record = {
            "id": sid,
            "file_path": str(out_path.resolve()),
            "file_name": filename,
            "file_hash": file_hash,
            "product_name": product_name,
            "created_ts": time.time(),
            "text_len": len(text),
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
                "filename_original": filename
            }
        }
        
        # Update index
        index[sid] = record
        save_index(index)
        
        print(f"✓ SDS ingested successfully: {sid}")
        return record
        
    except Exception as e:
        print(f"ERROR: Failed to ingest PDF {filename}: {e}")
        raise