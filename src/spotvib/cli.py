"""Video input, analysis and reproducible output files."""

import argparse
import csv
import json
import math
import sys
import tempfile
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analysis import analyze
from .report import write_report
from .tracking import Registration, contrast, locate


def track(video, dest, args):
    cap = cv2.VideoCapture(str(video))
    writer = None
    rows = []
    previous = None
    try:
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Cannot decode video: {video}")
        fps = args.fps or cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Video FPS unavailable. Supply --fps.")
        h, w = frame.shape[:2]
        roi = args.roi or (0, 0, w, int(h * args.top_fraction))
        for region in (roi, args.background_roi):
            if region is None:
                continue
            x, y, width, height = region
            if min(x, y) < 0 or min(width, height) < 3 or x+width > w or y+height > h:
                raise ValueError(f"ROI {region} is outside the {w}×{h} frame or too small")
        registration = (Registration(args.background_roi, args.registration_response)
                        if args.background_roi else None)
        if args.overlay:
            writer = cv2.VideoWriter(str(dest / "overlay.mp4"),
                                      cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            if not writer.isOpened():
                raise ValueError("Could not open MP4 encoder. Retry without --overlay.")
        while ok:
            color = contrast(frame, args.color)
            spot = locate(color, roi, previous, args.radius, args.min_peak, args.gaussian)
            reacquired = False
            if spot is None and previous is not None:
                spot = locate(color, roi, None, args.radius, args.min_peak, args.gaussian)
                reacquired = spot is not None
            if spot:
                previous = (spot.x, spot.y)
                reacquired |= bool(rows and rows[-1]["x_px"] is None)
            offset, response, segment, valid = (
                registration.update(frame) if registration else ((0., 0.), None, 0, True)
            )
            index = len(rows)
            rows.append(dict(
                frame=index, time_s=index/fps, x_px=spot.x if spot else None,
                y_px=spot.y if spot else None, peak=spot.peak if spot else None,
                area_px=spot.area if spot else None, method=spot.method if spot else "lost",
                reacquired=reacquired, camera_x_px=float(offset[0]), camera_y_px=float(offset[1]),
                registration_response=float(response) if response is not None and np.isfinite(response) else None,
                segment=segment,
                corrected_x_px=spot.x-float(offset[0]) if spot and valid else None,
                corrected_y_px=spot.y-float(offset[1]) if spot and valid else None,
            ))
            if writer is not None:
                if spot:
                    cv2.drawMarker(frame, (round(spot.x), round(spot.y)), (0, 255, 0),
                                   cv2.MARKER_CROSS, 17, 2)
                else:
                    cv2.putText(frame, "SPOT LOST", (8, 23), cv2.FONT_HERSHEY_SIMPLEX,
                                .6, (0, 0, 255), 1)
                writer.write(frame)
            ok, frame = cap.read()
    finally:
        if writer is not None:
            writer.release()
        cap.release()
    return rows, fps, roi


def plots(rows, dest, args, run, spectrum):
    time = [row["time_s"] for row in rows]
    unit = "mm" if args.mm_per_px else "px"
    scale = args.mm_per_px or 1
    fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
    for axis in ("x", "y"):
        data = np.array([row[f"displacement_{axis}_px"] for row in rows], float)
        ax.plot(time, data * scale, label=axis)
    if len(run):
        ax.axvspan(time[run[0]], time[run[-1]], alpha=.12, label="Metrics interval")
    ax.set(xlabel="Time (s)", ylabel=f"Displacement ({unit})")
    ax.legend()
    fig.savefig(dest / "time_series.png", dpi=140)
    plt.close(fig)
    if len(run) >= 2:
        xy = np.array([[rows[i]["displacement_x_px"], rows[i]["displacement_y_px"]]
                       for i in run]) * scale
        fig, ax = plt.subplots(figsize=(5, 5), layout="constrained")
        ax.plot(*xy.T, marker=".", markersize=2)
        ax.set(xlabel=f"X ({unit})", ylabel=f"Y ({unit})", aspect="equal")
        ax.invert_yaxis()
        fig.savefig(dest / "trajectory.png", dpi=140)
        plt.close(fig)
    if spectrum is not None:
        freq, power = spectrum
        fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
        ax.plot(freq, power[:, 0], label="x")
        ax.plot(freq, power[:, 1], label="y")
        ax.set(xlabel="Observed frequency (Hz)", ylabel=f"PSD ({unit}²/Hz)")
        ax.legend()
        fig.savefig(dest / "spectrum.png", dpi=140)
        plt.close(fig)


def process(video, destination, args):
    if destination.exists():
        raise ValueError(f"Output already exists: {destination}")
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        dest = Path(folder) / "result"
        dest.mkdir()
        rows, fps, roi = track(video, dest, args)
        quality, metrics, warnings, run, spectrum = analyze(rows, fps, args)
        summary = dict(video=video.name, fps=fps, nyquist_hz=fps/2, roi=roi,
                       settings={k: v for k, v in vars(args).items()
                                 if k not in {"videos", "output"} and v != math.inf},
                       quality=quality, metrics=metrics, warnings=warnings)
        with (dest / "trajectory.csv").open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        (dest / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )
        plots(rows, dest, args, run, spectrum)
        write_report(dest, summary)
        dest.rename(destination)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="parent results directory")
    parser.add_argument("--color", choices=["red", "green"], default="red")
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--background-roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--top-fraction", type=float, default=1.0)
    parser.add_argument("--radius", type=int, default=50)
    parser.add_argument("--min-peak", type=float, default=8)
    parser.add_argument("--gaussian", action="store_true")
    parser.add_argument("--overlay", action="store_true")
    parser.add_argument("--fps", type=float)
    parser.add_argument("--start", type=float, default=0.)
    parser.add_argument("--end", type=float, default=math.inf)
    parser.add_argument("--frame-window", type=int, nargs=2, metavar=("FIRST", "LAST"))
    parser.add_argument("--detrend", type=float, default=1., help="moving average seconds; 0 centers only")
    parser.add_argument("--mad", type=float, default=0., help="MAD threshold multiplier; 0 disables")
    parser.add_argument("--mm-per-px", type=float)
    parser.add_argument("--registration-response", type=float, default=.2)
    args = parser.parse_args()
    numeric = [args.top_fraction, args.min_peak, args.start, args.detrend, args.mad,
               args.registration_response] + [v for v in (args.fps, args.mm_per_px) if v is not None]
    if (not all(map(math.isfinite, numeric)) or not 0 < args.top_fraction <= 1
            or args.radius < 2 or args.min_peak <= 0 or not 0 <= args.start < args.end
            or min(args.detrend, args.mad) < 0 or not 0 <= args.registration_response <= 1
            or (args.fps is not None and args.fps <= 0)
            or (args.mm_per_px is not None and args.mm_per_px <= 0)):
        parser.error("Invalid numeric option. See --help.")
    if args.frame_window and not 0 <= args.frame_window[0] <= args.frame_window[1]:
        parser.error("--frame-window expects nonnegative, ascending frame numbers")
    names = [video.stem.casefold() for video in args.videos]
    if len(set(names)) != len(names):
        parser.error("Input video stems must be unique within a batch")
    args.output.mkdir(parents=True, exist_ok=True)
    status = 0
    for video in args.videos:
        destination = args.output / video.stem
        try:
            result = process(video, destination, args)
            print(f"{video.name}: tracked {result['quality']['tracking_rate']:.1%}; {destination}")
        except (OSError, ValueError, cv2.error) as exc:
            print(f"{video.name}: {exc}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
