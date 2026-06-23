#!/usr/bin/env python3
"""
Apiro Calibration Experiment — Data Collection Script
======================================================
Queries LLaMA 3.1 8B and Mistral 7B via Ollama for each of the 60 clinical
questions at three temperatures (0.3, 0.7, 1.2).

For each question × model × temperature combination, this script records:
  - token_entropy:         Shannon entropy of the top-40 logprob distribution
                           for the FIRST generated token.
  - top1_probability:      Probability of the single most likely first token.
  - semantic_dispersion:   Mean pairwise cosine distance across 10 short answers
                           embedded with all-mpnet-base-v2.
  - entropy_variance:      Variance of per-sample token entropy across 10 samples.
  - temperature_sensitivity: Computed in analyze_results.py (post-hoc from saved data).

Output: data/raw_results.json
"""

import json
import math
import time
import argparse
from pathlib import Path
from itertools import combinations
from typing import Optional

import numpy as np
import requests
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434"
MODELS = {
    "llama3.1:8b": "llama3.1",
    "mistral:7b":  "mistral",
}
TEMPERATURES = [0.3, 0.7, 1.2]
N_SAMPLES = 10          # repeated samples per question × temp × model
TOP_LOGPROBS = 40       # top-k logprobs for entropy computation
MAX_FIRST_TOKEN = 1     # only the first token for token entropy
MAX_ANSWER_TOKENS = 80  # ~2 sentences for semantic dispersion
EMBED_MODEL = "all-mpnet-base-v2"

DATA_DIR   = Path(__file__).parent.parent / "data"
SCRIPT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

def check_model_available(model_name: str) -> bool:
    """Return True if the model is pulled in Ollama."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        pulled = {m["name"] for m in resp.json().get("models", [])}
        # Match by prefix in case of tag variants
        for p in pulled:
            if p.startswith(model_name.split(":")[0]):
                return True
        return False
    except Exception as e:
        print(f"  [WARN] Could not check model list: {e}")
        return False


def query_first_token_logprobs(
    model: str,
    prompt: str,
    temperature: float,
    top_k: int = TOP_LOGPROBS,
    retries: int = 3,
) -> Optional[dict]:
    """
    Query Ollama for the top-k logprobs of the first generated token only.
    Uses /api/generate with num_predict=1 and logprobs=true.

    Returns:
        {"logprobs": [...], "token": str}  or None on failure.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": MAX_FIRST_TOKEN,
            "top_k": 100,               # ensure enough candidates are tracked
        },
        "logprobs": True,
        "top_logprobs": top_k,
    }
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            # Ollama returns logprobs at top level or inside the response dict.
            # Structure: data["logprobs"] is a list of per-position dicts,
            # each with "token", "logprob", "top_logprobs" (list of {token, logprob}).
            logprobs_raw = data.get("logprobs")
            if not logprobs_raw:
                # Some models don't surface logprobs; return None to flag this.
                return None

            # We only care about position 0 (the first token).
            first_pos = logprobs_raw[0] if isinstance(logprobs_raw, list) else logprobs_raw
            top_entries = first_pos.get("top_logprobs", [])
            if not top_entries:
                return None

            return {
                "token": first_pos.get("token", ""),
                "logprobs": [e["logprob"] for e in top_entries],
                "tokens":   [e["token"]  for e in top_entries],
            }
        except requests.exceptions.Timeout:
            print(f"  [WARN] Timeout on attempt {attempt+1}/{retries}")
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            print(f"  [WARN] Request error attempt {attempt+1}/{retries}: {e}")
            time.sleep(3)
    return None


def query_short_answer(
    model: str,
    prompt: str,
    temperature: float,
    retries: int = 3,
) -> Optional[str]:
    """
    Generate a short answer (≤ 2 sentences) for embedding-based semantic dispersion.
    """
    system_prompt = (
        "You are a concise medical expert. Answer the question in exactly 1-2 sentences. "
        "Be direct. Do not start with 'As a medical expert' or similar preambles."
    )
    full_prompt = f"{system_prompt}\n\nQuestion: {prompt}\nAnswer:"
    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": MAX_ANSWER_TOKENS,
            "stop": ["\n\n", "Question:"],
        },
    }
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
        except requests.exceptions.Timeout:
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            print(f"  [WARN] Short-answer request error: {e}")
            time.sleep(3)
    return None


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def shannon_entropy(logprobs: list[float]) -> float:
    """
    Compute Shannon entropy (in nats) from a list of log-probabilities.
    logprobs are natural-log probabilities (Ollama returns log base e).
    """
    probs = np.exp(np.array(logprobs, dtype=np.float64))
    # Normalise in case they don't sum to 1 (top-k truncation)
    probs = probs / probs.sum()
    # Clip to avoid log(0)
    probs = np.clip(probs, 1e-12, 1.0)
    return float(-np.sum(probs * np.log(probs)))


