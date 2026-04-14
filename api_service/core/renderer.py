# ────────────────────────────────────────────────────────────────────────────────
# 🚧 FUTURE FEATURE: DECLARATIVE JSON RENDERER
# ────────────────────────────────────────────────────────────────────────────────
# This module implements a standalone "Video Engine" that renders videos based on a 
# JSON specification (similar to Remotion or After Effects Scripting).
# 
# NOTE: This is currently EXPERIMENTAL and separate from the main auto-clipping pipeline.
# It is intended for future use cases where precise, programmatic control over 
# every frame, text, and transition is required (e.g., frontend-driven editing).
# ────────────────────────────────────────────────────────────────────────────────

import os
import requests
import tempfile
from moviepy.editor import (
    VideoFileClip, TextClip, ImageClip, CompositeVideoClip, 
    ColorClip, AudioFileClip, CompositeAudioClip
)
from pydantic import BaseModel
from typing import List, Optional, Union, Literal

# ─────────────────────────────────────────────────────────────
# 1. Define the Schema (The Language of the Engine)
# ─────────────────────────────────────────────────────────────

class Asset(BaseModel):
    type: Literal['video', 'image', 'text', 'audio']
    src: Optional[str] = None
    text: Optional[str] = None
    style: Optional[dict] = {}  # Font, color, size, bg_color, stroke_color, stroke_width, shadow_color, shadow_offset

class Animation(BaseModel):
    type: Literal['fade_in', 'fade_out', 'pop_in', 'scale_in', 'slide_up', 'slide_left']
    duration: float = 0.5

class Clip(BaseModel):
    asset: Asset
    start: float
    length: Optional[float] = None
    trim_start: float = 0.0
    scale: float = 1.0
    position: Union[Literal['center', 'top', 'bottom', 'left', 'right'], List[int]] = 'center'
    opacity: float = 1.0
    volume: float = 1.0
    layer: int = 0
    animations: List[Animation] = []  # List of animations to apply

class Track(BaseModel):
    clips: List[Clip]

class Timeline(BaseModel):
    background: str = "#000000"
    tracks: List[Track]

class OutputSpec(BaseModel):
    format: str = "mp4"
    resolution: str = "1080:1920"  # width:height
    fps: int = 30

class RenderRequest(BaseModel):
    timeline: Timeline
    output: OutputSpec

# ─────────────────────────────────────────────────────────────
# 2. The Engine (JSON -> MoviePy)
# ─────────────────────────────────────────────────────────────

