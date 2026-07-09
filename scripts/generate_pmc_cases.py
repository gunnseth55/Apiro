"""
scripts/generate_pmc_cases.py
------------------------------
Generates 10 gold-standard diagnostic evaluation cases from the local
PMC-Patients-V2.json dataset.

4-stage pipeline per case:
  Stage 1: Solvability filter — skip cases that require biopsy to diagnose.
  Stage 2: Acute target extraction — strict JSON output (avoids hallucination).
  Stage 3: Vignette scrubbing — remove diagnosis spoilers.
  Stage 4: Seed node extraction — anchor to chief complaint.

FIX vs feature/signal-rewrite:
  Stage 2 now uses format="json" and extracts {"diagnosis": "..."} to prevent
  the LLM from producing conversational paragraphs instead of a clean name.
"""

import json
import re
import requests

OLLAMA_BASE_URL = "http://localhost:11434"
PRIMARY_MODEL = "llama3.1:8b"


def _extract_one(vignette: str, domain: str, id_prefix: str, idx: int) -> dict | None:
    """Ask the LLM for exactly ONE finding of a specific domain. Much more reliable than bulk."""
    if domain == "symptom":
        task = "Extract the SINGLE most important SYMPTOM or SIGN the patient presented with (what they complained about or what was found on exam)."
    elif domain == "lab_result":
        task = "Extract the SINGLE most diagnostically relevant LAB RESULT or IMAGING FINDING mentioned (e.g. elevated WBC, bilateral infiltrates, ECG finding, X-ray result)."
    else:
        task = "Extract the SINGLE most relevant RISK FACTOR or PAST MEDICAL HISTORY item (e.g. age, comorbidity, prior procedure, recent travel, substance use)."

    prompt = (
        f"{task}\n"
        "Output ONLY a JSON object with keys: id, claim, domain, depth, entropy.\n"
        "- id: string\n"
        "- claim: exact text from the vignette (do NOT add diagnosis or treatment)\n"
        f"- domain: \"{domain}\"\n"
        "- depth: 0\n"
        "- entropy: float 0.1-0.9 (higher = more ambiguous)\n\n"
        f"Vignette:\n{vignette}\n\nJSON:"
    )
    try:
        res = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": PRIMARY_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=60,
        ).json().get("response", "{}")
        obj = json.loads(res)
        if isinstance(obj, list):
            obj = obj[0] if obj else {}
        if "claim" in obj and obj["claim"].strip():
            obj["id"] = f"{id_prefix}{idx}"
            obj["domain"] = domain
            obj["depth"] = 0
            obj.setdefault("entropy", 0.7)
            return obj
    except Exception as e:
        print(f"  Seed extraction ({domain}) failed: {e}")
    return None


def generate_seed_nodes(vignette: str) -> list:
    """
    Extract 3-4 seed nodes by making separate focused LLM calls per domain.
    This is far more reliable than asking for a bulk JSON array in one shot.
    """
    seeds = []
    for domain, prefix, idx in [("symptom", "s", 1), ("lab_result", "l", 1), ("history", "h", 1)]:
        node = _extract_one(vignette, domain, prefix, idx)
        if node:
            seeds.append(node)
    # Optionally add a second symptom if we have fewer than 3
    if len(seeds) < 3:
        node = _extract_one(vignette, "symptom", "s", 2)
        if node and node["claim"] != (seeds[0]["claim"] if seeds else ""):
            seeds.append(node)
    return seeds



print("Loading local PMC-Patients-V2 dataset...")
with open("data/PMC-Patients-V2.json", "r") as f:
    dataset = json.load(f)

skip_count = 50
cases = []
count = 0

