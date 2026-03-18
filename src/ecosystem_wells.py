"""Ecosystem storm detection using density-basin / gravity-well approach."""

import numpy as np
from sklearn.decomposition import PCA
from collections import Counter
from datetime import datetime

# Well detection parameters
TIME_SCALE = 1.0  # Give time equal weight to semantics
SEMANTIC_BANDWIDTH = 0.10  # Very tight semantic clustering
TIME_BANDWIDTH = 0.20  # Very tight time clustering
MIN_DENSITY_PEAK = 30.0  # High threshold
PEAK_NEIGHBOR_RADIUS = 0.15  # Very local peaks
MAX_BASIN_RADIUS = 0.25  # Very tight basins
MIN_BASIN_AFFINITY = 1.0  # Strict assignment
MIN_EVENTS_PER_WELL = 8


def project_events_to_3d(events, embeddings):
    """Project events into 3D semantic-time space.
    
    Args:
        events: List of event objects
        embeddings: numpy array of embeddings
    
    Returns:
        coords: (N, 3) array of [pc1, pc2, time_scaled]
        pca: fitted PCA object
    """
    # Project embeddings to 2D using PCA
    pca = PCA(n_components=2)
    semantic_2d = pca.fit_transform(embeddings)
    
    print(f"PCA explained variance: PC1={pca.explained_variance_ratio_[0]:.3f}, PC2={pca.explained_variance_ratio_[1]:.3f}")
    
    # Extract and scale time
    timestamps = []
    for e in events:
        if isinstance(e.timestamp, str):
            t = datetime.fromisoformat(e.timestamp.replace('Z', '+00:00'))
        else:
            t = e.timestamp
        timestamps.append(t.timestamp())
    
    timestamps = np.array(timestamps)
    
    # Normalize time to [0, 1] range
    time_min = timestamps.min()
    time_max = timestamps.max()
    time_normalized = (timestamps - time_min) / (time_max - time_min + 1e-10)
    
    # Scale time
    time_scaled = time_normalized * TIME_SCALE
    
    # Combine into 3D coordinates
    coords = np.column_stack([semantic_2d[:, 0], semantic_2d[:, 1], time_scaled])
    
    return coords, pca


def compute_density_at_points(coords, bandwidth_semantic=SEMANTIC_BANDWIDTH, bandwidth_time=TIME_BANDWIDTH):
    """Compute density at each event point using Gaussian kernel.
    
    Args:
        coords: (N, 3) array of coordinates
        bandwidth_semantic: bandwidth for semantic dimensions
        bandwidth_time: bandwidth for time dimension
    
    Returns:
        densities: (N,) array of density values
    """
    n = len(coords)
    densities = np.zeros(n)
    
    for i in range(n):
        # Compute distances to all other points
        semantic_dist = np.sqrt(
            (coords[:, 0] - coords[i, 0])**2 + 
            (coords[:, 1] - coords[i, 1])**2
        )
        time_dist = np.abs(coords[:, 2] - coords[i, 2])
        
        # Gaussian kernel contribution
        semantic_contrib = np.exp(-(semantic_dist**2) / (2 * bandwidth_semantic**2))
        time_contrib = np.exp(-(time_dist**2) / (2 * bandwidth_time**2))
        
        # Combined density
        densities[i] = np.sum(semantic_contrib * time_contrib)
    
    return densities


def detect_density_peaks(coords, densities, min_density=MIN_DENSITY_PEAK, neighbor_radius=PEAK_NEIGHBOR_RADIUS):
    """Detect local density peaks.
    
    Args:
        coords: (N, 3) array of coordinates
        densities: (N,) array of density values
        min_density: minimum density for peak
        neighbor_radius: radius to check for local maximum
    
    Returns:
        peak_indices: list of indices that are peaks
    """
    n = len(coords)
    peak_indices = []
    
    for i in range(n):
        if densities[i] < min_density:
            continue
        
        # Check if this is a local maximum
        is_peak = True
        for j in range(n):
            if i == j:
                continue
            
            # Compute distance
            dist = np.sqrt(np.sum((coords[i] - coords[j])**2))
            
            if dist < neighbor_radius and densities[j] > densities[i]:
                is_peak = False
                break
        
        if is_peak:
            peak_indices.append(i)
    
    return peak_indices


def assign_events_to_basins(coords, densities, peak_indices, max_radius=MAX_BASIN_RADIUS, min_affinity=MIN_BASIN_AFFINITY):
    """Assign events to density basins.
    
    Args:
        coords: (N, 3) array of coordinates
        densities: (N,) array of density values
        peak_indices: list of peak indices
        max_radius: maximum distance to assign to basin
        min_affinity: minimum affinity to assign
    
    Returns:
        assignments: (N,) array of peak indices (-1 for unassigned)
    """
    n = len(coords)
    assignments = np.full(n, -1, dtype=int)
    
    for i in range(n):
        best_peak = -1
        best_affinity = min_affinity
        
        for peak_idx in peak_indices:
            # Compute distance to peak
            dist = np.sqrt(np.sum((coords[i] - coords[peak_idx])**2))
            
            if dist > max_radius:
                continue
            
            # Compute affinity
            affinity = densities[peak_idx] * np.exp(-dist)
            
            if affinity > best_affinity:
                best_affinity = affinity
                best_peak = peak_idx
        
        assignments[i] = best_peak
    
    return assignments


