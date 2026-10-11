# engines.py
import os
import sys
import wave
import math
import asyncio
import io
import traceback
import glob
import requests
import subprocess
import numpy as np
import shutil
import re
import logging  
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

from utils import logger, detect_ffmpeg, natural_sort_key, build_manifest_from_timeline, save_project_manifest, update_library_manifest
from constants import EDGE_TONE_PRESETS, AZURE_STYLES

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

def build_azure_ssml(text: str, voice: str, style: str = "general", styledegree: Optional[float] = None, lang: str = "en-US") -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
    style_attrs = f'style="{style}"'
    if styledegree is not None:
        degree = max(0.01, min(2.0, styledegree))
        style_attrs += f' styledegree="{degree:.2f}"'
    return (
        f"<speak version='1.0' xml:lang='{lang}'>"
        f"<voice name='{voice}'>"
        f"<mstts:express-as xmlns:mstts='https://www.w3.org/2001/mstts' {style_attrs}>"
        f"{text}"
        f"</mstts:express-as>"
        f"</voice>"
        f"</speak>"
    )

def generate_azure_audio(text: str, output_path: str, region: str, subscription_key: str, voice: str, style: str, styledegree: Optional[float] = None) -> bool:
    if not subscription_key:
        logger.error("Azure subscription key is missing.")
        return False
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    ssml = build_azure_ssml(text=text, voice=voice, style=style, styledegree=styledegree, lang=voice.split("-")[0] if "-" in voice else "en-US")
    headers = {"Ocp-Apim-Subscription-Key": subscription_key, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "SlideshowApp/1.0"}
    try:
        resp = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=30)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f: f.write(resp.content)
            return True
        else:
            logger.error(f"Azure TTS error: HTTP {resp.status_code} - {resp.text.strip()}")
            return False
    except Exception as e:
        logger.error(f"Azure TTS request failed: {e}")
        return False
    
def apply_ken_burns(img_array: np.ndarray, zoom_factor: float) -> np.ndarray:
    # FIX: Return original image if PIL is not available to prevent crash
    if Image is None:
        return img_array
        
    h, w = img_array.shape[:2]
    new_h, new_w = int(h / zoom_factor), int(w / zoom_factor)
    if new_h >= h or new_w >= w: return img_array
    start_h, start_w = (h - new_h) // 2, (w - new_w) // 2
    cropped = img_array[start_h:start_h+new_h, start_w:start_w+new_w]
    return np.array(Image.fromarray(cropped).resize((w, h), Image.LANCZOS))

def reset_worker_logger():
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]: root_logger.removeHandler(handler)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(process)d] %(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)
    root_logger.setLevel(logging.INFO)

