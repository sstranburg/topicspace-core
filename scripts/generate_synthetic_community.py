#!/usr/bin/env python3
"""Generate synthetic community_posts.jsonl for testing the overlay pipeline."""
import json
import numpy as np
from pathlib import Path

# Load storms
storms = []
for fname in ['actor_storms.jsonl', 'ecosystem_storms.jsonl']:
    p = Path(f'data/derived/{fname}')
    if p.exists():
        with open(p) as f:
            for line in f:
                if line.strip():
                    storms.append(json.loads(line))

# Load embeddings
emb_data = np.load('data/derived/tech_ecosystem_embeddings.npz', allow_pickle=True)
embeddings = emb_data['embeddings']
event_ids = list(emb_data['event_ids'])
emb_map = {eid: embeddings[i] for i, eid in enumerate(event_ids)}

# Build storm centroids
storm_centroids = {}
for s in storms:
    eids = s.get('event_ids', [])
    vecs = [emb_map[eid] for eid in eids if eid in emb_map]
    if vecs:
        storm_centroids[s['storm_id']] = np.mean(vecs, axis=0)

print(f"Storms with centroids: {len(storm_centroids)}")

# Target storms with community posts
targets = [
    ('NVDA_2026-02-23', 'nvidia', ['NVDA'], [
        ("CUDA lock-in is getting worse with each generation",
         "Every new toolkit release makes it harder to switch. ROCm still cannot compete."),
        ("Power consumption of H100 clusters is insane",
         "Our DC is hitting power limits. 700W per GPU times thousands of GPUs."),
        ("NVDA earnings were great but margins are the real story",
         "Revenue growth impressive but how sustainable are these margins?"),
        ("GPU scarcity still a problem for smaller companies",
         "Big cloud providers hoarding all the supply."),
        ("Blackwell delays could open door for AMD",
         "If GB200 slips further MI300X could grab more share."),
    ]),
    ('AMD_2026-02-25', 'amd', ['AMD'], [
        ("MI300X benchmarks looking competitive finally",
         "Real workloads showing 80-90 percent of H100 performance at lower cost."),
        ("AMD ROCm ecosystem still needs work",
         "Software stack is the bottleneck not the hardware anymore."),
        ("AMD gaining datacenter share but slowly",
         "Server CPU share growing but GPU adoption still limited."),
        ("EPYC Turin looks like a beast",
         "Zen 5 server chips could take even more share from Intel."),
    ]),
    ('GOOGL_2026-02-27', 'machinelearning', ['GOOGL'], [
        ("Google Gemini improvements are real",
         "Latest benchmarks show significant gains over previous versions."),
        ("TPU vs GPU debate heating up",
         "Google pushing TPUs hard but most researchers still prefer CUDA."),
        ("Waymo expansion plans seem aggressive",
         "Autonomous driving rollout timeline feels optimistic."),
    ]),
    ('TSM_2026-03-08', 'semiconductors', ['TSM', 'NVDA'], [
        ("TSMC 2nm timeline looks tight",
         "Yield rates at 3nm were rough. 2nm will be even harder."),
        ("Geopolitical risk for TSMC keeps growing",
         "Taiwan situation makes everyone nervous about supply chain."),
        ("TSMC Arizona fab behind schedule",
         "Construction delays and workforce issues."),
        ("CoWoS packaging capacity is the real bottleneck",
         "Advanced packaging limiting AI chip supply."),
    ]),
    ('AMZN_2026-03-03', 'cloudcomputing', ['AMZN'], [
        ("AWS custom chips Trainium2 looking promising",
         "Could reduce dependence on NVIDIA for inference workloads."),
        ("Amazon logistics AI is underrated",
         "Their warehouse automation is years ahead of competition."),
        ("AWS pricing getting more aggressive",
         "New reserved instance pricing is very competitive."),
    ]),
    ('MSFT_2026-03-02', 'machinelearning', ['MSFT'], [
        ("Copilot adoption slower than Microsoft claims",
         "Enterprise rollout hitting friction. Users reverting to manual workflows."),
        ("Azure OpenAI capacity constraints",
         "Cannot get GPT-4 quota even with enterprise agreement."),
        ("Microsoft nuclear power deal is smart long-term",
         "Three Mile Island restart shows how serious the power problem is."),
    ]),
]

# Precursor posts (will not match any storm)
precursors = [
    ('datacenter', [],
     "Data center power grid constraints becoming critical",
     "Multiple regions hitting power capacity limits. New builds taking 3 plus years."),
    ('datacenter', ['AMZN', 'MSFT'],
     "Cloud providers buying nuclear power plants",
     "Amazon and Microsoft both making nuclear deals."),
    ('datacenter', ['NVDA', 'AMZN'],
     "Inference cost is the next big problem",
     "Training costs get attention but inference at scale is the real spend."),
    ('hardware', [],
     "Liquid cooling adoption accelerating",
     "Air cooling cannot handle modern GPU densities."),
    ('hardware', ['NVDA'],
     "GB200 power requirements are unprecedented",
     "1200W per module. Data centers need complete power overhaul."),
    ('investing', [],
     "Semiconductor cycle peak concerns growing",
     "Multiple analysts warning about inventory buildup in H2."),
    ('machinelearning', [],
     "Open source models closing the gap fast",
     "Llama and Mistral catching up to proprietary models rapidly."),
    ('semiconductors', ['TSM'],
     "EUV supply chain single point of failure",
     "ASML is literally the only supplier. One disruption and everything stops."),
]

posts = []
post_id = 0
np.random.seed(42)

for storm_id, subreddit, actors, post_data in targets:
    centroid = storm_centroids.get(storm_id)
    if centroid is None:
        print(f"  WARNING: No centroid for {storm_id}")
        continue
    for title, text in post_data:
        post_id += 1
        noise = np.random.randn(len(centroid)) * 0.001
        emb = centroid + noise
        emb = (emb / np.linalg.norm(emb)).astype(np.float32)
        posts.append({
            'post_id': f'reddit_{post_id:04d}',
            'source': 'reddit',
            'signal_layer': 'community',
            'subreddit': subreddit,
            'title': title,
            'text': text,
            'timestamp': '2026-03-10T14:00:00Z',
            'score': int(np.random.randint(25, 300)),
            'num_comments': int(np.random.randint(12, 150)),
            'embedding': emb.tolist(),
            'actors': actors,
            'tags': [],
        })

dim = embeddings.shape[1]
for subreddit, actors, title, text in precursors:
    post_id += 1
    emb = np.random.randn(dim).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    posts.append({
        'post_id': f'reddit_{post_id:04d}',
        'source': 'reddit',
        'signal_layer': 'community',
        'subreddit': subreddit,
        'title': title,
        'text': text,
        'timestamp': '2026-03-11T10:00:00Z',
        'score': int(np.random.randint(30, 200)),
        'num_comments': int(np.random.randint(15, 80)),
        'embedding': emb.tolist(),
        'actors': actors,
        'tags': [],
    })

out_path = Path('data/normalized/community_posts.jsonl')
with open(out_path, 'w') as f:
    for p in posts:
        f.write(json.dumps(p) + '\n')

print(f"Created {len(posts)} synthetic community posts")
print(f"  Storm-targeted: {len(posts) - len(precursors)}")
print(f"  Precursor: {len(precursors)}")
