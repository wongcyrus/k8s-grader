# Game Logic Guide

## Overview

The K8s Grader is a **gamified Kubernetes learning system** where players interact with NPCs (Non-Player Characters) to receive and complete Kubernetes challenges. This guide explains the complete game flow, state management, and player experience.

## Game Concepts

### Players
- **Identity**: Identified by email address
- **Progress**: Tracked per game (e.g., game01, game02)
- **Credentials**: Each player has unique K8s cluster credentials
- **Personalization**: Each player gets unique task parameters (prevents cheating)

### NPCs (Non-Player Characters)
- **Role**: Task givers and guides
- **Personality**: Each NPC has unique background and dialogue
- **Availability**: NPCs can be locked (cooldown) or assigned to tasks
- **Random Chat**: 30% chance of casual conversation before task

### Tasks
- **Structure**: Sequential challenges (01, 02, 03...)
- **Phases**: Each task has multiple test phases (setup, challenge, check, cleanup)
- **Points**: Players earn points for completing phases
- **Retry**: Limited attempts per phase (typically 3-5)

### Sessions
- **Personalization**: Each player gets unique resource names
- **Deterministic**: Same player always gets same values (seeded by email)
- **Isolation**: Prevents players from interfering with each other


## Complete Game Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PLAYER STARTS GAME                              │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  Register K8s Account  │
                    │  (Save credentials)    │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Generate API Key     │
                    │   (Encrypted email)    │
                    └────────────┬───────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────────┐
│                         MAIN GAME LOOP                                  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  1. Player talks to NPC                                          │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│              ┌────────────────────────────┐                            │
│              │  Random Chat? (30%)        │                            │
│              └────┬──────────────────┬────┘                            │
│                   │ Yes              │ No                              │
│                   ▼                  ▼                                  │
│          ┌────────────┐    ┌──────────────────┐                       │
│          │ Casual     │    │ Check NPC Status │                       │
│          │ Dialogue   │    └────────┬─────────┘                       │
│          └────────────┘             │                                  │
│                                     ▼                                  │
│                        ┌────────────────────────┐                     │
│                        │ NPC Available?         │                     │
│                        └──┬──────────────────┬──┘                     │
│                           │ No               │ Yes                    │
│                           ▼                  ▼                         │
│                  ┌─────────────────┐  ┌──────────────┐               │
│                  │ NPC Locked?     │  │ Get Current  │               │
│                  │ "Come back      │  │ Task         │               │
│                  │  later!"        │  └──────┬───────┘               │
│                  └─────────────────┘         │                        │
│                           │                  ▼                         │
│                           │      ┌───────────────────────┐            │
│                           │      │ Task Already Started? │            │
│                           │      └──┬────────────────┬───┘            │
│                           │         │ No             │ Yes            │
│                           │         ▼                ▼                 │
│                           │  ┌──────────────┐  ┌──────────────┐      │
│                           │  │ START TASK   │  │ CONTINUE     │      │
│                           │  │ (New state)  │  │ TASK         │      │
│                           │  └──────┬───────┘  └──────┬───────┘      │
│                           │         │                 │               │
│                           │         └────────┬────────┘               │
│                           │                  │                        │
│                           │                  ▼                         │
│                           │      ┌───────────────────────┐            │
│                           │      │ EXECUTE CURRENT PHASE │            │
│                           │      └──────────┬────────────┘            │
│                           │                 │                         │
│                           └─────────────────┴─────────────────┐       │
│                                                                │       │
└────────────────────────────────────────────────────────────────┼───────┘
                                                                 │
                                                                 ▼
                                                    (Continue to Phase Execution)
```


## Phase Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PHASE EXECUTION CYCLE                              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  1. Validate Phase Can Execute                                   │  │
│  │     - Task status = IN_PROGRESS?                                 │  │
│  │     - Current phase matches?                                     │  │
│  │     - Attempts < max_attempts?                                   │  │
│  │     - Prerequisites passed?                                      │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│              ┌────────────────────────────┐                            │
│              │  2. Inject K8s Credentials │                            │
│              │     - endpoint              │                            │
│              │     - client_certificate    │                            │
│              │     - client_key            │                            │
│              │     - email                 │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  3. Generate Session Data  │                            │
│              │     - random_name()         │                            │
│              │     - random_number()       │                            │
│              │     - student_id()          │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  4. Run Pytest Tests       │                            │
│              │     - Download game source │                            │
│              │     - Create json_input    │                            │
│              │     - Execute test file    │                            │
│              │     - Generate HTML report │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  5. Check Test Result      │                            │
│              └──┬──────────────────────┬──┘                            │
│                 │ PASSED               │ FAILED                        │
│                 ▼                      ▼                                │
│    ┌────────────────────┐   ┌──────────────────────┐                 │
│    │ Award Points       │   │ Increment Attempts   │                 │
│    │ Move to Next Phase │   │ Stay on Same Phase   │                 │
│    └────────┬───────────┘   └──────────┬───────────┘                 │
│             │                           │                              │
│             ▼                           ▼                              │
│    ┌────────────────────┐   ┌──────────────────────┐                 │
│    │ More Phases?       │   │ Max Attempts?        │                 │
│    └──┬──────────────┬──┘   └──┬────────────────┬──┘                 │
│       │ Yes          │ No      │ No             │ Yes                 │
│       ▼              ▼         ▼                ▼                      │
│  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌──────────────┐            │
│  │ Return  │  │ Complete │  │ Return │  │ ABANDON TASK │            │
│  │ "Next   │  │ Task     │  │ "Retry"│  │ Clear NPC    │            │
│  │ Phase"  │  │          │  │        │  │ Allow Retry  │            │
│  └─────────┘  └──────────┘  └────────┘  └──────────────┘            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```


