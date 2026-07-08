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


def generate_seed_nodes(vignette: str) -> list:
    prompt = f"""
    You are a medical AI. Read the following clinical case report and extract 3 to 4 core initial clinical findings (symptoms, signs, or initial lab results) as seed nodes for a diagnostic engine.
    IMPORTANT: At least one seed node MUST represent the patient's primary chief complaint (the acute reason they sought care). Do not focus primarily on incidental anatomical anomalies unless they are the direct cause of the acute presentation.
    Output EXACTLY a JSON array of objects. Each object must have 'id', 'claim', 'domain', 'depth' (always 0), and 'entropy' (a float between 0.1 and 0.9 representing initial uncertainty).
    Example:
    [
      {{"id": "s1", "claim": "<extract a specific symptom from the vignette here>", "domain": "symptom", "depth": 0, "entropy": 0.8}}
    ]

    Case Report:
    {vignette}

    JSON Output:
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": PRIMARY_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=120
        )
        res = response.json().get("response", "[]")
        parsed = json.loads(res)
        if isinstance(parsed, dict):
            if "seed_nodes" in parsed:
                return parsed["seed_nodes"]
            return [parsed]
        return parsed
    except Exception as e:
        print(f"Error generating seeds: {e}")
        return []


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
