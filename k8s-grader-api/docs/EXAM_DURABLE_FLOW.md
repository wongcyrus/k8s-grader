# Exam Durable Flow

**Last Updated:** July 22, 2026

This document describes the current exam-mode architecture, the end-to-end action flow, the state transitions, and the runtime issues that were fixed during the Lambda durable-function refactor.

The goal is to let you review whether the implementation matches the intended exam behavior.

---

## 1. Scope

This document covers the exam-specific path only:

- exam web UI
- exam WebSocket handler
- durable exam command Lambda
- exam authorization/session checks
- task state transitions in exam mode
- WebSocket push updates back to the browser

It does **not** describe the normal non-exam `/task` flow in detail.

---

## 2. Main Components

### Frontend

- exam website hosted from S3 and served through CloudFront
- browser opens a WebSocket connection to the exam WebSocket API
- browser sends actions:
  - `subscribe`
  - `start`
  - `reset`
  - `run`
  - `status`
  - `records`

### `exam-ws-handler/app.py`

Responsibilities:

- validate WebSocket connection setup
- store connection metadata in `ExamWsConnectionTable`
- resolve `connection_id -> email/exam_code/game/task`
- forward exam actions to the durable function through `invoke_durable_function(...)`
- send an initial state snapshot on subscribe

### `exam-durable-handler/app.py`

Responsibilities:

- durable entrypoint for exam commands
- run one durable step per requested action
- load and validate exam state
- start/reset/run/status/records behavior
- push status responses back to matching WebSocket connections

### Supporting services

- `ExamService`
  - verifies exam code
  - authorizes task access
  - ensures exam-mode task state exists
  - runs phase execution through `TaskService`
- `TaskService`
  - starts tasks
  - executes phases
  - completes or abandons tasks
- `TaskStateMachine`
  - determines next legal action
  - enforces phase ordering and completion logic

---

## 3. Data Used by Exam Flow

### `ExamWsConnectionTable`

Stores active WebSocket subscriptions:

- `connection_id`
- `email`
- `scope = exam_code#game#task`
- `exam_code`
- `game`
- `task`
- `connected_at`

This lets the durable Lambda push updates to exactly the browser tab(s) watching one exam task.

### `ExamCodeTable`

Stores exam-code configuration, including:

- status
- allowed game
- allowed tasks
- start/end time window
- max attempts

### `ExamSessionTable`

Stores verified exam sessions per user and exam code.

### `TaskStateTable`

Stores actual task progress for the exam task:

- task status
- current phase
- per-phase attempt data
- session data
- total points
- exam metadata

### `TestRecordTable`

Stores phase execution records for exam history / records view.

### `AccountTable`

Stores the student Kubernetes endpoint and client credentials used during `start`, `reset`, and `run`.

---

## 4. High-Level Request Flow

```text
Browser
  -> WebSocket API
    -> exam-ws-handler
      -> invoke_durable_function(...)
        -> exam-command-durable:live
          -> ExamService / TaskService / TaskStateMachine
            -> DynamoDB + S3 + pytest/game source flow
          -> broadcast result to WebSocket connection(s)
            -> Browser
```

---

## 5. WebSocket Flow

## 5.1 Connect

The browser connects using:

```text
wss://pag62vjtb7.execute-api.us-east-1.amazonaws.com/Prod?apiKey=...&examCode=...&game=...&task=...
```

`$connect` behavior:

1. reads `apiKey`, `examCode`, `game`, `task` from query string
2. decrypts the API key to get the email
3. stores the connection row in `ExamWsConnectionTable`
4. returns `CONNECTED`

At this stage it does **not** run the task. It only registers the connection.

## 5.2 Subscribe

The browser then sends:

```json
{"action":"subscribe","apiKey":"...","examCode":"...","game":"...","task":"..."}
```

Behavior:

1. stores or refreshes the connection metadata
2. loads current `TaskStateTable` item for `email + game#task`
3. sends a snapshot message back

Snapshot result:

- if no state exists:
  - `NOT_STARTED`
- if state exists:
  - current task status
  - current phase
  - total points

This is why the UI can reconnect and still recover current status.

## 5.3 Action messages

For actions in:

- `start`
- `reset`
- `run`
- `status`
- `records`

