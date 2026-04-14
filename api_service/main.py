from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html
from typing import Optional, List, Union
from enum import Enum
import os
import uuid
import shutil
import glob
import requests
import json
from fastapi.concurrency import run_in_threadpool
from processor import VideoProcessor
from core.renderer import JSONRenderer, RenderRequest
from core.config import Config
from core.logger import Logger
from core.task_queue import TaskManager
from pydantic import BaseModel, Field

logger = Logger.get_logger(__name__)
task_manager = TaskManager()

# Ensure directories exist
Config.setup_dirs()

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: Optional[int] = None
    message: Optional[str] = None
    result: Optional[dict] = None

class FileInfo(BaseModel):
    filename: str
    size: int
    size_mb: float
    download_url: str

class FilesListResponse(BaseModel):
    status: str
    total_files: int
    files: List[FileInfo]

class QueuedTaskResponse(BaseModel):
    status: str
    task_id: str
    message: str

# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class VideoStyle(str, Enum):
    cinematic         = "cinematic"
    cinematic_blur    = "cinematic_blur"
    vertical_full     = "vertical_full"
    split_vertical    = "split_vertical"
    split_horizontal  = "split_horizontal"

class CaptionMode(str, Enum):
    word           = "word"
    sentence       = "sentence"
    highlight_word = "highlight_word"
    none           = "none"

class CaptionStyle(str, Enum):
    classic       = "classic"
    modern_glow   = "modern_glow"
    tiktok_bold   = "tiktok_bold"
    tiktok_neon   = "tiktok_neon"
    youtube_clean = "youtube_clean"
    youtube_box   = "youtube_box"

class Language(str, Enum):
    auto = "auto"
    en   = "en"

# ─────────────────────────────────────────────
# App Initialization
# ─────────────────────────────────────────────

app = FastAPI(
    title="🎬 Auto-Clipping API",
    docs_url=None,
    redoc_url=None,
    description="""
## Auto-Clipping API
Automatically extract **viral-worthy clips** from long-form videos using AI.
### Features
- 🎯 **Smart clip detection** — AI analyzes and scores the most impactful moments
- 🎨 **Multiple video styles** — Cinematic, TikTok vertical, split-screen, and more
- 💬 **Auto captions** — Word-by-word, sentence, or highlight-word modes
- 🌍 **Multi-language support** — Auto-detect or specify the output language
- 🔔 **Webhook notifications** — Get notified when processing is done
- 📝 **Full transcripts** — Each clip response includes its transcript
### Workflow
1. Upload your video via `/auto-clip`
2. Poll `/status/{task_id}` for progress
3. Download results via `/download/{filename}`
    """,
    version="1.0.0",
    contact={"name": "Auto-Clip Support"},
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "Clipping",     "description": "Upload videos and manage the auto-clipping pipeline."},
        {"name": "Tasks",        "description": "Monitor task status and progress."},
        {"name": "Files",        "description": "List and download processed video clips."},
    ]
)

# ─────────────────────────────────────────────
# Custom Root Swagger UI
# ─────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )

clipper = VideoProcessor()

# ─────────────────────────────────────────────
# Background Task Function
# ─────────────────────────────────────────────

