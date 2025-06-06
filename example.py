import streamlit as st
import networkx as nx
import json
import base64
import requests
import qrcode
from PIL import Image
import io
import tempfile
import time

from streamlit_agraph import agraph, Node, Edge, Config
from streamlit_qrcode_scanner import qrcode_scanner

import plotly.graph_objects as go

import numpy as np

# GitHub Configuration
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # Set in Streamlit secrets
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")   # Format: "username/repository"
BASE_PATH = "campus_navigator"

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# Helper functions for GitHub API
def get_github_files(path):
    """Get list of files in a GitHub directory"""
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

def initialize_github_structure():
    """Initialize the required folder structure on GitHub"""
    try:
        # Check if base structure exists
        base_files = get_github_files(BASE_PATH)
        
        # Create nav_data.json if it doesn't exist
        nav_data_exists = any(f['name'] == 'nav_data.json' for f in base_files if f['type'] == 'file')
        if not nav_data_exists:
            initial_data = {"nodes": {}, "connections": {}}
            create_file(f"{BASE_PATH}/nav_data.json", json.dumps(initial_data, indent=2), "Initialize navigation data")
            st.info("Created initial nav_data.json")
        
        # Create placeholder files for directories (GitHub doesn't store empty directories)
        images_path = f"{BASE_PATH}/images/.gitkeep"
        qr_path = f"{BASE_PATH}/qrcodes/.gitkeep"
        
        # Check if directories exist by trying to access them
        if not get_github_files(f"{BASE_PATH}/images"):
            create_file(images_path, "# Placeholder for images directory", "Create images directory")
            st.info("Created images directory")
            
        if not get_github_files(f"{BASE_PATH}/qrcodes"):
            create_file(qr_path, "# Placeholder for QR codes directory", "Create QR codes directory")
            st.info("Created QR codes directory")
            
        return True
    except Exception as e:
        st.error(f"Error initializing GitHub structure: {str(e)}")
        return False

# Data management functions
def load_navigation_data():
    """Load navigation data from GitHub"""
    try:
        data_path = f"{BASE_PATH}/nav_data.json"
        content = get_file_content(data_path)
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                st.error("Error parsing navigation data")
                return {"nodes": {}, "connections": {}}
        else:
            # Try to initialize structure if data doesn't exist
            st.warning("Navigation data not found. Initializing...")
            if initialize_github_structure():
                return {"nodes": {}, "connections": {}}
            else:
                st.error("Failed to initialize GitHub structure")
                return {"nodes": {}, "connections": {}}
    except Exception as e:
        st.error(f"Error loading navigation data: {str(e)}")
        return {"nodes": {}, "connections": {}}

def save_navigation_data(data):
    """Save navigation data to GitHub"""
    try:
        data_path = f"{BASE_PATH}/nav_data.json"
        content = json.dumps(data, indent=2)
        return update_file(data_path, content, "Update navigation data")
    except Exception as e:
        st.error(f"Error saving navigation data: {str(e)}")
        return False

def upload_image_to_github(uploaded_file, node_name, path_key):
    """Upload image to GitHub and return the path"""
    try:
        file_extension = uploaded_file.name.split('.')[-1]
        # Sanitize filename
        safe_filename = "".join(c for c in uploaded_file.name if c.isalnum() or c in '._-')
        image_path = f"{BASE_PATH}/images/{node_name}_{path_key}_{safe_filename}"
        
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
        if create_file(qr_path, img_bytes.getvalue(), f"Generate QR code for {node_name}", is_binary=True) or \
           update_file(qr_path, img_bytes.getvalue(), f"Update QR code for {node_name}", is_binary=True):
            return qr_path
        return None
    except Exception as e:
        st.error(f"Error generating QR code: {str(e)}")
        return None

def get_qr_code_from_github(node_name):
    """Get QR code image from GitHub"""
    try:
        qr_path = f"{BASE_PATH}/qrcodes/{node_name}.png"
        image_data = get_file_content(qr_path, is_binary=True)
        if image_data:
            return Image.open(io.BytesIO(image_data))
        return None
    except Exception as e:
        st.error(f"Error loading QR code: {str(e)}")
        return None

# Initialize session state
if 'nav_data' not in st.session_state:
    st.session_state.nav_data = load_navigation_data()
if 'selected_node' not in st.session_state:
    st.session_state.selected_node = None
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = True

# Refresh data function
def refresh_data():
    """Refresh navigation data from GitHub"""
    with st.spinner("Refreshing data from GitHub..."):
        st.session_state.nav_data = load_navigation_data()
    st.success("Data refreshed successfully!")
    st.rerun()

