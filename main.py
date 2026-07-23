from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pymongo import MongoClient
from bson.objectid import ObjectId 
import bcrypt
import math
from collections import defaultdict
import location 
import routing
import geometry

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE SETUP (MongoDB) ---
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    db = client["palm_opt_system"]
    users_col = db["users"]
    history_col = db["history"]
    client.server_info()
    print("✅ Connected to MongoDB!")
except Exception as e:
    print("⚠️  WARNING: Could not connect to MongoDB. Is it running?")


# --- SERVE THE FRONTEND FILES ---
@app.get("/", response_class=HTMLResponse)
async def get_index():
    return FileResponse("index.html")

@app.get("/script.js")
async def get_script():
    return FileResponse("script.js")


# --- AUTHENTICATION ENDPOINTS ---
@app.post("/register")
async def register_user(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password").encode('utf-8')

    if users_col.find_one({"username": username}):
        return {"error": "Username already exists."}

    hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
    
    users_col.insert_one({
        "username": username,
        "password": hashed_password
    })
    return {"status": "success", "message": "User registered successfully!"}

@app.post("/login")
async def login_user(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password").encode('utf-8')

    user = users_col.find_one({"username": username})
    if not user:
        return {"error": "Invalid username or password."}

    if bcrypt.checkpw(password, user["password"]):
        return {"status": "success", "username": username}
    else:
        return {"error": "Invalid username or password."}


# --- DATABASE HISTORY ENDPOINTS ---
@app.post("/save_analysis")
async def save_analysis(request: Request):
    data = await request.json()
    history_col.insert_one(data)
    return {"status": "success", "message": "Analysis saved to database!"}

@app.get("/history/{username}")
async def get_history(username: str):
    try:
        records = list(history_col.find({"username": username}).sort("_id", -1))
        for r in records:
            r["_id"] = str(r["_id"]) 
        return {"status": "success", "history": records}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/history/{item_id}")
async def delete_history(item_id: str):
    try:
        history_col.delete_one({"_id": ObjectId(item_id)})
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.put("/history/{item_id}")
async def rename_history(item_id: str, request: Request):
    try:
        data = await request.json()
        new_name = data.get("name")
        history_col.update_one({"_id": ObjectId(item_id)}, {"$set": {"custom_name": new_name}})
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}


# --- BASELINE SEQUENCE DISTANCE ENDPOINT ---
@app.post("/compute_sequence_distance")
async def compute_sequence_distance(request: Request):
    try:
        data = await request.json()
        raw_roads = data.get("processed_roads", [])
        raw_fcps  = data.get("fcps", [])
        sequence  = data.get("sequence", [])

        if len(sequence) < 2:
            return {"error": "Sequence must have at least 2 FCPs."}

        roads = [[tuple(pt) for pt in road] for road in raw_roads]
        fcps  = [tuple(pt) for pt in raw_fcps]

        # Re-snap each FCP to its nearest road segment so it joins the graph
        fcp_info = []
        for cx, cy in fcps:
            best_snap, best_seg, min_dist = None, None, float('inf')
            for road in roads:
                for i in range(len(road) - 1):
                    pt1, pt2 = road[i], road[i+1]
                    candidate = location.get_closest_point_on_line((cx, cy), pt1, pt2)
                    dist = math.hypot(candidate[0]-cx, candidate[1]-cy)
                    if dist < min_dist:
                        min_dist = dist
                        best_snap = candidate
                        best_seg  = (pt1, pt2)
            if best_seg:
                fcp_info.append(((cx, cy), best_seg[0], best_seg[1]))

        graph = routing.build_graph(roads, fcp_info)

        total_dist = 0
        for i in range(len(sequence) - 1):
            a, b = fcps[sequence[i]], fcps[sequence[i+1]]
            _, dist = routing.dijkstra(graph, a, b)
            if dist == float('inf'):
                return {"error": f"Cannot route from FCP {sequence[i]+1} to FCP {sequence[i+1]+1}. Ensure all roads are connected."}
            total_dist += dist

        # Close the loop back to the starting FCP
        _, dist_back = routing.dijkstra(graph, fcps[sequence[-1]], fcps[sequence[0]])
        if dist_back == float('inf'):
            return {"error": "Cannot route from last FCP back to first FCP."}
        total_dist += dist_back

        max_walk_m = None
        raw_boundary = data.get("boundary", [])
        if raw_boundary and len(raw_boundary) >= 3 and len(fcps) > 0:
            boundary_pts = [tuple(pt) for pt in raw_boundary]
            fruits = geometry.generate_fruit_grid(boundary_pts,
                                                  target_spacing_m=20.0)
            if fruits:
                max_walk_km = 0
                for f in fruits:
                    min_d = min(geometry.haversine_distance_km(f, c) for c in fcps)
                    if min_d > max_walk_km:
                        max_walk_km = min_d
                max_walk_m = round(max_walk_km * 1000, 1)

        result = {"status": "success", "distance_km": round(total_dist, 3)}
        if max_walk_m is not None:
            result["max_walk_m"] = max_walk_m
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# --- THE OPTIMIZATION ENDPOINT ---
@app.post("/optimize")
async def run_optimization(request: Request):
    try:
        data = await request.json()
        
        raw_boundary = data.get("boundary", [])
        raw_roads = data.get("roads", [])
        num_fcps = data.get("num_fcps", 5)
        mill_coords = data.get("mill", None) 
        
        boundary_points = [tuple(pt) for pt in raw_boundary]
        drawn_roads = [[tuple(pt) for pt in road] for road in raw_roads]
        drawn_roads = geometry.process_crosshatch_roads(drawn_roads)

        SNAP_RADIUS = 0.00005 
        all_nodes = []
        snapped_roads = []

        for road in drawn_roads:
            new_road = []
            for pt in road:
                snapped_pt = pt
                for existing_node in all_nodes:
                    if math.hypot(pt[0]-existing_node[0], pt[1]-existing_node[1]) < SNAP_RADIUS:
                        snapped_pt = existing_node
                        break
                
                if not new_road or snapped_pt != new_road[-1]:
                    new_road.append(snapped_pt)
                    
                if snapped_pt not in all_nodes:
                    all_nodes.append(snapped_pt)
                    
            if len(new_road) > 1:
                snapped_roads.append(new_road)
                
        drawn_roads = snapped_roads

        if not drawn_roads or len(boundary_points) < 3:
            return {"error": "Invalid map data."}

        lats = [p[0] for p in boundary_points]
        lngs = [p[1] for p in boundary_points]
        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)

        FRUIT_SPACING_M = 20.0
        fruits = geometry.generate_fruit_grid(boundary_points,
                                              target_spacing_m=FRUIT_SPACING_M)

        if len(fruits) == 0:
            fruits.append((min_lat + (max_lat-min_lat)/2, min_lng + (max_lng-min_lng)/2))

        # 1. Run K-Means with what the user requested
        clusters_center = location.run_kmeans(fruits, num_fcps)
        
        # 2. Calculate the ACTUAL max walking distance for this layout
        actual_max_walk_km = 0
        for f in fruits:
            min_dist = min((geometry.haversine_distance_km((f[0], f[1]), (c[0], c[1])) / 1.3) for c in clusters_center)
            if min_dist > actual_max_walk_km:
                actual_max_walk_km = min_dist
                
        actual_max_walk_m = round(actual_max_walk_km * 1000, 1) 
        
        # 3. Calculate the "Recommended" FCPs silently in the background
        recommended_fcps = num_fcps
        MAX_WALK_KM = 0.150  # 150 meters maximum walking distance
        
        if actual_max_walk_km > MAX_WALK_KM: 
            temp_k = num_fcps + 1
            
           
            while temp_k <= 50:  
                temp_centers = location.run_kmeans(fruits, temp_k)
                
               
                temp_max_walk = 0
                for f in fruits:
                    dist = min((geometry.haversine_distance_km((f[0], f[1]), (c[0], c[1])) / 1.3) for c in temp_centers)
                    if dist > temp_max_walk:
                        temp_max_walk = dist
                
           
                if temp_max_walk <= MAX_WALK_KM:
                    recommended_fcps = temp_k
                    break
                    
                temp_k += 1
                
           
            else:
                recommended_fcps = ">50 (Max system limit)"

        final_fcps_info = []
        for cx, cy in clusters_center:
            best_internal = None       
            best_perimeter = None      
            for road in drawn_roads:
                for i in range(len(road) - 1):
                    pt1, pt2 = road[i], road[i+1]
                    candidate = location.get_closest_point_on_line((cx, cy), pt1, pt2)
                    dist = math.hypot(candidate[0]-cx, candidate[1]-cy)
                    if geometry.is_perimeter_segment(pt1, pt2, boundary_points):
                        if best_perimeter is None or dist < best_perimeter[0]:
                            best_perimeter = (dist, candidate, (pt1, pt2))
                    else:
                        if best_internal is None or dist < best_internal[0]:
                            best_internal = (dist, candidate, (pt1, pt2))

      
            if best_internal is not None and (
                best_perimeter is None or best_internal[0] <= best_perimeter[0] * 3.0
            ):
                chosen = best_internal
            elif best_perimeter is not None:
                chosen = best_perimeter
            else:
                chosen = best_internal

            if chosen is not None:
                _, best_snap, best_segment = chosen
                final_fcps_info.append((best_snap, best_segment[0], best_segment[1]))

        MERGE_RADIUS_KM = 0.005 
        unique_fcps_with_roads = []

        for info in final_fcps_info:
            candidate_pt = info[0]
            road_seg = (info[1], info[2])   
            is_duplicate = False

            for existing_pt, _ in unique_fcps_with_roads:
                if geometry.haversine_distance_km(candidate_pt, existing_pt) < MERGE_RADIUS_KM:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_fcps_with_roads.append((candidate_pt, road_seg))

        final_fcps      = [pt  for pt, _   in unique_fcps_with_roads]
        fcp_road_segs   = [seg for _,  seg in unique_fcps_with_roads]

        geo_seed = geometry.road_grouped_seed(final_fcps, fcp_road_segs, drawn_roads)

        fcp_lane_ids = geometry.get_lane_ids_for_fcps(fcp_road_segs, drawn_roads, final_fcps)
        
        actual_num_fcps = len(final_fcps)

        if actual_num_fcps < 2:
            return {"error": f"Only found {actual_num_fcps} unique road point(s). Please draw longer/more roads or request fewer FCPs."}
        
        # Routing Math
        graph = routing.build_graph(drawn_roads, final_fcps_info)
        distance_matrix = [[0]*actual_num_fcps for _ in range(actual_num_fcps)]

        # 1. FINISH BUILDING THE MATRIX FIRST
        for i in range(actual_num_fcps):
            for j in range(actual_num_fcps):
                if i != j:
                    path, dist = routing.dijkstra(graph, final_fcps[i], final_fcps[j])
                    if dist == float('inf'):
                        return {"error": f"ROUTING FAILED: Cannot drive from FCP {i+1} to FCP {j+1}. Please ensure all dirt roads are connected together!"}
                    distance_matrix[i][j] = dist

        # 2. RUN THE GENETIC ALGORITHM (AMOS_NECP) with the road-grouped seed
        best_sequence = routing.run_genetic_algorithm(distance_matrix, final_fcps, geo_seed, graph, fcp_lane_ids)

        # 3. LOCAL SEARCH REFINEMENT -- 2-opt then Or-opt (see routing.py).
        best_sequence = routing.two_opt(best_sequence, distance_matrix, final_fcps, graph, fcp_lane_ids)
        best_sequence = routing.or_opt(best_sequence, distance_matrix, final_fcps, graph, fcp_lane_ids)

        estate_entrance_to_return = None
        macro_distance_km = 0
        gate_candidates = []

        if mill_coords is not None and all_nodes:
            gate_candidates = geometry.find_gate_nodes(drawn_roads, boundary_points)
            if not gate_candidates:
                gate_candidates = all_nodes

            entrance_override = data.get("entrance_override", None)
            if entrance_override is not None:
                ov = (entrance_override[0], entrance_override[1])
                estate_entrance_to_return = min(
                    gate_candidates,
                    key=lambda node: geometry.haversine_distance_km(ov, node)
                )
            else:
                estate_entrance_to_return = min(
                    gate_candidates,
                    key=lambda node: geometry.haversine_distance_km(mill_coords, node)
                )
            macro_distance_km = geometry.haversine_distance_km(mill_coords, estate_entrance_to_return)


        if estate_entrance_to_return and best_sequence:
            closest_fcp_idx = 0
            min_dist_to_entrance = float('inf')

            for i in range(len(final_fcps)):
                _, dist = routing.dijkstra(graph, estate_entrance_to_return, final_fcps[i])
                if dist < min_dist_to_entrance:
                    min_dist_to_entrance = dist
                    closest_fcp_idx = i

            sequence_position = best_sequence.index(closest_fcp_idx)
            best_sequence = best_sequence[sequence_position:] + best_sequence[:sequence_position]


        # --- 3. BUILD THE COMPLETE SEAMLESS PATH ---
        total_degree_distance = 0
        truck_path_nodes = []
        segment_breakdown = []

        if best_sequence:
            first_fcp = final_fcps[best_sequence[0]]
            last_fcp = final_fcps[best_sequence[-1]]

            # Segment A: Drive from Entrance to FCP 1
            if estate_entrance_to_return:
                path_in, dist_in = routing.dijkstra(graph, estate_entrance_to_return, first_fcp)
                truck_path_nodes.extend(path_in)
                total_degree_distance += dist_in
                segment_breakdown.append({
                    "distance_km": round(dist_in, 2),
                    "label": "Entrance to FCP 1"
                })

            # Segment B: Drive between all FCPs
            for i in range(len(best_sequence) - 1):
                start_idx = best_sequence[i]
                end_idx = best_sequence[i+1]
                
                start = final_fcps[start_idx]
                end = final_fcps[end_idx]
                
                path, dist = routing.dijkstra(graph, start, end)
                truck_path_nodes.extend(path)
                total_degree_distance += dist
                
                segment_breakdown.append({
                    "distance_km": round(dist, 2),
                    "label": f"FCP {i+1} to FCP {i+2}"
                })

            # Segment C: Drive from Last FCP back to the Entrance
            if estate_entrance_to_return:
                path_out, dist_out = routing.dijkstra(graph, last_fcp, estate_entrance_to_return)
                truck_path_nodes.extend(path_out)
                total_degree_distance += dist_out
                segment_breakdown.append({
                    "distance_km": round(dist_out, 2),
                    "label": f"FCP {len(best_sequence)} to Entrance"
                })
            else:
                path, dist = routing.dijkstra(graph, last_fcp, first_fcp)
                truck_path_nodes.extend(path)
                total_degree_distance += dist
                segment_breakdown.append({
                    "distance_km": round(dist, 2),
                    "label": f"FCP {len(best_sequence)} to FCP 1"
                })

        if estate_entrance_to_return:
            segment_breakdown.append({
                "distance_km": round(macro_distance_km, 2),
                "label": "Estate Exit to Mill"
            })

        # Calculate Final Totals (Internal Dirt Roads + Public Highway Round Trip)
        total_km = total_degree_distance + (macro_distance_km * 2)
        total_time_mins = (total_km / 20.0) * 60

        return {
            "status": "success",
            "fruits": fruits,
            "fcps": final_fcps,
            "sequence": best_sequence,
            "path": truck_path_nodes,
            "segments": segment_breakdown,
            "boundary": raw_boundary,
            "processed_roads": [[[pt[0], pt[1]] for pt in road] for road in drawn_roads],
            "estate_entrance": estate_entrance_to_return,
            "gate_candidates": gate_candidates,
            "metrics": {
                "distance_km": round(total_km, 2),
                "time_mins": round(total_time_mins, 1),
                "actual_max_walk_m": actual_max_walk_m, 
                "recommended_fcps": recommended_fcps  
            }
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"PYTHON MATH CRASH: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)