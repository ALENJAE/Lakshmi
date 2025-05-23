import streamlit as st
import networkx as nx
import json
import os
import qrcode
from PIL import Image
from pathlib import Path
import tempfile

from streamlit_agraph import agraph, Node, Edge, Config
from streamlit_qrcode_scanner import qrcode_scanner

import numpy as np
import cv2

# Configuration
SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "nav_data.json"
IMAGE_DIR = SCRIPT_DIR / "node_images"
QR_DIR = SCRIPT_DIR / "qrcodes"

# Create directories if they don't exist
IMAGE_DIR.mkdir(exist_ok=True)
QR_DIR.mkdir(exist_ok=True)

def delete_node():
    st.subheader("Delete Node")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if not nodes:
        st.warning("No nodes available to delete")
        return
    
    node_to_delete = st.selectbox("Select Node to Delete", nodes)
    
    if st.button("Delete Node"):
        # Remove associated QR code
        qr_path = QR_DIR / f"{node_to_delete}.png"
        if qr_path.exists():
            qr_path.unlink()
        
        # Remove node from nodes
        del st.session_state.nav_data['nodes'][node_to_delete]
        
        # Remove all connections involving this node
        connections = list(st.session_state.nav_data['connections'].items())
        for conn, details in connections:
            if node_to_delete in conn.split("::")[0] or node_to_delete in conn.split("::")[-1]:
                del st.session_state.nav_data['connections'][conn]
        
        save_data(st.session_state.nav_data)
        st.success(f"Node {node_to_delete} and all associated connections deleted!")
        st.rerun()

def delete_path():
    st.subheader("Delete Path from Node")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if not nodes:
        st.warning("No nodes available")
        return
    
    node = st.selectbox("Select Node", nodes)
    paths = st.session_state.nav_data['nodes'][node]
    
    if not paths:
        st.warning("No paths available in selected node")
        return
    
    # Show path labels instead of keys
    path_options = [(f"{idx+1}. {path_data['label']}", path_key) 
                    for idx, (path_key, path_data) in enumerate(paths.items())]
    
    selected_path = st.selectbox("Select Path to Delete", 
                               options=[opt[0] for opt in path_options],
                               format_func=lambda x: x)
    path_to_delete = next(opt[1] for opt in path_options if opt[0] == selected_path)
    
    if st.button("Delete Path"):
        # Remove path from node
        del st.session_state.nav_data['nodes'][node][path_to_delete]
        
        # Remove all connections using this path
        connections = list(st.session_state.nav_data['connections'].items())
        for conn, details in connections:
            if f"{node}::{path_to_delete}" in conn:
                del st.session_state.nav_data['connections'][conn]
        
        save_data(st.session_state.nav_data)
        st.success(f"Path '{paths[path_to_delete]['label']}' deleted from {node}!")
        st.rerun()

def delete_link():
    st.subheader("Delete Connection Between Nodes")
    connections = list(st.session_state.nav_data['connections'].items())
    if not connections:
        st.warning("No connections available")
        return
    
    # Create display-friendly connection list with labels
    connection_list = []
    for conn, details in connections:
        source = details['from']
        path_key = details['path_key']
        target = details['to']
        path_label = st.session_state.nav_data['nodes'][source][path_key]['label']
        connection_list.append(f"{source} ({path_label}) ➔ {target}")
    
    selected_conn = st.selectbox("Select Connection to Delete", connection_list)
    conn_index = connection_list.index(selected_conn)
    conn_key = list(st.session_state.nav_data['connections'].keys())[conn_index]
    
    if st.button("Delete Connection"):
        del st.session_state.nav_data['connections'][conn_key]
        save_data(st.session_state.nav_data)
        st.success(f"Connection '{selected_conn}' deleted successfully!")
        st.rerun()


