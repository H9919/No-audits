# services/embeddings.py — SBERT guardrails: lazy-load, async warmup, cache, fast fallback
import os, time, threading
from pathlib import Path
import numpy as np

# Feature flag: enable semantic embeddings
ENABLE_SBERT = os.getenv('ENABLE_SBERT', 'false').lower() == 'true'

# Import only if requested
_SBERT_IMPORT_OK = False
try:
    if ENABLE_SBERT:
        from sentence_transformers import SentenceTransformer
        _SBERT_IMPORT_OK = True
except Exception:
    _SBERT_IMPORT_OK = False

SBERT_AVAILABLE = ENABLE_SBERT and _SBERT_IMPORT_OK

# Internal model holder
_SBERT_MODEL = None
_SBERT_LOADING = False

def _load_model():
    global _SBERT_MODEL, _SBERT_LOADING
    try:
        model_name = os.getenv('SBERT_MODEL', 'paraphrase-MiniLM-L6-v2')
        cache_dir = Path(os.getenv('SBERT_CACHE', 'data/models')).absolute()
        cache_dir.mkdir(parents=True, exist_ok=True)
        _SBERT_MODEL = SentenceTransformer(model_name, cache_folder=str(cache_dir), device='cpu')
        # quick warmup (tiny) to compile kernels
        _ = _SBERT_MODEL.encode(["ok"], normalize_embeddings=True, show_progress_bar=False)
        print(f"✓ SBERT model ready: {model_name} (cache={cache_dir})")
    except Exception as e:
        print(f"⚠ SBERT load failed: {e}")
        _SBERT_MODEL = None
    finally:
        _SBERT_LOADING = False

def ensure_model_async():
    """Start background load if enabled and not loaded yet; never block the request."""
    if not SBERT_AVAILABLE:
        return
    global _SBERT_LOADING
    if _SBERT_MODEL is None and not _SBERT_LOADING:
        _SBERT_LOADING = True
        threading.Thread(target=_load_model, daemon=True).start()

def is_sbert_available():
    return SBERT_AVAILABLE

def model_ready():
    return _SBERT_MODEL is not None

def get_embedding_dim():
    # MiniLM family uses 384 dims
    return 384

def embed_texts(texts, timeout_ms=800):
    """Return embeddings or zeros if model not ready quickly."""
    if not texts:
        return np.zeros((0, get_embedding_dim()), dtype='float32')
    if not SBERT_AVAILABLE:
        return np.zeros((len(texts), get_embedding_dim()), dtype='float32')
    if _SBERT_MODEL is None:
        ensure_model_async()
        return np.zeros((len(texts), get_embedding_dim()), dtype='float32')
    try:
        t0 = time.monotonic()
        vecs = _SBERT_MODEL.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        dt = (time.monotonic() - t0) * 1000.0
        if dt > timeout_ms:
            print(f"⚠ SBERT encode slow: {dt:.0f}ms for {len(texts)} texts")
        return np.asarray(vecs, dtype='float32')
    except Exception as e:
        print(f"⚠ SBERT encode failed: {e}")
        return np.zeros((len(texts), get_embedding_dim()), dtype='float32')

def embed_query(q: str):
    return embed_texts([q])[0] if q else np.zeros(get_embedding_dim(), dtype='float32')

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    try:
        return float(np.dot(a, b))
    except Exception:
        return 0.0
