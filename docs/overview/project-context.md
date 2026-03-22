# Project Context

## Abstract
- What: 本文档定义 CT 项目的目标、系统边界、模块地图与统一入口命令。
- When: 新成员入项、AI 智能体首次理解仓库、或架构评审前必须先读。
- Not: 不描述具体算法实现细节；实现细节以专题文档为准。
- Key rules:
  - 以本页和 `docs/README.md` 作为文档导航起点。
  - 代码行为以源码为准，文档必须与入口脚本参数保持一致。
  - 领域术语以本页术语表定义为准。

## Scope
- In:
  - 问题定义与业务目标。
  - 模块职责边界（Continuous_model / visualization / Td_petri）。
  - 统一入口命令与核心配置位置。
- Out:
  - 具体奖励公式推导。
  - 函数级 API 细节。
  - 历史实验日志全文。

## Architecture or Data Flow
- 模块地图:
  - `solutions/Continuous_model/`: 连续时间 Petri 网环境、训练与推理导出。
  - `visualization/`: PySide6 可视化与回放界面。
  - `solutions/Td_petri/`: 离散时间/链式动作建模与序列工具。
  - `data/petri_configs/`: 训练与环境配置。
- 高层数据流:
  1. 配置加载 (`data/petri_configs`, `data/ppo_configs`)。
  2. 环境构建 (`pn_single.py` / `env_single.py`)。
  3. 训练或推理导出 (`train_single.py`, `train_concurrent.py`, `export_inference_sequence.py`)。
  4. 可视化回放 (`visualization/main.py`)。

## Interfaces
- 统一入口命令（推荐）:
  - 级联训练: `python -m solutions.Continuous_model.train_single --device cascade`（可选 `--artifact-dir <dir>` 写入该目录产物、`training_metrics_plot.png`、有 best 时 `gantt.png`；亦可单独运行 `python -m solutions.Continuous_model.eval.plot_train_metrics`）
  - 并发训练: `python -m solutions.Continuous_model.train_concurrent --config data/ppo_configs/concurrent_phase2_config.json`
  - 推理导出: `python -m solutions.Continuous_model.export_inference_sequence --device cascade --model <model_path>`（默认 `seq/tmp.json`；`--out-name` 控制文件名）
  - 可视化: `python -m visualization.main --device cascade`
  - Td_petri 主入口: `python -m solutions.Td_petri.tdpn`
- 关键配置:
  - `data/petri_configs/single.json`
  - `data/petri_configs/cascade.json`
  - `data/ppo_configs/s_train.json`

## Behavior Rules
1. 文档层“权威入口”仅指向 5 个主文档。
2. 旧文档文件名仅作为兼容跳转页，不再承载规范说明。
3. 命令示例必须可在当前代码入口中找到同名参数。
4. 涉及“已移除接口”时，只允许写在 `docs/deprecated/` 或迁移说明中。

## Examples
- 正例:
  - 先读 `docs/README.md`，再按主题进入 `overview -> continuous-model -> training -> visualization`。
  - 新增功能文档时，先更新主文档，再在兼容页补迁移说明。
- 反例:
  - 直接在旧文件（如历史单页说明）写新规范。
  - 文档命令与脚本参数不一致。

## Edge Cases
- 根 `README.md` 含历史日志，可能与最新实现存在差异；架构和入口以 `docs/` 主文档为准。
- 某些脚本含平台相关默认路径（Windows 绝对路径），调用时建议显式传参覆盖。

## Related Docs
- `../README.md`
- `../continuous-model/pn-single.md`
- `../training/training-guide.md`
- `../visualization/ui-guide.md`
- `../td-petri/td-petri-guide.md`

## Change Notes
- 2026-03-19: 新建规范化项目描述文档，作为后续主题文档的统一上下文入口。
