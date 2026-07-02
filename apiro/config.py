"""
config.py — Apiro global constants and configuration.
All tuneable parameters live here. Import this everywhere.

Every value can be overridden via environment variables (12-factor app).
Copy .env.example → .env and edit to customise for your environment.
Docker Compose injects these automatically from .env / environment: blocks.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR   = Path(__file__).parent.parent
DATA_DIR   = Path(os.environ.get("DATA_DIR",   str(ROOT_DIR / "data")))
CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", str(DATA_DIR / "corpus")))
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", str(DATA_DIR / "chroma_db")))
LOG_DIR    = Path(os.environ.get("LOG_DIR",    str(DATA_DIR / "logs")))

for _d in [DATA_DIR, CORPUS_DIR, CHROMA_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Ollama / LLM
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL",  "http://localhost:11434")
PRIMARY_MODEL     = os.environ.get("PRIMARY_MODEL",    "mistral:latest")
TOP_LOGPROBS      = int(os.environ.get("TOP_LOGPROBS",      "20"))   # top-k logprobs for entropy (Ollama max = 20)
MAX_FIRST_TOKEN   = int(os.environ.get("MAX_FIRST_TOKEN",   "1"))    # only first token for entropy
MAX_ANSWER_TOKENS = int(os.environ.get("MAX_ANSWER_TOKENS", "80"))   # short answer generation

# Temperatures for weighted entropy — noise-reduction averaging
_temps_raw = os.environ.get("ENTROPY_TEMPERATURES", "0.3,0.7,1.2")
ENTROPY_TEMPERATURES: list[float] = [float(t) for t in _temps_raw.split(",")]

# Temperature weights — highest weight on T=0.3 (purest signal, least noise)
ENTROPY_TEMP_WEIGHTS: dict[float, float] = {0.3: 0.6, 0.7: 0.3, 1.2: 0.1}

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
EMBED_MODEL       = os.environ.get("EMBED_MODEL",       "all-mpnet-base-v2")
EMBED_DIM         = int(os.environ.get("EMBED_DIM",     "768"))
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "apiro_corpus")
RAG_TOP_K         = int(os.environ.get("RAG_TOP_K",     "6"))    # chunks retrieved per query

# Minimum number of RAG chunks required before we trust corpus grounding.
# If fewer come back, expander switches to parametric mode (LLM-only).
RAG_MIN_CHUNKS_FOR_GROUNDING = int(os.environ.get("RAG_MIN_CHUNKS_FOR_GROUNDING", "2"))

# ---------------------------------------------------------------------------
# Corpus chunking
# ---------------------------------------------------------------------------
CHUNK_SIZE_TOKENS    = int(os.environ.get("CHUNK_SIZE_TOKENS",    "300"))
CHUNK_OVERLAP_TOKENS = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "50"))

# ---------------------------------------------------------------------------
# Graph traversal
# ---------------------------------------------------------------------------
MAX_TRAVERSAL_DEPTH = int(os.environ.get("MAX_TRAVERSAL_DEPTH", "8"))
MAX_NODES_PER_RUN   = int(os.environ.get("MAX_NODES_PER_RUN",   "30"))   # hard cap per run
FRONTIER_SORT       = os.environ.get("FRONTIER_SORT", "entropy_desc")    # always expand highest-entropy first
N_CHILD_HYPOTHESES  = int(os.environ.get("N_CHILD_HYPOTHESES",  "3"))    # child nodes per expansion

# RAG retrieval
RAG_DOMAIN_FILTER = os.environ.get("RAG_DOMAIN_FILTER", "true").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Path-length / diagnostic-hit evaluation
# ---------------------------------------------------------------------------
# When True, diagnostic hits are only counted in *generated* nodes (depth > 0),
# excluding seed nodes that may already contain the ground-truth diagnosis.
EVAL_EXCLUDE_SEED_HITS = os.environ.get("EVAL_EXCLUDE_SEED_HITS", "true").lower() in ("true", "1", "yes")

# Secondary winner tie-breaker: if path_length is equal, EF wins if its
# entropy_auc is this fraction lower than BF's (e.g. 0.10 = 10% lower).
EVAL_AUC_TIEBREAKER_MARGIN = float(os.environ.get("EVAL_AUC_TIEBREAKER_MARGIN", "0.10"))

# ---------------------------------------------------------------------------
# Heuristic seed entropy (used when entropy_engine=None in build_cases)
# ---------------------------------------------------------------------------
# Values calibrated on llama3.1:8b / mistral:latest:
#   - symptom/history: high uncertainty (many DDx possible)
#   - lab: moderate (narrows to a set of conditions)
#   - imaging: lower (specific findings constrain heavily)
#   - vital: moderate-high
SEED_ENTROPY_BY_FINDING_TYPE: dict[str, float] = {
    "symptom":   float(os.environ.get("ENTROPY_SYMPTOM",   "0.80")),
    "history":   float(os.environ.get("ENTROPY_HISTORY",   "0.72")),
    "vital":     float(os.environ.get("ENTROPY_VITAL",     "0.65")),
    "lab":       float(os.environ.get("ENTROPY_LAB",       "0.58")),
    "imaging":   float(os.environ.get("ENTROPY_IMAGING",   "0.32")),
    "diagnosis": float(os.environ.get("ENTROPY_DIAGNOSIS", "0.20")),  # near-certain
}
SEED_ENTROPY_DEFAULT = float(os.environ.get("SEED_ENTROPY_DEFAULT", "0.693"))  # ln(2) fallback

# ---------------------------------------------------------------------------
# Vital sign thresholds (used by clinical_case_adapter.py)
# ---------------------------------------------------------------------------
VITAL_THRESHOLDS: dict[str, tuple[float, float]] = {
    "blood_pressure_systolic":  (90.0, 180.0),
    "blood_pressure_diastolic": (60.0, 120.0),
    "heart_rate":               (50.0, 120.0),
    "oxygen_saturation":        (0.0,   94.0),  # SpO2 below 94 is flagged
    "temperature":              (36.0,  38.5),
}

# ---------------------------------------------------------------------------
# Saturation stopping condition
# ---------------------------------------------------------------------------
# Theta values are calibrated empirically for the yes/no verification prompt.
# The model's "confident floor" across traversal runs is ~0.49 nats.
# Theta is set 0.05 nats above that floor so saturation fires when entropy
# genuinely plateaus: H < theta for SATURATION_WINDOW consecutive nodes.
SATURATION_WINDOW       = int(os.environ.get("SATURATION_WINDOW",    "5"))
SATURATION_MAX_VARIANCE = float(os.environ.get("SATURATION_MAX_VARIANCE", "0.04"))

# Guard: do NOT declare saturation when mean RAG retrieval depth is below this.
# Set to 0 to disable (default). Set > 0 (e.g. 2.0) to enable.
SATURATION_CORPUS_DRY_GUARD = float(os.environ.get("SATURATION_CORPUS_DRY_GUARD", "0"))

THETA_BY_DOMAIN: dict[str, float] = {
    "pathophysiology": 0.55,   # empirical: well-supported mechanism claims hit ~0.43
    "pharmacology":    0.55,   # empirical: nitroglycerin/angina hit 0.43 at depth 1
    "genetics":        0.70,   # empirical: ClinVar conflicting-classification claims plateau at 0.66-0.69
    "imaging":         0.55,
    "lab":             0.55,
    "treatment":       0.55,
    "comorbidity":     0.70,   # comorbidities inherently uncertain — higher threshold
}
DEFAULT_THETA = float(os.environ.get("DEFAULT_THETA", "0.55"))

# ---------------------------------------------------------------------------
# Rabbit hole detection
# ---------------------------------------------------------------------------
RABBIT_HOLE_MIN_DEPTH       = int(os.environ.get("RABBIT_HOLE_MIN_DEPTH",       "3"))
RABBIT_HOLE_REVERSAL_WINDOW = int(os.environ.get("RABBIT_HOLE_REVERSAL_WINDOW", "4"))

# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------
CONTRADICTION_MODEL         = os.environ.get("CONTRADICTION_MODEL", "cross-encoder/nli-MiniLM2-L6-H768")
# EF traversal uses a tighter threshold (0.92) to avoid false-positive edges.
# BF baseline uses the same to ensure fair comparison.
CONTRADICTION_THRESHOLD_EF  = float(os.environ.get("CONTRADICTION_THRESHOLD_EF", "0.92"))
CONTRADICTION_THRESHOLD_BF  = float(os.environ.get("CONTRADICTION_THRESHOLD_BF", "0.92"))
CONTRADICTION_THRESHOLD     = float(os.environ.get("CONTRADICTION_THRESHOLD",    "0.92"))  # default alias

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
PUBMED_BATCH_SIZE    = int(os.environ.get("PUBMED_BATCH_SIZE",    "500"))
PUBMED_MAX_ABSTRACTS = int(os.environ.get("PUBMED_MAX_ABSTRACTS", "500000"))
OMIM_API_KEY         = os.environ.get("OMIM_API_KEY", "")   # Set via env or .env file
HF_TOKEN             = os.environ.get("HF_TOKEN", "")        # Optional HuggingFace token
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

# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "8000"))
