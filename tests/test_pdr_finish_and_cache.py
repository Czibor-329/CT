import numpy as np

from solutions.PDR.net import Petri


def test_pdr_has_transition_place_cache() -> None:
    petri = Petri(n_wafer=2, ttime=5, takt_cycle=[0, 0])

    assert len(petri.pre_places_by_t) == petri.T
    assert len(petri.pst_places_by_t) == petri.T

    for t in range(petri.T):
        expected_pre = np.nonzero(petri.pre[:, t] > 0)[0].tolist()
        expected_pst = np.nonzero(petri.pst[:, t] > 0)[0].tolist()
        assert petri.pre_places_by_t[t] == expected_pre
        assert petri.pst_places_by_t[t] == expected_pst


def test_pdr_finish_only_depends_on_terminal_place_tokens() -> None:
    petri = Petri(n_wafer=2, ttime=5, takt_cycle=[0, 0])
    m = np.zeros_like(petri.m0)
    m[petri.terminal_place_idx] = petri.n_wafer
    m[petri.idle_idx["start"]] = 1

    assert petri.is_finished_marking(m) is True