# Image Upload Handler (GitHub version)
def handle_image_upload_github(field_key, node_name, existing_images):
    uploaded_files = st.file_uploader(
        f"Upload images for {field_key}", 
        accept_multiple_files=True, 
        key=f"img_{field_key}_{node_name}",
        type=['png', 'jpg', 'jpeg', 'gif']
    )
    img_paths = existing_images if existing_images else []
    
    if uploaded_files:
        progress_bar = st.progress(0)
        for idx, uploaded_file in enumerate(uploaded_files):
            progress_bar.progress((idx + 1) / len(uploaded_files))
            with st.spinner(f"Uploading {uploaded_file.name}..."):
                img_path = upload_image_to_github(uploaded_file, node_name, field_key)
                if img_path and img_path not in img_paths:
                    img_paths.append(img_path)
                    st.success(f"✅ Uploaded {uploaded_file.name}")
                elif img_path in img_paths:
                    st.info(f"ℹ️ {uploaded_file.name} already exists")
                else:
                    st.error(f"❌ Failed to upload {uploaded_file.name}")
        progress_bar.empty()
    
    # Display existing images
    if img_paths:
        st.write("**Current Images:**")
        cols = st.columns(min(len(img_paths), 3))
        for idx, img_path in enumerate(img_paths):
            with cols[idx % 3]:
                img = get_image_from_github(img_path)
                if img:
                    st.image(img, caption=img_path.split('/')[-1], width=150)
                else:
                    st.error(f"Failed to load: {img_path.split('/')[-1]}")
    
    return img_paths

# Node Management (Enhanced GitHub version)
def handle_node_creation():
    st.subheader("Node Editor")
    
    # Add refresh button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Refresh Data"):
            refresh_data()
    
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
    
    if st.button("💾 Save Node"):
        if node_name:
            # Update node data
            if selected_node and selected_node != node_name and selected_node in st.session_state.nav_data['nodes']:
                del st.session_state.nav_data['nodes'][selected_node]
            
            st.session_state.nav_data['nodes'][node_name] = fields
            
            # Generate QR code
            with st.spinner("Generating QR code..."):
                qr_path = generate_and_save_qr(node_name)
                if qr_path:
                    st.success("✅ QR code generated")
                else:
                    st.warning("⚠️ QR code generation failed")
            
            # Save to GitHub
            with st.spinner("Saving to GitHub..."):
                if save_navigation_data(st.session_state.nav_data):
                    st.success("✅ Node saved successfully!")
                    time.sleep(1)  # Small delay to ensure save completes
                    st.rerun()
                else:
                    st.error("❌ Failed to save node data")
        else:
            st.error("Please enter a node name")
    
    # Display QR code for existing node
    if selected_node:
        st.subheader(f"QR Code for {selected_node}")
        qr_img = get_qr_code_from_github(selected_node)
        if qr_img:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(qr_img, caption=f"QR Code for {selected_node}", width=200)
        else:
            st.warning("QR code not found. It will be generated when you save the node.")

# Delete Functions (Enhanced GitHub version)
def delete_node():
    st.subheader("🗑️ Delete Node")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if not nodes:
        st.warning("No nodes available to delete")
        return
    
    node_to_delete = st.selectbox("Select Node to Delete", nodes)
    
    # Show what will be deleted
    if node_to_delete:
        st.warning(f"This will delete:")
        st.write(f"- Node: {node_to_delete}")
        st.write(f"- QR Code: {node_to_delete}.png")
        
        node_data = st.session_state.nav_data['nodes'][node_to_delete]
        image_count = sum(len(path_data.get('images', [])) for path_data in node_data.values())
        st.write(f"- {image_count} associated images")
        
        # Count connections
        connection_count = sum(1 for conn in st.session_state.nav_data['connections'] 
                             if node_to_delete in conn.split("::"))
        st.write(f"- {connection_count} connections")
    
    confirm = st.checkbox(f"I confirm I want to delete {node_to_delete} and all associated data")
    
    if st.button("🗑️ Delete Node") and confirm:
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
                if node_to_delete in conn.split("::"):
                    del st.session_state.nav_data['connections'][conn]
            
            # Save updated data
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"✅ Node {node_to_delete} and all associated files deleted!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Failed to save updated data")

