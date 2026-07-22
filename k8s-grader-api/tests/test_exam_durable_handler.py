"""Tests for the durable exam command handler."""
import importlib.util
import json
import logging
import os
import sys
import types
from unittest.mock import patch


MODULE_NAME = "exam_durable_app"
HANDLER_PATH = os.path.join(os.path.dirname(__file__), "..", "exam-durable-handler", "app.py")


def load_module():
    fake_sdk = types.ModuleType("aws_durable_execution_sdk_python")

    class DurableContext:
        pass

    def durable_execution(fn):
        return fn

    def durable_step(fn):
        return fn

    fake_sdk.DurableContext = DurableContext
    fake_sdk.durable_execution = durable_execution
    fake_sdk.durable_step = durable_step

    sys.modules["aws_durable_execution_sdk_python"] = fake_sdk
    spec = importlib.util.spec_from_file_location(MODULE_NAME, HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


class StubContext:
    def __init__(self):
        self.calls = []

    def step(self, value):
        self.calls.append(value)
        return {"wrapped": value}


def test_execute_exam_command_dispatches_start():
    module = load_module()

    with patch.object(module, "handle_exam_start", return_value={"statusCode": 200}) as mock_start:
        result = module.execute_exam_command(
            "start",
            "student@example.com",
            "EXAM-001",
            "game02",
            "087_task",
        )

    mock_start.assert_called_once_with("student@example.com", "EXAM-001", "game02", "087_task")
    assert result == {"statusCode": 200}


def test_execute_exam_command_step_wraps_plain_helper():
    module = load_module()

    with patch.object(module, "execute_exam_command", return_value={"statusCode": 200}) as mock_execute:
        result = module.execute_exam_command_step(None, "status", "student@example.com", "EXAM-001", "game02", "087_task")

    mock_execute.assert_called_once_with("status", "student@example.com", "EXAM-001", "game02", "087_task")
    assert result == {"statusCode": 200}


def test_execute_exam_command_rejects_invalid_payload():
    module = load_module()

    result = module.execute_exam_command("run", "", "", None, None)

    body = json.loads(result["body"])
    assert body["status"] == "ERROR"
    assert "Invalid exam command payload" in body["message"]


def test_lambda_handler_routes_through_context_step():
    module = load_module()
    context = StubContext()
    event = {
        "action": "records",
        "email": "student@example.com",
        "exam_code": "EXAM-001",
        "game": "game02",
        "task_id": "087_task",
    }

    with patch.object(module, "records_exam_command_step", return_value={"statusCode": 200}) as mock_step:
        result = module.lambda_handler(event, context)

    mock_step.assert_called_once_with(
        "student@example.com",
        "EXAM-001",
        "game02",
        "087_task",
    )
    assert context.calls == [{"statusCode": 200}]
    assert result == {"wrapped": {"statusCode": 200}}


def test_handle_exam_records_broadcasts_only_with_scope():
    module = load_module()
    exam_service = module.get_exam_service()

    with patch.object(exam_service, "list_records", return_value=[{"task": "087_task"}]), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        response = module.handle_exam_records("student@example.com", "EXAM-001", "game02", "087_task")

    body = json.loads(response["body"])
    assert body["status"] == "OK"
    assert body["records"] == [{"task": "087_task"}]
    mock_broadcast.assert_called_once()


def test_execute_exam_command_surfaces_unhandled_action_errors():
    module = load_module()

    with patch.object(module, "handle_exam_run", side_effect=RuntimeError("boom")), \
         patch.object(module, "broadcast_exam_response") as mock_broadcast:
        result = module.execute_exam_command(
            "run",
            "student@example.com",
            "EXAM-001",
            "game02",
            "087_task",
        )

    body = json.loads(result["body"])
    assert body["status"] == "ERROR"
    assert "Exam action 'run' failed: boom" in body["message"]
    mock_broadcast.assert_called_once()


def test_module_resets_log_record_factory():
    original_factory = logging.getLogRecordFactory()

    class FakeLogRecord(logging.LogRecord):
        pass

    logging.setLogRecordFactory(FakeLogRecord)
    try:
        module = load_module()
        assert module.logging.getLogRecordFactory() is logging.LogRecord
    finally:
        logging.setLogRecordFactory(original_factory)
