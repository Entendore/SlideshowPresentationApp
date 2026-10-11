# core/manifest.py
import os
import json
from datetime import datetime
from typing import Dict, Any, List
from utils.helpers import logger, get_project_dirs

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_library_manifest_path() -> str:
    return os.path.join(BASE_DIR, "library_manifest.json")

def get_project_manifest_path(project_dir: str) -> str:
    return os.path.join(project_dir, "manifest.json")

def load_manifest(path: str) -> Dict[str, Any]:
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_manifest(path: str, data: Dict[str, Any]):
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as e: logger.error(f"Failed to save manifest {path}: {e}")

def should_skip_render(project_path: str, config: Dict[str, Any]) -> bool:
    manifest = load_manifest(get_project_manifest_path(project_path))
    if not manifest: return False
    
    output_info = manifest.get("output", {})
    video_path = os.path.join(output_info.get("dir"), output_info.get("video_filename"))
    if not os.path.exists(video_path): return False

    stored_config = manifest.get("config_snapshot", {})
    critical_keys = ["width", "height", "fps", "encoder", "render_mode", "tts_backend", "enable_zoom", "zoom_factor"]
    
    for k in critical_keys:
        if stored_config.get(k) != config.get(k):
            logger.info(f"Config changed ({k}), re-rendering required.")
            return False

    assets = manifest.get("assets", {})
    for filename, data in assets.items():
        full_path = os.path.join(project_path, filename)
        if not os.path.exists(full_path) or os.path.getmtime(full_path) > data.get("mtime", 0):
            logger.info(f"Asset modified ({filename}), re-rendering required.")
            return False
            
    return True

def finalize_manifests(project_path: str, timeline: List[Dict], config: Dict, final_video: str, render_mode: str):
    project_name = os.path.basename(project_path)
    output_dir = config.get('output_dir', 'Output')
    
    # Build Assets Metadata
    assets_meta = {}
    for item in timeline:
        for f in [item['html'], item.get('txt')]:
            if f and os.path.exists(f):
                assets_meta[os.path.basename(f)] = {"mtime": os.path.getmtime(f), "size": os.path.getsize(f)}

    total_dur = sum(item['duration'] for item in timeline)
    config_snapshot = {k: config.get(k) for k in ["width", "height", "fps", "encoder", "render_mode", "tts_backend", "enable_zoom", "zoom_factor", "transition_duration"]}
    
    project_manifest = {
        "meta": {"version": 2, "created_at": datetime.utcnow().isoformat() + "Z", "last_rendered_at": datetime.utcnow().isoformat() + "Z", "project_name": project_name},
        "config_snapshot": config_snapshot,
        "assets": assets_meta,
        "render": {"slide_count": len(timeline), "total_duration": round(total_dur, 2)},
        "slides": [{"index": i, "html": os.path.basename(t['html']), "duration": t['duration']} for i, t in enumerate(timeline)],
        "output": {"dir": output_dir, "video_filename": os.path.basename(final_video), "render_mode": render_mode}
    }
    
    save_manifest(get_project_manifest_path(project_path), project_manifest)
    
    # Update Global Library
    lib_path = get_library_manifest_path()
    lib = load_manifest(lib_path)
    lib["projects"] = lib.get("projects", {})
    lib["projects"][project_name] = {
        "path": project_path,
        "updated_at": project_manifest["meta"]["last_rendered_at"],
        "render_mode": render_mode,
        "video_file": project_manifest["output"]["video_filename"],
        "duration": total_dur
    }
    save_manifest(lib_path, lib)