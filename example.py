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

# Enhanced QR Scanner with mobile-friendly features
def enhanced_qr_scanner():
    st.subheader("📱 QR Scanner")
    
    # Add custom CSS for mobile optimization
    st.markdown("""
    <style>
    .qr-scanner-container {
        width: 100%;
        max-width: 100vw;
        height: 70vh;
        position: relative;
        border-radius: 15px;
        overflow: hidden;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    
    .scanner-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.5);
        z-index: 10;
        pointer-events: none;
    }
    
    .scanner-frame {
        position: absolute;
        top: 15%;
        left: 10%;
        right: 10%;
        bottom: 15%;
        border: 3px solid #00ff00;
        border-radius: 20px;
        box-shadow: 0 0 0 9999px rgba(0,0,0,0.5);
        animation: scanner-pulse 2s infinite;
    }
    
    @keyframes scanner-pulse {
        0% { border-color: #00ff00; }
        50% { border-color: #00aa00; }
        100% { border-color: #00ff00; }
    }
    
    .scanner-corners {
        position: absolute;
        width: 50px;
        height: 50px;
        border: 4px solid #00ff00;
    }
    
    .corner-tl { top: -2px; left: -2px; border-right: none; border-bottom: none; }
    .corner-tr { top: -2px; right: -2px; border-left: none; border-bottom: none; }
    .corner-bl { bottom: -2px; left: -2px; border-right: none; border-top: none; }
    .corner-br { bottom: -2px; right: -2px; border-left: none; border-top: none; }
    
    .zoom-controls {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 20;
        display: flex;
        gap: 10px;
        background: rgba(0,0,0,0.7);
        padding: 10px;
        border-radius: 25px;
    }
    
    .zoom-btn {
        background: rgba(255,255,255,0.2);
        border: 2px solid white;
        color: white;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        font-size: 20px;
        cursor: pointer;
        transition: all 0.3s;
    }
    
    .zoom-btn:hover {
        background: rgba(255,255,255,0.4);
    }
    
    .scanner-instructions {
        position: absolute;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        color: white;
        text-align: center;
        background: rgba(0,0,0,0.7);
        padding: 10px 20px;
        border-radius: 20px;
        z-index: 20;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize zoom level in session state
    if 'zoom_level' not in st.session_state:
        st.session_state.zoom_level = 1.0
    
    # Zoom controls
    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
    
    with col1:
        if st.button("🔍➖", help="Zoom Out"):
            st.session_state.zoom_level = max(0.5, st.session_state.zoom_level - 0.2)
            st.rerun()
    
    with col2:
        if st.button("🔍➕", help="Zoom In"):
            st.session_state.zoom_level = min(3.0, st.session_state.zoom_level + 0.2)
            st.rerun()
    
    with col3:
        if st.button("🎯", help="Reset Zoom"):
            st.session_state.zoom_level = 1.0
            st.rerun()
    
    with col4:
        if st.button("🔦", help="Toggle Flash"):
            st.info("Flash toggle requested")
    
    with col5:
        st.write(f"Zoom: {st.session_state.zoom_level:.1f}x")
    
    # Display current zoom level
    st.info(f"📱 Camera Zoom: {st.session_state.zoom_level:.1f}x | Point camera at QR code within the green frame")
    
    # Enhanced QR scanner with larger box and mobile optimization
    qr_code = qrcode_scanner(
        key='enhanced_qrcode_scanner',
        # Significantly larger box size for mobile
        box_size=min(st.session_state.get('window_width', 800), 600),
        # Enhanced scanner parameters
        fps_limit=30,
        torch=False,  # Flash control
        # Custom styling for mobile
        style={
            'width': '100%',
            'height': '70vh',
            'border-radius': '15px',
            'border': '3px solid #4CAF50',
            'box-shadow': '0 4px 20px rgba(0,0,0,0.3)'
        }
    )
    
    # Add scanning overlay effect
    st.markdown("""
    <div class="scanner-overlay">
        <div class="scanner-frame">
            <div class="scanner-corners corner-tl"></div>
            <div class="scanner-corners corner-tr"></div>
            <div class="scanner-corners corner-bl"></div>
            <div class="scanner-corners corner-br"></div>
        </div>
        <div class="scanner-instructions">
            <div>📱 Hold phone steady</div>
            <div>🎯 Align QR code in green frame</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if qr_code:
        node_name = qr_code
        if node_name in st.session_state.nav_data['nodes']:
            st.session_state.selected_node = node_name
            st.success(f"✅ Scanned Node: {node_name}")
            st.balloons()  # Celebration effect
            return node_name
        else:
            st.error("❌ Scanned QR code not found in database.")
            st.info("💡 Make sure you're scanning a valid campus navigation QR code")
    
    return None

# Alternative mobile-optimized QR scanner function
def mobile_qr_scanner():
    """Mobile-optimized QR scanner with full-screen experience"""
    st.subheader("📱 Mobile QR Scanner")
    
    # Add JavaScript for mobile optimization
    st.markdown("""
    <script>
    // Mobile optimization script
    function optimizeForMobile() {
        // Get screen dimensions
        const screenWidth = window.screen.width;
        const screenHeight = window.screen.height;
        
        // Set scanner size based on screen
        const scannerSize = Math.min(screenWidth * 0.9, screenHeight * 0.6);
        
        // Store in session for Python access
        window.parent.postMessage({
            type: 'screenInfo',
            width: screenWidth,
            height: screenHeight,
            scannerSize: scannerSize
        }, '*');
    }
    
    // Call on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', optimizeForMobile);
    } else {
        optimizeForMobile();
    }
    </script>
    """, unsafe_allow_html=True)
    
    # Mobile-specific controls
    st.markdown("### 📱 Camera Controls")
    
    # Create responsive layout
    control_cols = st.columns([2, 2, 2, 2])
    
    with control_cols[0]:
        zoom_out = st.button("🔍➖ Zoom Out", use_container_width=True)
    with control_cols[1]:
        zoom_in = st.button("🔍➕ Zoom In", use_container_width=True)
    with control_cols[2]:
        reset_zoom = st.button("🎯 Reset", use_container_width=True)
    with control_cols[3]:
        toggle_flash = st.button("🔦 Flash", use_container_width=True)
    
    # Handle zoom controls
    if zoom_out:
        st.session_state.zoom_level = max(0.5, st.session_state.get('zoom_level', 1.0) - 0.25)
    if zoom_in:
        st.session_state.zoom_level = min(4.0, st.session_state.get('zoom_level', 1.0) + 0.25)
    if reset_zoom:
        st.session_state.zoom_level = 1.0
    
    # Display zoom level
    zoom_level = st.session_state.get('zoom_level', 1.0)
    st.info(f"🔍 Current Zoom: {zoom_level:.1f}x")
    
    # Enhanced scanner with mobile-first approach
    scanner_container = st.container()
    
    with scanner_container:
        # Use larger box size for mobile
        mobile_box_size = 800  # Increased from default
        
        qr_code = qrcode_scanner(
            key='mobile_qr_scanner',
            box_size=mobile_box_size,
            fps_limit=24,  # Optimized for mobile
            torch=st.session_state.get('flash_enabled', False)
        )
        
        # Add mobile-friendly instructions
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 15px;
            border-radius: 10px;
            color: white;
            text-align: center;
            margin: 10px 0;
        ">
            <h4>📱 Scanning Instructions</h4>
            <p>• Hold your phone steady</p>
            <p>• Point camera at QR code</p>
            <p>• Move closer or farther to focus</p>
            <p>• Use zoom controls if needed</p>
        </div>
        """, unsafe_allow_html=True)
    
    return qr_code

# QR Scanner using streamlit_qrcode_scanner
def qr_scanner():
    """Enhanced QR Scanner - use this to replace the original function"""
    return enhanced_qr_scanner()

def is_mobile_device():
    """Detect if user is on mobile device"""
    # This would typically use user agent detection in a real app
    # For Streamlit, we can use JavaScript or assume mobile based on screen size
    return True  # Assume mobile for enhanced experience

# Custom CSS injection function for mobile optimization
def inject_mobile_css():
    """Inject mobile-optimized CSS"""
    st.markdown("""
    <style>
    /* Mobile-first responsive design */
    @media (max-width: 768px) {
        .stButton > button {
            width: 100%;
            padding: 12px;
            font-size: 16px;
            margin: 5px 0;
        }
        
        .stSelectbox > div > div {
            font-size: 16px;
        }
        
        /* Make QR scanner full width on mobile */
        .stCamera > div {
            width: 100% !important;
            max-width: none !important;
        }
        
        /* Enhance touch targets */
        .stRadio > div {
            gap: 15px;
        }
        
        .stRadio > div > label {
            padding: 10px;
            border-radius: 8px;
            background: rgba(0,0,0,0.05);
        }
    }
    
    /* Camera preview enhancements */
    video {
        border-radius: 15px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3) !important;
    }
    
    /* Success/Error message styling */
    .stSuccess, .stError {
        font-size: 18px;
        padding: 15px;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)


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
    inject_mobile_css()
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
