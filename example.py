import streamlit as st
import networkx as nx
import json
import base64
import requests
import qrcode
from PIL import Image
import io
import tempfile

from streamlit_agraph import agraph, Node, Edge, Config
from streamlit_qrcode_scanner import qrcode_scanner

# GitHub Configuration
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # Set in Streamlit secrets
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")   # Format: "username/repository"
BASE_PATH = "campus_navigator"

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# Helper functions for GitHub API
def get_github_files(path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    response = requests.get(url, headers=HEADERS)
    return response.json() if response.status_code == 200 else []

def create_file(file_path, content, message, is_binary=False):
    """Create a file in GitHub repository"""
    try:
        if is_binary:
            encoded_content = base64.b64encode(content).decode()
        else:
            encoded_content = base64.b64encode(content.encode()).decode()
        
        data = {
            "message": message,
            "content": encoded_content
        }
        response = requests.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            json=data,
            headers=HEADERS
        )
        return response.status_code == 201
    except Exception as e:
        st.error(f"Error creating file: {str(e)}")
        return False

def update_file(file_path, content, message, is_binary=False):
    """Update an existing file in GitHub repository"""
    try:
        # Get current file SHA
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            headers=HEADERS
        )
        
        if response.status_code != 200:
            return create_file(file_path, content, message, is_binary)
        
        sha = response.json()['sha']
        
        if is_binary:
            encoded_content = base64.b64encode(content).decode()
        else:
            encoded_content = base64.b64encode(content.encode()).decode()
        
        data = {
            "message": message,
            "content": encoded_content,
            "sha": sha
        }
        response = requests.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            json=data,
            headers=HEADERS
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error updating file: {str(e)}")
        return False

def get_file_content(file_path, is_binary=False):
    """Get file content from GitHub repository"""
    try:
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            headers=HEADERS
        )
        if response.status_code == 200:
            content = response.json()['content']
            decoded = base64.b64decode(content)
            return decoded if is_binary else decoded.decode()
        return None
    except Exception as e:
        st.error(f"Error getting file content: {str(e)}")
        return None

