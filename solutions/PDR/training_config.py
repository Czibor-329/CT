"""PPO训练配置类"""
from dataclasses import dataclass, fields
import json
from pathlib import Path


@dataclass
class TrainingConfig:
    # 网络结构参数
    n_hidden: int = 128
    n_layer: int = 3
    
    # 训练批次参数
    frames_per_batch: int = 320
    batch: int = 20
    total_batch: int = 20
    sub_batch_size: int = 64
    num_epochs: int = 5
    num_envs: int = 5
    
    # PPO算法参数
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    lr: float = 1e-4
    
    # 熵系数参数
    entropy_start: float = 0.02
    entropy_end: float = 0.01

    # 损失与优化
    critic_coeff: float = 0.5
    grad_clip_norm: float = 1.0
    
    # 设备和随机种子
    device: str = "cpu"
    seed: int = 42

    @classmethod
    def load(cls, filepath: str | None = None) -> "TrainingConfig":
        """从JSON文件加载配置；未指定路径时读取默认配置。"""
        config_path = (
            Path(filepath)
            if filepath is not None
            else Path(__file__).with_name("training_config_default.json")
        )
        with config_path.open("r", encoding="utf-8") as f:
            config_dict = json.load(f)

        valid_keys = {item.name for item in fields(cls)}
        filtered = {k: v for k, v in config_dict.items() if k in valid_keys}
        cfg = cls(**filtered)
        if cfg.n_hidden <= 0:
            raise ValueError("n_hidden must be positive")
        if cfg.n_layer <= 0:
            raise ValueError("n_layer must be positive")
        if cfg.total_batch <= 0:
            raise ValueError("total_batch must be positive")
        if cfg.frames_per_batch <= 0:
            raise ValueError("frames_per_batch must be positive")
        if cfg.sub_batch_size <= 0:
            raise ValueError("sub_batch_size must be positive")
        if cfg.num_epochs <= 0:
            raise ValueError("num_epochs must be positive")
        if cfg.num_envs <= 0:
            raise ValueError("num_envs must be positive")
        return cfg
