#!/usr/bin/env python3
"""Validate and seed exam configuration into DynamoDB."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


NUMERIC_PREFIX_RE = re.compile(r"^(\d+)_")


@dataclass
class ExamSeedPlan:
    exam_code: str
    game: str
    tasks: List[str]
    starts_at: str
    ends_at: str
    max_attempts: int
    status: str
    task_source: str
    order_mode: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate exam tasks and seed ExamCodeTable/GameAccessTable."
    )
    parser.add_argument("--stack-name", default="k8s-grader-api-dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--exam-code", required=True)
    parser.add_argument("--game", required=True)
    parser.add_argument(
        "--game-tests-root",
        default="../../k8s-game-rule/tests",
        help="Path to tests root that contains game folders (default: ../../k8s-game-rule/tests)",
    )
    parser.add_argument(
        "--task-folder",
        default=".",
        help="Folder under the game directory containing task folders (default: .)",
    )
    parser.add_argument(
        "--order-mode",
        choices=["lexicographic", "numeric_prefix", "explicit"],
        default="numeric_prefix",
    )
    parser.add_argument(
        "--tasks",
        default="",
        help="Comma-separated task IDs when order-mode=explicit",
    )
    parser.add_argument(
        "--starts-at",
        required=True,
        help="ISO8601 datetime, e.g. 2026-01-01T00:00:00+00:00",
    )
    parser.add_argument(
        "--ends-at",
        required=True,
        help="ISO8601 datetime, e.g. 2026-12-31T23:59:59+00:00",
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--status", default="active")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--update", action="store_true")
    return parser.parse_args()


def parse_iso8601(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO datetime '{value}'") from exc


def resolve_tasks(
    game_dir: Path,
    task_folder: str,
    order_mode: str,
    explicit_tasks: List[str],
) -> List[str]:
    tasks_root = (game_dir / task_folder).resolve()
    if not tasks_root.exists() or not tasks_root.is_dir():
        raise ValueError(f"Task folder does not exist: {tasks_root}")

    discovered = sorted(
        p.name
        for p in tasks_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not discovered:
        raise ValueError(f"No task folders found under: {tasks_root}")

    if order_mode == "explicit":
        if not explicit_tasks:
            raise ValueError("order-mode=explicit requires --tasks")
        missing = [task for task in explicit_tasks if task not in discovered]
        if missing:
            raise ValueError(f"Explicit tasks not found in folder: {missing}")
        return explicit_tasks

    if order_mode == "lexicographic":
        return discovered

    # numeric_prefix
    missing_prefix = [task for task in discovered if not NUMERIC_PREFIX_RE.match(task)]
    if missing_prefix:
        raise ValueError(
            "All tasks must start with numeric prefix (<num>_) for numeric_prefix order. "
            f"Invalid tasks: {missing_prefix}"
        )
    return sorted(
        discovered,
        key=lambda task: (int(NUMERIC_PREFIX_RE.match(task).group(1)), task),
    )


def validate_task_folder(task_path: Path) -> None:
    instruction_path = task_path / "instruction.md"
    if not instruction_path.exists():
        raise ValueError(f"{task_path.name}: missing instruction.md")

    instruction = instruction_path.read_text(encoding="utf-8").strip()
    if not instruction:
        raise ValueError(f"{task_path.name}: instruction.md is empty")

    test_files = sorted(task_path.glob("test_*.py"))
    if not test_files:
        raise ValueError(f"{task_path.name}: missing test_*.py files")

    check_file = task_path / "test_05_check.py"
    if not check_file.exists():
        raise ValueError(
            f"{task_path.name}: missing test_05_check.py (required for exam validation)"
        )

    manifest_path = task_path / "manifest.json"
    if manifest_path.exists():
        try:
            json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{task_path.name}: invalid manifest.json: {exc}") from exc


def validate_exam_plan(plan: ExamSeedPlan, game_dir: Path, task_folder: str) -> None:
    if not plan.tasks:
        raise ValueError("Task list is empty")

    if len(plan.tasks) != len(set(plan.tasks)):
        raise ValueError("Task list contains duplicates")

    starts_at = parse_iso8601(plan.starts_at)
    ends_at = parse_iso8601(plan.ends_at)
    if ends_at <= starts_at:
        raise ValueError("ends-at must be after starts-at")

    if plan.max_attempts <= 0:
        raise ValueError("max-attempts must be > 0")

    tasks_root = (game_dir / task_folder).resolve()
    for task in plan.tasks:
        task_path = tasks_root / task
        if not task_path.exists() or not task_path.is_dir():
            raise ValueError(f"Task folder missing: {task_path}")
        validate_task_folder(task_path)


def get_stack_output(stack_name: str, region: str, key: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == key:
            return output["OutputValue"]
    raise ValueError(f"CloudFormation output not found: {key}")


def assert_game_source_exists(table_name: str, game: str, region: str) -> None:
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    response = table.get_item(Key={"game": game})
    item = response.get("Item")
    if not item or not item.get("source"):
        raise ValueError(f"Game source not found for game '{game}' in {table_name}")


def seed_dynamodb(
    plan: ExamSeedPlan,
    stack_name: str,
    region: str,
    update: bool,
) -> None:
    exam_code_table = get_stack_output(stack_name, region, "ExamCodeTable")
    game_access_table = get_stack_output(stack_name, region, "GameAccessTable")
    game_source_table = get_stack_output(stack_name, region, "GameSourceTable")

    assert_game_source_exists(game_source_table, plan.game, region)

    ddb = boto3.resource("dynamodb", region_name=region)
    exam_table = ddb.Table(exam_code_table)
    access_table = ddb.Table(game_access_table)

    existing = exam_table.get_item(Key={"examCode": plan.exam_code}).get("Item")
    if existing and not update:
        raise ValueError(
            f"Exam code '{plan.exam_code}' already exists. Use --update to overwrite."
        )

    now = int(time.time())
    exam_item = {
        "examCode": plan.exam_code,
        "game": plan.game,
        "allowedTasks": plan.tasks,
        "startsAt": plan.starts_at,
        "endsAt": plan.ends_at,
        "maxAttempts": plan.max_attempts,
        "status": plan.status,
        "time": now,
    }

    access_item = {
        "game": plan.game,
        "mode": "exam",
        "allowed_tasks": plan.tasks,
        "time": now,
    }

    exam_table.put_item(Item=exam_item)
    access_table.put_item(Item=access_item)


def build_plan_from_args(args: argparse.Namespace) -> ExamSeedPlan:
    game_dir = (Path(args.game_tests_root) / args.game).resolve()
    if not game_dir.exists() or not game_dir.is_dir():
        raise ValueError(f"Game folder does not exist: {game_dir}")

    explicit_tasks = [task.strip() for task in args.tasks.split(",") if task.strip()]
    tasks = resolve_tasks(
        game_dir=game_dir,
        task_folder=args.task_folder,
        order_mode=args.order_mode,
        explicit_tasks=explicit_tasks,
    )

    plan = ExamSeedPlan(
        exam_code=args.exam_code,
        game=args.game,
        tasks=tasks,
        starts_at=args.starts_at,
        ends_at=args.ends_at,
        max_attempts=args.max_attempts,
        status=args.status,
        task_source=str((game_dir / args.task_folder).resolve()),
        order_mode=args.order_mode,
    )
    validate_exam_plan(plan, game_dir=game_dir, task_folder=args.task_folder)
    return plan


def main() -> int:
    args = parse_args()
    try:
        plan = build_plan_from_args(args)
    except ValueError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    payload: Dict[str, Any] = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "exam_code": plan.exam_code,
        "game": plan.game,
        "order_mode": plan.order_mode,
        "task_source": plan.task_source,
        "task_count": len(plan.tasks),
        "tasks": plan.tasks,
        "starts_at": plan.starts_at,
        "ends_at": plan.ends_at,
        "max_attempts": plan.max_attempts,
        "status": plan.status,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload, indent=2))

    if not args.apply:
        return 0

    try:
        seed_dynamodb(
            plan=plan,
            stack_name=args.stack_name,
            region=args.region,
            update=args.update,
        )
    except (ValueError, ClientError) as exc:
        print(f"Apply failed: {exc}", file=sys.stderr)
        return 1

    print("Exam configuration applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