# Initialize session state
def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"nodes": {}, "connections": {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

if 'nav_data' not in st.session_state:
    st.session_state.nav_data = load_data()
if 'selected_node' not in st.session_state:
    st.session_state.selected_node = None

# QR Code Generation
def generate_qr(node_name):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(node_name)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_path = QR_DIR / f"{node_name}.png"
    img.save(qr_path)
    return str(qr_path)

# Image Upload Handler
def handle_image_upload(field_key, existing_images):
    uploaded_files = st.file_uploader(f"Upload images for {field_key}", accept_multiple_files=True, key=f"img_{field_key}")
    img_paths = existing_images if existing_images else []
    if uploaded_files:
        for uploaded_file in uploaded_files:
            img_path = IMAGE_DIR / uploaded_file.name
            with open(img_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            if str(img_path) not in img_paths:
                img_paths.append(str(img_path))
    return img_paths

# Node Management
def handle_node_creation():
    st.subheader("Node Editor")
    existing_nodes = list(st.session_state.nav_data['nodes'].keys())
    selected_node = st.selectbox("Select Node", [""] + existing_nodes)
    
    node_name = st.text_input("Node Name", value=selected_node or "")
    num_fields = st.number_input(
        "Number of Paths", 1, 10,
        value=len(st.session_state.nav_data['nodes'].get(selected_node, {})) if selected_node else 1
    )

    fields = {}
    if selected_node:
        fields = st.session_state.nav_data['nodes'][selected_node].copy()
    
    for i in range(1, int(num_fields)+1):
        field_key = f"path_{i}"
        with st.expander(f"Path {i}", expanded=True):
            fields[field_key] = {
                'label': st.text_input(f"Label for {field_key}", value=fields.get(field_key, {}).get('label', ''), key=f"label_{field_key}"),
                'distance': st.number_input(f"Distance (ft) for {field_key}", value=fields.get(field_key, {}).get('distance', 0), key=f"dist_{field_key}"),
                'instruction': st.text_area(f"Instruction for {field_key}", value=fields.get(field_key, {}).get('instruction', ''), key=f"instr_{field_key}"),
                'images': handle_image_upload(field_key, fields.get(field_key, {}).get('images', [])),
                'landmark': st.text_input(f"Nearby Landmark for {field_key}", value=fields.get(field_key, {}).get('landmark', ''), key=f"landmark_{field_key}")
            }
    
    if st.button("Save Node"):
        if selected_node and selected_node != node_name:
            del st.session_state.nav_data['nodes'][selected_node]
        st.session_state.nav_data['nodes'][node_name] = fields
        generate_qr(node_name)  # Generate/update QR code
        save_data(st.session_state.nav_data)
        st.success("Node saved!")
        st.rerun()

# Node Linking
def handle_node_linking():
    st.subheader("Link Nodes")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if len(nodes) < 2:
        st.info("At least two nodes are needed to create a link.")
        return
    
    # Source node selection
    source = st.selectbox("Source Node", nodes, key="link_source")
    
    # Get path labels for source node
    source_paths = st.session_state.nav_data['nodes'][source]
    path_options = [(f"{idx+1}. {path_data['label']}", path_key) 
                    for idx, (path_key, path_data) in enumerate(source_paths.items())]
    
    # Show labels instead of path keys
    selected_path = st.selectbox("Select Path from Source", 
                               options=[opt[0] for opt in path_options],
                               format_func=lambda x: x)
    path_key = next(opt[1] for opt in path_options if opt[0] == selected_path)
    
    # Target node selection
    target = st.selectbox("Target Node", [n for n in nodes if n != source], key="link_target")
    
    if st.button("Create Link"):
        conn_key = f"{source}::{path_key}::{target}"
        st.session_state.nav_data['connections'][conn_key] = {
            "from": source,
            "to": target,
            "path_key": path_key
        }
        save_data(st.session_state.nav_data)
        st.success(f"Link created from {source} ({source_paths[path_key]['label']}) to {target}")
        st.rerun()


# QR Scanner using streamlit_qrcode_scanner
def qr_scanner():
    st.subheader("QR Scanner")
    qr_code = qrcode_scanner(key='qrcode_scanner',box_size = 800)
    if qr_code:
        node_name = qr_code
        if node_name in st.session_state.nav_data['nodes']:
            st.session_state.selected_node = node_name
            st.success(f"Scanned Node: {node_name}")
            return node_name
        else:
            st.error("Scanned node not found in database.")
    return None

# Navigation Display
def display_navigation(path):
    for i in range(len(path)-1):
        current = path[i]
        next_node = path[i+1]
        connection = None
        path_key = None
        for conn, details in st.session_state.nav_data['connections'].items():
            source, pkey, target = conn.split("::")
            if source == current and target == next_node:
                connection = details
                path_key = pkey
                break
        if connection and path_key:
            node_data = st.session_state.nav_data['nodes'][current][path_key]
            col1, col2 = st.columns([1, 2])
            with col1:
                st.subheader(f"Step {i+1}")
                if node_data['images']:
                    img = Image.open(node_data['images'][0])
                    st.image(img, caption=node_data['label'])
                else:
                    st.warning("No image available")
            with col2:
                st.markdown(f"""
                **From:** {current}  
                **To:** {next_node}  
                **Instruction:** {node_data['instruction']}  
                **Distance:** {node_data['distance']} ft  
                **Landmark:** {node_data['landmark']}  
                """)
            st.markdown("---")

# Path Finding with weight calculation
def find_path_with_weight(start, end):
    G = nx.DiGraph()
    # Add nodes
    for node in st.session_state.nav_data['nodes']:
        G.add_node(node)
    # Add edges with weights
    for conn, details in st.session_state.nav_data['connections'].items():
        source = details['from']
        target = details['to']
        path_key = details['path_key']
        distance = st.session_state.nav_data['nodes'][source][path_key]['distance']
        G.add_edge(source, target, weight=distance, path_key=path_key)
    
    try:
        path = nx.shortest_path(G, start, end, weight='weight')
        total_distance = nx.shortest_path_length(G, start, end, weight='weight')
        return path, total_distance, G
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None, 0, G

# Path Finding (original for backward compatibility)
def find_path(start, end):
    path, _, _ = find_path_with_weight(start, end)
    return path

# Path visualization with highlighted route and weights
def show_path_graph_with_weights(path, total_distance):
    st.subheader(f"Navigation Path (Total Distance: {total_distance:.1f} ft)")
    
    # Create nodes - highlight path nodes
    nodes = []
    for node_name in st.session_state.nav_data['nodes']:
        if node_name in path:
            if node_name == path[0]:
                nodes.append(Node(id=node_name, label=f"{node_name}\n(START)", color="#4CAF50", size=25))
            elif node_name == path[-1]:
                nodes.append(Node(id=node_name, label=f"{node_name}\n(END)", color="#F44336", size=25))
            else:
                nodes.append(Node(id=node_name, label=node_name, color="#FF9800", size=20))
        else:
            nodes.append(Node(id=node_name, label=node_name, color="#9E9E9E", size=15))
    
    # Create edges - highlight path edges
    edges = []
    path_edges = set()
    
    # Get path edges
    for i in range(len(path)-1):
        path_edges.add((path[i], path[i+1]))
    
    for conn, details in st.session_state.nav_data['connections'].items():
        source = details['from']
        target = details['to']
        path_key = details['path_key']
        distance = st.session_state.nav_data['nodes'][source][path_key]['distance']
        
        if (source, target) in path_edges:
            # Highlight path edges
            edges.append(Edge(source=source, target=target, 
                            label=f"{distance} ft", color="#2196F3", width=5))
        else:
            # Regular edges
            edges.append(Edge(source=source, target=target, 
                            label=f"{distance} ft", color="#757575", width=2))
    
    config = Config(height=600, width=800, directed=True, 
                   physics={'enabled': True, 'stabilization': {'iterations': 100}})
    
    if nodes:
        agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.info("No nodes to display.")

# Simple Graph Visualization
def show_graph():
    st.subheader("Node Network Graph (Simple)")
    G = nx.DiGraph()
    for node in st.session_state.nav_data['nodes']:
        G.add_node(node)
    for conn, details in st.session_state.nav_data['connections'].items():
        source = details['from']
        target = details['to']
        G.add_edge(source, target)
    if G.number_of_nodes() > 0:
        dot_str = nx.nx_pydot.to_pydot(G).to_string()
        st.graphviz_chart(dot_str)
    else:
        st.info("No nodes to display.")

# Interactive Graph Visualization with weights
def show_interactive_graph():
    st.subheader("Interactive Node Graph with Distances")
    nodes = [Node(id=n, label=n) for n in st.session_state.nav_data['nodes']]
    edges = []
    for conn, details in st.session_state.nav_data['connections'].items():
        source = details['from']
        target = details['to']
        path_key = details['path_key']
        distance = st.session_state.nav_data['nodes'][source][path_key]['distance']
        edges.append(Edge(source=source, target=target, label=f"{distance} ft"))
    config = Config(height=500, width=700, directed=True)
    if nodes:
        agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.info("No nodes to display.")

# Main Application
def main():
    st.sidebar.title("Smart Campus Navigator")
    mode = st.sidebar.radio("Mode", ["User", "Admin"])
    
    if mode == "Admin":
        st.title("System Administration")
        
        admin_action = st.selectbox(
            "Select Action",
            ["Create Node", "Link Nodes", "Delete Node", "Delete Path", "Delete Connection"]
        )
        
        if admin_action == "Create Node":
            handle_node_creation()
        elif admin_action == "Link Nodes":
            handle_node_linking()
        elif admin_action == "Delete Node":
            delete_node()
        elif admin_action == "Delete Path":
            delete_path()
        elif admin_action == "Delete Connection":
            delete_link()
        
        st.markdown("---")
        show_graph()
        st.markdown("---")
        show_interactive_graph()

    else:
        st.title("Campus Navigation")
        node_keys = list(st.session_state.nav_data['nodes'].keys())
        
        if not node_keys:
            st.info("No nodes available. Please add nodes in Admin mode.")
            return
        
        # User mode selection
        user_mode = st.radio("Navigation Mode", ["QR Scanner Mode", "Manual Selection Mode"])
        
        if user_mode == "QR Scanner Mode":
            # Step 1: Scan QR code for source node
            st.subheader("Step 1: Scan QR Code for Source Node")
            qr_code = qrcode_scanner()

            if qr_code:
                if qr_code in node_keys:
                    st.session_state.selected_node = qr_code
                    st.success(f"Source node detected: {qr_code}")
                else:
                    st.error("Scanned QR does not match any node.")

            # Step 2: If source is set, allow destination selection
            if st.session_state.selected_node:
                source = st.session_state.selected_node
                st.info(f"Source: {source}")
                destination_options = [n for n in node_keys if n != source]
                if not destination_options:
                    st.warning("No other nodes available as destination.")
                    return
                destination = st.selectbox("Step 2: Select Destination Node", destination_options)
                
                if st.button("Get Directions"):
                    path, total_distance, G = find_path_with_weight(source, destination)
                    if path:
                        st.success(f"Path found! Total distance: {total_distance:.1f} feet")
                        
                        # Show path visualization with weights
                        show_path_graph_with_weights(path, total_distance)
                        
                        st.markdown("---")
                        # Show detailed navigation instructions
                        st.subheader("Step-by-Step Navigation")
                        display_navigation(path)
                    else:
                        st.error("No path found")
            else:
                st.info("Please scan a QR code to set the source node.")

        else:  # Manual Selection Mode
            st.subheader("Manual Navigation")
            col1, col2 = st.columns(2)
            
            with col1:
                source = st.selectbox("Select Source Node", node_keys, key="manual_source")
            
            with col2:
                destination_options = [n for n in node_keys if n != source]
                destination = st.selectbox("Select Destination Node", destination_options, key="manual_destination")
            
            if st.button("Get Directions", key="manual_directions"):
                path, total_distance, G = find_path_with_weight(source, destination)
                if path:
                    st.success(f"Path found! Total distance: {total_distance:.1f} feet")
                    
                    # Show path visualization with weights
                    show_path_graph_with_weights(path, total_distance)
                    
                    st.markdown("---")
                    # Show detailed navigation instructions
                    st.subheader("Step-by-Step Navigation")
                    display_navigation(path)
                else:
                    st.error("No path found")
        
        # Always show full network graph at the bottom
        st.markdown("---")
        show_interactive_graph()


if __name__ == "__main__":
    main()
