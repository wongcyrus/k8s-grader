# Current Phase Not Cleared After Last Phase - BUG FOUND! 🎯

**Date:** February 2, 2026  
**Status:** Fixed  
**Priority:** CRITICAL

## The New Bug

After fixing the task completion bug, we discovered another issue:

### Symptoms
1. User completes all phases
2. API returns: `{status: 'OK', message: 'All phases completed!'}`
3. User asks NPC again
4. API tries to execute 'check' phase again instead of returning COMPLETED status

### Root Cause

In `task_state_machine.py` line 128-133, when the last phase passes:

```python
# Move to next phase
next_phase = self.manifest.get_next_phase(phase_id)
if next_phase:
    self.state.current_phase_id = next_phase.id
    logger.info(f"Advanced to phase '{next_phase.id}'")
else:
    # No more phases - task ready for completion
    logger.info("No more phases - task ready for completion")
    # ← BUG: current_phase_id is still 'check'!
```

When `next_phase` is `None` (no more phases), the code doesn't clear `current_phase_id`. This means:

1. Check phase passes
2. `current_phase_id` remains 'check' (not set to None)
3. State is saved with `current_phase_id='check'`
4. `can_complete_task()` returns True
5. Task is marked as COMPLETED
6. **BUT** on the next API call, the handler sees `current_phase_id='check'` and tries to execute it again!

### The Flow

**What happens:**
```
1. execute_phase('check') → passes
2. current_phase_id = 'check' (not cleared!)
3. can_complete_task() → True
4. complete_task() → status = 'completed'
5. Save state: {status: 'completed', current_phase_id: 'check'}  ← WRONG!
6. Next call: Load state, see current_phase_id='check'
7. Try to execute 'check' again → can_execute_phase() fails because already passed
8. Return FAILED or try to re-run
```

**What should happen:**
```
1. execute_phase('check') → passes
2. current_phase_id = None (cleared!)  ← FIX
3. can_complete_task() → True
4. complete_task() → status = 'completed'
5. Save state: {status: 'completed', current_phase_id: None}  ← CORRECT!
6. Next call: Load state, see status='completed'
7. Return task_completed_response() immediately
```

## The Fix

Modified `task_state_machine.py` line 133:

```python
# Move to next phase
next_phase = self.manifest.get_next_phase(phase_id)
if next_phase:
    self.state.current_phase_id = next_phase.id
    logger.info(f"Advanced to phase '{next_phase.id}'")
else:
    # No more phases - clear current phase and task ready for completion
    self.state.current_phase_id = None  # ← FIX: Clear current_phase_id
    logger.info("No more phases - task ready for completion")
```

## Files Modified

✅ `k8s-grader/k8s-grader-api/common-layer/common/state_machine/task_state_machine.py` - Line 133: Set `current_phase_id = None` when no more phases

## Testing

After this fix:

1. Complete all phases of a task
2. Should see: `{status: 'COMPLETED', message: '🎉 Task completed!'}`
3. Ask NPC again
4. Should see: `{status: 'COMPLETED', message: '🎉 Task completed!'}` (not trying to execute check again)

## Impact

- ✅ `current_phase_id` properly cleared after last phase
- ✅ No confusion about which phase to execute
- ✅ Completed tasks stay completed
- ✅ No attempts to re-execute already passed phases

## Deployment

Ready to deploy. Single line change.

```bash
cd k8s-grader/k8s-grader-api
./deploy.sh
```

## Related Bugs

This is the THIRD bug in the task completion flow:

1. **Bug 1:** Handler using stale state variable (fixed)
2. **Bug 2:** `complete_task()` loading fresh state from DB (fixed)
3. **Bug 3:** `current_phase_id` not cleared after last phase (THIS BUG - fixed)

All three bugs needed to be fixed for task completion to work correctly!
