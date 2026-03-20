# Training Guide

## Abstract
- What: 本文档定义 Continuous_model 的训练入口、配置优先级、产物输出和复现实验最小流程。
- When: 启动训练、更新训练参数、排查训练产物时使用。
- Not: 不覆盖 Td_petri 的链式搜索策略实现。
- Key rules:
  - 单设备训练入口是 `train_single.py`。
  - 并发训练入口是 `train_concurrent.py`。
  - 命令示例必须与脚本实际参数一致。

## Scope
- In:
  - single/cascade/concurrent 训练入口。
  - 配置来源与覆盖关系。
  - 输出模型路径与日志观察点。
- Out:
  - 具体网络结构推导。
  - UI 回放细节。

## Architecture or Data Flow
1. 读取配置 (`data/ppo_configs/*.json`)。
2. 构建环境 (`Env_PN_Single` 或 `Env_PN_Concurrent`)。
3. rollout 采样与 PPO 更新。
4. 保存 best/final 权重。
5. 可选导出推理序列用于可视化回放。

## Interfaces
- 单设备训练:
  - `python -m solutions.Continuous_model.train_single --device single --rollout-n-envs 1`
  - 参数: `--device`, `--compute-device`, `--checkpoint`, `--proc-time-rand-enabled`, `--rollout-n-envs`
- 并发训练:
  - `python -m solutions.Continuous_model.train_concurrent --config data/ppo_configs/concurrent_phase2_config.json`
  - 参数: `--config`, `--checkpoint`
- 导出推理序列:
  - `python -m solutions.Continuous_model.export_inference_sequence --device single --model <model_path>`（输出 `seq/tmp.json`）
- 关键配置优先级:
  - single: `s_train.json` 作为基础，CLI 参数覆盖。
  - concurrent: `--config` 文件优先，不存在时退回默认配置对象。

## Behavior Rules
1. 训练文档必须同时列出 single 与 concurrent 入口，不混用参数。
2. 产物说明必须区分“公共 best 路径”和“时间戳备份目录”。
3. 当前实现约束必须如实记录（例如 single best 固定写入 `models/tmp.pt`）。
4. 禁止继续在主文档中引用已移除的旧观测切换参数。

## Examples
- 正例:
  - 单设备 CPU 训练: `python -m solutions.Continuous_model.train_single --device single --compute-device cpu`
  - 单设备 GPU 更新 + 多环境 rollout: `python -m solutions.Continuous_model.train_single --device single --compute-device cuda --rollout-n-envs 8`
  - 并发训练: `python -m solutions.Continuous_model.train_concurrent --config data/ppo_configs/concurrent_phase2_config.json`
- 反例:
  - 将 concurrent 参数传给 train_single。
  - 误以为导出脚本会按 `--out-name` 生成文件名。

## Edge Cases
- `train_concurrent.py` 的默认 `--config` 是本机绝对路径，跨机器时应显式传相对路径。
- single 训练 best 权重会覆盖 `models/tmp.pt`，并行实验需额外备份策略。
- 推理导出当前固定写 `seq/tmp.json`，并发运行会互相覆盖。

## Related Docs
- `../overview/project-context.md`
- `../continuous-model/pn-single.md`
- `../visualization/ui-guide.md`
- `../deprecated/continuous-solution-design.md`

## Change Notes
- 2026-03-19: 建立训练主文档，统一 single/cascade/concurrent 入口与产物说明。
