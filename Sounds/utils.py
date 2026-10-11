# utils.py
import os
import re
import sys
import subprocess
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger()
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def detect_ffmpeg() -> Optional[str]:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "ffmpeg"
    except FileNotFoundError:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            return get_ffmpeg_exe()
        except ImportError:
            return None

def get_library_manifest_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "library_manifest.json")

def get_project_manifest_path(project_dir: str) -> str:
    return os.path.join(project_dir, "manifest.json")

def load_project_manifest(project_dir: str) -> Dict[str, Any]:
    path = get_project_manifest_path(project_dir)
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load manifest from {path}: {e}")
        return {}

def save_project_manifest(project_dir: str, data: Dict[str, Any]):
    path = get_project_manifest_path(project_dir)
    try:
        os.makedirs(project_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Cannot create project dir {project_dir}: {e}")
        raise

    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.error(f"Failed to write manifest {path}: {e}")
        raise

def update_library_manifest(project_path: str):
    lib_path = get_library_manifest_path()
    lib = {}
    if os.path.exists(lib_path):
        try:
            with open(lib_path, "r", encoding="utf-8") as f:
                lib = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load library manifest: {e}")

    project_name = os.path.basename(project_path)
    proj_manifest = load_project_manifest(project_path)

    lib["projects"] = lib.get("projects", {})
    output_info = proj_manifest.get("output", {})
    render_info = proj_manifest.get("render", {})
    
    lib["projects"][project_name] = {
        "path": project_path,
        "updated_at": proj_manifest.get("meta", {}).get("last_rendered_at"),
        "render_mode": output_info.get("render_mode"),
        "video_file": output_info.get("video_filename"),
        "duration_seconds": render_info.get("total_duration"),
        "slide_count": render_info.get("slide_count"),
        "status": "ready"
    }

    try:
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(lib, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to write library manifest: {e}")

def build_manifest_from_timeline(
    project_name: str, project_dir: str, config: Dict[str, Any],
    timeline: List[Dict[str, Any]], output_dir: str, final_video: str,
    render_mode: str, assets_meta: Dict[str, Dict[str, float]], rendered_at: str = None
) -> Dict[str, Any]:
    if rendered_at is None:
        rendered_at = datetime.utcnow().isoformat() + "Z"

    existing = load_project_manifest(project_dir)
    created_at = existing.get("meta", {}).get("created_at") or rendered_at

    slides_manifest = []
    total_duration = 0.0
    
    for item in timeline:
        html_file = os.path.basename(item["html"])
        txt_file = os.path.splitext(html_file)[0] + ".txt"
        audio_file = os.path.basename(item.get("audio", ""))
        duration = item.get("duration", 3.0)
        total_duration += duration
        slides_manifest.append({
            "index": len(slides_manifest), "html": html_file,
            "text": txt_file, "audio": audio_file, "duration": duration,
        })

    config_snapshot = {
        "width": config.get("width"), "height": config.get("height"),
        "fps": config.get("fps"), "encoder": config.get("encoder"),
        "render_mode": render_mode, "tts_backend": config.get("tts_backend"),
        "edge_voice": config.get("edge_voice"), "azure_voice": config.get("azure_voice"),
        "enable_zoom": config.get("enable_zoom"), "zoom_factor": config.get("zoom_factor"),
        "transition_duration": config.get("transition_duration")
    }

    return {
        "meta": {"version": 2, "created_at": created_at, "last_rendered_at": rendered_at, "project_name": project_name},
        "config_snapshot": config_snapshot, "assets": assets_meta,
        "render": {"slide_count": len(timeline), "total_duration": round(total_duration, 2), "engine": "playwright-ffmpeg"},
        "slides": slides_manifest,
        "output": {"dir": output_dir, "video_filename": os.path.basename(final_video), "render_mode": render_mode},
    }