# PN Single Guide

## Abstract
- What: 本文档定义单设备连续时间 Petri 网（pn_single）在当前仓库中的架构、接口与行为约束。
- When: 修改 `pn_single.py`、`env_single.py`、`train_single.py`、导出/追责脚本前必须先读。
- Not: 不覆盖并发双机械手 `pn.py` 的完整实现细节。
- Key rules:
  - 单设备统一入口是 `Env_PN_Single`。
- 旧版 place-obs 环境入口与观测切换参数已移除。
  - 关键执行链固定为 `构网 -> mask -> step -> reward`。

## Scope
- In:
  - `ClusterTool`（`solutions/Continuous_model/pn_single.py`）职责与执行链。
  - `Env_PN_Single`（`solutions/Continuous_model/env_single.py`）接口。
  - 单设备相关脚本：训练、导出、二次释放惩罚验证。
- Out:
  - 并发模型 `pn.py` 的细节。
  - 可视化 UI 实现细节。

## Architecture or Data Flow
1. `construct_single.py` 根据 `device_mode + route_code` 构建网络结构与元数据。
2. `ClusterTool` 维护标识、使能判定、时间推进、reward 计算、违规统计。
3. `Env_PN_Single` 封装 TorchRL 风格 `reset/step`，并暴露 `action_mask`。
4. 训练脚本 `train_single.py` 调用 `collect_rollout_ultra` 执行 CPU rollout + batched PPO update。
5. 导出脚本 `export_inference_sequence.py` 生成 `seq/tmp.json` 与动作使能日志。

## Interfaces
- 环境接口:
  - 类: `solutions.Continuous_model.env_single.Env_PN_Single`
  - 关键参数: `device_mode`, `robot_capacity`, `route_code`, `proc_time_rand_enabled`
- 训练入口:
  - `python -m solutions.Continuous_model.train_single --device single --rollout-n-envs 1`
  - 关键参数: `--device`, `--compute-device`, `--checkpoint`, `--proc-time-rand-enabled`, `--rollout-n-envs`
- 推理导出入口:
  - `python -m solutions.Continuous_model.export_inference_sequence --device single --model <model_path>`
  - 当前 action sequence 输出固定为 `seq/tmp.json`
- 二次释放惩罚验证入口:
  - `python -m solutions.Continuous_model.check_release_penalty --sequence <json_name> --results-dir results`
  - `--sequence` 必填，脚本按仓库根目录 `seq/<json_name>` 解析。

## Behavior Rules
1. 路径参数严格校验：`device_mode` 与 `route_code` 非法时直接报错。
2. WAIT 掩码规则：存在加工完成待取片晶圆时，仅允许短 WAIT（5s）。
3. 导出脚本的 `--out-name` 当前不参与文件命名，仅保留兼容。
4. `check_release_penalty.py` 未设置 `--sequence` 时不能执行。
5. 旧观测分支（place-obs）不再作为当前实现接口。

## Examples
- 正例:
  - 单设备训练（CPU rollout，多环境采样）
  - 单设备推理序列导出后，用可视化回放 JSON
- 反例:
  - 继续使用旧版观测切换参数
  - 假设导出路径为历史 `action_series/<name>_<timestamp>.json`

## Edge Cases
- `train_single.py` 最佳模型当前写入 `models/tmp.pt`，并会在 `saved_models/single_<timestamp>/` 保留备份。
- `check_release_penalty.py` 的 `--sequence` 参数若传完整路径，会被额外拼接到 `seq/`，建议只传文件名。

## Related Docs
- `../overview/project-context.md`
- `../training/training-guide.md`
- `../visualization/ui-guide.md`
- `../deprecated/continuous-solution-design.md`

## Change Notes
- 2026-03-19: 建立 pn_single 主文档，统一单设备入口、脚本接口与行为规则说明。
