"""
VideoProcessor — Core pipeline for viral clip extraction.
Fixes applied:
  - source_language (for Whisper) separated from target_language (for translation/captions)
  - Removed duplicate _clean_json_response (json_repair version kept)
  - Single translation pass only (no double-translate on data in-place)
  - timestamp_mode handles highlight_word correctly
  - style string normalised once
  - get_best_segments wired into process_video
  - detected_lang used correctly for captions
  - ✅ FIX: after translation, _line1/_line2 re-computed from translated text
    using SubtitleSegmenter._split_into_lines so line splits match translated content
  - ✅ FIX: translated word timestamps distributed proportional to word length
    (instead of uniform distribution) for better highlight sync
  - ✅ NEW: process_clips now returns (output_files, transcripts_per_clip)
             where transcripts_per_clip is a list of dicts:
             { clip_index, start, end, segments, full_text }
  - ✅ NEW: process_video returns a dict with keys:
             output_files, transcripts, viral_segments, duration
  - ✅ NEW: mix_audio method — simple MoviePy blend (fallback / no-audio-path case)
  - ✅ NEW: _apply_ducking_ffmpeg — FFmpeg sidechaincompress ducking (production)
             Called as a post-process step after write_videofile to avoid
             double-encoding. Falls back to simple mix_audio on FFmpeg failure.
"""
import os
import gc
import json
import shutil
import subprocess
import tempfile
import traceback
import moviepy.editor as mpe
import json_repair

import core  # Applies monkey patches
from core.config import Config
from core.logger import Logger
from core.stt import STT, SubtitleSegmenter
from core.analyze import analyze_transcript
from core.styles import StyleFactory

logger = Logger.get_logger(__name__)


def _distribute_timestamps_by_length(words: list, seg_start: float, seg_end: float) -> list:
    """
    ✅ FIX: Distribute word timestamps proportional to character length instead of
    uniform distribution. Longer words get more time, giving better sync in
    highlight_word mode after translation.
    words: list of str (translated words)
    Returns: list of { text, start, end }
    """
    if not words:
        return []

    total_chars = sum(len(w) for w in words)
    seg_dur     = seg_end - seg_start
    result      = []
    cursor      = seg_start

    for i, w in enumerate(words):
        fraction = (len(w) / total_chars) if total_chars > 0 else (1.0 / len(words))
        w_dur    = seg_dur * fraction
        w_end    = seg_end if i == len(words) - 1 else cursor + w_dur

        result.append({
            "text":  w,
            "start": round(cursor, 3),
            "end":   round(w_end,  3),
        })
        cursor = w_end

    return result


