import numpy as np
import torch
from tensordict import TensorDict

from solutions.PDR.net import Petri
from solutions.PDR.train_pdr import EnvPDR


def test_prepare_train_candidates_keeps_smallest_delta_top_k(monkeypatch) -> None:
    petri = Petri(n_wafer=2, ttime=5, takt_cycle=[0, 0])
    petri.reset()
    petri.reset_train_state()
    base_marks = petri._clone_marks(petri.train_current_marks)

    deltas = [9, 3, 1, 7, 0, 4, 8, 2, 6, 5]

    def fake_collect(*args, **kwargs) -> None:
        import solutions.PDR.net as net_mod

        net_mod.LEAF_NODES = []
        net_mod.LEAF_CLOCKS = []
        net_mod.LEAF_PATHS = []
        net_mod.LEAF_PATH_RECORDS = []
        net_mod.LEAF_LP_RELEASE_COUNTS = []
        for idx, delta in enumerate(deltas):
            m = petri.train_current_m.copy()
            m[petri.terminal_place_idx] = idx % (petri.n_wafer + 1)
            net_mod.LEAF_NODES.append({"m": m, "marks": petri._clone_marks(base_marks)})
            net_mod.LEAF_CLOCKS.append(int(petri.train_current_clock + delta))
            net_mod.LEAF_PATHS.append([])
            net_mod.LEAF_PATH_RECORDS.append([])
            net_mod.LEAF_LP_RELEASE_COUNTS.append(0)

    monkeypatch.setattr(petri, "collect_leaves_iterative", fake_collect)

    prepared = petri.prepare_train_candidates(candidate_k=8)
    kept_deltas = list(prepared["candidate_deltas"])

    assert bool(prepared["has_candidate"]) is True
    assert int(prepared["valid_count"]) == 8
    assert kept_deltas == sorted(deltas)[:8]
    assert prepared["action_mask"].tolist() == [True] * 8


def test_prepare_train_candidates_builds_mask_when_candidates_not_enough(monkeypatch) -> None:
    petri = Petri(n_wafer=2, ttime=5, takt_cycle=[0, 0])
    petri.reset()
    petri.reset_train_state()
    base_marks = petri._clone_marks(petri.train_current_marks)

    def fake_collect(*args, **kwargs) -> None:
        import solutions.PDR.net as net_mod

        net_mod.LEAF_NODES = []
        net_mod.LEAF_CLOCKS = []
        net_mod.LEAF_PATHS = []
        net_mod.LEAF_PATH_RECORDS = []
        net_mod.LEAF_LP_RELEASE_COUNTS = []
        for delta in [1, 4, 2]:
            net_mod.LEAF_NODES.append({"m": petri.train_current_m.copy(), "marks": petri._clone_marks(base_marks)})
            net_mod.LEAF_CLOCKS.append(int(petri.train_current_clock + delta))
            net_mod.LEAF_PATHS.append([])
            net_mod.LEAF_PATH_RECORDS.append([])
            net_mod.LEAF_LP_RELEASE_COUNTS.append(0)

    monkeypatch.setattr(petri, "collect_leaves_iterative", fake_collect)
    prepared = petri.prepare_train_candidates(candidate_k=8)

    assert bool(prepared["has_candidate"]) is True
    assert int(prepared["valid_count"]) == 3
    assert prepared["action_mask"].tolist() == [True, True, True, False, False, False, False, False]


def test_train_step_returns_scrap_penalty_and_resets_when_no_leaf(monkeypatch) -> None:
    petri = Petri(n_wafer=2, ttime=5, takt_cycle=[0, 0])
    petri.reset()
    petri.reset_train_state()
    petri.train_current_m = np.zeros_like(petri.train_current_m)

    def fake_collect(*args, **kwargs) -> None:
        import solutions.PDR.net as net_mod

        net_mod.LEAF_NODES = []
        net_mod.LEAF_CLOCKS = []
        net_mod.LEAF_PATHS = []
        net_mod.LEAF_PATH_RECORDS = []
        net_mod.LEAF_LP_RELEASE_COUNTS = []

    monkeypatch.setattr(petri, "collect_leaves_iterative", fake_collect)

    obs, reward, done, info = petri.train_step(action_idx=0, candidate_k=8, scrap_penalty=-1000.0)

    assert done is True
    assert float(reward) == -1000.0
    assert bool(info["scrap"]) is True
    assert isinstance(info["time"], int)
    assert np.array_equal(obs.astype(np.int32), petri.m0.astype(np.int32))


def test_env_step_adds_finish_bonus_on_top_of_base_reward(monkeypatch) -> None:
    env = EnvPDR(seed=0)

    def fake_prepare(candidate_k: int = 8):
        return {
            "has_candidate": True,
            "candidate_k": int(candidate_k),
            "valid_count": 1,
            "action_mask": np.array([True] + [False] * (candidate_k - 1), dtype=bool),
            "candidate_deltas": [5],
            "candidate_states": [],
        }

    def fake_train_step(action_idx: int, candidate_k: int, scrap_penalty: float, prepared=None):
        _ = action_idx
        _ = candidate_k
        _ = scrap_penalty
        _ = prepared
        obs = np.zeros(env.net.P, dtype=np.float32)
        info = {
            "action_mask": np.array([False] * env.candidate_k, dtype=bool),
            "scrap": False,
            "delta_clock": 5,
            "finish": True,
            "candidate_count": 1,
            "time": 123,
        }
        return obs, -5.0, True, info

    monkeypatch.setattr(env.net, "prepare_train_candidates", fake_prepare)
    monkeypatch.setattr(env.net, "train_step", fake_train_step)

    out = env._step(TensorDict({"action": torch.tensor(0)}, batch_size=[]))
    assert bool(out["finish"].item()) is True
    assert bool(out["scrap"].item()) is False
    assert bool(out["terminated"].item()) is True
    assert float(out["reward"].item()) == 995.0
    assert int(out["time"].item()) == 123