def delete_path():
    st.subheader("🗑️ Delete Path from Node")
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
    
    # Show what will be deleted
    if path_to_delete:
        path_data = st.session_state.nav_data['nodes'][node][path_to_delete]
        st.warning(f"This will delete:")
        st.write(f"- Path: {path_data['label']}")
        st.write(f"- {len(path_data.get('images', []))} associated images")
        
        # Count connections using this path
        connection_count = sum(1 for conn in st.session_state.nav_data['connections'] 
                             if f"{node}::{path_to_delete}" in conn)
        st.write(f"- {connection_count} connections")
    
    if st.button("🗑️ Delete Path"):
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
                st.success(f"✅ Path '{path_data['label']}' deleted from {node}!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Failed to save updated data")

def delete_link():
    st.subheader("🗑️ Delete Connection Between Nodes")
    connections = list(st.session_state.nav_data['connections'].items())
    if not connections:
        st.warning("No connections available")
        return
    
    connection_list = []
    for conn, details in connections:
        source = details['from']
        path_key = details['path_key']
        target = details['to']
        if path_key in st.session_state.nav_data['nodes'][source]:
            path_label = st.session_state.nav_data['nodes'][source][path_key]['label']
            connection_list.append(f"{source} ({path_label}) ➔ {target}")
        else:
            connection_list.append(f"{source} (deleted path) ➔ {target}")
    
    selected_conn = st.selectbox("Select Connection to Delete", connection_list)
    conn_index = connection_list.index(selected_conn)
    conn_key = list(st.session_state.nav_data['connections'].keys())[conn_index]
    
    if st.button("🗑️ Delete Connection"):
        with st.spinner("Deleting connection..."):
            del st.session_state.nav_data['connections'][conn_key]
            
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"✅ Connection '{selected_conn}' deleted successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Failed to save updated data")

# Node Linking (Enhanced GitHub version)
def handle_node_linking():
    st.subheader("🔗 Link Nodes")
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if len(nodes) < 2:
        st.info("At least two nodes are needed to create a link.")
        return
    
    source = st.selectbox("Source Node", nodes, key="link_source")
    source_paths = st.session_state.nav_data['nodes'][source]
    
    if not source_paths:
        st.warning(f"No paths available in {source}")
        return
        
    path_options = [(f"{idx+1}. {path_data['label']}", path_key) 
                    for idx, (path_key, path_data) in enumerate(source_paths.items())]
    
    selected_path = st.selectbox("Select Path from Source", 
                               options=[opt[0] for opt in path_options])
    path_key = next(opt[1] for opt in path_options if opt[0] == selected_path)
    
    target = st.selectbox("Target Node", [n for n in nodes if n != source], key="link_target")
    
    # Check if link already exists
    conn_key = f"{source}::{path_key}::{target}"
    link_exists = conn_key in st.session_state.nav_data['connections']
    
    if link_exists:
        st.warning("⚠️ This link already exists!")
    
    if st.button("🔗 Create Link", disabled=link_exists):
        with st.spinner("Creating link..."):
            st.session_state.nav_data['connections'][conn_key] = {
                "from": source,
                "to": target,
                "path_key": path_key
            }
            
            if save_navigation_data(st.session_state.nav_data):
                st.success(f"✅ Link created from {source} ({source_paths[path_key]['label']}) to {target}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Failed to save link data")

# Navigation Display (Enhanced GitHub version)
def display_navigation(path):
    total_steps = len(path) - 1
    st.info(f"Total Steps: {total_steps}")
    
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
            
            with st.container():
                st.markdown(f"### 📍 Step {i+1} of {total_steps}")
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if node_data.get('images'):
                        with st.spinner("Loading image..."):
                            img = get_image_from_github(node_data['images'][0])
                            if img:
                                st.image(img, caption=node_data['label'], use_column_width=True)
                            else:
                                st.warning("Failed to load image")
                        
                        # Show additional images if available
                        if len(node_data['images']) > 1:
                            with st.expander(f"View all {len(node_data['images'])} images"):
                                for img_path in node_data['images']:
                                    img = get_image_from_github(img_path)
                                    if img:
                                        st.image(img, caption=img_path.split('/')[-1])
                    else:
                        st.info("No image available for this step")
                
                with col2:
                    st.markdown(f"""
                    **From:** 📍 {current}  
                    **To:** 📍 {next_node}  
                    **Direction:** {node_data['label']}  
                    **Distance:** 📏 {node_data['distance']} ft  
                    **Instruction:** 📝 {node_data['instruction']}  
                    **Landmark:** 🏛️ {node_data['landmark']}  
                    """)
                
                st.markdown("---")

# Path Finding Functions
def find_path_with_weight(start, end):
    G = nx.DiGraph()
    for node in st.session_state.nav_data['nodes']:
        G.add_node(node)
    
    for conn, details in st.session_state.nav_data['connections'].items():
        source = details['from']
        target = details['to']
        path_key = details['path_key']
        if path_key in st.session_state.nav_data['nodes'][source]:
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