def semantic_dispersion(answers: list[str], embedder: SentenceTransformer) -> float:
    """
    Compute mean pairwise cosine DISTANCE (1 - cosine_similarity) across
    all pairs of embedded answers.
    """
    if len(answers) < 2:
        return 0.0
    embeddings = embedder.encode(answers, normalize_embeddings=True)
    # With L2-normalised embeddings, cosine similarity = dot product.
    # cosine distance = 1 - cosine similarity.
    distances = []
    for i, j in combinations(range(len(embeddings)), 2):
        cos_sim = float(np.dot(embeddings[i], embeddings[j]))
        distances.append(1.0 - cos_sim)
    return float(np.mean(distances))


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    questions_path: Path,
    output_path: Path,
    smoke_test: bool = False,
    smoke_n_per_group: int = 2,
    smoke_temps: Optional[list] = None,
    smoke_samples: int = 2,
):
    # Load questions
    with open(questions_path) as f:
        questions = json.load(f)["questions"]

    if smoke_test:
        print("=== SMOKE TEST MODE ===")
        temps = smoke_temps or [0.7]
        n_samples = smoke_samples
        # 2 from each group
        by_group: dict[str, list] = {}
        for q in questions:
            by_group.setdefault(q["group"], []).append(q)
        selected = []
        for group, qs in sorted(by_group.items()):
            selected.extend(qs[:smoke_n_per_group])
        questions = selected
        print(f"  Using {len(questions)} questions, temps={temps}, samples={n_samples}")
    else:
        temps = TEMPERATURES
        n_samples = N_SAMPLES
        print(f"=== FULL EXPERIMENT ===")
        print(f"  {len(questions)} questions × {len(temps)} temps × {len(MODELS)} models × {n_samples} samples")
        print(f"  Total LLM calls: {len(questions) * len(temps) * len(MODELS) * n_samples}")

    # Load sentence embedder
    print(f"\nLoading sentence embedder: {EMBED_MODEL}")
    embedder = SentenceTransformer(EMBED_MODEL)
    print("  Embedder loaded.")

    # Verify model availability
    print("\nChecking Ollama model availability...")
    for model_key in MODELS:
        available = check_model_available(model_key)
        print(f"  {model_key}: {'OK' if available else 'NOT FOUND — will attempt anyway'}")

    results = []
    total_iterations = len(questions) * len(temps) * len(MODELS)

    with tqdm(total=total_iterations, desc="Collecting data") as pbar:
        for question in questions:
            qid   = question["id"]
            group = question["group"]
            text  = question["question"]

            for model_key, model_label in MODELS.items():
                for temp in temps:

                    # ---- Token-level data: N_SAMPLES first-token logprob queries ----
                    per_sample_entropies = []
                    top1_probs = []

                    for sample_idx in range(n_samples):
                        lp_result = query_first_token_logprobs(
                            model=model_key,
                            prompt=text,
                            temperature=temp,
                        )
                        if lp_result is None:
                            # Model doesn't surface logprobs — record NaN
                            per_sample_entropies.append(float("nan"))
                            top1_probs.append(float("nan"))
                        else:
                            lps = lp_result["logprobs"]
                            ent = shannon_entropy(lps)
                            per_sample_entropies.append(ent)
                            top1_probs.append(float(np.exp(lps[0])))

                    valid_entropies = [e for e in per_sample_entropies if not math.isnan(e)]
                    mean_entropy   = float(np.mean(valid_entropies))  if valid_entropies else float("nan")
                    entropy_var    = float(np.var(valid_entropies))   if valid_entropies else float("nan")
                    mean_top1_prob = float(np.mean([p for p in top1_probs if not math.isnan(p)])) \
                                     if any(not math.isnan(p) for p in top1_probs) else float("nan")

                    # ---- Semantic-level data: N_SAMPLES short answers ----
                    answers = []
                    for _ in range(n_samples):
                        ans = query_short_answer(
                            model=model_key,
                            prompt=text,
                            temperature=temp,
                        )
                        if ans:
                            answers.append(ans)

                    sem_disp = semantic_dispersion(answers, embedder) if len(answers) >= 2 else float("nan")

                    record = {
                        "question_id":         qid,
                        "group":               group,
                        "category":            question["category"],
                        "model":               model_label,
                        "model_key":           model_key,
                        "temperature":         temp,
                        "token_entropy":       mean_entropy,
                        "top1_probability":    mean_top1_prob,
                        "entropy_variance":    entropy_var,
                        "semantic_dispersion": sem_disp,
                        "per_sample_entropies": per_sample_entropies,
                        "sampled_answers":     answers,
                        "n_valid_entropy_samples": len(valid_entropies),
                        "n_valid_answers":     len(answers),
                    }
                    results.append(record)
                    pbar.update(1)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"metadata": {
            "smoke_test":  smoke_test,
            "models":      list(MODELS.values()),
            "temperatures": temps,
            "n_samples":   n_samples,
            "top_logprobs": TOP_LOGPROBS,
            "embed_model": EMBED_MODEL,
        }, "results": results}, f, indent=2)

    print(f"\nResults saved to {output_path}")
    print(f"Total records: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Apiro Calibration Experiment.")
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="Run a quick smoke test with 2 questions per group, 1 temp, 2 samples.",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON file path (default: data/raw_results.json or data/smoke_results.json).",
    )
    args = parser.parse_args()

    questions_path = DATA_DIR / "questions.json"
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = DATA_DIR / ("smoke_results.json" if args.smoke_test else "raw_results.json")

    run_experiment(
        questions_path=questions_path,
        output_path=output_path,
        smoke_test=args.smoke_test,
    )
