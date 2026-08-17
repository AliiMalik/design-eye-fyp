"""Simulated scanpath playback: frame compositing plus GIF and MP4 encoding.

What this is, precisely: the model predicts WHERE attention concentrates, not
WHEN. The playback orders those peaks by predicted strength and spaces them with
dwell times taken from the eye-movement literature. It is a legible presentation
of a spatial prediction, not a recording of real gaze and not a temporal
prediction. Wording shown to users says exactly that.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.analytics import SACCADE_MS, scanpath_timeline

logger = logging.getLogger(__name__)

FPS = 25
MAX_LONG_SIDE = 900          # keeps GIF weight sane and h264 encoding quick
TRAIL_ALPHA = 0.55
DIM_FACTOR = 0.45            # how much the unvisited image is darkened
GAZE_RADIUS = 26
HALO_RADIUS = 78

ACCENT = (237, 92, 92)       # RGB, current gaze
VISITED = (79, 91, 213)      # RGB, already-seen fixations
FIRST = (124, 58, 237)       # RGB, rank 1


class FFmpegUnavailable(RuntimeError):
    """ffmpeg is not installed in this environment."""


@dataclass
class ScanpathClip:
    frames: list[np.ndarray]   # RGB uint8
    width: int
    height: int
    fps: int
    duration_ms: int


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _even(value: int) -> int:
    """h264 requires even dimensions."""
    return value if value % 2 == 0 else value - 1


def _fit(image: Image.Image) -> tuple[Image.Image, float]:
    scale = min(1.0, MAX_LONG_SIDE / float(max(image.size)))
    if scale >= 1.0:
        width, height = image.size
    else:
        width, height = int(image.width * scale), int(image.height * scale)
    width, height = max(2, _even(width)), max(2, _even(height))
    return image.resize((width, height), Image.LANCZOS), width / float(image.width)


def _gaze_position(timeline: list[dict], t_ms: int) -> tuple[float, float, int]:
    """Gaze point at time t. Returns (x, y, fixations_completed).

    During a dwell the point rests on the fixation; between dwells it travels
    linearly, which is what makes the motion read as a saccade.
    """
    for i, step in enumerate(timeline):
        if t_ms < step["start_ms"]:
            previous = timeline[i - 1]
            span = max(1, step["start_ms"] - previous["end_ms"])
            progress = (t_ms - previous["end_ms"]) / span
            progress = min(1.0, max(0.0, progress))
            x = previous["x"] + (step["x"] - previous["x"]) * progress
            y = previous["y"] + (step["y"] - previous["y"]) * progress
            return x, y, i
        if t_ms <= step["end_ms"]:
            return float(step["x"]), float(step["y"]), i + 1

    last = timeline[-1]
    return float(last["x"]), float(last["y"]), len(timeline)


def _draw_frame(base: np.ndarray, timeline: list[dict], scale: float,
                t_ms: int) -> np.ndarray:
    """Composite one frame: dimmed page, revealed trail, foveal spotlight."""
    height, width = base.shape[:2]
    gx, gy, seen = _gaze_position(timeline, t_ms)
    gx, gy = gx * scale, gy * scale

    # Dim the page, then lift a soft circle around the current gaze so the eye
    # is drawn where the prediction says a viewer would be looking.
    frame = (base.astype(np.float32) * DIM_FACTOR)
    spotlight = np.zeros((height, width), dtype=np.float32)
    cv2.circle(spotlight, (int(gx), int(gy)), HALO_RADIUS, 1.0, -1)
    spotlight = cv2.GaussianBlur(spotlight, (0, 0), HALO_RADIUS / 2.2)
    if spotlight.max() > 0:
        spotlight /= spotlight.max()
    frame = frame + base.astype(np.float32) * (1.0 - DIM_FACTOR) * spotlight[..., None]
    frame = np.clip(frame, 0, 255).astype(np.uint8)

    overlay = frame.copy()

    # Trail through the fixations already reached.
    points = [(int(s["x"] * scale), int(s["y"] * scale)) for s in timeline[:seen]]
    for a, b in zip(points, points[1:]):
        cv2.line(overlay, a, b, VISITED, 3, cv2.LINE_AA)
    if points:
        cv2.line(overlay, points[-1], (int(gx), int(gy)), VISITED, 2, cv2.LINE_AA)

    for i, (px, py) in enumerate(points):
        colour = FIRST if i == 0 else VISITED
        cv2.circle(overlay, (px, py), 17, colour, -1, cv2.LINE_AA)
        cv2.circle(overlay, (px, py), 17, (255, 255, 255), 2, cv2.LINE_AA)
        label = str(timeline[i]["rank"])
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.putText(overlay, label, (px - tw // 2, py + th // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

    frame = cv2.addWeighted(overlay, TRAIL_ALPHA, frame, 1 - TRAIL_ALPHA, 0)

    # The travelling gaze marker sits above everything, at full strength.
    cv2.circle(frame, (int(gx), int(gy)), GAZE_RADIUS, ACCENT, 3, cv2.LINE_AA)
    cv2.circle(frame, (int(gx), int(gy)), 5, ACCENT, -1, cv2.LINE_AA)

    return frame


def build_clip(image: Image.Image, nodes: list[dict],
               hold_ms: int = 700) -> ScanpathClip:
    """Render the playback frames for one mockup.

    ``nodes`` are dicts with x, y, rank, intensity in ORIGINAL pixel space.
    ``hold_ms`` keeps the completed path on screen so a looping GIF is readable.
    """
    if not nodes:
        raise ValueError("A scanpath needs at least one fixation")

    from app.services.analytics import FocusNodeData

    typed = [FocusNodeData(x=int(n["x"]), y=int(n["y"]), rank=int(n["rank"]),
                           intensity=float(n.get("intensity", 0.5))) for n in nodes]
    timeline = scanpath_timeline(typed)

    fitted, scale = _fit(image.convert("RGB"))
    base = np.array(fitted, dtype=np.uint8)

    total_ms = timeline[-1]["end_ms"] + hold_ms
    step_ms = int(1000 / FPS)
    frames = [_draw_frame(base, timeline, scale, t)
              for t in range(0, total_ms, step_ms)]

    return ScanpathClip(frames=frames, width=base.shape[1], height=base.shape[0],
                        fps=FPS, duration_ms=total_ms)


def encode_gif(clip: ScanpathClip) -> bytes:
    """Animated GIF via Pillow. No external binary required."""
    images = [Image.fromarray(f) for f in clip.frames]
    buf = io.BytesIO()
    images[0].save(
        buf, format="GIF", save_all=True, append_images=images[1:],
        duration=int(1000 / clip.fps), loop=0, optimize=True,
        disposal=2,
    )
    return buf.getvalue()


def encode_mp4(clip: ScanpathClip) -> bytes:
    """H.264 MP4: raw RGB frames in over stdin, encoded to a temporary file.

    The output cannot be a pipe. MP4 patches its moov atom after the frames are
    written, so the muxer needs a seekable target -- piping to stdout fails with
    "muxer does not support non seekable output". Fragmented MP4
    (frag_keyframe+empty_moov) would stream, but produces a file some editors and
    slide tools refuse; a temp file keeps +faststart and maximum compatibility,
    which matters because this artefact gets embedded in reports and decks.
    """
    binary = ffmpeg_path()
    if binary is None:
        raise FFmpegUnavailable(
            "ffmpeg is not installed, so MP4 export is unavailable. "
            "Download the GIF instead."
        )

    payload = b"".join(frame.tobytes() for frame in clip.frames)

    with tempfile.TemporaryDirectory(prefix="designeye-scanpath-") as tmp:
        target = Path(tmp) / "scanpath.mp4"
        command = [
            binary, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{clip.width}x{clip.height}", "-r", str(clip.fps),
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(target),
        ]
        process = subprocess.run(command, input=payload, capture_output=True,
                                 timeout=180)
        if process.returncode != 0 or not target.is_file():
            detail = process.stderr.decode("utf-8", "replace")[:300]
            logger.error("ffmpeg failed (%s): %s", process.returncode, detail)
            raise RuntimeError("Could not encode the MP4.")
        return target.read_bytes()


def filmstrip(clip: ScanpathClip, columns: int = 3, rows: int = 2) -> bytes:
    """Contact sheet of evenly spaced frames, for the PDF (which cannot animate)."""
    wanted = columns * rows
    if not clip.frames:
        raise ValueError("No frames to lay out")

    indices = np.linspace(0, len(clip.frames) - 1, wanted).astype(int)
    tile_w, tile_h = clip.width // 2, clip.height // 2
    sheet = Image.new("RGB", (tile_w * columns, tile_h * rows), (255, 255, 255))

    for position, index in enumerate(indices):
        tile = Image.fromarray(clip.frames[index]).resize((tile_w, tile_h), Image.LANCZOS)
        sheet.paste(tile, ((position % columns) * tile_w, (position // columns) * tile_h))

    buf = io.BytesIO()
    sheet.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
