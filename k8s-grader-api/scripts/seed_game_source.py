#!/usr/bin/env python3
"""Validate and seed a private game source archive into S3/DynamoDB."""
from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import boto3


SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    "venv",
    ".venv",
    "htmlcov",
    ".aws-sam",
}


@dataclass
class GameSourceSeedPlan:
    game: str
    repo_root: Path
    bucket: str
    key: str
    uri: str
    mode: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and seed a private game source archive for exercise/exam use."
    )
    parser.add_argument("--stack-name", default="k8s-grader-api-dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--game", required=True)
    parser.add_argument(
        "--repo-root",
        default="../../k8s-game-rule",
        help="Path to the k8s-game-rule repository (default: ../../k8s-game-rule)",
    )
    parser.add_argument(
        "--s3-key",
        default="",
        help="Override the S3 object key (default: <game>/k8s-game-rule.zip)",
    )
    parser.add_argument(
        "--mode",
        choices=["exercise", "exam"],
        default="exercise",
        help="Mode to store in GameAccessTable (default: exercise)",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def validate_game_repo(repo_root: Path, game: str) -> None:
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError(f"Game rule repository does not exist: {repo_root}")

    tests_root = repo_root / "tests"
    if not tests_root.exists() or not tests_root.is_dir():
        raise ValueError(f"Tests root does not exist: {tests_root}")

    game_dir = tests_root / game
    if not game_dir.exists() or not game_dir.is_dir():
        raise ValueError(f"Game folder does not exist: {game_dir}")


def get_stack_output(stack_name: str, region: str, key: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == key:
            return output["OutputValue"]
    raise ValueError(f"CloudFormation output not found: {key}")


def get_stack_resource_physical_id(stack_name: str, region: str, logical_id: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stack_resource(StackName=stack_name, LogicalResourceId=logical_id)
    physical_id = response.get("StackResourceDetail", {}).get("PhysicalResourceId", "")
    if not physical_id:
        raise ValueError(f"CloudFormation resource not found: {logical_id}")
    return physical_id


def build_plan(
    *,
    stack_name: str,
    region: str,
    game: str,
    repo_root: Path,
    s3_key: str,
    mode: str,
) -> GameSourceSeedPlan:
    validate_game_repo(repo_root, game)
    bucket = get_stack_resource_physical_id(stack_name, region, "GameSourceBucket")
    key = s3_key or f"{game}/k8s-game-rule.zip"
    return GameSourceSeedPlan(
        game=game,
        repo_root=repo_root.resolve(),
        bucket=bucket,
        key=key,
        uri=f"s3://{bucket}/{key}",
        mode=mode,
    )


def create_archive(repo_root: Path, archive_path: Path) -> None:
    repo_root = repo_root.resolve()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for file_name in files:
                path = Path(root) / file_name
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                zf.write(path, arcname=str(path.relative_to(repo_root.parent)))


def seed_game_source(plan: GameSourceSeedPlan, stack_name: str, region: str) -> None:
    game_source_table = get_stack_output(stack_name, region, "GameSourceTable")
    game_access_table = get_stack_output(stack_name, region, "GameAccessTable")

    with tempfile.NamedTemporaryFile(prefix=f"{plan.game}-source-", suffix=".zip", delete=False) as temp_file:
        archive_path = Path(temp_file.name)

    try:
        create_archive(plan.repo_root, archive_path)
        boto3.client("s3", region_name=region).upload_file(str(archive_path), plan.bucket, plan.key)

        ddb = boto3.resource("dynamodb", region_name=region)
        ddb.Table(game_source_table).put_item(
            Item={
                "game": plan.game,
                "source": plan.uri,
            }
        )
        ddb.Table(game_access_table).put_item(
            Item={
                "game": plan.game,
                "mode": plan.mode,
            }
        )
    finally:
        if archive_path.exists():
            archive_path.unlink()


def main() -> int:
    args = parse_args()
    plan = build_plan(
        stack_name=args.stack_name,
        region=args.region,
        game=args.game,
        repo_root=Path(args.repo_root),
        s3_key=args.s3_key,
        mode=args.mode,
    )

    print(f"Game: {plan.game}")
    print(f"Repository: {plan.repo_root}")
    print(f"Tests folder: {plan.repo_root / 'tests' / plan.game}")
    print(f"S3 URI: {plan.uri}")
    print(f"Access mode: {plan.mode}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to upload the archive and update DynamoDB.")
        return 0

    seed_game_source(plan, args.stack_name, args.region)
    print("Game source uploaded and database records updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
