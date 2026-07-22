#!/usr/bin/env python3
"""Reset a task state stage in DynamoDB (dry-run by default)."""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import boto3
from botocore.exceptions import ClientError

STANDARD_PHASE_ORDER = [
    "setup",
    "ready",
    "answer",
    "challenge",
    "check",
    "cleanup",
]
PHASE_RANK = {phase: idx for idx, phase in enumerate(STANDARD_PHASE_ORDER)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset current phase for a task state in TaskStateTable."
    )
    parser.add_argument("--stack-name", default="k8s-grader-api-dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--email", required=True)
    parser.add_argument("--game", required=True)
    parser.add_argument("--task", required=True, help="Task ID, e.g. 087_kustomize_configuration")
    parser.add_argument("--phase-id", required=True, help="Target phase ID, e.g. setup/ready/challenge/check")
    parser.add_argument(
        "--clear-all-phases",
        action="store_true",
        help="Drop all existing phase_states and reset total_points to 0",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def get_stack_output(stack_name: str, region: str, key: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == key:
            return output["OutputValue"]
    raise ValueError(f"CloudFormation output not found: {key}")


def load_state_item(table_name: str, region: str, email: str, game: str, task: str) -> Dict[str, Any]:
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    response = table.get_item(Key={"email": email, "gameTask": f"{game}#{task}"})
    item = response.get("Item")
    if not item:
        raise ValueError(f"Task state not found for {email} {game}#{task}")
    return item


def _should_drop_phase(existing_phase: str, target_phase: str) -> bool:
    if existing_phase == target_phase:
        return True
    if existing_phase in PHASE_RANK and target_phase in PHASE_RANK:
        return PHASE_RANK[existing_phase] >= PHASE_RANK[target_phase]
    return False


def reset_state_item(
    item: Dict[str, Any], target_phase: str, clear_all_phases: bool = False
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    before = deepcopy(item)
    phase_states = item.get("phase_states", {}) or {}

    if clear_all_phases:
        new_phase_states: Dict[str, Any] = {}
    else:
        new_phase_states = {
            phase_id: state
            for phase_id, state in phase_states.items()
            if not _should_drop_phase(phase_id, target_phase)
        }

    total_points = 0
    for state in new_phase_states.values():
        if state.get("status") == "passed":
            total_points += int(state.get("points_earned", 0) or 0)

    now = datetime.now(timezone.utc).isoformat()
    item["phase_states"] = new_phase_states
    item["current_phase_id"] = target_phase
    item["status"] = "in_progress"
    item["completed_at"] = None
    item["updated_at"] = now
    item["total_points"] = total_points

    summary = {
        "old_status": before.get("status"),
        "new_status": item.get("status"),
        "old_current_phase": before.get("current_phase_id"),
        "new_current_phase": item.get("current_phase_id"),
        "old_phase_count": len(phase_states),
        "new_phase_count": len(new_phase_states),
        "old_total_points": before.get("total_points", 0),
        "new_total_points": item.get("total_points", 0),
        "cleared_all_phases": clear_all_phases,
    }
    return item, summary


def save_state_item(table_name: str, region: str, item: Dict[str, Any]) -> None:
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    table.put_item(Item=item)


def main() -> int:
    args = parse_args()
    try:
        table_name = get_stack_output(args.stack_name, args.region, "TaskStateTable")
        item = load_state_item(table_name, args.region, args.email, args.game, args.task)
        updated, summary = reset_state_item(
            item=item,
            target_phase=args.phase_id,
            clear_all_phases=args.clear_all_phases,
        )
    except (ValueError, ClientError) as exc:
        print(f"Reset failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "table": table_name,
        "email": args.email,
        "game": args.game,
        "task": args.task,
        "target_phase": args.phase_id,
        "summary": summary,
    }
    print(json.dumps(payload, indent=2))

    if not args.apply:
        return 0

    try:
        save_state_item(table_name, args.region, updated)
    except ClientError as exc:
        print(f"Apply failed: {exc}", file=sys.stderr)
        return 1

    print("Task stage reset applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
