"""Helpers for invoking Lambda durable functions."""
import json
from typing import Any, Dict, Optional

import boto3


def invoke_durable_function(
    function_name: str,
    payload: Dict[str, Any],
    *,
    invocation_type: str = "Event",
    client: Optional[Any] = None,
) -> str:
    """Invoke a Lambda durable function using a qualified ARN or alias-qualified name."""
    if not function_name:
        raise ValueError("ExamCommandDurableFunctionArn is not configured")

    if ":" not in function_name:
        raise ValueError("Durable functions require a qualified ARN or alias-qualified function name")

    lambda_client = client or boto3.client("lambda")
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType=invocation_type,
        Payload=json.dumps(payload).encode("utf-8"),
    )
    return response.get("ResponseMetadata", {}).get("RequestId", "")