def delete_file(file_path):
    """Delete a file from GitHub repository"""
    try:
        # Get current file SHA
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            headers=HEADERS
        )
        
        if response.status_code != 200:
            return True  # File doesn't exist, consider it deleted
        
        sha = response.json()['sha']
        
        data = {
            "message": f"Delete {file_path}",
            "sha": sha
        }
        response = requests.delete(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            json=data,
            headers=HEADERS
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting file: {str(e)}")
        return False

def delete_folder_contents(folder_path):
    """Delete all contents of a folder recursively"""
    try:
        contents = get_github_files(folder_path)
        success = True
        for item in contents:
            if item['type'] == 'file':
                if not delete_file(item['path']):
                    success = False
            elif item['type'] == 'dir':
                if not delete_folder_contents(item['path']):
                    success = False
        return success
    except Exception as e:
        st.error(f"Error deleting folder contents: {str(e)}")
        return False

# Data management functions
def load_navigation_data():
    """Load navigation data from GitHub"""
    data_path = f"{BASE_PATH}/nav_data.json"
    content = get_file_content(data_path)
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            st.error("Error parsing navigation data")
            return {"nodes": {}, "connections": {}}
    return {"nodes": {}, "connections": {}}

def save_navigation_data(data):
    """Save navigation data to GitHub"""
    data_path = f"{BASE_PATH}/nav_data.json"
    content = json.dumps(data, indent=2)
    return update_file(data_path, content, "Update navigation data")

def upload_image_to_github(uploaded_file, node_name, path_key):
    """Upload image to GitHub and return the path"""
    try:
        file_extension = uploaded_file.name.split('.')[-1]
        image_path = f"{BASE_PATH}/images/{node_name}_{path_key}_{uploaded_file.name}"
        
        if create_file(image_path, uploaded_file.getvalue(), f"Upload image for {node_name}", is_binary=True):
            return image_path
        return None
    except Exception as e:
        st.error(f"Error uploading image: {str(e)}")
        return None

def get_image_from_github(image_path):
    """Get image from GitHub repository"""
    try:
        image_data = get_file_content(image_path, is_binary=True)
        if image_data:
            return Image.open(io.BytesIO(image_data))
        return None
    except Exception as e:
        st.error(f"Error loading image: {str(e)}")
        return None

def generate_and_save_qr(node_name):
    """Generate QR code and save to GitHub"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(node_name)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert PIL image to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        qr_path = f"{BASE_PATH}/qrcodes/{node_name}.png"
        if create_file(qr_path, img_bytes.getvalue(), f"Generate QR code for {node_name}", is_binary=True):
            return qr_path
        return None
    except Exception as e:
        st.error(f"Error generating QR code: {str(e)}")
        return None

# Initialize session state
if 'nav_data' not in st.session_state:
    st.session_state.nav_data = load_navigation_data()
if 'selected_node' not in st.session_state:
    st.session_state.selected_node = None

# Image Upload Handler (GitHub version)
def handle_image_upload_github(field_key, node_name, existing_images):
    uploaded_files = st.file_uploader(
        f"Upload images for {field_key}", 
        accept_multiple_files=True, 
        key=f"img_{field_key}_{node_name}"
    )
    img_paths = existing_images if existing_images else []
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            with st.spinner(f"Uploading {uploaded_file.name}..."):
                img_path = upload_image_to_github(uploaded_file, node_name, field_key)
                if img_path and img_path not in img_paths:
                    img_paths.append(img_path)
                    st.success(f"Uploaded {uploaded_file.name}")
    return img_paths

# Node Management (GitHub version)
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
                'label': st.text_input(
                    f"Label for {field_key}", 
                    value=fields.get(field_key, {}).get('label', ''), 
                    key=f"label_{field_key}_{node_name}"
                ),
                'distance': st.number_input(
                    f"Distance (ft) for {field_key}", 
                    value=fields.get(field_key, {}).get('distance', 0), 
                    key=f"dist_{field_key}_{node_name}"
                ),
                'instruction': st.text_area(
                    f"Instruction for {field_key}", 
                    value=fields.get(field_key, {}).get('instruction', ''), 
                    key=f"instr_{field_key}_{node_name}"
                ),
                'images': handle_image_upload_github(
                    field_key, 
                    node_name, 
                    fields.get(field_key, {}).get('images', [])
                ),
                'landmark': st.text_input(
                    f"Nearby Landmark for {field_key}", 
                    value=fields.get(field_key, {}).get('landmark', ''), 
                    key=f"landmark_{field_key}_{node_name}"
                )
            }
    
    if st.button("Save Node"):
        if node_name:
            # Update node data
            if selected_node and selected_node != node_name and selected_node in st.session_state.nav_data['nodes']:
                del st.session_state.nav_data['nodes'][selected_node]
            
            st.session_state.nav_data['nodes'][node_name] = fields
            
            # Generate QR code
            with st.spinner("Generating QR code..."):
                generate_and_save_qr(node_name)
            
            # Save to GitHub
            with st.spinner("Saving to GitHub..."):
                if save_navigation_data(st.session_state.nav_data):
                    st.success("Node saved successfully!")
                    st.rerun()
                else:
                    st.error("Failed to save node data")
        else:
            st.error("Please enter a node name")

# Delete Functions (GitHub version)
def delete_node():
    st.subheader("Delete Node")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if not nodes:
        st.warning("No nodes available to delete")
        return
    
    node_to_delete = st.selectbox("Select Node to Delete", nodes)
    
    if st.button("Delete Node"):
        with st.spinner("Deleting node and associated files..."):
            # Delete QR code
            qr_path = f"{BASE_PATH}/qrcodes/{node_to_delete}.png"
            delete_file(qr_path)
            
            # Delete associated images
            node_data = st.session_state.nav_data['nodes'][node_to_delete]
            for path_key, path_data in node_data.items():
                if 'images' in path_data:
                    for img_path in path_data['images']:
                        delete_file(img_path)
            
            # Remove node from data
            del st.session_state.nav_data['nodes'][node_to_delete]
            
            # Remove all connections involving this node
            connections = list(st.session_state.nav_data['connections'].items())
            for conn, details in connections:
                if node_to_delete in conn.split("::")[0] or node_to_delete in conn.split("::")[-1]:
                    del st.session_state.nav_data['connections'][conn]
            
            # Save updated data
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"Node {node_to_delete} and all associated files deleted!")
                st.rerun()
            else:
                st.error("Failed to save updated data")

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
    
    path_options = [(f"{idx+1}. {path_data['label']}", path_key) 
                    for idx, (path_key, path_data) in enumerate(paths.items())]
    
    selected_path = st.selectbox("Select Path to Delete", 
                               options=[opt[0] for opt in path_options])
    path_to_delete = next(opt[1] for opt in path_options if opt[0] == selected_path)
    
    if st.button("Delete Path"):
        with st.spinner("Deleting path and associated files..."):
            # Delete associated images
            path_data = st.session_state.nav_data['nodes'][node][path_to_delete]
            if 'images' in path_data:
                for img_path in path_data['images']:
                    delete_file(img_path)
            
            # Remove path from node
            del st.session_state.nav_data['nodes'][node][path_to_delete]
            
            # Remove connections using this path
            connections = list(st.session_state.nav_data['connections'].items())
            for conn, details in connections:
                if f"{node}::{path_to_delete}" in conn:
                    del st.session_state.nav_data['connections'][conn]
            
            # Save updated data
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"Path '{path_data['label']}' deleted from {node}!")
                st.rerun()
            else:
                st.error("Failed to save updated data")

def delete_link():
    st.subheader("Delete Connection Between Nodes")
    connections = list(st.session_state.nav_data['connections'].items())
    if not connections:
        st.warning("No connections available")
        return
    
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
        with st.spinner("Deleting connection..."):
            del st.session_state.nav_data['connections'][conn_key]
            
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"Connection '{selected_conn}' deleted successfully!")
                st.rerun()
            else:
                st.error("Failed to save updated data")

# Node Linking (GitHub version)
def handle_node_linking():
    st.subheader("Link Nodes")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if len(nodes) < 2:
        st.info("At least two nodes are needed to create a link.")
        return
    
    source = st.selectbox("Source Node", nodes, key="link_source")
    source_paths = st.session_state.nav_data['nodes'][source]
    path_options = [(f"{idx+1}. {path_data['label']}", path_key) 
                    for idx, (path_key, path_data) in enumerate(source_paths.items())]
    
    selected_path = st.selectbox("Select Path from Source", 
                               options=[opt[0] for opt in path_options])
    path_key = next(opt[1] for opt in path_options if opt[0] == selected_path)
    
    target = st.selectbox("Target Node", [n for n in nodes if n != source], key="link_target")
    
    if st.button("Create Link"):
        with st.spinner("Creating link..."):
            conn_key = f"{source}::{path_key}::{target}"
            st.session_state.nav_data['connections'][conn_key] = {
                "from": source,
                "to": target,
                "path_key": path_key
            }
            
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"Link created from {source} ({source_paths[path_key]['label']}) to {target}")
                st.rerun()
            else:
                st.error("Failed to save link data")

# Navigation Display (GitHub version)
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
                if node_data.get('images'):
                    with st.spinner("Loading image..."):
                        img = get_image_from_github(node_data['images'][0])
                        if img:
                            st.image(img, caption=node_data['label'])
                        else:
                            st.warning("Failed to load image")
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

# Path Finding Functions (same as before)
def find_path_with_weight(start, end):
    G = nx.DiGraph()
    for node in st.session_state.nav_data['nodes']:
        G.add_node(node)
    
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

def find_path(start, end):
    path, _, _ = find_path_with_weight(start, end)
    return path

# Improved Visualization Functions with better sizing and responsiveness
def show_path_graph_with_weights(path, total_distance):
    st.subheader(f"Navigation Path (Total Distance: {total_distance:.1f} ft)")
    
    # Create a container with custom styling for better visibility
    with st.container():
        st.markdown("""
        <style>
        .main .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }
        </style>
        """, unsafe_allow_html=True)
        
        nodes = []
        for node_name in st.session_state.nav_data['nodes']:
            if node_name in path:
                if node_name == path[0]:
                    nodes.append(Node(id=node_name, label=f"{node_name}\n(START)", 
                                    color="#4CAF50", size=30, font={"size": 16, "color": "#fff"}))
                elif node_name == path[-1]:
                    nodes.append(Node(id=node_name, label=f"{node_name}\n(END)", 
                                    color="#F44336", size=30, font={"size": 16, "color": "#fff"}))
                else:
                    nodes.append(Node(id=node_name, label=node_name, 
                                    color="#FF9800", size=25, font={"size": 14, "color": "#fff"}))
            else:
                nodes.append(Node(id=node_name, label=node_name, 
                                color="#9E9E9E", size=20, font={"size": 12, "color": "#333"}))
        
        edges = []
        path_edges = set()
        
        for i in range(len(path)-1):
            path_edges.add((path[i], path[i+1]))
        
        for conn, details in st.session_state.nav_data['connections'].items():
            source = details['from']
            target = details['to']
            path_key = details['path_key']
            distance = st.session_state.nav_data['nodes'][source][path_key]['distance']
            
            if (source, target) in path_edges:
                edges.append(Edge(source=source, target=target, 
                                label=f"{distance} ft", color="#2196F3", width=6,
                                font={"size": 14, "strokeWidth": 2, "strokeColor": "#fff"}))
            else:
                edges.append(Edge(source=source, target=target, 
                                label=f"{distance} ft", color="#BDBDBD", width=2,
                                font={"size": 10}))
        
        # Improved configuration with better physics and sizing
        config = Config(
            height=700,  # Increased height
            width="100%",  # Full width
            directed=True,
            physics={
                'enabled': True,
                'stabilization': {
                    'enabled': True,
                    'iterations': 200,
                    'fit': True
                },
                'barnesHut': {
                    'gravitationalConstant': -8000,
                    'centralGravity': 0.3,
                    'springLength': 95,
                    'springConstant': 0.04,
                    'damping': 0.09,
                    'avoidOverlap': 0.1
                },
                'solver': 'barnesHut'
            },
            layout={
                'hierarchical': {
                    'enabled': False
                }
            },
            interaction={
                'dragNodes': True,
                'dragView': True,
                'zoomView': True,
                'selectConnectedEdges': True,
                'hover': True
            },
            configure={
                'enabled': False
            },
            edges={
                'smooth': {
                    'enabled': True,
                    'type': 'dynamic'
                }
            }
        )
        
        if nodes:
            # Add instructions for better user experience
            st.info("💡 **Navigation Tips:** Use mouse wheel to zoom, click and drag to pan the view. The blue highlighted path shows your route.")
            agraph(nodes=nodes, edges=edges, config=config)
        else:
            st.info("No nodes to display.")

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

def show_interactive_graph():
    st.subheader("Interactive Node Graph with Distances")
    
    # Create container for better layout
    with st.container():
        nodes = []
        for n in st.session_state.nav_data['nodes']:
            nodes.append(Node(id=n, label=n, size=20, font={"size": 14}))
        
        edges = []
        for conn, details in st.session_state.nav_data['connections'].items():
            source = details['from']
            target = details['to']
            path_key = details['path_key']
            distance = st.session_state.nav_data['nodes'][source][path_key]['distance']
            edges.append(Edge(source=source, target=target, 
                            label=f"{distance} ft", font={"size": 12}))
        
        config = Config(
            height=600, 
            width="100%",  # Full width
            directed=True,
            physics={
                'enabled': True,
                'stabilization': {'iterations': 150, 'fit': True},
                'barnesHut': {
                    'gravitationalConstant': -2000,
                    'centralGravity': 0.1,
                    'springLength': 100,
                    'springConstant': 0.05,
                    'damping': 0.09
                }
            },
            interaction={
                'dragNodes': True,
                'dragView': True,
                'zoomView': True
            }
        )
        
        if nodes:
            st.info("💡 **Graph Controls:** Drag nodes to rearrange, use mouse wheel to zoom, click and drag empty space to pan.")
            agraph(nodes=nodes, edges=edges, config=config)
        else:
            st.info("No nodes to display.")

# QR Scanner
def qr_scanner():
    qr_code = qrcode_scanner(key='qrcode_scanner', box_size=800)
    if qr_code:
        node_name = qr_code
        if node_name in st.session_state.nav_data['nodes']:
            st.session_state.selected_node = node_name
            st.success(f"Scanned Node: {node_name}")
            return node_name
        else:
            st.error("Scanned node not found in database.")
    return None

# Main Application
def main():
    # Set page config for better layout
    st.set_page_config(
        page_title="Smart Campus Navigator",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Check GitHub configuration
    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.error("GitHub configuration missing. Please set GITHUB_TOKEN and GITHUB_REPO in Streamlit secrets.")
        st.info("Required secrets: GITHUB_TOKEN, GITHUB_REPO")
        return
    
    st.sidebar.title("🗺️ Smart Campus Navigator")
    mode = st.sidebar.radio("Mode", ["User", "Admin"])
    
    if mode == "Admin":
        st.title("🔧 System Administration")
        
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
        st.title("🧭 Campus Navigation")
        node_keys = list(st.session_state.nav_data['nodes'].keys())
        
        if not node_keys:
            st.info("No nodes available. Please add nodes in Admin mode.")
            return
        
        user_mode = st.radio("Navigation Mode", ["QR Scanner Mode", "Manual Selection Mode"])
        
        if user_mode == "QR Scanner Mode":
            st.subheader("📱 Step 1: Scan QR Code for Source Node")
            qr_code = qrcode_scanner()

            if qr_code:
                if qr_code in node_keys:
                    st.session_state.selected_node = qr_code
                    st.success(f"✅ Source node detected: {qr_code}")
                else:
                    st.error("❌ Scanned QR does not match any node.")

            if st.session_state.selected_node:
                source = st.session_state.selected_node
                st.info(f"📍 Source: {source}")
                destination_options = [n for n in node_keys if n != source]
                if not destination_options:
                    st.warning("No other nodes available as destination.")
                    return
                destination = st.selectbox("🎯 Step 2: Select Destination Node", destination_options)
                
                if st.button("🗺️ Get Directions", type="primary"):
                    with st.spinner("🔍 Finding optimal path..."):
                        path, total_distance, G = find_path_with_weight(source, destination)
                        if path:
                            st.success(f"✅ Path found! Total distance: {total_distance:.1f} feet")
                            show_path_graph_with_weights(path, total_distance)
                            st.markdown("---")
                            st.subheader("📋 Step-by-Step Navigation")
                            display_navigation(path)
                        else:
                            st.error("❌ No path found between selected nodes")
            else:
                st.info("👆 Please scan a QR code to set the source node.")

        else:  # Manual Selection Mode
            st.subheader("🎯 Manual Navigation")
            col1, col2 = st.columns(2)
            
            with col1:
                source = st.selectbox("📍 Select Source Node", node_keys, key="manual_source")
            
            with col2:
                destination_options = [n for n in node_keys if n != source]
                destination = st.selectbox("🎯 Select Destination Node", destination_options, key="manual_destination")
            
            if st.button("🗺️ Get Directions", key="manual_directions", type="primary"):
                with st.spinner("🔍 Finding optimal path..."):
                    path, total_distance, G = find_path_with_weight(source, destination)
                    if path:
                        st.success(f"✅ Path found! Total distance: {total_distance:.1f} feet")
                        show_path_graph_with_weights(path, total_distance)
                        st.markdown("---")
                        st.subheader("📋 Step-by-Step Navigation")
                        display_navigation(path)
                    else:
                        st.error("❌ No path found between selected nodes")
        
        st.markdown("---")
        show_interactive_graph()

if __name__ == "__main__":
    main()
