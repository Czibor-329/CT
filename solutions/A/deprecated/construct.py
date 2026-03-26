from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple, Union

import numpy as np

Stage = Union[str, List[str]]
INF = 10**9


@dataclass(slots=True)
class BasedToken:
    enter_time: int
    stay_time: int = 0
    token_id: int = -1
    machine: int = -1
    route_type: int = 0
    step: int = 0
    where: int = 0

    def clone(self) -> "BasedToken":
        return BasedToken(
            enter_time=self.enter_time,
            stay_time=self.stay_time,
            token_id=self.token_id,
            machine=self.machine,
            route_type=self.route_type,
            step=self.step,
            where=self.where,
        )


@dataclass
class Place:
    name: str
    capacity: int
    processing_time: int
    type: int
    tokens: Deque[BasedToken] = field(default_factory=deque)

    def clone(self) -> "Place":
        cloned = Place(
            name=self.name,
            capacity=self.capacity,
            processing_time=self.processing_time,
            type=self.type,
        )
        cloned.tokens = deque(tok.clone() for tok in self.tokens)
        return cloned

    def head(self) -> BasedToken:
        return self.tokens[0]

    def pop_head(self) -> BasedToken:
        return self.tokens.popleft()

    def append(self, token: BasedToken) -> None:
        self.tokens.append(token)


@dataclass
class RobotSpec:
    tokens: int
    reach: Set[str]


@dataclass
class ModuleSpec:
    tokens: int = 0
    ptime: int = 0
    capacity: int = 1


@dataclass
class SharedGroup:
    name: str
    places: Set[str]
    cap: int = 2


