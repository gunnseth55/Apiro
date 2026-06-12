import logging
import sys
from apiro.corpus.embedder import Embedder

logging.basicConfig(level=logging.INFO)

def main():
    embedder = Embedder()
    count = embedder.count
    print(f"Total documents: {count}")
    if count > 0:
        results = embedder._collection.get(limit=10)
        metadatas = results.get("metadatas", [])
        for i, meta in enumerate(metadatas):
            print(f"Doc {i} metadata: {meta}")

if __name__ == "__main__":
    main()
