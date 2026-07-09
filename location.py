import math
import random


def _nearest_center_dist(f, centers):
    return min(math.hypot(f[0] - c[0], f[1] - c[1]) for c in centers)


def run_kmeans(fruits, num_fcps, iterations=50, tol=1e-9):
    if num_fcps <= 0 or not fruits:
        return []
    if num_fcps >= len(fruits):
        seen = []
        for f in fruits:
            if f not in seen:
                seen.append(f)
        return seen


    seed_basis = hash((len(fruits),
                       round(fruits[0][0], 6), round(fruits[0][1], 6),
                       round(fruits[-1][0], 6), round(fruits[-1][1], 6)))
    rng = random.Random(seed_basis)
    clusters_center = [rng.choice(fruits)]
    while len(clusters_center) < num_fcps:
        best_fruit = None
        max_distance = -1
        for f in fruits:
            d = _nearest_center_dist(f, clusters_center)
            if d > max_distance:
                max_distance = d
                best_fruit = f
        if max_distance <= tol:
            remaining = [f for f in fruits if f not in clusters_center]
            if not remaining:
                break
            best_fruit = remaining[0]
        clusters_center.append(best_fruit)

    # --- Lloyd iteration with early stop + empty-cluster re-seeding ---
    for _ in range(iterations):
        clusters = [[] for _ in range(len(clusters_center))]
        for f in fruits:
            best_k = 0
            min_dist = float('inf')
            for i, c in enumerate(clusters_center):
                dist = math.hypot(f[0] - c[0], f[1] - c[1])
                if dist < min_dist:
                    min_dist = dist
                    best_k = i
            clusters[best_k].append(f)

        new_centers = []
        for i in range(len(clusters_center)):
            if clusters[i]:
                avg_x = sum(f[0] for f in clusters[i]) / len(clusters[i])
                avg_y = sum(f[1] for f in clusters[i]) / len(clusters[i])
                new_centers.append((avg_x, avg_y))
            else:
                reference = new_centers if new_centers else clusters_center
                farthest = max(fruits, key=lambda f: _nearest_center_dist(f, reference))
                new_centers.append(farthest)

        shift = max(
            math.hypot(new_centers[i][0] - clusters_center[i][0],
                       new_centers[i][1] - clusters_center[i][1])
            for i in range(len(clusters_center))
        )
        clusters_center = new_centers
        if shift <= tol:
            break

    return clusters_center

def get_closest_point_on_line(cluster_center, pt1, pt2):
    px, py = cluster_center
    ax, ay = pt1
    bx, by = pt2
    
    dx = bx - ax
    dy = by - ay
    
    distance_squared = dx*dx + dy*dy
    if distance_squared == 0:
        return pt1
        
    t = ((px - ax) * dx + (py - ay) * dy) / distance_squared
    t = max(0, min(1, t))
    
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    
    return (closest_x, closest_y)

def find_constrained_fcps(fruits, max_walking_distance):
    """
    Continually increases the number of FCPs until every single fruit
    is within the max_walking_distance of an FCP center.
    """
    num_fcps = 1
    print(f"Calculating optimal FCPs for a max walking distance of {max_walking_distance}...")
    
    while True:
        # 1. Run your custom K-Means for the current number of FCPs
        centers = run_kmeans(fruits, num_fcps)
        
        # 2. Check the maximum distance from any fruit to its nearest FCP
        max_dist = 0
        for f in fruits:
            min_dist_to_center = min(math.hypot(f[0]-c[0], f[1]-c[1]) for c in centers)
            if min_dist_to_center > max_dist:
                max_dist = min_dist_to_center
                
        # 3. Check if the harvester constraint is met
        if max_dist <= max_walking_distance:
            print(f"✅ Constraint Met! We need {num_fcps} FCPs.")
            return centers
            
        # 4. If the walk is still too far, add another FCP and try again
        num_fcps += 1