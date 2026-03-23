from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Dict

import numpy as np
import torch
import torch.nn as nn
from tensordict import TensorDict
from tensordict.nn import TensorDictModule
from torch.optim import Adam
from torchrl.collectors import SyncDataCollector
from torchrl.data import Binary, Categorical, Composite, Unbounded
from torchrl.data.replay_buffers import ReplayBuffer
from torchrl.data.replay_buffers.samplers import SamplerWithoutReplacement
from torchrl.data.replay_buffers.storages import LazyTensorStorage
from torchrl.envs import EnvBase
from torchrl.envs.utils import ExplorationType, set_exploration_type
from torchrl.modules import MaskedCategorical, ProbabilisticActor, ValueOperator
from torchrl.objectives import ClipPPOLoss
from torchrl.objectives.value import GAE

from solutions.PDR.net import Petri
from solutions.PPO.network.models import MaskedPolicyHead

TRAIN_DEVICE = "cpu"
N_WAFER = 7
TTIME = 5
SEARCH_DEPTH = 5
CANDIDATE_K = 8
SCRAP_PENALTY = -1000.0
FINISH_BONUS = 1000.0

SEED = 42
N_HIDDEN = 128
N_LAYER = 2
LR = 3e-4
FRAMES_PER_BATCH = 256
TOTAL_BATCH = 200
NUM_EPOCHS = 4
SUB_BATCH_SIZE = 64
GAMMA = 0.99
GAE_LAMBDA = 0.95
CLIP_EPS = 0.2
ENTROPY_START = 0.02
ENTROPY_END = 0.001


class EnvPDR(EnvBase):
    metadata = {"render.modes": ["human", "rgb_array"], "reder_fps": 30}
    batch_locked = False

    def __init__(
        self,
        device: str = "cpu",
        seed: int | None = None,
        n_wafer: int = N_WAFER,
        ttime: int = TTIME,
        search_depth: int = SEARCH_DEPTH,
        candidate_k: int = CANDIDATE_K,
        finish_bonus: float = FINISH_BONUS,
        scrap_penalty: float = SCRAP_PENALTY,
    ) -> None:
        super().__init__(device=device)
        self.net = Petri(n_wafer=n_wafer, ttime=ttime)
        self.net.search_depth = int(search_depth)
        self.candidate_k = int(candidate_k)
        self.n_actions = int(candidate_k)
        self.finish_bonus = float(finish_bonus)
        self.scrap_penalty = float(scrap_penalty)
        self._out_time = torch.zeros(1, dtype=torch.int64)
        self._out_reward = torch.zeros(1, dtype=torch.float32)
        self._make_spec()
        if seed is None:
            seed = torch.empty((), dtype=torch.int64).random_().item()
        self.set_seed(int(seed))

    def _make_spec(self) -> None:
        obs_dim = int(self.net.P)
        self.observation_spec = Composite(
            observation_f=Unbounded(shape=(obs_dim,), dtype=torch.float32, device=self.device),
            action_mask=Binary(n=self.n_actions, dtype=torch.bool),
            time=Unbounded(shape=(1,), dtype=torch.int64, device=self.device),
            shape=(),
        )
        self.action_spec = Categorical(n=self.n_actions, shape=(1,), dtype=torch.int64)
        self.reward_spec = Unbounded(shape=(1,), dtype=torch.float32)
        self.state_spec = Composite(shape=())
        self.done_spec = Composite(
            terminated=Unbounded(shape=(1,), dtype=torch.bool),
            finish=Unbounded(shape=(1,), dtype=torch.bool),
            scrap=Unbounded(shape=(1,), dtype=torch.bool),
        )

    def _sanitize_mask(self, action_mask: np.ndarray) -> np.ndarray:
        mask = np.asarray(action_mask, dtype=bool).copy()
        if mask.size != self.candidate_k:
            out = np.zeros(self.candidate_k, dtype=bool)
            out[: min(mask.size, self.candidate_k)] = mask[: min(mask.size, self.candidate_k)]
            mask = out
        if not mask.any():
            mask[0] = True
        return mask

    def _build_state_td(self, obs: np.ndarray, action_mask: np.ndarray, time_v: int) -> TensorDict:
        self._out_time[0] = int(time_v)
        return TensorDict(
            {
                "observation_f": torch.as_tensor(obs, dtype=torch.float32),
                "action_mask": torch.as_tensor(action_mask, dtype=torch.bool),
                "time": self._out_time.clone(),
            },
            batch_size=[],
        )

    def _reset(self, td_params: TensorDict | None = None) -> TensorDict:
        self.net.reset()
        obs = self.net.reset_train_state()
        prepared = self.net.prepare_train_candidates(candidate_k=self.candidate_k)
        return self._build_state_td(
            obs=obs,
            action_mask=self._sanitize_mask(np.asarray(prepared["action_mask"], dtype=bool)),
            time_v=int(self.net.train_current_clock),
        )

    def _step(self, tensordict: TensorDict | None = None) -> TensorDict:
        action_idx = int(tensordict["action"].item())
        prepared = self.net.prepare_train_candidates(candidate_k=self.candidate_k)
        obs, base_reward, done, info = self.net.train_step(
            action_idx=action_idx,
            candidate_k=self.candidate_k,
            scrap_penalty=0.0,
            prepared=prepared,
        )
        finish = bool(info["finish"])
        scrap = bool(info["scrap"])
        reward = float(base_reward)
        if finish:
            reward += self.finish_bonus
        if scrap:
            reward += self.scrap_penalty

        if done:
            next_mask = np.zeros(self.candidate_k, dtype=bool)
            next_mask[0] = True
        else:
            next_prepared = self.net.prepare_train_candidates(candidate_k=self.candidate_k)
            next_mask = self._sanitize_mask(np.asarray(next_prepared["action_mask"], dtype=bool))

        self._out_time[0] = int(info["time"])
        self._out_reward[0] = float(reward)
        out = TensorDict(
            {
                "observation_f": torch.as_tensor(obs, dtype=torch.float32),
                "action_mask": torch.as_tensor(next_mask, dtype=torch.bool),
                "time": self._out_time.clone(),
                "finish": torch.tensor(finish, dtype=torch.bool),
                "scrap": torch.tensor(scrap, dtype=torch.bool),
                "reward": self._out_reward.clone(),
                "terminated": torch.tensor(bool(done), dtype=torch.bool),
            },
            batch_size=[],
        )
        return out

    def _set_seed(self, seed: int | None) -> None:
        self.rng = torch.manual_seed(seed)


