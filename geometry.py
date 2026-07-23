"""
Geometry utilities: fruit grid generation, road cleanup, gate/entrance
detection, and lane grouping for the FCP routing seed.
"""

import math
from collections import defaultdict

import location
import routing


def haversine_distance_km(coord1, coord2):
    """Straight-line distance x1.3 (detour factor: real walking/driving
    paths through the field are longer than a straight line)."""
    return routing.haversine(coord1[0], coord1[1], coord2[0], coord2[1]) * 1.3


def is_inside_polygon(x, y, polygon):
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xints:
                            inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def generate_fruit_grid(boundary_points, target_spacing_m=20.0,
                        min_steps=8, max_steps=60):
    """Lay a lat/lng grid over the boundary's bounding box, spaced ~20m
    apart, then keep only the points that fall inside the polygon."""
    if len(boundary_points) < 3:
        return []

    lats = [p[0] for p in boundary_points]
    lngs = [p[1] for p in boundary_points]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)

    # Bounding-box dimensions in meters, so grid step count is spacing-aware.
    height_m = routing.haversine(min_lat, min_lng, max_lat, min_lng) * 1000.0
    width_m  = routing.haversine(min_lat, min_lng, min_lat, max_lng) * 1000.0

    spacing = target_spacing_m if target_spacing_m > 0 else 20.0
    steps_lat = int(round(height_m / spacing))
    steps_lng = int(round(width_m / spacing))

    steps_lat = max(min_steps, min(max_steps, steps_lat))
    steps_lng = max(min_steps, min(max_steps, steps_lng))

    lat_step = (max_lat - min_lat) / steps_lat if steps_lat > 0 else 0
    lng_step = (max_lng - min_lng) / steps_lng if steps_lng > 0 else 0

    fruits = []
    for i in range(steps_lat + 1):
        for j in range(steps_lng + 1):
            lat = min_lat + i * lat_step
            lng = min_lng + j * lng_step
            if is_inside_polygon(lat, lng, boundary_points):
                fruits.append((lat, lng))

    return fruits


def get_line_intersection(p1, p2, p3, p4):
    """Parametric segment-segment intersection. Returns the point only if
    it lies strictly inside BOTH segments (0<t<1 and 0<u<1)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denom == 0:
        return None  # parallel lines

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0 < t < 1 and 0 < u < 1:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return (round(ix, 6), round(iy, 6))  # rounded to kill float noise
    return None


def process_crosshatch_roads(drawn_roads):
    """Clean up hand-drawn roads in two passes:
    1) Snap near-miss T-junction endpoints onto the road they almost touch.
    2) Split every segment at real crossings (X) and snapped T-junctions,
       so the road network becomes a proper graph of connected edges.
    """
    raw_segments = []
    for road in drawn_roads:
        for i in range(len(road) - 1):
            raw_segments.append([road[i], road[i + 1]])

    # --- Pass 1: snap undershot T-junction endpoints (within ~15m) ---
    for i, segA in enumerate(raw_segments):
        for end_idx in [0, 1]:
            pt = segA[end_idx]
            for j, segB in enumerate(raw_segments):
                if i == j:
                    continue
                proj = location.get_closest_point_on_line(pt, segB[0], segB[1])
                dist = math.hypot(pt[0] - proj[0], pt[1] - proj[1])
                if 0 < dist < 0.00015:
                    segA[end_idx] = (round(proj[0], 6), round(proj[1], 6))

    # --- Pass 2: split each segment at X-crossings and T-junctions ---
    processed_roads = []
    for i, segA in enumerate(raw_segments):
        intersections = []
        for j, segB in enumerate(raw_segments):
            if i == j:
                continue

            ix = get_line_intersection(segA[0], segA[1], segB[0], segB[1])
            if ix:
                intersections.append(ix)

            # T-junction: segB's endpoint sits exactly on segA's line.
            for pt in [segB[0], segB[1]]:
                proj = location.get_closest_point_on_line(pt, segA[0], segA[1])
                if math.hypot(pt[0] - proj[0], pt[1] - proj[1]) < 0.00001:
                    if pt != segA[0] and pt != segA[1]:
                        intersections.append(pt)

        if not intersections:
            processed_roads.append(segA)
        else:
            intersections.sort(key=lambda p: math.hypot(p[0]-segA[0][0], p[1]-segA[0][1]))
            spliced = [segA[0]]
            for ix in intersections:
                if math.hypot(ix[0]-spliced[-1][0], ix[1]-spliced[-1][1]) > 0.00001:
                    spliced.append(ix)
            spliced.append(segA[1])
            processed_roads.append(spliced)

    return processed_roads


# ============================================================
# GATE / ENTRANCE DETECTION -- candidates for the mill connection
# ============================================================

def _point_to_boundary_km(node, boundary):
    """Shortest distance from a point to the boundary polygon's edges."""
    best = float('inf')
    n = len(boundary)
    for i in range(n):
        p1 = boundary[i]
        p2 = boundary[(i + 1) % n]
        proj = location.get_closest_point_on_line(node, p1, p2)
        best = min(best, haversine_distance_km(node, proj))
    return best


