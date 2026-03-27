from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from results.paths import action_sequence_path, safe_name


def _normalize_transition_name(action_name: str) -> str:
    """
    把按分支拆分的 u 变迁归一为基础动作名。
    例如：u_LP_TM2_1 / u_LP_TM2_2 -> u_LP_TM2
    """
    m = re.match(r"^(u_[^_]+_[^_]+)_\d+$", action_name)
    if m:
        return str(m.group(1))
    return action_name


def build_single_replay_payload(full_transition_records: list[dict[str, Any]]) -> dict[str, Any]:
    sequence: list[dict[str, Any]] = []
    step = 1
    prev_fire_time: int | None = None

    for item in full_transition_records:
        action_name = _normalize_transition_name(str(item["transition"]))
        fire_time = int(item["fire_time"])

        if prev_fire_time is None:
            sequence.append(
                {
                    "step": step,
                    "time": fire_time,
                    "action": action_name,
                    "actions": [action_name,"WAIT"],
                }
            )
            prev_fire_time = fire_time
            step += 1
            continue

        delta = fire_time - prev_fire_time
        wait_count = (delta - 1) // 5 if delta > 5 else 0
        wait_time = prev_fire_time
        for _ in range(wait_count):
            wait_time += 5
            sequence.append(
                {
                    "step": step,
                    "time": wait_time,
                    "action": "WAIT_5s",
                    "actions": ["WAIT_5s","WAIT"],
                }
            )
            step += 1

        sequence.append(
            {
                "step": step,
                "time": fire_time,
                "action": action_name,
                "actions": [action_name,"WAIT"],
            }
        )
        prev_fire_time = fire_time
        step += 1

    return {
        "schema_version": 2,
        "device_mode": "single",
        "sequence": sequence,
    }


def export_single_replay_payload(
    full_transition_records: list[dict[str, Any]],
    out_name: str = "pdr_sequence",
) -> Path:
    payload = build_single_replay_payload(full_transition_records)
    out_path = action_sequence_path(safe_name(str(out_name), "pdr_sequence"))
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def _load_records_from_json(records_json_path: Path) -> list[dict[str, Any]]:
    with records_json_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        return list(raw.get("full_transition_records", []))
    return list(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="将 PDR full_transition_records 转为 UI 可回放序列")
    parser.add_argument("--records-json", type=Path, required=True, help="输入 records JSON 文件路径")
    parser.add_argument("--out-name", type=str, default="pdr_sequence", help="输出到 results/action_sequences/<out_name>.json")
    args = parser.parse_args()

    records = _load_records_from_json(args.records_json)
    out_path = export_single_replay_payload(records, out_name=args.out_name)
    print(f"[INFO] replay sequence exported: {out_path}")


if __name__ == "__main__":
    main()
