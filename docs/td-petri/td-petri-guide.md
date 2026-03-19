# TD Petri Guide

## Abstract
- What: 本文档定义 Td_petri 子系统的建模目标、入口脚本、与 Continuous_model 的边界关系。
- When: 修改 `solutions/Td_petri` 或接入 planB 序列链路前使用。
- Not: 不覆盖 Continuous_model 的连续时间训练实现。
- Key rules:
  - Td_petri 文档只描述 `solutions/Td_petri/` 相关逻辑。
  - 与 Continuous_model 的交互边界必须显式说明。
  - 序列文件契约必须使用字段级描述。

## Scope
- In:
  - `tdpn.py` 主入口与离散时间调度流程。
  - `generate_planB_sequence.py` 的序列生成链路。
  - `planB_sequence.json` 的用途与字段约定。
- Out:
  - Continuous_model 的 PPO 训练细节。
  - 可视化 UI 组件实现。

## Architecture or Data Flow
1. `tdpn.py` 构建/搜索离散时间 Petri 网，输出调度结果并可绘制甘特图。
2. `generate_planB_sequence.py` 读取 PPO 模型与环境状态，生成 `planB_sequence.json`。
3. 可视化层读取序列并执行离线回放（Model B）。
4. Continuous_model 导出的序列与 Td_petri 序列在回放场景下共享相同顶层契约（`schema_version=2` 风格）。

## Interfaces
- Td_petri 主入口:
  - `python -m solutions.Td_petri.tdpn`
- 生成 planB 序列:
  - `python -m solutions.Td_petri.generate_planB_sequence`
- 核心文件:
  - `solutions/Td_petri/tdpn.py`
  - `solutions/Td_petri/tdpn_parser.py`
  - `solutions/Td_petri/construct.py`
  - `solutions/Td_petri/planB_sequence.json`
- 序列契约（当前样例）:
  - 顶层: `reward_report`, `schema_version`, `device_mode`, `sequence`
  - `sequence` 元素: `step`, `time`, `action`/`actions`

## Behavior Rules
1. Td_petri 与 Continuous_model 的边界在于“建模/搜索方法”，不是回放协议。
2. 文档必须标注哪些脚本使用绝对路径或本机默认路径。
3. `planB_sequence.json` 作为回放输入时，字段必须完整且顺序可迭代。

## Examples
- 正例:
  - 先执行 `python -m solutions.Td_petri.tdpn` 观察离散时间调度结果。
  - 再执行 `python -m solutions.Td_petri.generate_planB_sequence` 生成回放序列。
- 反例:
  - 将 Td_petri 术语直接套用到 Continuous_model 的连续时间环境中。

## Edge Cases
- `generate_planB_sequence.py` 内含默认模型路径，跨机器时通常需要先调整路径或环境。
- `tdpn.py` 无 CLI 参数，批量实验需通过代码层修改入口变量。

## Related Docs
- `../overview/project-context.md`
- `../training/training-guide.md`
- `../visualization/ui-guide.md`
- `../deprecated/td-petri.md`

## Change Notes
- 2026-03-19: 建立 td_petri 主文档，明确与 continuous_model 的边界和序列契约。