## Task State Machine

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TASK LIFECYCLE                                  │
│                                                                         │
│                    ┌──────────────────┐                                │
│                    │  NOT_STARTED     │                                │
│                    │  (Initial state) │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             │ start_task()                              │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │  IN_PROGRESS     │◄──────────┐                    │
│                    │  (Active task)   │           │                    │
│                    └────────┬─────────┘           │                    │
│                             │                     │                    │
│                ┌────────────┼────────────┐        │                    │
│                │            │            │        │                    │
│                ▼            ▼            ▼        │                    │
│         ┌──────────┐ ┌──────────┐ ┌──────────┐  │                    │
│         │ Phase 1  │ │ Phase 2  │ │ Phase N  │  │                    │
│         │ Execute  │ │ Execute  │ │ Execute  │  │                    │
│         └────┬─────┘ └────┬─────┘ └────┬─────┘  │                    │
│              │            │            │         │                    │
│              │ PASSED     │ PASSED     │ PASSED  │                    │
│              └────────────┴────────────┘         │                    │
│                             │                     │                    │
│                             │ All required        │                    │
│                             │ phases passed       │                    │
│                             ▼                     │                    │
│                    ┌──────────────────┐           │                    │
│                    │   COMPLETED      │           │                    │
│                    │   (Success!)     │           │                    │
│                    └──────────────────┘           │                    │
│                                                    │                    │
│                                                    │                    │
│                    ┌──────────────────┐           │                    │
│                    │   ABANDONED      │           │                    │
│                    │   (Max attempts) │───────────┘                    │
│                    └────────┬─────────┘    retry (delete & restart)   │
│                             │                                           │
│                             │ Player can retry                          │
│                             │ (starts fresh)                            │
│                             └──────────────────────────────────────────┤
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### State Transitions

| From State | Action | To State | Notes |
|------------|--------|----------|-------|
| NOT_STARTED | start_task() | IN_PROGRESS | Creates initial phase states |
| IN_PROGRESS | execute_phase() → PASSED | IN_PROGRESS | Moves to next phase |
| IN_PROGRESS | execute_phase() → FAILED | IN_PROGRESS | Stays on same phase, increments attempts |
| IN_PROGRESS | complete_task() | COMPLETED | All required phases passed |
| IN_PROGRESS | fail_task() | ABANDONED | Max attempts reached |
| ABANDONED | start_task() | IN_PROGRESS | Deletes old state, starts fresh |


## Phase State Machine

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PHASE LIFECYCLE                                 │
│                                                                         │
│                    ┌──────────────────┐                                │
│                    │    PENDING       │                                │
│                    │  (Not started)   │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             │ execute_phase()                           │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │    RUNNING       │                                │
│                    │  (Tests running) │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                    ┌────────┴────────┐                                 │
│                    │                 │                                 │
│                    ▼                 ▼                                 │
│           ┌─────────────────┐  ┌─────────────────┐                   │
│           │     PASSED      │  │     FAILED      │                   │
│           │  (Tests OK)     │  │  (Tests failed) │                   │
│           │  +Points        │  │  attempts++     │                   │
│           └─────────────────┘  └────────┬────────┘                   │
│                                          │                             │
│                                          │                             │
│                                ┌─────────┴─────────┐                  │
│                                │                   │                   │
│                                ▼                   ▼                   │
│                    ┌──────────────────┐  ┌──────────────────┐        │
│                    │ attempts <       │  │ attempts >=      │        │
│                    │ max_attempts     │  │ max_attempts     │        │
│                    └────────┬─────────┘  └────────┬─────────┘        │
│                             │                     │                   │
│                             ▼                     ▼                   │
│                    ┌──────────────────┐  ┌──────────────────┐        │
│                    │  Stay FAILED     │  │  Task ABANDONED  │        │
│                    │  (Can retry)     │  │  (No more tries) │        │
│                    └──────────────────┘  └──────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Phase Properties

Each phase tracks:
- **status**: PENDING → RUNNING → PASSED/FAILED
- **attempts**: Number of execution attempts
- **last_result**: Test result (OK, FAILED, ERROR, TIMEOUT)
- **last_report_url**: Link to HTML test report
- **points_earned**: Points awarded (0 if not passed)
- **last_executed_at**: Timestamp of last execution


