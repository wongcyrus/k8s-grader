"""Tests for exam seeding validation script."""
import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_exam_code.py"
SPEC = importlib.util.spec_from_file_location("seed_exam_code", SCRIPT_PATH)
seed_exam_code = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seed_exam_code
SPEC.loader.exec_module(seed_exam_code)


def create_task(root: Path, name: str, with_check: bool = True, instruction: str = "Do task") -> None:
    task_dir = root / name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "instruction.md").write_text(instruction, encoding="utf-8")
    (task_dir / "test_01_setup.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    if with_check:
        (task_dir / "test_05_check.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def test_resolve_tasks_numeric_prefix_orders_by_prefix(tmp_path: Path):
    game_dir = tmp_path / "game02"
    tasks_dir = game_dir / "tasks"
    create_task(tasks_dir, "123_c")
    create_task(tasks_dir, "007_a")
    create_task(tasks_dir, "087_b")

    tasks = seed_exam_code.resolve_tasks(
        game_dir=game_dir,
        task_folder="tasks",
        order_mode="numeric_prefix",
        explicit_tasks=[],
    )
    assert tasks == ["007_a", "087_b", "123_c"]


def test_resolve_tasks_numeric_prefix_fails_without_prefix(tmp_path: Path):
    game_dir = tmp_path / "game02"
    tasks_dir = game_dir / "tasks"
    create_task(tasks_dir, "bad_task")

    with pytest.raises(ValueError, match="numeric prefix"):
        seed_exam_code.resolve_tasks(
            game_dir=game_dir,
            task_folder="tasks",
            order_mode="numeric_prefix",
            explicit_tasks=[],
        )


def test_validate_task_folder_requires_check_phase(tmp_path: Path):
    task_dir = tmp_path / "087_missing_check"
    task_dir.mkdir(parents=True)
    (task_dir / "instruction.md").write_text("hi", encoding="utf-8")
    (task_dir / "test_01_setup.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    with pytest.raises(ValueError, match="test_05_check.py"):
        seed_exam_code.validate_task_folder(task_dir)


def test_build_plan_from_args_success(tmp_path: Path):
    tests_root = tmp_path / "tests"
    game_dir = tests_root / "game02"
    tasks_dir = game_dir / "examset"
    create_task(tasks_dir, "087_kustomize_configuration")
    create_task(tasks_dir, "123_service_hairpin_mode")

    args = seed_exam_code.argparse.Namespace(
        stack_name="k8s-grader-api-dev",
        region="us-east-1",
        exam_code="GAME02-EXAM-TEST",
        game="game02",
        game_tests_root=str(tests_root),
        task_folder="examset",
        order_mode="numeric_prefix",
        tasks="",
        starts_at="2026-01-01T00:00:00+00:00",
        ends_at="2026-12-31T23:59:59+00:00",
        max_attempts=3,
        status="active",
        apply=False,
        update=False,
    )

    plan = seed_exam_code.build_plan_from_args(args)
    assert plan.exam_code == "GAME02-EXAM-TEST"
    assert plan.tasks == ["087_kustomize_configuration", "123_service_hairpin_mode"]


def test_build_plan_from_args_fails_if_explicit_task_missing(tmp_path: Path):
    tests_root = tmp_path / "tests"
    game_dir = tests_root / "game02"
    tasks_dir = game_dir / "examset"
    create_task(tasks_dir, "087_kustomize_configuration")

    args = seed_exam_code.argparse.Namespace(
        stack_name="k8s-grader-api-dev",
        region="us-east-1",
        exam_code="GAME02-EXAM-TEST",
        game="game02",
        game_tests_root=str(tests_root),
        task_folder="examset",
        order_mode="explicit",
        tasks="087_kustomize_configuration,999_missing",
        starts_at="2026-01-01T00:00:00+00:00",
        ends_at="2026-12-31T23:59:59+00:00",
        max_attempts=3,
        status="active",
        apply=False,
        update=False,
    )

    with pytest.raises(ValueError, match="not found"):
        seed_exam_code.build_plan_from_args(args)
