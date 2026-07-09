import matplotlib.pyplot as plt
import random

def calculate_route_distance(route, distance_matrix):
    total_dist = 0.0
    for i in range(len(route)):
        total_dist += distance_matrix[route[i]][route[(i + 1) % len(route)]]
    return total_dist

def ordered_crossover(p1, p2):
    size = len(p1)
    start, end = sorted(random.sample(range(size), 2))
    child = [-1] * size
    child[start:end+1] = p1[start:end+1]
    p2_idx = 0
    for i in range(size):
        if child[i] == -1:
            while p2[p2_idx] in child: p2_idx += 1
            child[i] = p2[p2_idx]
    return child

def mutate(route):
    # Increased mutation rate slightly to keep the "search" active
    if random.random() < 0.3:
        idx1, idx2 = random.sample(range(len(route)), 2)
        route[idx1], route[idx2] = route[idx2], route[idx1]
    return route

def run_convergence_simulation(num_nodes, seed_val, filename):
    random.seed(seed_val) # Consistency for your thesis!
    pop_size = 50 
    generations = 500
    # Increased range (10 to 100) to make the differences between paths more distinct
    matrix = [[random.uniform(10, 100) for _ in range(num_nodes)] for _ in range(num_nodes)]
    
    current_pop = [random.sample(range(num_nodes), num_nodes) for _ in range(pop_size)]
    best_distances = []

    print(f"🚀 Running Convergence for {num_nodes} nodes...")

    for gen in range(generations):
        pop_with_scores = [(r, calculate_route_distance(r, matrix)) for r in current_pop]
        pop_with_scores.sort(key=lambda x: x[1])
        best_distances.append(pop_with_scores[0][1])
        
        next_gen = [pop_with_scores[0][0]]
        while len(next_gen) < pop_size:
            p1 = random.choice(pop_with_scores[:25])[0]
            p2 = random.choice(pop_with_scores[:25])[0]
            next_gen.append(mutate(ordered_crossover(p1, p2)))
        current_pop = next_gen

    plt.figure(figsize=(8, 5))
    plt.plot(range(generations), best_distances, color='#dc2626', linewidth=2)
    plt.title(f'GA Convergence: {num_nodes} Nodes (Case Study)', fontsize=14, fontweight='bold')
    plt.xlabel('Generation', fontsize=12)
    plt.ylabel('Total Route Distance (km)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Graph saved: {filename}")

if __name__ == "__main__":
    # Case Study 1: Smallholder (Let's use 10 nodes to see the 'drop')
    run_convergence_simulation(10, 42, 'Smallholder_Convergence.png')
    
    # Case Study 2: Industrial (Let's use 20 nodes to see the 'drop')
    run_convergence_simulation(20, 42, 'Industrial_Convergence.png')