## NPC Management Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         NPC AVAILABILITY                                │
│                                                                         │
│                    ┌──────────────────┐                                │
│                    │  Player talks    │                                │
│                    │  to NPC          │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │  Check NPC Lock  │                                │
│                    └────┬────────┬────┘                                │
│                         │        │                                     │
│                    Locked│        │Available                           │
│                         ▼        ▼                                     │
│              ┌──────────────┐  ┌──────────────────┐                   │
│              │ "Come back   │  │ Check Assignment │                   │
│              │  in X min"   │  └────┬────────┬────┘                   │
│              └──────────────┘       │        │                         │
│                                     │        │                         │
│                          Assigned to│        │No assignment            │
│                          other NPC  │        │                         │
│                                     ▼        ▼                         │
│                          ┌──────────────┐  ┌──────────────┐           │
│                          │ "Complete    │  │ Give Task    │           │
│                          │  task from   │  │ to Player    │           │
│                          │  NPC X"      │  └──────────────┘           │
│                          └──────────────┘                              │
│                                                                         │
│                                                                         │
│                    ┌──────────────────┐                                │
│                    │  Task Completed  │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │  Lock NPC for    │                                │
│                    │  30 minutes      │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │  Clear           │                                │
│                    │  Assignment      │                                │
│                    └──────────────────┘                                │
│                                                                         │
│                                                                         │
│                    ┌──────────────────┐                                │
│                    │  Task Abandoned  │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │  Clear           │                                │
│                    │  Assignment      │                                │
│                    │  (NO LOCK)       │                                │
│                    └────────┬─────────┘                                │
│                             │                                           │
│                             ▼                                           │
│                    ┌──────────────────┐                                │
│                    │  Player can      │                                │
│                    │  retry           │                                │
│                    │  immediately     │                                │
│                    └──────────────────┘                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### NPC States

| State | Description | Player Action |
|-------|-------------|---------------|
| **Available** | Not locked, no assignment | Can receive task |
| **Locked** | Cooldown after task completion | "Come back later!" |
| **Assigned** | Player has ongoing task from this NPC | Continue task |
| **Busy** | Player has task from different NPC | "Complete other task first!" |


## Session Data & Personalization

### How Personalization Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SESSION DATA GENERATION                              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  1. Player starts task                                           │  │
│  │     email: "john@example.com"                                    │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│              ┌────────────────────────────┐                            │
│              │  2. Extract student_id     │                            │
│              │     "john@example.com"     │                            │
│              │     → "john"               │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  3. Seed random generator  │                            │
│              │     seed = hash("john")    │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  4. Generate session data  │                            │
│              │                            │                            │
│              │  Template:                 │                            │
│              │  {                         │                            │
│              │    "namespace":            │                            │
│              │      "{{random_name()}}"   │                            │
│              │      "{{student_id()}}"    │                            │
│              │  }                         │                            │
│              │                            │                            │
│              │  Generated:                │                            │
│              │  {                         │                            │
│              │    "namespace":            │                            │
│              │      "happy_dolphin_john"  │                            │
│              │  }                         │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  5. Store in TaskState     │                            │
│              │     session_data = {...}   │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  6. Pass to tests          │                            │
│              │     /tmp/json_input.json   │                            │
│              └────────────────────────────┘                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Session Functions

| Function | Description | Example |
|----------|-------------|---------|
| `{{student_id()}}` | Extract ID from email | "john@example.com" → "john" |
| `{{random_name()}}` | Generate random name (seeded) | "happy_dolphin" |
| `{{random_number(1,100)}}` | Generate random number (seeded) | 42 |
| `{{base64_encode(value)}}` | Base64 encode value | "john" → "am9obg==" |

### Benefits

1. **Prevents Cheating**: Each player has different resource names
2. **Deterministic**: Same player always gets same values
3. **Isolated**: Players can't interfere with each other
4. **Flexible**: Support any Jinja2 template expressions


## Task Abandonment & Retry Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ABANDONMENT & RETRY FLOW                             │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Phase fails repeatedly                                          │  │
│  │  attempts = 3, max_attempts = 3                                  │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│              ┌────────────────────────────┐                            │
│              │  Detect max attempts       │                            │
│              │  reached                   │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Call abandon_task()       │                            │
│              │  - Mark status=ABANDONED   │                            │
│              │  - Save to DynamoDB        │                            │
│              │  - Clear NPC assignment    │                            │
│              │  - NO LOCK on NPC          │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Return to player:         │                            │
│              │  "Task abandoned. You can  │                            │
│              │   try again with same NPC" │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Player talks to NPC again │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Detect ABANDONED status   │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Delete old TaskState      │                            │
│              │  from DynamoDB             │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Start fresh task          │                            │
│              │  - New TaskState           │                            │
│              │  - status=IN_PROGRESS      │                            │
│              │  - attempts reset to 0     │                            │
│              │  - New session data        │                            │
│              └────────────┬───────────────┘                            │
│                           │                                             │
│                           ▼                                             │
│              ┌────────────────────────────┐                            │
│              │  Player tries again!       │                            │
│              └────────────────────────────┘                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Points

1. **No Lock**: When task is abandoned, NPC is NOT locked (unlike completion)
2. **Immediate Retry**: Player can retry immediately with same NPC
3. **Fresh Start**: Old state is deleted, new state created
4. **Reset Attempts**: All attempt counters reset to 0
5. **New Session**: New personalized session data generated


## Complete Player Journey Example

