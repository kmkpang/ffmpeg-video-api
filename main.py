import os
import time
import shutil
import uuid
import logging
import subprocess
import requests
import tempfile
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables (for local development)
load_dotenv()

# Initialize FastAPI
app = FastAPI(title="FFMPEG Video Editor Bot")

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("video-bot")

# Pydantic models for request validation
class VideoRequest(BaseModel):
    video_id: str
    image_urls: List[str]
    voice_audio_url: str

# Supabase configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.warning("SUPABASE_URL or SUPABASE_KEY is missing from environment variables.")

# Helper function to initialize Supabase client dynamically to prevent startup failure if env vars aren't set yet
def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")
    return create_client(url, key)

def download_file(url: str, local_path: str):
    logger.info(f"Downloading {url} to {local_path}")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def get_audio_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def process_video_background(video_id: str, image_urls: List[str], voice_audio_url: str):
    temp_dir = tempfile.mkdtemp()
    supabase = get_supabase_client()
    
    try:
        logger.info(f"Starting video processing background task for video_id: {video_id}")
        
        # 1. Update render_status in Supabase to 'rendering'
        supabase.table("videos").update({
            "render_status": "rendering",
            "error_message": None
        }).eq("id", video_id).execute()
        
        # 2. Download the voiceover audio file
        audio_local = os.path.join(temp_dir, "audio.mp3")
        download_file(voice_audio_url, audio_local)
        
        # 3. Get audio duration
        duration = get_audio_duration(audio_local)
        logger.info(f"Audio duration: {duration} seconds")
        
        # 4. Calculate timing per image
        N = len(image_urls)
        if N == 0:
            raise ValueError("No image URLs provided for the video.")
            
        durations = []
        base_dur = round(duration / N, 2)
        for i in range(N - 1):
            durations.append(base_dur)
        # The last segment absorbs any floating-point rounding differences
        durations.append(round(duration - sum(durations), 2))
        
        # 5. Download images and generate short video segments with Ken Burns effect
        segment_paths = []
        for i, img_url in enumerate(image_urls):
            img_local = os.path.join(temp_dir, f"image_{i}.jpg")
            download_file(img_url, img_local)
            
            segment_path = os.path.join(temp_dir, f"segment_{i}.mp4")
            segment_paths.append(segment_path)
            
            # Alternate zoom directions: Even index zooms IN, Odd zooms OUT
            zoom_in = (i % 2 == 0)
            total_frames = int(durations[i] * 30)  # Render at 30 fps
            
            if zoom_in:
                # Slowly zoom in from 1.0 to 1.25, centering the camera viewport
                vf_filter = f"scale=2048:3584,zoompan=z='min(zoom+0.0008,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920,setsar=1"
            else:
                # Slowly zoom out from 1.25 to 1.0, centering the camera viewport
                vf_filter = f"scale=2048:3584,zoompan=z='max(1.25-0.0008*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920,setsar=1"
            
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", img_local,
                "-vf", vf_filter,
                "-c:v", "libx264",
                "-t", str(durations[i]),
                "-pix_fmt", "yuv420p",
                "-r", "30",
                segment_path
            ]
            logger.info(f"Generating segment {i} of duration {durations[i]}s (frames: {total_frames})")
            subprocess.run(cmd, check=True, capture_output=True)
            
        # 6. Create txt listing files for FFMPEG concat demuxer
        concat_txt = os.path.join(temp_dir, "inputs.txt")
        with open(concat_txt, "w") as f:
            for seg in segment_paths:
                f.write(f"file '{seg}'\n")
                
        # 7. Concatenate all segments (fast operation, no re-encoding required)
        merged_video = os.path.join(temp_dir, "merged.mp4")
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt,
            "-c", "copy",
            merged_video
        ]
        logger.info("Concatenating video segments")
        subprocess.run(cmd_concat, check=True, capture_output=True)
        
        # 8. Merge the concatenated video track with the audio track
        final_video = os.path.join(temp_dir, "final.mp4")
        cmd_merge = [
            "ffmpeg", "-y",
            "-i", merged_video,
            "-i", audio_local,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            final_video
        ]
        logger.info("Merging audio and video tracks")
        subprocess.run(cmd_merge, check=True, capture_output=True)
        
        # 9. Upload the final video file to Supabase Storage (bucket: 'videos')
        storage_path = f"generated_videos/{video_id}_{int(time.time())}.mp4"
        logger.info(f"Uploading final video to Supabase bucket 'videos' at path '{storage_path}'")
        with open(final_video, "rb") as f:
            supabase.storage.from_("videos").upload(
                path=storage_path,
                file=f,
                file_options={"content-type": "video/mp4", "x-upsert": "true"}
            )
            
        # 10. Retrieve the public URL of the uploaded video
        public_url = supabase.storage.from_("videos").get_public_url(storage_path)
        logger.info(f"Video uploaded successfully. Public URL: {public_url}")
        
        # 11. Update the record in Supabase to 'completed' with final URL
        supabase.table("videos").update({
            "final_video_url": public_url,
            "render_status": "completed",
            "error_message": None
        }).eq("id", video_id).execute()
        
    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        try:
            supabase.table("videos").update({
                "render_status": "failed",
                "error_message": str(e)
            }).eq("id", video_id).execute()
        except Exception as db_err:
            logger.error(f"Failed to record failure state in database: {str(db_err)}")
            
    finally:
        # Securely clean up the temporary workspace
        try:
            shutil.rmtree(temp_dir)
            logger.info("Cleaned up temporary workspace.")
        except Exception as cleanup_err:
            logger.error(f"Error cleaning up temp directory: {str(cleanup_err)}")

@app.post("/generate-video")
def generate_video(payload: VideoRequest, background_tasks: BackgroundTasks):
    """
    Accepts video_id, image_urls, and voice_audio_url.
    Begins rendering the video in a background task to prevent HTTP timeouts.
    """
    try:
        # Basic validation of environment variables before scheduling
        get_supabase_client()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    background_tasks.add_task(
        process_video_background,
        payload.video_id,
        payload.image_urls,
        payload.voice_audio_url
    )
    
    return {
        "status": "queued",
        "message": "Video rendering started in background.",
        "video_id": payload.video_id
    }

@app.get("/health")
def health_check():
    """
    Health check endpoint for Render.com keep-alive and readiness check.
    """
    # Verify FFMPEG availability
    ffmpeg_available = False
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        ffmpeg_available = True
    except Exception:
        pass
        
    return {
        "status": "healthy",
        "ffmpeg_installed": ffmpeg_available,
        "supabase_configured": bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))
    }
