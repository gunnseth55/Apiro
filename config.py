"""
config.py — Apiro global constants and configuration.
All tuneable parameters live here. Import this everywhere.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR   = Path(__file__).parent
DATA_DIR   = ROOT_DIR / "data"
CORPUS_DIR = DATA_DIR / "corpus"
CHROMA_DIR = DATA_DIR / "chroma_db"
LOG_DIR    = DATA_DIR / "logs"

for _d in [DATA_DIR, CORPUS_DIR, CHROMA_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Ollama / LLM
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL  = "http://localhost:11434"
PRIMARY_MODEL    = "qwen3:8b"        # Configured to use the locally available model
TOP_LOGPROBS     = 20                   # top-k logprobs for entropy computation (Ollama max is 20)
MAX_FIRST_TOKEN  = 1                    # only first token for entropy
MAX_ANSWER_TOKENS = 80                  # short answer generation
ENTROPY_TEMPERATURES = [0.3, 0.7, 1.2] # temperatures for weighted entropy
# Temperature weights — highest weight on T=0.3 (purest signal, least noise)
ENTROPY_TEMP_WEIGHTS = {0.3: 0.6, 0.7: 0.3, 1.2: 0.1}

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
EMBED_MODEL    = "all-mpnet-base-v2"
EMBED_DIM      = 768
CHROMA_COLLECTION = "apiro_corpus"
RAG_TOP_K      = 6    # chunks retrieved per query

# ---------------------------------------------------------------------------
# Corpus chunking
# ---------------------------------------------------------------------------
CHUNK_SIZE_TOKENS   = 300
CHUNK_OVERLAP_TOKENS = 50

# ---------------------------------------------------------------------------
# Graph traversal
# ---------------------------------------------------------------------------
MAX_TRAVERSAL_DEPTH = 8
FRONTIER_SORT       = "entropy_desc"   # always expand highest-entropy node first
N_CHILD_HYPOTHESES  = 3                # child nodes generated per expansion

# ---------------------------------------------------------------------------
# Saturation stopping condition
# ---------------------------------------------------------------------------
SATURATION_WINDOW       = 5      # look back at last N expanded nodes
SATURATION_MAX_VARIANCE = 0.04   # entropy variance threshold
THETA_BY_DOMAIN = {
    "pathophysiology": 0.30,
    "pharmacology":    0.25,
    "genetics":        0.20,
    "imaging":         0.25,
    "lab":             0.20,
    "treatment":       0.25,
    "comorbidity":     0.35,
}
DEFAULT_THETA = 0.25

# ---------------------------------------------------------------------------
# Rabbit hole detection
# ---------------------------------------------------------------------------
RABBIT_HOLE_MIN_DEPTH      = 3
RABBIT_HOLE_REVERSAL_WINDOW = 4

# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------
CONTRADICTION_MODEL    = "cross-encoder/nli-MiniLM2-L6-H768"
CONTRADICTION_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Domain classifier
# ---------------------------------------------------------------------------
DOMAINS = [
    "pathophysiology",
    "pharmacology",
    "genetics",
    "imaging",
    "lab findings",
    "treatment",
    "comorbidity",
]

# ---------------------------------------------------------------------------
# Corpus sources
# ---------------------------------------------------------------------------
PUBMED_BATCH_SIZE    = 500
PUBMED_MAX_ABSTRACTS = 500_000
OMIM_API_KEY         = ""   # Set via environment variable OMIM_API_KEY
PUBMED_SEARCH_TERMS  = [
    "diagnosis AND treatment",
    "differential diagnosis",
    "clinical presentation",
    "pathophysiology",
    "drug mechanism of action",
    "genetic disorder",
    "rare disease",
    "comorbidity",
]