def train() -> tuple[Dict[str, list], ProbabilisticActor]:
    torch.manual_seed(SEED)
    env = EnvPDR(
        device="cpu",
        seed=SEED,
        n_wafer=N_WAFER,
        ttime=TTIME,
        search_depth=SEARCH_DEPTH,
        candidate_k=CANDIDATE_K,
        finish_bonus=FINISH_BONUS,
        scrap_penalty=SCRAP_PENALTY,
    )

    saved_models_dir = os.path.join(os.path.dirname(__file__), "saved_models")
    os.makedirs(saved_models_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(saved_models_dir, f"pdr_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)
    best_model_path = os.path.join(saved_models_dir, "CT_pdr_best.pt")
    latest_model_path = os.path.join(saved_models_dir, "CT_pdr_latest.pt")

    obs_dim = int(env.observation_spec["observation_f"].shape[0])
    n_actions = int(env.action_spec.space.n)
    policy_backbone = MaskedPolicyHead(
        hidden=N_HIDDEN,
        n_obs=obs_dim,
        n_actions=n_actions,
        n_layers=N_LAYER,
    )
    td_module = TensorDictModule(policy_backbone, in_keys=["observation_f"], out_keys=["logits"])
    policy = ProbabilisticActor(
        module=td_module,
        in_keys={"logits": "logits", "mask": "action_mask"},
        out_keys=["action"],
        distribution_class=MaskedCategorical,
        return_log_prob=True,
    ).to(TRAIN_DEVICE)
    value_module = ValueOperator(
        module=nn.Sequential(
            nn.Linear(obs_dim, N_HIDDEN),
            nn.ReLU(),
            nn.Linear(N_HIDDEN, N_HIDDEN),
            nn.ReLU(),
            nn.Linear(N_HIDDEN, N_HIDDEN),
            nn.ReLU(),
            nn.Linear(N_HIDDEN, 1),
        ),
        in_keys=["observation_f"],
    ).to(TRAIN_DEVICE)
    optim = Adam(list(policy.parameters()) + list(value_module.parameters()), lr=LR)

    collector = SyncDataCollector(
        env,
        policy,
        frames_per_batch=FRAMES_PER_BATCH,
        total_frames=FRAMES_PER_BATCH * TOTAL_BATCH,
        device=TRAIN_DEVICE,
    )
    replay_buffer = ReplayBuffer(
        storage=LazyTensorStorage(max_size=FRAMES_PER_BATCH),
        sampler=SamplerWithoutReplacement(),
    )
    gae = GAE(gamma=GAMMA, lmbda=GAE_LAMBDA, value_network=value_module)
    loss_module = ClipPPOLoss(
        actor=policy,
        critic=value_module,
        clip_epsilon=CLIP_EPS,
        entropy_coeff=ENTROPY_START,
        critic_coeff=0.5,
        normalize_advantage=True,
    )

    frame_count = 0
    best_reward = float("-inf")
    log = defaultdict(list)
    with set_exploration_type(ExplorationType.RANDOM):
        for batch_idx, tensordict_data in enumerate(collector):
            frac = min(1.0, batch_idx / max(1, TOTAL_BATCH))
            entropy_coeff = ENTROPY_START + (ENTROPY_END - ENTROPY_START) * frac
            loss_module.entropy_coeff.copy_(
                torch.tensor(
                    entropy_coeff,
                    device=loss_module.entropy_coeff.device,
                    dtype=loss_module.entropy_coeff.dtype,
                )
            )

            gae_vals = gae(tensordict_data)
            tensordict_data.set("advantage", gae_vals.get("advantage"))
            tensordict_data.set("value_target", gae_vals.get("value_target"))
            replay_buffer.extend(tensordict_data)

            for _ in range(NUM_EPOCHS):
                for _ in range(FRAMES_PER_BATCH // SUB_BATCH_SIZE):
                    subdata = replay_buffer.sample(SUB_BATCH_SIZE).to(TRAIN_DEVICE)
                    loss_vals = loss_module(subdata)
                    loss = (
                        loss_vals["loss_objective"]
                        + loss_vals["loss_critic"]
                        + loss_vals["loss_entropy"]
                    )
                    optim.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(
                        list(policy.parameters()) + list(value_module.parameters()),
                        max_norm=1.0,
                    )
                    optim.step()

            frame_count += int(tensordict_data.numel())
            batch_reward = float(tensordict_data["next", "reward"].sum().item())
            finish_mask = tensordict_data["next", "finish"]
            scrap_mask = tensordict_data["next", "scrap"]
            finish_count = int(finish_mask.sum().item())
            scrap_count = int(scrap_mask.sum().item())
            finished_times = tensordict_data["next", "time"][finish_mask]
            mean_makespan = (
                float(finished_times.float().mean().item())
                if finish_count > 0
                else 0.0
            )

            print(
                f"batch {batch_idx + 1:04d} | frames={frame_count} | "
                f"sum_reward={batch_reward:.2f} | finish={finish_count} | "
                f"scrap={scrap_count} | makespan={mean_makespan:.2f}",
                flush=True,
            )
            log["reward"].append(batch_reward)
            log["finish"].append(finish_count)
            log["scrap"].append(scrap_count)
            log["makespan"].append(mean_makespan)

            if batch_reward > best_reward and finish_count > 0:
                best_reward = batch_reward
                torch.save(policy.state_dict(), best_model_path)
                torch.save(policy.state_dict(), os.path.join(backup_dir, "CT_pdr_best.pt"))
                print(f"  -> New best model saved! reward={batch_reward:.2f}", flush=True)

    torch.save(policy.state_dict(), os.path.join(backup_dir, "CT_pdr_final.pt"))
    torch.save(policy.state_dict(), latest_model_path)
    print(f"Training done. Best reward: {best_reward:.2f}", flush=True)
    print(f"Best model: {best_model_path}", flush=True)
    print(f"Latest model: {latest_model_path}", flush=True)
    print(f"Backup folder: {backup_dir}", flush=True)
    return log, policy


if __name__ == "__main__":
    train()


