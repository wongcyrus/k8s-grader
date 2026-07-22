"""Integration tests for exam-mode flow against deployed stack."""
import os

import pytest
import requests


def _auth_headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "Authorization": api_key,
    }


@pytest.fixture(scope="session")
def exam_code() -> str:
    return os.environ.get("EXAM_CODE", "GAME02-EXAM-20260721")


@pytest.fixture(scope="session")
def exam_game() -> str:
    return os.environ.get("EXAM_GAME", "game02")


@pytest.fixture(scope="session")
def exam_task() -> str:
    return os.environ.get("EXAM_TASK", "087_kustomize_configuration")


@pytest.fixture(scope="session")
def minikube_url() -> str:
    return os.environ.get("MINIKUBE_URL", "https://fuzzy-capybara-6ppxv9grwqc4xp4-8001.app.github.dev/")


@pytest.mark.integration
class TestExamIntegration:
    """Exam flow integration tests using real deployed endpoints."""

    def test_exam_setup_verify_and_start(
        self,
        api_endpoint,
        test_api_key,
        exam_code,
        exam_game,
        exam_task,
        minikube_url,
    ):
        # 1) Save account (endpoint-only path; cert/key are auto-filled server-side for minikube-style setup)
        save_response = requests.post(
            f"{api_endpoint}/save-k8s-account/",
            files={"endpoint": (None, minikube_url)},
            headers=_auth_headers(test_api_key),
            timeout=30,
        )
        assert save_response.status_code == 200
        save_data = save_response.json()
        assert save_data["status"] == "OK"

        # 2) Verify exam code and scope
        verify_response = requests.get(
            f"{api_endpoint}/exam/verify-code",
            params={"examCode": exam_code},
            headers=_auth_headers(test_api_key),
            timeout=30,
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["status"] == "VERIFIED"
        assert verify_data["game"] == exam_game
        assert exam_task in verify_data.get("allowed_tasks", [])

        # 3) Start exam task
        start_response = requests.get(
            f"{api_endpoint}/exam/start",
            params={
                "examCode": exam_code,
                "game": exam_game,
                "task": exam_task,
            },
            headers=_auth_headers(test_api_key),
            timeout=30,
        )
        assert start_response.status_code == 200
        start_data = start_response.json()
        assert start_data["status"] in {"STARTED", "COMPLETED", "ABANDONED"}
        assert start_data.get("task_id") == exam_task

        # 4) Status should be queryable and return exam state payload
        status_response = requests.get(
            f"{api_endpoint}/exam/status",
            params={
                "examCode": exam_code,
                "game": exam_game,
                "task": exam_task,
            },
            headers=_auth_headers(test_api_key),
            timeout=30,
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["status"] == "OK"
        assert "state" in status_data
        assert "manifest" in status_data
