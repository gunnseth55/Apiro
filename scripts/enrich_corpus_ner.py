# scripts/enrich_corpus_ner.py
"""
One-time offline enrichment: tag all ChromaDB chunks with disease_name metadata
using BC5CDR NER (trained specifically on biomedical disease + chemical mentions).
Run once, results persist in ChromaDB. Zero LLM calls, ever.
"""
import json
import logging
from collections import Counter
from pathlib import Path
import spacy

logger = logging.getLogger(__name__)

# BC5CDR is the right model: trained on disease NER in biomedical text.
# en_core_sci_sm tags broader ENTITY/CHEMICAL/DISEASE — less precise.
NER_MODEL = "en_ner_bc5cdr_md"


def enrich_collection(collection, batch_size: int = 256) -> dict[str, str]:
    """
    Iterate all chunks in collection, run NER, update disease_name metadata.
    Returns {chunk_id: disease_name} for all successfully tagged chunks.
    """
    nlp = spacy.load(NER_MODEL)
    results: dict[str, str] = {}

    # Fetch all chunks (documents + ids + existing metadata)
    all_data = collection.get(include=["documents", "metadatas"])
    ids       = all_data["ids"]
    texts     = all_data["documents"]
    metadatas = all_data["metadatas"]

    logger.info(f"Enriching {len(ids)} chunks with NER disease tags...")

    # Process in batches for speed (spaCy pipe is faster than per-doc)
    for batch_start in range(0, len(ids), batch_size):
        batch_ids   = ids[batch_start : batch_start + batch_size]
        batch_texts = texts[batch_start : batch_start + batch_size]
        batch_metas = metadatas[batch_start : batch_start + batch_size]

        docs = list(nlp.pipe(batch_texts, batch_size=batch_size))

        update_ids, update_metas = [], []
        for chunk_id, doc, meta in zip(batch_ids, docs, batch_metas):
            # Only tag chunks that don't already have a disease_name
            if meta.get("disease_name"):
                continue

            diseases = [ent.text.strip() for ent in doc.ents if ent.label_ == "DISEASE"]
            if not diseases:
                continue

            # Most-frequent entity in this chunk = its primary disease topic
            primary = Counter(diseases).most_common(1)[0][0]

            # Quality gate: reject single-word or suspiciously short hits
            if len(primary.split()) < 2 and len(primary) < 8:
                continue

            results[chunk_id] = primary
            new_meta = {**meta, "disease_name": primary}
            update_ids.append(chunk_id)
            update_metas.append(new_meta)

        if update_ids:
            # ChromaDB update requires re-providing embeddings or using update()
            collection.update(ids=update_ids, metadatas=update_metas)

        logger.info(
            f"  Processed {min(batch_start + batch_size, len(ids))}/{len(ids)} chunks, "
            f"tagged {len(results)} so far..."
        )

    logger.info(f"Enrichment complete. Tagged {len(results)}/{len(ids)} chunks.")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import chromadb

    # Adjust path to match your Apiro ChromaDB setup
    client = chromadb.PersistentClient(path="data/chroma_db")
    collection = client.get_collection("apiro_corpus")
    enrich_collection(collection)
