"""Tests for integration cleanup helpers."""
import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tests" / "integration" / "cleanup_test_keys.py"
SPEC = importlib.util.spec_from_file_location("cleanup_test_keys", SCRIPT_PATH)
cleanup_test_keys = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleanup_test_keys
SPEC.loader.exec_module(cleanup_test_keys)


def test_is_test_email_matches_current_prefixes():
    assert cleanup_test_keys.is_test_email("test-abc123@ex.com") is True
    assert cleanup_test_keys.is_test_email("integration-test-abc@example.com") is True
    assert cleanup_test_keys.is_test_email("student@example.com") is False


def test_get_test_emails_from_dynamodb_collects_paginated_matches():
    class FakeClient:
        def __init__(self):
            self.calls = 0

        def scan(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "Items": [
                        {"email": {"S": "test-a@ex.com"}},
                        {"email": {"S": "student@example.com"}},
                    ],
                    "LastEvaluatedKey": {"email": {"S": "continue"}},
                }
            return {
                "Items": [
                    {"email": {"S": "integration-test-b@example.com"}},
                ]
            }

    emails = cleanup_test_keys.get_test_emails_from_dynamodb(FakeClient(), "AccountTable")

    assert emails == ["integration-test-b@example.com", "test-a@ex.com"]


def test_delete_items_by_email_deletes_partition_and_sort_key_rows():
    class FakeClient:
        def __init__(self):
            self.deleted = []

        def delete_item(self, **kwargs):
            self.deleted.append(kwargs)

        def query(self, **kwargs):
            return {
                "Items": [
                    {"gameTask": {"S": "game01#task01"}},
                    {"gameTask": {"S": "game01#task02"}},
                ]
            }

    client = FakeClient()
    cleanup_test_keys.delete_items_by_email(client, "TaskStateTable", "test-a@ex.com", "gameTask")

    assert len(client.deleted) == 2
    assert client.deleted[0]["Key"]["gameTask"]["S"] == "game01#task01"
    assert client.deleted[1]["Key"]["gameTask"]["S"] == "game01#task02"
