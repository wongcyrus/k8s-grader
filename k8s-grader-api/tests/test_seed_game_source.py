"""Tests for private game source seeding script."""
import importlib.util
from pathlib import Path
import sys
import zipfile

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_game_source.py"
SPEC = importlib.util.spec_from_file_location("seed_game_source", SCRIPT_PATH)
seed_game_source = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seed_game_source
SPEC.loader.exec_module(seed_game_source)


def create_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "k8s-game-rule"
    (repo_root / "tests" / "game02" / "087_sidecar_containers").mkdir(parents=True, exist_ok=True)
    (repo_root / "tests" / "game02" / "087_sidecar_containers" / "instruction.md").write_text(
        "Do task",
        encoding="utf-8",
    )
    return repo_root


def test_validate_game_repo_requires_game_folder(tmp_path: Path):
    repo_root = tmp_path / "k8s-game-rule"
    (repo_root / "tests").mkdir(parents=True)

    with pytest.raises(ValueError, match="Game folder does not exist"):
        seed_game_source.validate_game_repo(repo_root, "game02")


def test_build_plan_uses_stack_bucket_and_default_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root = create_repo(tmp_path)
    monkeypatch.setattr(seed_game_source, "get_stack_resource_physical_id", lambda *args: "game-source-bucket")

    plan = seed_game_source.build_plan(
        stack_name="k8s-grader-api-dev",
        region="us-east-1",
        game="game02",
        repo_root=repo_root,
        s3_key="",
        mode="exercise",
    )

    assert plan.bucket == "game-source-bucket"
    assert plan.key == "game02/k8s-game-rule.zip"
    assert plan.uri == "s3://game-source-bucket/game02/k8s-game-rule.zip"
    assert plan.mode == "exercise"


def test_create_archive_keeps_repo_root_and_skips_hidden_dirs(tmp_path: Path):
    repo_root = create_repo(tmp_path)
    (repo_root / ".git" / "ignored").mkdir(parents=True, exist_ok=True)
    (repo_root / ".git" / "ignored" / "config").write_text("secret", encoding="utf-8")
    (repo_root / ".env").write_text("TOP_SECRET=1", encoding="utf-8")
    (repo_root / "tests" / "game02" / ".secrets").write_text("hidden", encoding="utf-8")
    archive_path = tmp_path / "game-source.zip"

    seed_game_source.create_archive(repo_root, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()

    assert "k8s-game-rule/tests/game02/087_sidecar_containers/instruction.md" in names
    assert not any(name.startswith("k8s-game-rule/.git/") for name in names)
    assert "k8s-game-rule/.env" not in names
    assert "k8s-game-rule/tests/game02/.secrets" not in names
