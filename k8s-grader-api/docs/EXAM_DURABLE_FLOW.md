# Exam Durable Flow

**Last Updated:** November 4, 2026

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

It does **not** describe the removed legacy game `/task` flow; game mode now uses its own WebSocket durable path.

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
- browser does **not** store task/question text in browser storage
- on reconnect/refresh, browser restores exam context and auto-requests `status`
- disables conflicting submissions, question selection, and account/form changes while an exam command is pending
- reconnecting or waiting for a response does not cancel backend execution

### `exam-ws-handler/app.py`

Responsibilities:

- validate WebSocket connection setup
- store connection metadata in `ExamWsConnectionTable`
- resolve `connection_id -> email/exam_code/game/task`
- forward exam actions to the durable function through `invoke_durable_function(...)`
- send an initial state snapshot on subscribe
- acquire a shared execution lease before queueing `start`, `run`, or `reset`
- return active execution metadata for busy requests and status checks

### `exam-durable-handler/app.py`

Responsibilities:

- durable entrypoint for exam commands
- run one durable step per requested action
- load and validate exam state
- start/reset/run/status/records behavior
- push status responses back to matching WebSocket connections
- retain the execution lease through phase execution and automatic cleanup
- release the owned lease before broadcasting the terminal command response

### Supporting services

- `ExamService`
  - verifies exam code
  - authorizes task access
  - ensures exam-mode task state exists
  - runs phase execution through `TaskService`
- `TaskService`
  - starts tasks
  - executes phases
- `ExamExecutionGuard` (`common/exam_execution.py`)
  - serializes exam mutations across questions and exam codes for one student/game
  - uses conditional writes and ownership-safe release
- exam durable handler's `finish_exam_task(...)`
  - runs automatic cleanup before completing or abandoning an exam task
  - keeps cleanup failures retryable without changing the shared game completion path
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

Current behavior:

- records are saved per phase execution
- the exam UI records view is filtered by the current `task_id`
- auto-chained `setup -> ready` saves separate records for both phases when both execute in one `run`

### `WebSocketExecutionGuardTable`

Exam commands use the key `exam#<email>#<game>#mutation`. The key deliberately
excludes task, exam code, and action, so another question, exam code, browser tab,
or REST request cannot start a conflicting exam mutation for that student/game.

Each lease records `execution_id`, `command_request_id`, task, exam code, action,
phase, start time, and `expires_at`. Reads are strongly consistent; acquisition
is conditional, and release requires the matching `execution_id`. An expired
owner cannot remove a newer owner's lease.

The lease lasts 3,660 seconds, longer than the durable function's configured
3,600-second execution timeout, and is renewed when execution starts and phase
progress is published. Normal completion releases it immediately; expiry is
fallback recovery, not a browser response timeout.

Game commands retain their existing `game#...#mutation` keys and behavior.

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
2. checks for an active student/game execution lease
3. sends `RUNNING` with `active_execution` if a command is active; otherwise reads the selected task state and sends its snapshot

Snapshot result:

- if an execution is active:
  - its task, action, execution ID, and current phase, even when it belongs to another question
- if no state exists:
  - `NOT_STARTED`
- if state exists:
  - current task status
  - current phase
  - total points

The browser also requests full `status` to restore the rendered question,
scores, and available tasks; these are not part of the initial snapshot.

## 5.3 Action messages

For actions in:

- `start`
- `reset`
- `run`
- `status`
- `records`

the WebSocket handler:

1. looks up the stored connection
2. returns active execution metadata immediately for `status` or `records` when a command is running
3. applies the action cooldown
4. acquires the shared lease for `start`, `run`, or `reset`; a conflict returns `BUSY` with `active_execution` instead of queueing another command
5. pushes `QUEUED` with the acquired lease to the submitting connection, then builds a durable payload:

```json
{
  "action": "...",
  "email": "...",
  "exam_code": "...",
  "game": "...",
  "task_id": "...",
  "execution_id": "...",
  "status_request_id": "..."
}
```

6. invokes the qualified durable function alias asynchronously
7. returns the invocation acknowledgement:

```json
{"status":"QUEUED","action":"run","request_id":"..."}
```

The actual result comes later via WebSocket push from the durable Lambda.

The browser supplies `command_request_id` on mutation requests. The gateway
stores it in the lease; the server-generated `execution_id` identifies the lease
owner. `status_request_id` correlates a status response with the browser's
current restore request.

## 5.4 Conflicting actions and REST requests

- Start, Run, and Reset share one lease, not separate per-action or per-task locks.
- The lease covers queueing, setup, chained readiness checks, grading, and automatic cleanup.
- Cooldowns remain separate; passing a cooldown does not mean an execution has finished.
- Synchronous `/exam/start`, `/exam/run`, and `/exam/reset` use the same guard.
- Asynchronous REST Run acquires the lease before queueing and passes ownership to the durable worker.
- Status/overview reads used by the exam handlers do not persist point normalization or advance phases, so polling cannot overwrite a running task's saved state.

## 5.5 Browser recovery

The browser locks mutation buttons, task selection, account inputs, exam
verification, and saved-form reset as soon as it submits a mutation. It also
locks controls while restoring task state. Reconnect remains available when
disconnected.

While a command is pending, the browser checks status every three seconds.
It waits for an outstanding status response instead of replacing it each tick;
after 30 seconds it retries reconciliation **without unlocking the task**.
Socket closure, generic errors, rejected duplicates, and stale responses do
not establish that execution has stopped.

