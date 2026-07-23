# Game Logic Guide

## Overview

Game mode now uses a **WebSocket-only durable flow**. The RPG client sends `talk` and `status` actions over the game WebSocket API, the backend queues a durable Lambda invocation, and the durable worker pushes live task updates back to the same browser connection.

This is different from the older REST-style game flow:

- the client must have `wsUrl` in the page URL
- task progression is streamed over WebSocket
- game mode uses the same saved Kubernetes account data as exam mode
- RPG mode does **not** abandon a task after repeated failures

## Current End-to-End Flow

1. The RPG page loads with `wsUrl`, `apiKey`, and `game`.
2. `NpcK8sPluginCommand.js` opens the game WebSocket and sends `subscribe`.
3. When the player talks to an NPC, the plugin sends:

   ```json
   {
     "action": "talk",
     "apiKey": "...",
     "game": "game01",
     "npc": "Stella"
   }
   ```

4. `game-ws-handler/app.py` validates the request and queues the durable game command Lambda.
5. `game-command-handler/app.py` starts or resumes the current task, runs task phases, and pushes `game_status` updates back over WebSocket.
6. The RPG plugin converts backend statuses into player-facing text and shows reports in a popup when available.

## Durable Game Rules

The durable game worker follows these rules:

- **Task-first talk flow**: talking to an NPC runs or resumes the assigned task flow instead of falling back to flavor chat.
- **Shared account source**: game mode reads the player's Kubernetes credentials from the same `AccountTable` used by exam mode.
- **Answer phase is skipped**: if a task reaches `answer`, the worker marks it passed with 0 points and advances to the next real grading phase.
- **Challenge before check**: if saved state lands on `check` before `challenge` has passed, the worker rewinds back to `challenge`.
- **No RPG lockout on failures**: game mode keeps returning normal `FAILED` results; it does not abandon the task when attempts reach `max_attempts`.
- **Durable multi-phase progression**: one `talk` can advance through multiple phases until the player hits a failing phase or completes the task.

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

`NpcK8sPluginCommand.js` rewrites the most important backend errors into player-facing text:

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

## Important Files

- `game-ws-handler/app.py` - queues durable game commands from WebSocket actions
- `game-command-handler/app.py` - durable task runner for RPG game mode
- `tests/test_game_ws_handler.py` - WebSocket handler regression coverage
- `tests/test_game_command_handler.py` - durable game-flow regression coverage
- `k8s-isekai/js/plugins/NpcK8sPluginCommand.js` - RPG Maker WebSocket client and player-facing message mapping