def show_path_graph_with_weights(path, total_distance):
    st.subheader(f"🗺️ Navigation Path (Total Distance: {total_distance:.1f} ft)")
    
    nodes = []
    for node_name in st.session_state.nav_data['nodes']:
        if node_name in path:
            if node_name == path[0]:
                nodes.append(Node(id=node_name, label=f"{node_name}\n(🚀START)", color="#4CAF50", size=25))
            elif node_name == path[-1]:
                nodes.append(Node(id=node_name, label=f"{node_name}\n(🏁END)", color="#F44336", size=25))
            else:
                nodes.append(Node(id=node_name, label=node_name, color="#FF9800", size=20))
        else:
            nodes.append(Node(id=node_name, label=node_name, color="#9E9E9E", size=15))

    edges = []
    for i in range(len(path)-1):
        current = path[i]
        next_node = path[i+1]
        
        # Find the connection details
        connection_details = None
        for conn, details in st.session_state.nav_data['connections'].items():
            source, path_key, target = conn.split("::")
            if source == current and target == next_node:
                connection_details = details
                break
        
        if connection_details:
            path_key = connection_details['path_key']
            if path_key in st.session_state.nav_data['nodes'][current]:
                distance = st.session_state.nav_data['nodes'][current][path_key]['distance']
                label = st.session_state.nav_data['nodes'][current][path_key]['label']
                edges.append(Edge(
                    source=current,
                    target=next_node,
                    label=f"{label}\n{distance}ft",
                    color="#2196F3",
                    width=8
                ))

    config = Config(
        width=800,
        height=600,
        directed=True,
        physics=False,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F0F8FF",
        maxZoom=2,
        minZoom=0.1
    )
    
    if nodes and edges:
        agraph(nodes=nodes, edges=edges, config=config)
    else:
        st.warning("No path visualization available")



def show_full_graph():
    st.subheader("🗺️ Complete Campus Network")
    
    # Set fixed zoom values
    min_zoom = 0.3
    max_zoom = 4.0
    
    if not st.session_state.nav_data['nodes']:
        st.info("No nodes available. Create some nodes first!")
        return
    
    # Create NetworkX graph for layout calculation
    G = nx.Graph()
    
    # Add nodes
    for node_name in st.session_state.nav_data['nodes']:
        G.add_node(node_name)
    
    # Add edges with weights
    edge_info = {}
    for conn, details in st.session_state.nav_data['connections'].items():
        source = details['from']
        target = details['to']
        path_key = details['path_key']
        
        if path_key in st.session_state.nav_data['nodes'][source]:
            distance = st.session_state.nav_data['nodes'][source][path_key]['distance']
            G.add_edge(source, target, weight=distance)
            edge_info[(source, target)] = distance
    
    # Calculate layout
    pos = nx.spring_layout(G, k=3, iterations=50)
    
    # Create edge traces
    edge_x = []
    edge_y = []
    edge_info_text = []
    
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        
        # Add distance label at midpoint
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        distance = edge_info.get(edge, edge_info.get((edge[1], edge[0]), 0))
        edge_info_text.append((mid_x, mid_y, f"{distance}ft"))
    
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=2, color='#4CAF50'),
        hoverinfo='none',
        mode='lines'
    )
    
    # Create node traces
    node_x = []
    node_y = []
    node_text = []
    node_info = []
    
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        
        # Create hover info
        adjacencies = list(G.neighbors(node))
        node_info.append(f'Node: {node}<br>Connections: {len(adjacencies)}<br>Connected to: {", ".join(adjacencies)}')
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=node_text,
        textposition="middle center",
        hovertext=node_info,
        marker=dict(
            showscale=False,
            color='#2196F3',
            size=30,
            line=dict(width=2, color='#1976D2')
        )
    )
    
    # Create distance label traces
    label_traces = []
    for mid_x, mid_y, label in edge_info_text:
        label_trace = go.Scatter(
            x=[mid_x], y=[mid_y],
            mode='text',
            text=[label],
            textfont=dict(size=10, color='#333333'),
            showlegend=False,
            hoverinfo='none'
        )
        label_traces.append(label_trace)
    
    # Create figure
    fig_data = [edge_trace, node_trace] + label_traces
    
    fig = go.Figure(
        data=fig_data,
        layout=go.Layout(
            title=dict(
                text="Campus Network Graph",
                font=dict(size=20),
                x=0.5
            ),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=60),
            annotations=[
                dict(
                    text="Campus Network Graph - Interactive View",
                    showarrow=False,
                    xref="paper", yref="paper",
                    x=0.5, y=-0.05,
                    xanchor='center',
                    font=dict(size=12, color='#666666')
                )
            ],
            xaxis=dict(
                showgrid=False, 
                zeroline=False, 
                showticklabels=False,
                scaleanchor="y",
                scaleratio=1
            ),
            yaxis=dict(
                showgrid=False, 
                zeroline=False, 
                showticklabels=False
            ),
            plot_bgcolor='#f8f9fa',
            paper_bgcolor='white',
            # Configure zoom limits
            dragmode='pan',
            # Set zoom range
        )
    )
    
    # Update layout with zoom constraints
    fig.update_layout(
        xaxis=dict(
            range=[min(node_x) - 0.5, max(node_x) + 0.5],
            fixedrange=False
        ),
        yaxis=dict(
            range=[min(node_y) - 0.5, max(node_y) + 0.5],
            fixedrange=False
        )
    )
    
    # Configure zoom behavior
    config = {
        'displayModeBar': True,
        'displaylogo': False,
        'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
        'scrollZoom': True,
        'doubleClick': 'reset',
        'toImageButtonOptions': {
            'format': 'png',
            'filename': 'campus_network',
            'height': 600,
            'width': 800,
            'scale': 1
        }
    }
    
    # Graph controls info
    st.info("""
    **Graph Controls:**
    - 🖱️ **Pan**: Click and drag to move around
    - 🔍 **Zoom**: Scroll wheel or use toolbar buttons  
    - 🏠 **Reset**: Double-click to reset view
    - 📷 **Export**: Use camera icon in toolbar
    """)
    
    # Display the graph
    st.plotly_chart(fig, use_container_width=True, config=config)
    
    # Additional controls
    with st.expander("📊 Graph Statistics"):
        st.write(f"**Nodes:** {len(G.nodes())}")
        st.write(f"**Edges:** {len(G.edges())}")
        st.write(f"**Average Distance:** {np.mean(list(edge_info.values())):.1f}ft")
        st.write(f"**Total Network Length:** {sum(edge_info.values()):.1f}ft")
