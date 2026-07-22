import json
import logging
import os
import shutil
import threading
import urllib.request
import zipfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
import pytest
from common.database import get_game_source
from common.status import GamePhrase, TestResult
from jinja2 import Environment

logger = logging.getLogger(__name__)

PYTEST_TIMEOUT_SECONDS = 30

MAPPING = {
    GamePhrase.SETUP: "01_setup",
    GamePhrase.READY: "02_ready",
    GamePhrase.ANSWER: "03_answer",
    GamePhrase.CHALLENGE: "04_challenge",
    GamePhrase.CHECK: "05_check",
    GamePhrase.CLEANUP: "06_cleanup",
}

GAME_PHRASE_ORDER = [
    GamePhrase.SETUP,
    GamePhrase.READY,
    GamePhrase.CHALLENGE,
    GamePhrase.CHECK,
    GamePhrase.CLEANUP,
]


def get_root_path(game: str) -> str:
    return f"/tmp/{game}"


def get_test_base_path(game: str) -> str:
    return f"/tmp/{game}/tests"


def run_tests(test_phase, game: str, task: str, timeout: int = None) -> TestResult:
    """
    Run pytest tests for a specific phase.
    
    CRITICAL: Answer phase is SKIPPED in production.
    The answer phase auto-deploys solutions and is ONLY for development/testing.
    
    Args:
        test_phase: Either a GamePhrase enum or a string ('setup', 'check', etc.)
        game: Game identifier
        task: Task identifier
        timeout: Optional timeout in seconds
    """
    # Convert string to GamePhrase enum if needed
    if isinstance(test_phase, str):
        try:
            test_phase = GamePhrase(test_phase)
        except ValueError:
            logger.error(f"Invalid test phase: {test_phase}")
            return TestResult.USAGE_ERROR
    
    # ============================================================
    # SKIP ANSWER PHASE - Never run in production
    # ============================================================
    if test_phase == GamePhrase.ANSWER:
        logger.info(f"Skipping answer phase for {game}/{task} - answer phase is for development only")
        return TestResult.NO_TESTS_COLLECTED
    # ============================================================
    
    get_tests(game)
    retcode = TestResult.OK.value
    result_container = [retcode]

    def run_pytest():
        result_container[0] = pytest.main(
            [
                f"--rootdir={get_root_path(game)}",
                "--import-mode=importlib",
                "--html=/tmp/report.html",
                "--self-contained-html",
                "-x",
                f"{get_test_base_path(game)}/{game}/{task}/test_{MAPPING[test_phase]}.py",
            ]
        )

    thread = threading.Thread(target=run_pytest)
    thread.start()
    # Use provided timeout or fall back to default
    timeout_seconds = timeout if timeout is not None else PYTEST_TIMEOUT_SECONDS
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        return TestResult.TIME_OUT
    return TestResult(result_container[0])


def get_archive_root(archive_path: str) -> str:
    with zipfile.ZipFile(archive_path) as archive:
        roots = {
            name.split("/", 1)[0]
            for name in archive.namelist()
            if name and not name.endswith("/")
        }

    if len(roots) != 1:
        raise ValueError(f"Expected one root directory in archive, got: {sorted(roots)}")

    return roots.pop()


def download_source_archive(source: str, archive_path: str) -> None:
    if source.startswith("s3://"):
        parsed = urlparse(source)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid S3 source URI: {source}")

        boto3.client("s3").download_file(bucket, key, archive_path)
        return

    if source.startswith("https://") or source.startswith("http://"):
        urllib.request.urlretrieve(source, archive_path)
        return

    raise ValueError(f"Unsupported game source URI: {source}")


def build_source_fingerprint(source: str) -> str:
    """Build a deterministic fingerprint for source cache invalidation."""
    if source.startswith("s3://"):
        parsed = urlparse(source)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid S3 source URI: {source}")

        response = boto3.client("s3").head_object(Bucket=bucket, Key=key)
        etag = (response.get("ETag") or "").strip('"')
        size = response.get("ContentLength", 0)
        last_modified = response.get("LastModified")
        last_modified_token = ""
        if last_modified:
            if hasattr(last_modified, "isoformat"):
                last_modified_token = str(last_modified.isoformat())
            elif hasattr(last_modified, "timestamp"):
                last_modified_token = str(last_modified.timestamp())
            else:
                last_modified_token = str(last_modified)
        return f"{source}#etag={etag}#size={size}#lm={last_modified_token}"

    if source.startswith("https://") or source.startswith("http://"):
        return source

    raise ValueError(f"Unsupported game source URI: {source}")


