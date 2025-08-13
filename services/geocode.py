
def reverse_geocode(lat: str, lng: str) -> str:
    """Offline-safe stub: formats coordinates into a readable string."""
    lat = (lat or "").strip()
    lng = (lng or "").strip()
    if not lat or not lng:
        return ""
    try:
        lat_f = float(lat); lng_f = float(lng)
        return f"{lat_f:.5f}, {lng_f:.5f} (approx)"
    except Exception:
        return f"{lat}, {lng}"
