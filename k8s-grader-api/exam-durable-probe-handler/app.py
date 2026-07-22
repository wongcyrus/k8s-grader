"""Minimal durable probe handler used to isolate runtime issues."""

from datetime import datetime, timezone
from typing import Any, Dict

from aws_durable_execution_sdk_python import DurableContext, durable_execution, durable_step


@durable_step
def probe_step(step_context, mode: str) -> Dict[str, Any]:
    step_context.logger.info("Running durable probe", extra={"mode": mode})
    if mode == "fail":
        raise RuntimeError("intentional durable probe failure")

    return {
        "status": "ok",
        "mode": mode,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@durable_execution
def lambda_handler(event: Dict[str, Any], context: DurableContext) -> Dict[str, Any]:
    payload = event if isinstance(event, dict) else {}
    mode = payload.get("mode", "ok")
    return context.step(probe_step(mode))