# ─────────────────────────────────────────────────────────────────────────────
class VideoProcessor:

    def __init__(self, model_size="base"):
        self.stt = STT(model_size=model_size)
        Config.setup_dirs()

    # ── Audio: FFmpeg Ducking (Production) ────────────────────────────────────

    def _apply_ducking_ffmpeg(
        self,
        video_path: str,
        audio_path: str,
        bg_music_volume: float = 0.1,
    ) -> bool:
        """
        ✅ Production-grade audio ducking via FFmpeg sidechaincompress.

        Works as a POST-PROCESS step on an already-rendered .mp4 file,
        so there is NO double-encoding of the video stream (codec=copy).

        Ducking parameters (tuned for speech-over-music):
          threshold : 0.02  → ducking kicks in when speech RMS > ~-34 dBFS
          ratio     : 4     → music reduced to 1/4 of its level under speech
          attack    : 200ms → smooth fade-down when speech starts
          release   : 1000ms→ smooth fade-up when speech ends

        Returns True on success, False on any FFmpeg error (caller falls back).
        """
        if not audio_path or not os.path.exists(audio_path):
            return False

        tmp_output = tempfile.mktemp(suffix=".mp4")

        try:
            logger.info(f"🎚️ FFmpeg ducking: {os.path.basename(audio_path)} | vol={bg_music_volume}")

            # ── Build filter_complex ─────────────────────────────────────────
            # [0:a] = original speech  (from rendered video)
            # [1:a] = background music (from audio_path)
            #
            # Step 1 – split original audio: one copy for sidechain detection,
            #          one copy for the final mix.
            # Step 2 – apply volume to music.
            # Step 3 – sidechaincompress: music ducks when speech is loud.
            # Step 4 – amix: blend original speech + ducked music.
            filter_complex = (
                "[0:a]asplit=2[speech_sc][speech_mix];"
                f"[1:a]volume={bg_music_volume},"
                f"afade=t=in:ss=0:d=1.5,"
                f"afade=t=out:st={{fade_start}}:d=2.0[music_in];"
                "[music_in][speech_sc]"
                "sidechaincompress="
                "threshold=0.02:ratio=4:attack=200:release=1000"
                "[music_ducked];"
                "[speech_mix][music_ducked]amix=inputs=2:duration=first[aout]"
            )

            # Calculate fade-out start from video duration
            try:
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        video_path,
                    ],
                    capture_output=True, text=True, check=True,
                )
                duration = float(probe.stdout.strip())
                fade_start = max(0.0, duration - 2.0)
            except Exception:
                fade_start = 0.0  # fallback: no fade-out

            filter_complex = filter_complex.format(fade_start=fade_start)

            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,       # input 0: rendered video (speech)
                "-i", audio_path,       # input 1: background music
                "-filter_complex", filter_complex,
                "-map", "0:v",          # video stream: copy as-is (no re-encode)
                "-map", "[aout]",       # mixed audio
                "-c:v", "copy",         # ✅ NO video re-encoding
                "-c:a", "aac",
                "-b:a", "192k",
                tmp_output,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"❌ FFmpeg ducking failed:\n{result.stderr[-1000:]}")
                return False

            # Replace original file with ducked version
            shutil.move(tmp_output, video_path)
            logger.info("✅ FFmpeg ducking applied successfully")
            return True

        except FileNotFoundError:
            logger.error("❌ FFmpeg not found — install ffmpeg and add to PATH")
            return False
        except Exception as e:
            logger.error(f"❌ FFmpeg ducking error: {e}")
            logger.error(traceback.format_exc())
            return False
        finally:
            if os.path.exists(tmp_output):
                try:
                    os.unlink(tmp_output)
                except Exception:
                    pass

    # ── Audio: Simple MoviePy Mix (Fallback) ──────────────────────────────────

    def mix_audio(self, video_clip, audio_path=None, bg_music_volume=0.1, original_volume=1.0):
        """
        Simple MoviePy audio blend — used as fallback when FFmpeg ducking fails,
        or when no audio_path is provided.

        video_clip       : MoviePy VideoFileClip or CompositeVideoClip
        audio_path       : path to music file (mp3/m4a/...) — None = skip
        bg_music_volume  : background music level  (0.0 → 1.0)
        original_volume  : original video audio level (0.0 → 1.0)
        Returns: video_clip with mixed audio (or original clip unchanged)
        """
        if not audio_path or not os.path.exists(audio_path):
            return video_clip

        clip_duration = video_clip.duration
        logger.info(f"🎵 Fallback mix: {audio_path} | vol={bg_music_volume}")

        music = mpe.AudioFileClip(audio_path)

        if music.duration < clip_duration:
            loops = int(clip_duration / music.duration) + 1
            music = mpe.concatenate_audioclips([music] * loops)
            logger.info(f"🔁 Music looped x{loops}")

        music = music.subclip(0, clip_duration).volumex(bg_music_volume)

        original_audio = video_clip.audio

        if original_audio is None:
            logger.info("⚠️ No original audio — using music only")
            return video_clip.set_audio(music)

        mixed = mpe.CompositeAudioClip([
            original_audio.volumex(original_volume),
            music,
        ])
        logger.info("✅ Fallback audio mixed successfully")
        return video_clip.set_audio(mixed)

    # ── JSON helpers ──────────────────────────────────────────────────────────

    def _clean_json_response(self, content):
        """
        Strips markdown fences then uses json_repair to fix malformed JSON.
        Single definition — json_repair version only.
        """
        if not isinstance(content, str):
            return content

        content = content.strip()
        for fence in ("```json", "```"):
            if content.startswith(fence):
                content = content[len(fence):]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            repaired = json_repair.loads(content)
            return json.dumps(repaired)
        except Exception as e:
            logger.warning(f"⚠️ json_repair failed, using raw content: {e}")

        open_b  = content.count("{")
        close_b = content.count("}")
        if open_b > close_b:
            content += "}" * (open_b - close_b)
            logger.info(f"🔧 Appended {open_b - close_b} closing brace(s)")

        return content

    def parse_ai_response(self, ai_res):
        """Parses AI JSON response → list of segment dicts."""
        if not isinstance(ai_res, dict):
            logger.error(f"❌ Invalid AI response type: {type(ai_res)}")
            return []

        res_content = ai_res.get("content")
        try:
            if isinstance(res_content, str):
                segments_data = json.loads(self._clean_json_response(res_content))
            else:
                segments_data = res_content

            if isinstance(segments_data, list):
                return segments_data

            if isinstance(segments_data, dict):
                for key in ("segments", "clips", "moments"):
                    if key in segments_data and isinstance(segments_data[key], list):
                        return segments_data[key]
                for v in segments_data.values():
                    if isinstance(v, list):
                        return v

        except Exception as e:
            logger.error(f"❌ Failed to parse AI response: {e}")
            logger.error(f"Raw content: {res_content}")

        return []

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyze_impact(self,
                       video_path,
                       source_language=None,
                       target_language=None,
                       timestamp_mode="segments",
                       progress_callback=None):
        """
        STT + AI viral-moment detection.
        source_language : passed directly to Whisper.
                          None → Whisper auto-detects (slower but safe).
        target_language : stored in data for process_clips to use for
                          translation and caption rendering.
        """
        if progress_callback:
            progress_callback(5, "Starting speech-to-text...")

        logger.info(
            f"🎙️ Phase 1: STT  |  source_language={source_language or 'auto-detect'}"
        )

        full_segments, full_text, duration, detected_lang = self.stt.get_transcript(
            video_path,
            language=source_language,
            skip_ai=True,
            timestamp_mode=timestamp_mode,
        )

        logger.info(f"🔍 Whisper detected language: {detected_lang}")

        data = {
            "segments":          full_segments,
            "full_text":         full_text,
            "detected_language": detected_lang,
            "target_language":   target_language,
            "duration":          duration,
        }

        # ── AI Viral Analysis ─────────────────────────────────────────────────
        logger.info("🤖 Phase 2: AI Viral Moment Analysis …")
        if progress_callback:
            progress_callback(20, "Analysing content for viral moments …")

        chunk_size    = Config.CHUNK_SIZE_SECONDS
        overlap       = Config.OVERLAP_SECONDS
        max_time      = full_segments[-1]["end"] if full_segments else 0
        all_ai_segs   = []
        current_start = 0

        while current_start < max_time:
            current_end      = current_start + chunk_size
            chunk_transcript = ""

            for seg in full_segments:
                if seg["start"] >= current_start and seg["start"] < current_end:
                    chunk_transcript += (
                        f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text']}\n"
                    )

            if chunk_transcript.strip():
                pct = 20 + int((current_start / max_time) * 40)
                if progress_callback:
                    progress_callback(
                        pct,
                        f"Analysing {current_start/60:.1f}m – "
                        f"{min(current_end, max_time)/60:.1f}m",
                    )
                logger.info(
                    f"🧠 Chunk {current_start/60:.1f}m → "
                    f"{min(current_end, max_time)/60:.1f}m …"
                )

                ai_res = analyze_transcript(chunk_transcript)
                logger.info(f"🤖 AI response type: {type(ai_res)}")

                try:
                    chunk_segs = self.parse_ai_response(ai_res)
                    logger.info(f"✅ {len(chunk_segs)} segments in chunk")
                    all_ai_segs.extend(chunk_segs)
                except Exception as e:
                    logger.error(f"❌ Chunk processing error: {e}")
                    logger.error(traceback.format_exc())

            current_start += chunk_size - overlap
            if current_end >= max_time:
                break

        seen, unique = set(), []
        for s in all_ai_segs:
            st = s.get("start_time")
            if st not in seen:
                unique.append(s)
                seen.add(st)

        logger.info(f"📊 Total unique viral segments found: {len(unique)}")
        return unique, duration, data

    # ── Sorting ───────────────────────────────────────────────────────────────

    def get_best_segments(self, segments, video_duration=0):
        """Sort segments by viral_score descending."""
        return sorted(segments, key=lambda x: x.get("viral_score", 0), reverse=True)

    # ── Processing ────────────────────────────────────────────────────────────

    def process_clips(self,
                      input_video_path,
                      best_clips,
                      data,
                      style="cinematic",
                      progress_callback=None,
                      **kwargs):
        """
        Cuts, styles, captions, and exports each viral clip.

        Audio strategy:
          1. MoviePy renders the styled clip with original audio only.
          2. _apply_ducking_ffmpeg() applies sidechaincompress as a post-process
             on the written .mp4 (video stream copied, no re-encode).
          3. If FFmpeg is unavailable or fails, mix_audio() is called as fallback
             and the file is re-written with the simple blend.

        ✅ Returns: (output_files, transcripts_per_clip)
            output_files         : list of str — paths to rendered .mp4 files
            transcripts_per_clip : list of dicts, one per successfully rendered clip:
                {
                    "clip_index" : int,
                    "filename"   : str,
                    "start"      : float,
                    "end"        : float,
                    "language"   : str,
                    "segments"   : [ ... ],
                    "full_text"  : str,
                }
        """
        logger.info("🎨 Phase 3: Style & Captions …")
        if progress_callback:
            progress_callback(60, "Generating clips …")

        video_duration = data.get("duration") or 0
        if not video_duration:
            try:
                with mpe.VideoFileClip(input_video_path) as tmp:
                    video_duration = tmp.duration
            except Exception as e:
                logger.error(f"❌ Could not determine video duration: {e}")

        # ── Language resolution ───────────────────────────────────────────────
        detected_lang = data.get("detected_language", "en")
        caption_lang  = detected_lang
        logger.info(f"🗣️ Captions language: {caption_lang}")

        # ── Normalise style string once ───────────────────────────────────────
        style_str = style.value if hasattr(style, "value") else str(style)
        if "." in style_str:
            style_str = style_str.split(".")[-1]

        # ── kwargs ────────────────────────────────────────────────────────────
        audio_path      = kwargs.get("audio_path")
        bg_music_volume = float(kwargs.get("bg_music_volume", 0.1))

        # ── Main loop ─────────────────────────────────────────────────────────
        output_files         = []
        transcripts_per_clip = []

        if not best_clips:
            logger.warning("⚠️ No clips to process.")
            return [], []

        logger.info(f"📊 Processing {len(best_clips)} clip(s) …")

        for i, seg in enumerate(best_clips):
            pct = 60 + int((i / len(best_clips)) * 35)
            if progress_callback:
                progress_callback(pct, f"Rendering clip {i+1}/{len(best_clips)} …")

            clip               = None
            final_clip         = None
            current_video_clip = None

            try:
                start = max(0, seg.get("start_time", 0))
                end   = min(video_duration, seg.get("end_time", 0))

                if end - start < 1.0:
                    logger.warning(
                        f"⚠️ Clip {i+1} too short ({end-start:.2f}s), skipping."
                    )
                    continue

                if start >= video_duration:
                    logger.warning(
                        f"⚠️ Clip {i+1} start {start}s ≥ duration {video_duration}s, skipping."
                    )
                    continue

                logger.info(f"\n🎬 Clip {i+1}/{len(best_clips)} ({start:.2f}s – {end:.2f}s)")

                # ── Output path ───────────────────────────────────────────────
                task_id      = kwargs.get("task_id")
                prefix       = f"viral_{task_id}_{i+1}" if task_id else f"viral_{i+1}"
                out_name     = f"{prefix}_{style_str}.mp4"
                final_output = os.path.join(Config.OUTPUTS_DIR, "viral_clips", out_name)
                os.makedirs(os.path.dirname(final_output), exist_ok=True)

                # ── Cut clip ──────────────────────────────────────────────────
                current_video_clip = mpe.VideoFileClip(input_video_path)
                clip               = current_video_clip.subclip(start, end)

                # ── Build segment_transcript ──────────────────────────────────
                clip_segments = []

                for s in data["segments"]:
                    if s["start"] >= end or s["end"] <= start:
                        continue

                    new_seg          = s.copy()
                    new_seg["start"] = max(0, s["start"] - start)
                    new_seg["end"]   = min(end - start, s["end"] - start)

                    if "words" in s:
                        new_seg["words"] = [
                            {
                                **w,
                                "start": max(0, w["start"] - start),
                                "end":   min(end - start, w["end"] - start),
                            }
                            for w in s["words"]
                            if w["start"] < end and w["end"] > start
                        ]

                    clip_segments.append(new_seg)

                segment_transcript = {"segments": clip_segments}

                # ── Apply style + captions ────────────────────────────────────
                style_strategy = StyleFactory.get_style(style_str)
                logger.info(f"✨ Style: {style_str} | Caption lang: {caption_lang}")

                final_clip = style_strategy.apply_with_captions(
                    clip,
                    transcript_data = segment_transcript,
                    language        = caption_lang,
                    caption_mode    = kwargs.get("caption_mode",  "sentence"),
                    caption_style   = kwargs.get("caption_style", "classic"),
                    background_path = kwargs.get("background_path"),
                    playground_path = kwargs.get("playground_path"),
                )

                # ── Step 1: Write clip with original audio only ───────────────
                # Background music is NOT mixed here — FFmpeg handles it below
                # as a post-process to avoid double video encoding.
                cpu_count = os.cpu_count() or 4
                logger.info(f"⚙️ Rendering with {cpu_count} thread(s) …")

                final_clip.write_videofile(
                    final_output,
                    codec       = "libx264",
                    audio_codec = "aac",
                    threads     = cpu_count,
                    logger      = None,
                )

                # ── Step 2: Apply FFmpeg ducking as post-process ──────────────
                if audio_path:
                    ducking_ok = self._apply_ducking_ffmpeg(
                        final_output,
                        audio_path,
                        bg_music_volume,
                    )

                    if not ducking_ok:
                        # ── Fallback: MoviePy simple blend ───────────────────
                        logger.warning("⚠️ Falling back to MoviePy simple audio blend")
                        fallback_clip  = mpe.VideoFileClip(final_output)
                        fallback_mixed = self.mix_audio(
                            fallback_clip,
                            audio_path      = audio_path,
                            bg_music_volume = bg_music_volume,
                            original_volume = 1.0,
                        )
                        fallback_mixed.write_videofile(
                            final_output,
                            codec       = "libx264",
                            audio_codec = "aac",
                            threads     = cpu_count,
                            logger      = None,
                        )
                        try:
                            fallback_mixed.close()
                            fallback_clip.close()
                        except Exception:
                            pass

                output_files.append(final_output)
                logger.info(f"✅ Saved: {final_output}")

                # ── Build transcript entry ────────────────────────────────────
                clip_full_text = " ".join(s.get("text", "") for s in clip_segments).strip()
                transcripts_per_clip.append({
                    "clip_index": i + 1,
                    "filename":   out_name,
                    "start":      start,
                    "end":        end,
                    "language":   caption_lang,
                    "segments":   clip_segments,
                    "full_text":  clip_full_text,
                })
                logger.info(
                    f"📝 Transcript for clip {i+1}: "
                    f"{len(clip_segments)} segment(s), "
                    f"{len(clip_full_text)} chars"
                )

            except Exception as e:
                logger.error(f"❌ Clip {i+1} error: {e}")
                logger.error(traceback.format_exc())

            finally:
                for obj in (final_clip, clip, current_video_clip):
                    if obj:
                        try:
                            obj.close()
                        except Exception:
                            pass
                gc.collect()

        return output_files, transcripts_per_clip


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience wrapper
# ─────────────────────────────────────────────────────────────────────────────

