# Exam Page User Guide

This guide covers the student **Exam Page** (`exam.html`), not the RPG Exercise
Portal or teacher dashboard. Use the portal URL supplied by your instructor.

## Before you begin

Have your API key, exam code, Kubernetes login, and a terminal with `kubectl`
ready. Use your own assigned cluster; the service rejects an endpoint already
registered to another account.

Keep one exam tab open. Do not run RPG exercises, another game, or another
person's tasks against the same cluster concurrently. The exam lock protects
exam questions for your account and game; it is not a cluster-wide or
cross-portal lock.

**The normal sequence is:**

```text
Submit Kubernetes Login -> Open Exam Access -> wait for Connected
  -> select Task -> Start question -> wait for Your turn
  -> work in Kubernetes -> Submit answer -> wait for assessment and cleanup
  -> next question, or the exam completion report
```

## 1. Enter your API key and Kubernetes login

The **API Key** identifies your platform account. It is not your Kubernetes
token and is not your exam code.

Choose one Kubernetes login method:

| Input | What to provide |
| --- | --- |
| **Kubeconfig (Recommended)** | Paste YAML into **Kubeconfig YAML**, or select a `.yaml`, `.yml`, or `.conf` file. |
| **Kubeconfig YAML** and **Kubeconfig file** together | Avoid filling both: a non-empty uploaded file takes precedence over pasted YAML. Clear the file selection if you want to use pasted YAML instead. |
| **Manual Endpoint + Cert** | Enter the Kubernetes API **Endpoint**, normally `https://host:6443`, and select the client certificate and matching private key files supplied for your cluster. |
| **Client Certificate** / **Client Key** | Supply both together, never just one. The browser accepts `.crt`, `.pem`, or `.cer` certificates and `.key` or `.pem` keys. |

The manual form also allows both certificate inputs to be empty for legacy
compatibility. Do not rely on endpoint-only access unless your instructor
explicitly provides that setup; a successful health probe does not establish
permission to create or grade resources.

Use a self-contained kubeconfig with a token or embedded
`client-certificate-data` and `client-key-data`. External certificate/key file
paths and `exec` login plugins are not supported. If the file contains multiple
contexts, it must select the intended `current-context`. Ask your instructor for
a supported kubeconfig rather than uploading a cloud CLI-dependent login file.

Click **Submit Kubernetes Login**. The service parses the credentials and probes
the Kubernetes endpoint before saving them. Wait for `status: OK` in **Exam
Setup Result**. This saves cluster access; it does **not** prepare a question.
The saved Kubernetes account is shared with the platform's Game flow.

Changing the login method, kubeconfig, endpoint, certificate, or key makes
**Open Exam Access** unavailable until you submit the login successfully again.
After changing the API key, also resubmit the Kubernetes login for that account.

## 2. Open exam access and select a question

Enter the instructor's **Exam Code**, then click **Open Exam Access**. The server
checks the code and its opening window and returns the permitted game and tasks.
Errors appear in **Exam Response**; account-submission results appear separately
in **Exam Setup Result**.

After verification:

1. **Verified Exam Scope** appears. **Game** is assigned by the exam code; it is
   not an editable choice.
2. Wait for **Connection: Connected** and for **Restoring task state from the
   server...** to finish.
3. Choose a question from **Task**, if selection is available. Changing it
   reconnects the exam session to that question and restores its server state;
   it does not start the question.

Typing a different API key or exam code does not, by itself, switch an existing
exam connection. When no question owns the environment, submit the login again
if changing accounts, then click **Open Exam Access** for the intended code.

## 3. Start, solve, and submit a question

Click **Start question** once. It reserves your environment for this question
and runs preparation: `setup` creates resources, then `ready` checks readiness
when that phase exists. Wait until **Stage: Your turn**.

Read **Question** and make the required changes in your own Kubernetes terminal.
Use the namespace, names, and requirements shown for your question.

**Submit answer is not a text or file upload.** It tests the current state of
your Kubernetes cluster. Do not paste an answer into the kubeconfig field.

When your work is ready, click **Submit answer** once. Assessment runs
`challenge -> check` when both phases exist; otherwise it runs the applicable
assessment phase. A challenge can deliberately change cluster resources to
test their behavior. Do not keep changing the cluster during assessment.

The development/reference-solution `answer` phase is not a student step and
does not deploy the solution for you.

## 4. Understand the stage and action

Follow **Stage**, its explanation, and **Next step** together. Questions can omit
optional phases; you do not need to click once for every internal phase.

