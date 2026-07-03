import json
import os
import requests
import random

OLLAMA_BASE_URL = "http://localhost:11434"
PRIMARY_MODEL = "llama3.1:8b"

def generate_seed_nodes(vignette: str) -> list:
    prompt = f"""
    You are a medical AI. Read the following clinical case report and extract 3 to 4 core initial clinical findings (symptoms, signs, or initial lab results) as seed nodes for a diagnostic engine.
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
        # Filter for cases with a reasonable length to ensure some noise but not break the script's timeout
        vignette = row['patient']
        # For target diagnosis, PMC-Patients has 'similar_patients' or 'relevant_articles'. 
        # But this dataset is just the case notes. Wait, we need a ground truth diagnosis.
        # Let's ask the LLM to extract the final diagnosis from the text.
        diag_prompt = f"Extract the final confirmed primary diagnosis from this case report. Output ONLY the disease name, nothing else.\n\nCase: {vignette}"
        try:
            diag_res = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": PRIMARY_MODEL, "prompt": diag_prompt, "stream": False},
                timeout=60
            ).json().get("response", "Unknown Diagnosis").strip()
        except:
            continue
            
        print(f"Processing case {count+1}...")
        
        scrub_prompt = f"Rewrite the following clinical case report to completely remove any explicit mention of the final diagnosis, biopsy results, or surgical resolutions that give away the diagnosis. Leave only the patient history, initial presentation, symptoms, and initial lab/imaging findings intact. Do not add any introductory or concluding remarks. Output ONLY the rewritten text.\n\nCase: {vignette}"
        try:
            scrubbed_vignette = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": PRIMARY_MODEL, "prompt": scrub_prompt, "stream": False},
                timeout=120
            ).json().get("response", vignette).strip()
        except:
            scrubbed_vignette = vignette

        seeds = generate_seed_nodes(scrubbed_vignette)
        if not seeds:
            continue
            
        cases.append({
            "case_id": f"pmc_case_{count+1}",
            "description": f"Real world case report from PMC (Scrubbed)",
            "target_diagnosis": diag_res,
            "vignette": scrubbed_vignette,
            "seed_nodes": seeds
        })
        count += 1
        if count >= 10:
            break

with open("data/pmc_cases.json", "w") as f:
    json.dump(cases, f, indent=2)
    
print("Saved 10 PMC cases to data/pmc_cases.json")
