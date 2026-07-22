"""Tests for the minimal durable probe handler."""

import importlib.util
import os
import sys
import types
from unittest.mock import patch


MODULE_NAME = "exam_durable_probe_app"
HANDLER_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "exam-durable-probe-handler",
    "app.py",
)


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


class StubStepContext:
    def __init__(self):
        self.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)


class StubContext:
    def __init__(self):
        self.calls = []

    def step(self, value):
        self.calls.append(value)
        return {"wrapped": value}


def test_probe_step_returns_serializable_payload():
    module = load_module()

    result = module.probe_step(StubStepContext(), "ok")

    assert result["status"] == "ok"
    assert result["mode"] == "ok"
    assert isinstance(result["checked_at"], str)


def test_probe_step_can_raise_intentional_failure():
    module = load_module()

    try:
        module.probe_step(StubStepContext(), "fail")
    except RuntimeError as err:
        assert str(err) == "intentional durable probe failure"
    else:
        raise AssertionError("probe_step did not raise")


def test_lambda_handler_routes_through_context_step():
    module = load_module()
    context = StubContext()

    with patch.object(module, "probe_step", return_value={"status": "ok", "mode": "ok"}) as mock_step:
        result = module.lambda_handler({"mode": "ok"}, context)

    mock_step.assert_called_once_with("ok")
    assert len(context.calls) == 1
    assert context.calls[0]["status"] == "ok"
    assert context.calls[0]["mode"] == "ok"
    assert result["wrapped"]["status"] == "ok"
