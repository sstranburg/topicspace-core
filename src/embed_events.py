import numpy as np
import requests
import os
from dotenv import load_dotenv

load_dotenv()

from src.merge_events import load_jsonl

EMBEDDING_API_URL = "https://api.openai.com"
EMBEDDING_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-large"


def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> np.ndarray:
    """Get embeddings from OpenAI API in batches."""
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        response = requests.post(
            f"{EMBEDDING_API_URL}/v1/embeddings",
            headers={
                "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": batch
            },
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        all_embeddings.extend(embeddings)
        
        print(f"  Processed {min(i + batch_size, len(texts))}/{len(texts)} texts")
    
    return np.array(all_embeddings, dtype=np.float32)


def embed_events(jsonl_path: str, output_npz: str, output_jsonl: str):
    """
    Load events, generate embeddings, and save to files.
    
    Args:
        jsonl_path: Path to normalized events JSONL
        output_npz: Path to save embeddings as NPZ
        output_jsonl: Path to save event metadata with embeddings
    """
    print("Loading events...")
    events = load_jsonl(jsonl_path)
    print(f"Loaded {len(events)} events")
    
    print("\nGenerating embeddings...")
    texts = [f"{e.title} {e.text}" for e in events]
    embeddings = get_embeddings_batch(texts)
    
    # Normalize embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms
    
    print(f"\nEmbedding shape: {embeddings.shape}")
    print(f"Checking for NaNs: {np.isnan(embeddings).any()}")
    
    # Save NPZ with event_id mapping
    event_ids = [e.event_id for e in events]
    print(f"\nSaving embeddings to {output_npz}...")
    np.savez(
        output_npz,
        embeddings=embeddings,
        event_ids=event_ids
    )
    
    # Save JSONL with metadata
    print(f"Saving metadata to {output_jsonl}...")
    import json
    with open(output_jsonl, 'w') as f:
        for i, event in enumerate(events):
            data = {
                'event_id': event.event_id,
                'timestamp': event.timestamp,
                'actors': event.actors,
                'tags': event.tags,
                'title': event.title,
                'embedding_index': i
            }
            f.write(json.dumps(data) + '\n')
    
    print(f"\n✅ Done! Generated {len(embeddings)} embeddings")
    return embeddings, event_ids