class SuperPetriBuilder:
    def __init__(self, d_ptime: int = 5, default_ttime: int = 5):
        self.d_ptime = int(d_ptime)
        self.default_ttime = int(default_ttime)

    @staticmethod
    def _as_list(stage: Stage) -> List[str]:
        return stage if isinstance(stage, list) else [stage]

    @classmethod
    def expand_route_to_edges(cls, route: List[Stage]) -> Set[Tuple[str, str]]:
        edges: Set[Tuple[str, str]] = set()
        for i in range(len(route) - 1):
            left = cls._as_list(route[i])
            right = cls._as_list(route[i + 1])
            for src in left:
                for dst in right:
                    edges.add((src, dst))
        return edges

    @staticmethod
    def pick_robot_for_edge(src: str, dst: str, robots: Dict[str, RobotSpec]) -> str:
        candidates = [name for name, spec in robots.items() if src in spec.reach and dst in spec.reach]
        if len(candidates) != 1:
            raise ValueError(f"Edge {src}->{dst} robot ambiguous/none, candidates={candidates}")
        return candidates[0]

    def build(
        self,
        modules: Dict[str, ModuleSpec],
        robots: Dict[str, RobotSpec],
        routes: List[List[Stage]],
        shared_groups: Optional[List[SharedGroup]] = None,
        edge_weight: int = 1,
    ) -> Dict[str, object]:
        del shared_groups
        edge_weight = int(edge_weight)

        # name -> (capacity, ptime, type, tokens)
        # type: 1 process, 2 transport, 3 idle/source-sink, 4 robot resource
        place_specs: Dict[str, Tuple[int, int, int, List[BasedToken]]] = {}
        for name, spec in modules.items():
            ptype = 3 if name.startswith("LP") else 1
            place_specs[name] = (int(spec.capacity), int(spec.ptime), ptype, [])

        for robot_name, spec in robots.items():
            robot_tokens = [BasedToken(enter_time=0) for _ in range(int(spec.tokens))]
            place_specs[robot_name] = (int(spec.tokens), 0, 4, robot_tokens)

        all_edges: Set[Tuple[str, str]] = set()
        for route in routes:
            all_edges |= self.expand_route_to_edges(route)

        u_transitions: Dict[Tuple[str, str], str] = {}
        t_transitions: Dict[str, str] = {}
        arc_pre: List[Tuple[str, str, int]] = []
        arc_post: List[Tuple[str, str, int]] = []

        for src, dst in sorted(all_edges):
            robot_name = self.pick_robot_for_edge(src, dst, robots)
            u_name = f"u_{src}_{dst}"
            t_name = f"t_{dst}"
            d_name = f"d_{dst}"
            if d_name not in place_specs:
                place_specs[d_name] = (1, self.d_ptime, 2, [])

            u_transitions[(src, dst)] = u_name
            t_transitions[dst] = t_name

            # src + robot -> u -> d ; d -> t -> dst + robot
            arc_pre.append((src, u_name, edge_weight))
            arc_pre.append((robot_name, u_name, edge_weight))
            arc_post.append((u_name, d_name, edge_weight))
            arc_pre.append((d_name, t_name, edge_weight))
            arc_post.append((t_name, dst, edge_weight))
            arc_post.append((t_name, robot_name, edge_weight))

        # Initialize LP tokens with route_type and step.
        route_lp_map: Dict[str, int] = {}
        for route_type, route in enumerate(routes, start=1):
            first_stage = self._as_list(route[0])
            for lp_name in first_stage:
                if lp_name.startswith("LP") and lp_name != "LP_done":
                    route_lp_map[lp_name] = route_type

        next_token_id = 0
        for lp_name, route_type in route_lp_map.items():
            cap, ptime, ptype, _ = place_specs[lp_name]
            tok_cnt = int(modules[lp_name].tokens)
            lp_tokens = [
                BasedToken(
                    enter_time=0,
                    token_id=next_token_id + i,
                    route_type=route_type,
                    step=0,
                )
                for i in range(tok_cnt)
            ]
            next_token_id += tok_cnt
            place_specs[lp_name] = (cap, ptime, ptype, lp_tokens)

        id2p_name = list(place_specs.keys())
        id2t_name = sorted(set(u_transitions.values()) | set(t_transitions.values()))
        p_idx = {name: i for i, name in enumerate(id2p_name)}
        t_idx = {name: i for i, name in enumerate(id2t_name)}

        P, T = len(id2p_name), len(id2t_name)
        pre = np.zeros((P, T), dtype=int)
        pst = np.zeros((P, T), dtype=int)

        for src, t_name, w in arc_pre:
            pre[p_idx[src], t_idx[t_name]] += int(w)
        for t_name, dst, w in arc_post:
            pst[p_idx[dst], t_idx[t_name]] += int(w)

        marks: List[Place] = []
        m0 = np.zeros(P, dtype=int)
        ptime = np.zeros(P, dtype=int)
        capacity = np.zeros(P, dtype=int)

        for name in id2p_name:
            cap, proc_time, ptype, tokens = place_specs[name]
            place = Place(name=name, capacity=cap, processing_time=proc_time, type=ptype)
            for tok in tokens:
                place.append(tok)
            marks.append(place)
            i = p_idx[name]
            m0[i] = len(tokens)
            ptime[i] = int(proc_time)
            capacity[i] = int(cap)

        md = m0.copy()
        total_wafers = int(
            sum(int(modules[name].tokens) for name in modules if name.startswith("LP") and name != "LP_done")
        )
        if "LP_done" in p_idx:
            md[p_idx["LP_done"]] = total_wafers
        for name in modules:
            if name.startswith("LP") and name != "LP_done":
                md[p_idx[name]] = 0

        idle_idx: Dict[str, int] = {}
        if "LP1" in p_idx:
            idle_idx["start1"] = p_idx["LP1"]
        if "LP2" in p_idx:
            idle_idx["start2"] = p_idx["LP2"]
        if "LP" in p_idx:
            idle_idx["start"] = p_idx["LP"]
        if "LP_done" in p_idx:
            idle_idx["end"] = p_idx["LP_done"]

        return {
            "m0": m0,
            "md": md,
            "pre": pre,
            "pst": pst,
            "ptime": ptime,
            "capacity": capacity,
            "id2p_name": id2p_name,
            "id2t_name": id2t_name,
            "idle_idx": idle_idx,
            "marks": marks,
        }
