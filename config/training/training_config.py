"""PPO 训练配置：Pydantic 模型，支持 YAML / JSON 文件。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, computed_field


class PPOTrainingConfig(BaseModel):
    """PPO 训练配置参数。"""

    model_config = ConfigDict(extra="ignore")

    n_hidden: int = 128
    n_layer: int = 4

    total_batch: int = 150
    sub_batch_size: int = 64
    num_epochs: int = 10

    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    lr: float = 1e-4

    entropy_start: float = 0.02
    entropy_end: float = 0.01

    device: str = "cpu"
    seed: int = 42

    @computed_field
    @property
    def frames_per_batch(self) -> int:
        return self.sub_batch_size * self.num_epochs

    def save(self, filepath: str) -> None:
        path = Path(filepath)
        os.makedirs(path.parent, exist_ok=True)
        payload: dict[str, Any] = self.model_dump(mode="json", exclude={"frames_per_batch"})
        with open(path, "w", encoding="utf-8") as f:
            if path.suffix.lower() in (".yaml", ".yml"):
                yaml.safe_dump(
                    payload,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )
            else:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"配置已保存到: {filepath}")

    @classmethod
    def load(cls, filepath: str) -> "PPOTrainingConfig":
        path = Path(filepath)
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix.lower() in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"配置文件顶层必须是映射: {path}")
        return cls.model_validate(data)

    def __str__(self) -> str:
        lines = ["=" * 50, "PPO训练配置:"]
        lines.append(f"  网络: hidden={self.n_hidden}, layers={self.n_layer}")
        lines.append(f"  批次: total={self.total_batch}, sub_batch={self.sub_batch_size}, epochs={self.num_epochs}")
        lines.append(f"  PPO: gamma={self.gamma}, lambda={self.gae_lambda}, clip={self.clip_epsilon}, lr={self.lr}")
        lines.append(f"  熵系数: {self.entropy_start} -> {self.entropy_end}")
        lines.append(f"  设备: {self.device}, 种子: {self.seed}")
        lines.append("=" * 50)
        return "\n".join(lines)