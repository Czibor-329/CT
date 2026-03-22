from data.petri_configs.env_config import PetriEnvConfig
from solutions.Continuous_model.pn_single import ClusterTool
from pathlib import Path


def _fire_by_name(net: ClusterTool, transition_name: str) -> None:
    tid = net.id2t_name.index(transition_name)
    net.step(a1=tid, detailed_reward=True)


def _pick_one_transition(net: ClusterTool, prefix: str) -> str:
    """返回首个以 prefix 开头的变迁名。"""
    for name in net.id2t_name:
        if str(name).startswith(prefix):
            return str(name)
    raise AssertionError(f"transition with prefix {prefix!r} not found")


def _enabled_transition_indices(net: ClusterTool) -> list[int]:
    T = int(net.T)
    m = net.get_action_mask(wait_action_start=T, n_actions=T + len(net.wait_durations))
    return [i for i in range(T) if bool(m[i])]


def _cascade_cfg(route_name: str, route_code: int, process_time_map: dict[str, int]) -> PetriEnvConfig:
    """加载 cascade 配置并注入最小测试覆盖参数。"""
    cfg = PetriEnvConfig.load(Path("data/petri_configs/cascade.json"))
    cfg.n_wafer = 1
    cfg.stop_on_scrap = False
    cfg.device_mode = "cascade"
    cfg.route_code = int(route_code)
    cfg.single_route_name = str(route_name)
    cfg.process_time_map = {str(k): int(v) for k, v in dict(process_time_map).items()}
    return cfg


def test_cascade_token_route_queue_advances_on_each_fire():
    cfg = _cascade_cfg(
        route_name="2-1",
        route_code=2,
        process_time_map={
            "PM7": 5,
            "PM8": 5,
            "PM1": 5,
            "PM2": 5,
            "LLD": 5,
            "PM9": 5,
            "PM10": 5,
        },
    )
    net = ClusterTool(config=cfg)

    lp = net._get_place("LP")
    tok = lp.head()
    assert hasattr(tok, "route_queue")
    assert hasattr(tok, "route_head_idx")
    assert tok.route_queue[tok.route_head_idx] == -1

    _fire_by_name(net, _pick_one_transition(net, "u_LP_"))
    tm2_tok = net._get_place("TM2").head()
    gate = tm2_tok.route_queue[tm2_tok.route_head_idx]
    assert isinstance(gate, tuple)
    assert len(gate) == 2

    _fire_by_name(net, _pick_one_transition(net, "t_TM2_PM7"))
    pm7 = net._get_place("PM7")
    pm7_tok = pm7.head()
    assert pm7_tok.route_queue[pm7_tok.route_head_idx] == -1


def test_cascade_t_routing_uses_route_queue_gate():
    cfg = _cascade_cfg(
        route_name="1-1",
        route_code=1,
        process_time_map={"PM7": 5, "PM8": 5, "PM3": 5, "PM4": 5, "LLD": 5, "PM9": 5, "PM10": 5},
    )
    net = ClusterTool(config=cfg)

    lp = net._get_place("LP")
    tok = lp.head()
    assert hasattr(tok, "route_queue")
    assert hasattr(tok, "route_head_idx")
    _fire_by_name(net, _pick_one_transition(net, "u_LP_"))
    net.step(detailed_reward=True, wait_duration=5)
    enabled_names = {net.id2t_name[t] for t in _enabled_transition_indices(net)}
    assert any(name in enabled_names for name in ("t_TM2_PM7", "t_TM2_PM8"))
    assert "t_TM3_PM3" not in enabled_names
    assert "t_TM3_PM4" not in enabled_names


def test_cascade_route4_token_route_queue_shape_and_tail_gate():
    cfg = _cascade_cfg(
        route_name="1-4",
        route_code=4,
        process_time_map={"PM7": 5, "PM8": 5, "LLD": 5},
    )
    net = ClusterTool(config=cfg)
    lp_tok = net._get_place("LP").head()
    queue = lp_tok.route_queue

    assert queue[0] == -1
    assert len(queue) == 12
    assert queue[1] == (net._t_route_code_map["t_TM2_PM7"], net._t_route_code_map["t_TM2_PM8"])
    assert queue[3] == net._t_route_code_map["t_TM2_LLC"]
    assert isinstance(queue[5], tuple) and len(queue[5]) == 2
    assert isinstance(queue[7], tuple) and len(queue[7]) == 3
    assert queue[9] == net._t_route_code_map["t_TM3_LLD"]
    assert queue[-1] == net._t_route_code_map["t_TM2_LP_done"]


def test_cascade_route5_token_route_queue_shape_and_tail_gate():
    cfg = _cascade_cfg(
        route_name="2-4",
        route_code=5,
        process_time_map={"PM7": 5, "PM8": 5, "PM9": 5, "PM10": 5},
    )
    net = ClusterTool(config=cfg)
    lp_tok = net._get_place("LP").head()
    queue = lp_tok.route_queue

    assert queue[0] == -1
    assert len(queue) == 6
    assert queue[1] == (net._t_route_code_map["t_TM2_PM7"], net._t_route_code_map["t_TM2_PM8"])
    assert queue[3] == (net._t_route_code_map["t_TM2_PM9"], net._t_route_code_map["t_TM2_PM10"])
    assert queue[-1] == net._t_route_code_map["t_TM2_LP_done"]
