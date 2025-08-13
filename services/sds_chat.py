import numpy as np
from typing import Dict, List
from .embeddings import embed_query, cosine_sim
from typing import Optional

def answer_question_for_sds(rec: Dict, question: str) -> str:
    chunks: List[str] = rec.get("chunks", [])
    embs = rec.get("embeddings", [])
    if not chunks:
        return "I couldn't find content for this SDS."

    if embs and question.strip():
        try:
            qv = embed_query(question)
            # compute similarity to each chunk
            best_idx = -1
            best_score = -1.0
            for i, ev in enumerate(embs):
                ev = np.asarray(ev, dtype="float32")
                score = cosine_sim(qv, ev)
                if score > best_score:
                    best_score, best_idx = score, i
            if best_idx >= 0:
                ans = chunks[best_idx]
                return answer_with_citation(rec, ans)
        except Exception:
            pass

    # fallback
    # return first chunk to avoid empty responses
    ans = chunks[0]
    return answer_with_citation(rec, ans)


def _find_page_for_answer(rec: Dict, answer_text: str) -> int:
    """Best-effort page detection by substring search."""
    pages = rec.get("page_texts") or []
    if not pages or not answer_text:
        return 0
    probe = (answer_text[:200] or "").strip()
    for i, pt in enumerate(pages):
        if probe and probe in pt:
            return i+1
    # fallback: find page with maximum overlap
    best_i, best_overlap = 0, 0
    for i, pt in enumerate(pages):
        overlap = len(set(probe.split()) & set(pt.split()))
        if overlap > best_overlap:
            best_overlap, best_i = overlap, i
    return best_i+1

def answer_with_citation(rec: Dict, text: str) -> str:
    page = _find_page_for_answer(rec, text)
    fn = rec.get("file_name","SDS.pdf")
    suffix = f"\n\n(Source: {fn}, page {page})" if page else ""
    return ((text[:1500] + " …") if len(text) > 1500 else text) + suffix
