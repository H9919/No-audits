# EHS

## New Additions (Prompts 2–12)
- Centralized upload validation (`utils/uploads.py`).
- Incident forms now support anonymity, site/region, and GPS fields.
- Hybrid likelihood estimation (`services/risk_matrix.py: estimate_likelihood_from_text`).
- CAPA semantic suggester (fallback) in `services/capa_manager.py`.
- 5 Whys support scaffold in chatbot (`FiveWhysManager`).
- SDS ingest stores `page_texts`; SDS chat cites page numbers.
- Anonymous redaction and GPS/meta in PDF export.
- GHS/NFPA simple label route at `/sds/<id>/label`.
- Tests added for uploads, SDS citation, risk hybrid, and PDF smoke.
