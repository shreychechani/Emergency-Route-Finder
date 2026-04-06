from markupsafe import Markup
from flask import Flask, render_template, request, jsonify
import osmnx as ox
import folium
from geopy.geocoders import Nominatim
import heapq
import random
import pickle
import os

app = Flask(__name__)


def initialize_data(cache_file="hospitals_cache.pkl"):
    if os.path.exists(cache_file):
        try:
            print("Loading cached data from file...")
            with open(cache_file, 'rb') as f:
                G, hospital_nodes, hospital_coords = pickle.load(f)
            print("Cached data loaded successfully.")
        except Exception as e:
            print(f"Error loading cache file: {e}. Fetching fresh data...")
            G, hospital_nodes, hospital_coords = fetch_fresh_data(cache_file)
    else:
        print("Cache file not found. Fetching fresh data...")
        G, hospital_nodes, hospital_coords = fetch_fresh_data(cache_file)
    return G, hospital_nodes, hospital_coords


def fetch_fresh_data(cache_file):
    G = ox.graph_from_place("Jaipur, Rajasthan, India", network_type="drive")
    hospitals = ox.features_from_place("Jaipur, Rajasthan, India", tags={"amenity": "hospital"})

    hospital_nodes = []
    hospital_coords = {}

    for _, row in hospitals.iterrows():
        if row.geometry.geom_type in ["Point", "Polygon"]:
            lat, lon = row.geometry.centroid.y, row.geometry.centroid.x
            try:
                node = ox.nearest_nodes(G, lon, lat)
                hospital_nodes.append(node)
                hospital_coords[node] = (lat, lon)
            except Exception:
                continue

    with open(cache_file, 'wb') as f:
        pickle.dump((G, hospital_nodes, hospital_coords), f)

    print("Data cached successfully.")
    return G, hospital_nodes, hospital_coords



def dijkstra(G, source, traffic, speed_base=30):
    dist = {node: float('inf') for node in G}
    dist[source] = 0
    predecessors = {node: None for node in G}

    queue = [(0, source)]
    visited = set()

    while queue:
        time_u, u = heapq.heappop(queue)

        if u in visited:
            continue
        visited.add(u)

        for v in G.neighbors(u):
            edge = (u, v)
            edge_speed = speed_base

            if edge in traffic:
                if traffic[edge] == 'medium':
                    edge_speed *= 0.5
                elif traffic[edge] == 'high':
                    edge_speed *= 0.3

            distance = G[u][v][0].get('length', 1)
            travel_time = (distance / 1000) / edge_speed
            new_time = time_u + travel_time

            if new_time < dist[v]:
                dist[v] = new_time
                predecessors[v] = u
                heapq.heappush(queue, (new_time, v))

    return dist, predecessors


def reconstruct_path(predecessors, source, target):
    if target not in predecessors or predecessors[target] is None:
        return None

    path = []
    current = target

    while current is not None and current != source:
        path.append(current)
        current = predecessors[current]

    if current == source:
        path.append(source)
        path.reverse()
        return path

    return None


def simulate_traffic(G):
    traffic_levels = ['low', 'medium', 'high']
    traffic = {}

    for u, v in G.edges():
        traffic[(u, v)] = random.choice(traffic_levels)

    return traffic



def get_location_coordinates(place_name):
    geolocator = Nominatim(user_agent="emergency_route_finder", timeout=10)
    location = geolocator.geocode(place_name + ", Jaipur, Rajasthan, India")

    if not location:
        return None

    return (location.latitude, location.longitude)


def analyze_traffic_path(G, path, traffic):
    if not path or len(path) < 2:
        return 0, "No traffic data"

    high_traffic_count = 0
    total_edges = len(path) - 1

    for i in range(len(path) - 1):
        edge = (path[i], path[i + 1])
        if edge in traffic and traffic[edge] == 'high':
            high_traffic_count += 1

    traffic_percentage = (high_traffic_count / total_edges) * 100 if total_edges > 0 else 0
    traffic_status = "High Traffic Route" if traffic_percentage > 30 else "Low Traffic Route"

    return traffic_percentage, traffic_status



def compute_emergency_route(accident_site):
    print("Starting route computation for:", accident_site)

    G, hospital_nodes, hospital_coords = initialize_data()

    accident_coords = get_location_coordinates(accident_site)
    if not accident_coords:
        return None, "Invalid location. Please enter a valid place in Jaipur."

    accident_node = ox.nearest_nodes(G, accident_coords[1], accident_coords[0])

    traffic = simulate_traffic(G)
    dist, predecessors = dijkstra(G, accident_node, traffic)

    hospital_times = [(h, dist[h]) for h in hospital_nodes if h in dist and dist[h] != float('inf')]

    if not hospital_times:
        return None, "No accessible hospitals found."

    hospital_times.sort(key=lambda x: x[1])
    nearest_hospital, nearest_time = hospital_times[0]

    nearest_path = reconstruct_path(predecessors, accident_node, nearest_hospital)

    if not nearest_path:
        return None, "No valid path to the nearest hospital."

    initial_traffic_percentage, initial_traffic_status = analyze_traffic_path(G, nearest_path, traffic)

    m = folium.Map(location=accident_coords, zoom_start=13)

    folium.Marker(accident_coords, icon=folium.Icon(color="blue"), popup="Accident Site").add_to(m)

    # Initial route
    lat, lon = hospital_coords[nearest_hospital]
    folium.Marker((lat, lon), icon=folium.Icon(color="red"),
                  popup=f"{initial_traffic_status}: {nearest_time*3600:.1f}s").add_to(m)

    path_coords = [(G.nodes[node]['y'], G.nodes[node]['x']) for node in nearest_path]
    folium.PolyLine(path_coords, color="red", weight=5, opacity=0.8).add_to(m)

    # Alternative route logic
    if initial_traffic_percentage > 30 and len(hospital_times) > 1:
        alternative_hospital, alternative_time = hospital_times[1]
        alternative_path = reconstruct_path(predecessors, accident_node, alternative_hospital)

        if alternative_path:
            alt_traffic_percentage, alt_status = analyze_traffic_path(G, alternative_path, traffic)

            if alt_traffic_percentage <= 30:
                lat, lon = hospital_coords[alternative_hospital]

                folium.Marker((lat, lon), icon=folium.Icon(color="green"),
                              popup=f"{alt_status}: {alternative_time*3600:.1f}s").add_to(m)

                path_coords = [(G.nodes[node]['y'], G.nodes[node]['x']) for node in alternative_path]
                folium.PolyLine(path_coords, color="green", weight=5, opacity=0.8).add_to(m)

    try:
        map_html = m._repr_html_()
    except Exception as e:
        return "Error generating map", str(e)

    return initial_traffic_status, map_html


# -------------------- ROUTES --------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/compute_route', methods=['POST'])
def compute_route():
    accident_site = request.form['accident_site']

    try:
        traffic_status, map_html = compute_emergency_route(accident_site)

        if isinstance(map_html, str) and map_html.startswith("Error"):
            return jsonify({'error': map_html})

        return jsonify({'map_html': map_html, 'traffic_status': traffic_status})

    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)