def form_ecosystem_wells(events, embeddings, coords, densities, peak_indices, assignments, min_events=MIN_EVENTS_PER_WELL):
    """Form ecosystem wells from basin assignments.
    
    Args:
        events: List of event objects
        embeddings: numpy array of embeddings
        coords: (N, 3) array of coordinates
        densities: (N,) array of density values
        peak_indices: list of peak indices
        assignments: (N,) array of peak assignments
        min_events: minimum events per well
    
    Returns:
        wells: list of well dicts
    """
    wells = []
    
    for well_idx, peak_idx in enumerate(peak_indices):
        # Get events in this basin
        basin_mask = (assignments == peak_idx)
        basin_event_indices = np.where(basin_mask)[0]
        
        if len(basin_event_indices) < min_events:
            continue
        
        basin_events = [events[i] for i in basin_event_indices]
        basin_embeddings = embeddings[basin_event_indices]
        basin_coords = coords[basin_event_indices]
        
        # Compute centroid
        centroid = np.mean(basin_embeddings, axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        
        # Get time range
        timestamps = []
        for e in basin_events:
            if isinstance(e.timestamp, str):
                t = datetime.fromisoformat(e.timestamp.replace('Z', '+00:00'))
            else:
                t = e.timestamp
            timestamps.append(t)
        
        start_time = min(timestamps)
        end_time = max(timestamps)
        duration_days = (end_time - start_time).days
        
        # Get actors
        actors_involved = []
        actor_counts = Counter()
        for e in basin_events:
            for actor in e.actors:
                if actor not in actors_involved:
                    actors_involved.append(actor)
                actor_counts[actor] += 1
        
        dominant_actors = [actor for actor, count in actor_counts.most_common(3)]
        
        # Compute actor metrics
        num_unique_actors = len(actors_involved)
        total_actor_mentions = sum(actor_counts.values())
        dominant_actor_ratio = actor_counts.most_common(1)[0][1] / total_actor_mentions if total_actor_mentions > 0 else 0
        
        actor_entropy = 0.0
        if total_actor_mentions > 0:
            for count in actor_counts.values():
                p = count / total_actor_mentions
                if p > 0:
                    actor_entropy -= p * np.log2(p)
        
        # Compute well quality metrics
        peak_coord = coords[peak_idx]
        distances_to_peak = [np.sqrt(np.sum((c - peak_coord)**2)) for c in basin_coords]
        mean_distance_to_peak = np.mean(distances_to_peak)
        basin_radius = np.max(distances_to_peak)
        
        # Get representative titles
        similarities = []
        for i, e in enumerate(basin_events):
            sim = np.dot(basin_embeddings[i], centroid)
            similarities.append((sim, e))
        
        similarities.sort(reverse=True, key=lambda x: x[0])
        representative_events = [
            {
                'event_id': e.event_id,
                'title': e.title,
                'timestamp': e.timestamp if isinstance(e.timestamp, str) else e.timestamp.isoformat(),
                'actors': e.actors,
                'similarity': float(sim)
            }
            for sim, e in similarities[:3]
        ]
        
        # Get unique titles
        unique_titles = []
        seen_titles = set()
        for sim, e in similarities:
            if e.title not in seen_titles:
                unique_titles.append(e.title)
                seen_titles.add(e.title)
                if len(unique_titles) >= 10:
                    break
        
        # Classify well scope
        if num_unique_actors == 0:
            well_scope = "no_actor"
        elif num_unique_actors == 1:
            well_scope = "single_actor"
        elif num_unique_actors <= 3:
            well_scope = "cross_actor"
        else:
            well_scope = "ecosystem_wide"
        
        # Create well object
        well = {
            'well_id': f"eco_well_{well_idx:02d}",
            'peak_density': float(densities[peak_idx]),
            'peak_coord': peak_coord.tolist(),
            'event_count': len(basin_events),
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_days': duration_days,
            'actors_involved': actors_involved,
            'dominant_actors': dominant_actors,
            'actor_counts': dict(actor_counts),
            'num_unique_actors': num_unique_actors,
            'dominant_actor_ratio': round(dominant_actor_ratio, 3),
            'actor_entropy': round(actor_entropy, 3),
            'mean_event_distance_to_peak': round(float(mean_distance_to_peak), 3),
            'basin_radius': round(float(basin_radius), 3),
            'well_scope': well_scope,
            'event_ids': [e.event_id for e in basin_events],
            'representative_events': representative_events,
            'cluster_titles_topN': unique_titles,
            'centroid_embedding': centroid.tolist()
        }
        
        wells.append(well)
    
    # Sort by peak density
    wells.sort(key=lambda x: x['peak_density'], reverse=True)
    
    return wells
