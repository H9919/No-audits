from pathlib import Path
import qrcode

def sds_detail_url(sid: str) -> str:
    # local link; if deployed behind a domain, replace with absolute URL
    return f"/sds/{sid}"

def ensure_qr(sid: str, url: str) -> str:
    out_dir = Path("static/qr")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sid}.png"
    if not out_path.exists():
        img = qrcode.make(url)
        img.save(out_path)
    return str(out_path)

