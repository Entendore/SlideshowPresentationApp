# core/renderer.py
import os
import asyncio
import glob
import re
import math
import subprocess
import logging
import numpy as np
import io
import traceback
import wave
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

try:
    from playwright.async_api import async_playwright
except ImportError: async_playwright = None

try:
    from PIL import Image
except ImportError: Image = None

from core.tts import TTSEngine
from core.manifest import finalize_manifests, should_skip_render
from utils.helpers import logger, natural_sort_key, detect_ffmpeg

class RenderWorker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ffmpeg_path = config.get('ffmpeg_path') or detect_ffmpeg()
        self.width = config.get('width', 1280)
        self.height = config.get('height', 720)
        self.fps = config.get('fps', 30)
        self.transition_duration = config.get('transition_duration', 0.5)
        self.transition_frames = int(self.transition_duration * self.fps)
        
    async def process_slide_asset(self, index: int, html_path: str, temp_dir: str, render_mode: str) -> Dict[str, Any]:
        """Generate Audio and Screenshot for a single slide in parallel."""
        slide_num = str(index + 1)
        
        # 1. Audio Generation
        duration = 3.0
        wav_path = os.path.join(temp_dir, f"a{index}.wav")
        txt_path = os.path.splitext(html_path)[0] + ".txt"
        
        # Read Text
        text = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f: text = f.read().strip()
        if not text: text = f"This is slide {slide_num} with no text."
        
        if render_mode == 'full':
            # Check if WAV already exists in project dir (reuse)
            source_wav = os.path.join(os.path.dirname(html_path), f"slide{slide_num}.wav")
            if os.path.exists(source_wav):
                try:
                    with wave.open(source_wav, 'r') as w:
                        duration = w.getnframes() / float(w.getframerate())
                    # Copy to temp
                    import shutil
                    shutil.copy(source_wav, wav_path)
                except: duration = 3.0
            else:
                # Generate TTS
                mp3_path = wav_path.replace(".wav", ".mp3")
                backend = self.config.get("tts_backend", "edge")
                try:
                    if backend == "azure":
                        TTSEngine.generate_azure_sync(
                            text, mp3_path, 
                            self.config.get("azure_region"), self.config.get("azure_subscription_key"),
                            self.config.get("azure_voice"), 
                            TTSEngine.normalize_style_for_azure(self.config.get("edge_tone", "general")),
                            self.config.get("azure_styledegree", 1.0)
                        )
                    else:
                        await TTSEngine.generate_edge(
                            text, mp3_path, 
                            self.config.get("edge_voice"), 
                            self.config.get("edge_tone", "general")
                        )
                    
                    # Convert to WAV
                    TTSEngine.convert_mp3_to_wav(mp3_path, wav_path, self.ffmpeg_path)
                    
                    # Get duration
                    with wave.open(wav_path, 'r') as w: duration = w.getnframes() / float(w.getframerate())
                except Exception as e:
                    logger.error(f"TTS failed for slide {index}: {e}")
                    duration = max(3.0, len(text.split()) / 2.5)
        else:
            # Video only mode: estimate duration
            duration = max(3.0, len(text.split()) / 2.5)

        # 2. Screenshot Capture (Playwright)
        img_array = None
        if async_playwright:
            try:
                # We run a mini-playwright instance per task or reuse? 
                # Reusing one browser context with multiple pages is faster but managing connection per task is safer for process isolation.
                # For simplicity in this refactor, we launch per slide (can be optimized to use a shared context pool).
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=['--disable-gpu'])
                    page = await browser.new_page()
                    await page.set_viewport_size({"width": self.width, "height": self.height})
                    await page.goto(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}", wait_until="domcontentloaded")
                    await asyncio.sleep(0.5)
                    
                    img_bytes = await page.screenshot(type="jpeg", quality=85)
                    img = Image.open(io.BytesIO(img_bytes))
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img_array = np.array(img)
                    await browser.close()
            except Exception as e:
                logger.error(f"Screenshot failed for slide {index}: {e}")
                img_array = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        else:
            img_array = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        return {
            "index": index,
            "html": html_path,
            "txt": txt_path,
            "audio": wav_path,
            "duration": duration,
            "image": img_array
        }

    def render_project(self, project_path: str, msg_queue):
        """Main entry point for the worker."""
        try:
            if should_skip_render(project_path, self.config):
                msg_queue.put(("SKIP", project_path))
                return

            project_name = os.path.basename(project_path)
            output_dir = self.config.get('output_dir', 'Output')
            temp_dir = os.path.join(output_dir, "temp", project_name)
            os.makedirs(temp_dir, exist_ok=True)
            
            render_mode = self.config.get('render_mode', 'full')
            msg_queue.put((project_name, "PREPARING ASSETS", 0))
            
            # Discover slides
            html_files = sorted(glob.glob(os.path.join(project_path, "slide*.html")), key=natural_sort_key)
            if not html_files: raise Exception("No slides found")

            # --- PARALLEL PHASE ---
            # Process all slides concurrently (Audio Gen + Screenshots)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Limit concurrency to avoid memory explosion
            semaphore = asyncio.Semaphore(self.config.get('render_workers', 3))
            
            async def bound_process(i, html):
                async with semaphore:
                    return await self.process_slide_asset(i, html, temp_dir, render_mode)

            try:
                timeline = loop.run_until_complete(asyncio.gather(*[bound_process(i, f) for i, f in enumerate(html_files)]))
            finally:
                loop.close()

            # --- SEQUENTIAL PHASE (FFmpeg Pipe) ---
            msg_queue.put((project_name, "ENCODING VIDEO", 0))
            final_video = os.path.join(output_dir, project_name + ".mp4")
            
            # Determine encoder
            encoder = self.config.get('encoder', 'auto')
            if encoder == "auto":
                try:
                    r = subprocess.run([self.ffmpeg_path, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    encoder = "h264_nvenc" if "nvenc" in r.stdout else "libx264"
                except: encoder = "libx264"

            cmd = [
                self.ffmpeg_path, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
                "-pix_fmt", "rgb24", "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps), "-i", "-",
                "-c:v", encoder, "-preset", "fast", "-pix_fmt", "yuv420p", "-crf", "23",
                os.path.join(temp_dir, "video_raw.mp4")
            ]
            
            ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Stream frames
            total_slides = len(timeline)
            for i in range(total_slides):
                item = timeline[i]
                img_current = item['image']
                duration = item['duration']
                is_last = (i == total_slides - 1)
                
                # Calculate frames
                static_frames = max(0, int(math.ceil(duration * self.fps))) if is_last else max(0, int(math.ceil((duration - self.transition_duration) * self.fps)))
                
                # Write Static Frames
                for _ in range(static_frames):
                    ffmpeg_proc.stdin.write(img_current.tobytes())
                
                # Write Transition Frames
                if not is_last:
                    img_next = timeline[i+1]['image']
                    for t in range(self.transition_frames):
                        alpha = t / self.transition_frames
                        blended = (img_current * (1.0 - alpha) + img_next * alpha).astype(np.uint8)
                        ffmpeg_proc.stdin.write(blended.tobytes())

            if ffmpeg_proc.stdin: ffmpeg_proc.stdin.close()
            ffmpeg_proc.wait()

            # --- MUXING ---
            msg_queue.put((project_name, "FINALIZING", 0))
            raw_video = os.path.join(temp_dir, "video_raw.mp4")
            
            if render_mode == 'full':
                listfile = os.path.join(temp_dir, "audio_list.txt")
                with open(listfile, "w") as f:
                    for item in timeline: f.write(f"file '{os.path.abspath(item['audio']).replace(os.sep, '/')}'\n")
                audio_full = os.path.join(temp_dir, "audio_full.wav")
                
                subprocess.run([self.ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", audio_full], check=True)
                subprocess.run([self.ffmpeg_path, "-y", "-i", raw_video, "-i", audio_full, "-c:v", "copy", "-c:a", "aac", "-shortest", final_video], check=True)
            else:
                subprocess.run([self.ffmpeg_path, "-y", "-i", raw_video, "-c:v", "copy", final_video], check=True)

            # Update Manifests
            finalize_manifests(project_path, timeline, self.config, final_video, render_mode)
            msg_queue.put(("DONE", project_path))

        except Exception as e:
            logger.error(f"Render failed: {traceback.format_exc()}")
            msg_queue.put(("ERROR", str(e)))

# Wrapper for multiprocessing compatibility
def render_project_worker(project_path, msg_queue, config):
    # Ensure clean logging
    import logging
    logging.basicConfig(level=logging.INFO, format='[%(process)d] %(message)s')
    worker = RenderWorker(config)
    worker.render_project(project_path, msg_queue)