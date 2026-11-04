"""Exam-only execution leases shared across questions and mutation actions."""
import json
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr

from common.database import ExecutionGuardRepository


EXAM_MUTATIONS = {"start", "run", "reset"}
# Longer than the exam durable function's 3600-second execution timeout.
EXAM_EXECUTION_TTL_SECONDS = 3660
current_exam_execution = ContextVar("current_exam_execution", default=None)


class ExamExecutionGuard:
    def __init__(self):
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = ExecutionGuardRepository().table
        return self._table

    @staticmethod
    def scope(email, game):
        return f"exam#{email}#{game}#mutation"

    def get_active(self, email, game):
        item = self.table.get_item(
            Key={"scope_key": self.scope(email, game)}, ConsistentRead=True
        ).get("Item")
        if item and int(item["expires_at"]) > int(time.time()):
            return item
        return None

    def acquire(self, email, game, exam_code, task_id, action, command_request_id=""):
        now = int(time.time())
        item = {
            "scope_key": self.scope(email, game),
            "email": email,
            "game": game,
            "exam_code": exam_code,
            "task_id": task_id,
            "action": action,
            "execution_id": uuid.uuid4().hex,
            "command_request_id": command_request_id,
            "status": "RUNNING",
            "phase": action,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": now + EXAM_EXECUTION_TTL_SECONDS,
        }
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression=Attr("scope_key").not_exists()
                | Attr("expires_at").lte(now),
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return None
        return item

    def release(self, scope_key, execution_id):
        try:
            self.table.delete_item(
                Key={"scope_key": scope_key},
                ConditionExpression=Attr("execution_id").eq(execution_id),
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def set_phase(self, execution, phase):
        expires_at = int(time.time()) + EXAM_EXECUTION_TTL_SECONDS
        self.table.update_item(
            Key={"scope_key": execution["scope_key"]},
            UpdateExpression="SET #phase = :phase, expires_at = :expires_at",
            ExpressionAttributeNames={"#phase": "phase"},
            ExpressionAttributeValues={":phase": phase, ":expires_at": expires_at},
            ConditionExpression=Attr("execution_id").eq(execution["execution_id"]),
        )
        execution["phase"] = phase
        execution["expires_at"] = expires_at

    def busy_payload(self, email, game):
        return {
            "status": "BUSY",
            "message": (
                "An exam task is already running. "
                "Wait for setup, testing, and cleanup to finish."
            ),
            "active_execution": self.get_active(email, game),
        }

    def busy_response(self, email, game):
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
            "body": json.dumps(self.busy_payload(email, game), default=int),
        }

    def execute(
        self, action, email, exam_code, game, task_id, callback, execution_id=""
    ):
        if execution_id:
            execution = self.get_active(email, game)
            if not execution or (
                execution["execution_id"],
                execution["exam_code"],
                execution["task_id"],
                execution["action"],
            ) != (execution_id, exam_code, task_id, action):
                return self.busy_response(email, game)
        else:
            execution = self.acquire(email, game, exam_code, task_id, action)
            if not execution:
                return self.busy_response(email, game)

        token = current_exam_execution.set(execution)
        try:
            self.set_phase(execution, action)
            response = callback()
        finally:
            current_exam_execution.reset(token)
            self.release(execution["scope_key"], execution["execution_id"])

        payload = json.loads(response["body"])
        payload.update(
            task_id=task_id,
            execution_id=execution["execution_id"],
            command_request_id=execution.get("command_request_id", ""),
            command_finished=True,
            active_execution=self.get_active(email, game),
        )
        response["body"] = json.dumps(payload, default=int)
        return response
