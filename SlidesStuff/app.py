import os
import json
import shutil
from datetime import datetime
from flask import Flask, jsonify, send_from_directory, request
from werkzeug.utils import secure_filename
import subprocess

# --- CONFIGURATION ---
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
PRESENTATIONS_FOLDER = os.path.join(APP_ROOT, 'presentations')

if not os.path.exists(PRESENTATIONS_FOLDER):
    os.makedirs(PRESENTATIONS_FOLDER)

app = Flask(__name__)

# --- FIX: Set max upload size to 2GB ---
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024 

# --- HELPER CLASSES ---

class SlideProject:
    """Represents a Slideshow Project on the disk."""
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.slides = self._scan_slides()
        self.status = self._check_status()

    def _scan_slides(self):
        """Scans the project folder for HTML files and pairs them with TXT files."""
        files = os.listdir(self.path)
        # Natural sort for slides
        html_files = sorted([f for f in files if f.lower().endswith(('.html', '.htm'))], 
                         key=lambda x: int(''.join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else x)
        
        slides = []
        for h_file in html_files:
            base_name = os.path.splitext(h_file)[0]
            txt_file = f"{base_name}.txt"
            
            script_content = ""
            if os.path.exists(os.path.join(self.path, txt_file)):
                with open(os.path.join(self.path, txt_file), 'r', encoding='utf-8') as f:
                    script_content = f.read()
            
            html_content = ""
            html_path = os.path.join(self.path, h_file)
            if os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                html_content = f"<h1 class='sh-h1'>{base_name.replace('_', ' ').title()}</h1><p class='sh-p'>Content loaded from file.</p>"
            
            slides.append({
                'filename': h_file,
                'script_filename': txt_file,
                'html': html_content,
                'script': script_content
            })
        return slides

    def _check_status(self):
        """Updated to check for MP4 files."""
        files = os.listdir(self.path)
        if any(f.lower().endswith('.mp4') for f in files):
            return "done"
        if any(f.lower().endswith('.webm') for f in files):
            return "done"
        return "not done"

class ProjectManager:
    """Manages scanning and manifest generation."""
    @staticmethod
    def scan_all():
        projects = []
        if os.path.exists(PRESENTATIONS_FOLDER):
            for name in os.listdir(PRESENTATIONS_FOLDER):
                path = os.path.join(PRESENTATIONS_FOLDER, name)
                if os.path.isdir(path):
                    p = SlideProject(name, path)
                    projects.append({
                        'id': name,
                        'title': name.replace('-', ' ').title(),
                        'status': p.status,
                        'slide_count': len(p.slides),
                        'date': datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d')
                    })
        return projects

# --- ROUTES ---

@app.route('/')
def index():
    return send_from_directory(APP_ROOT, 'index.html')

@app.route('/api/manifest')
def get_manifest():
    projects = ProjectManager.scan_all()
    return jsonify(projects)

@app.route('/api/project/<project_id>/slides')
def get_project_slides(project_id):
    project_path = os.path.join(PRESENTATIONS_FOLDER, project_id)
    if not os.path.exists(project_path):
        return jsonify({'error': 'Project not found'}), 404
    project = SlideProject(project_id, project_path)
    return jsonify({'id': project_id, 'title': project.name, 'slides': project.slides})

@app.route('/api/project/<project_id>/slide/<filename>', methods=['POST'])
def update_slide(project_id, filename):
    """Updates HTML or Script content for a specific slide."""
    project_path = os.path.join(PRESENTATIONS_FOLDER, project_id)
    if not os.path.exists(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    data = request.json
    safe_filename = secure_filename(filename)
    
    if 'html' in data:
        html_path = os.path.join(project_path, safe_filename)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(data['html'])
            
    if 'script' in data:
        base_name = os.path.splitext(safe_filename)[0]
        txt_path = os.path.join(project_path, f"{base_name}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(data['script'])
            
    return jsonify({'status': 'success'})

@app.route('/api/project/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Deletes a project folder."""
    project_path = os.path.join(PRESENTATIONS_FOLDER, project_id)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Project not found'}), 404

@app.route('/api/upload_folder', methods=['POST'])
def upload_folder():
    files = request.files.getlist('files')
    if not files: return jsonify({'error': 'No files provided'}), 400
    
    folder_name = files[0].filename.split('/')[0] if '/' in files[0].filename else f"Project_{datetime.now().timestamp()}"
    target_dir = os.path.join(PRESENTATIONS_FOLDER, folder_name)
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    for file in files:
        filename = secure_filename(file.filename)
        if '/' in filename: filename = filename.split('/', 1)[1]
        file.save(os.path.join(target_dir, filename))
        
    return jsonify({'status': 'success', 'message': f'Imported {len(files)} files', 'project_id': folder_name})

@app.route('/api/render/<project_id>', methods=['POST'])
def save_video(project_id):
    """Handles video upload and FFmpeg conversion."""
    project_path = os.path.join(PRESENTATIONS_FOLDER, project_id)
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    temp_webm_path = os.path.join(project_path, "temp_source.webm")
    file.save(temp_webm_path)
    
    # --- DEBUG: Print file size to terminal to verify ---
    file_size = os.path.getsize(temp_webm_path)
    print(f"[DEBUG] Received file size: {file_size} bytes")

    # --- FIX: Check for empty file (0 bytes) ---
    if file_size == 0:
        os.remove(temp_webm_path)
        print("[DEBUG] Rejected file: Size is 0")
        return jsonify({'error': 'Recording failed (0 bytes). The project likely has no slides.'}), 400

    final_mp4_path = os.path.join(project_path, f"{project_id}.mp4")
    
    try:
        # Run FFmpeg
        subprocess.run([
            'ffmpeg', '-i', temp_webm_path, 
            '-c:v', 'libx264', 
            '-c:a', 'aac', 
            '-movflags', '+faststart', 
            '-y', 
            final_mp4_path
        ], check=True, capture_output=True)
        
        if os.path.exists(temp_webm_path):
            os.remove(temp_webm_path)
            
        return jsonify({'status': 'success', 'message': 'Video converted to MP4 successfully'})
        
    except FileNotFoundError:
        return jsonify({'error': 'FFmpeg not found. Please install FFmpeg on the server and add it to PATH.'}), 500
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown FFmpeg error"
        print(f"FFmpeg Error: {error_msg}")
        return jsonify({'error': f'FFmpeg Conversion failed: {error_msg}'}), 500

@app.route('/presentations/<path:filepath>')
def serve_presentation_asset(filepath):
    """Serves static files (css, images) from project folders."""
    return send_from_directory(PRESENTATIONS_FOLDER, filepath)

# --- DEMO GENERATOR ---
def create_demo_project():
    if not os.listdir(PRESENTATIONS_FOLDER):
        demo_path = os.path.join(PRESENTATIONS_FOLDER, 'Demo_Roadmap')
        os.makedirs(demo_path)
        slides_data = [(1, "Q1 Strategy", "Welcome to the roadmap."), (2, "Key Goals", "Our primary objective is growth."), (3, "Milestones", "We aim to launch by Q2."), (4, "Summary", "Thank you for watching.")]
        for num, title, script in slides_data:
            html = f"<div style='padding: 40px; background: #f0f9ff; height: 100%;'><h1 style='color: #0369a1; border-bottom: 4px solid #0ea5e9; padding-bottom: 10px;'>{title}</h1><p style='color: #334155; font-size: 1.5rem; margin-top: 20px;'>{script}</p></div>"
            with open(os.path.join(demo_path, f"{num}.html"), "w", encoding='utf-8') as f: f.write(html)
            with open(os.path.join(demo_path, f"{num}.txt"), "w", encoding='utf-8') as f: f.write(script)

if __name__ == '__main__':
    create_demo_project()
    print(f"Root: {APP_ROOT}")
    print("Open http://127.0.0.1:5000")
    app.run(debug=True, port=5000)