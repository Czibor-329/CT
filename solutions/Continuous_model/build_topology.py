import numpy as np
from typing import Tuple,Dict,List,Optional,Mapping
from pathlib import Path


_FIXED_CASCADE_TOPOLOGY_VERSION = 2
_FIXED_CASCADE_PLACE_ORDER: Tuple[str, ...] = (
    "LP","PM1","PM2","PM3","PM4",
    "PM5","PM6","PM7","PM8","PM9","PM10",
    "LLC","LLD","LP_done","TM2","TM3",
)
_FIXED_CASCADE_SOURCES: Tuple[str, ...] = (
    "LP","PM1","PM2","PM3","PM4",
    "PM5","PM6","PM7","PM8","PM9",
    "PM10","LLC","LLD",
)
_FIXED_CASCADE_TARGETS: Tuple[str, ...] = (
    "PM1","PM2","PM3","PM4","PM5",
    "PM6","PM7","PM8","PM9","PM10",
    "LLC","LLD","LP_done",
)
_FIXED_CASCADE_TRANSPORTS: Tuple[str, ...] = ("TM2", "TM3")
_TM2_SCOPE: frozenset[str] = frozenset({
    "LP", "PM7", "PM8", "PM9", "PM10", "LLC", "LLD", "LP_done",
})
_TM3_SCOPE: frozenset[str] = frozenset({
    "PM1", "PM2", "PM3", "PM4", "PM5", "PM6", "LLC", "LLD",
})


def _build_topology() -> Dict[str, object]:
    """构建级联固定拓扑（按 TM2/TM3 作用域生成白名单弧）。"""
    id2p_name = list(_FIXED_CASCADE_PLACE_ORDER)
    id2t_name: List[str] = []
    u_edges: List[Tuple[str, str, str]] = []
    t_edges: List[Tuple[str, str, str]] = []
    transport_scope: Dict[str, frozenset[str]] = {
        "TM2": _TM2_SCOPE,
        "TM3": _TM3_SCOPE,
    }
    for transport in _FIXED_CASCADE_TRANSPORTS:
        scope = transport_scope[transport]
        for src in _FIXED_CASCADE_SOURCES:
            if src not in scope or src == "LP_done":
                continue
            t_name = f"u_{src}_{transport}"
            id2t_name.append(t_name)
            u_edges.append((src, t_name, transport))
        for dst in _FIXED_CASCADE_TARGETS:
            if dst not in scope or dst == "LP":
                continue
            t_name = f"t_{transport}_{dst}"
            id2t_name.append(t_name)
            t_edges.append((transport, t_name, dst))

    p_idx = {name: i for i, name in enumerate(id2p_name)}
    t_idx = {name: i for i, name in enumerate(id2t_name)}
    pre = np.zeros((len(id2p_name), len(id2t_name)), dtype=int)
    pst = np.zeros((len(id2p_name), len(id2t_name)), dtype=int)
    t_target_place: Dict[str, str] = {}
    source_to_transport_u: Dict[Tuple[str, str], str] = {}
    for src, t_name, transport in u_edges:
        pre[p_idx[src], t_idx[t_name]] = 1
        pst[p_idx[transport], t_idx[t_name]] = 1
        source_to_transport_u[(src, transport)] = t_name
    for transport, t_name, dst in t_edges:
        pre[p_idx[transport], t_idx[t_name]] = 1
        pst[p_idx[dst], t_idx[t_name]] = 1
        t_target_place[t_name] = dst

    return {
        "id2p_name": id2p_name,
        "id2t_name": id2t_name,
        "pre": pre,
        "pst": pst,
        "t_target_place": t_target_place,
        "source_to_transport_u": source_to_transport_u,
    }


def _load_topology() -> Optional[Dict[str, object]]:
    """从磁盘加载固定拓扑缓存；不存在或损坏则返回 None。"""
    root = Path(__file__).resolve().parents[2]
    cache_file = root / "data" / "cache" / f"topology_v{_FIXED_CASCADE_TOPOLOGY_VERSION}.npz"
    if not cache_file.exists():
        return None
    try:
        blob = np.load(cache_file, allow_pickle=True)
        version_arr = np.array(blob["version"]).reshape(-1)
        version = int(version_arr[0]) if version_arr.size > 0 else -1
        if version != _FIXED_CASCADE_TOPOLOGY_VERSION:
            return None
        pre = np.array(blob["pre"], dtype=int)
        pst = np.array(blob["pst"], dtype=int)
        id2p_name = [str(x) for x in blob["id2p_name"].tolist()]
        id2t_name = [str(x) for x in blob["id2t_name"].tolist()]
        t_target_items = blob["t_target_items"].tolist()
        source_transport_items = blob["source_transport_items"].tolist()
        t_target_place = {str(k): str(v) for k, v in t_target_items}
        source_to_transport_u = {
            (str(k1), str(k2)): str(v)
            for (k1, k2), v in source_transport_items
        }
        return {
            "id2p_name": id2p_name,
            "id2t_name": id2t_name,
            "pre": pre,
            "pst": pst,
            "t_target_place": t_target_place,
            "source_to_transport_u": source_to_transport_u,
        }
    except Exception:
        return None


def _save_topology(topology: Mapping[str, object]) -> None:
    """将固定拓扑写入磁盘缓存，供跨进程复用。"""
    root = Path(__file__).resolve().parents[2]
    cache_file = root / "data" / "cache" / f"topology_v{_FIXED_CASCADE_TOPOLOGY_VERSION}.npz"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    t_target_items = list((topology.get("t_target_place") or {}).items())
    source_transport_items = list((topology.get("source_to_transport_u") or {}).items())
    np.savez(
        cache_file,
        version=np.array([_FIXED_CASCADE_TOPOLOGY_VERSION], dtype=int),
        pre=np.array(topology["pre"], dtype=int),
        pst=np.array(topology["pst"], dtype=int),
        id2p_name=np.array(list(topology["id2p_name"]), dtype=object),
        id2t_name=np.array(list(topology["id2t_name"]), dtype=object),
        t_target_items=np.array(t_target_items, dtype=object),
        source_transport_items=np.array(source_transport_items, dtype=object),
    )


def get_topology() -> Dict[str, object]:
    """获取级联固定拓扑：优先读缓存，未命中则构建并落盘。"""
    cached = _load_topology()
    if cached is not None:
        return cached
    built = _build_topology()
    _save_topology(built)
    return built