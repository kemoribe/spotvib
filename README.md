# SpotVib

SpotVib 从反射光斑视频中提取二维轨迹，计算振动幅度和观测主频。适用于画面中可分辨的单个红色或绿色光斑，例如光杠杆实验。算法沿用课程项目中的颜色差分、连通域、加权质心、二维高斯拟合和相位相关配准。

## 安装与体验

在本目录下用 Python 3.10 或更高版本安装。

```sh
python -m pip install .
python examples/synthetic_video.py results/demo.mp4
spotvib results/demo.mp4 -o results/run --roi 100 80 120 80 --background-roi 15 15 80 80 --gaussian --overlay
```

示例由程序生成，设定了 6 Hz、8 px 的水平正弦振动和缓慢相机平移，可用来核对整个流程。

## 分析自己的视频

```sh
spotvib clip1.mp4 clip2.mp4 -o results/experiment --color red --top-fraction 0.62 --min-peak 5 --overlay
```

- `--roi X Y W H` 限定光斑搜索范围，单位为像素，优先于 `--top-fraction`。画面有同色干扰时，先在预览中检查 ROI。
- `--background-roi X Y W H` 启用相机平移校正。选含固定纹理且远离光斑和运动物体的区域。相位相关失效时切断当前轨迹段。
- `--frame-window FIRST LAST` 选择分析帧，两个端点均包含，帧号从 0 开始。也可用 `--start` 和 `--end` 按秒设置左闭右开的区间。
- `--detrend 0` 仅去均值，默认按 1 秒局部均值去趋势。`--mad 4` 可选剔除明显异常点，默认关闭。检查去趋势和剔除对波形的影响。
- `--mm-per-px` 只接受已知的屏幕比例。此时图和汇总指标以 mm 表示屏幕光斑位移。镜面实际位移仍需光路与结构模型。

每段视频输出到同名子目录。已有结果目录采用报错保护，重跑时指定新的输出目录。

| 文件 | 内容 |
| --- | --- |
| `trajectory.csv` | 逐帧原始和校正后坐标、候选峰值、检测方法、配准响应、分析标记及去趋势位移，坐标始终为 px |
| `summary.json` | 运行参数、追踪覆盖率、重捕获与配准失败次数、分析窗口、幅度指标和警告 |
| `time_series.png` | 去趋势波形和用于汇总的连续区间 |
| `trajectory.png` | 有效区间的二维轨迹 |
| `spectrum.png` | 满足长度要求时的功率谱 |
| `overlay.mp4` | 启用 `--overlay` 时的逐帧核对预览 |
| `analysis_report.html` | 一页式报告，含振动指标、追踪质量、判读提示、参数与内嵌图表 |

可用浏览器直接打开报告。图表随 HTML 保存，CSV、JSON 和视频链接需要对应文件放在同一目录。

追踪率只统计程序找到候选光斑的帧。碰到同色干扰时，请用叠加预览确认。缺帧、离群和配准断点会切断分析区间，幅度和频谱取最长的连续区间。时间取帧号除以名义帧率，变帧率视频需在明确时间基准后再解释频谱。超过奈奎斯特频率的真实振动可能表现为更低的观测主频。

完整开发和发布计划见 [PLAN.md](PLAN.md)。
