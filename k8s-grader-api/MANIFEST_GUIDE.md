# Task Manifest Guide

## Overview

The `manifest.json` file is a **declarative configuration** that defines a Kubernetes learning task. It replaces the old implicit file-based discovery system with an explicit, self-documenting format.

**Note:** manifest.json is **optional**! If not present, the system will auto-generate a manifest by discovering test files in the task directory. However, creating a manifest.json is **highly recommended** for better control over task metadata, points, timeouts, and descriptions.

## Location

Each task directory can optionally contain a `manifest.json` file:

```
k8s-game-rule/tests/game01/
└── 01_default_namespace/
    ├── manifest.json          ← Required
    ├── instruction.md
    ├── test_01_setup.py
    ├── test_05_check.py
    └── test_06_cleanup.py
```

## Schema

### Root Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✅ | Unique identifier (e.g., "01", "02") |
| `title` | string | ✅ | Display name for the task |
| `description` | string | ✅ | What the user will learn/do |
| `difficulty` | string | ✅ | "beginner", "intermediate", or "advanced" |
| `estimated_minutes` | number | ✅ | Expected completion time |
| `phases` | array | ✅ | List of phase configurations |
| `prerequisites` | array | ✅ | Task IDs that must be completed first |
| `tags` | array | ✅ | Keywords for search/filtering |
| `hints` | array | ✅ | Optional hints for users |

### Phase Object

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | ✅ | - | Phase identifier: "setup", "ready", "challenge", "check", "cleanup" |
| `name` | string | ✅ | - | Display name |
| `description` | string | ✅ | - | What this phase does |
| `test_file` | string | ✅ | - | Python test file name |
| `required` | boolean | ❌ | true | Must pass to continue |
| `auto_run` | boolean | ❌ | false | Run automatically (typically cleanup) |
| `timeout_seconds` | number | ❌ | 30 | Test execution timeout |
| `max_attempts` | number | ❌ | 3 | Maximum retry attempts |
| `points` | number | ❌ | 0 | Points awarded for passing |

## Phase Types

### 1. Setup Phase
- **Purpose**: Initialize environment, prepare resources
- **Typical test_file**: `test_01_setup.py`
- **Required**: Usually `true`
- **Auto-run**: `false`
- **Points**: Usually `0`

### 2. Ready Phase (Optional)
- **Purpose**: Verify prerequisites, check environment
- **Typical test_file**: `test_03_answer.py` or `test_02_ready.py`
- **Required**: Usually `true`
- **Auto-run**: `false`
- **Points**: Small amount (5-10)

### 3. Challenge Phase (Optional)
- **Purpose**: Present the main task to the user
- **Typical test_file**: `test_04_challenge.py`
- **Required**: Usually `true`
- **Auto-run**: `false`
- **Points**: Medium amount (10-20)

### 4. Check Phase
- **Purpose**: Validate user's solution
- **Typical test_file**: `test_05_check.py`
- **Required**: Usually `true`
- **Auto-run**: `false`
- **Points**: Highest amount (15-30)

### 5. Cleanup Phase
- **Purpose**: Remove resources, clean up environment
- **Typical test_file**: `test_06_cleanup.py`
- **Required**: Usually `false`
- **Auto-run**: `true` (runs automatically after task)
- **Points**: Usually `0`

## Example: Simple Task

```json
{
  "task_id": "01",
  "title": "Verify Default Namespace",
  "description": "Connect to your Kubernetes cluster and verify that the default namespace exists.",
  "difficulty": "beginner",
  "estimated_minutes": 5,
  "phases": [
    {
      "id": "setup",
      "name": "Setup",
      "description": "Initialize the task environment",
      "test_file": "test_01_setup.py",
      "required": true,
      "auto_run": false,
      "timeout_seconds": 30,
      "max_attempts": 3,
      "points": 0
    },
    {
      "id": "check",
      "name": "Check",
      "description": "Verify that the default namespace exists",
      "test_file": "test_05_check.py",
      "required": true,
      "auto_run": false,
      "timeout_seconds": 30,
      "max_attempts": 3,
      "points": 10
    },
    {
      "id": "cleanup",
      "name": "Cleanup",
      "description": "Clean up task resources",
      "test_file": "test_06_cleanup.py",
      "required": false,
      "auto_run": true,
      "timeout_seconds": 30,
      "max_attempts": 1,
      "points": 0
    }
  ],
  "prerequisites": [],
  "tags": ["kubernetes", "namespace", "beginner"],
  "hints": [
    "Make sure you have provided the correct cluster credentials",
    "The default namespace is created automatically"
  ]
}
```

