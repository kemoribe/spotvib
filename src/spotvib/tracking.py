"""Color contrast, connected components and subpixel spot localization."""

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import curve_fit


@dataclass(frozen=True)
class Spot:
    x: float
    y: float
    peak: float
    area: int
    method: str


def contrast(frame, color):
    blue, green, red = np.moveaxis(frame.astype(np.float32), -1, 0)
    if color == "red":
        return red - np.maximum(green, blue)
    return green - np.maximum(red, blue)


def gaussian(xy, amplitude, x, y, sx, sy, floor):
    xx, yy = xy
    return floor + amplitude * np.exp(-0.5 * (((xx-x)/sx)**2 + ((yy-y)/sy)**2))


def locate(plane, roi, previous, radius, min_peak, fit):
    left, top, width, height = roi
    right, bottom = left + width, top + height
    if previous is not None:
        x, y = round(previous[0]), round(previous[1])
        left, right = max(left, x-radius), min(right, x+radius+1)
        top, bottom = max(top, y-radius), min(bottom, y+radius+1)
    patch = plane[top:bottom, left:right]
    if min(patch.shape) < 3:
        return None
    border = np.r_[patch[0], patch[-1], patch[:, 0], patch[:, -1]]
    signal = np.maximum(patch - np.median(border), 0)
    smooth = cv2.GaussianBlur(signal, (5, 5), 0)
    _, peak, _, (px, py) = cv2.minMaxLoc(smooth)
    if peak < min_peak:
        return None
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        (smooth > 0.45 * peak).astype(np.uint8), connectivity=8
    )
    label = labels[py, px]
    area = int(stats[label, cv2.CC_STAT_AREA])
    if area < 3:
        return None
    # Expand the component locally to capture the edge of the spot.
    x0, x1 = max(0, px-8), min(patch.shape[1], px+9)
    y0, y1 = max(0, py-8), min(patch.shape[0], py+9)
    local = signal[y0:y1, x0:x1]
    mask = cv2.dilate((labels[y0:y1, x0:x1] == label).astype(np.uint8),
                      np.ones((3, 3), np.uint8))
    weights = (local * mask)**1.5
    yy, xx = np.mgrid[y0:y1, x0:x1]
    if not weights.sum():
        return None
    x = float(np.sum(xx * weights) / weights.sum())
    y = float(np.sum(yy * weights) / weights.sum())
    method = "centroid"
    if fit and peak >= 12 and min(local.shape) >= 7:
        try:
            params, _ = curve_fit(
                gaussian, (xx.ravel(), yy.ravel()), (local * mask).ravel(),
                p0=(local.max(), x, y, 2, 2, 0),
                bounds=((0, max(x0, x-3), max(y0, y-3), .6, .6, -20),
                        (np.inf, min(x1-1, x+3), min(y1-1, y+3), 8, 8, np.inf)),
                maxfev=150,
            )
            x, y = map(float, params[1:3])
            method = "gaussian"
        except (RuntimeError, ValueError):
            pass
    return Spot(x+left, y+top, peak, area, method)


class Registration:
    """Estimate translation on a fixed, textured background ROI."""

    def __init__(self, roi, min_response):
        self.roi = roi
        self.min_response = min_response
        self.previous = None
        self.offset = np.zeros(2)
        self.segment = 0
        self.window = cv2.createHanningWindow(tuple(roi[2:]), cv2.CV_32F)

    def update(self, frame):
        x, y, w, h = self.roi
        gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY).astype(np.float32)
        response = None
        valid = True
        if self.previous is not None:
            shift, response = cv2.phaseCorrelate(self.previous.copy(), gray.copy(), self.window)
            valid = (np.isfinite(response) and response >= self.min_response
                     and np.isfinite(shift).all() and np.linalg.norm(shift) < min(w, h)/4)
            if valid:
                self.offset += shift
            else:
                self.segment += 1
                self.offset[:] = 0
        self.previous = gray
        return self.offset.copy(), response, self.segment, valid