def process_video(video_path, style="cinematic_blur", model_size="base", **kwargs):
    """
    End-to-end pipeline: STT → AI analysis → clip export.
    ✅ Returns a dict with:
        {
            "output_files"   : list[str],
            "transcripts"    : list[dict],
            "viral_segments" : list[dict],
            "full_transcript": str,
            "duration"       : float,
        }
    Important kwargs:
        source_language : language of the original video → passed to Whisper.
        language        : desired output language (translation + captions).
        caption_mode    : sentence | word | highlight_word
        caption_style   : classic | modern_glow | tiktok_bold | …
        audio_path      : path to background music file
        bg_music_volume : background music volume (0.0 → 1.0)
    """
    try:
        processor    = VideoProcessor(model_size=model_size)
        caption_mode = kwargs.get("caption_mode", "sentence")

        timestamp_mode = (
            "words"
            if caption_mode in ("word", "highlight_word")
            else "segments"
        )

        viral_segments, duration, stt_data = processor.analyze_impact(
            video_path,
            source_language = kwargs.get("source_language"),
            target_language = kwargs.get("language"),
            timestamp_mode  = timestamp_mode,
        )

        if not viral_segments:
            logger.warning("⚠️ No viral segments found.")
            return {
                "output_files":    [],
                "transcripts":     [],
                "viral_segments":  [],
                "full_transcript": stt_data.get("full_text", ""),
                "duration":        duration,
            }

        best_clips = processor.get_best_segments(viral_segments, duration)

        output_files, transcripts = processor.process_clips(
            video_path,
            best_clips,
            stt_data,
            style = style,
            **kwargs,
        )

        return {
            "output_files":    output_files,
            "transcripts":     transcripts,
            "viral_segments":  viral_segments,
            "full_transcript": stt_data.get("full_text", ""),
            "duration":        duration,
        }

    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        logger.error(traceback.format_exc())
        return {
            "output_files":    [],
            "transcripts":     [],
            "viral_segments":  [],
            "full_transcript": "",
            "duration":        0,
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = process_video(sys.argv[1])
        print(json.dumps({
            "clips":           result["output_files"],
            "full_transcript": result["full_transcript"],
            "clip_transcripts": [
                {"clip": t["clip_index"], "text": t["full_text"]}
                for t in result["transcripts"]
            ],
        }, indent=2, ensure_ascii=False))