### Scenario: John completes his first task

```
Step 1: Registration
──────────────────────
John visits: https://api.example.com/save-k8s-account
Provides:
  - Email: john@example.com
  - K8s endpoint: https://k8s.example.com
  - Client certificate
  - Client key

System stores credentials in AccountTable


Step 2: Get API Key
──────────────────────
John visits: https://api.example.com/keygen?secret=SECRET&email=john@example.com
System generates encrypted API key: gAAAAABh...
John saves this key for API calls


Step 3: Talk to NPC Alice
──────────────────────────
Game calls: POST /task
Headers: x-api-key: gAAAAABh...
Body: {email: "john@example.com", game: "game01", npc: "alice"}

System checks:
  ✓ API key valid
  ✓ Alice not locked
  ✓ No ongoing task from other NPC
  ✓ Current task = "01_default_namespace"
  ✓ Task not started yet

System:
  1. Creates TaskState (status=IN_PROGRESS)
  2. Generates session data:
     {
       "namespace": "happy_dolphin_john",
       "$endpoint": "https://k8s.example.com",
       "$client_certificate": "...",
       "$client_key": "...",
       "$email": "john@example.com",
       "$instruction": "Verify that the default namespace exists"
     }
  3. Saves to TaskStateTable
  4. Assigns task to Alice in NpcAssignmentTable

Response:
{
  "status": "STARTED",
  "task_id": "01_default_namespace",
  "current_phase": "setup",
  "message": "Verify that the default namespace exists",
  "progress": 0.0
}


Step 4: Setup Phase Executes
──────────────────────────────
Game calls: POST /task (same request)

System:
  1. Loads TaskState (status=IN_PROGRESS, current_phase="setup")
  2. Validates can execute setup phase
  3. Runs pytest on test_01_setup.py
     - Downloads game source from S3
     - Creates /tmp/json_input.json with session data
     - Executes tests with 30s timeout
  4. Tests PASS
  5. Updates phase state:
     - status=PASSED
     - points_earned=0
     - report_url="https://s3.../report.html"
  6. Moves to next phase: "check"
  7. Saves TaskState

Response:
{
  "status": "OK",
  "current_phase": "check",
  "next_phase": "check",
  "message": "Verify that the default namespace exists",
  "report_url": "https://s3.../report.html",
  "progress": 0.33,
  "points": 0
}


Step 5: Check Phase Executes
──────────────────────────────
Game calls: POST /task (same request)

System:
  1. Loads TaskState (current_phase="check")
  2. Runs pytest on test_05_check.py
  3. Tests PASS
  4. Updates phase state:
     - status=PASSED
     - points_earned=10
     - total_points=10
  5. Moves to next phase: "cleanup"
  6. Saves TaskState

Response:
{
  "status": "OK",
  "current_phase": "cleanup",
  "next_phase": "cleanup",
  "message": "Verify that the default namespace exists",
  "report_url": "https://s3.../report.html",
  "progress": 0.66,
  "points": 10
}


Step 6: Cleanup Phase Auto-Runs
─────────────────────────────────
Game calls: POST /task (same request)

System:
  1. Loads TaskState (current_phase="cleanup")
  2. Runs pytest on test_06_cleanup.py
  3. Tests PASS
  4. All required phases complete!
  5. Calls complete_task():
     - Marks status=COMPLETED
     - Locks Alice for 30 minutes
     - Clears NPC assignment
     - Saves TaskState

Response:
{
  "status": "COMPLETED",
  "task_id": "01_default_namespace",
  "message": "🎉 Task completed! You earned 10 points!",
  "report_url": "https://s3.../report.html",
  "easter_egg_url": "https://...",
  "progress": 1.0,
  "total_points": 10
}


Step 7: Next Task
──────────────────
John talks to Bob (different NPC)

System:
  ✓ Bob not locked
  ✓ No ongoing task
  ✓ Current task = "02_create_namespace"
  ✓ Task not started yet

Starts new task with Bob...
```


## Failure & Retry Example

### Scenario: Sarah fails a phase and retries

```
Step 1: Sarah starts task
──────────────────────────
Task: "03_create_pod"
Phase: "setup" → PASSED (0 points)
Phase: "check" → Current phase


Step 2: First attempt fails
────────────────────────────
Game calls: POST /task

System:
  1. Runs test_05_check.py
  2. Tests FAIL (pod not found)
  3. Updates phase state:
     - status=FAILED
     - attempts=1
     - max_attempts=3
     - last_result="FAILED"
  4. Stays on "check" phase
  5. Saves TaskState

Response:
{
  "status": "FAILED",
  "current_phase": "check",
  "next_phase": "check",
  "message": "Tests failed. Check the report.",
  "report_url": "https://s3.../report.html",
  "attempts": 1,
  "test_result": "FAILED"
}


Step 3: Sarah fixes issue, retries
────────────────────────────────────
Game calls: POST /task (same request)

System:
  1. Loads TaskState (current_phase="check", attempts=1)
  2. Validates: attempts (1) < max_attempts (3) ✓
  3. Runs test_05_check.py again
  4. Tests FAIL again (wrong pod name)
  5. Updates phase state:
     - status=FAILED
     - attempts=2
  6. Saves TaskState

Response:
{
  "status": "FAILED",
  "current_phase": "check",
  "next_phase": "check",
  "message": "Tests failed. Check the report.",
  "report_url": "https://s3.../report.html",
  "attempts": 2,
  "test_result": "FAILED"
}


Step 4: Third attempt succeeds
────────────────────────────────
Game calls: POST /task

System:
  1. Runs test_05_check.py
  2. Tests PASS!
  3. Updates phase state:
     - status=PASSED
     - points_earned=20
     - total_points=20
  4. Moves to "cleanup" phase
  5. Saves TaskState

Response:
{
  "status": "OK",
  "current_phase": "cleanup",
  "next_phase": "cleanup",
  "message": "Phase completed!",
  "report_url": "https://s3.../report.html",
  "progress": 0.66,
  "points": 20
}
```


