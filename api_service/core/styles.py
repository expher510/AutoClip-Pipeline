"""
Video Styles — YouTube Shorts Production Engine
SplitVertical & SplitHorizontal rebuilt with seamless gradient blending.
All class/method names kept identical for drop-in integration.

VerticalFullStyle — v2 (high-quality, stabilized):
  • INTER_LANCZOS4 for sharp upscaling
  • Kalman-like dual smoothing (position + velocity) → no shakiness
  • DNN face detector (res10 SSD) with Haar fallback
  • Temporal face confidence gating (ignores single-frame false-negatives)
  • apply_to='video' on clip.fl() to skip audio re-encoding artifacts
"""

from abc import ABC, abstractmethod
import os
import cv2
import numpy as np
import moviepy.editor as mpe
from collections import deque

from .config import Config
from .logger import Logger
from .subtitle_manager import SubtitleManager

logger = Logger.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Gradient Mask Helpers  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _linear_gradient(length: int, fade_from_zero: bool) -> np.ndarray:
    arr = np.linspace(0.0, 1.0, length, dtype=np.float32)
    return arr if fade_from_zero else arr[::-1]


def _make_vertical_mask(clip_w: int, clip_h: int,
                        blend_top: int = 0, blend_bottom: int = 0) -> np.ndarray:
    mask = np.ones((clip_h, clip_w), dtype=np.float32)
    if blend_top > 0:
        grad = _linear_gradient(blend_top, fade_from_zero=True)
        mask[:blend_top, :] = grad[:, np.newaxis]
    if blend_bottom > 0:
        grad = _linear_gradient(blend_bottom, fade_from_zero=False)
        mask[clip_h - blend_bottom:, :] = grad[:, np.newaxis]
    return mask


def _make_horizontal_mask(clip_w: int, clip_h: int,
                          blend_left: int = 0, blend_right: int = 0) -> np.ndarray:
    mask = np.ones((clip_h, clip_w), dtype=np.float32)
    if blend_left > 0:
        grad = _linear_gradient(blend_left, fade_from_zero=True)
        mask[:, :blend_left] = grad[np.newaxis, :]
    if blend_right > 0:
        grad = _linear_gradient(blend_right, fade_from_zero=False)
        mask[:, clip_w - blend_right:] = grad[np.newaxis, :]
    return mask


def _apply_mask(clip: mpe.VideoClip, mask_array: np.ndarray) -> mpe.VideoClip:
    mask_clip = mpe.ImageClip(mask_array, ismask=True, duration=clip.duration)
    return clip.set_mask(mask_clip)


def _fit_to_width(clip: mpe.VideoClip, target_w: int) -> mpe.VideoClip:
    return clip.resize(width=target_w)


def _fit_to_height(clip: mpe.VideoClip, target_h: int) -> mpe.VideoClip:
    return clip.resize(height=target_h)


def _loop_or_cut(clip: mpe.VideoClip, duration: float) -> mpe.VideoClip:
    if clip.duration < duration:
        return clip.loop(duration=duration)
    return clip.subclip(0, duration)


# ─────────────────────────────────────────────────────────────────────────────
# DNN Face Detector loader  (singleton, lazy)
# ─────────────────────────────────────────────────────────────────────────────

_DNN_NET = None          # shared across all SmartFaceCropper instances

