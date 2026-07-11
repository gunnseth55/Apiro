import argparse
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("run")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

class OllamaLLMClient:
    def __init__(self, url, model):
        self.url = url
        self.model = model

    def generate(self, prompt: str) -> str:
        import requests
        resp = requests.post(
            f"{self.url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2, "num_predict": 180}},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    def chat(self, prompt: str) -> str:
        return self.generate(prompt)

if __name__ == "__main__":
    print("Please use scripts/investigate.py or scripts/app.py as the entry point.")
    sys.exit(0)
