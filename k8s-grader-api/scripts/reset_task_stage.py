#!/usr/bin/env python3
"""Reset a task state stage in DynamoDB (dry-run by default)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
COMMON_LAYER_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "common-layer")
if COMMON_LAYER_DIR not in sys.path:
    sys.path.insert(0, COMMON_LAYER_DIR)

STANDARD_PHASE_ORDER = [
    "setup",
    "ready",
    "answer",
    "challenge",
    "check",
    "cleanup",
]
PHASE_RANK = {phase: idx for idx, phase in enumerate(STANDARD_PHASE_ORDER)}


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset current phase for a task state in TaskStateTable."
    )
    parser.add_argument("--stack-name", default="k8s-grader-api-dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--email", required=True)
    parser.add_argument("--game", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--task", help="Task ID, e.g. 087_kustomize_configuration")
    target.add_argument(
        "--all-tasks",
        action="store_true",
        help="Reset all saved task states for the specified game",
    )
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


def load_state_items(table_name: str, region: str, email: str, game: str) -> List[Dict[str, Any]]:
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    items: List[Dict[str, Any]] = []
    query_kwargs: Dict[str, Any] = {
        "KeyConditionExpression": Key("email").eq(email) & Key("gameTask").begins_with(f"{game}#"),
    }

    while True:
        response = table.query(**query_kwargs)
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
        query_kwargs["ExclusiveStartKey"] = last_evaluated_key

    return items


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


def regenerate_session_data(
    item: Dict[str, Any],
    stack_name: str,
    region: str,
) -> Dict[str, Any]:
    from common.models.task_manifest import TaskManifest

    game = str(item["game"])
    task_id = get_task_id(item, game)
    email = str(item["email"])
    exam_code = item.get("exam_code")

    os.environ["GameSourceTable"] = get_stack_output(stack_name, region, "GameSourceTable")

    session_data = _generate_session_data(email, game, task_id)
    manifest = TaskManifest.load(game, task_id)
    session_data["$instruction"] = manifest.description
    session_data["$email"] = email
    if exam_code:
        session_data["$exam_code"] = str(exam_code)
    return session_data


def _generate_session_data(email: str, game: str, task_id: str) -> Dict[str, Any]:
    try:
        from common.session import generate_session

        return generate_session(email, game, task_id)
    except ModuleNotFoundError as exc:
        if exc.name != "names_generator":
            raise
        return _generate_session_data_via_venv(email, game, task_id)


def _generate_session_data_via_venv(email: str, game: str, task_id: str) -> Dict[str, Any]:
    python_executable = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
    if not os.path.exists(python_executable):
        raise RuntimeError(
            "names_generator is not available in the current Python environment and "
            f"fallback interpreter was not found at {python_executable}"
        )

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    python_paths = [COMMON_LAYER_DIR]
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(python_paths)

    completed = subprocess.run(
        [
            python_executable,
            "-c",
            (
                "import json; "
                "from common.session import generate_session; "
                f"print(json.dumps(generate_session({email!r}, {game!r}, {task_id!r})))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def save_state_item(table_name: str, region: str, item: Dict[str, Any]) -> None:
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    table.put_item(Item=item)


def get_task_id(item: Dict[str, Any], game: str) -> str:
    task_id = item.get("task_id")
    if task_id:
        return str(task_id)

    game_task = str(item.get("gameTask", ""))
    prefix = f"{game}#"
    if game_task.startswith(prefix):
        return game_task[len(prefix):]
    return game_task


def main() -> int:
    args = parse_args()
    try:
        table_name = get_stack_output(args.stack_name, args.region, "TaskStateTable")
        items = (
            [load_state_item(table_name, args.region, args.email, args.game, args.task)]
            if args.task
            else load_state_items(table_name, args.region, args.email, args.game)
        )
    except (ValueError, ClientError) as exc:
        print(f"Reset failed: {exc}", file=sys.stderr)
        return 1

    if not items:
        print(f"Reset failed: no task states found for {args.email} {args.game}", file=sys.stderr)
        return 1

    reset_results = []
    updated_items = []
    for item in sorted(items, key=lambda entry: get_task_id(entry, args.game)):
        updated, summary = reset_state_item(
            item=item,
            target_phase=args.phase_id,
            clear_all_phases=args.clear_all_phases,
        )
        updated["session_data"] = regenerate_session_data(updated, args.stack_name, args.region)
        summary["session_regenerated"] = True
        updated_items.append(updated)
        reset_results.append(
            {
                "task": get_task_id(updated, args.game),
                "summary": summary,
            }
        )

    payload = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "table": table_name,
        "email": args.email,
        "game": args.game,
        "task": args.task,
        "all_tasks": args.all_tasks,
        "task_count": len(reset_results),
        "target_phase": args.phase_id,
        "results": reset_results,
    }
    print(json.dumps(payload, indent=2, cls=DecimalEncoder))

    if not args.apply:
        return 0

    try:
        for updated in updated_items:
            save_state_item(table_name, args.region, updated)
    except ClientError as exc:
        print(f"Apply failed: {exc}", file=sys.stderr)
        return 1

    print(f"Task stage reset applied to {len(updated_items)} task(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