def render_project_worker(project_path, msg_queue, config):
    """Worker function for multiprocessing."""
    reset_worker_logger()
    
    async def generate_audio_edge_tts(text, output_path, voice, tone):
        if not edge_tts: return False
        preset = EDGE_TONE_PRESETS.get(tone, {})
        try:
            communicate = edge_tts.Communicate(text, voice, rate=preset.get("rate", "+0%"), volume=preset.get("volume", "+0%"), pitch=preset.get("pitch", "+0Hz"))
            await communicate.save(output_path)
            return True
        except Exception as e:
            logging.error(f"Worker Audio Gen Error: {e}")
            return False
            
    async def run_async():
        project_name = os.path.basename(project_path)
        output_dir = config.get('output_dir', 'Output')
        temp_dir = os.path.join(output_dir, "temp", project_name)
        render_mode = config.get('render_mode', 'full')
        
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Cannot create temp dir: {e}")
            msg_queue.put(("ERROR", f"Cannot create temp dir: {e}"))
            return

        final_video = os.path.join(output_dir, project_name + ".mp4")
        transition_duration = config.get('transition_duration', 0.5)
        transition_frames = int(transition_duration * config['fps'])
        ffmpeg_path = config.get('ffmpeg_path')
        
        enable_zoom = config.get('enable_zoom', False)
        zoom_factor = config.get('zoom_factor', 1.1)

        ffmpeg_proc = None
        timeline = []

        try:
            if render_mode == 'full': msg_queue.put((project_name, "PREPARING AUDIO", 0))
            else: msg_queue.put((project_name, "PREPARING VIDEO ONLY (audio skipped)", 0))
            
            html_files = sorted(glob.glob(os.path.join(project_path, "slide*.html")), key=natural_sort_key)
            if not html_files:
                msg_queue.put(("ERROR", "No slides found."))
                return

            for i, html_file in enumerate(html_files):
                match = re.search(r'slide(\d+)\.html', os.path.basename(html_file))
                slide_num = match.group(1) if match else str(i+1)
                
                target_audio = os.path.join(temp_dir, f"a{i}.wav")
                duration = 3.0 
                
                if render_mode == 'full':
                    sourced_wav = os.path.join(project_path, f"slide{slide_num}.wav") 
                    if os.path.exists(sourced_wav):
                        try:
                            shutil.copy(sourced_wav, target_audio)
                            with wave.open(target_audio, 'r') as w: duration = w.getnframes() / float(w.getframerate())
                        except: duration = 3.0
                    else:
                        txt_file = os.path.splitext(html_file)[0] + ".txt"
                        text_to_speak = ""
                        if os.path.exists(txt_file):
                            with open(txt_file, "r", encoding="utf-8") as f: content = f.read().strip()
                            text_to_speak = content if content else f"This is Slide {slide_num} with no text."
                        else:
                            text_to_speak = f"This is Slide {slide_num} with no text."
                        
                        temp_mp3 = target_audio.replace(".wav", ".mp3")
                        success = False
                        
                        if config.get("tts_backend") == 'azure':
                             style_name = config.get("azure_style", "calm")
                             styledegree = config.get("azure_styledegree", 1.0)
                             success = generate_azure_audio(
                                 text_to_speak, temp_mp3, 
                                 config.get("azure_region"), 
                                 config.get("azure_subscription_key"), 
                                 config.get("azure_voice"), 
                                 style_name, styledegree
                             )
                        else:
                            tone_style = config.get("edge_tone", "general")
                            success = await generate_audio_edge_tts(text_to_speak, temp_mp3, config.get("edge_voice"), tone_style)

                        if success and os.path.exists(temp_mp3):
                            try:
                                subprocess.run([ffmpeg_path, "-y", "-i", temp_mp3, "-ar", "22050", "-ac", "1", target_audio], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
                                os.remove(temp_mp3)
                                with wave.open(target_audio, 'r') as w: duration = w.getnframes() / float(w.getframerate())
                            except Exception as e:
                                logger.warning(f"Audio generation error: {e}")
                                duration = max(3.0, len(text_to_speak.split()) / 2.5)
                        else:
                            logger.warning(f"Failed to generate audio for slide {slide_num}.")
                            duration = max(3.0, len(text_to_speak.split()) / 2.5)
                else:
                    txt_file = os.path.splitext(html_file)[0] + ".txt"
                    if os.path.exists(txt_file):
                        with open(txt_file, "r", encoding="utf-8") as f: words = len(f.read().split())
                        duration = max(3.0, words / 2.5)
                
                timeline.append({'html': html_file, 'audio': target_audio, 'duration': duration})

            msg_queue.put((project_name, "RENDERING VIDEO", 0))
            encoder = config.get('encoder', 'auto')
            if encoder == "auto":
                try:
                    r = subprocess.run([ffmpeg_path, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if "nvenc" in r.stdout: encoder = "h264_nvenc"
                    else: encoder = "libx264"
                except: encoder = "libx264"

            cmd = [ffmpeg_path, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{config['width']}x{config['height']}", "-r", str(config['fps']), "-i", "-", "-c:v", encoder, "-preset", "fast", "-pix_fmt", "yuv420p", "-crf", "23", os.path.join(temp_dir, "video_raw.mp4")]

            try:
                with open(os.path.join(temp_dir, "ffmpeg_encode.log"), 'w') as err_log:
                    ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_log)
            except Exception as e:
                logger.error(f"Error starting FFmpeg: {e}")

            if not async_playwright: raise Exception("Playwright not installed")

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--disable-gpu', '--no-sandbox'])
                page = await browser.new_page()
                await page.set_viewport_size({"width": config['width'], "height": config['height']})
                
                slide_images = []

                # PHASE 1: CAPTURE ALL
                for i, item in enumerate(timeline):
                    try:
                        file_url = f"file:///{os.path.abspath(item['html']).replace(os.sep, '/')}"
                        await page.goto(file_url, wait_until="domcontentloaded")
                        await asyncio.sleep(0.5) 
                        img_bytes = await page.screenshot(type="jpeg", quality=85)
                        img = Image.open(io.BytesIO(img_bytes))
                        if img.mode != 'RGB': img = img.convert('RGB')
                        slide_images.append(np.array(img))
                        msg_queue.put((project_name, i + 1, len(timeline)))
                    except Exception as e:
                        logger.error(f"Capture failed slide {i}: {e}")
                        slide_images.append(np.zeros((config['height'], config['width'], 3), dtype=np.uint8))
                
                await browser.close()

                # PHASE 2: WRITE FRAMES
                total_slides = len(timeline)
                logger.info(f"Starting frame write sequence: {total_slides} slides")
                msg_queue.put(("INFO", "Writing video frames..."))
                
                for i in range(total_slides):
                    img_current = slide_images[i]
                    duration = timeline[i]['duration']
                    is_last = (i == total_slides - 1)
                    
                    static_frames = max(0, int(math.ceil((duration - transition_duration) * config['fps']))) if not is_last else int(math.ceil(duration * config['fps']))
                    
                    logger.info(f"Slide {i+1}: {duration}s ({static_frames} frames)")

                    if static_frames > 0:
                        for f_idx in range(static_frames):
                            frame_to_write = img_current
                            if enable_zoom:
                                progress = f_idx / static_frames
                                current_zoom = 1.0 + (zoom_factor - 1.0) * progress
                                frame_to_write = apply_ken_burns(img_current, current_zoom)
                            
                            try:
                                ffmpeg_proc.stdin.write(frame_to_write.tobytes())
                            except BrokenPipeError:
                                logger.error("FFmpeg pipe broken during static frame write.")
                                raise

                    if not is_last:
                        img_next = slide_images[i+1]
                        start_frame = img_current
                        end_frame = img_next
                        
                        if enable_zoom:
                            start_frame = apply_ken_burns(img_current, zoom_factor)

                        try:
                            for t in range(transition_frames):
                                alpha = t / transition_frames
                                blended = (start_frame * (1.0 - alpha) + end_frame * alpha).astype(np.uint8)
                                ffmpeg_proc.stdin.write(blended.tobytes())
                        except BrokenPipeError:
                            logger.error("FFmpeg pipe broken during transition.")
                            raise

        except Exception as e:
            logger.error(f"Worker Failure: {traceback.format_exc()}")
            msg_queue.put(("ERROR", str(e)))
        finally:
            if ffmpeg_proc:
                try:
                    if ffmpeg_proc.stdin: ffmpeg_proc.stdin.close()
                    ffmpeg_proc.wait()
                except: pass

            msg_queue.put((project_name, "FINALIZING", 0))
            
            try:
                logger.info("Muxing audio...")
                raw_video = os.path.join(temp_dir, "video_raw.mp4")
                if not os.path.exists(raw_video): raise FileNotFoundError("Video not found")
                
                if render_mode == 'full':
                    listfile = os.path.join(temp_dir, "audio_list.txt")
                    with open(listfile, "w") as f:
                        for item in timeline: f.write(f"file '{os.path.abspath(item['audio']).replace(os.sep, '/')}'\n")
                    audio_full = os.path.join(temp_dir, "audio_full.wav")
                    
                    subprocess.run([ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", audio_full], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    subprocess.run([ffmpeg_path, "-y", "-i", raw_video, "-i", audio_full, "-c:v", "copy", "-c:a", "aac", "-shortest", final_video], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                else:
                    subprocess.run([ffmpeg_path, "-y", "-i", raw_video, "-c:v", "copy", "-shortest", final_video], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
            except Exception as e:
                logger.error(f"Finalize failed: {e}")
                msg_queue.put(("ERROR", str(e)))

            try:
                assets_meta = {}
                for item in timeline:
                    html_path = item['html']
                    txt_path = os.path.splitext(html_path)[0] + ".txt"
                    if os.path.exists(html_path): assets_meta[os.path.basename(html_path)] = {"mtime": os.path.getmtime(html_path), "size": os.path.getsize(html_path)}
                    if os.path.exists(txt_path): assets_meta[os.path.basename(txt_path)] = {"mtime": os.path.getmtime(txt_path), "size": os.path.getsize(txt_path)}

                manifest_data = build_manifest_from_timeline(project_name, project_path, config, timeline, output_dir, final_video, render_mode, assets_meta)
                save_project_manifest(project_path, manifest_data)
                update_library_manifest(project_path)
            except Exception as e: logger.error(f"Manifest update failed: {e}")
            
    try:
        asyncio.run(run_async())
    except Exception: logger.error("Async wrapper crash")
    return project_path