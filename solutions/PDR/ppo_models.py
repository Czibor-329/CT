from __future__ import annotations

import torch
import torch.nn as nn


class MaskedPolicyHead(nn.Module):
    def __init__(self, hidden: int, n_obs: int, n_actions: int, n_layers: int = 2) -> None:
        super().__init__()
        if n_layers < 1:
            raise ValueError("n_layers must be >= 1")

        layers: list[nn.Module] = []
        in_features = int(n_obs)
        for _ in range(int(n_layers)):
            layers.append(nn.Linear(in_features, int(hidden)))
            layers.append(nn.ReLU())
            in_features = int(hidden)
        layers.append(nn.Linear(in_features, int(n_actions)))
        self.network = nn.Sequential(*layers)

    def forward(self, observation_f: torch.Tensor) -> torch.Tensor:
        return self.network(observation_f)
