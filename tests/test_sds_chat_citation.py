
from services.sds_chat import answer_with_citation

def test_answer_with_citation():
    rec = {
        "file_name": "sample.pdf",
        "page_texts": ["Alpha bravo", "Charlie delta echo"],
    }
    text = "Charlie delta echo and more text"
    out = answer_with_citation(rec, text)
    assert "(Source: sample.pdf, page 2)" in out
