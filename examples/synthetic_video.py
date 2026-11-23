"""Generate a shareable 60 fps demo with known 6 Hz motion and camera drift."""

import argparse
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output filename.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    texture = rng.integers(20, 75, (240, 320), dtype=np.uint8)
    yy, xx = np.mgrid[:240, :320]
    writer = cv2.VideoWriter(str(args.output), cv2.VideoWriter_fourcc(*"mp4v"),
                             60, (320, 240))
    if not writer.isOpened():
        raise RuntimeError("MP4 encoder unavailable")
    try:
        for i in range(180):
            t = i/60
            drift = 1.5*t
            gray = cv2.warpAffine(texture, np.float32([[1, 0, drift], [0, 1, 0]]),
                                  (320, 240), borderMode=cv2.BORDER_REFLECT)
            frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            x = 160 + drift + 8*np.sin(2*np.pi*6*t)
            spot = 170*np.exp(-((xx-x)**2 + (yy-120)**2)/8)
            frame[:, :, 2] = np.clip(gray + spot, 0, 255).astype(np.uint8)
            writer.write(frame)
    finally:
        writer.release()


if __name__ == "__main__":
    main()