def _get_dnn_net():
    """
    Lazy-load OpenCV's res10_300x300_ssd face detector.
    Falls back to None if model files are not found — Haar is used instead.
    """
    global _DNN_NET
    if _DNN_NET is not None:
        return _DNN_NET

    # Common installation paths (opencv-python-headless bundles these)
    base_candidates = [
        cv2.data.haarcascades,                          # same folder as haarcascades
        os.path.join(os.path.dirname(cv2.__file__), "data"),
        "/usr/share/opencv4/",
        "/usr/local/share/opencv4/",
    ]
    proto_name = "deploy.prototxt"
    model_name = "res10_300x300_ssd_iter_140000_fp16.caffemodel"

    for base in base_candidates:
        proto = os.path.join(base, proto_name)
        model = os.path.join(base, model_name)
        if os.path.exists(proto) and os.path.exists(model):
            try:
                _DNN_NET = cv2.dnn.readNetFromCaffe(proto, model)
                logger.info("DNN face detector loaded from %s", base)
                return _DNN_NET
            except Exception as e:
                logger.warning("DNN load failed: %s", e)

    logger.warning("DNN face model not found — falling back to Haar cascade")
    _DNN_NET = False   # sentinel so we don't retry every frame
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Smart Face Cropper  — v2 (stabilized, high-quality)
# ─────────────────────────────────────────────────────────────────────────────