def is_perimeter_segment(p1, p2, boundary, tol_km=0.025):
    """True if both endpoints AND the midpoint of a road segment sit close
    to the estate boundary (i.e. this road runs along the perimeter)."""
    if not boundary or len(boundary) < 3:
        return False
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    return (_point_to_boundary_km(p1, boundary) <= tol_km and
            _point_to_boundary_km(p2, boundary) <= tol_km and
            _point_to_boundary_km(mid, boundary) <= tol_km)


def find_gate_nodes(drawn_roads, boundary, tol_km=0.030):
    """Pick candidate estate entrances, in order of preference:
    1) dead-end road nodes near the boundary (a road that stops at the fence)
    2) any dead-end at all
    3) any boundary-touching node (covers all-loop road networks)
    4) fall back to every node
    """
    node_degree = defaultdict(int)
    seen_nodes = []
    seen_keys = set()
    for road in drawn_roads:
        for i in range(len(road)):
            pt = road[i]
            key = (round(pt[0], 7), round(pt[1], 7))
            if key not in seen_keys:
                seen_keys.add(key)
                seen_nodes.append(pt)
        for i in range(len(road) - 1):
            node_degree[(round(road[i][0], 7), round(road[i][1], 7))] += 1
            node_degree[(round(road[i+1][0], 7), round(road[i+1][1], 7))] += 1

    def deg(pt):
        return node_degree[(round(pt[0], 7), round(pt[1], 7))]

    has_boundary = boundary and len(boundary) >= 3

    def near_boundary(pt):
        return has_boundary and _point_to_boundary_km(pt, boundary) <= tol_km

    deadends = [pt for pt in seen_nodes if deg(pt) == 1]

    gates = [pt for pt in deadends if near_boundary(pt)]
    if gates:
        return gates
    if deadends:
        return deadends
    if has_boundary:
        gates = [pt for pt in seen_nodes if near_boundary(pt)]
        if gates:
            return gates
    return seen_nodes


# ============================================================
# LANE / COLUMN DETECTION -- feeds the GA's seed sequence
# ============================================================

