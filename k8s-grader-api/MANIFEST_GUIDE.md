# Task Manifest Guide

## Overview

The `manifest.json` file is a declarative configuration that defines a Kubernetes learning task. It replaces the old implicit file-based discovery system with an explicit, self-documenting format.

## Location

Each task directory must contain a `manifest.json` file:

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
