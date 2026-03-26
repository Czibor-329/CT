from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

# 标题中的「路径」等汉字需无衬线中文字体，否则为方框（Windows 常见：微软雅黑 / 黑体）
_CJK_SANS = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC", "Arial Unicode MS", "DejaVu Sans"]


def _apply_cjk_matplotlib_font() -> None:
    plt.rcParams["font.sans-serif"] = _CJK_SANS + list(plt.rcParams.get("font.sans-serif", []))
    plt.rcParams["axes.unicode_minus"] = False


def _moving_average(arr: np.ndarray, window: int) -> np.ndarray:
    if arr.size == 0:
        return arr
    window = max(1, int(window))
    if window > arr.size:
        window = int(arr.size)
    if window % 2 == 0:
        window = max(1, window - 1)
    if window <= 1:
        return arr.copy()
    pad = window // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def plot_metrics(
    metrics_json: Path,
    out_png: Path,
    *,
    smooth_window: int = 5,
    show: bool = False,
    route_label: str | None = None,
) -> None:
    if route_label:
        _apply_cjk_matplotlib_font()
    metrics_json = Path(metrics_json)
    raw = json.loads(metrics_json.read_text(encoding="utf-8"))
    reward = np.asarray(raw.get("reward", []), dtype=float)
    if reward.size == 0:
        return
    n = int(reward.size)
    makespan = np.asarray(raw.get("makespan", []), dtype=float)
    finish = np.asarray(raw.get("finish", []), dtype=float)
    scrap = np.asarray(raw.get("scrap", []), dtype=float)

    epochs = np.arange(1, n + 1)
    w = max(1, int(smooth_window))
    reward_smooth = _moving_average(reward, w)

    valid_ms = makespan != 0
    ms_epochs = epochs[valid_ms]
    ms_values = makespan[valid_ms]

    color_reward = "#E69F00"
    color_makespan = "#0072B2"
    color_finish = "#009E73"
    color_scrap = "#D55E00"

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax1 = axes[0]
    ax1.plot(
        epochs,
        reward_smooth,
        linestyle="-",
        linewidth=2,
        color=color_reward,
        label="Reward",
    )
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Reward")
    ax1.set_title(f"Reward & Makespan | {route_label}" if route_label else "Reward & Makespan")
    ax1.grid(True, alpha=0.3)

    ax1b = ax1.twinx()
    ax1b.plot(
        ms_epochs,
        ms_values,
        linestyle="--",
        linewidth=2,
        color=color_makespan,
        label="Makespan",
    )
    ax1b.set_ylabel("Makespan")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1b.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")

    ax2 = axes[1]
    width = 0.4
    ax2.bar(epochs - width / 2, finish, width=width, color=color_finish, label="Finish")
    ax2.bar(epochs + width / 2, scrap, width=width, color=color_scrap, label="Scrap")
    ax2.set_xlabel("Epoch")
    ax2.set_ylabel("Count")
    ax2.set_title(f"Finish & Scrap | {route_label}" if route_label else "Finish & Scrap")
    ax2.legend()
    ax2.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    out_png = _normalize_png_output(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), dpi=300, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def _load_metrics_payload(metrics_json: Path) -> dict:
    metrics_json = Path(metrics_json)
    return json.loads(metrics_json.read_text(encoding="utf-8"))


def _normalize_png_output(out_png: Path) -> Path:
    out_png = Path(out_png)
    if out_png.suffix == "":
        return out_png.with_suffix(".png")
    return out_png


def plot_makespan_comparison(
    file_paths: Sequence[Path],
    out_png: Path,
    *,
    window: int = 9,
    titles: str = "Makespan Comparison",
    show: bool = False,
) -> None:
    """
    参数：
    - file_paths: list[str]，json文件路径列表
    - window: 平滑窗口大小
    - out_png: 输出 PNG 路径
    - titles: 图标题
    """

    def moving_average(x, w):
        result = np.full(len(x), np.nan, dtype=float)
        half = w // 2

        for i in range(len(x)):
            left = max(0, i - half)
            right = min(len(x), i + half + 1)
            window_data = x[left:right]

            valid = window_data[~np.isnan(window_data)]
            if len(valid) > 0:
                result[i] = valid.mean()

        return result

    def safe_to_float_array(seq):
        values = []
        for v in seq:
            try:
                if v is None:
                    values.append(np.nan)
                else:
                    values.append(float(v))
            except (TypeError, ValueError):
                values.append(np.nan)
        arr = np.array(values, dtype=float)
        arr[arr==0] = np.nan
        return arr

    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "legend.fontsize": 10,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.linewidth": 0.8,
        "grid.linewidth": 0.6,
        "lines.linewidth": 2.4,
    })

    colors_map = ["#f39c12", "#e74c3c", "#6d4c41"]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))

    plotted_count = 0

    for idx, path in enumerate(file_paths):
        label = Path(path).stem
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "makespan" not in data:
            print(f"[Skip] {path}: no 'makespan' field.")
            continue

        ms_raw = data["makespan"]
        if ms_raw is None or len(ms_raw) == 0:
            print(f"[Skip] {path}: empty 'makespan'.")
            continue

        ms = safe_to_float_array(ms_raw)

        # 如果全是缺失值，也跳过
        if np.all(np.isnan(ms)):
            print(f"[Skip] {path}: all makespan values are invalid.")
            continue

        x = np.arange(1, len(ms) + 1)
        smooth = moving_average(ms, window)

        color = colors_map[idx % len(colors_map)]

        ax.plot(
            x,
            smooth,
            label=label,
            color=color,
            linewidth=2.6
        )
        plotted_count += 1

    if plotted_count == 0:
        print("No valid makespan data to plot.")
        return

    ax.grid(True, alpha=0.25)
    ax.set_xlabel("Training Episode")
    ax.set_ylabel("Makespan")
    ax.set_title(titles, pad=10)

    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=9))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    leg = ax.legend(frameon=True, fancybox=False, edgecolor="0.85")
    leg.get_frame().set_alpha(0.95)

    fig.tight_layout()
    out_png = _normalize_png_output(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), dpi=400, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="从 training_metrics.json 绘制双子图 PNG")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", type=Path, help="单文件模式：training_metrics.json 路径")
    mode.add_argument("--compare-inputs", type=Path, nargs="+", help="对比模式：多个 training_metrics.json 路径")
    p.add_argument("--output", type=Path, required=True, help="输出 PNG 路径")
    p.add_argument("--smooth-window", type=int, default=5, help="reward 滑动平均窗口")
    p.add_argument("--show", action="store_true", help="保存后弹出交互窗口")
    p.add_argument("--route-label", type=str, default=None, help="子图标题后缀，例如「路径 1-4」")
    p.add_argument(
        "--compare-by",
        type=str,
        choices=["candidate_k", "search_depth"],
        default="candidate_k",
        help="对比模式下分组字段",
    )
    args = p.parse_args()
    if args.compare_inputs:
        plot_makespan_comparison(
            args.compare_inputs,
            args.output,
            show=args.show,
        )
        return

    plot_metrics(
        args.input,
        args.output,
        smooth_window=args.smooth_window,
        show=args.show,
        route_label=args.route_label,
    )


if __name__ == "__main__":
    main()
