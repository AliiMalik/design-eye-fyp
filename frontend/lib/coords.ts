/**
 * The single conversion between API coordinates and screen coordinates.
 *
 * Every focus node, path segment, and hit test goes through here. API
 * coordinates are always in ORIGINAL image pixel space; nothing downstream may
 * do its own scaling maths (BUILD.md section 10).
 */

export interface ImageFit {
  /** Uniform scale from image pixels to stage pixels. */
  scale: number;
  /** Letterbox offsets inside the stage, in stage pixels. */
  offsetX: number;
  offsetY: number;
  /** Rendered size of the image inside the stage. */
  drawWidth: number;
  drawHeight: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Fit an image inside a container, preserving aspect ratio (contain). */
export function computeFit(
  imageWidth: number,
  imageHeight: number,
  containerWidth: number,
  containerHeight: number,
): ImageFit {
  if (imageWidth <= 0 || imageHeight <= 0 || containerWidth <= 0 || containerHeight <= 0) {
    return { scale: 1, offsetX: 0, offsetY: 0, drawWidth: 0, drawHeight: 0 };
  }
  const scale = Math.min(containerWidth / imageWidth, containerHeight / imageHeight);
  const drawWidth = imageWidth * scale;
  const drawHeight = imageHeight * scale;
  return {
    scale,
    offsetX: (containerWidth - drawWidth) / 2,
    offsetY: (containerHeight - drawHeight) / 2,
    drawWidth,
    drawHeight,
  };
}

/** Image pixel space -> stage pixel space. */
export function toScreenCoords(point: Point, fit: ImageFit): Point {
  return {
    x: point.x * fit.scale + fit.offsetX,
    y: point.y * fit.scale + fit.offsetY,
  };
}

/** Stage pixel space -> image pixel space. */
export function toImageCoords(point: Point, fit: ImageFit): Point {
  if (fit.scale === 0) return { x: 0, y: 0 };
  return {
    x: (point.x - fit.offsetX) / fit.scale,
    y: (point.y - fit.offsetY) / fit.scale,
  };
}

/** SVG path through the focus nodes, in stage coordinates. */
export function focusPath(nodes: Point[], fit: ImageFit): string {
  if (nodes.length === 0) return "";
  return nodes
    .map((n, i) => {
      const p = toScreenCoords(n, fit);
      return `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    })
    .join(" ");
}