def get_tests(game: str) -> None:
    source = get_game_source(game)
    if not source:
        raise ValueError(f"Game source not found for {game}")
    source_fingerprint = build_source_fingerprint(source)
    
    # Cache invalidation: Check if source URL changed
    source_cache_file = f"/tmp/{game}_source.txt"
    cached_source_fingerprint = None
    if os.path.exists(source_cache_file):
        with open(source_cache_file, "r") as f:
            cached_source_fingerprint = f.read().strip()
    
    # If source changed, clear the cache
    if cached_source_fingerprint and cached_source_fingerprint != source_fingerprint:
        logger.info(f"Game source changed for {game}, clearing cache")
        # Remove old files if they exist
        zip_file = f"/tmp/{game}.zip"
        if os.path.exists(zip_file):
            os.remove(zip_file)
        root_path = get_root_path(game)
        if os.path.exists(root_path):
            shutil.rmtree(root_path)
    
    distination = f"/tmp/{game}.zip"
    root_path = get_root_path(game)
    needs_download = not os.path.exists(distination)
    needs_extract = not os.path.exists(root_path)

    if not needs_download and not needs_extract:
        return

    try:
        if needs_download:
            download_source_archive(source, distination)

        if needs_extract:
            shutil.unpack_archive(distination, "/tmp/")
            source_folder = get_archive_root(distination)
            extracted_path = f"/tmp/{source_folder}"
            if not os.path.exists(extracted_path):
                raise ValueError(f"Extracted archive folder not found: {source_folder}")

            if os.path.exists(root_path):
                shutil.rmtree(root_path)
            shutil.move(extracted_path, root_path)

            # Save the current source fingerprint for cache validation
            with open(source_cache_file, "w") as f:
                f.write(source_fingerprint)
    except (IOError, OSError, shutil.Error, ClientError, ValueError) as e:
        raise RuntimeError(f"Failed to download or extract tests: {e}") from e


def get_tasks(game: str) -> List[str]:
    get_tests(game)
    folder = f"{get_test_base_path(game)}/{game}/"
    tasks = []
    for file in sorted(os.listdir(folder)):
        if os.path.isdir(os.path.join(folder, file)) and "99_test_template" not in file:
            tasks.append(file)
    return tasks


def get_session_template(game: str, task: str) -> Dict[str, any]:
    get_tests(game)
    session = {}
    game_session_file = f"{get_test_base_path(game)}/{game}/session.json"
    task_session_file = f"{get_test_base_path(game)}/{game}/{task}/session.json"
    if os.path.exists(game_session_file):
        with open(game_session_file, "r", encoding="utf-8") as file:
            game_session = json.load(file)
            session.update(game_session)
    if os.path.exists(task_session_file):
        with open(task_session_file, "r", encoding="utf-8") as file:
            task_session = json.load(file)
            session.update(task_session)

    return session


def get_current_task(game: str, finished_tasks: List[str]) -> Optional[str]:
    all_tasks = get_tasks(game)
    current_task = None
    for task in all_tasks:
        if task not in [task for task in finished_tasks]:
            current_task = task
            break
    return current_task


def render(template: str, session: Dict[str, any]) -> str:
    env = Environment()
    jinja_template = env.from_string(template)
    template_string = jinja_template.render(session)
    return template_string


def get_instruction(game: str, task: str, session: Dict[str, any]) -> Optional[str]:
    get_tests(game)
    instructions_file = f"{get_test_base_path(game)}/{game}/{task}/instruction.md"

    if os.path.exists(instructions_file):
        with open(instructions_file, "r", encoding="utf-8") as file:
            instruction = file.read()
        return render(instruction, session)
    return None


def get_ai_instruction(instruction: str, session: Dict[str, any]) -> str:
    return render(instruction, session)


def get_next_game_phrase(game: str, task: str, current_game_phrase) -> Optional[GamePhrase]:
    """
    Get the next game phrase that has a test file.
    
    Args:
        game: Game identifier
        task: Task identifier
        current_game_phrase: Either a GamePhrase enum or a string
        
    Returns:
        Next GamePhrase enum or None if no more phases
    """
    # Convert string to GamePhrase enum if needed
    if isinstance(current_game_phrase, str):
        try:
            current_game_phrase = GamePhrase(current_game_phrase)
        except ValueError:
            logger.error(f"Invalid game phrase: {current_game_phrase}")
            return None
    
    get_tests(game)

    current_index = GAME_PHRASE_ORDER.index(current_game_phrase)
    for next_index in range(current_index + 1, len(GAME_PHRASE_ORDER)):
        test_file = f"{get_test_base_path(game)}/{game}/{task}/test_{MAPPING[GAME_PHRASE_ORDER[next_index]]}.py"
        if os.path.exists(test_file):
            return GAME_PHRASE_ORDER[next_index]
    return None
