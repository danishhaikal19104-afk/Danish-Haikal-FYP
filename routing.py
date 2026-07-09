import math
import random

def haversine(lat1, lon1, lat2, lon2):
    # Calculates the great-circle distance between two points in kilometers
    R = 6371.0 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def build_graph(roads, fcp_info):
    graph = {}
    
    def add_edge(node1, node2):
        if node1 not in graph: graph[node1] = {}
        if node2 not in graph: graph[node2] = {}
        dist = haversine(node1[0], node1[1], node2[0], node2[1])
        graph[node1][node2] = dist
        graph[node2][node1] = dist

    for road in roads:
        for i in range(len(road) - 1):
            add_edge(road[i], road[i+1])
            
    for fcp, pt1, pt2 in fcp_info:
        add_edge(fcp, pt1)
        add_edge(fcp, pt2)
        
    return graph

def dijkstra(graph, start, end):
    distances = {node: float('inf') for node in graph}
    distances[start] = 0
    previous = {node: None for node in graph}
    unvisited = list(graph.keys())

    while len(unvisited) > 0:
        current = unvisited[0]
        for node in unvisited:
            if distances[node] < distances[current]:
                current = node
                
        if distances[current] == float('inf') or current == end:
            break
            
        unvisited.remove(current)

        for neighbor, weight in graph[current].items():
            alt = distances[current] + weight
            if alt < distances[neighbor]:
                distances[neighbor] = alt
                previous[neighbor] = current

    path = []
    curr = end
    while curr is not None:
        path.insert(0, curr)
        curr = previous[curr]
        
    return path, distances[end]

def calculate_turn_angle(p1, p2, p3):
    v1_lat, v1_lng = p2[0] - p1[0], p2[1] - p1[1]
    v2_lat, v2_lng = p3[0] - p2[0], p3[1] - p2[1]
    mag1 = math.hypot(v1_lat, v1_lng)
    mag2 = math.hypot(v2_lat, v2_lng)
    if mag1 == 0 or mag2 == 0: return 0.0
    dot = (v1_lat * v2_lat + v1_lng * v2_lng) / (mag1 * mag2)
    dot = max(-1.0, min(1.0, dot)) 
    return math.degrees(math.acos(dot)) 

def calculate_route_distance(route, distance_matrix, fcp_coords, graph, lane_ids):
    total_dist = 0.0
    route_len = len(route)

    for i in range(route_len):
        current_idx = route[i]
        next_idx = route[(i + 1) % route_len]

        # 1. Physical driving distance
        total_dist += distance_matrix[current_idx][next_idx]

        # 2. Context-Aware Turn Penalty
        prev_idx = route[(i - 1) % route_len]
        p_prev = fcp_coords[prev_idx]
        p_curr = fcp_coords[current_idx]
        p_next = fcp_coords[next_idx]

        angle = calculate_turn_angle(p_prev, p_curr, p_next)
        is_dead_end = len(graph.get(p_curr, [])) <= 1

        if angle > 90.0:
            if is_dead_end:
                total_dist += 5.0
            else:
                sharpness = (angle - 90.0) / 90.0
                total_dist += 50.0 * (sharpness ** 2)

    # 3. Lane Fragmentation Penalty
    total_dist += _lane_fragmentation_count(route, lane_ids) * FRAGMENT_PENALTY

    # 4. Lane Order Penalty
    total_dist += _lane_order_excess(route, lane_ids) * LANE_ORDER_PENALTY

    return total_dist


FRAGMENT_PENALTY = 75.0     # cost per "extra" visit to a lane already left behind
LANE_ORDER_PENALTY = 60.0   # cost per rank skipped beyond one (empirically tuned: see notes)

def _lane_fragmentation_count(route, lane_ids):
    runs = []
    for idx in route:
        lid = lane_ids[idx]
        if not runs or runs[-1] != lid:
            runs.append(lid)
    if len(runs) > 1 and runs[0] == runs[-1]:
        runs.pop()

    counts = {}
    for lid in runs:
        counts[lid] = counts.get(lid, 0) + 1

    return sum(c - 1 for c in counts.values() if c > 1)