# QR Code Scanner Integration
def handle_qr_scanner():
    st.subheader("📱 QR Code Scanner")
    
    scanner_tab1, scanner_tab2 = st.tabs(["📷 Live Scanner", "📁 Upload Image"])
    
    with scanner_tab1:
        st.info("Use your device camera to scan QR codes")
        qr_code = qrcode_scanner(key="qr_scanner")
        
        if qr_code:
            st.success(f"✅ QR Code detected: {qr_code}")
            if qr_code in st.session_state.nav_data['nodes']:
                st.session_state.selected_node = qr_code
                st.info(f"📍 Node '{qr_code}' selected for navigation")
            else:
                st.warning(f"⚠️ Node '{qr_code}' not found in the system")
    
    with scanner_tab2:
        uploaded_qr = st.file_uploader("Upload QR Code Image", type=['png', 'jpg', 'jpeg'])
        if uploaded_qr:
            try:
                from pyzbar import pyzbar
                import cv2
                import numpy as np
                
                # Convert uploaded file to opencv format
                file_bytes = np.asarray(bytearray(uploaded_qr.read()), dtype=np.uint8)
                img = cv2.imdecode(file_bytes, 1)
                
                # Decode QR codes
                qr_codes = pyzbar.decode(img)
                
                if qr_codes:
                    for qr in qr_codes:
                        qr_data = qr.data.decode('utf-8')
                        st.success(f"✅ QR Code found: {qr_data}")
                        if qr_data in st.session_state.nav_data['nodes']:
                            st.session_state.selected_node = qr_data
                            st.info(f"📍 Node '{qr_data}' selected for navigation")
                        else:
                            st.warning(f"⚠️ Node '{qr_data}' not found in the system")
                else:
                    st.error("❌ No QR code found in the uploaded image")
            except ImportError:
                st.error("❌ QR code reading libraries not available. Please use the live scanner.")
            except Exception as e:
                st.error(f"❌ Error processing QR code: {str(e)}")