| Stage | What is happening | What you should do |
| --- | --- | --- |
| **Not started** | No question environment has been prepared. | Select a question and click **Start question**. |
| **Preparing environment** | Resources are being created or checked for readiness. | Wait; do not submit or change questions. |
| **Preparation needed** | Preparation is incomplete or failed. | Read the response/report. Use **Prepare environment** or **Retry preparation**, as shown, after addressing the issue. |
| **Your turn** | Preparation finished, or assessment failed with attempts remaining. | Work in Kubernetes, then click **Submit answer**. |
| **Assessing your work** | Challenge/check is running. | Wait; do not submit again or edit the cluster. |
| **Cleaning up** | Question resources are being removed. | Wait even if the answer already passed. |
| **Cleanup needs attention** | Cleanup did not finish. | Read the error, then use **Retry cleanup**. The environment is still reserved. |
| **Finished** | The question completed and its environment was released. | Continue with a remaining question or review the final report. |
| **Attempts exhausted** | The question finished without a pass, after cleanup. | Continue with remaining questions; ask your instructor about any permitted retry. |

**Expected wait for this run**, **Task estimate**, and **Remaining task time** are
estimates, not countdown deadlines or permission to start a second request.

### Failed assessment

Read **Exam Response** and open the available test report. If attempts remain,
the stage returns to **Your turn**. Correct your cluster and submit again; you
do not need to start the question again. Where defined, the challenge runs again
before the next check.

**Attempts** is a phase counter, not a count of questions or necessarily a count
of button clicks. A single action may execute multiple phases, each with its
own result. Use the response's attempt limit rather than assuming a fixed number.

### Passed assessment or exhausted attempts

Allow cleanup to finish. A passing result or a displayed score does not by itself
mean that the environment has been released.

After the question finishes, it is removed from the remaining **Task** choices.
The page automatically selects/restores the next remaining question, but you
must click **Start question** to prepare it. If none remain, the page displays
**Exam completed**, the final exam score, and the per-question status/score
table. There is no separate whole-exam submit button.

Both completed and attempts-exhausted questions count as finished for this list.
The normal selector does not offer finished questions for restarting.

## 5. Leave a question before passing

The question owns your environment even while **Your turn** is idle. You cannot
select another task, change credentials or exam code, or reset saved form data
until that ownership is released.

To change questions before finishing:

1. Wait until the current operation has stopped and the connection is available.
2. Click **Leave question and clean up**.
3. Read the confirmation. Confirming removes the question's Kubernetes
   resources and clears its current progress after cleanup succeeds.
4. Wait for the response confirming the question was left. You may then select
   another question or start this one again.

Cancelling the confirmation does nothing. Leaving is **not a pause**: current
progress and task marks are reset, although saved attempt history is preserved.

If cleanup fails, the question remains reserved. Use **Retry cleanup** after
addressing the reported problem. A retry of leave-cleanup still finishes the
leave/reset operation; it does not turn it into a completed answer.
Cleanup retries do not rerun grading. Contact your instructor if credentials
expire or cleanup cannot succeed; do not try to bypass the lock with another tab.

## 6. Button reference

| Button | When to use it | Effect |
| --- | --- | --- |
| **Submit Kubernetes Login** | Before opening access; no operation or owned environment. | Saves/probes the chosen cluster login. Does not start a question. |
| **Open Exam Access** | After a successful login submission; no operation or owned environment. | Verifies the code, loads its scope, and connects to the selected task. |
| **Start question** | Selected question is not started; connected and restoration finished. | Reserves the environment and runs preparation only. |
| **Submit answer** | Your turn; connected and idle. | Grades the live cluster, then performs automatic cleanup when the question finishes. |
| **Prepare environment / Retry preparation** | Preparation needs attention; connected and idle. | Continues/retries preparation rather than grading your answer. |
| **Retry cleanup** | Cleanup needs attention; connected and idle. | Continues cleanup without repeating assessment. |
| **Leave question and clean up** | Current unfinished question; connected and idle. | After confirmation, cleans resources and resets current progress. Not available for a completed question. |
| **Attempt History** | Current started question, between operations. | Requests saved phase runs for the current task and exam code. Reconnect first if disconnected. |
| **Reconnect Exam** | Verified session shows disconnected. | Reconnects and restores authoritative server status. Does not start, retry, reset, or cancel a question. |
| **Reset Saved Form Data** | No operation or owned environment. | After confirmation, clears this exam page's browser state and closes its connection. Does not clean Kubernetes, erase server records, delete the saved Kubernetes account, or revoke the API key. |
| **Open test report / Open report** | A response or history entry provides a report. | Opens a report popup. Allow popups for this site if your browser blocks it. |

Buttons may be hidden until relevant, or disabled while a request or status
restore is pending. Disabled exam action buttons have tooltips explaining why. Rapid repeated
clicks can also show **Please wait a moment before clicking again**.

## 7. Scores and attempt history

**Task score** is the current question's mark; **Exam score** is the sum of the
question marks in this exam's scope. Exam points come from passed `check`
phases, not preparation, challenges, or cleanup.

**Attempt History** shows saved phase runs for the currently selected task and
exam code, including phase, result, time, and available report links. One submit
can produce multiple rows; rows are not all separate answer submissions.
After finishing advances the selector, the history button follows the new
question. It is not an all-exam archive browser, and all exam action buttons are
hidden when no tasks remain. Ask your instructor for records of finished
questions if needed.

## 8. Refreshing, reconnecting, and saved data

