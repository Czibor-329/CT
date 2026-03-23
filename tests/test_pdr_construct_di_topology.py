import re

from solutions.PDR.construct import build_pdr_net


def test_pdr_uses_shared_d_places_by_robot_and_dst() -> None:
    info = build_pdr_net(n_wafer=3)
    place_names = info["id2p_name"]

    assert "d_TM2" not in place_names
    assert "d_TM3" not in place_names

    d_places = [name for name in place_names if re.fullmatch(r"d_TM[23]_[A-Za-z0-9_]+", name)]
    assert sorted(d_places) == sorted(
        [
            "d_TM2_PM7",
            "d_TM2_PM8",
            "d_TM2_LLC",
            "d_TM2_LP_done",
            "d_TM3_PM1",
            "d_TM3_PM2",
            "d_TM3_LLD",
        ]
    )


def test_pdr_has_tm_resource_places_and_seize_release_arcs() -> None:
    info = build_pdr_net(n_wafer=2)
    id2p = info["id2p_name"]
    id2t = info["id2t_name"]
    pre = info["pre"]
    pst = info["pst"]
    m0 = info["m0"]
    cap = info["capacity"]

    tm2_idx = id2p.index("TM2")
    tm3_idx = id2p.index("TM3")
    assert m0[tm2_idx] == 1
    assert m0[tm3_idx] == 1
    assert cap[tm2_idx] == 1
    assert cap[tm3_idx] == 1

    u_name_pattern = re.compile(r"^u_[^_]+_(TM2|TM3)_\d+$")
    for t_idx, t_name in enumerate(id2t):
        if t_name.startswith("u_"):
            m = u_name_pattern.match(t_name)
            assert m is not None
            robot = str(m.group(1))
            tm_idx = id2p.index(robot)
            assert pre[tm_idx, t_idx] == 1
            assert pst[tm_idx, t_idx] == 0
        if t_name.startswith("t_"):
            robot = t_name.split("_")[1]
            tm_idx = id2p.index(robot)
            assert pst[tm_idx, t_idx] == 1
            assert pre[tm_idx, t_idx] == 0


def test_each_d_connects_u_group_and_single_t() -> None:
    info = build_pdr_net(n_wafer=2)
    id2p = info["id2p_name"]
    id2t = info["id2t_name"]
    pre = info["pre"]
    pst = info["pst"]

    d_places = [name for name in id2p if re.fullmatch(r"d_TM[23]_[A-Za-z0-9_]+", name)]
    for d_name in d_places:
        p_idx = id2p.index(d_name)
        incoming_t_idx = [t for t in range(len(id2t)) if pst[p_idx, t] > 0]
        outgoing_t_idx = [t for t in range(len(id2t)) if pre[p_idx, t] > 0]

        assert len(incoming_t_idx) >= 1
        assert len(outgoing_t_idx) == 1
        for t_idx in incoming_t_idx:
            assert id2t[t_idx].startswith("u_")
        assert id2t[outgoing_t_idx[0]].startswith("t_")
