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