the WebSocket handler:

1. looks up the stored connection
2. builds a durable payload:

```json
{
  "action": "...",
  "email": "...",
  "exam_code": "...",
  "game": "...",
  "task_id": "..."
}
```

3. invokes the qualified durable function alias asynchronously
4. returns immediate WebSocket response:

```json
{"status":"QUEUED","action":"run"}
```

The actual result comes later via WebSocket push from the durable Lambda.

---

## 6. Durable Handler Flow

Entry point:

- `@durable_execution`
- normal handler name: `app.lambda_handler`
- one durable `context.step(...)` call per action

Current action routing:

- `start` -> `handle_exam_start(...)`
- `reset` -> `handle_exam_reset(...)`
- `run` -> `handle_exam_run(...)`
- `status` -> `handle_exam_status(...)`
- `records` -> `handle_exam_records(...)`

Important implementation rule:

- the durable step now wraps a **plain helper result**
- it does **not** nest one durable step inside another

That change was required because nested durable-step objects were not serializable by the AWS durable SDK.

---

## 7. Exam Logic by Action

## 7.1 `start`

Purpose:

- validate that the student is allowed to work on this exam task
- attach K8s credentials into task session data
- create the task if needed
- return the starting phase information

Detailed flow:

1. validate `game` and `task_id`
2. `ExamService.authorize(...)`
   - exam code exists
   - exam code is active
   - game matches exam scope
   - verified exam session exists
   - task is allowed for the session
   - game is in exam mode
3. load user K8s account from `AccountTable`
4. validate client certificate, key, and endpoint
5. clear managed `/tmp` files
6. write user cert/key files to `/tmp`
7. load `TaskManifest`
8. ensure task state exists in exam mode
9. if previous state was `ABANDONED`, recreate from scratch
10. inject runtime session values:
    - `$endpoint`
    - `$client_certificate`
    - `$client_key`
    - `$email`
    - `$exam_code`
11. save state
12. return:
    - `STARTED`, or
    - `COMPLETED` if already completed
13. broadcast the result to matching WebSocket subscribers

## 7.2 `reset`

Purpose:

- explicitly restart the current exam task from phase 1

Allowed only when:

- task exists
- task is `IN_PROGRESS` or `ABANDONED`
- task is **not** `COMPLETED`

Detailed flow:

1. authorize exam scope
2. load existing task state
3. reject if not started
4. reject if already completed
5. reload K8s credentials
6. clear `/tmp`
7. delete existing task state
8. recreate exam task from scratch
9. restore session runtime data
10. return `STARTED` response with an extra reset note
11. broadcast to WebSocket subscribers

Important behavior:

- reset clears current state
- records history remains in `TestRecordTable`

## 7.3 `run`

Purpose:

- execute the next legal exam phase

Detailed flow:

1. authorize exam scope
2. load current task state
3. reject if task not started
4. load manifest
5. use `TaskStateMachine.get_next_action()`

Possible branches:

### Branch A: `complete_task`

- complete the task immediately
- return `COMPLETED`

### Branch B: `max_attempts_reached`

- abandon the task
- return `ABANDONED`

### Branch C: `execute_phase` or `retry_phase`

1. reload K8s credentials
2. clear `/tmp`
3. write cert/key files
4. update runtime session data
5. save state
6. run phase via `ExamService.run_phase(...)`
7. if there is a test result:
   - save a record to `TestRecordTable`
8. if phase execution failed:
   - if max attempts now reached -> `ABANDONED`
   - else -> `FAILED`
9. if phase execution succeeded:
   - if task can now complete -> `COMPLETED`
   - else -> `OK` with next-phase information
10. broadcast result

This is the main grading path.

## 7.4 `status`

Purpose:

- return current task state and next expected action without mutating progress

Returns:

- current serialized state
- manifest
- rendered task description
- next action from state machine
- allowed task list for the exam session

This is the best endpoint for reviewing whether the UI and state machine agree on the current stage.

## 7.5 `records`

Purpose:

- return saved test history for the student and exam code

Source:

- `TestRecordTable`

Result is also broadcast over WebSocket when `game` and `task` are present.

---

## 8. Exam State Model

Task status values relevant to exam flow:

