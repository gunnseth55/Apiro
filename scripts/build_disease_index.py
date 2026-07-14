# scripts/build_disease_index.py
"""
Build a dedicated symptom-to-disease index from HPO + OMIM ontology files.
This is a SEPARATE ChromaDB collection from the MedRAG textbook corpus.
At inference time, CandidateDiscoverer queries this instead of / in addition to MedRAG.

Data sources (all free, no license required):
  - hp.obo           : https://hpo.jax.org/data/ontology      (HPO term definitions)
  - phenotype.hpoa   : https://hpo.jax.org/data/annotations   (disease → HPO terms)
  - mimTitles.txt    : https://omim.org/downloads             (OMIM disease names)
"""

import logging
import re
from collections import defaultdict
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── HPO OBO parser ────────────────────────────────────────────────────────────

def parse_hpo_obo(obo_path: str) -> dict[str, str]:
    """Parse hp.obo → {HP:XXXXXXX: 'symptom description'}"""
    hpo_terms: dict[str, str] = {}
    current_id = None
    current_name = None

    with open(obo_path) as f:
        for line in f:
            line = line.strip()
            if line == "[Term]":
                current_id = current_name = None
            elif line.startswith("id: HP:"):
                current_id = line.split("id: ")[1]
            elif line.startswith("name: "):
                current_name = line.split("name: ", 1)[1]
                if current_id and current_name:
                    hpo_terms[current_id] = current_name

    logger.info(f"Parsed {len(hpo_terms)} HPO terms from {obo_path}")
    return hpo_terms


def parse_hpoa(hpoa_path: str) -> dict[str, list[str]]:
    """
    Parse phenotype.hpoa → {disease_name: [hpo_term_id, ...]}

    HPOA format (tab-separated):
      database_id  disease_name  qualifier  hpo_id  reference  evidence  ...
    """
    disease_phenotypes: dict[str, list[str]] = defaultdict(list)

    with open(hpoa_path) as f:
        for line in f:
            if line.startswith("#") or line.startswith("database_id"):
                continue
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue

            disease_name = parts[1].strip()
            qualifier    = parts[2].strip()
            hpo_id       = parts[3].strip()

            # Skip negated phenotypes ("NOT fever")
            if qualifier == "NOT":
                continue
            if not hpo_id.startswith("HP:"):
                continue

            disease_phenotypes[disease_name].append(hpo_id)

    logger.info(f"Parsed {len(disease_phenotypes)} diseases from {hpoa_path}")
    return disease_phenotypes


def build_disease_profiles(
    hpo_terms: dict[str, str],
    disease_phenotypes: dict[str, list[str]],
    min_phenotypes: int = 3,
) -> list[dict]:
    """
    For each disease in HPOA, build a structured profile document:
      {
        "disease": "Tuberculosis",
        "phenotype_text": "fever night sweats weight loss cough hemoptysis lymphadenopathy ...",
        "n_phenotypes": 12
      }

    This is the document we embed and store in ChromaDB.
    Diseases with fewer than min_phenotypes HPO terms are filtered out
    (they'd produce noise candidates).
    """
    profiles = []
    for disease_name, hpo_ids in disease_phenotypes.items():
        if len(hpo_ids) < min_phenotypes:
            continue

        # Resolve HPO IDs to human-readable symptom names
        symptom_names = [
            hpo_terms[hpo_id]
            for hpo_id in hpo_ids
            if hpo_id in hpo_terms
        ]
        if not symptom_names:
            continue

        phenotype_text = "; ".join(symptom_names)

        profiles.append({
            "disease":        disease_name,
            "phenotype_text": phenotype_text,
            "n_phenotypes":   len(symptom_names),
            "hpo_ids":        ",".join(hpo_ids[:20]),  # store top 20 for metadata
        })

    logger.info(f"Built {len(profiles)} disease profiles (min_phenotypes={min_phenotypes})")
    return profiles


def build_index(
    obo_path:   str,
    hpoa_path:  str,
    chroma_path: str,
    collection_name: str = "disease_profiles",
    model_name: str = "sentence-transformers/all-mpnet-base-v2", # Using the same model as our other embedder
    batch_size: int = 256,
):
    """
    Full pipeline: parse HPO files → build disease profiles → embed → store in ChromaDB.

    This is a one-time offline operation. Results persist.
    Typical runtime: ~5 minutes for ~8,000 OMIM diseases on CPU.
    """
    hpo_terms          = parse_hpo_obo(obo_path)
    disease_phenotypes = parse_hpoa(hpoa_path)
    profiles           = build_disease_profiles(hpo_terms, disease_phenotypes)

    # Embed all profile texts
    logger.info(f"Embedding {len(profiles)} profiles with {model_name} on CPU...")
    model = SentenceTransformer(model_name, device="cpu")

    texts     = [p["phenotype_text"] for p in profiles]
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    # Store in ChromaDB
    client     = chromadb.PersistentClient(path=chroma_path)
    # Clear existing collection if rebuilding
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # Batch upsert
    for batch_start in range(0, len(profiles), batch_size):
        batch_profiles = profiles[batch_start : batch_start + batch_size]
        batch_embs     = embeddings[batch_start : batch_start + batch_size]

        collection.add(
            ids=[f"disease_{batch_start + i}" for i in range(len(batch_profiles))],
            embeddings=batch_embs.tolist(),
            documents=[p["phenotype_text"] for p in batch_profiles],
            metadatas=[
                {
                    "disease_name":  p["disease"],
                    "n_phenotypes":  p["n_phenotypes"],
                    "hpo_ids":       p["hpo_ids"],
                }
                for p in batch_profiles
            ],
        )
        logger.info(f"  Indexed {min(batch_start + batch_size, len(profiles))}/{len(profiles)}...")

    logger.info(
        f"Disease index built: {collection.count()} profiles in "
        f"collection '{collection_name}' at '{chroma_path}'"
    )
    return collection


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    build_index(
        obo_path    = "data/ontology/hp.obo",
        hpoa_path   = "data/ontology/phenotype.hpoa",
        chroma_path = "data/chroma_db",
    )