## Example: Complex Task

```json
{
  "task_id": "15",
  "title": "Deploy Multi-Container Pod",
  "description": "Create a pod with multiple containers that communicate via shared volumes.",
  "difficulty": "intermediate",
  "estimated_minutes": 20,
  "phases": [
    {
      "id": "setup",
      "name": "Setup",
      "description": "Prepare the environment and resources",
      "test_file": "test_01_setup.py",
      "required": true,
      "auto_run": false,
      "timeout_seconds": 30,
      "max_attempts": 3,
      "points": 0
    },
    {
      "id": "ready",
      "name": "Ready",
      "description": "Verify prerequisites are met",
      "test_file": "test_02_ready.py",
      "required": true,
      "auto_run": false,
      "timeout_seconds": 30,
      "max_attempts": 3,
      "points": 5
    },
    {
      "id": "challenge",
      "name": "Challenge",
      "description": "Present the task requirements",
      "test_file": "test_04_challenge.py",
      "required": true,
      "auto_run": false,
      "timeout_seconds": 30,
      "max_attempts": 3,
      "points": 10
    },
    {
      "id": "check",
      "name": "Check",
      "description": "Validate the multi-container pod configuration",
      "test_file": "test_05_check.py",
      "required": true,
      "auto_run": false,
      "timeout_seconds": 60,
      "max_attempts": 5,
      "points": 25
    },
    {
      "id": "cleanup",
      "name": "Cleanup",
      "description": "Remove all created resources",
      "test_file": "test_06_cleanup.py",
      "required": false,
      "auto_run": true,
      "timeout_seconds": 30,
      "max_attempts": 1,
      "points": 0
    }
  ],
  "prerequisites": ["10", "12", "14"],
  "tags": ["kubernetes", "pod", "multi-container", "volumes", "intermediate"],
  "hints": [
    "Use emptyDir volume for container communication",
    "Each container needs its own name and image",
    "Containers in the same pod share the network namespace",
    "Use 'kubectl describe pod' to debug issues"
  ]
}
```

## Validation Rules

### Task ID
- Must be unique within a game
- Typically numeric: "01", "02", "15"
- Used in prerequisites and API calls

### Difficulty Levels
- `beginner`: First-time Kubernetes users
- `intermediate`: Some Kubernetes experience
- `advanced`: Complex scenarios, production concepts

### Phase IDs
Must be one of:
- `setup` - Always first
- `ready` - Optional, after setup
- `challenge` - Optional, presents task
- `check` - Required, validates solution
- `cleanup` - Always last, usually auto-run

### Prerequisites
- Array of task_id strings
- Tasks must be completed in order
- Empty array `[]` means no prerequisites
- Example: `["01", "02"]` means tasks 01 and 02 must be done first

### Points System
- Setup: 0 points (preparation)
- Ready: 5-10 points (verification)
- Challenge: 10-20 points (understanding)
- Check: 15-30 points (solution)
- Cleanup: 0 points (housekeeping)
- Total per task: typically 20-50 points

## Best Practices

### 1. Clear Descriptions
```json
// ❌ Bad
"description": "Do something with pods"

// ✅ Good
"description": "Create a pod named 'nginx' using the nginx image and expose port 80"
```

### 2. Realistic Time Estimates
```json
// Consider:
// - Reading instructions: 2-3 min
// - Implementing solution: varies
// - Debugging: 2-5 min
"estimated_minutes": 10  // Total realistic time
```

### 3. Helpful Hints
```json
"hints": [
  "Use 'kubectl run' for quick pod creation",  // Command hint
  "Port 80 is the default HTTP port",          // Concept hint
  "Check pod status with 'kubectl get pods'"   // Debugging hint
]
```

