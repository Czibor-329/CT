"""
级联设备构网工具（cascade-only）：输出连续 Petri 固定拓扑与动态路由装配结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import numpy as np
from solutions.Continuous_model.build_topology import get_topology
from solutions.Continuous_model.construct import BasedToken
from solutions.Continuous_model.helper_function import _preprocess_process_time_map as _hf_preprocess_process_time_map
from solutions.Continuous_model.pn import LL, PM, Place, SR, TM
from solutions.Continuous_model.route_compiler_single import (
    RobotSpec as CompiledRobotSpec,
    RouteIR,
    TokenRoutePlan,
    build_route_meta_from_route_ir,
    build_token_route_plan,
    compile_route_stages,
)

SOURCE = 3
ROBOT = 2
CHAMBER = 1
BUFFER = 4

BUFFER_NAMES: Set[str] = {"LLC"}

# 级联模式下固定 8 维 TM 去向 one-hot（逐目标编码，避免按目标组压缩导致信息丢失）
CASCADE_TM2_TARGET_ORDER: Tuple[str, ...] = (
    "PM7",
    "PM8",
    "PM9",
    "PM10",
    "LLC",
    "LLD",
    "LP_done",
    "LP",
)
CASCADE_TM3_TARGET_ORDER: Tuple[str, ...] = (
    "PM1",
    "PM2",
    "PM3",
    "PM4",
    "PM5",
    "PM6",
    "LLC",
    "LLD",
)
CASCADE_TM2_TARGET_ONEHOT: Dict[str, int] = {
    name: idx for idx, name in enumerate(CASCADE_TM2_TARGET_ORDER)
}
CASCADE_TM3_TARGET_ONEHOT: Dict[str, int] = {
    name: idx for idx, name in enumerate(CASCADE_TM3_TARGET_ORDER)
}




def _build_route_source_target_transport(route_ir: RouteIR) -> Dict[Tuple[str, str], str]:
    """按当前 route 生成 (source,target)->transport 映射，用于动态选择 u 变迁。"""
    mapping: Dict[Tuple[str, str], str] = {}
    for hop in route_ir.transports:
        src_stage = route_ir.stages[hop.from_stage_idx]
        dst_stage = route_ir.stages[hop.to_stage_idx]
        transport_name = str(hop.transport_place).replace("d_", "")
        for src in src_stage.candidates:
            for dst in dst_stage.candidates:
                mapping[(str(src), str(dst))] = transport_name
    return mapping



def parse_route(
    stages: List[List[str]],
    buffer_names: Optional[Set[str]] = None,
) -> Dict[str, object]:
    """
    从路线 stages 解析路由元数据。

    stages: 阶段序列，如 [["PM1"], ["PM3","PM4"], ["PM6"]] 表示 LP->PM1->[PM3,PM4]->PM6->LP_done
    buffer_names: 缓冲库所（如 LLC），不计入 chambers，但计入 timeline_chambers

    Returns:
        chambers, timeline_chambers, u_targets, step_map,
        release_station_aliases, release_chain_by_u, system_entry_places
    """
    buffer_names = buffer_names or BUFFER_NAMES

    def _is_buffer_stage(stage: List[str]) -> bool:
        return len(stage) == 1 and stage[0] in buffer_names

    # release_station_aliases: s1=stage[0], s2=stage[1], ...
    release_station_aliases: Dict[str, List[str]] = {}
    for i, stage in enumerate(stages):
        release_station_aliases[f"s{i + 1}"] = list(stage)

    # chambers: 按序展开，排除 buffer stage
    chamber_list: List[str] = []
    for stage in stages:
        if not _is_buffer_stage(stage):
            chamber_list.extend(stage)
    chambers = tuple(chamber_list)

    # timeline_chambers: chambers + 路径中的 buffer
    buffers_in_route = [
        s[0] for s in stages if _is_buffer_stage(s)
    ]
    timeline_chambers = chambers + tuple(buffers_in_route)

    # step_map: 按 stage 序分配，LP_done = len(stages)+1
    step_map: Dict[str, int] = {"LP_done": len(stages) + 1}
    step = 1
    for stage in stages:
        for place in stage:
            step_map[place] = step
        step += 1

    # u_targets: stage[i] 中每点 -> stage[i+1]；最后 stage -> [LP_done]
    u_targets: Dict[str, List[str]] = {}
    # LP -> stage[0]
    if stages:
        u_targets["LP"] = list(stages[0])

    for i, stage in enumerate(stages):
        next_stage = stages[i + 1] if i + 1 < len(stages) else ["LP_done"]
        for place in stage:
            u_targets[place] = list(next_stage)

    # system_entry_places: stage[0] 的 place 集合
    system_entry_places = set(stages[0]) if stages else set()

    # release_chain_by_u: 释放点 u_* 的下游 s_n 链
    # 释放点: u_LP（投放到 stage 0），以及每个 buffer 后 unload 的 u_*（投放到 buffer 的下一 stage）
    release_chain_by_u: Dict[str, List[str]] = {}
    if stages:
        # u_LP 投放 à stage 0，链为 s1 到 s_n
        release_chain_by_u["u_LP"] = [f"s{k}" for k in range(1, len(stages) + 1)]

    for i, stage in enumerate(stages):
        if _is_buffer_stage(stage):
            # buffer 如 LLC，u_LLC 投放 à 下一 stage，链为从 s_{i+2} 到 s_n
            buffer_name = stage[0]
            u_name = f"u_{buffer_name}"
            chain = [f"s{k}" for k in range(i + 2, len(stages) + 1)]
            if chain:
                release_chain_by_u[u_name] = chain

    # u_LLD: 从 LLD unload 投放到下一 stage（PM9/PM10 或 LP_done）
    for i, stage in enumerate(stages):
        if stage == ["LLD"] and i + 1 < len(stages):
            release_chain_by_u["u_LLD"] = [f"s{i + 2}"]  # s_{i+2} 对应 stages[i+1]
            break
        if stage == ["LLD"] and i + 1 >= len(stages):
            # route 3: LLD 为最后一 stage，无 s5
            break

    # 修正 release_chain_by_u：与现有一致
    # u_LP: [s1, s2]（cascade）或 [s1,s2] 或 [s1,s2,s3]（single）
    # u_LLC: [s3, s4]
    # u_LLD: [s5] 仅当存在 s5 时
    if len(stages) >= 2 and _is_buffer_stage(stages[1]):
        release_chain_by_u["u_LP"] = ["s1", "s2"]
    if len(stages) >= 4 and _is_buffer_stage(stages[1]):
        release_chain_by_u["u_LLC"] = ["s3", "s4"]
    if len(stages) >= 5:
        release_chain_by_u["u_LLD"] = ["s5"]

    return {
        "chambers": chambers,
        "timeline_chambers": timeline_chambers,
        "u_targets": u_targets,
        "step_map": step_map,
        "release_station_aliases": release_station_aliases,
        "release_chain_by_u": release_chain_by_u,
        "system_entry_places": system_entry_places,
    }


def _route_ir_preprocess_chambers(
    route_ir: RouteIR,
    source_name: str,
    sink_name: str,
) -> Tuple[str, ...]:
    """配置驱动：与 pn_single 一致，跳过 buffer stage 的 candidates（如 LLC）。"""
    names: List[str] = []
    for stage in route_ir.stages[1:-1]:
        if str(stage.stage_type) == "buffer":
            continue
        for chamber_name in stage.candidates:
            if chamber_name in {source_name, sink_name}:
                continue
            if chamber_name not in names:
                names.append(chamber_name)
    return tuple(names)


def preprocess_process_time_map(process_time_map: Mapping[str, int], chambers: Tuple[str, ...],
                                route_config: Optional[Mapping[str, Any]] = None):
    """
    按腔室清单对工序时长做默认填充与取整到 5 秒（与 helper_function 一致）。
    chambers 不含 buffer 库所（如 LLC）时，后者不走本预处理。
    """
    raw = dict(process_time_map)

    cfg_ch = dict(route_config.get("chambers") or {})
    defaults = {
        name: int((spec or {}).get("process_time", 0))
        for name, spec in cfg_ch.items()
        if name in chambers
    }
    missing = sorted(c for c in chambers if c not in raw and c not in defaults)
    if missing:
        raise ValueError(
            "missing default process times for chambers: "
            f"{missing}"
        )
    return dict(_hf_preprocess_process_time_map(raw, chambers, defaults))



def _build_single_device_net_from_route_config(
    n_wafer: int,
    ttime: int,
    robot_capacity: int,
    process_time_map: Optional[Dict[str, int]],
    route_code: int,
    device_mode: str,
    obs_config: Optional[Dict[str, Any]],
    route_config: Mapping[str, Any],
    route_name: Optional[str],
) -> Dict[str, object]:
    """构建 cascade 运行网：固定 place 拓扑 + route 动态变迁集合。"""
    process_time_map = process_time_map or {}
    mode = str(device_mode).lower()
    source_cfg = dict(route_config.get("source") or {"name": "LP", "capacity": max(1, n_wafer)})
    sink_cfg = dict(route_config.get("sink") or {"name": "LP_done", "capacity": max(1, n_wafer)})
    source_name = str(source_cfg.get("name", "LP"))
    sink_name = str(sink_cfg.get("name", "LP_done"))
    if source_name != "LP" or sink_name != "LP_done":
        raise ValueError(
            "cascade fixed topology requires source=LP and sink=LP_done"
        )
    selected_route_name = route_name

    chambers_cfg = dict(route_config.get("chambers") or {})
    chamber_kind_map: Dict[str, str] = {}
    for cname, cfg in chambers_cfg.items():
        chamber_kind_map[str(cname)] = str((cfg or {}).get("kind", "process"))

    robots_cfg_raw = dict(route_config.get("robots") or {})
    robots_cfg: Dict[str, CompiledRobotSpec] = {}
    for rb_name, rb in robots_cfg_raw.items():
        managed = tuple(str(x) for x in (rb or {}).get("managed_chambers", ()))
        transport_place = str((rb or {}).get("transport_place", str(rb_name))).replace("d_", "")
        robots_cfg[str(rb_name)] = CompiledRobotSpec(
            name=str(rb_name),
            managed_chambers=managed,
            transport_place=transport_place,
            priority=int((rb or {}).get("priority", 0)),
        )

    route_entry = dict((route_config.get("routes") or {}).get(selected_route_name) or {})
    route_ir = compile_route_stages(
        route_name=selected_route_name,
        route_cfg=route_entry,
        source_name=source_name,
        sink_name=sink_name,
        chamber_kind_map=chamber_kind_map,
        robots=robots_cfg,
    )

    # 每条 route 的 stage 级参数（process/cleaning）覆盖 chamber 级默认值
    route_stage_proc_time: Dict[str, int] = {}
    route_stage_clean_dur: Dict[str, int] = {}
    route_stage_clean_trig: Dict[str, int] = {}

    def _set_consistent_int(target: Dict[str, int], name: str, value: int, field_name: str) -> None:
        if name in target and int(target[name]) != int(value):
            raise ValueError(
                f"route {selected_route_name} has conflicting {field_name} for {name}: "
                f"{target[name]} vs {value}"
            )
        target[name] = int(value)

    for stage in route_ir.stages:
        is_process_stage = str(stage.stage_type) == "process"
        for chamber_name in stage.candidates:
            if chamber_name in {source_name, sink_name}:
                continue
            # 对 process stage，<=0 视为“未指定”，避免把未知工时覆盖成 0
            if stage.stage_process_time is not None:
                p_val = float(stage.stage_process_time)
                if (not is_process_stage) or p_val > 0:
                    _set_consistent_int(
                        route_stage_proc_time,
                        chamber_name,
                        int(round(p_val)),
                        "process_time",
                    )
            if stage.stage_cleaning_duration is not None:
                _set_consistent_int(
                    route_stage_clean_dur,
                    chamber_name,
                    int(stage.stage_cleaning_duration),
                    "cleaning_duration",
                )
            if stage.stage_cleaning_trigger_wafers is not None:
                _set_consistent_int(
                    route_stage_clean_trig,
                    chamber_name,
                    int(stage.stage_cleaning_trigger_wafers),
                    "cleaning_trigger_wafers",
                )

    ch_pre = _route_ir_preprocess_chambers(route_ir, source_name, sink_name)
    merged_for_preprocess: Dict[str, int] = dict(process_time_map)
    merged_for_preprocess.update(route_stage_proc_time)
    processed_pt = preprocess_process_time_map(merged_for_preprocess, ch_pre, route_config)

    static_topology = get_topology()
    id2p_name = list(static_topology["id2p_name"])
    all_t_names = list(static_topology["id2t_name"])
    all_pre = np.array(static_topology["pre"], dtype=int)
    all_pst = np.array(static_topology["pst"], dtype=int)
    all_t_target_place = dict(static_topology["t_target_place"])

    # ===== 根据路径信息动态选择变迁 =====
    route_source_target_transport = _build_route_source_target_transport(route_ir)
    active_u_names: Set[str] = set()
    active_t_names: Set[str] = set()
    stage_target_order: List[str] = []
    stage_target_seen: Set[str] = set()
    for stage in route_ir.stages[1:]:
        for dst in stage.candidates:
            d = str(dst)
            if d not in stage_target_seen:
                stage_target_seen.add(d)
                stage_target_order.append(d)
    for (src, dst), transport in route_source_target_transport.items():
        active_u_names.add(f"u_{src}_{transport}")
        active_t_names.add(f"t_{transport}_{dst}")

    # 筛选出路径中设计的变迁，对t_*变迁来说，记录其目标
    selected_t_indices: List[int] = []
    id2t_name: List[str] = []
    t_target_place: Dict[str, str] = {}
    for idx, t_name in enumerate(all_t_names):
        if t_name.startswith("u_") and t_name in active_u_names:
            selected_t_indices.append(idx)
            id2t_name.append(t_name)
            continue
        if t_name.startswith("t_") and t_name in active_t_names:
            selected_t_indices.append(idx)
            id2t_name.append(t_name)
            target = all_t_target_place.get(t_name)
            if target is not None:
                t_target_place[t_name] = str(target)

    if not id2t_name:
        raise ValueError("route produced empty transition set")

    pre = np.array(all_pre[:, selected_t_indices], dtype=int)
    pst = np.array(all_pst[:, selected_t_indices], dtype=int)
    t_count = len(id2t_name)

    # ======= 构造晶圆路由队列 ===========
    target_code_map: Dict[str, int] = {
        name: i + 1 for i, name in enumerate(stage_target_order)
    }
    t_route_code_map: Dict[str, int] = {}
    for t_name in id2t_name:
        if not t_name.startswith("t_"):
            continue
        target = t_target_place.get(t_name)
        if target is None:
            continue
        code = int(target_code_map.get(str(target), -1))
        if code > 0:
            t_route_code_map[t_name] = code

    route_queue: List[object] = []
    for idx in range(len(route_ir.stages) - 1):
        route_queue.append(-1)
        next_stage = route_ir.stages[idx + 1]
        gate_codes: List[int] = []
        for dst in next_stage.candidates:
            code = int(target_code_map.get(str(dst), -1))
            if code > 0:
                gate_codes.append(code)
        if len(gate_codes) == 1:
            route_queue.append(gate_codes[0])
        else:
            route_queue.append(tuple(gate_codes))
    token_route_queue = tuple(route_queue)

    token_plan: TokenRoutePlan = build_token_route_plan(
        route_ir=route_ir,
        transition_names=[f"t_{name}" for name in stage_target_order],
    )

    p_idx = {name: i for i, name in enumerate(id2p_name)}

    # 模块参数
    modules: Dict[str, SingleModuleSpec] = {}
    # 运行时 token 数由 n_wafer 决定；若配置里的 source/sink 容量小于 n_wafer，
    # 会导致后期 LP_done 满仓后 LLD 无目标可放（u_LLD 长期不使能）。
    source_capacity = max(int(source_cfg.get("capacity", max(1, n_wafer))), int(n_wafer))
    sink_capacity = max(int(sink_cfg.get("capacity", max(1, n_wafer))), int(n_wafer))
    modules[source_name] = SingleModuleSpec(tokens=n_wafer, ptime=0, capacity=max(1, source_capacity))
    modules[sink_name] = SingleModuleSpec(tokens=0, ptime=0, capacity=max(1, sink_capacity))

    for name in id2p_name:
        if name in {source_name, sink_name}:
            continue
        if name in {"TM2", "TM3"}:
            # transport
            rb_cfg = next(
                (
                    dict(v)
                    for v in (route_config.get("robots") or {}).values()
                    if str(v.get("transport_place", "")).replace("d_", "") == name
                ),
                {},
            )
            modules[name] = SingleModuleSpec(
                tokens=0,
                ptime=int(rb_cfg.get("dwell_time", ttime)),
                capacity=int(rb_cfg.get("capacity", robot_capacity)),
            )
            continue
        c_cfg = dict(chambers_cfg.get(name) or {})
        if name in processed_pt:
            ptime = int(processed_pt[name])
        else:
            ptime = int(
                route_stage_proc_time.get(
                    name,
                    process_time_map.get(name, c_cfg.get("process_time", 0)),
                )
            )
        modules[name] = SingleModuleSpec(
            tokens=0,
            ptime=ptime,
            capacity=int(c_cfg.get("capacity", 1)),
        )

    m0 = np.array([modules[name].tokens for name in id2p_name], dtype=int)
    md = m0.copy()
    md[p_idx[source_name]] = 0
    md[p_idx[sink_name]] = n_wafer
    ptime = np.array([modules[name].ptime for name in id2p_name], dtype=int)
    capacity = np.array([modules[name].capacity for name in id2p_name], dtype=int)
    ttime_arr = np.array([ttime for _ in range(t_count)], dtype=int)

    # transport onehot map
    # 配置驱动路径默认使用逐目标编码；cascade 固定为 8 维目标字典。
    tm_target_onehot_map: Dict[str, Dict[str, int]] = {}
    for hop in route_ir.transports:
        tp = str(hop.transport_place)
        dst_candidates = tuple(route_ir.stages[hop.to_stage_idx].candidates)
        if mode == "cascade" and tp == "TM2":
            tm_target_onehot_map[tp] = dict(CASCADE_TM2_TARGET_ONEHOT)
            continue
        if mode == "cascade" and tp == "TM3":
            tm_target_onehot_map[tp] = dict(CASCADE_TM3_TARGET_ONEHOT)
            continue
        m = tm_target_onehot_map.setdefault(tp, {})
        for dst_name in dst_candidates:
            if dst_name not in m:
                m[dst_name] = len(m)

    ctx = obs_config or {}
    p_res = int(ctx.get("P_Residual_time", 15))
    d_res = int(ctx.get("D_Residual_time", 10))
    clean_dur_default = int(ctx.get("cleaning_duration", 150))
    clean_trig_default = int(ctx.get("cleaning_trigger_wafers", 5))
    cleaning_duration_map: Dict[str, int] = dict(ctx.get("cleaning_duration_map") or {})
    cleaning_trigger_wafers_map: Dict[str, int] = dict(ctx.get("cleaning_trigger_wafers_map") or {})
    scrap_clip = float(ctx.get("scrap_clip_threshold", 20.0))

    buffer_names = {
        name for name, cfg in chambers_cfg.items()
        if str((cfg or {}).get("kind", "")) == "buffer"
    }

    # ============= 构造marks ==============
    marks: List[Place] = []
    for name in id2p_name:
        spec = modules[name]
        if name == source_name or name == sink_name:
            ptype = SOURCE
        elif name in {"TM2", "TM3"}:
            ptype = ROBOT
        else:
            kind = str((chambers_cfg.get(name) or {}).get("kind", "process"))
            ptype = 5 if kind in {"buffer", "loadlock"} else 1

        if obs_config is not None:
            if name == source_name:
                place = SR(name=name, capacity=100, processing_time=0, type=SOURCE, n_wafer=n_wafer)
            elif name == sink_name:
                place = SR(name=name, capacity=100, processing_time=0, type=SOURCE)
            elif name in {"TM2", "TM3"}:
                tm_map = tm_target_onehot_map.get(name, {})
                if mode == "cascade" and name == "TM2":
                    tm_map = dict(CASCADE_TM2_TARGET_ONEHOT)
                elif mode == "cascade" and name == "TM3":
                    tm_map = dict(CASCADE_TM3_TARGET_ONEHOT)
                onehot_dim = max(tm_map.values(), default=-1) + 1 if tm_map else 0
                place = TM(
                    name=name,
                    capacity=spec.capacity,
                    processing_time=spec.ptime,
                    type=ROBOT,
                    D_Residual_time=d_res,
                    target_onehot_map=tm_map,
                    onehot_dim=onehot_dim,
                )
            elif ptype == 5:
                place = LL(name=name, capacity=spec.capacity, processing_time=spec.ptime, type=ptype)
            elif ptype == CHAMBER:
                c_dur = int(
                    route_stage_clean_dur.get(
                        name,
                        cleaning_duration_map.get(
                            name,
                            (chambers_cfg.get(name) or {}).get("cleaning_duration", clean_dur_default),
                        ),
                    )
                )
                c_trig = int(
                    route_stage_clean_trig.get(
                        name,
                        cleaning_trigger_wafers_map.get(
                            name,
                            (chambers_cfg.get(name) or {}).get("cleaning_trigger_wafers", clean_trig_default),
                        ),
                    )
                )
                place = PM(
                    name=name,
                    capacity=spec.capacity,
                    processing_time=spec.ptime,
                    type=ptype,
                    P_Residual_time=p_res,
                    cleaning_duration=max(1, c_dur),
                    cleaning_trigger_wafers=max(1, c_trig),
                    scrap_clip_threshold=scrap_clip,
                )
            else:
                place = Place(name=name, capacity=spec.capacity, processing_time=spec.ptime, type=ptype)
        else:
            place = Place(name=name, capacity=spec.capacity, processing_time=spec.ptime, type=ptype)

        marks.append(place)

    # ===== 注入token =====
    LP_place = marks[p_idx[source_name]]
    _add_token_to_LP(n_wafer, LP_place, token_route_queue)

    route_meta = build_route_meta_from_route_ir(route_ir, buffer_names=buffer_names or BUFFER_NAMES)
    full_timeline_chambers = tuple(
        name for name in id2p_name
        if (name.startswith("PM") or name in {"LLC", "LLD"})
    )
    route_meta["chambers"] = full_timeline_chambers
    route_meta["timeline_chambers"] = full_timeline_chambers
    process_time_map_out = {
        n: int(modules[n].ptime)
        for n in full_timeline_chambers
        if n in modules
    }

    pre_place_indices: List[np.ndarray] = [np.flatnonzero(pre[:, t] > 0) for t in range(t_count)]
    pst_place_indices: List[np.ndarray] = [np.flatnonzero(pst[:, t] > 0) for t in range(t_count)]
    transport_pre_place_idx: List[int] = []
    for t in range(t_count):
        found = next(
            (int(idx) for idx in pre_place_indices[t] if id2p_name[int(idx)] in {"TM2", "TM3"}),
            -1,
        )
        transport_pre_place_idx.append(int(found))

    return {
        "m0": m0,
        "P": pre.shape[0],
        "T": pre.shape[1],
        "pre_place_indices": pre_place_indices,
        "pst_place_indices": pst_place_indices,
        "transport_pre_place_idx": transport_pre_place_idx,
        "ttime": ttime_arr,
        "capacity": capacity,
        "id2p_name": id2p_name,
        "id2t_name": id2t_name,
        "idle_idx": {"start": p_idx[source_name], "end": p_idx[sink_name]},
        "marks": marks,
        "n_wafer": n_wafer,
        "n_wafer_route1": n_wafer,
        "n_wafer_route2": 0,
        "single_route_code": route_code,
        "single_device_mode": mode,
        "route_meta": route_meta,
        "t_route_code_map": t_route_code_map,
        "t_target_place_map": t_target_place,
        "route_source_target_transport": route_source_target_transport,
        "token_route_queue_template": token_route_queue,
        "token_route_plan_template": token_plan,
        "route_ir": route_ir,
        "process_time_map": process_time_map_out,
        "fixed_topology": True,
    }


def _add_token_to_LP(n_wafer: int, place: Place, token_route_queue: tuple[object, ...]):

        for tok_id in range(n_wafer):
            place.append(
                BasedToken(
                    enter_time=0,
                    token_id=tok_id,
                    route_type=1,
                    step=0,
                    where=0,
                    route_queue=token_route_queue,
                    route_head_idx=0,
                )
            )


@dataclass
class SingleModuleSpec:
    tokens: int = 0
    ptime: int = 0
    capacity: int = 1


def build_single_device_net(
    n_wafer: int,
    ttime: int = 5,
    robot_capacity: int = 1,
    process_time_map: Optional[Dict[str, int]] = None,
    route_code: int = 0,
    device_mode: str = "cascade",
    obs_config: Optional[Dict[str, Any]] = None,
    route_config: Optional[Mapping[str, Any]] = None,
    route_name: Optional[str] = None,
) -> Dict[str, object]:
    """
    构建 cascade-only 固定拓扑 Petri 网结构。

    约束：
    - route_config 必填，schema 需包含 source/sink/chambers/robots/routes
    - route_name 用于选择具体路线
    - route_code 仅用于兼容旧配置的路由别名选择
    - device_mode 必须是 cascade，single 路径已下线

    返回 dict 除 pre/pst/m0/md/marks/id2p_name/id2t_name 等外，还包含预计算索引（供 get_enable_t/_fire 复用）：
    - pre_place_indices: List[np.ndarray]，pre_place_indices[t] 为变迁 t 的前置库所下标
    - pst_place_indices: List[np.ndarray]，pst_place_indices[t] 为变迁 t 的后置库所下标
    - transport_pre_place_idx: List[int]，transport_pre_place_idx[t] 为变迁 t 的运输位前置库所下标（无则为 -1）
    - process_time_map: Dict[str, int]，与 route_meta["chambers"] 一致的腔室工序时长（已含默认填充与取整到 5 秒）
    """
    mode = str(device_mode).lower()
    raw_pm = dict(process_time_map or {})
    route_code = int(route_code)
    if mode != "cascade":
        raise ValueError("build_single_device_net now supports cascade only")
    if route_config is None:
        raise ValueError("build_single_device_net requires route_config")
    return _build_single_device_net_from_route_config(
        n_wafer=n_wafer,
        ttime=ttime,
        robot_capacity=robot_capacity,
        process_time_map=raw_pm,
        route_code=route_code,
        device_mode=mode,
        obs_config=obs_config,
        route_config=route_config,
        route_name=route_name,
    )
