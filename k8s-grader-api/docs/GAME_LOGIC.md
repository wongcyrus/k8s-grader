# Game Logic Guide

## Overview

Game mode now uses a **WebSocket-only durable flow**. The RPG client sends `talk` and `status` actions over the game WebSocket API, the backend queues a durable Lambda invocation, and the durable worker pushes live task updates back to the same browser connection.

This is different from the older REST-style game flow:

- the client must know the game WebSocket URL, either from the exercise portal's saved same-origin state or from a direct `wsUrl` page parameter
- task progression is streamed over WebSocket
- game mode uses the same saved Kubernetes account data as exam mode
- RPG mode does **not** abandon a task after repeated failures

## Current End-to-End Flow

1. The student opens the **exercise portal** (`index.html`), saves their API key and Kubernetes login, and launches the RPG page on the same origin.
2. The RPG page loads `game` from the page URL or shared exercise-portal state, and reads `apiKey` plus `wsUrl` from same-origin localStorage when they are not present in the URL.
3. `NpcK8sPluginCommand.js` opens the game WebSocket and sends `subscribe`.
4. When the player talks to an NPC, the plugin sends:

   ```json
   {
     "action": "talk",
     "apiKey": "...",
     "game": "game01",
     "npc": "Stella"
   }
   ```

5. `game-ws-handler/app.py` validates the request and queues the durable game command Lambda.
6. `game-command-handler/app.py` starts or resumes the current task, runs task phases, and pushes `game_status` updates back over WebSocket.
7. The RPG plugin shows player-facing text from the backend and opens reports in a popup when available.

## Durable Game Rules

The durable game worker follows these rules:

- **Task-first talk flow**: talking to an NPC runs or resumes the assigned task flow instead of falling back to flavor chat.
- **Shared account source**: game mode reads the player's Kubernetes credentials from the same `AccountTable` used by exam mode.
- **Answer phase is skipped**: if a task reaches `answer`, the worker marks it passed with 0 points and advances to the next real grading phase.
- **Challenge before check**: if saved state lands on `check` before `challenge` has passed, the worker rewinds back to `challenge`.
- **No RPG lockout on failures**: game mode keeps returning normal `FAILED` results; it does not abandon the task when attempts reach `max_attempts`.
- **Durable multi-phase progression**: one `talk` can advance through multiple phases until the player hits a failing phase or completes the task.
- **Doom Client Integration (`DOOM_TASK_SOURCE`)**:
  - Uses `npc = "doom"` to bypass RPG NPC background checks and single-NPC assignment locks.
  - Bypasses attempt count tracking (`_counts_attempts`), enabling infinite in-game retries.
  - Renders Jinja2 session variables (e.g. `{{ namespace }}`) in `_build_game_status_payload` for `NOT_STARTED` tasks so task instructions display filled parameters before execution starts.

## Player-Facing Message Truth Table

The RPG plugin intentionally hides backend jargon like raw phase/status combinations and instead shows what the player should do next.

| Backend payload | What the player sees | Meaning |
| --- | --- | --- |
| `STARTED` | current instruction | The task just started. |
| `RUNNING` | current instruction | Keep working on the current task. |
| `FAILED` + `task_description` | `No mark yet. <instruction> Try again.` | The task was checked and did not pass yet. |
| `FAILED` without instruction | backend message or `No mark yet. Try again.` | The player needs another attempt. |
| `OK` + `task_description` | next instruction | The current step passed and the player can continue. |
| `COMPLETED` | completion message | All tasks are finished. |
| `ERROR` | mapped player-safe error text | The player needs to fix setup or follow the correct NPC/task order. |

## Error Message Mapping

Player-facing errors are normalized in Python before they reach the RPG client. `NpcK8sPluginCommand.js` displays those backend-safe `ERROR` messages directly:

| Backend error | Player-facing text |
| --- | --- |
| `Aiden does not have any task for you!` | `Aiden has no task for you right now.` |
| `Complete task from Stella first!` | `Finish your task from Stella first.` |
| `User account not found` | `Please save your Kubernetes account first.` |
| `K8s credentials missing or incomplete` | `Your Kubernetes account details are incomplete. Please save them again.` |

The plugin does **not** tell the player to try another NPC unless the backend literally returns that meaning.

## Reports and Retries

- Failed checks can include a `report_url`; the plugin opens the report popup automatically.
- Success payloads can include an `easter_egg_url`; the plugin opens it after success.
- Resetting DynamoDB task state only resets app-side progress. If the Kubernetes cluster still contains the required resources, early phases may pass again immediately on the next run.

## Debugging Skipped Tests & Immediate Failures

If a test appears to skip Pytest execution and immediately returns a failure:

1. **Prerequisite Phase Unpassed**: If `can_execute_phase()` fails (e.g., previous required phase like `setup` has not passed), test execution is skipped and `_phase_failed_payload` returns `❌ Phase Blocked: Must complete phase 'setup' first`.
2. **Duplicate Execution Lock**: If another test is actively running in the background, `game-ws-handler` returns `A test execution is already in progress. Please wait for it to finish.`.
3. **Action Rate Limit**: If `talk` triggers occur within 2 seconds, `game-ws-handler` returns `Please wait a moment before trying again.`.

## Important Files

- `game-ws-handler/app.py` - queues durable game commands from WebSocket actions
- `game-command-handler/app.py` - durable task runner for RPG game mode
- `tests/test_game_ws_handler.py` - WebSocket handler regression coverage
- `tests/test_game_command_handler.py` - durable game-flow regression coverage
- `k8s-isekai/js/plugins/NpcK8sPluginCommand.js` - RPG Maker WebSocket client and player-facing message mapping
