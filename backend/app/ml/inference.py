"""Model loading (process-wide singleton) and the saliency inference pipeline."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from app.ml.model import SalGANGenerator
from app.ml.preprocess import (
    LetterboxMeta,
    letterbox_with_meta,
    minmax_normalise,
    preprocess,
    unletterbox_saliency,
)

logger = logging.getLogger(__name__)

_model: SalGANGenerator | None = None
_model_meta: dict = {}
_lock = threading.Lock()

HEATMAP_ALPHA = 0.72        # peak opacity at maximum predicted attention
HEATMAP_ALPHA_GAMMA = 0.65  # falloff curve for the per-pixel alpha


@dataclass
class SaliencyOutput:
    """Result of one forward pass, in ORIGINAL image pixel space."""

    saliency: np.ndarray        # float32 (H, W) in [0, 1], original dimensions
    overlay_bgr: np.ndarray     # uint8 (H, W, 3) JET overlay, BGR for cv2.imwrite
    inference_time_ms: int
    letterbox: LetterboxMeta


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_model(weights_path: str | Path, device: torch.device | None = None
               ) -> SalGANGenerator:
    """Load the checkpoint once per process and cache it.

    Handles both checkpoint layouts: a wrapper dict carrying the generator under
    ``"G"`` (alongside ``epoch`` / ``val`` metadata) and a raw ``state_dict``.
    """
    global _model, _model_meta
    if _model is not None:
        return _model

    with _lock:
        if _model is not None:  # another thread won the race
            return _model

        device = device or get_device()
        path = Path(weights_path)
        if not path.is_file():
            raise FileNotFoundError(f"Model weights not found at {path}")

        ckpt = torch.load(path, map_location=device, weights_only=False)
        if isinstance(ckpt, dict) and "G" in ckpt:
            state_dict = ckpt["G"]
            meta = {
                "epoch": ckpt.get("epoch"),
                "val": ckpt.get("val"),
                "ui": ckpt.get("ui"),
                "checkpoint_model_version": ckpt.get("model_version"),
            }
        else:
            state_dict = ckpt
            meta = {"epoch": None, "val": None}

        model = SalGANGenerator(pretrained=False)
        model.load_state_dict(state_dict, strict=True)
        model.eval().to(device)

        _model = model
        _model_meta = {**meta, "device": str(device), "weights_path": str(path)}
        logger.info(
            "Saliency model loaded | device=%s epoch=%s val=%s",
            device, meta.get("epoch"), meta.get("val"),
        )
        return _model


def get_model() -> SalGANGenerator | None:
    return _model


def is_loaded() -> bool:
    return _model is not None


def get_model_meta() -> dict:
    return dict(_model_meta)


def predict_saliency(img: Image.Image, model: SalGANGenerator | None = None
                     ) -> SaliencyOutput:
    """Run one forward pass and return a saliency map in original pixel space."""
    model = model or _model
    if model is None:
        raise RuntimeError("Model is not loaded; call load_model() first.")

    device = next(model.parameters()).device
    rgb = img.convert("RGB")
    canvas, meta = letterbox_with_meta(rgb)
    tensor = preprocess(canvas).unsqueeze(0).to(device)

    start = time.perf_counter()
    with torch.no_grad():
        logits = model(tensor)
        saliency_224 = torch.sigmoid(logits).squeeze().cpu().numpy()
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # Crop the letterbox padding BEFORE rescaling, or the heatmap sits offset
    # from the UI on every non-square upload.
    saliency = unletterbox_saliency(saliency_224.astype(np.float32), meta)
    saliency = minmax_normalise(saliency)

    overlay = build_overlay(rgb, saliency)
    return SaliencyOutput(
        saliency=saliency,
        overlay_bgr=overlay,
        inference_time_ms=elapsed_ms,
        letterbox=meta,
    )


# --- aspect-aware inference ------------------------------------------------
#
# The model's input is a fixed 224x224 square, so a tall upload is letterboxed
# into a narrow strip of it. A 2.75:1 phone screen occupies 81x224 -- the model
# genuinely sees the design 81 pixels wide, and the saliency it returns is that
# coarse. Coarse saliency is diffuse saliency, entropy rises, and the focus term
# collapses.
#
# Measured across every screen available, aspect ratio correlates with the
# Clarity Score at Spearman -0.730: landscape screens score 73-98, phone screens
# 15-39. The cause is the frame, not the design -- squashing the SAME pixels to
# square triples focus_raw (0.0560 -> 0.0875 on the messages screen), and
# stretching a desktop screen to 2.75:1 drops it from 0.918 to 0.498.
#
# So a tall frame is split into near-square bands, each of which fills the
# model's input properly, and the results are reassembled. This is a RESOLUTION
# technique, not a perceptual claim: the user sees the whole screen at once, so
# the bands are stitched back into one map and scored once. That is the
# difference between this and services/viewports.py, which splits a scrolling
# page because nobody sees all of it at once and scores each screenful.

# Below this the letterbox waste is not worth a second forward pass, and it
# keeps every calibration sample (all wider than 1.1:1) on the original path so
# TC-07 and TC-08 are untouched.
MIN_TILED_ASPECT = 1.5
MAX_INFERENCE_TILES = 4
INFERENCE_TILE_OVERLAP = 0.10


def inference_tile_count(width: int, height: int) -> int:
    """How many near-square bands this frame should be split into."""
    aspect = height / float(max(1, width))
    if aspect < MIN_TILED_ASPECT:
        return 1
    return max(1, min(MAX_INFERENCE_TILES, int(round(aspect))))


def _bands(height: int, n: int) -> list[tuple[int, int]]:
    step = height / n
    pad = step * INFERENCE_TILE_OVERLAP
    out = []
    for i in range(n):
        out.append((max(0, int(round(i * step - pad))),
                    min(height, int(round((i + 1) * step + pad)))))
    return out


def predict_saliency_hires(img: Image.Image, model: SalGANGenerator | None = None
                           ) -> SaliencyOutput:
    """Saliency for one frame, recovering the resolution a tall frame loses.

    Near-square frames take the ordinary single-pass path unchanged.
    """
    n = inference_tile_count(img.width, img.height)
    if n <= 1:
        return predict_saliency(img, model)

    model = model or _model
    if model is None:
        raise RuntimeError("Model is not loaded; call load_model() first.")
    device = next(model.parameters()).device

    rgb = img.convert("RGB")
    width, height = rgb.size
    total = np.zeros((height, width), dtype=np.float32)
    weight = np.zeros((height, width), dtype=np.float32)
    elapsed_ms = 0
    first_meta: LetterboxMeta | None = None

    for top, bottom in _bands(height, n):
        canvas, meta = letterbox_with_meta(rgb.crop((0, top, width, bottom)))
        tensor = preprocess(canvas).unsqueeze(0).to(device)

        start = time.perf_counter()
        with torch.no_grad():
            band = torch.sigmoid(model(tensor)).squeeze().cpu().numpy()
        elapsed_ms += int((time.perf_counter() - start) * 1000)

        # Deliberately NOT normalised per band. Sigmoid output is on an absolute
        # scale, so leaving it raw keeps bands comparable; normalising each one
        # first would stretch a quiet band up to match a busy one, flatten the
        # stitched map and cost the very focus this is meant to recover.
        band = unletterbox_saliency(band.astype(np.float32), meta)

        rows = bottom - top
        feather = np.ones(rows, dtype=np.float32)
        ramp = max(1, int(rows * INFERENCE_TILE_OVERLAP))
        if top > 0:
            feather[:ramp] = np.linspace(0.0, 1.0, ramp, dtype=np.float32)
        if bottom < height:
            feather[-ramp:] = np.linspace(1.0, 0.0, ramp, dtype=np.float32)

        total[top:bottom] += band * feather[:, None]
        weight[top:bottom] += feather[:, None]
        first_meta = first_meta or meta

    np.divide(total, weight, out=total, where=weight > 1e-6)
    saliency = minmax_normalise(total)      # once, over the whole frame

    assert first_meta is not None
    return SaliencyOutput(
        saliency=saliency,
        overlay_bgr=build_overlay(rgb, saliency),
        inference_time_ms=elapsed_ms,
        letterbox=first_meta,
    )


def build_overlay(img: Image.Image, saliency: np.ndarray,
                  alpha: float = HEATMAP_ALPHA) -> np.ndarray:
    """Alpha-blend a JET colormap of ``saliency`` over ``img``. Returns BGR.

    ``alpha`` is the peak opacity, reached only where predicted attention is
    highest; it falls off with intensity so cold regions stay legible. A flat
    blend at 0.5 everywhere (the literal BUILD.md wording) tints the whole
    mockup JET-blue wherever attention is near zero, which hides the very design
    being reviewed. See docs/DEVIATIONS.md.
    """
    base_rgb = np.array(img.convert("RGB"), dtype=np.uint8)
    base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)

    if saliency.shape[:2] != base_bgr.shape[:2]:
        saliency = cv2.resize(
            saliency, (base_bgr.shape[1], base_bgr.shape[0]),
            interpolation=cv2.INTER_CUBIC,
        )

    heat_u8 = np.clip(saliency * 255.0, 0, 255).astype(np.uint8)
    heat_bgr = cv2.applyColorMap(heat_u8, cv2.COLORMAP_JET).astype(np.float32)

    # Gamma < 1 keeps mid-intensity regions readable without flooding the cold ones.
    weight = (np.clip(saliency, 0.0, 1.0) ** HEATMAP_ALPHA_GAMMA) * alpha
    weight = weight[..., None].astype(np.float32)

    blended = heat_bgr * weight + base_bgr.astype(np.float32) * (1.0 - weight)
    return np.clip(blended, 0, 255).astype(np.uint8)
