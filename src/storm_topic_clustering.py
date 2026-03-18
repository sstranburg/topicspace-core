"""Storm-level topic clustering to identify dominant narratives within storms."""

import json
from collections import Counter

# Clustering configuration
CLUSTER_TITLE_POOL_SIZE = 10
MIN_TITLES_FOR_CLUSTERING = 5
MIN_EVENTS_FOR_CLUSTERING = 8
MAX_CLUSTERS = 3


def get_adaptive_k(n_titles):
    """Determine optimal k for clustering based on title count.
    
    Args:
        n_titles: Number of titles available
    
    Returns:
        k value for k-means, or None if clustering not recommended
    """
    if n_titles < MIN_TITLES_FOR_CLUSTERING:
        return None
    elif n_titles < 8:
        return 2
    else:
        return min(3, MAX_CLUSTERS)


def extract_cluster_terms(titles, top_n=5):
    """Extract key terms from cluster titles."""
    from collections import Counter
    import re
    
    text = ' '.join(titles).lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    words = [w for w in text.split() if len(w) > 3]
    
    word_counts = Counter(words)
    return [word for word, count in word_counts.most_common(top_n)]


def extract_cluster_bigrams(titles, min_freq=1):
    """Extract bigrams from cluster titles."""
    from collections import Counter
    import re
    
    text = ' '.join(titles).lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    words = [w for w in text.split() if len(w) > 2]
    
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    bigram_counts = Counter(bigrams)
    
    return [bigram for bigram, count in bigram_counts.most_common(5) if count >= min_freq]


def load_embeddings():
    """Load embeddings and build title->embedding map.
    
    Returns:
        dict mapping title -> embedding vector (as list)
    """
    try:
        # Try to import numpy
        import numpy as np
        
        # Load embeddings array
        data = np.load('data/derived/tech_ecosystem_embeddings.npz')
        embeddings = data['embeddings']
        
        # Load title mapping
        title_to_embedding = {}
        with open('data/derived/tech_ecosystem_embedded.jsonl', 'r') as f:
            for line in f:
                event = json.loads(line)
                idx = event.get('embedding_index')
                title = event.get('title')
                if idx is not None and title and idx < len(embeddings):
                    title_to_embedding[title] = embeddings[idx].tolist()
        
        print(f"✓ Loaded embeddings using numpy")
        return title_to_embedding
    except ImportError:
        print("⚠ numpy not available, clustering disabled")
        return {}
    except Exception as e:
        print(f"⚠ Could not load embeddings: {e}")
        return {}


def cluster_storm_titles(titles, embeddings, k=2):
    """Cluster titles within a storm to find dominant topic.
    
    Args:
        titles: List of title strings
        embeddings: list of embedding vectors (each is a list of floats)
        k: Number of clusters (default 2)
    
    Returns:
        dict with dominant_cluster_idx, cluster_labels, cluster_sizes, dominant_titles
    """
    if len(titles) < k:
        # Not enough titles to cluster, return all as single cluster
        return {
            'dominant_cluster_idx': 0,
            'cluster_labels': [0] * len(titles),
            'cluster_sizes': {0: len(titles)},
            'dominant_titles': titles,
            'num_clusters': 1
        }
    
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        
        # Convert to numpy array
        embeddings_array = np.array(embeddings)
        
        # Run k-means clustering
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(embeddings_array)
        
        # Find largest cluster
        cluster_counts = Counter(cluster_labels)
        dominant_cluster_idx = cluster_counts.most_common(1)[0][0]
        
        # Get titles from dominant cluster
        dominant_titles = [titles[i] for i, label in enumerate(cluster_labels) if label == dominant_cluster_idx]
        
        return {
            'dominant_cluster_idx': int(dominant_cluster_idx),
            'cluster_labels': cluster_labels.tolist(),
            'cluster_sizes': dict(cluster_counts),
            'dominant_titles': dominant_titles,
            'num_clusters': k
        }
    except Exception as e:
        print(f"Warning: Clustering failed: {e}")
        # Fallback: return all titles as single cluster
        return {
            'dominant_cluster_idx': 0,
            'cluster_labels': [0] * len(titles),
            'cluster_sizes': {0: len(titles)},
            'dominant_titles': titles,
            'num_clusters': 1
        }


def get_dominant_topic_titles(storm, title_embeddings_map, use_adaptive_k=True):
    """Extract dominant topic titles from a storm using clustering.
    
    Args:
        storm: Storm dict with cluster_titles_topN or representative_titles
        title_embeddings_map: Dict mapping title -> embedding vector (list)
        use_adaptive_k: Whether to use adaptive k selection
    
    Returns:
        dict with dominant_titles, clustering_info, used_clustering
    """
    # Try to use cluster_titles_topN first, fall back to representative_titles
    titles = storm.get('cluster_titles_topN', storm.get('representative_titles', []))
    event_count = storm.get('event_count', 0)
    
    # Check eligibility
    if event_count < MIN_EVENTS_FOR_CLUSTERING or len(titles) < MIN_TITLES_FOR_CLUSTERING:
        return {
            'dominant_titles': titles,
            'used_clustering': False,
            'num_clusters': 1,
            'dominant_cluster_size': len(titles),
            'cluster_dominance_ratio': 1.0,
            'cluster_titles_count': len(titles),
            'clustering_eligible': False
        }
    
    # Get embeddings for these titles
    embeddings = []
    valid_titles = []
    
    for title in titles:
        if title in title_embeddings_map:
            embeddings.append(title_embeddings_map[title])
            valid_titles.append(title)
    
    if len(valid_titles) < MIN_TITLES_FOR_CLUSTERING:
        return {
            'dominant_titles': titles,
            'used_clustering': False,
            'num_clusters': 1,
            'dominant_cluster_size': len(titles),
            'cluster_dominance_ratio': 1.0,
            'cluster_titles_count': len(titles),
            'clustering_eligible': False
        }
    
    # Determine k adaptively
    k = get_adaptive_k(len(valid_titles)) if use_adaptive_k else 2
    
    if k is None:
        return {
            'dominant_titles': valid_titles,
            'used_clustering': False,
            'num_clusters': 1,
            'dominant_cluster_size': len(valid_titles),
            'cluster_dominance_ratio': 1.0,
            'cluster_titles_count': len(valid_titles),
            'clustering_eligible': False
        }
    
    # Cluster
    result = cluster_storm_titles(valid_titles, embeddings, k=k)
    
    # Calculate dominance ratio
    dominant_size = result['cluster_sizes'][result['dominant_cluster_idx']]
    dominance_ratio = dominant_size / len(valid_titles)
    
    # Extract terms from dominant cluster
    dominant_titles = result['dominant_titles']
    dominant_terms = extract_cluster_terms(dominant_titles)
    dominant_bigrams = extract_cluster_bigrams(dominant_titles)
    
    return {
        'dominant_titles': dominant_titles,
        'used_clustering': True,
        'num_clusters': result['num_clusters'],
        'dominant_cluster_size': dominant_size,
        'cluster_dominance_ratio': round(dominance_ratio, 2),
        'cluster_titles_count': len(valid_titles),
        'clustering_eligible': True,
        'dominant_cluster_terms': dominant_terms[:3],
        'dominant_cluster_bigrams': dominant_bigrams[:2]
    }
