
from utils.uploads import is_allowed

def test_is_allowed_pdf_mime():
    assert is_allowed("doc.pdf", "application/pdf")

def test_is_allowed_reject_double_ext():
    assert not is_allowed("doc.pdf.exe", "application/pdf")

def test_is_allowed_wrong_mime():
    assert not is_allowed("doc.pdf", "image/png")