- `NOT_STARTED`
- `IN_PROGRESS`
- `COMPLETED`
- `ABANDONED`

Practical meaning:

- `NOT_STARTED`
  - no usable task progress yet
- `IN_PROGRESS`
  - student may continue working
- `COMPLETED`
  - task is finished; reset is blocked
- `ABANDONED`
  - max attempts reached; `start` recreates only after explicit reset/start path logic

Phase-level behavior is still driven by the generic task state machine.

---

## 9. Browser-Visible Message Pattern

The durable handler broadcasts:

```json
{
  "type": "exam_status",
  "source_action": "run",
  "data": { ...action-specific response body... }
}
```

This means the browser receives:

- the action source (`start`, `run`, `status`, etc.)
- the current logical payload

So the UI can distinguish:

- queued command acknowledgement from WebSocket handler
- final durable result from durable handler

---

## 10. Runtime Issues Found During Refactor

## 10.1 Old issue: `elapsed_delta` / `timedelta` crash

Observed error:

```text
TypeError: Object of type timedelta is not JSON serializable
when serializing dict item 'elapsed_delta'
```

Root cause:

- importing the full exam durable path caused the global Python log-record factory to become `cmdkit.logging.LogRecord`
- that custom record added:
  - `elapsed`
  - `elapsed_delta`
  - `elapsed_hms`
  - `elapsed_ms`
- AWS Lambda JSON logging could not serialize the injected `timedelta`

Fix:

- explicitly reset the log-record factory in `exam-durable-handler/app.py`

```python
logging.setLogRecordFactory(logging.LogRecord)
```

## 10.2 Old issue: nested durable-step serialization

Observed error:

```text
Serialization failed ... Unsupported type: <class 'function'>
```

Root cause:

- the handler used one durable step that called another decorated durable step helper
- the AWS durable SDK attempted to serialize an internal function-like durable-step object

Fix:

- use one durable step wrapper only
- keep `execute_exam_command(...)` as a plain helper

## 10.3 Hardening change: lazy initialization

The durable handler now avoids heavy top-level initialization:

- `TaskService()` is lazy
- `ExamService()` is lazy
- `boto3.resource("dynamodb")` is lazy
- `common.session` no longer imports `common.pytest` at module import time

This reduces Lambda init-time side effects and makes runtime failures easier to isolate.

---

## 11. Current Review Checklist

Use this to decide whether the logic is right:

1. **WebSocket connect**
   - does every browser tab register `email + exam_code + game + task` correctly?
2. **Subscribe snapshot**
   - should reconnect always show current task state immediately?  
   - current code: **yes**
3. **Start rules**
   - should `start` require verified exam code and saved K8s account?  
   - current code: **yes**
4. **Reset rules**
   - should completed tasks be non-resettable?  
   - current code: **yes**
5. **Run rules**
   - should next action be entirely state-machine driven?  
   - current code: **yes**
6. **Attempt exhaustion**
   - should max attempts move the task to `ABANDONED`?  
   - current code: **yes**
7. **Records history**
   - should reset preserve historical records?  
   - current code: **yes**
8. **WebSocket updates**
   - should durable results always be pushed back to all matching subscribers?  
   - current code: **yes**, by `email + exam_code + game + task` scope

---

## 12. Current Live Entry Points

### Exam website

```text
https://d3kg66ckvfzhtl.cloudfront.net
```

### WebSocket template

```text
wss://pag62vjtb7.execute-api.us-east-1.amazonaws.com/Prod?apiKey=YOUR_API_KEY&examCode=YOUR_EXAM_CODE&game=YOUR_GAME&task=YOUR_TASK
```

### Durable Lambda alias

```text
arn:aws:lambda:us-east-1:111964674713:function:k8s-grader-api-dev-exam-command-durable:live
```

---

## 13. Files to Review

Primary files:

- `exam-ws-handler/app.py`
- `exam-durable-handler/app.py`
- `common-layer/common/services/exam_service.py`
- `common-layer/common/services/task_service.py`
- `common-layer/common/state_machine/task_state_machine.py`
- `template.yaml`

Helpful related files:

- `common-layer/common/durable_invoker.py`
- `tests/test_exam_ws_handler.py`
- `tests/test_exam_durable_handler.py`
- `tests/test_durable_invoker.py`

