import argparse
import matplotlib.pyplot as plt
import numpy as np
import torch
from solutions.PPO.enviroment import Env_PN
from solutions.PPO.train import train
from torchrl.envs import (Compose, DTypeCastTransform, TransformedEnv, ActionMask)
import time
from data.ppo_configs.training_config import PPOTrainingConfig
import warnings
import os
import sys

warnings.filterwarnings(
    "ignore",
    message="size_average and reduce args will be deprecated*",
    category=UserWarning,
)


def create_env(device):
    """
    创建训练和评估环境

    Args:
        device: 计算设备

    Returns:
        (train_env, eval_env): 训练和评估环境
    """
    base_env1 = Env_PN(device=device)
    base_env2 = Env_PN(device=device)

    transform = Compose([
        ActionMask(),
        DTypeCastTransform(dtype_in=torch.int64, dtype_out=torch.float32,
                           in_keys="observation", out_keys="observation_f"),
    ])

    train_env = TransformedEnv(base_env1, transform)
    eval_env = TransformedEnv(base_env2, transform)

    return train_env, eval_env


def get_config_path(custom_config: str = None):
    """
    获取配置文件路径

    Args:
        custom_config: 自定义配置文件路径

    Returns:
        配置文件的绝对路径
    """
    if custom_config:
        if os.path.isabs(custom_config):
            return custom_config
        else:
            return os.path.abspath(custom_config)

    # 默认配置：phase2_config.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(script_dir, "..", "..")
    config_path = os.path.join(project_root, "data", "ppo_configs", "phase2_config.json")
    return os.path.abspath(config_path)


def train_single_phase(device, config_path: str = None, checkpoint_path: str = None):
    """
    执行 PPO 训练

    Args:
        device: 计算设备
        config_path: 配置文件路径（可选）
        checkpoint_path: checkpoint 文件路径（可选）

    Returns:
        (log, policy): 训练日志和策略网络
    """
    print("\n" + "=" * 60)
    print("[PPO 训练] 开始")
    print("  训练目标: 完整奖励（加工腔室超时 + 运输位超时）")
    print("=" * 60)

    # 创建环境
    train_env, eval_env = create_env(device)

    # 加载配置
    config_file = get_config_path(config_path)
    if not os.path.exists(config_file):
        print(f"错误: 配置文件不存在: {config_file}")
        sys.exit(1)
    
    print(f"加载配置: {config_file}")
    config = PPOTrainingConfig.load(config_file)
    config.device = str(device)  # 更新设备

    # 加载checkpoint（如果提供）
    if checkpoint_path:
        if not os.path.exists(checkpoint_path):
            print(f"警告: checkpoint文件不存在: {checkpoint_path}")
            checkpoint_path = None
        else:
            print(f"加载checkpoint: {checkpoint_path}")

    # 开始训练
    start_time = time.time()
    log, policy = train(train_env, eval_env, config=config, checkpoint_path=checkpoint_path)
    elapsed_time = time.time() - start_time
    
    print(f"\n训练完成! 用时: {elapsed_time:.2f}s")
    
    return log, policy


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="PPO 训练工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用默认配置 (phase2_config.json) 训练
  python run_ppo.py

  # 使用自定义配置
  python run_ppo.py --config data/ppo_configs/custom/my_config.json

  # 从 checkpoint 继续训练
  python run_ppo.py --checkpoint solutions/PPO/saved_models/CT_phase2_best.pt
        """
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="自定义配置文件路径（可选）。如果不指定，使用 data/ppo_configs/phase2_config.json"
    )
    
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="checkpoint文件路径（可选），用于继续训练或迁移学习"
    )
    
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cpu", "cuda"],
        help="计算设备: cpu 或 cuda。默认: 自动检测"
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 设置环境变量
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    
    # 确定计算设备
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    print("=" * 60)
    print("PPO训练工具")
    print(f"计算设备: {device}")
    print("=" * 60)
    
    # 执行训练
    train_single_phase(
        device=device,
        config_path=args.config,
        checkpoint_path=args.checkpoint
    )


if __name__ == "__main__":
    main()