# System Statistics and Overview
def show_system_stats():
    st.subheader("📊 System Statistics")
    
    nodes = st.session_state.nav_data['nodes']
    connections = st.session_state.nav_data['connections']
    
    # Basic stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🏢 Total Nodes", len(nodes))
    
    with col2:
        total_paths = sum(len(node_data) for node_data in nodes.values())
        st.metric("🛤️ Total Paths", total_paths)
    
    with col3:
        st.metric("🔗 Total Connections", len(connections))
    
    with col4:
        total_images = sum(
            len(path_data.get('images', [])) 
            for node_data in nodes.values() 
            for path_data in node_data.values()
        )
        st.metric("🖼️ Total Images", total_images)
    
    # Detailed breakdown
    st.subheader("📋 Node Details")
    if nodes:
        node_data = []
        for node_name, node_paths in nodes.items():
            paths_count = len(node_paths)
            images_count = sum(len(path_data.get('images', [])) for path_data in node_paths.values())
            connections_count = sum(1 for conn in connections if node_name in conn.split("::"))
            
            node_data.append({
                "Node": node_name,
                "Paths": paths_count,
                "Images": images_count,
                "Connections": connections_count
            })
        
        st.dataframe(node_data, use_container_width=True)
    else:
        st.info("No nodes available")

# Data Export/Import Functions
def export_navigation_data():
    st.subheader("📤 Export Navigation Data")
    
    if st.button("📋 Generate Export Data"):
        export_data = {
            "export_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "nav_data": st.session_state.nav_data,
            "statistics": {
                "total_nodes": len(st.session_state.nav_data['nodes']),
                "total_connections": len(st.session_state.nav_data['connections']),
                "total_paths": sum(len(node_data) for node_data in st.session_state.nav_data['nodes'].values())
            }
        }
        
        json_str = json.dumps(export_data, indent=2)
        
        st.download_button(
            label="💾 Download Navigation Data",
            data=json_str,
            file_name=f"campus_nav_export_{int(time.time())}.json",
            mime="application/json"
        )
        
        st.success("✅ Export data generated successfully!")

def import_navigation_data():
    st.subheader("📥 Import Navigation Data")
    
    st.warning("⚠️ Importing will replace ALL current navigation data!")
    
    uploaded_file = st.file_uploader("Choose JSON file", type=['json'])
    
    if uploaded_file:
        try:
            import_data = json.load(uploaded_file)
            
            # Validate structure
            if 'nav_data' in import_data and 'nodes' in import_data['nav_data'] and 'connections' in import_data['nav_data']:
                st.success("✅ Valid navigation data file detected")
                
                # Show import statistics
                if 'statistics' in import_data:
                    stats = import_data['statistics']
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Nodes to Import", stats.get('total_nodes', 0))
                    with col2:
                        st.metric("Connections to Import", stats.get('total_connections', 0))
                    with col3:
                        st.metric("Paths to Import", stats.get('total_paths', 0))
                
                # Show export timestamp if available
                if 'export_timestamp' in import_data:
                    st.info(f"📅 Data exported on: {import_data['export_timestamp']}")
                
                confirm_import = st.checkbox("I confirm I want to replace all current data")
                
                if st.button("📥 Import Data") and confirm_import:
                    with st.spinner("Importing navigation data..."):
                        st.session_state.nav_data = import_data['nav_data']
                        
                        if save_navigation_data(st.session_state.nav_data):
                            st.success("✅ Navigation data imported successfully!")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Failed to save imported data")
            else:
                st.error("❌ Invalid file format. Please upload a valid navigation data export.")
        except json.JSONDecodeError:
            st.error("❌ Invalid JSON file")
        except Exception as e:
            st.error(f"❌ Error importing data: {str(e)}")

# QR Code Management
def manage_qr_codes():
    st.subheader("🏷️ QR Code Management")
    
    nodes = list(st.session_state.nav_data['nodes'].keys())
    if not nodes:
        st.info("No nodes available for QR code management")
        return
    
    # Display all QR codes
    st.write("**Available QR Codes:**")
    
    cols = st.columns(3)
    for idx, node_name in enumerate(nodes):
        with cols[idx % 3]:
            st.write(f"**{node_name}**")
            qr_img = get_qr_code_from_github(node_name)
            if qr_img:
                st.image(qr_img, caption=f"QR for {node_name}", width=150)
                
                # Download button for individual QR codes
                img_bytes = io.BytesIO()
                qr_img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                
                st.download_button(
                    label="💾 Download",
                    data=img_bytes.getvalue(),
                    file_name=f"qr_{node_name}.png",
                    mime="image/png",
                    key=f"download_qr_{node_name}"
                )
            else:
                st.warning("QR not found")
                if st.button(f"🔄 Generate", key=f"gen_qr_{node_name}"):
                    with st.spinner(f"Generating QR for {node_name}..."):
                        qr_path = generate_and_save_qr(node_name)
                        if qr_path:
                            st.success("✅ Generated!")
                            st.rerun()
                        else:
                            st.error("❌ Failed!")
    
    # Bulk operations
    st.subheader("🔄 Bulk QR Operations")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Regenerate All QR Codes"):
            progress_bar = st.progress(0)
            success_count = 0
            
            for idx, node_name in enumerate(nodes):
                progress_bar.progress((idx + 1) / len(nodes))
                with st.spinner(f"Generating QR for {node_name}..."):
                    if generate_and_save_qr(node_name):
                        success_count += 1
                    time.sleep(0.5)  # Small delay to show progress
            
            progress_bar.empty()
            st.success(f"✅ Generated {success_count}/{len(nodes)} QR codes successfully!")
            time.sleep(1)
            st.rerun()
    
    with col2:
        # Download all QR codes as ZIP
        if st.button("📦 Download All QR Codes"):
            import zipfile
            
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                for node_name in nodes:
                    qr_img = get_qr_code_from_github(node_name)
                    if qr_img:
                        img_bytes = io.BytesIO()
                        qr_img.save(img_bytes, format='PNG')
                        zip_file.writestr(f"qr_{node_name}.png", img_bytes.getvalue())
            
            zip_buffer.seek(0)
            
            st.download_button(
                label="💾 Download QR Codes ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"campus_qr_codes_{int(time.time())}.zip",
                mime="application/zip"
            )