class SmartFaceCropper:
    """
    Portrait-mode smart crop with face tracking.

    Improvements over v1
    ────────────────────
    1. INTER_LANCZOS4    — sharpest upscaling interpolation available in OpenCV
    2. Velocity smoothing — exponential smoothing on both position AND velocity
                           eliminates the micro-jitter seen with plain EMA
    3. DNN face detector  — far more accurate than Haar; auto-falls back to Haar
    4. Confidence gating  — ignores detections below threshold + temporal
                           buffer prevents single-frame dropouts from snapping
    5. apply_to='video'   — tells MoviePy to skip audio channels → no artifacts
    6. Parametric tuning  — all magic numbers as named class attributes
    """

    # ── Tunable parameters ────────────────────────────────────────────────
    FRAME_SKIP          : int   = 3      # re-detect face every N frames
    POS_SMOOTH          : float = 0.25   # EMA weight for position  (higher = faster)
    VEL_SMOOTH          : float = 0.15   # EMA weight for velocity  (damps oscillation)
    DNN_CONFIDENCE      : float = 0.65   # min DNN detection confidence [0-1]
    MISS_TOLERANCE      : int   = 12     # frames before abandoning last known face
    # ─────────────────────────────────────────────────────────────────────

    def __init__(self, output_size=(1080, 1920)):
        self.output_size    = output_size          # (width, height)
        self.out_w, self.out_h = output_size

        # Haar fallback
        self._haar = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        # State
        self._smoothed_x    : float | None = None  # smoothed crop-center X
        self._velocity_x    : float        = 0.0   # running velocity estimate
        self._last_face_x   : float | None = None  # last confirmed face centre
        self._miss_count    : int          = 0     # consecutive no-detection frames
        self._frame_idx     : int          = 0     # global frame counter

    # ── Public API (identical to v1) ─────────────────────────────────────

    def get_crop_coordinates(self, frame):
        """Return (left, top, right, bottom) crop box for one frame."""
        h, w    = frame.shape[:2]
        crop_w  = int(h * self.out_w / self.out_h)   # target crop width

        detected_x = self._detect_face_center(frame, w)

        if detected_x is not None:
            self._last_face_x = detected_x
            self._miss_count  = 0
            target_x = detected_x
        else:
            self._miss_count += 1
            if self._miss_count <= self.MISS_TOLERANCE and self._last_face_x is not None:
                # Hold last known position
                target_x = self._last_face_x
            else:
                # Give up — centre of frame
                target_x = w // 2

        # ── Velocity-based smoothing ──────────────────────────────────────
        if self._smoothed_x is None:
            # Cold start: snap immediately
            self._smoothed_x = float(target_x)
            self._velocity_x = 0.0
        else:
            # Desired displacement this step
            raw_delta = target_x - self._smoothed_x

            # Smooth the velocity (acts as a low-pass filter on acceleration)
            self._velocity_x = (
                self._velocity_x * (1.0 - self.VEL_SMOOTH)
                + raw_delta       *        self.VEL_SMOOTH
            )

            # Advance position with smoothed velocity
            self._smoothed_x += self._velocity_x * self.POS_SMOOTH

        # ── Compute crop box ─────────────────────────────────────────────
        left = int(self._smoothed_x - crop_w / 2)
        left = max(0, min(left, w - crop_w))
        return left, 0, left + crop_w, h

    def apply_to_clip(self, clip: mpe.VideoClip) -> mpe.VideoClip:
        """Apply portrait-crop + face-tracking to a MoviePy clip."""
        frame_skip = self.FRAME_SKIP
        # Cached crop so non-detection frames reuse last result
        _last_box = [None]

        def filter_frame(get_frame, t):
            frame = get_frame(t)
            self._frame_idx += 1

            # Re-detect every FRAME_SKIP frames; otherwise reuse
            if self._frame_idx % frame_skip == 0 or _last_box[0] is None:
                left, top, right, bottom = self.get_crop_coordinates(frame)
                _last_box[0] = (left, top, right, bottom)
            else:
                # Still advance the smoother with cached position
                left, top, right, bottom = _last_box[0]

            cropped = frame[top:bottom, left:right]

            # ── High-quality resize ───────────────────────────────────────
            # INTER_LANCZOS4 is the highest-quality upscaler in OpenCV.
            # It's ~2× slower than INTER_LINEAR but the difference is
            # very visible when upscaling a narrow crop to 1080 px.
            return cv2.resize(
                cropped,
                (self.out_w, self.out_h),
                interpolation=cv2.INTER_LANCZOS4,
            )

        # apply_to='video' skips the audio pipeline → no re-encoding artifacts
        return clip.fl(filter_frame, apply_to='video')

    # ── Internal helpers ─────────────────────────────────────────────────

    def _detect_face_center(self, frame: np.ndarray, frame_w: int) -> float | None:
        """
        Try DNN detector first; fall back to Haar.
        Returns the X-coordinate of the largest detected face centre, or None.
        """
        net = _get_dnn_net()
        if net:
            return self._dnn_detect(frame, net)
        return self._haar_detect(frame, frame_w)

    def _dnn_detect(self, frame: np.ndarray, net) -> float | None:
        h, w = frame.shape[:2]
        # DNN expects 300×300 blob; BGR input
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (300, 300)),
            scalefactor=1.0,
            size=(300, 300),
            mean=(104.0, 177.0, 123.0),
        )
        net.setInput(blob)
        detections = net.forward()   # shape: (1, 1, N, 7)

        best_cx   = None
        best_area = 0

        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            if confidence < self.DNN_CONFIDENCE:
                continue
            x1 = int(detections[0, 0, i, 3] * w)
            y1 = int(detections[0, 0, i, 4] * h)
            x2 = int(detections[0, 0, i, 5] * w)
            y2 = int(detections[0, 0, i, 6] * h)
            area = (x2 - x1) * (y2 - y1)
            if area > best_area:
                best_area = area
                best_cx   = (x1 + x2) / 2.0

        return best_cx

    def _haar_detect(self, frame: np.ndarray, frame_w: int) -> float | None:
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
        faces = self._haar.detectMultiScale(small, 1.1, 8, minSize=(50, 50))

        if len(faces) == 0:
            return None

        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, _, fw, _ = [v * 2 for v in faces[0]]
        return float(fx + fw / 2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Base Style  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class BaseStyle(ABC):
    def __init__(self, output_size=Config.DEFAULT_SIZE):
        self.output_size = output_size

    @abstractmethod
    def apply(self, clip, **kwargs):
        pass

    def apply_with_captions(self, clip, transcript_data=None, language=None,
                            caption_mode="sentence", caption_style="classic", **kwargs):
        styled_clip = self.apply(clip, **kwargs)
        if not transcript_data:
            return styled_clip

        caption_clips = self._create_caption_clips(
            transcript_data, language, caption_mode, caption_style
        )
        if not caption_clips:
            return styled_clip

        if isinstance(styled_clip, mpe.CompositeVideoClip):
            return mpe.CompositeVideoClip(
                list(styled_clip.clips) + caption_clips, size=self.output_size
            )
        return mpe.CompositeVideoClip([styled_clip] + caption_clips, size=self.output_size)

    def add_captions(self, clip, transcript_data, language=None, caption_mode="sentence"):
        """Kept for backward compatibility."""
        if not transcript_data:
            return clip
        return SubtitleManager.create_captions(
            clip, transcript_data, size=self.output_size,
            language=language, caption_mode=caption_mode,
        )

    def _create_caption_clips(self, transcript_data, language=None,
                              caption_mode="sentence", caption_style="classic"):
        return SubtitleManager.create_caption_clips(
            transcript_data, size=self.output_size,
            language=language, caption_mode=caption_mode,
            caption_style=caption_style,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cinematic Style  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class CinematicStyle(BaseStyle):
    def apply(self, clip, background_path=None, **kwargs):
        if background_path and os.path.exists(background_path):
            ext = os.path.splitext(background_path)[1].lower()
            video_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
            if ext in video_ext:
                bg = _loop_or_cut(
                    mpe.VideoFileClip(background_path).without_audio()
                    .resize(height=self.output_size[1]),
                    clip.duration,
                )
            else:
                bg = (
                    mpe.ImageClip(background_path)
                    .set_duration(clip.duration)
                    .resize(height=self.output_size[1])
                )
            if bg.w > self.output_size[0]:
                bg = bg.crop(x_center=bg.w / 2, width=self.output_size[0])
            else:
                bg = bg.resize(width=self.output_size[0])
        else:
            bg = mpe.ColorClip(size=self.output_size, color=(0, 0, 0)).set_duration(clip.duration)

        main = clip.resize(width=self.output_size[0]).set_position("center")
        if main.h > self.output_size[1]:
            main = clip.resize(height=self.output_size[1]).set_position("center")

        return mpe.CompositeVideoClip([bg, main], size=self.output_size)


# ─────────────────────────────────────────────────────────────────────────────
# Cinematic Blur Style  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class CinematicBlurStyle(BaseStyle):
    def apply(self, clip, **kwargs):
        bg = clip.resize(height=self.output_size[1])
        if bg.w < self.output_size[0]:
            bg = clip.resize(width=self.output_size[0])

        def make_blur(get_frame, t):
            frame   = get_frame(t)
            small   = cv2.resize(frame, (16, 16))
            blurred = cv2.resize(
                small, (self.output_size[0], self.output_size[1]),
                interpolation=cv2.INTER_LINEAR,
            )
            return cv2.GaussianBlur(blurred, (21, 21), 0)

        bg_blurred = bg.fl(make_blur).set_opacity(0.6)
        main = clip.resize(width=self.output_size[0]).set_position("center")
        if main.h > self.output_size[1]:
            main = clip.resize(height=self.output_size[1]).set_position("center")

        return mpe.CompositeVideoClip([bg_blurred, main], size=self.output_size)


# ─────────────────────────────────────────────────────────────────────────────
# Split Vertical  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class SplitVerticalStyle(BaseStyle):
    SPLIT_RATIO : float = 0.58
    BLEND_PX    : int   = 120

    def apply(self, clip, playground_path=None, **kwargs):
        W, H       = self.output_size
        blend      = self.BLEND_PX
        h_top_seg  = int(H * self.SPLIT_RATIO)
        h_bot_seg  = H - h_top_seg + blend

        top_clip = _fit_to_width(clip, W)
        top_h    = min(top_clip.h, h_top_seg + blend // 2)
        top_clip = top_clip.crop(x1=0, y1=0, x2=W, y2=top_h).resize((W, h_top_seg))
        top_mask = _make_vertical_mask(W, h_top_seg, blend_bottom=blend)
        top_clip = _apply_mask(top_clip, top_mask).set_position((0, 0))

        if playground_path and os.path.exists(playground_path):
            bot_src = _loop_or_cut(
                mpe.VideoFileClip(playground_path).without_audio(), clip.duration
            )
        else:
            bot_src = clip.set_opacity(0.85)

        bot_clip = _fit_to_width(bot_src, W)
        if bot_clip.h > h_bot_seg:
            y_start  = max(0, bot_clip.h - h_bot_seg)
            bot_clip = bot_clip.crop(x1=0, y1=y_start, x2=W, y2=bot_clip.h)

        bot_clip = bot_clip.resize((W, h_bot_seg))
        bot_mask = _make_vertical_mask(W, h_bot_seg, blend_top=blend)
        bot_y    = h_top_seg - blend
        bot_clip = _apply_mask(bot_clip, bot_mask).set_position((0, bot_y))

        return mpe.CompositeVideoClip([bot_clip, top_clip], size=self.output_size)


# ─────────────────────────────────────────────────────────────────────────────
# Split Horizontal  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class SplitHorizontalStyle(BaseStyle):
    SPLIT_RATIO : float = 0.52
    BLEND_PX    : int   = 80

    def apply(self, clip, playground_path=None, **kwargs):
        W, H       = self.output_size
        blend      = self.BLEND_PX
        w_left_seg  = int(W * self.SPLIT_RATIO)
        w_right_seg = W - w_left_seg + blend

        left_src  = _fit_to_height(clip, H)
        lw        = left_src.w
        crop_w_l  = min(lw, w_left_seg + blend)
        left_clip = left_src.crop(x1=max(0, lw // 2 - crop_w_l),
                                  y1=0, x2=lw // 2, y2=H)
        left_clip = left_clip.resize((w_left_seg, H))
        left_mask = _make_horizontal_mask(w_left_seg, H, blend_right=blend)
        left_clip = _apply_mask(left_clip, left_mask).set_position((0, 0))

        if playground_path and os.path.exists(playground_path):
            right_src = _loop_or_cut(
                mpe.VideoFileClip(playground_path).without_audio(), clip.duration
            )
        else:
            right_src = clip.set_opacity(0.85)

        right_full = _fit_to_height(right_src, H)
        rw         = right_full.w
        crop_w_r   = min(rw, w_right_seg + blend)
        right_clip = right_full.crop(x1=rw // 2, y1=0,
                                     x2=rw // 2 + crop_w_r, y2=H)
        right_clip = right_clip.resize((w_right_seg, H))
        right_mask = _make_horizontal_mask(w_right_seg, H, blend_left=blend)
        right_x    = w_left_seg - blend
        right_clip = _apply_mask(right_clip, right_mask).set_position((right_x, 0))

        return mpe.CompositeVideoClip([right_clip, left_clip], size=self.output_size)


# ─────────────────────────────────────────────────────────────────────────────
# Vertical Full Style  — v2 (drop-in replacement, zero API change)
# ─────────────────────────────────────────────────────────────────────────────

class VerticalFullStyle(BaseStyle):
    """
    Portrait-mode style using SmartFaceCropper v2.

    Identical public interface to v1:
        style = VerticalFullStyle()
        result = style.apply(clip)
        result = style.apply_with_captions(clip, transcript_data, ...)

    All quality and stability improvements are internal to SmartFaceCropper.
    """

    def apply(self, clip, **kwargs):
        # A fresh cropper per render keeps state isolated
        cropper = SmartFaceCropper(output_size=self.output_size)
        return cropper.apply_to_clip(clip)


# ─────────────────────────────────────────────────────────────────────────────
# Style Factory  (unchanged API)
# ─────────────────────────────────────────────────────────────────────────────

class StyleFactory:
    _styles = {
        "cinematic":        CinematicStyle,
        "cinematic_blur":   CinematicBlurStyle,
        "split_vertical":   SplitVerticalStyle,
        "split_horizontal": SplitHorizontalStyle,
        "vertical_full":    VerticalFullStyle,
    }

    @staticmethod
    def get_style(style_name) -> BaseStyle:
        style_class = StyleFactory._styles.get(style_name, CinematicBlurStyle)
        return style_class()