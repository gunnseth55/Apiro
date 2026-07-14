import requests
import json
import sys

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b"

def test_logprobs():
    prompt = "Please output exactly the word 'Pneumonia' and nothing else."
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    
    # First check if the model is alive
    try:
        requests.get("http://localhost:11434/api/tags", timeout=2)
    except:
        print("Ollama is not running or not accessible.")
        return

    # Try passing logprobs parameter (Ollama might not support it natively on all models, or might use different keys)
    # The Ollama API documentation doesn't formally list a 'logprobs' parameter for /api/generate yet in the same way OpenAI does,
    # but let's test if it returns anything if we ask or if we can extract probabilities.
    payload["options"]["logprobs"] = True
    
    print(f"Testing {MODEL} for logprobs support...")
    res = requests.post(OLLAMA_URL, json=payload)
    if res.status_code == 200:
        data = res.json()
        print("Response received.")
        print(f"Text output: {data.get('response', '')}")
        print("Keys in response:", list(data.keys()))
        if "logprobs" in data or "eval_duration" in data:
            print("Full JSON structure:")
            print(json.dumps(data, indent=2))
    else:
        print(f"Error {res.status_code}: {res.text}")

if __name__ == "__main__":
    test_logprobs()
