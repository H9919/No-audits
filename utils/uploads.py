
from pathlib import Path
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".txt"}
MAX_BYTES = 20 * 1024 * 1024  # 20 MB

def _has_double_extension(name: str) -> bool:
    # e.g., "file.pdf.exe"
    parts = name.split(".")
    return len(parts) > 2 and parts[-1] not in {"gz","zip","7z"}  # allow common archives elsewhere

def is_allowed(filename: str, mimetype: str) -> bool:
    if not filename:
        return False
    name = secure_filename(filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False
    if _has_double_extension(name):
        return False
    # Basic MIME sanity checks
    if ext == ".pdf" and "pdf" not in (mimetype or "").lower():
        return False
    return True

def save_upload(file_storage, dest_dir: Path) -> Path:
    """Save a Werkzeug FileStorage to a directory outside web root safely."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = secure_filename(file_storage.filename or "upload.bin")
    out = dest_dir / name
    # size check (if possible)
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_BYTES:
        raise ValueError("File too large")
    file_storage.save(out)
    return out

def safe_send_path(base_dir: Path, candidate: Path) -> Path:
    """Ensure candidate is within base_dir before serving."""
    p = candidate.resolve()
    b = base_dir.resolve()
    if not str(p).startswith(str(b)):
        raise ValueError("Unsafe path")
    return p
