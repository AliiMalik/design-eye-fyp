"""Letterbox preprocessing + padding-aware postprocessing.

The letterbox offsets returned by :func:`letterbox_resize` MUST be used to crop
the padding off the 224x224 saliency map before it is rescaled back to the
original image size. Skipping the crop leaves the heatmap visibly offset from
the UI on every non-square upload (BUILD.md section 3, correctness requirement).
"""

from dataclasses import dataclass

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps

IMG_SIZE = 224
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)


@dataclass(frozen=True)
class LetterboxMeta:
    """Geometry needed to undo a letterbox transform."""

    orig_width: int
    orig_height: int
    content_width: int   # width of the real image content inside the canvas
    content_height: int
    pad_left: int
    pad_top: int
    size: int = IMG_SIZE

    @property
    def crop_box(self) -> tuple[int, int, int, int]:
        """(top, left, bottom, right) of the content region in canvas space."""
        return (
            self.pad_top,
            self.pad_left,
            self.pad_top + self.content_height,
            self.pad_left + self.content_width,
        )


def letterbox_resize(img, size=IMG_SIZE, fill=(255, 255, 255)):
    img = img.copy()
    img.thumbnail((size, size), Image.LANCZOS)
    dw, dh = size - img.width, size - img.height
    padding = (dw // 2, dh // 2, dw - dw // 2, dh - dh // 2)
    return ImageOps.expand(img, padding, fill=fill)


def letterbox_with_meta(img: Image.Image, size: int = IMG_SIZE
                        ) -> tuple[Image.Image, LetterboxMeta]:
    """Letterbox an image and report the geometry needed to reverse it."""
    orig_w, orig_h = img.size
    probe = img.copy()
    probe.thumbnail((size, size), Image.LANCZOS)
    dw, dh = size - probe.width, size - probe.height
    meta = LetterboxMeta(
        orig_width=orig_w,
        orig_height=orig_h,
        content_width=probe.width,
        content_height=probe.height,
        pad_left=dw // 2,
        pad_top=dh // 2,
        size=size,
    )
    return letterbox_resize(img, size=size), meta


def preprocess(img):
    arr = np.array(img.convert("RGB")).astype(np.float32) / 255.0
    t = torch.from_numpy(arr).permute(2, 0, 1)
    t = (t - MEAN) / STD
    return t


def unletterbox_saliency(saliency: np.ndarray, meta: LetterboxMeta) -> np.ndarray:
    """Crop letterbox padding off a saliency map and rescale to original size.

    Returns a float32 array of shape ``(orig_height, orig_width)``.
    """
    top, left, bottom, right = meta.crop_box
    cropped = saliency[top:bottom, left:right]
    if cropped.size == 0:  # degenerate geometry; fall back to the whole canvas
        cropped = saliency
    resized = cv2.resize(
        cropped.astype(np.float32),
        (meta.orig_width, meta.orig_height),
        interpolation=cv2.INTER_CUBIC,
    )
    return resized.astype(np.float32)


def minmax_normalise(arr: np.ndarray) -> np.ndarray:
    """Scale an array into [0, 1]; a constant array becomes all zeros."""
    lo = float(arr.min())
    hi = float(arr.max())
    if hi - lo < 1e-12:
        return np.zeros_like(arr, dtype=np.float32)
    return ((arr - lo) / (hi - lo)).astype(np.float32)
