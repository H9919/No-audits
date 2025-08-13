
from services.risk_matrix import estimate_likelihood_from_text

def test_likelihood_keywords_only():
    out = estimate_likelihood_from_text("This happens frequently and is recurring")
    assert out["score"] >= 7
    assert out["confidence"] >= 0.4