Controls unlock only after a matching terminal command result or a correlated
status response confirming no active execution. Late messages from previous
sockets or completed executions cannot regress the current task. Question
switching between idle, unfinished tasks remains allowed; this is an execution
lock, not a requirement to finish every question before browsing another one.

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
- mutations use `guarded_exam_command_step(...)`, which validates or acquires lease ownership, executes the command, releases the owned lease, and then broadcasts its result
- status uses `synchronized_exam_status_step(...)` to echo the browser's status request ID

That change was required because nested durable-step objects were not serializable by the AWS durable SDK.

---

## 7. Exam Logic by Action

## 7.1 `start`

Purpose:

- validate that the student is allowed to work on this exam task
- attach K8s credentials into task session data
- create the task if needed
- return the starting phase information

Start initializes task state; it does not execute setup tests. Run performs
setup and subsequent phases under the execution lease.

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
   - includes the extracted `/tmp/<game>` test tree, `/tmp/<game>.zip`, and `/tmp/<game>_source.txt`
   - this effectively removes stale task-local `__pycache__` content before Lambda test execution
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
- no conflicting exam command is executing for this student/game

Detailed flow:

1. authorize exam scope
2. load existing task state
3. reject if not started
4. reject if already completed
5. delete existing task state
6. return `RESET` response telling the student to click **Start**
7. broadcast to WebSocket subscribers after releasing the execution lease

Important behavior:

- reset clears current state
- records history remains in `TestRecordTable`
- reset does **not** auto-start the task again
- the next **Start** recreates the state with deterministic per-student `session_data`

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

- run automatic cleanup, if configured
- mark complete and return `COMPLETED` only after successful cleanup

### Branch B: `max_attempts_reached`

- run automatic cleanup, if configured
- mark abandoned and return `ABANDONED` only after successful cleanup

### Branch C: `execute_phase` or `retry_phase`

1. reload K8s credentials
2. clear `/tmp`
3. write cert/key files
4. update runtime session data
5. save state
6. run phase via `ExamService.run_phase(...)`
7. if the current exam phase is `answer`:
   - skip `test_03_answer.py`
   - silently advance to the next real grading phase
   - do not expose answer as a normal scoring step for students
8. if the executed phase was `setup` and it passed into `ready`:
   - automatically run `ready` in the same exam `run` request
   - save records for both `setup` and `ready`
   - return both phase results in `executed_phases`
9. if phase execution failed:
   - if max attempts now reached -> `ABANDONED`
   - else -> `FAILED`
10. if phase execution succeeded:
   - if task can now complete -> `COMPLETED`
   - else -> `OK` with next-phase information
11. if the task completed or was abandoned and manifest cleanup is `auto_run`:
   - cleanup is triggered automatically
12. broadcast result

This is the main grading path.

Important UX behavior:

- a single exam `run` now auto-chains `setup -> ready`
- exam mode awards points only for a passed `check` phase
- the browser response includes `executed_phases`, so the student can see both results
- `ready` failure stops the chain and leaves the task on `ready` for retry
- setup, readiness, grading, and cleanup progress messages retain `active_execution` and keep controls locked
- on automatic cleanup failure or exception, return `FAILED` with `cleanup_failed: true`, retain `IN_PROGRESS` at `cleanup`, and let Run retry cleanup
- a cleanup retry after attempt exhaustion preserves the original abandonment reason
- only successful completion/abandonment removes the task from `remaining_tasks`; automatic advancement waits for the finished command

## 7.4 `status`

Purpose:

- return current task state and next expected action without mutating progress

Returns:

- `RUNNING` with `active_execution` while an exam command is active
- otherwise, `active_execution: null` and:
- current serialized state
- manifest
- rendered task description
- next action from state machine
- allowed task list for the exam session
- exam overview fields such as `remaining_tasks`, `finished_tasks`, and `exam_score`

This is the best endpoint for reviewing whether the UI and state machine agree on the current stage.
It is also the browser-safe restore path after refresh because it does not consume attempts.

## 7.5 `records`

Purpose:

- return saved test history for the current student, exam code, and selected task

Source:

- `TestRecordTable`

Current behavior:

- records are filtered by `email + exam_code + current task_id`
- records are normalized before being sent back to the browser
- records are returned through the same WebSocket response path as other exam actions

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
- enough information to rebuild the visible question and scores after refresh

So the UI can distinguish:

- queued command acknowledgement from WebSocket handler
- `RUNNING` progress with `active_execution`, including during cleanup
- `BUSY` rejection without treating it as the active command's result
- final durable result from durable handler

Terminal mutation payloads include `task_id`, `execution_id`,
`command_request_id`, and `command_finished: true`. They also include the
current `active_execution` after release, normally `null`. Task status
`IN_PROGRESS` describes saved task progress; it is not proof that tests are
currently executing.

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
9. **Execution isolation**
   - duplicate Run and conflicting Start/Reset/other-question requests must not queue while an exam mutation owns the lease
   - reconnects, response timeouts, and rejected duplicates must not unlock an active execution
10. **Cleanup and advancement**
    - task selection stays locked through automatic cleanup
    - cleanup failure remains retryable and is not reported as completion
    - successful completion still restores the next question without stale state

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

- `../exam-web/exam.js`
- `exam-ws-handler/app.py`
- `exam-durable-handler/app.py`
- `common-layer/common/exam_execution.py`
- `common-layer/common/services/exam_service.py`
- `common-layer/common/services/task_service.py`
- `common-layer/common/state_machine/task_state_machine.py`
- `template.yaml`

Helpful related files:

- `common-layer/common/durable_invoker.py`
- `tests/test_exam_ws_handler.py`
- `tests/test_exam_durable_handler.py`
- `tests/test_exam_execution.py`
- `tests/test_exam_web.mjs`
- `tests/test_task_handler.py`
- `tests/test_durable_invoker.py`