def _lane_order_excess(route, lane_ids):
    runs = []
    for idx in route:
        lid = lane_ids[idx]
        if not runs or runs[-1] != lid:
            runs.append(lid)
    if len(runs) > 1 and runs[0] == runs[-1]:
        runs.pop()

    m = len(runs)
    if m <= 2:
        return 0

    diffs = [abs(runs[i] - runs[(i + 1) % m]) for i in range(m)]
    max_diff = max(diffs)

    total_excess = 0
    exempted = False
    for d in diffs:
        if not exempted and d == max_diff:
            exempted = True  # the one allowed "closing the loop" jump
            continue
        total_excess += max(0, d - 1)

    return total_excess


# ============================================================
# AMOS_NECP -- GENETIC ALGORITHM
# ============================================================

def _insert_one(route):
    """Pull one city out and reinsert it elsewhere -- the mild operator."""
    i = random.randrange(len(route))
    city = route.pop(i)
    j = random.randrange(len(route))
    route.insert(j, city)
    return route

def _swap_two(route):
    """Exchange two random cities -- the exploratory operator."""
    i, j = random.sample(range(len(route)), 2)
    route[i], route[j] = route[j], route[i]
    return route

def _string_inverse(route):
    """Reverse a random sub-segment -- the diversifying operator."""
    i, j = sorted(random.sample(range(len(route)), 2))
    route[i:j+1] = route[i:j+1][::-1]
    return route

def _amos_mutate(route, gen, gen_boundary_1, gen_boundary_2):
    if gen <= gen_boundary_1:
        return _insert_one(route)
    elif gen <= gen_boundary_2:
        return _swap_two(route)
    else:
        return _string_inverse(route)

def run_genetic_algorithm(distance_matrix, fcp_coords, geo_seed, graph, lane_ids,
                           population_size=300, child_pool_size=400,
                           generations=300, crossover_rate=0.8, mutation_rate=0.1):
    random.seed(42)  # Fixed seed for reproducible results
    num_fcps = len(distance_matrix)


    lane_sequence = []
    seen_lanes = set()
    for idx in geo_seed:
        lid = lane_ids[idx]
        if lid not in seen_lanes:
            lane_sequence.append(lid)
            seen_lanes.add(lid)


    seed_members = {lid: [] for lid in lane_sequence}
    for idx in geo_seed:
        seed_members[lane_ids[idx]].append(idx)

    gen_boundary_1 = generations / 3.0
    gen_boundary_2 = 2.0 * generations / 3.0

    def assemble(chromosome):
        route = []
        for lid in lane_sequence:
            route.extend(chromosome[lid])
        return route

    def route_cost(chromosome):
        return calculate_route_distance(assemble(chromosome), distance_matrix, fcp_coords, graph, lane_ids)

    def ordered_crossover_segment(seg1, seg2):
        if len(seg1) <= 1 or random.random() > crossover_rate:
            return seg1.copy()
        size = len(seg1)
        start, end = sorted(random.sample(range(size), 2))
        child = [-1] * size
        child[start:end+1] = seg1[start:end+1]
        p2_index = 0
        for i in range(size):
            if child[i] == -1:
                while seg2[p2_index] in child:
                    p2_index += 1
                child[i] = seg2[p2_index]
        return child

    def crossover_chromosome(c1, c2):
        return {lid: ordered_crossover_segment(c1[lid], c2[lid]) for lid in lane_sequence}

    def mutate_chromosome(chromosome, gen):
        mutable_lanes = [lid for lid in lane_sequence if len(chromosome[lid]) >= 2]
        if not mutable_lanes:
            return chromosome
        lid = random.choice(mutable_lanes)
        chromosome[lid] = _amos_mutate(chromosome[lid], gen, gen_boundary_1, gen_boundary_2)
        return chromosome

    def roulette_select(scored_population):
        worst = scored_population[-1][1]
        weights = [(worst - d) + 1e-6 for _, d in scored_population]
        return random.choices(scored_population, weights=weights, k=1)[0][0]

    def random_chromosome():
        return {lid: random.sample(members, len(members)) for lid, members in seed_members.items()}


    seed_chromosome = {lid: seed_members[lid].copy() for lid in lane_sequence}
    reversed_chromosome = {lid: seed_members[lid][::-1] for lid in lane_sequence}
    population = [seed_chromosome, reversed_chromosome]
    while len(population) < population_size:
        population.append(random_chromosome())

    best_route_ever = None
    shortest_distance_ever = float('inf')

    for gen in range(1, generations + 1):
        scored = [(c, route_cost(c)) for c in population]

        for chromosome, dist in scored:
            if dist < shortest_distance_ever:
                shortest_distance_ever = dist
                best_route_ever = assemble(chromosome)

        scored.sort(key=lambda x: x[1])

        # --- Elitism Strategy: preserve the best two unconditionally ---
        elites = [
            {lid: seg.copy() for lid, seg in scored[0][0].items()},
            {lid: seg.copy() for lid, seg in scored[1][0].items()},
        ]

        # --- Generate child_pool_size candidates via roulette + crossover + AMOS mutation ---
        child_candidates = []
        for _ in range(child_pool_size):
            p1 = roulette_select(scored)
            p2 = roulette_select(scored)
            child = crossover_chromosome(p1, p2)
            if random.random() < mutation_rate:
                child = mutate_chromosome(child, gen)
            child_candidates.append(child)

        # --- Keep only the best (population_size - 2) candidates ("NChild") ---
        scored_children = [(c, route_cost(c)) for c in child_candidates]
        scored_children.sort(key=lambda x: x[1])
        survivors = [c for c, _ in scored_children[:population_size - 2]]

        population = elites + survivors

    return best_route_ever