class JSONRenderer:
    def __init__(self, output_dir="outputs"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.temp_files = []

    def _download_asset(self, url):
        """Helper to download assets from URLs"""
        if not url.startswith(('http:', 'https:')):
            return url
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Get extension or default
            ext = os.path.splitext(url)[1] or ".tmp"
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            
            for chunk in response.iter_content(chunk_size=8192):
                tf.write(chunk)
            
            tf.close()
            self.temp_files.append(tf.name)
            return tf.name
        except Exception as e:
            print(f"Failed to download asset: {url} - {e}")
            return None

    def cleanup(self):
        """Remove temp files"""
        for f in self.temp_files:
            try:
                os.remove(f)
            except:
                pass

    def render(self, request: RenderRequest, output_filename: str):
        """
        Takes a JSON spec and renders a video file.
        """
        try:
            width, height = map(int, request.output.resolution.split(":"))
            fps = request.output.fps
            
            # 1. Create Background
            final_video_clips = []
            max_duration = 0
            audio_clips = []

            # Background Color
            bg_clip = ColorClip(size=(width, height), color=request.timeline.background)
            
            # 2. Process Tracks & Clips
            # Flatten all clips and sort by layer
            all_clips_spec = []
            for track in request.timeline.tracks:
                for clip_spec in track.clips:
                    all_clips_spec.append(clip_spec)
            
            # Sort by layer (ascending)
            all_clips_spec.sort(key=lambda x: x.layer)

            for clip_spec in all_clips_spec:
                clip = self._create_moviepy_clip(clip_spec, width, height)
                
                if clip:
                    # Apply timing
                    clip = clip.set_start(clip_spec.start)
                    
                    # Update max duration
                    end_time = clip_spec.start + clip.duration
                    if end_time > max_duration:
                        max_duration = end_time
                    
                    # Separate audio/video
                    if clip_spec.asset.type == 'audio':
                        audio_clips.append(clip)
                    else:
                        final_video_clips.append(clip)

            # 3. Final Composition
            bg_clip = bg_clip.set_duration(max_duration)
            final_video_clips.insert(0, bg_clip)

            final_video = CompositeVideoClip(final_video_clips, size=(width, height))
            
            # Handle Audio Mixing
            composite_audio_list = []
            if final_video.audio:
                composite_audio_list.append(final_video.audio)
            composite_audio_list.extend(audio_clips)
            
            if composite_audio_list:
                final_video.audio = CompositeAudioClip(composite_audio_list)

            final_video = final_video.set_duration(max_duration)

            # 4. Write File
            output_path = os.path.join(self.output_dir, output_filename)
            final_video.write_videofile(
                output_path, 
                fps=fps, 
                codec="libx264", 
                audio_codec="aac",
                threads=4,
                preset="medium"
            )
            
            return output_path
        finally:
            self.cleanup()

    def _create_moviepy_clip(self, clip_spec: Clip, screen_w, screen_h):
        asset = clip_spec.asset
        clip = None

        try:
            src_path = asset.src
            if src_path and src_path.startswith(('http', 'https')):
                src_path = self._download_asset(src_path)
            
            # Check file existence for local files
            if src_path and not os.path.exists(src_path) and not src_path.startswith(('http', 'https')):
                 # Try relative to project root if absolute fails
                 if os.path.exists(os.path.abspath(src_path)):
                     src_path = os.path.abspath(src_path)

            # --- Video ---
            if asset.type == 'video':
                if not src_path: return None
                clip = VideoFileClip(src_path)
                if clip_spec.length:
                    end = clip_spec.trim_start + clip_spec.length
                    clip = clip.subclip(clip_spec.trim_start, min(end, clip.duration))
                else:
                    clip = clip.subclip(clip_spec.trim_start)
                
                # Resize video
                if clip_spec.scale != 1.0:
                    clip = clip.resize(clip_spec.scale)
                
                # Audio Volume
                if clip.audio:
                    clip = clip.volumex(clip_spec.volume)

            # --- Image ---
            elif asset.type == 'image':
                if not src_path: return None
                clip = ImageClip(src_path)
                if clip_spec.length:
                    clip = clip.set_duration(clip_spec.length)
                
                if clip_spec.scale != 1.0:
                    clip = clip.resize(clip_spec.scale)

            # --- Text ---
            elif asset.type == 'text':
                if not asset.text: return None
                fontsize = asset.style.get('fontSize', 70)
                color = asset.style.get('color', 'white')
                font = asset.style.get('font', 'Arial')
                bg_color = asset.style.get('backgroundColor', None)
                stroke_color = asset.style.get('stroke_color', None)
                stroke_width = asset.style.get('stroke_width', 1)
                
                # TextClip wrapper
                # Note: You need ImageMagick installed for TextClip
                clip = TextClip(
                    asset.text, 
                    fontsize=fontsize, 
                    color=color, 
                    font=font,
                    bg_color=bg_color,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width,
                    method='caption',
                    size=(int(screen_w * 0.9), None) # Auto-wrap
                )
                if clip_spec.length:
                    clip = clip.set_duration(clip_spec.length)

            # --- Audio ---
            elif asset.type == 'audio':
                if not src_path: return None
                clip = AudioFileClip(src_path)
                if clip_spec.length:
                    end = clip_spec.trim_start + clip_spec.length
                    clip = clip.subclip(clip_spec.trim_start, min(end, clip.duration))
                clip = clip.volumex(clip_spec.volume)
                return clip

            # --- Common Visual Props ---
            if clip:
                # 1. Apply Position first
                pos = clip_spec.position
                if isinstance(pos, list):
                    pos = tuple(pos)
                clip = clip.set_position(pos)
                
                # 2. Apply Opacity
                if clip_spec.opacity < 1.0:
                    clip = clip.set_opacity(clip_spec.opacity)
                
                # 3. Apply Animations
                for anim in clip_spec.animations:
                    clip = self._apply_animation(clip, anim, screen_w, screen_h)

            return clip

        except Exception as e:
            print(f"Error creating clip for asset {asset}: {e}")
            return None

    def _create_text_clip_from_style(self, text, style, screen_w):
        """Helper to create a TextClip with full styling support"""
        try:
            fontsize = style.get('fontSize', 70)
            color = style.get('color', 'white')
            font = style.get('font', 'Arial')
            bg_color = style.get('backgroundColor', None)
            stroke_color = style.get('stroke_color', None)
            stroke_width = style.get('stroke_width', 0)
            
            # Shadow implementation (simple drop shadow via composition if needed, 
            # but TextClip has limited shadow support directly. 
            # We can simulate it by creating a black copy behind.)
            shadow_color = style.get('shadow_color', None)
            shadow_offset = style.get('shadow_offset', (2, 2))
            
            # Main Text
            txt_clip = TextClip(
                text, 
                fontsize=fontsize, 
                color=color, 
                font=font,
                bg_color=bg_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                method='caption',
                align='center',
                size=(int(screen_w * 0.9), None) # Auto-wrap
            )
            
            if shadow_color:
                # Create shadow layer
                shadow_clip = TextClip(
                    text, 
                    fontsize=fontsize, 
                    color=shadow_color, 
                    font=font,
                    method='caption',
                    align='center',
                    size=(int(screen_w * 0.9), None)
                ).set_position(lambda t: (shadow_offset[0], shadow_offset[1])) # Offset relative to parent
                
                # Composite shadow + text
                # We need a CompositeVideoClip that fits both
                w, h = txt_clip.size
                composite = CompositeVideoClip(
                    [shadow_clip, txt_clip.set_position('center')], 
                    size=(w + abs(shadow_offset[0])*2, h + abs(shadow_offset[1])*2)
                )
                return composite
            
            return txt_clip
        except Exception as e:
            print(f"Error creating text clip: {e}")
            return None

    def _apply_animation(self, clip, anim: Animation, w, h):
        """Apply MoviePy transformations for animations"""
        d = anim.duration
        
        if anim.type == 'fade_in':
            return clip.fadein(d)
        
        elif anim.type == 'fade_out':
            return clip.fadeout(d)
            
        elif anim.type == 'pop_in':
            # Scale from 0 to 1 with a slight bounce effect could be complex, 
            # simple linear scale 0->1 for now
            return clip.resize(lambda t: min(1, t / d) if t < d else 1)
            
        elif anim.type == 'scale_in':
             # Zoom from 0.8 to 1.0
            return clip.resize(lambda t: 0.8 + 0.2 * (t / d) if t < d else 1)

        elif anim.type == 'slide_up':
            # Move from bottom to original position
            # Note: This overrides static position, so needs care. 
            # We assume 'pos' was set to the final destination.
            # Get final x, y. This is tricky in MoviePy as pos can be strings.
            # Simplified: Slide from bottom of screen
            def slide(t):
                if t >= d: return clip.pos(t) # Stay at final
                progress = t / d
                x, y = clip.pos(t)
                # If y is a string (like 'center'), we can't easily calculate offset without computing logic
                # Fallback to simple fade if pos is relative, or implement relative sliding later
                return x, y # Placeholder: Real sliding requires resolving 'center' to pixels
            
            # Better approach for slide: CompositeVideoClip handles pos better. 
            # For now, let's use a simple transform if pos is absolute, else skip
            pass 

        return clip

# ─────────────────────────────────────────────────────────────
# 3. Helpers (STT -> Timeline)
# ─────────────────────────────────────────────────────────────

def convert_whisper_to_timeline(
    whisper_result: dict,
    video_path: str,
    max_words_per_line: int = 5,
    base_style: dict = {},
    highlight_style: dict = {}
) -> Timeline:
    """
    Convert Whisper STT output to a renderer Timeline.
    
    Args:
        whisper_result: The raw output from Whisper (segments with words).
        video_path: Path to the source video.
        max_words_per_line: Max words to show at once (auto-segmentation).
        base_style: Default text style.
        highlight_style: Style for the active word (karaoke effect).
    """
    tracks = []
    
    # 1. Video Track (Background)
    video_track = Track(clips=[
        Clip(
            asset=Asset(type='video', src=video_path),
            start=0,
            layer=0
        )
    ])
    tracks.append(video_track)
    
    # 2. Text Track (Captions)
    text_clips = []
    
    all_words = []
    # Flatten segments into a single list of words
    if 'segments' in whisper_result:
        for seg in whisper_result['segments']:
            if 'words' in seg:
                all_words.extend(seg['words'])
    
    # Group words into chunks (lines)
    for i in range(0, len(all_words), max_words_per_line):
        chunk = all_words[i : i + max_words_per_line]
        if not chunk: continue
        
        start_time = chunk[0]['start']
        end_time = chunk[-1]['end']
        text_content = " ".join([w['word'].strip() for w in chunk])
        
        # Build Word objects with highlight timing
        words_objs = []
        for w in chunk:
            words_objs.append(Word(
                text=w['word'].strip(),
                start=w['start'],
                end=w['end'],
                style=highlight_style # Active style
            ))
            
        text_clips.append(Clip(
            asset=Asset(
                type='text',
                text=text_content,
                words=words_objs,
                style=base_style
            ),
            start=start_time,
            length=end_time - start_time,
            position='center', # Default position
            layer=1
        ))
        
    tracks.append(Track(clips=text_clips))
    
    return Timeline(background="#000000", tracks=tracks)

    def _apply_animation(self, clip, anim: Animation, w, h):
        """Apply MoviePy transformations for animations"""
        d = anim.duration
        
        if anim.type == 'fade_in':
            return clip.fadein(d)
        
        elif anim.type == 'fade_out':
            return clip.fadeout(d)
            
        elif anim.type == 'pop_in':
            # Scale from 0 to 1 with a slight bounce effect could be complex, 
            # simple linear scale 0->1 for now
            return clip.resize(lambda t: min(1, t / d) if t < d else 1)
            
        elif anim.type == 'scale_in':
             # Zoom from 0.8 to 1.0
            return clip.resize(lambda t: 0.8 + 0.2 * (t / d) if t < d else 1)

        elif anim.type == 'slide_up':
            # Move from bottom to original position
            # Note: This overrides static position, so needs care. 
            # We assume 'pos' was set to the final destination.
            # Get final x, y. This is tricky in MoviePy as pos can be strings.
            # Simplified: Slide from bottom of screen
            def slide(t):
                if t >= d: return clip.pos(t) # Stay at final
                progress = t / d
                x, y = clip.pos(t)
                # If y is a string (like 'center'), we can't easily calculate offset without computing logic
                # Fallback to simple fade if pos is relative, or implement relative sliding later
                return x, y # Placeholder: Real sliding requires resolving 'center' to pixels
            
            # Better approach for slide: CompositeVideoClip handles pos better. 
            # For now, let's use a simple transform if pos is absolute, else skip
            pass 

        return clip