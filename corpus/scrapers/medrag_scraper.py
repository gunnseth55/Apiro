"""
corpus/scrapers/medrag_scraper.py
===================================
Streams the MedRAG/pubmed dataset from HuggingFace — pre-chunked PubMed
abstracts ready for direct embedding. No NCBI email or API key required.

Dataset: https://huggingface.co/datasets/MedRAG/pubmed
Fields per record:
    id       — unique snippet ID
    PMID     — PubMed ID
    title    — article title
    content  — abstract text (~200 token snippets)
    contents — title + content concatenated (used here as text)

Because MedRAG records are already chunked, they go DIRECTLY to the
Embedder without passing through corpus/chunker.py. The build_corpus.py
orchestrator handles this by setting chunk_size=None for this source.

Usage:
    from corpus.scrapers.medrag_scraper import MedRAGScraper
    scraper = MedRAGScraper(max_records=100_000)
    records = scraper.fetch()

Each record dict is already a final chunk:
    {
        "chunk_id":       str,   # MedRAG's own 'id' field
        "pmid":           str,
        "title":          str,
        "text":           str,   # = contents (title + abstract snippet)
        "source_db":      "medrag_pubmed",
        "medical_domain": str,   # coarse classification from title keywords
        "chunk_index":    0,
        "n_chunks":       1,
    }
"""

import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)

# Coarse domain keywords (same as pubmed_scraper, kept local to avoid coupling)
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "genetics":        ["gene", "mutation", "variant", "allele", "chromosome"],
    "pharmacology":    ["drug", "medication", "dose", "pharmacokinetic", "inhibitor",
                        "mechanism of action", "adverse"],
    "imaging":         ["mri", "ct scan", "x-ray", "ultrasound", "radiograph", "imaging"],
    "lab":             ["laboratory", "serum", "blood test", "troponin", "creatinine",
                        "hemoglobin", "d-dimer", "biopsy"],
    "treatment":       ["treatment", "therapy", "surgery", "intervention",
                        "guideline", "protocol", "first-line"],
    "comorbidity":     ["comorbidity", "complication", "secondary", "multimorbidity"],
    "pathophysiology": ["pathophysiology", "mechanism", "pathogenesis", "etiology",
                        "inflammatory", "fibrosis"],
}


def _guess_domain(text: str) -> str:
    text_lower = text.lower()
    scores = {d: sum(1 for kw in kws if kw in text_lower)
              for d, kws in _DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "pathophysiology"


class MedRAGScraper:
    """
    Streams MedRAG/pubmed from HuggingFace.

    Args:
        max_records:  Maximum records to return (0 = stream entire dataset).
        split:        Dataset split to use (only 'train' exists).
    """

    def __init__(self, max_records: int = 100_000, split: str = "train"):
        self.max_records = max_records
        self.split       = split

    def fetch(self) -> list[dict]:
        """
        Stream MedRAG/pubmed and return up to max_records chunk dicts.

        Returns:
            List of pre-chunked record dicts ready for direct Embedder.ingest().
        """
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError(
                "HuggingFace `datasets` library not installed. "
                "Run: pip install datasets"
            )

        logger.info(
            f"Streaming MedRAG/pubmed from HuggingFace "
            f"(max_records={self.max_records or 'unlimited'})..."
        )

        dataset = load_dataset(
            "MedRAG/pubmed",
            split=self.split,
            streaming=True,
            trust_remote_code=False,
        )

        records: list[dict] = []
        for i, example in enumerate(dataset):
            if self.max_records and i >= self.max_records:
                break

            # 'contents' = title + content (pre-concatenated by MedRAG)
            text  = example.get("contents") or example.get("content", "")
            title = example.get("title", "")
            pmid  = str(example.get("PMID", ""))
            uid   = str(example.get("id", f"medrag_{i:08d}"))

            if not text.strip():
                continue

            records.append({
                "chunk_id":       uid,
                "pmid":           pmid,
                "title":          title,
                "text":           text,
                "source_db":      "medrag_pubmed",
                "medical_domain": _guess_domain(text),
                "chunk_index":    0,
                "n_chunks":       1,
            })

            if i % 10_000 == 0 and i > 0:
                logger.info(f"  Streamed {i:,} records...")

        logger.info(f"MedRAG/pubmed fetch complete. {len(records):,} records.")
        return records