# ============================================================
# LOCAL SEARCH REFINEMENT -- 2-opt and Or-opt
# ============================================================

def two_opt(sequence, distance_matrix, fcp_coords, graph, lane_ids, loop_cap=150):
    best_sequence = sequence.copy()
    best_cost = calculate_route_distance(best_sequence, distance_matrix, fcp_coords, graph, lane_ids)
    improved = True
    loop_count = 0
    n = len(best_sequence)

    while improved and loop_count < loop_cap:
        improved = False
        loop_count += 1
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # ignore the wrap-around edge comparing the same node
                if lane_ids[best_sequence[i+1]] != lane_ids[best_sequence[j]]:
                    continue  # would reorder lanes, not just points within one

                candidate = best_sequence.copy()
                candidate[i+1:j+1] = candidate[i+1:j+1][::-1]
                candidate_cost = calculate_route_distance(candidate, distance_matrix, fcp_coords, graph, lane_ids)

                if candidate_cost < best_cost - 0.0001:
                    best_sequence = candidate
                    best_cost = candidate_cost
                    improved = True

    return best_sequence


def or_opt(sequence, distance_matrix, fcp_coords, graph, lane_ids, loop_cap=100):
    best_sequence = sequence.copy()
    best_cost = calculate_route_distance(best_sequence, distance_matrix, fcp_coords, graph, lane_ids)
    improved = True
    loop_count = 0

    while improved and loop_count < loop_cap:
        improved = False
        loop_count += 1
        n = len(best_sequence)

        for seg_len in (1, 2):
            for i in range(n):
                seg_preview = [best_sequence[(i + k) % n] for k in range(seg_len)]
                seg_lanes = {lane_ids[node] for node in seg_preview}
                if len(seg_lanes) > 1:
                    continue  # segment itself straddles a lane boundary -- leave it alone
                seg_lane = next(iter(seg_lanes))

                best_candidate = None
                best_candidate_cost = best_cost - 0.0001

                for j in range(n):
                    if j == i - 1 or j == i or j == (i + seg_len - 2):
                        continue
                    if seg_len == 1 and j == (i - 1) % n:
                        continue
                    if lane_ids[best_sequence[j % n]] != seg_lane:
                        continue  # would move the segment into a different lane

                    seg = [best_sequence[(i + k) % n] for k in range(seg_len)]
                    remaining = [best_sequence[x % n] for x in range(n)
                                 if x % n not in {(i + k) % n for k in range(seg_len)}]
                    anchor = best_sequence[j % n]
                    if anchor not in remaining:
                        continue
                    ins = remaining.index(anchor)
                    candidate = remaining[:ins+1] + seg + remaining[ins+1:]

                    candidate_cost = calculate_route_distance(candidate, distance_matrix, fcp_coords, graph, lane_ids)
                    if candidate_cost < best_candidate_cost:
                        best_candidate_cost = candidate_cost
                        best_candidate = candidate

                if best_candidate is not None:
                    best_sequence = best_candidate
                    best_cost = best_candidate_cost
                    improved = True
                    break
            if improved:
                break

    return best_sequence