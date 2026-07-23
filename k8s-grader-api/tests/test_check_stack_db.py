"""Tests for stack-backed DB inspection script."""
import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_stack_db.py"
SPEC = importlib.util.spec_from_file_location("check_stack_db", SCRIPT_PATH)
check_stack_db = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_stack_db
SPEC.loader.exec_module(check_stack_db)


def test_describe_tables_resolves_outputs_and_status(monkeypatch):
    monkeypatch.setattr(
        check_stack_db,
        "get_stack_outputs",
        lambda stack_name, region: {
            "AccountTable": "AccountTableName",
            "TaskStateTable": "TaskStateTableName",
        },
    )

    class FakeDynamoClient:
        def describe_table(self, TableName):
            return {
                "Table": {
                    "TableStatus": "ACTIVE",
                    "ItemCount": 7,
                    "KeySchema": [
                        {"AttributeName": "email", "KeyType": "HASH"},
                        {"AttributeName": "gameTask", "KeyType": "RANGE"},
                    ],
                }
            }

    class FakeBoto3:
        def client(self, service_name, region_name=None):
            assert service_name == "dynamodb"
            return FakeDynamoClient()

    monkeypatch.setattr(check_stack_db, "boto3", FakeBoto3())

    rows = check_stack_db.describe_tables("stack", "us-east-1")

    account_row = next(row for row in rows if row["output_key"] == "AccountTable")
    assert account_row["table_name"] == "AccountTableName"
    assert account_row["status"] == "ACTIVE"
    assert account_row["items"] == "7"
    assert account_row["keys"] == "email:HASH, gameTask:RANGE"

    missing_row = next(row for row in rows if row["output_key"] == "ApiKeyTable")
    assert missing_row["status"] == "MISSING"