## Max Attempts & Abandonment Example

### Scenario: Mike fails too many times

```
Step 1: Mike starts task
─────────────────────────
Task: "05_create_deployment"
Phase: "setup" → PASSED
Phase: "check" → Current phase (max_attempts=3)


Step 2: Attempt 1 - FAILED
────────────────────────────
Tests fail: Deployment not found
attempts=1, max_attempts=3

Response: "FAILED" (can retry)


Step 3: Attempt 2 - FAILED
────────────────────────────
Tests fail: Wrong replica count
attempts=2, max_attempts=3

Response: "FAILED" (can retry)


Step 4: Attempt 3 - FAILED
────────────────────────────
Tests fail: Wrong image
attempts=3, max_attempts=3

System detects: attempts >= max_attempts!

System:
  1. Calls abandon_task()
  2. Marks status=ABANDONED
  3. Clears NPC assignment (NO LOCK)
  4. Saves TaskState

Response:
{
  "status": "ABANDONED",
  "task_id": "05_create_deployment",
  "message": "❌ Task abandoned: Maximum attempts reached for phase 'check'. You can try again with the same NPC.",
  "reason": "Maximum attempts reached for phase 'check'",
  "report_url": "https://s3.../report.html",
  "progress": 0.0,
  "total_points": 0
}


Step 5: Mike talks to same NPC again
──────────────────────────────────────
Game calls: POST /task (same NPC)

System:
  1. Loads TaskState (status=ABANDONED)
  2. Detects ABANDONED status
  3. Deletes old TaskState from DynamoDB
  4. Starts fresh task:
     - New TaskState
     - status=IN_PROGRESS
     - attempts=0 for all phases
     - New session data
  5. Saves new TaskState

Response:
{
  "status": "STARTED",
  "task_id": "05_create_deployment",
  "current_phase": "setup",
  "message": "Create a deployment with 3 replicas",
  "progress": 0.0
}

Mike can try again from the beginning!
```

### Key Differences: Completion vs Abandonment

| Aspect | Task Completed | Task Abandoned |
|--------|----------------|----------------|
| **NPC Lock** | ✅ Locked 30 min | ❌ Not locked |
| **Assignment** | Cleared | Cleared |
| **Retry** | Must wait 30 min | Immediate retry |
| **State** | Kept in DB | Deleted on retry |
| **Points** | Kept | Lost |


## Database Tables & Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATABASE ARCHITECTURE                           │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  AccountTable                                                    │  │
│  │  ─────────────                                                   │  │
│  │  PK: email                                                       │  │
│  │  - endpoint (K8s API URL)                                        │  │
│  │  - client_certificate                                            │  │
│  │  - client_key                                                    │  │
│  │  - created_at                                                    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  ApiKeyTable                                                     │  │
│  │  ────────────                                                    │  │
│  │  PK: email                                                       │  │
│  │  - api_key (encrypted with Fernet)                               │  │
│  │  - created_at                                                    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  TaskStateTable (MAIN STATE)                                     │  │
│  │  ───────────────                                                 │  │
│  │  PK: email#game#task_id                                          │  │
│  │  - status (NOT_STARTED, IN_PROGRESS, COMPLETED, ABANDONED)       │  │
│  │  - current_phase_id                                              │  │
│  │  - npc (assigned NPC name)                                       │  │
│  │  - total_points                                                  │  │
│  │  - session_data (JSON with personalized values)                  │  │
│  │  - phase_states (JSON map of phase_id → PhaseState)             │  │
│  │  - created_at                                                    │  │
│  │  - updated_at                                                    │  │
│  │  - completed_at                                                  │  │
│  │                                                                  │  │
│  │  PhaseState structure:                                           │  │
│  │  {                                                               │  │
│  │    "status": "PASSED",                                           │  │
│  │    "attempts": 2,                                                │  │
│  │    "last_result": "OK",                                          │  │
│  │    "last_report_url": "https://...",                             │  │
│  │    "points_earned": 10,                                          │  │
│  │    "last_executed_at": "2026-01-31T..."                          │  │
│  │  }                                                               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  NpcAssignmentTable                                              │  │
│  │  ───────────────────                                             │  │
│  │  PK: email#game                                                  │  │
│  │  - npc (currently assigned NPC)                                  │  │
│  │  - task_id (current task)                                        │  │
│  │  - assigned_at                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  NpcLockTable                                                    │  │
│  │  ─────────────                                                   │  │
│  │  PK: email#game#npc                                              │  │
│  │  - locked_until (timestamp)                                      │  │
│  │  - ttl (DynamoDB TTL for auto-deletion)                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  NpcBackgroundTable                                              │  │
│  │  ───────────────────                                             │  │
│  │  PK: npc_name                                                    │  │
│  │  - age                                                           │  │
│  │  - gender                                                        │  │
│  │  - background (character story)                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  TestRecordTable                                                 │  │
│  │  ────────────────                                                │  │
│  │  PK: email#game#timestamp                                        │  │
│  │  - task_id                                                       │  │
│  │  - phase_id                                                      │  │
│  │  - test_result (OK, FAILED, ERROR, TIMEOUT)                      │  │
│  │  - report_url                                                    │  │
│  │  - executed_at                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  GameSourceTable                                                 │  │
│  │  ────────────────                                                │  │
│  │  PK: game                                                        │  │
│  │  - source_url (GitHub URL for test files)                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Example