### 4. Appropriate Timeouts
```json
// Simple checks
"timeout_seconds": 30

// Complex operations (deployments, scaling)
"timeout_seconds": 60

// Very long operations (rare)
"timeout_seconds": 120
```

### 5. Sensible Retry Limits
```json
// Setup/Cleanup (should work first time)
"max_attempts": 1

// Check phases (allow learning from mistakes)
"max_attempts": 3

// Complex tasks (more attempts)
"max_attempts": 5
```

## Session Data & Personalization

### Overview

Each user gets **unique, personalized task parameters** to prevent cheating. Session data is generated when a task starts and stored with the task state.

### How It Works

1. **Session Template** (`session.json` in task directory):
```json
{
  "namespace": "{{random_name()}}{{student_id()}}",
  "pod_name": "nginx-{{random_number(1, 100)}}",
  "label_value": "{{base64_encode(student_id())}}"
}
```

2. **Available Functions**:
   - `{{student_id()}}` - Extracts from email (e.g., "john" from "john@example.com")
   - `{{random_name()}}` - Generates random name seeded by student ID (e.g., "happy_dolphin")
   - `{{random_number(from, to)}}` - Generates random number seeded by student ID
   - `{{base64_encode(value)}}` - Base64 encodes a value

3. **Generated for user john@example.com**:
```json
{
  "namespace": "happy_dolphin_john",
  "pod_name": "nginx-42",
  "label_value": "am9obg=="
}
```

4. **Storage**: Session data is stored in `TaskState.session_data` in TaskStateTable

5. **Usage**: Tests access session data via `json_input` fixture in conftest.py

### Example Task with Session Data

**Directory structure:**
```
01_create_namespace/
├── manifest.json
├── session.json          ← Session template
├── instruction.md
├── test_01_setup.py
├── test_04_challenge.py
└── test_05_check.py
```

**session.json:**
```json
{
  "namespace": "ns-{{random_name()}}{{random_number(1,99)}}"
}
```

**test_05_check.py:**
```python
def test_namespace_exists(json_input):
    """Check if user created the namespace"""
    namespace = json_input['namespace']  # e.g., "ns-happy_dolphin42"
    
    # Verify namespace exists
    result = subprocess.run(
        ['kubectl', 'get', 'namespace', namespace],
        capture_output=True
    )
    assert result.returncode == 0, f"Namespace {namespace} not found"
```

### Benefits

- **Prevents cheating**: Each user has different resource names
- **Deterministic**: Same user always gets same values (seeded by student ID)
- **Flexible**: Support any Jinja2 template expressions
- **Isolated**: Users can't interfere with each other's resources

### Backward Compatibility

The refactored system stores session data in TaskState.session_data (in TaskStateTable) for better data locality. The old SessionTable has been removed.

## Auto-Generation (Optional Manifest)

### Overview

If `manifest.json` is **not present**, the system automatically generates a manifest by discovering test files in the task directory. This provides **100% backward compatibility** with the old system.

### How Auto-Generation Works

1. **Scans for test files** in task directory:
   - `test_01_setup.py` → setup phase (0 points)
   - `test_02_ready.py` → ready phase (5 points)
   - `test_03_answer.py` → answer phase (10 points)
   - `test_04_challenge.py` → challenge phase (15 points)
   - `test_05_check.py` → check phase (20 points)
   - `test_06_cleanup.py` → cleanup phase (0 points, auto-run)

2. **Generates default configuration**:
   - Title: Derived from task_id (e.g., "01_test_task" → "01 Test Task")
   - Difficulty: "beginner"
   - Estimated time: 15 minutes
   - Timeout: 30 seconds per phase
   - Max attempts: 3 per phase

3. **Creates phases** for each discovered test file

### Example: Task Without Manifest

**Directory structure:**
```
02_create_namespace/
├── test_01_setup.py
├── test_04_challenge.py
├── test_05_check.py
├── test_06_cleanup.py
├── session.json
└── instruction.md
```

