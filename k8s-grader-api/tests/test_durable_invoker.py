"""Tests for durable Lambda invocation helper."""
import json

import pytest

from common.durable_invoker import invoke_durable_function


class StubLambdaClient:
    def __init__(self):
        self.calls = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"RequestId": "req-123"}}


def test_invoke_durable_function_requires_configured_arn():
    with pytest.raises(ValueError, match="not configured"):
        invoke_durable_function("", {"action": "run"})


def test_invoke_durable_function_requires_qualified_identifier():
    with pytest.raises(ValueError, match="qualified ARN"):
        invoke_durable_function("exam-command-durable", {"action": "run"})


def test_invoke_durable_function_invokes_lambda_client():
    client = StubLambdaClient()

    request_id = invoke_durable_function(
        "arn:aws:lambda:us-east-1:123456789012:function:exam-command-durable:live",
        {"action": "run", "task_id": "087_task"},
        client=client,
    )

    assert request_id == "req-123"
    assert client.calls == [{
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:exam-command-durable:live",
        "InvocationType": "Event",
        "Payload": json.dumps({"action": "run", "task_id": "087_task"}).encode("utf-8"),
    }]