def process_video_task(
    task_id: str,
    video_path: str,
    playground_path: Optional[str],
    audio_path: Optional[str],
    bg_image_path: Optional[str],
    style: VideoStyle,
    bg_music_volume: float,
    secondary_video_volume: float,
    webhook_url: Optional[str],
    language: Language = Language.auto,
    caption_mode: CaptionMode = CaptionMode.sentence,
    caption_style: CaptionStyle = CaptionStyle.classic,
    channel_name: str = "main",   # ✅ pass-through for n8n routing
):
    result = {}
    try:
        def update_progress(progress, message):
            task_manager.update_task_progress(task_id, progress, message)

        update_progress(1, "Starting video analysis...")

        # 1. Determine timestamp mode
        timestamp_mode = (
            "words" if caption_mode in (CaptionMode.word, CaptionMode.highlight_word)
            else "segments"
        )

        # 2. Analyze video (STT + AI)
        scored_segments, total_duration, llm_moments = clipper.analyze_impact(
            video_path,
            source_language=language,
            timestamp_mode=timestamp_mode,
            progress_callback=update_progress
        )

        # 3. Select best clips
        best_clips = clipper.get_best_segments(
            scored_segments,
            video_duration=total_duration
        )

        # 4. Process and export clips
        # ✅ CHANGED: process_clips now returns (output_files, transcripts_per_clip)
        output_files, transcripts_per_clip = clipper.process_clips(
            video_path,
            best_clips,
            llm_moments,
            style=style,
            task_id=task_id,
            language=language,
            playground_path=playground_path,
            audio_path=audio_path,
            bg_music_volume=bg_music_volume,
            secondary_video_volume=secondary_video_volume,
            background_path=bg_image_path,
            caption_mode=caption_mode,
            caption_style=caption_style,
            progress_callback=update_progress
        )

        result = {
            "status":             "success",
            "task_id":            task_id,
            "clips_found":        len(best_clips),
            "output_files":       [os.path.basename(f) for f in output_files],
            "full_transcript":    llm_moments.get("full_text", ""),
            "clip_transcripts":   transcripts_per_clip,
            "best_segments_info": best_clips,
            "channel_name":       channel_name,   # ✅ returned as-is for n8n routing
        }

        task_manager.update_task_progress(task_id, 100, "Completed successfully", result=result)

    except Exception as e:
        import traceback
        error_msg = f"Error during processing: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        result = {
            "status":       "error",
            "task_id":      task_id,
            "error":        str(e),
            "traceback":    traceback.format_exc(),
            "channel_name": channel_name,   # ✅ include even on error for n8n routing
        }
        task_manager.update_task_progress(task_id, -1, error_msg, result=result)

    # Send webhook notification
    if webhook_url and webhook_url.strip() and webhook_url.startswith(('http://', 'https://')):
        try:
            logger.info(f"Sending results to webhook: {webhook_url}")
            response = requests.post(
                webhook_url,
                data=json.dumps(result),
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            logger.info(f"Webhook sent. Status Code: {response.status_code}")
            if response.status_code >= 400:
                logger.warning(f"Webhook Response Error: {response.text}")
        except Exception as webhook_err:
            logger.error(f"Failed to send webhook: {webhook_err}")

    return result

# ─────────────────────────────────────────────
# Endpoints — Clipping
# ─────────────────────────────────────────────

@app.post(
    "/auto-clip",
    tags=["Clipping"],
    response_model=Union[QueuedTaskResponse, dict],
    summary="Upload & auto-clip a video",
    responses={
        200: {"description": "Task queued successfully or completed result"},
        500: {"description": "Internal server error"},
    }
)
async def create_auto_clip(
    video: UploadFile = File(..., description="Main video file to clip (required)"),
    playground_video: Optional[UploadFile] = File(None, description="Secondary video for split-screen styles"),
    audio: Optional[UploadFile] = File(None, description="Background music file"),
    background_image: Optional[UploadFile] = File(None, description="Background image for vertical styles"),
    style: VideoStyle = Form(VideoStyle.cinematic_blur, description="Output video style"),
    caption_mode: CaptionMode = Form(CaptionMode.sentence, description="Caption display mode"),
    caption_style: CaptionStyle = Form(CaptionStyle.classic, description="Caption visual style"),
    webhook_url: Optional[str] = Form(None, description="URL to notify when processing completes"),
    language: Language = Form(Language.auto, description="Target language for captions"),
    bg_music_volume: float = Form(0.1, ge=0.0, le=1.0, description="Background music volume (0.0 – 1.0)"),
    secondary_video_volume: float = Form(0.2, ge=0.0, le=1.0, description="Secondary video volume (0.0 – 1.0)"),
    channel_name: str = Form("main", description="Channel name returned as-is in webhook for n8n routing e.g. gaming, edu, tiktok — default: main"),
):
    """
    Upload a video to be automatically clipped into viral-ready short clips.

    **Response includes:**
    - `output_files` — list of rendered clip filenames
    - `full_transcript` — complete transcript of the original video
    - `clip_transcripts` — per-clip transcript with timestamps and text

    - If `webhook_url` is provided: Runs **asynchronously** and returns a `task_id`.
    - If `webhook_url` is MISSING: Runs **synchronously** and returns the final result.
    """
    task_id = uuid.uuid4().hex[:8]

    # Save main video
    video_path = os.path.join(Config.UPLOADS_DIR, f"{task_id}_{video.filename}")
    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    # Save secondary (playground) video
    playground_path = None
    if playground_video and playground_video.filename and style in [VideoStyle.split_vertical, VideoStyle.split_horizontal]:
        playground_path = os.path.join(Config.UPLOADS_DIR, f"{task_id}_{playground_video.filename}")
        with open(playground_path, "wb") as f:
            shutil.copyfileobj(playground_video.file, f)

    # Save background image
    bg_image_path = None
    if background_image and background_image.filename:
        bg_image_path = os.path.join(Config.UPLOADS_DIR, f"{task_id}_{background_image.filename}")
        with open(bg_image_path, "wb") as f:
            shutil.copyfileobj(background_image.file, f)

    # Save audio
    audio_path = None
    if audio and audio.filename:
        audio_path = os.path.join(Config.UPLOADS_DIR, f"{task_id}_{audio.filename}")
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

    # ── Async (Webhook) vs Sync ───────────────────────────────────────────────
    if webhook_url:
        task_manager.add_task(
            process_video_task,
            task_id=task_id,
            video_path=video_path,
            playground_path=playground_path,
            audio_path=audio_path,
            bg_image_path=bg_image_path,
            style=style,
            bg_music_volume=bg_music_volume,
            secondary_video_volume=secondary_video_volume,
            webhook_url=webhook_url,
            language=language,
            caption_mode=caption_mode,
            caption_style=caption_style,
            channel_name=channel_name,
        )
        return {
            "status":  "queued",
            "task_id": task_id,
            "message": f"Task queued successfully. Track progress at /status/{task_id}"
        }
    else:
        logger.info(f"⏳ Sync mode: Processing task {task_id} inline (no webhook)...")
        result = await run_in_threadpool(
            process_video_task,
            task_id=task_id,
            video_path=video_path,
            playground_path=playground_path,
            audio_path=audio_path,
            bg_image_path=bg_image_path,
            style=style,
            bg_music_volume=bg_music_volume,
            secondary_video_volume=secondary_video_volume,
            webhook_url=None,
            language=language,
            caption_mode=caption_mode,
            caption_style=caption_style,
            channel_name=channel_name,
        )
        return result

# ─────────────────────────────────────────────
# Endpoints — Tasks
# ─────────────────────────────────────────────

@app.get(
    "/status/{task_id}",
    tags=["Tasks"],
    summary="Get task status",
    responses={
        200: {"description": "Task status returned"},
        404: {"description": "Task not found"},
    }
)
async def get_task_status(task_id: str):
    """
    Poll the status and progress of a clipping task by its `task_id`.

    **Progress values:**
    - `1–99` → In progress
    - `100` → Completed successfully (result includes `clip_transcripts`)
    - `-1` → Failed with error
    """
    status_info = task_manager.get_task_status(task_id)
    if not status_info:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return status_info

# ─────────────────────────────────────────────
# Endpoints — Files
# ─────────────────────────────────────────────

@app.get(
    "/download/{filename}",
    tags=["Files"],
    summary="Download a processed clip",
    responses={
        200: {"description": "Video file returned"},
        404: {"description": "File not found"},
    }
)
async def download_video(filename: str):
    """Download a processed clip by filename."""
    file_path = os.path.join(Config.OUTPUTS_DIR, "viral_clips", filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(Config.OUTPUTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)

@app.get(
    "/files",
    tags=["Files"],
    response_model=FilesListResponse,
    summary="List all output files",
)
async def list_files():
    """List all processed `.mp4` clips available for download."""
    try:
        files = []
        search_dirs = [
            Config.OUTPUTS_DIR,
            os.path.join(Config.OUTPUTS_DIR, "viral_clips")
        ]
        seen = set()

        for d in search_dirs:
            if not os.path.exists(d):
                continue
            for filename in os.listdir(d):
                if filename in seen or not filename.endswith(".mp4"):
                    continue
                file_path = os.path.join(d, filename)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    files.append({
                        "filename":     filename,
                        "size":         size,
                        "size_mb":      round(size / (1024 * 1024), 2),
                        "download_url": f"/download/{filename}"
                    })
                    seen.add(filename)

        return {
            "status":      "success",
            "total_files": len(files),
            "files":       files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# 🚧 FUTURE FEATURE: Experimental JSON Rendering
# ─────────────────────────────────────────────

@app.post("/render-json", tags=["Experimental"])
async def render_from_json(request: RenderRequest):
    """[EXPERIMENTAL] Render a video from a declarative JSON specification."""
    renderer = JSONRenderer()
    output_filename = f"render_{uuid.uuid4().hex}.mp4"
    try:
        output_path = await run_in_threadpool(
            renderer.render, request, output_filename
        )
        return {
            "status":       "success",
            "file":         output_filename,
            "download_url": f"/download/{output_filename}",
            "local_path":   output_path
        }
    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)