# Image Gallery Management
def manage_image_gallery():
    st.subheader("🖼️ Image Gallery")
    
    # Collect all images
    all_images = {}
    for node_name, node_data in st.session_state.nav_data['nodes'].items():
        for path_key, path_data in node_data.items():
            if 'images' in path_data and path_data['images']:
                for img_path in path_data['images']:
                    all_images[img_path] = {
                        'node': node_name,
                        'path': path_key,
                        'label': path_data.get('label', 'Unknown')
                    }
    
    if not all_images:
        st.info("No images found in the system")
        return
    
    st.write(f"**Total Images: {len(all_images)}**")
    
    # Filter options
    nodes = list(set(info['node'] for info in all_images.values()))
    selected_node_filter = st.selectbox("Filter by Node", ["All"] + nodes)
    
    # Display images
    filtered_images = all_images
    if selected_node_filter != "All":
        filtered_images = {path: info for path, info in all_images.items() 
                          if info['node'] == selected_node_filter}
    
    # Grid display
    cols = st.columns(3)
    for idx, (img_path, img_info) in enumerate(filtered_images.items()):
        with cols[idx % 3]:
            img = get_image_from_github(img_path)
            if img:
                st.image(img, caption=f"{img_info['node']} - {img_info['label']}", 
                        use_column_width=True)
                
                # Image details
                st.write(f"**Node:** {img_info['node']}")
                st.write(f"**Path:** {img_info['label']}")
                st.write(f"**File:** {img_path.split('/')[-1]}")
                
                # Delete button
                if st.button(f"🗑️ Delete", key=f"del_img_{idx}"):
                    if delete_file(img_path):
                        # Remove from nav_data
                        node_data = st.session_state.nav_data['nodes'][img_info['node']]
                        path_data = node_data[img_info['path']]
                        if img_path in path_data['images']:
                            path_data['images'].remove(img_path)
                        
                        if save_navigation_data(st.session_state.nav_data):
                            st.success("✅ Image deleted!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ Failed to update data")
                    else:
                        st.error("❌ Failed to delete image")
            else:
                st.error(f"Failed to load: {img_path.split('/')[-1]}")

