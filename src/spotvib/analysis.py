"""Compute metrics on the longest uninterrupted usable interval."""

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import periodogram


def analyze(rows, fps, args):
    frame = np.arange(len(rows))
    time = frame / fps
    xy = np.array([[r["corrected_x_px"], r["corrected_y_px"]] for r in rows], float)
    eligible = np.isfinite(xy).all(axis=1)
    eligible &= (time >= args.start) & (time < args.end)
    if args.frame_window:
        lo, hi = args.frame_window
        eligible &= (frame >= lo) & (frame <= hi)
    segments = np.array([r["segment"] for r in rows])
    warnings = [
        "Time is frame index / nominal FPS. Confirm constant frame rate before interpreting spectra.",
        "Observed peaks may alias from above Nyquist. A low observed peak cannot rule out aliasing.",
    ]
    values = xy.copy()
    values[~eligible] = np.nan
    accepted = eligible.copy()
    # Within each valid interval, subtract a local baseline and optionally flag outliers.
    boundaries = np.flatnonzero(np.r_[True, (eligible[1:] != eligible[:-1]) |
                                       (segments[1:] != segments[:-1]), True])
    for lo, hi in zip(boundaries[:-1], boundaries[1:]):
        if not eligible[lo]:
            continue
        block = xy[lo:hi]
        size = min(max(1, 2*round(args.detrend * fps / 2)+1), hi-lo)
        residual = (block - uniform_filter1d(block, size=size, axis=0, mode="nearest")
                    if args.detrend else block - block.mean(axis=0))
        values[lo:hi] = residual
        if args.mad:
            distance = np.abs(residual - np.median(residual, axis=0))
            scale = 1.4826 * np.median(distance, axis=0)
            threshold = np.where(scale > 1e-9, args.mad * scale, np.inf)
            accepted[lo:hi] &= (distance <= threshold).all(axis=1)
    values[~accepted] = np.nan
    indices = np.flatnonzero(accepted)
    cuts = np.flatnonzero((np.diff(indices) > 1) |
                         (np.diff(segments[indices]) != 0)) + 1
    run = max(np.split(indices, cuts), key=len)
    quality = {
        "frames": len(rows),
        "detected_frames": sum(r["x_px"] is not None for r in rows),
        "lost_frames": sum(r["x_px"] is None for r in rows),
        "reacquisitions": sum(r["reacquired"] for r in rows),
        "registration_breaks": int(segments[-1]),
        "mad_rejected_frames": int((eligible & ~accepted).sum()),
        "analysis_frames": len(run),
    }
    quality["tracking_rate"] = quality["detected_frames"] / len(rows)
    if quality["tracking_rate"] < .9:
        warnings.append("Tracking coverage is below the 90% review flag. Inspect the overlay.")
    if len(run) < int(accepted.sum()):
        warnings.append("Metrics use the longest uninterrupted usable interval only.")
    metrics, spectrum = {}, None
    if len(run) >= 2:
        data = values[run]
        scale = args.mm_per_px or 1.0
        scaled = data * scale
        std = scaled.std(axis=0)
        covariance = np.cov(scaled, rowvar=False, bias=True)
        eigenvalues, axes = np.linalg.eigh(covariance)
        direction = None
        if eigenvalues[-1] > 0 and eigenvalues[-1] - eigenvalues[0] > 1e-6*eigenvalues[-1]:
            direction = float(np.degrees(np.arctan2(*axes[::-1, -1])) % 180)
        metrics = {
            "unit": "mm" if args.mm_per_px else "px",
            "window_start_frame": int(run[0]), "window_end_frame": int(run[-1]),
            "std_xy": std.tolist(), "rms_xy": np.sqrt((scaled**2).mean(axis=0)).tolist(),
            "peak_to_peak_xy": np.ptp(scaled, axis=0).tolist(),
            "combined_std": float(np.linalg.norm(std)),
            "principal_axis_deg": direction,
        }
        if len(run) >= max(16, np.ceil(fps)):
            freq, psd = periodogram(scaled, fs=fps, window="hann", axis=0)
            power = psd.sum(axis=1)
            if np.max(power[1:]) > 0:
                peak = float(freq[1+np.argmax(power[1:])])
                metrics.update(observed_peak_hz=peak, frequency_bin_hz=fps/len(run))
                spectrum = (freq, psd)
                if peak >= .8 * fps/2:
                    warnings.append("Observed peak is near the nominal Nyquist frequency.")
        if spectrum is None:
            warnings.append("No spectrum reported. Need at least 16 contiguous frames, one second, and nonzero power.")
    else:
        warnings.append("Insufficient contiguous usable frames for displacement metrics.")
    for i, row in enumerate(rows):
        row.update(eligible=bool(eligible[i]), accepted=bool(accepted[i]),
                   displacement_x_px=float(values[i, 0]) if accepted[i] else None,
                   displacement_y_px=float(values[i, 1]) if accepted[i] else None)
    return quality, metrics, warnings, run, spectrum
