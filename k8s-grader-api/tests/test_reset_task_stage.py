"""Tests for reset task stage script."""
import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "reset_task_stage.py"
SPEC = importlib.util.spec_from_file_location("reset_task_stage", SCRIPT_PATH)
reset_task_stage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reset_task_stage
SPEC.loader.exec_module(reset_task_stage)


def test_reset_state_item_drops_target_and_later_standard_phases():
    item = {
        "email": "student@example.com",
        "gameTask": "game02#087_task",
        "status": "completed",
        "current_phase_id": None,
        "completed_at": "2026-01-01T00:00:00+00:00",
        "total_points": 25,
        "phase_states": {
            "setup": {"status": "passed", "points_earned": 0},
            "ready": {"status": "passed", "points_earned": 5},
            "challenge": {"status": "failed", "points_earned": 0},
            "check": {"status": "passed", "points_earned": 20},
        },
    }

    updated, summary = reset_task_stage.reset_state_item(item, target_phase="challenge")

    assert updated["status"] == "in_progress"
    assert updated["current_phase_id"] == "challenge"
    assert updated["completed_at"] is None
    assert set(updated["phase_states"].keys()) == {"setup", "ready"}
    assert updated["total_points"] == 5
    assert summary["old_phase_count"] == 4
    assert summary["new_phase_count"] == 2


def test_reset_state_item_clear_all_phases():
    item = {
        "status": "completed",
        "current_phase_id": "check",
        "completed_at": "2026-01-01T00:00:00+00:00",
        "total_points": 20,
        "phase_states": {
            "setup": {"status": "passed", "points_earned": 0},
            "check": {"status": "passed", "points_earned": 20},
        },
    }

    updated, summary = reset_task_stage.reset_state_item(
        item, target_phase="setup", clear_all_phases=True
    )

    assert updated["phase_states"] == {}
    assert updated["total_points"] == 0
    assert updated["current_phase_id"] == "setup"
    assert summary["cleared_all_phases"] is True


def test_get_task_id_prefers_explicit_task_id():
    item = {
        "task_id": "087_sidecar_containers",
        "gameTask": "game02#ignored",
    }

    assert reset_task_stage.get_task_id(item, "game02") == "087_sidecar_containers"


def test_get_task_id_falls_back_to_game_task_suffix():
    item = {
        "gameTask": "game02#087_sidecar_containers",
    }

    assert reset_task_stage.get_task_id(item, "game02") == "087_sidecar_containers"


def test_parse_args_supports_all_tasks(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reset_task_stage.py",
            "--email",
            "student@example.com",
            "--game",
            "game02",
            "--all-tasks",
            "--phase-id",
            "setup",
        ],
    )

    args = reset_task_stage.parse_args()

    assert args.all_tasks is True
    assert args.task is None
    assert args.phase_id == "setup"


def test_regenerate_session_data_adds_template_values(monkeypatch):
    item = {
        "email": "student@example.com",
        "game": "game02",
        "gameTask": "game02#087_sidecar_containers",
        "exam_code": "EXAM-001",
    }

    class FakeManifest:
        description = "Task instruction"

    monkeypatch.setattr(reset_task_stage, "get_stack_output", lambda *args, **kwargs: "GameSourceTableName")
    monkeypatch.setattr(reset_task_stage, "_generate_session_data", lambda email, game, task: {"namespace": "fresh-ns", "pod_name": "fresh-pod"})
    monkeypatch.setattr("common.models.task_manifest.TaskManifest.load", lambda game, task: FakeManifest())

    session = reset_task_stage.regenerate_session_data(item, "stack", "us-east-1")

    assert session["namespace"] == "fresh-ns"
    assert session["pod_name"] == "fresh-pod"
    assert session["$instruction"] == "Task instruction"
    assert session["$email"] == "student@example.com"
    assert session["$exam_code"] == "EXAM-001"


def test_regenerate_session_data_is_deterministic_per_student(monkeypatch):
    item = {
        "email": "student@example.com",
        "game": "game02",
        "gameTask": "game02#087_sidecar_containers",
    }

    class FakeManifest:
        description = "Task instruction"

    monkeypatch.setattr(reset_task_stage, "get_stack_output", lambda *args, **kwargs: "GameSourceTableName")
    monkeypatch.setattr(
        reset_task_stage,
        "_generate_session_data",
        lambda email, game, task: {
            "namespace": "eloquentdavinci350student",
            "pod_name": "eloquentdavinci",
        },
    )
    monkeypatch.setattr("common.models.task_manifest.TaskManifest.load", lambda game, task: FakeManifest())
    session_one = reset_task_stage.regenerate_session_data(item, "stack", "us-east-1")
    session_two = reset_task_stage.regenerate_session_data(item, "stack", "us-east-1")

    assert session_one["pod_name"] == session_two["pod_name"]
    assert session_one["namespace"] == session_two["namespace"]


def test_generate_session_data_uses_venv_fallback_for_names_generator(monkeypatch):
    class MissingNamesGenerator(ModuleNotFoundError):
        def __init__(self):
            super().__init__("No module named 'names_generator'")
            self.name = "names_generator"

    monkeypatch.setattr(
        reset_task_stage,
        "_generate_session_data_via_venv",
        lambda email, game, task: {"namespace": "from-venv", "pod_name": "from-venv"},
    )

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "common.session":
            raise MissingNamesGenerator()
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    session = reset_task_stage._generate_session_data("student@example.com", "game02", "087_sidecar_containers")

    assert session == {"namespace": "from-venv", "pod_name": "from-venv"}