def compute_lane_groups(all_road_network):
    """Group road edges into 'lanes': maximal chains of degree-2 nodes
    (i.e. a straight run of road with no junction in between), using
    union-find. Junctions (degree != 2) mark lane boundaries."""
    edges = []
    for road in all_road_network:
        for i in range(len(road) - 1):
            edges.append((road[i], road[i+1]))

    node_degree = defaultdict(int)
    for u, v in edges:
        node_degree[u] += 1
        node_degree[v] += 1

    parent = list(range(len(edges)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    node_to_edge_idxs = defaultdict(list)
    for idx, (u, v) in enumerate(edges):
        node_to_edge_idxs[u].append(idx)
        node_to_edge_idxs[v].append(idx)

    # Merge two edges into the same lane whenever they meet at a
    # pass-through node (degree 2 = "not a junction").
    for node, idxs in node_to_edge_idxs.items():
        if node_degree[node] == 2 and len(idxs) == 2:
            union(idxs[0], idxs[1])

    seg_to_lane = {}
    lane_boundary_nodes = defaultdict(set)
    for idx, (u, v) in enumerate(edges):
        lane_id = find(idx)
        key = (min(u, v), max(u, v))
        seg_to_lane[key] = lane_id
        if node_degree[u] != 2:
            lane_boundary_nodes[lane_id].add(u)
        if node_degree[v] != 2:
            lane_boundary_nodes[lane_id].add(v)

    return seg_to_lane, node_degree, lane_boundary_nodes


def order_lanes_2d(lane_ids, centroids):
    """Order lanes by a nearest-neighbour sweep from a corner, then
    polish with 2-opt (open-path, not a closed loop)."""
    lane_ids = list(lane_ids)
    if len(lane_ids) <= 2:
        return lane_ids

    unvisited = set(lane_ids)
    min_x = min(centroids[l][0] for l in lane_ids)
    min_y = min(centroids[l][1] for l in lane_ids)
    start = min(lane_ids, key=lambda l: math.hypot(centroids[l][0] - min_x, centroids[l][1] - min_y))

    order = [start]
    unvisited.discard(start)
    while unvisited:
        last = centroids[order[-1]]
        nxt = min(unvisited, key=lambda l: math.hypot(centroids[l][0] - last[0], centroids[l][1] - last[1]))
        order.append(nxt)
        unvisited.discard(nxt)

    # 2-opt refinement over the lane sequence (path, not a loop).
    n = len(order)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 2, n):
                a, b, c = order[i], order[i + 1], order[j]
                d = order[j + 1] if j + 1 < n else None

                removed = math.hypot(centroids[a][0]-centroids[b][0], centroids[a][1]-centroids[b][1])
                added = math.hypot(centroids[a][0]-centroids[c][0], centroids[a][1]-centroids[c][1])
                if d is not None:
                    removed += math.hypot(centroids[c][0]-centroids[d][0], centroids[c][1]-centroids[d][1])
                    added += math.hypot(centroids[b][0]-centroids[d][0], centroids[b][1]-centroids[d][1])

                if added < removed - 1e-9:
                    order[i+1:j+1] = reversed(order[i+1:j+1])
                    improved = True

    return order


def compute_lane_ranks(all_road_network, road_segs, fcps):
    """Assign each lane a numeric rank along the sweep order. Through-lanes
    (both ends are junctions) get integer ranks 0,1,2,...; dead-end lanes
    get a half-step rank next to their nearest through-lane (e.g. 2.5),
    so they sort in right after the lane they branch off from."""
    seg_to_lane, node_degree, lane_boundary_nodes = compute_lane_groups(all_road_network)

    def lane_id_for(seg):
        key = (min(seg[0], seg[1]), max(seg[0], seg[1]))
        return seg_to_lane[key]

    lane_fcp_sum = defaultdict(lambda: [0.0, 0.0, 0])
    for seg, fcp in zip(road_segs, fcps):
        lid = lane_id_for(seg)
        s = lane_fcp_sum[lid]
        s[0] += fcp[0]
        s[1] += fcp[1]
        s[2] += 1
    fcp_centroid = {lid: (s[0] / s[2], s[1] / s[2]) for lid, s in lane_fcp_sum.items()}

    def lane_is_dead_end(lane_id):
        return any(node_degree[b] == 1 for b in lane_boundary_nodes[lane_id])

    fcp_lanes = list(fcp_centroid.keys())
    through_ids = [lid for lid in fcp_lanes if not lane_is_dead_end(lid)]
    deadend_ids = [lid for lid in fcp_lanes if lane_is_dead_end(lid)]

    if not through_ids:
        through_ids = fcp_lanes
        deadend_ids = []

    through_order = order_lanes_2d(through_ids, fcp_centroid)
    rank = {lid: float(r) for r, lid in enumerate(through_order)}

    branch_counter = defaultdict(int)
    for lid in deadend_ids:
        nearest_through = min(
            through_ids,
            key=lambda t: math.hypot(fcp_centroid[t][0]-fcp_centroid[lid][0],
                                     fcp_centroid[t][1]-fcp_centroid[lid][1]),
            default=None,
        )
        base = rank[nearest_through] if nearest_through is not None else -1.0
        rank[lid] = base + 0.5 + branch_counter[nearest_through] * 1e-6
        branch_counter[nearest_through] += 1

    return seg_to_lane, node_degree, lane_boundary_nodes, rank


def get_lane_ids_for_fcps(road_segs, all_road_network, fcps):
    """Public helper: lane rank for each FCP's road segment, in order."""
    seg_to_lane, _, _, rank = compute_lane_ranks(all_road_network, road_segs, fcps)

    def lane_id_for(seg):
        key = (min(seg[0], seg[1]), max(seg[0], seg[1]))
        return rank[seg_to_lane[key]]

    return [lane_id_for(seg) for seg in road_segs]


def road_grouped_seed(fcps, road_segs, all_road_network):
    """Build the GA's starting tour: FCPs grouped by lane, lanes visited
    in sweep order, and each dead-end lane spliced in right after the
    through-lane point it's closest to. This gives the GA a sane,
    road-aware starting point instead of a random permutation."""
    n = len(fcps)
    if n <= 1:
        return list(range(n))

    seg_to_lane, node_degree, lane_boundary_nodes, rank = compute_lane_ranks(all_road_network, road_segs, fcps)

    def lane_id_for(seg):
        key = (min(seg[0], seg[1]), max(seg[0], seg[1]))
        return seg_to_lane[key]

    lane_groups = defaultdict(list)
    for idx in range(n):
        lane_groups[lane_id_for(road_segs[idx])].append(idx)

    def lane_is_dead_end(lane_id):
        return any(node_degree[b] == 1 for b in lane_boundary_nodes[lane_id])

    through_groups = {}
    deadend_groups = {}
    for lane_id, indices in lane_groups.items():
        if lane_is_dead_end(lane_id):
            deadend_groups[lane_id] = indices
        else:
            through_groups[lane_id] = indices

    for lane_id in through_groups:
        through_groups[lane_id].sort(key=lambda i: -fcps[i][0])

    sorted_through = sorted(through_groups.keys(), key=lambda lid: rank[lid])

    base_sequence = []
    for lane_id in sorted_through:
        group = through_groups[lane_id][:]
        if base_sequence:
            # Enter the next lane from whichever end is closer, so the
            # seed doesn't zig-zag back across a lane it just finished.
            prev_pt = fcps[base_sequence[-1]]
            first_pt = fcps[group[0]]
            last_pt = fcps[group[-1]]
            dist_first = math.hypot(prev_pt[0]-first_pt[0], prev_pt[1]-first_pt[1])
            dist_last = math.hypot(prev_pt[0]-last_pt[0], prev_pt[1]-last_pt[1])
            if dist_last < dist_first:
                group = group[::-1]
        base_sequence.extend(group)

    if not base_sequence:
        all_indices = list(range(n))
        all_indices.sort(key=lambda i: -fcps[i][0])
        return all_indices

    for lane_id, de_indices in deadend_groups.items():
        boundary = lane_boundary_nodes[lane_id]
        entry_candidates = [b for b in boundary if node_degree[b] > 1]
        entry_pt = entry_candidates[0] if entry_candidates else next(iter(boundary))

        best_pos = 0
        best_dist = float('inf')
        for pos, fcp_idx in enumerate(base_sequence):
            d = math.hypot(fcps[fcp_idx][0] - entry_pt[0], fcps[fcp_idx][1] - entry_pt[1])
            if d < best_dist:
                best_dist = d
                best_pos = pos

        de_sorted = sorted(
            de_indices,
            key=lambda i: math.hypot(fcps[i][0] - entry_pt[0], fcps[i][1] - entry_pt[1])
        )

        insert_at = best_pos + 1
        base_sequence = base_sequence[:insert_at] + de_sorted + base_sequence[insert_at:]

    return base_sequence