**Auto-generated manifest (in memory):**
```json
{
  "task_id": "02_create_namespace",
  "title": "02 Create Namespace",
  "description": "Auto-generated manifest for 02 Create Namespace",
  "difficulty": "beginner",
  "estimated_minutes": 15,
  "phases": [
    {
      "id": "setup",
      "name": "Setup",
      "test_file": "test_01_setup.py",
      "points": 0,
      "timeout_seconds": 30,
      "max_attempts": 3
    },
    {
      "id": "challenge",
      "name": "Challenge",
      "test_file": "test_04_challenge.py",
      "points": 15,
      "timeout_seconds": 30,
      "max_attempts": 3
    },
    {
      "id": "check",
      "name": "Check",
      "test_file": "test_05_check.py",
      "points": 20,
      "timeout_seconds": 30,
      "max_attempts": 3
    },
    {
      "id": "cleanup",
      "name": "Cleanup",
      "test_file": "test_06_cleanup.py",
      "points": 0,
      "auto_run": true,
      "timeout_seconds": 30,
      "max_attempts": 1
    }
  ],
  "tags": ["auto-generated"]
}
```

### When to Create manifest.json

**Use auto-generation (no manifest.json) when:**
- ✅ Migrating from old system
- ✅ Simple tasks with standard phases
- ✅ Default timeouts and points are acceptable
- ✅ Quick prototyping

**Create manifest.json when:**
- ✅ Custom phase names or descriptions needed
- ✅ Non-standard timeouts required
- ✅ Custom points distribution
- ✅ Prerequisites or tags needed
- ✅ Specific difficulty level
- ✅ Custom hints for users
- ✅ Better documentation desired

### Migration Strategy

**Phase 1: No Changes Required**
- Existing tasks work immediately with auto-generation
- No manifest.json needed
- 100% backward compatible

**Phase 2: Gradual Enhancement**
- Add manifest.json to important tasks
- Customize metadata, points, timeouts
- Improve user experience incrementally

**Phase 3: Full Migration**
- All tasks have manifest.json
- Rich metadata and documentation
- Optimal configuration

## Migration from Old System

### Old System (Implicit)
- Phases discovered by scanning test files
- No metadata about task
- No prerequisites tracking
- No points system
- Hard to understand task flow

### New System (Explicit)
- All phases declared in manifest
- Rich metadata (title, description, difficulty)
- Clear prerequisite chain
- Gamification with points
- Self-documenting

### Migration Steps

1. **Create manifest.json** in task directory
2. **List all test files** and map to phases
3. **Add metadata** (title, description, etc.)
4. **Define prerequisites** based on task order
5. **Assign points** based on difficulty
6. **Add helpful hints** for users
7. **Test** with new task handler

## Troubleshooting

### Manifest Not Found
```
Error: Manifest not found: /tmp/game01/tests/game01/01/manifest.json
```
**Solution**: Create `manifest.json` in the task directory

### Invalid Phase ID
```
Error: Invalid phase_id 'test'. Must be one of: setup, ready, challenge, check, cleanup
```
**Solution**: Use only valid phase IDs

### Missing Required Field
```
Error: Missing required field 'test_file' in phase 'check'
```
**Solution**: Add all required fields to phase configuration

### Circular Prerequisites
```
Error: Circular dependency detected: 01 -> 02 -> 01
```
**Solution**: Remove circular references in prerequisites

## Tools

### Validation Script
```bash
# Validate all manifests in a game
python tools/validate_manifests.py game01

# Validate single manifest
python tools/validate_manifests.py game01/01
```

### Generation Script
```bash
# Generate manifest from existing test files
python tools/generate_manifest.py game01/01
```

### Migration Script
```bash
# Migrate all tasks in a game
python tools/migrate_to_manifests.py game01
```

## Summary

The manifest.json system provides:
- ✅ Explicit task configuration
- ✅ Self-documenting structure
- ✅ Prerequisite management
- ✅ Gamification support
- ✅ Better user experience
- ✅ Easier maintenance

Replace implicit file scanning with declarative configuration for a more maintainable and user-friendly system.
