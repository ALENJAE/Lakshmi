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

import streamlit.components.v1 as components

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

def enhanced_mobile_qr_scanner():
    """Custom mobile-optimized QR scanner with fixed control buttons"""
    
    st.subheader("📱 Enhanced Mobile QR Scanner")
    
    # Custom HTML with improved mobile controls
    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qr-scanner/1.4.2/qr-scanner.umd.min.js"></script>
        <style>
            * {
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }
            
            body {
                margin: 0;
                padding: 0;
                background: #000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                overflow: hidden;
                touch-action: manipulation;
            }
            
            .scanner-container {
                position: relative;
                width: 100vw;
                height: 100vh;
                display: flex;
                flex-direction: column;
            }
            
            .video-container {
                position: relative;
                flex: 1;
                width: 100%;
                overflow: hidden;
            }
            
            #video-preview {
                width: 100%;
                height: 100%;
                object-fit: cover;
                transform-origin: center center;
                transition: transform 0.2s ease;
            }
            
            .scanner-overlay {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                pointer-events: none;
            }
            
            .scanner-frame {
                width: min(70vw, 70vh);
                height: min(70vw, 70vh);
                max-width: 280px;
                max-height: 280px;
                border: 4px solid #00ff41;
                border-radius: 20px;
                position: relative;
                animation: scanner-pulse 2s infinite;
                box-shadow: 
                    0 0 0 2px rgba(0,255,65,0.2),
                    0 0 20px rgba(0,255,65,0.3);
            }
            
            @keyframes scanner-pulse {
                0%, 100% { 
                    border-color: #00ff41; 
                    box-shadow: 0 0 0 2px rgba(0,255,65,0.2), 0 0 20px rgba(0,255,65,0.3);
                }
                50% { 
                    border-color: #00cc33; 
                    box-shadow: 0 0 0 4px rgba(0,255,65,0.4), 0 0 25px rgba(0,255,65,0.5);
                }
            }
            
            .instructions {
                position: absolute;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.85);
                color: white;
                padding: 12px 20px;
                border-radius: 20px;
                text-align: center;
                font-size: 14px;
                font-weight: 500;
                z-index: 100;
                max-width: 90%;
                backdrop-filter: blur(10px);
            }
            
            .zoom-display {
                position: absolute;
                top: 50%;
                right: 15px;
                transform: translateY(-50%);
                background: rgba(0,0,0,0.85);
                color: white;
                padding: 8px 12px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
                z-index: 100;
                backdrop-filter: blur(10px);
            }
            
            .controls-panel {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                background: rgba(0,0,0,0.9);
                backdrop-filter: blur(15px);
                padding: 20px;
                display: flex;
                justify-content: center;
                gap: 20px;
                z-index: 200;
                border-top: 1px solid rgba(255,255,255,0.1);
            }
            
            .control-btn {
                width: 60px;
                height: 60px;
                border-radius: 50%;
                border: 3px solid rgba(255,255,255,0.8);
                background: rgba(255,255,255,0.1);
                color: white;
                font-size: 20px;
                font-weight: bold;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s ease;
                user-select: none;
                touch-action: manipulation;
                backdrop-filter: blur(10px);
                position: relative;
                overflow: hidden;
            }
            
            .control-btn::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(255,255,255,0.1);
                border-radius: 50%;
                transform: scale(0);
                transition: transform 0.2s ease;
            }
            
            .control-btn:active::before {
                transform: scale(1);
            }
            
            .control-btn:active {
                transform: scale(0.95);
                border-color: #00ff41;
                background: rgba(0,255,65,0.2);
            }
            
            .control-btn.active {
                background: rgba(255,193,7,0.3);
                border-color: #ffc107;
                color: #ffc107;
            }
            
            .btn-label {
                position: absolute;
                bottom: -25px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 10px;
                color: rgba(255,255,255,0.8);
                white-space: nowrap;
            }
            
            .success-message {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: linear-gradient(135deg, #00ff41, #00cc33);
                color: white;
                padding: 20px 30px;
                border-radius: 15px;
                font-size: 18px;
                font-weight: bold;
                z-index: 300;
                display: none;
                animation: success-popup 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                box-shadow: 0 10px 30px rgba(0,255,65,0.3);
            }
            
            @keyframes success-popup {
                0% { 
                    transform: translate(-50%, -50%) scale(0.3) rotate(-10deg); 
                    opacity: 0; 
                }
                100% { 
                    transform: translate(-50%, -50%) scale(1) rotate(0deg); 
                    opacity: 1; 
                }
            }
            
            .error-message {
                position: absolute;
                bottom: 120px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(244,67,54,0.95);
                color: white;
                padding: 15px 25px;
                border-radius: 15px;
                font-size: 14px;
                z-index: 300;
                display: none;
                max-width: 90%;
                text-align: center;
                backdrop-filter: blur(10px);
            }
            
            .camera-status {
                position: absolute;
                top: 70px;
                right: 15px;
                background: rgba(0,0,0,0.8);
                color: white;
                padding: 6px 12px;
                border-radius: 10px;
                font-size: 12px;
                z-index: 100;
            }
            
            /* Responsive adjustments */
            @media (max-width: 480px) {
                .controls-panel {
                    padding: 15px;
                    gap: 15px;
                }
                
                .control-btn {
                    width: 55px;
                    height: 55px;
                    font-size: 18px;
                }
                
                .instructions {
                    font-size: 12px;
                    padding: 10px 16px;
                }
            }
            
            @media (max-height: 600px) {
                .controls-panel {
                    padding: 12px;
                }
                
                .control-btn {
                    width: 50px;
                    height: 50px;
                    font-size: 16px;
                }
            }
        </style>
    </head>
    <body>
        <div class="scanner-container">
            <div class="video-container">
                <video id="video-preview" playsinline muted></video>
                
                <div class="scanner-overlay">
                    <div class="scanner-frame"></div>
                </div>
                
                <div class="instructions">
                    <div><strong>📱 Point camera at QR code</strong></div>
                    <div>Keep code within green frame</div>
                </div>
                
                <div class="zoom-display" id="zoom-display">
                    🔍 1.0x
                </div>
                
                <div class="camera-status" id="camera-status">
                    📹 Rear Camera
                </div>
            </div>
            
            <div class="controls-panel">
                <div class="control-btn" id="zoom-out" title="Zoom Out">
                    ➖
                    <div class="btn-label">Zoom Out</div>
                </div>
                <div class="control-btn" id="zoom-in" title="Zoom In">
                    ➕
                    <div class="btn-label">Zoom In</div>
                </div>
                <div class="control-btn" id="flash-toggle" title="Toggle Flash">
                    🔦
                    <div class="btn-label">Flash</div>
                </div>
                <div class="control-btn" id="switch-camera" title="Switch Camera">
                    🔄
                    <div class="btn-label">Switch</div>
                </div>
            </div>
            
            <div class="success-message" id="success-message">
                ✅ QR Code Detected!
            </div>
            
            <div class="error-message" id="error-message">
                ❌ Camera access failed
            </div>
        </div>

        <script>
            let currentStream = null;
            let currentZoom = 1.0;
            let flashEnabled = false;
            let currentCamera = 'environment'; // 'user' for front camera
            let qrScanner = null;
            let videoElement = document.getElementById('video-preview');
            let isScanning = true;
            
            // Debounce function for button presses
            function debounce(func, wait) {
                let timeout;
                return function executedFunction(...args) {
                    const later = () => {
                        clearTimeout(timeout);
                        func(...args);
                    };
                    clearTimeout(timeout);
                    timeout = setTimeout(later, wait);
                };
            }
            
            // Initialize camera with better error handling
            async function initCamera() {
                try {
                    // Stop existing stream
                    if (currentStream) {
                        currentStream.getTracks().forEach(track => {
                            track.stop();
                        });
                    }
                    
                    // Request camera with specific constraints
                    const constraints = {
                        video: {
                            facingMode: currentCamera,
                            width: { ideal: 1920, min: 640 },
                            height: { ideal: 1080, min: 480 },
                            frameRate: { ideal: 30, min: 15 }
                        }
                    };
                    
                    console.log('Requesting camera access...');
                    currentStream = await navigator.mediaDevices.getUserMedia(constraints);
                    videoElement.srcObject = currentStream;
                    
                    // Wait for video to be ready
                    await new Promise((resolve) => {
                        videoElement.onloadedmetadata = resolve;
                    });
                    
                    // Initialize QR scanner
                    if (qrScanner) {
                        await qrScanner.destroy();
                    }
                    
                    qrScanner = new QrScanner(
                        videoElement,
                        result => {
                            if (isScanning) {
                                handleQRResult(result.data);
                            }
                        },
                        {
                            returnDetailedScanResult: true,
                            highlightScanRegion: false,
                            highlightCodeOutline: false,
                            maxScansPerSecond: 5,
                            preferredCamera: currentCamera
                        }
                    );
                    
                    await qrScanner.start();
                    console.log('QR Scanner started successfully');
                    
                    // Update camera status
                    updateCameraStatus();
                    
                    // Clear any error messages
                    document.getElementById('error-message').style.display = 'none';
                    
                } catch (error) {
                    console.error('Camera initialization failed:', error);
                    showError(`Camera error: ${error.message || 'Access denied'}`);
                }
            }
            
            // Handle QR code detection with better feedback
            function handleQRResult(data) {
                console.log('QR Code detected:', data);
                
                // Temporarily stop scanning to prevent duplicates
                isScanning = false;
                
                // Show success message with vibration
                document.getElementById('success-message').style.display = 'block';
                
                // Vibrate if supported
                if (typeof navigator !== 'undefined' && navigator.vibrate) {
                    navigator.vibrate([100, 50, 100]);
                }
                
                // Send result to Streamlit
                try {
                    if (window.parent && window.parent.postMessage) {
                        window.parent.postMessage({
                            type: 'qr-result',
                            data: data.trim()
                        }, '*');
                    }
                } catch (e) {
                    console.error('Failed to send message to parent:', e);
                }
                
                // Hide success message and resume scanning
                setTimeout(() => {
                    document.getElementById('success-message').style.display = 'none';
                    isScanning = true;
                }, 2000);
            }
            
            // Show error message
            function showError(message) {
                const errorEl = document.getElementById('error-message');
                errorEl.textContent = message;
                errorEl.style.display = 'block';
                setTimeout(() => {
                    errorEl.style.display = 'none';
                }, 5000);
            }
            
            // Update camera status display
            function updateCameraStatus() {
                const statusEl = document.getElementById('camera-status');
                statusEl.textContent = currentCamera === 'environment' ? '📹 Rear Camera' : '📹 Front Camera';
            }
            
            // Zoom controls with constraints
            function applyZoom() {
                const track = currentStream?.getVideoTracks()[0];
                if (track) {
                    try {
                        const capabilities = track.getCapabilities();
                        if (capabilities.zoom) {
                            track.applyConstraints({
                                advanced: [{ zoom: currentZoom }]
                            });
                        } else {
                            // Fallback: use CSS transform
                            videoElement.style.transform = `scale(${currentZoom})`;
                        }
                    } catch (e) {
                        // Always fallback to CSS transform
                        videoElement.style.transform = `scale(${currentZoom})`;
                    }
                }
                document.getElementById('zoom-display').textContent = `🔍 ${currentZoom.toFixed(1)}x`;
            }
            
            // Debounced zoom functions
            const debouncedZoomIn = debounce(() => {
                currentZoom = Math.min(4.0, currentZoom + 0.3);
                applyZoom();
            }, 100);
            
            const debouncedZoomOut = debounce(() => {
                currentZoom = Math.max(0.5, currentZoom - 0.3);
                applyZoom();
            }, 100);
            
            // Flash toggle with visual feedback
            async function toggleFlash() {
                const track = currentStream?.getVideoTracks()[0];
                const flashBtn = document.getElementById('flash-toggle');
                
                if (track) {
                    try {
                        const capabilities = track.getCapabilities();
                        if (capabilities.torch) {
                            flashEnabled = !flashEnabled;
                            await track.applyConstraints({
                                advanced: [{ torch: flashEnabled }]
                            });
                            
                            // Update button appearance
                            if (flashEnabled) {
                                flashBtn.classList.add('active');
                            } else {
                                flashBtn.classList.remove('active');
                            }
                        } else {
                            showError('Flash not supported on this device');
                        }
                    } catch (e) {
                        console.error('Flash toggle failed:', e);
                        showError('Flash control failed');
                    }
                }
            }
            
            // Camera switch with proper cleanup
            async function switchCamera() {
                const switchBtn = document.getElementById('switch-camera');
                switchBtn.style.transform = 'rotate(180deg)';
                
                currentCamera = currentCamera === 'environment' ? 'user' : 'environment';
                await initCamera();
                
                setTimeout(() => {
                    switchBtn.style.transform = 'rotate(0deg)';
                }, 300);
            }
            
            // Event listeners with proper touch handling
            document.getElementById('zoom-in').addEventListener('click', debouncedZoomIn);
            document.getElementById('zoom-out').addEventListener('click', debouncedZoomOut);
            document.getElementById('flash-toggle').addEventListener('click', toggleFlash);
            document.getElementById('switch-camera').addEventListener('click', switchCamera);
            
            // Enhanced touch feedback
            document.querySelectorAll('.control-btn').forEach(btn => {
                btn.addEventListener('touchstart', (e) => {
                    e.preventDefault();
                    btn.style.transform = 'scale(0.9)';
                }, { passive: false });
                
                btn.addEventListener('touchend', (e) => {
                    e.preventDefault();
                    btn.style.transform = 'scale(1)';
                }, { passive: false });
                
                // Prevent context menu on long press
                btn.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                });
            });
            
            // Handle page visibility changes
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    if (qrScanner) {
                        qrScanner.stop();
                    }
                } else {
                    if (qrScanner) {
                        qrScanner.start();
                    }
                }
            });
            
            // Handle orientation changes
            window.addEventListener('orientationchange', () => {
                setTimeout(() => {
                    if (qrScanner) {
                        qrScanner.stop();
                        qrScanner.start();
                    }
                }, 500);
            });
            
            // Initialize camera when page loads
            document.addEventListener('DOMContentLoaded', () => {
                console.log('DOM loaded, initializing camera...');
                initCamera();
            });
            
            // Fallback initialization
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', initCamera);
            } else {
                initCamera();
            }
        </script>
    </body>
    </html>
    """
    
    # Display the custom scanner
    components.html(html_code, height=700, scrolling=False)
    
    # JavaScript communication handler for receiving QR results
    st.markdown("""
    <script>
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'qr-result') {
            console.log('Received QR result:', event.data.data);
            // Store the result for Streamlit to pick up
            window.qrResult = event.data.data;
        }
    });
    </script>
    """, unsafe_allow_html=True)
    
    # Alternative: Use session state to handle QR results
    if 'qr_scan_result' not in st.session_state:
        st.session_state.qr_scan_result = None
    
    # Manual input as backup
    st.markdown("---")
    st.subheader("Manual QR Input (Backup)")
    manual_qr = st.text_input("If scanning doesn't work, enter QR code manually:", key="backup_qr_input")
    
    if manual_qr:
        st.session_state.qr_scan_result = manual_qr.strip()
    
    if st.session_state.qr_scan_result:
        result = st.session_state.qr_scan_result
        st.session_state.qr_scan_result = None  # Clear after use
        return result
    
    return None
# Alternative simpler version using HTML5 camera API
def simple_mobile_qr_scanner():
    """Simplified mobile QR scanner with better camera control"""
    
    html_scanner = """
    <div style="text-align: center; padding: 20px;">
        <div style="position: relative; display: inline-block; border-radius: 20px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.3);">
            <video id="qr-video" style="width: 90vw; max-width: 500px; height: 60vh; object-fit: cover;"></video>
            
            <!-- Scanner overlay -->
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; 
                        background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center;
                        pointer-events: none;">
                <div style="width: 250px; height: 250px; border: 4px solid #00ff00; 
                           border-radius: 20px; animation: pulse 2s infinite;">
                </div>
            </div>
            
            <!-- Controls -->
            <div style="position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
                        display: flex; gap: 15px;">
                <button onclick="zoomIn()" style="width: 50px; height: 50px; border-radius: 50%; 
                        background: rgba(0,0,0,0.7); color: white; border: 2px solid white; font-size: 16px;">➕</button>
                <button onclick="zoomOut()" style="width: 50px; height: 50px; border-radius: 50%; 
                        background: rgba(0,0,0,0.7); color: white; border: 2px solid white; font-size: 16px;">➖</button>
                <button onclick="toggleFlash()" style="width: 50px; height: 50px; border-radius: 50%; 
                        background: rgba(0,0,0,0.7); color: white; border: 2px solid white; font-size: 16px;">🔦</button>
            </div>
        </div>
        
        <div style="margin-top: 20px; padding: 15px; background: #f0f0f0; border-radius: 10px;">
            <h4>📱 Scanning Instructions</h4>
            <p>• Hold your phone steady<br>
            • Point camera at QR code<br>
            • Keep QR code within the green square<br>
            • Use ➕/➖ for zoom, 🔦 for flash</p>
        </div>
    </div>
    
    <style>
    @keyframes pulse {
        0%, 100% { border-color: #00ff00; opacity: 1; }
        50% { border-color: #00aa00; opacity: 0.7; }
    }
    </style>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qr-scanner/1.4.2/qr-scanner.umd.min.js"></script>
    <script>
    let videoElement = document.getElementById('qr-video');
    let currentStream = null;
    let currentZoom = 1.0;
    let qrScanner = null;
    
    async function startCamera() {
        try {
            currentStream = await navigator.mediaDevices.getUserMedia({
                video: { 
                    facingMode: 'environment',
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            });
            videoElement.srcObject = currentStream;
            
            qrScanner = new QrScanner(videoElement, result => {
                console.log('QR detected:', result.data);
                alert('QR Code: ' + result.data);
                // You can send this to Streamlit via postMessage
                window.parent.postMessage({qr_data: result.data}, '*');
            });
            
            qrScanner.start();
        } catch (error) {
            console.error('Camera error:', error);
            alert('Camera access failed: ' + error.message);
        }
    }
    
    function zoomIn() {
        currentZoom = Math.min(3.0, currentZoom + 0.3);
        videoElement.style.transform = `scale(${currentZoom})`;
    }
    
    function zoomOut() {
        currentZoom = Math.max(0.7, currentZoom - 0.3);
        videoElement.style.transform = `scale(${currentZoom})`;
    }
    
    function toggleFlash() {
        const track = currentStream?.getVideoTracks()[0];
        if (track) {
            track.applyConstraints({
                advanced: [{torch: !track.getSettings().torch}]
            }).catch(e => console.log('Flash not supported'));
        }
    }
    
    // Start camera when page loads
    startCamera();
    </script>
    """
    
    return components.html(html_scanner, height=700)
# QR Scanner using streamlit_qrcode_scanner
def qr_scanner():
    """Replace your existing qr_scanner function with this"""
    st.subheader("📱 QR Code Scanner")
    
    # Show a toggle for scanner type
    scanner_type = st.radio("Scanner Type", ["Enhanced Mobile Scanner", "Simple Scanner"], horizontal=True)
    
    if scanner_type == "Enhanced Mobile Scanner":
        result = enhanced_mobile_qr_scanner()
    else:
        result = simple_mobile_qr_scanner()
    
    # Handle any results
    if result:
        node_name = str(result).strip()
        if node_name in st.session_state.nav_data['nodes']:
            st.session_state.selected_node = node_name
            st.success(f"✅ Successfully scanned: {node_name}")
            st.balloons()
            return node_name
        else:
            st.error(f"❌ QR code '{node_name}' not found in navigation database")
    
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