for row in dataset:
    if len(row['patient'].split()) > 200 and len(row['patient'].split()) < 600:
        if skip_count > 0:
            skip_count -= 1
            continue
        vignette = row['patient']

        # Stage 1: Solvability Filter
        solvability_prompt = (
            "Does this case report present a diagnosis that is reasonably deducible "
            "from the initial clinical presentation (symptoms, signs, and basic labs/imaging)? "
            "If the diagnosis fundamentally requires a biopsy, pathology report, or exploratory "
            "surgery to determine (e.g. specific histological cancer subtypes), answer NO. "
            "Otherwise, answer YES.\n\n"
            f"Case: {vignette}"
        )
        try:
            solvability_res = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": PRIMARY_MODEL, "prompt": solvability_prompt, "stream": False},
                timeout=60
            ).json().get("response", "NO").strip().upper()
            if "YES" not in solvability_res:
                print(f"  Skipping (not solvable from presentation)")
                continue
        except:
            continue

        # Stage 2: Acute Target Extraction — strict JSON output to prevent hallucination
        diag_prompt = (
            "Extract the single ACUTE primary diagnosis from this case report. "
            "Output ONLY a JSON object with one field: {\"diagnosis\": \"<disease name>\"}. "
            "The diagnosis must be the condition the clinicians identified during this visit. "
            "Do NOT include pre-existing chronic conditions. "
            "Do NOT add any explanation. Output ONLY the JSON object.\n\n"
            f"Case: {vignette}"
        )
        try:
            diag_raw = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": PRIMARY_MODEL, "prompt": diag_prompt, "stream": False, "format": "json"},
                timeout=60
            ).json().get("response", "{}")
            diag_res = json.loads(diag_raw).get("diagnosis", "Unknown Diagnosis").strip()
        except:
            continue

        # Stage 2b: Deterministic histological label filter.
        # Diagnoses with pathology-only subtype qualifiers cannot be deduced
        # from clinical presentation alone — skip to keep the dataset honest.
        _HISTOLOGY_TERMS = re.compile(
            r"\b(poorly differentiated|well differentiated|moderately differentiated|"
            r"undifferentiated|serous|mucinous|adenocarcinoma|cystadenocarcinoma|"
            r"adenoma|carcinoid|stromal tumor|leiomyosarcoma|liposarcoma|fibrosarcoma|"
            r"rhabdomyosarcoma|angiosarcoma|chondrosarcoma|osteosarcoma|"
            r"mesothelioma|blastoma|histiocytoma|schwannoma|neurofibrosarcoma|"
            r"bronchioloalveolar|papillary carcinoma|follicular carcinoma|"
            r"medullary carcinoma|anaplastic|pleomorphic)\b",
            re.IGNORECASE,
        )
        if _HISTOLOGY_TERMS.search(diag_res):
            print(f"  Skipping (histology-only label: '{diag_res}')")
            continue

        print(f"Processing case {count+1}: {diag_res}")

        # Stage 3: Clean Scrubbing
        scrub_prompt = (
            "Rewrite this case report as a diagnostic challenge for a medical student. "
            "Stop the narrative immediately after the initial clinical presentation, physical exam, "
            "and first-line labs/imaging. Completely remove any mention of biopsies, surgical "
            "exploration, specific treatments given, or the final diagnosis. "
            "Do not add any introductory or concluding remarks. Output ONLY the rewritten text.\n\n"
            f"Case: {vignette}"
        )
        try:
            scrubbed_vignette = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": PRIMARY_MODEL, "prompt": scrub_prompt, "stream": False},
                timeout=120
            ).json().get("response", vignette).strip()
        except:
            scrubbed_vignette = vignette

        # Stage 4: Seed node generation
        seeds = generate_seed_nodes(scrubbed_vignette)
        if not seeds:
            print(f"  Skipping (no seeds generated)")
            continue

        cases.append({
            "case_id": f"pmc_case_{count+1}",
            "description": "Real world case report from PMC (Scrubbed)",
            "target_diagnosis": diag_res,
            "vignette": scrubbed_vignette,
            "seed_nodes": seeds
        })
        count += 1
        if count >= 10:
            break

with open("data/pmc_cases.json", "w") as f:
    json.dump(cases, f, indent=2)

print(f"\nSaved {count} PMC cases to data/pmc_cases.json")