```
1. Player talks to NPC
   ↓
2. Load from AccountTable (K8s credentials)
   ↓
3. Validate ApiKeyTable (encrypted key)
   ↓
4. Check NpcLockTable (is NPC available?)
   ↓
5. Check NpcAssignmentTable (ongoing task?)
   ↓
6. Load/Create TaskStateTable (task progress)
   ↓
7. Execute phase (run tests)
   ↓
8. Update TaskStateTable (phase results)
   ↓
9. Save to TestRecordTable (audit log)
   ↓
10. Update NpcAssignmentTable (if completed)
    ↓
11. Update NpcLockTable (if completed)
```


## API Response Types

### 1. Random Chat Response
```json
{
  "status": "OK",
  "message": "Hello! Nice weather today, isn't it?"
}
```

### 2. NPC Locked Response
```json
{
  "status": "ERROR",
  "message": "Alice does not have any task for you!"
}
```

### 3. Task Started Response
```json
{
  "status": "STARTED",
  "task_id": "01_default_namespace",
  "current_phase": "setup",
  "message": "Verify that the default namespace exists",
  "progress": 0.0
}
```

### 4. Phase Passed Response
```json
{
  "status": "OK",
  "current_phase": "check",
  "next_phase": "cleanup",
  "message": "Verify that the default namespace exists",
  "report_url": "https://s3.amazonaws.com/.../report.html",
  "progress": 0.66,
  "points": 10
}
```

### 5. Phase Failed Response
```json
{
  "status": "FAILED",
  "current_phase": "check",
  "next_phase": "check",
  "message": "Tests failed. Check the report.",
  "report_url": "https://s3.amazonaws.com/.../report.html",
  "attempts": 2,
  "test_result": "FAILED"
}
```

### 6. Task Completed Response
```json
{
  "status": "COMPLETED",
  "task_id": "01_default_namespace",
  "message": "🎉 Task completed! You earned 10 points!",
  "report_url": "https://s3.amazonaws.com/.../report.html",
  "easter_egg_url": "https://...",
  "progress": 1.0,
  "total_points": 10
}
```

### 7. Task Abandoned Response
```json
{
  "status": "ABANDONED",
  "task_id": "05_create_deployment",
  "message": "❌ Task abandoned: Maximum attempts reached for phase 'check'. You can try again with the same NPC.",
  "reason": "Maximum attempts reached for phase 'check'",
  "report_url": "https://s3.amazonaws.com/.../report.html",
  "progress": 0.0,
  "total_points": 0
}
```

### 8. All Tasks Complete Response
```json
{
  "status": "OK",
  "message": "🎉 Congratulations! You've completed all tasks!"
}
```


## Points & Progress System

### Points Distribution

Typical task structure:
```
setup phase:     0 points  (preparation)
ready phase:     5 points  (verification)
challenge phase: 10 points (understanding)
check phase:     20 points (solution)
cleanup phase:   0 points  (housekeeping)
─────────────────────────────────────────
Total:          35 points per task
```

### Progress Calculation

```python
progress = completed_phases / total_required_phases

Example:
- Total phases: 5 (setup, ready, challenge, check, cleanup)
- Required phases: 4 (cleanup is auto-run, not required)
- Completed: 2 (setup, ready)
- Progress: 2 / 4 = 0.5 (50%)
```

### Phase Completion Rules

| Phase Type | Required | Auto-run | Counts for Progress |
|------------|----------|----------|---------------------|
| setup | ✅ Yes | ❌ No | ✅ Yes |
| ready | ✅ Yes | ❌ No | ✅ Yes |
| challenge | ✅ Yes | ❌ No | ✅ Yes |
| check | ✅ Yes | ❌ No | ✅ Yes |
| cleanup | ❌ No | ✅ Yes | ❌ No |

### Task Completion Criteria

A task is complete when:
1. All **required** phases are **PASSED**
2. Auto-run phases (cleanup) execute automatically
3. Status changes to **COMPLETED**
4. Points are finalized
5. NPC is locked for 30 minutes


## Error Handling & Edge Cases