Refreshing or reopening the page normally restores the saved account/exam
context, reconnects, and requests server status automatically. Wait for that
restore before acting. An unfinished owning question can replace the cached
selection, including restoring its exam code.

If disconnected, click **Reconnect Exam**, then wait for **Connected** and the
restored stage. A server operation can continue while the browser is
disconnected. Reconnecting, refreshing, closing the page, navigating to another
portal page, or waiting past a time estimate does **not** cancel it or clean
resources.

This exam page stores the API key, endpoint, login-method choice, exam context,
and task selection in browser local storage. It does not persist the kubeconfig
textarea or selected credential-file contents there. The saved server login
can still be used after refresh even though those file inputs are empty.
If you edit/re-submit the login, supply the credentials again.

Use a trusted browser profile. **Reset Saved Form Data** clears this page's
cached values, not other portal pages' storage or server-side credentials.
It is not a way to leave an active question.

## 9. Troubleshooting

| What you see | What to do |
| --- | --- |
| **API Key is required** | Enter the platform API key before submitting login or exam actions. |
| **Open Exam Access** is disabled | Submit the Kubernetes login successfully. If a question already owns the environment, finish it or leave with cleanup first. |
| **Endpoint probe failed** | Check cluster availability, endpoint reachability from the grader, and the supplied credentials. Ask your instructor if unsure. |
| **Endpoint already exists, and no Sharing K8s cluster!** | Use your own assigned cluster, or ask your instructor to resolve an incorrect registration. |
| **Invalid exam code**, disabled/not-started/ended exam | Check the code with your instructor. Editing the input alone does not reopen access; use **Open Exam Access** when available. |
| **Restoring task state...**, `QUEUED`, `RUNNING`, or `BUSY` | Wait for server status. If disconnected, reconnect instead of resubmitting. Another tab may already have submitted the operation. |
| **Task** or credentials remain disabled during **Your turn** | This is intentional environment ownership. Submit your work or use **Leave question and clean up**. |
| History says the socket is still connecting | Reconnect and wait for status restoration before requesting history again. |
| Cleanup repeatedly fails or ownership cannot be released | Keep the question selected and contact your instructor with the stage/error and report, not your API key or credential files. |

## Control-logic trace

For instructors/maintainers, these are the implementation entry points behind
the instructions above:

Login and code verification use HTTP (`POST /save-k8s-account` and
`GET /exam/verify-code`). Question buttons send WebSocket actions: **Start
question** sends `start`, the submit/preparation/cleanup button sends `run`,
**Leave question and clean up** sends `reset`, and **Attempt History** sends
`records`. Reconnect opens a new socket and requests `status`; it does not
replay the last mutation.

| Behavior | Source and entry points |
| --- | --- |
| Visible inputs, panels, and button labels | [`exam.html`](../../exam-web/exam.html) |
| Input collection, local validation, login submission, exam verification, leave confirmation, and action dispatch | [`exam.js`](../../exam-web/exam.js): `readInputs`, `setAuthMethod`, `callApi` |
| Uploaded kubeconfig precedence and endpoint probe | [`save-k8s-account/app.py`](../save-k8s-account/app.py): `_kubeconfig_from_request`, `lambda_handler`, `probe_endpoint`; supported formats in [`common/kubeconfig.py`](../common-layer/common/kubeconfig.py): `parse_kubeconfig` |
| Visibility, disabling, environment ownership, and stage-specific button labels | `exam.js`: `updateExamButtons`, `getLifecycle`, `updateStateMachineUI`, task-change listener |
| Connection scope, status restoration, command correlation, and automatic next-task selection | `exam.js`: `connectExamSocket`, `sendExamActionViaSocket`, `refreshCurrentTaskStatus`, `showResponse`, `updateExamSummary`, `updateTaskOptions` |
| Server-side connection scope, snapshot, and durable-command dispatch | [`exam-ws-handler/app.py`](../exam-ws-handler/app.py): `_handle_connect`, `_send_state_snapshot`, `_handle_default` |
| Preparation/assessment pairs, retry, cleanup-first leave, and saved history | [`exam-durable-handler/app.py`](../exam-durable-handler/app.py): `handle_exam_start`, `handle_exam_run`, `finish_exam_task`, `finish_exam_reset`, `handle_exam_records` |
| Student-facing stage names | [`common/exam_lifecycle.py`](../common-layer/common/exam_lifecycle.py): `lifecycle_payload` |
| Exam ownership between commands | [`common/exam_execution.py`](../common-layer/common/exam_execution.py): `get_environment`, `claim_environment`, `release_environment` |
| Scores and removal of completed/abandoned questions | [`common/services/exam_service.py`](../common-layer/common/services/exam_service.py): `normalize_exam_points`, `get_exam_overview` |
| Local storage, reload, and local-only reset | `exam.js`: `saveState`, `loadState`, `resetStateButton` listener, final `restored` initialization |

See [Exam Durable Flow](EXAM_DURABLE_FLOW.md) for the backend architecture.
