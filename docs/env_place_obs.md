# Env_PN_Single_PlaceObs

## Abstract
- What: 定义单设备单动作 TorchRL 环境 `Env_PN_Single_PlaceObs` 的 observation 结构。
- When: 当训练策略需要按库所/机器状态建模，而不是按晶圆列表拼接时使用。
- Not: 不改 observation 语义，不改 `reset/step/reward` 接口形态；动作空间已扩展为多档 WAIT。
- Key rules:
 - observation 按 `LP -> TM(d_TM1) -> PM1 -> PM3 -> PM4` 顺序拼接。
 - `LP_done` 不进入主体 observation。
 - 时间相关特征统一归一化并裁剪到 `[0, 1]`。

## When to use
- 需要显式观察 PM3 与 PM4 分离状态（含清洗）时。
- 需要低维、语义稳定的 place-centered 状态向量时。

## When NOT to use
- 需要逐晶圆 one-hot 路由信息时（请使用 `Env_PN_Single`）。
- 需要保留按 `token_id` 排序的观测语义时。

## Behavior / Rules
- 动作空间沿用 `Env_PN_Single` 的统一动作目录：`transition + multi-wait`（默认 `5/10/20/50/100s`）。
- WAIT 推进规则：
 - 当 `wait_duration == 5` 时，固定推进 5 秒，不做事件截断。
 - 当 `LP_done` 已有完工晶圆时，大于 5 秒的 WAIT 会被动作掩码屏蔽。
 - 其他 WAIT 仍按 `min(wait_duration, next_event_delta)` 推进，避免一次跳过多个关键决策点。
- 观测维度固定为 32：
 - LP: 1 维
 - TM: 4 维
 - PM1/PM3/PM4: 每个 9 维
- LP 特征：
 - `remaining_wafer_norm = clip(len(LP.tokens) / n_wafer, 0, 1)`
- TM 特征：
 - `transport_complete`
 - `wafer_stay_over_long`
 - `wafer_stay_time_norm`
 - `distance_to_penalty_norm`
- PM 特征（每腔室一致）：
 - `occupied`
 - `processing`
 - `done_waiting_pick`
 - `remaining_process_time_norm`
 - `wafer_stay_time_norm`
 - `wafer_time_to_scrap_norm`
 - `is_cleaning`
 - `clean_remaining_time_norm`
 - `remaining_runs_before_clean_norm`

## Configuration / API
- 类名：`Env_PN_Single_PlaceObs`
- 基于：`solutions/Continuous_model/env_single.py`
- 关键归一化参数：
 - `P_Residual_time`
 - `D_Residual_time`
 - `single_cleaning_duration`
 - `single_cleaning_trigger_wafers`
 - `SCRAP_CLIP_THRESHOLD`
- 单设备工序时间参数：
 - `single_process_time_map.PM1/PM3/PM4`
 - 工序时间会在环境内部预处理为最接近的 5 的倍数（最小 5）
- 单设备工序时间随机参数（episode 固定采样）：
 - `single_proc_time_rand_enabled`
 - `single_proc_time_rand_scale_map.PM1/PM3/PM4.{min,max}`（每个加工腔室独立区间）
 - `single_proc_time_rand_min_scale`
 - `single_proc_time_rand_max_scale`
- 训练脚本参数：
 - `solutions/Continuous_model/train_single.py` 支持 `--place-obs`
 - 支持 `--proc-time-rand-enabled`
 - 不再支持 CLI 最小/最大随机区间覆盖（统一由配置文件控制）
 - 传入后使用 `Env_PN_Single_PlaceObs`；不传时默认 `Env_PN_Single`
- 推理导出参数：
 - `solutions/Continuous_model/export_inference_sequence.py` 支持 `--place-obs`
 - 在 `--device-mode single` 下传入后使用 `Env_PN_Single_PlaceObs`

## Examples
- 正例：需要策略直接感知 `PM3` 与 `PM4` 清洗状态时使用本环境。
- 反例：需要把每片晶圆位置编码成 one-hot 序列时不应使用本环境。

## Edge Cases / Gotchas
- TM 无晶圆时，TM 特征回退为 `[0, 0, 0, 1]`。
- PM 无晶圆时，工艺与超时相关特征置 0，仅保留清洗相关状态。
- 归一化分母均设置下限 `>=1`，避免除零。
- 若开启工序时间随机扰动，同一 episode 内工序时长固定；不同 episode 才会重新采样。

## Related Docs
- `docs/README.md`
