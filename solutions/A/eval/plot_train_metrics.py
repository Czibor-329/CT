from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# 标题中的「路径」等汉字需无衬线中文字体，否则为方框（Windows 常见：微软雅黑 / 黑体）
_CJK_SANS = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC", "Arial Unicode MS", "DejaVu Sans"]


def _apply_cjk_matplotlib_font() -> None:
    plt.rcParams["font.sans-serif"] = _CJK_SANS + list(plt.rcParams.get("font.sans-serif", []))
    plt.rcParams["axes.unicode_minus"] = False


def _moving_average(arr: np.ndarray, window: int) -> np.ndarray:
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
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), dpi=300, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="从 training_metrics.json 绘制双子图 PNG")
    p.add_argument("--input", type=Path, required=True, help="training_metrics.json 路径")
    p.add_argument("--output", type=Path, required=True, help="输出 PNG 路径")
    p.add_argument("--smooth-window", type=int, default=5, help="reward 滑动平均窗口")
    p.add_argument("--show", action="store_true", help="保存后弹出交互窗口")
    p.add_argument("--route-label", type=str, default=None, help="子图标题后缀，例如「路径 1-4」")
    args = p.parse_args()
    plot_metrics(
        args.input,
        args.output,
        smooth_window=args.smooth_window,
        show=args.show,
        route_label=args.route_label,
    )


if __name__ == "__main__":
    main()