### 1. Invalid API Key
```
Request: Invalid or expired API key
Response: {
  "status": "ERROR",
  "message": "Invalid or expired API key. Please generate a new one."
}
```

### 2. Missing K8s Credentials
```
Request: User not registered
Response: {
  "status": "ERROR",
  "message": "User account not found"
}
```

### 3. NPC Already Assigned
```
Request: Talk to Bob while having task from Alice
Response: {
  "status": "ERROR",
  "message": "Complete task from Alice first!"
}
```

### 4. Test Timeout
```
Phase execution exceeds timeout (default 30s)
Result: test_result = "TIMEOUT"
Phase marked as FAILED
Attempt counter incremented
```

### 5. Test Error
```
Test crashes or throws exception
Result: test_result = "ERROR"
Phase marked as FAILED
Error logged to CloudWatch
```

### 6. Network Issues
```
Cannot connect to K8s cluster
Result: test_result = "ERROR"
Phase marked as FAILED
Player should check credentials
```

### 7. Concurrent Requests
```
Two requests for same task at same time
DynamoDB handles with optimistic locking
Last write wins
Minimal impact on player experience
```

### 8. Abandoned Task Retry
```
Player retries abandoned task
Old state deleted
Fresh start with new session data
All attempts reset to 0
```


## Security & Anti-Cheating Measures

### 1. Personalized Session Data
- Each player gets unique resource names
- Seeded by student ID (deterministic)
- Prevents copy-paste solutions
- Example: "namespace-happy_dolphin_john" vs "namespace-brave_tiger_sarah"

### 2. Encrypted API Keys
- Fernet symmetric encryption
- Email embedded in key
- Cannot be forged or reused by others
- Keys stored in DynamoDB

### 3. K8s Credential Isolation
- Each player has own K8s cluster credentials
- Credentials stored encrypted
- Cannot access other players' resources
- Validated on every request

### 4. NPC Assignment Tracking
- One task per player at a time
- Cannot skip tasks
- Cannot work on multiple tasks simultaneously
- Progress tracked in DynamoDB

### 5. Attempt Limits
- Maximum attempts per phase (typically 3-5)
- Prevents brute force
- Encourages learning from mistakes
- Task abandoned after max attempts

### 6. Test Execution Isolation
- Tests run in Lambda (isolated environment)
- Temporary files cleaned after execution
- No persistent state between runs
- Cannot interfere with other players

### 7. Audit Trail
- All test executions logged to TestRecordTable
- CloudWatch logs for debugging
- Timestamps for all operations
- Can detect suspicious patterns


## Performance Considerations

### Lambda Cold Start
- First request: ~2-3 seconds (cold start)
- Subsequent requests: ~100-300ms (warm)
- Mitigation: Keep Lambda warm with scheduled pings

### DynamoDB Performance
- Single-digit millisecond latency
- On-demand capacity (auto-scaling)
- No connection pooling needed
- Efficient for read-heavy workloads

### Test Execution Time
- Typical phase: 5-15 seconds
- Includes:
  - Download game source from S3 (~1s)
  - Run pytest (~3-10s)
  - Upload report to S3 (~1s)
  - Update DynamoDB (~100ms)

### S3 Report Storage
- HTML reports stored in S3
- Pre-signed URLs for access
- 7-day expiration (configurable)
- Minimal cost (~$0.01/month)

### API Gateway Limits
- 10,000 requests/second (default)
- 29-second timeout
- Sufficient for educational use
- Can increase if needed

### Optimization Tips
1. Use repository pattern (connection reuse)
2. Lazy load DynamoDB tables
3. Cache NPC backgrounds
4. Batch DynamoDB operations (future)
5. Use Lambda layers for dependencies


## Summary

### Key Game Mechanics

1. **Sequential Tasks**: Players complete tasks in order (01, 02, 03...)
2. **NPC System**: NPCs give tasks and have cooldowns after completion
3. **Phase-Based**: Each task has multiple test phases (setup, check, cleanup)
4. **Retry System**: Limited attempts per phase, task abandoned if exceeded
5. **Personalization**: Each player gets unique resource names
6. **Points & Progress**: Gamification with points and progress tracking

### State Management

- **TaskState**: Main state object (status, phases, points, session)
- **PhaseState**: Per-phase tracking (attempts, results, reports)
- **NPC Assignment**: One task per player, tracked in DynamoDB
- **NPC Locks**: 30-minute cooldown after task completion

### Player Experience

1. Register K8s credentials
2. Generate API key
3. Talk to NPC → Receive task
4. Complete phases → Earn points
5. Task complete → NPC locked 30 min
6. Talk to different NPC → Next task

### Failure Handling

- **Phase Fails**: Retry same phase (up to max_attempts)
- **Max Attempts**: Task abandoned, can retry immediately
- **Test Timeout**: Counted as failure, attempt incremented
- **Test Error**: Logged, counted as failure

### Anti-Cheating

- Personalized session data (unique resource names)
- Encrypted API keys (cannot forge)
- K8s credential isolation (own cluster)
- Attempt limits (prevents brute force)
- Audit trail (all actions logged)

## Race Condition Prevention

### The Problem

