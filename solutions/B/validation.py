from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch
from tensordict import TensorDict
from torchrl.envs.utils import ExplorationType, set_exploration_type

from .clustertool_config import ClusterToolCfg
from .training_config import TrainingConfig
from .Env import Env
from .parse_sequences import export_single_replay_payload
from .train import build_policy_actor
from results.paths import model_output_path


EVAL_RUNS = 5
DEFAULT_OUT_NAME = "ppo_best_sequence"


def _select_action(
    policy,
    observation_f: torch.Tensor,
    action_mask: torch.Tensor,
) -> int:
    in_td = TensorDict(
        {
            "observation_f": observation_f,
            "action_mask": action_mask,
        },
        batch_size=[],
    )
    with torch.no_grad(), set_exploration_type(ExplorationType.MODE):
        out_td = policy(in_td)
    return int(out_td.get("action").item())


def _run_single_eval(policy, device: str, clustertool_cfg: ClusterToolCfg, seed: int) -> dict[str, Any]:
    env = Env(
        device=device,
        seed=seed,
        clustertool_cfg=clustertool_cfg,
    )
    td = env.reset()
    net = env.net
    run_records: list[dict[str, Any]] = []
    makespan = 0
    finish = False
    scrap = False

    while True:
        prepared = net._train_cached_candidates
        if prepared is None:
            prepared = net.prepare_train_candidates()

        has_candidate = bool(prepared["has_candidate"])
        if has_candidate:
            action_idx = _select_action(
                policy=policy,
                observation_f=td.get("observation_f").to(device),
                action_mask=td.get("action_mask").to(device),
            )
            valid_count = int(prepared["valid_count"])
            action_idx = max(0, min(action_idx, valid_count - 1))
            selected_state = prepared["candidate_states"][action_idx]
            run_records.extend(
                [dict(item) for item in selected_state.get("transition_records", [])]
            )
        else:
            action_idx = 0

        step_in = TensorDict(
            {"action": torch.tensor(action_idx, dtype=torch.int64)},
            batch_size=[],
        )
        stepped = env.step(step_in)
        next_td = stepped.get("next")
        makespan = int(next_td.get("time").item())
        finish = bool(next_td.get("finish").item())
        scrap = bool(next_td.get("scrap").item())
        done = bool(next_td.get("done").item())
        if done:
            break
        td = next_td.select("observation_f", "action_mask", "time").clone()

    env.close()
    return {
        "makespan": makespan,
        "finish": finish,
        "scrap": scrap,
        "records": run_records,
    }


def evaluate_model(model_path: str) -> dict[str, Any]:
    training_cfg = TrainingConfig.load()
    clustertool_cfg = ClusterToolCfg.load()
    device = training_cfg.device

    probe_env = Env(
        device=device,
        seed=training_cfg.seed,
        clustertool_cfg=clustertool_cfg,
    )
    obs_dim = int(probe_env.observation_spec["observation_f"].shape[-1])
    n_actions = int(probe_env.action_spec.space.n)
    probe_env.close()

    policy = build_policy_actor(
        obs_dim=obs_dim,
        n_actions=n_actions,
        n_hidden=training_cfg.n_hidden,
        n_layer=training_cfg.n_layer,
        device=device,
    )

    state_dict = torch.load(model_path, map_location=device)
    policy.load_state_dict(state_dict)
    policy.eval()

    results: list[dict[str, Any]] = []
    for run_idx in range(EVAL_RUNS):
        run_result = _run_single_eval(
            policy=policy,
            device=device,
            clustertool_cfg=clustertool_cfg,
            seed=int(training_cfg.seed) + run_idx,
        )
        run_result["run_idx"] = run_idx + 1
        results.append(run_result)
        print(
            f"[eval] run={run_idx + 1}/{EVAL_RUNS} | "
            f"finish={run_result['finish']} | scrap={run_result['scrap']} | "
            f"makespan={run_result['makespan']} | records={len(run_result['records'])}"
        )

    finished = [item for item in results if bool(item["finish"])]
    pool = finished if len(finished) > 0 else results
    best = min(pool, key=lambda x: int(x["makespan"]))
    out_path = export_single_replay_payload(
        full_transition_records=list(best["records"]),
        out_name=DEFAULT_OUT_NAME,
    )

    summary = {
        "model_path": str(model_path),
        "best_run_idx": int(best["run_idx"]),
        "best_makespan": int(best["makespan"]),
        "best_finish": bool(best["finish"]),
        "best_scrap": bool(best["scrap"]),
        "sequence_path": str(out_path),
        "runs": [
            {
                "run_idx": int(item["run_idx"]),
                "makespan": int(item["makespan"]),
                "finish": bool(item["finish"]),
                "scrap": bool(item["scrap"]),
                "records": int(len(item["records"])),
            }
            for item in results
        ],
    }
    print(
        f"[eval] best run={summary['best_run_idx']} | "
        f"makespan={summary['best_makespan']} | "
        f"sequence={summary['sequence_path']}"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="评估 PPO 模型并导出最优序列")
    parser.add_argument("--model-path", type=str, required=True, help="模型权重路径")
    args = parser.parse_args()

    model_path = model_output_path(args.model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"model file not found: {model_path}")
    evaluate_model(model_path=str(model_path))


if __name__ == "__main__":
    main()
