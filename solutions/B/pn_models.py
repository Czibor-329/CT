from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np


@dataclass
class Place:
    name: str
    capacity: int
    processing_time: int
    type: int
    tokens: List[Any] = field(default_factory=list)

    def append(self, token: Any) -> None:
        self.tokens.append(token)

    def pop_head(self) -> Any:
        if not self.tokens:
            raise IndexError(f"Place {self.name} has no tokens")
        return self.tokens.pop(0)

    def head(self) -> Any:
        if not self.tokens:
            raise IndexError(f"Place {self.name} has no tokens")
        return self.tokens[0]

    def clone(self) -> "Place":
        cloned = Place(
            name=self.name,
            capacity=self.capacity,
            processing_time=self.processing_time,
            type=self.type,
        )
        for token in self.tokens:
            if hasattr(token, "clone"):
                cloned.append(token.clone())
            else:
                cloned.append(token)
        return cloned

    def __len__(self) -> int:
        return len(self.tokens)


@dataclass(slots=True)
class FlatMarks:
    token_place: np.ndarray        # int32[N_wafer], tid -> place_id (-1 = in-transit)
    token_enter_time: np.ndarray   # int32[N_wafer], tid -> enter_time
    place_token: np.ndarray        # int32[P], pid -> tid (-1 if empty / non-cap1-wafer)
    wafer_queues: Dict[int, List[int]]     # multi-cap wafer pid -> [tid, ...] FIFO
    resource_queues: Dict[int, List[int]]  # resource pid -> [enter_time, ...] FIFO

    def clone(self) -> FlatMarks:
        return FlatMarks(
            token_place=self.token_place.copy(),
            token_enter_time=self.token_enter_time.copy(),
            place_token=self.place_token.copy(),
            wafer_queues={k: list(v) for k, v in self.wafer_queues.items()},
            resource_queues={k: list(v) for k, v in self.resource_queues.items()},
        )