When a player quickly chats with 2 NPCs (e.g., NPC-A and NPC-B), a race condition could occur where both NPCs would try to assign tasks simultaneously, resulting in incorrect locking behavior.

#### Root Cause

The issue was a classic **check-then-act** pattern without atomic operations:

```python
# Step 1: Check (in validate_npc_access)
assigned_npc = self.npc_repo.get_assigned_npc(email, game)
if assigned_npc and assigned_npc != npc:
    return False, "Complete task from {assigned_npc} first!"

# Step 2: Act (in start_task) - NOT ATOMIC!
self.npc_repo.assign_task(email, game, npc, task_id)
```

#### Race Condition Scenario

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RACE CONDITION (BEFORE FIX)                          │
│                                                                         │
│  Time  │  Request 1 (NPC-A)              │  Request 2 (NPC-B)          │
│  ──────┼─────────────────────────────────┼─────────────────────────────│
│   t0   │ Check assignment → None         │                             │
│   t1   │                                 │ Check assignment → None     │
│   t2   │ Assign NPC-A                    │                             │
│   t3   │                                 │ Assign NPC-B (overwrites!)  │
│   t4   │ Create task state (NPC-A)       │                             │
│   t5   │                                 │ Create task state (NPC-B)   │
│        │                                 │                             │
│ Result: Player has NPC-B assigned but NPC-A's task was started!        │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Solution

#### 1. Atomic DynamoDB Operations

Changed `assign_task()` to use DynamoDB conditional writes:

```python
def assign_task(self, email: str, game: str, npc: str, task_id: str) -> bool:
    try:
        self.assignment_table.put_item(
            Item={...},
            # Only succeed if no assignment exists
            ConditionExpression='attribute_not_exists(email) AND attribute_not_exists(game)'
        )
        return True
    except ConditionalCheckFailedException:
        # Assignment already exists - race condition prevented!
        return False
```

#### 2. Assign-First Pattern

Changed `start_task()` to assign NPC **before** creating task state:

```python
def start_task(self, email: str, game: str, task_id: str, npc: str) -> TaskState:
    # Check if already started
    existing = self.task_repo.get(email, game, task_id)
    if existing:
        # Verify it's the same NPC
        if existing.npc != npc:
            raise ValueError(f"Complete task from {existing.npc} first!")
        return existing
    
    # Try to assign NPC atomically FIRST (prevents race condition)
    assigned = self.npc_repo.assign_task(email, game, npc, task_id)
    if not assigned:
        # Another NPC already assigned
        assigned_npc = self.npc_repo.get_assigned_npc(email, game)
        raise ValueError(f"Complete task from {assigned_npc} first!")
    
    try:
        # Create task state...
        # ...
    except Exception as e:
        # Rollback assignment on any error
        self.npc_repo.clear_assignment(email, game)
        raise
```

#### 3. Client-Side Debouncing

Added `pendingRequest` flag in JavaScript to prevent multiple simultaneous requests:

```javascript
let pendingRequest = false;

const callApi = (npcName) => {
    if (callCount > 0 || pendingRequest) {
        $gameMessage.add('I am working on it now!');
        return;
    }
    
    pendingRequest = true;
    
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) {
            pendingRequest = false; // Clear flag
            // ...
        }
    };
};
```

### Fixed Race Condition Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RACE CONDITION (AFTER FIX)                           │
│                                                                         │
│  Time  │  Request 1 (NPC-A)              │  Request 2 (NPC-B)          │
│  ──────┼─────────────────────────────────┼─────────────────────────────│
│   t0   │ Atomic assign NPC-A → Success   │                             │
│   t1   │                                 │ Atomic assign NPC-B → FAIL  │
│   t2   │ Create task state (NPC-A)       │                             │
│   t3   │                                 │ Error: "Complete task from  │
│        │                                 │         NPC-A first!"       │
│        │                                 │                             │
│ Result: Only NPC-A assigned, NPC-B gets clear error message            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Benefits

1. **Atomic Operations**: DynamoDB conditional writes ensure only one NPC can assign at a time
2. **Fail-Fast**: Second NPC immediately fails with clear error message
3. **Rollback Safety**: If task creation fails, assignment is rolled back
4. **Client Protection**: Frontend prevents rapid-fire requests
5. **No Deadlocks**: No locks held during long operations

### Testing

Comprehensive tests verify the fix:

- `test_race_condition_prevention`: Verifies two NPCs cannot assign simultaneously
- `test_assign_task_atomic_operation`: Tests atomic DynamoDB operation
- `test_reassign_npc`: Confirms atomic operation prevents overwrites
- `test_assign_task_after_clear`: Ensures assignment works after clearing

Run tests:
```bash
cd k8s-grader/k8s-grader-api
./run_tests.sh
```

### Performance Impact

Minimal - conditional writes have the same performance as regular writes, just with additional validation. No database migration required.

## Related Documentation

- **[../README.md](../README.md)** - Project overview
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture
- **[MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)** - Task configuration
- **[DATABASE_GUIDE.md](DATABASE_GUIDE.md)** - Database layer
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - Testing guide
- **[CHANGELOG.md](CHANGELOG.md)** - Recent bug fixes

