"""Render a portable, single-page HTML summary of one video analysis."""

import base64
from html import escape


def table(rows):
    return "<dl>" + "".join(
        f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"
        for label, value in rows
    ) + "</dl>"


def format_metric(value):
    if isinstance(value, list):
        return " / ".join(format_metric(item) for item in value)
    return "不可用" if value is None else f"{value:.4g}"


def write_report(destination, summary):
    quality = summary["quality"]
    metrics = summary["metrics"]
    settings = summary["settings"]
    unit = metrics.get("unit", "mm" if settings.get("mm_per_px") else "px")
    window = "不可用"
    if "window_start_frame" in metrics:
        window = f'{metrics["window_start_frame"]}–{metrics["window_end_frame"]} 帧（含端点）'
    quality_table = table([
        ("追踪覆盖率", f'{quality["tracking_rate"]:.1%}'),
        ("检测帧 / 总帧", f'{quality["detected_frames"]} / {quality["frames"]}'),
        ("丢失帧", str(quality["lost_frames"])),
        ("重捕获次数", str(quality["reacquisitions"])),
        ("配准断点", str(quality["registration_breaks"])),
        ("MAD 剔除帧", str(quality["mad_rejected_frames"])),
        ("连续分析帧", str(quality["analysis_frames"])),
    ])
    metric_table = table([
        (label, format_metric(metrics.get(key)))
        for label, key in [
            (f"标准差 X / Y（{unit}）", "std_xy"),
            (f"RMS X / Y（{unit}）", "rms_xy"),
            (f"峰峰值 X / Y（{unit}）", "peak_to_peak_xy"),
            (f"合成标准差（{unit}）", "combined_std"),
            ("主轴方向（度，图像坐标）", "principal_axis_deg"),
            ("观测主频（Hz）", "observed_peak_hz"),
            ("频率格宽（Hz）", "frequency_bin_hz"),
        ]
    ])
    figures = []
    for filename, caption in [
        ("time_series.png", "去趋势后的光斑位移时序"),
        ("trajectory.png", "连续分析窗口内的二维轨迹"),
        ("spectrum.png", "功率谱与观测频率"),
    ]:
        plot = destination / filename
        if plot.is_file():
            png = base64.b64encode(plot.read_bytes()).decode("ascii")
            figures.append(
                f'<figure><img src="data:image/png;base64,{png}" alt="{caption}">'
                f'<figcaption>{caption}</figcaption></figure>'
            )
    warnings = "".join(f"<li>{escape(message)}</li>" for message in summary["warnings"])
    overlay_link = (' · <a href="overlay.mp4">追踪预览 MP4</a>'
                    if (destination / "overlay.mp4").is_file() else "")
    config_table = table([
        ("搜索区域 X / Y / W / H", format_metric(summary["roi"])),
        ("光斑颜色", str(settings["color"])),
        ("色差阈值", format_metric(settings["min_peak"])),
        ("去趋势窗口（秒，0 为仅去均值）", format_metric(settings["detrend"])),
        ("MAD 倍数（0 为关闭）", format_metric(settings["mad"])),
        ("背景平移校正", "启用" if settings.get("background_roi") else "关闭"),
        ("屏幕尺度（mm/px）", format_metric(settings.get("mm_per_px"))),
    ])
    video = escape(summary["video"])
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpotVib 分析报告 · {video}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #16303b; background: #f4f8f8; font: 16px/1.55 system-ui, sans-serif; }}
main {{ max-width: 1120px; margin: auto; padding: 28px 18px; overflow-wrap: anywhere; }}
h1, h2 {{ line-height: 1.2; margin: 0 0 12px; }}
h1 {{ font-size: 34px; }} h2 {{ font-size: 20px; }}
a {{ color: #00666e; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 14px; }}
section, figure {{ padding: 16px; margin: 14px 0; background: white; border: 1px solid #d5e3e4; border-radius: 8px; }}
.grid > * {{ margin: 0; }} .plots {{ margin-top: 14px; }}
dl {{ margin: 0; }} dl div {{ display: flex; gap: 12px; justify-content: space-between; padding: 5px 0; }}
dd {{ margin: 0; text-align: right; font-variant-numeric: tabular-nums; }}
img {{ width: 100%; display: block; }} figcaption {{ margin-top: 8px; text-align: center; }}
@media print {{ body {{ background: white; }} section, figure {{ break-inside: avoid; }} }}
</style></head>
<body><main><header>
<h1>SpotVib 光斑振动分析报告</h1>
<p>{video}<br>名义帧率 {summary["fps"]:.4g} fps · 奈奎斯特频率 {summary["nyquist_hz"]:.4g} Hz · {window}</p>
<p><a href="trajectory.csv">逐帧 CSV</a> · <a href="summary.json">参数与指标 JSON</a>{overlay_link}</p>
</header>
<div class="grid">
<section><h2>振动指标</h2>{metric_table}</section>
<section><h2>追踪质量</h2>{quality_table}</section>
</div>
<section><h2>判读提示</h2><ul>{warnings}
<li>追踪覆盖率只反映候选检测。可用预览核对候选位置。mm 表示标定后的屏幕光斑位移。</li>
</ul></section>
<div class="grid plots">{"".join(figures)}</div>
<section><h2>分析参数</h2>{config_table}</section>
</main></body></html>"""
    (destination / "analysis_report.html").write_text(document, encoding="utf-8")