# Main Application
def main():
    st.set_page_config(
        page_title="🗺️ Campus Navigator", 
        page_icon="🗺️", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🗺️ Campus Navigator")
    st.markdown("*Navigate your campus with ease using QR codes and interactive maps*")
    
    # Check GitHub configuration
    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.error("❌ GitHub configuration missing. Please set GITHUB_TOKEN and GITHUB_REPO in Streamlit secrets.")
        st.stop()
    
    # Initialize GitHub structure if needed
    if not st.session_state.get('github_initialized', False):
        with st.spinner("Initializing GitHub structure..."):
            if initialize_github_structure():
                st.session_state.github_initialized = True
            else:
                st.error("Failed to initialize GitHub structure")
                st.stop()
    
    # Sidebar Navigation
    st.sidebar.title("🧭 Navigation")
    page = st.sidebar.selectbox(
        "Choose Function",
        ["🏠 Home", "📱 QR Scanner", "🗺️ Find Path", "🔧 Admin Panel"]
    )
    
    # Main Content
    if page == "🏠 Home":
        st.header("Welcome to Campus Navigator!")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 🎯 Features:
            - **📱 QR Code Scanning**: Scan QR codes at campus locations
            - **🗺️ Smart Navigation**: Find optimal paths between locations
            - **📸 Visual Directions**: Step-by-step instructions with images
            - **🏛️ Landmark Recognition**: Navigate using familiar landmarks
            - **📊 Interactive Maps**: Visualize the entire campus network
            
            ### 🚀 How to Use:
            1. **Scan QR Code**: Use the QR scanner to identify your location
            2. **Select Destination**: Choose where you want to go
            3. **Follow Directions**: Get step-by-step navigation with images
            4. **Reach Destination**: Arrive at your destination efficiently!
            """)
        
        with col2:
            # Quick stats
            nodes_count = len(st.session_state.nav_data['nodes'])
            connections_count = len(st.session_state.nav_data['connections'])
            
            st.markdown("### 📊 Quick Stats")
            st.metric("Campus Locations", nodes_count)
            st.metric("Available Routes", connections_count)
            
            if nodes_count > 0:
                st.success("✅ System Ready!")
            else:
                st.warning("⚠️ No locations configured")
        
        # Show campus overview
        if st.session_state.nav_data['nodes']:
            st.header("🗺️ Campus Overview")
            show_full_graph()
    
    elif page == "📱 QR Scanner":
        st.header("📱 QR Code Scanner")
        handle_qr_scanner()
        
        # Show selected node info
        if st.session_state.selected_node:
            st.success(f"📍 Current Location: **{st.session_state.selected_node}**")
            
            # Quick navigation from current location
            st.subheader("🎯 Quick Navigation")
            available_destinations = [n for n in st.session_state.nav_data['nodes'].keys() 
                                    if n != st.session_state.selected_node]
            
            if available_destinations:
                destination = st.selectbox("Where do you want to go?", available_destinations)
                
                if st.button("🧭 Get Directions"):
                    path = find_path(st.session_state.selected_node, destination)
                    if path:
                        st.success(f"✅ Route found! {len(path)-1} steps to {destination}")
                        display_navigation(path)
                    else:
                        st.error("❌ No route found to destination")
            else:
                st.info("No other destinations available")
    
    elif page == "🗺️ Find Path":
        st.header("🗺️ Path Finding")
        
        nodes = list(st.session_state.nav_data['nodes'].keys())
        if len(nodes) < 2:
            st.warning("⚠️ At least 2 nodes are required for path finding")
            st.info("Please add more nodes in the Admin Panel")
            return
        
        col1, col2 = st.columns(2)
        
        with col1:
            start_node = st.selectbox("📍 Starting Point", nodes, 
                                    index=nodes.index(st.session_state.selected_node) 
                                    if st.session_state.selected_node in nodes else 0)
        
        with col2:
            available_destinations = [n for n in nodes if n != start_node]
            end_node = st.selectbox("🎯 Destination", available_destinations)
        
        if st.button("🔍 Find Best Route"):
            with st.spinner("Calculating optimal route..."):
                path, total_distance, graph = find_path_with_weight(start_node, end_node)
                
                if path:
                    st.success(f"✅ Route Found! Distance: {total_distance:.1f} ft, Steps: {len(path)-1}")
                    
                    # Show path visualization
                    show_path_graph_with_weights(path, total_distance)
                    
                    # Show detailed navigation
                    st.header("📋 Step-by-Step Directions")
                    display_navigation(path)
                else:
                    st.error("❌ No route found between selected locations")
                    st.info("Check if the locations are connected in the Admin Panel")
    
    elif page == "🔧 Admin Panel":
        st.header("🔧 Admin Panel")
        
        # Authentication could be added here
        admin_tabs = st.tabs([
            "🏢 Manage Nodes", 
            "🔗 Link Nodes", 
            "🗑️ Delete Items",
            "📊 Statistics",
            "🏷️ QR Codes",
            "🖼️ Images",
            "💾 Data Management"
        ])
        
        with admin_tabs[0]:
            handle_node_creation()
        
        with admin_tabs[1]:
            handle_node_linking()
        
        with admin_tabs[2]:
            delete_tab1, delete_tab2, delete_tab3 = st.tabs(["🏢 Delete Node", "🛤️ Delete Path", "🔗 Delete Link"])
            
            with delete_tab1:
                delete_node()
            
            with delete_tab2:
                delete_path()
            
            with delete_tab3:
                delete_link()
        
        with admin_tabs[3]:
            show_system_stats()
        
        with admin_tabs[4]:
            manage_qr_codes()
        
        with admin_tabs[5]:
            manage_image_gallery()
        
        with admin_tabs[6]:
            data_tab1, data_tab2 = st.tabs(["📤 Export", "📥 Import"])
            
            with data_tab1:
                export_navigation_data()
            
            with data_tab2:
                import_navigation_data()

if __name__ == "__main__":
    main()
