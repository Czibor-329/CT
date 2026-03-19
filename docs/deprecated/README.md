# Deprecated Docs Index

## Abstract
- What: 本文档汇总历史文档到新主文档的迁移映射。
- When: 访问旧链接、修复断链、或核对兼容保留策略时使用。
- Not: 不承载当前规范说明。
- Key rules:
  - 规范内容以 5 个主文档为准。
  - 旧文档只保留跳转与差异说明。
  - 默认保留 2 个版本迭代后再评估删除。

## Migration Map
- `docs/project.md` -> `docs/overview/project-context.md`
- `docs/架构.md` -> `docs/continuous-model/pn-single.md`
- `docs/continuous_solution_design.md` -> `docs/continuous-model/pn-single.md` + `docs/training/training-guide.md`
- `docs/viz.md` -> `docs/visualization/ui-guide.md`
- `docs/td_petri.md` -> `docs/td-petri/td-petri-guide.md`
- `docs/td_petri_modeling.md` -> `docs/td-petri/td-petri-guide.md`
- `docs/env_place_obs.md` -> 历史说明保留，参考 `docs/continuous-model/pn-single.md`

## Retention Policy
1. 兼容页必须包含“新路径 + 迁移日期 + 差异说明”。
2. 新增规范不得写入兼容页。
3. 兼容周期默认 2 个版本迭代。

## Related Docs
- `../README.md`
- `../overview/project-context.md`
- `../continuous-model/pn-single.md`
- `../training/training-guide.md`
- `../visualization/ui-guide.md`
- `../td-petri/td-petri-guide.md`

## Change Notes
- 2026-03-19: 新增 deprecated 索引，统一旧文档迁移映射与保留策略。
