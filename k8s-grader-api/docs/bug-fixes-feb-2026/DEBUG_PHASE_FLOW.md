# Debug: Phase Flow Analysis

## Expected Flow

### Task with 3 phases: setup → answer → check

**Call 1: Start task**
- State: `current_phase_id = 'setup'`, `status = 'in_progress'`
- Response: `{status: 'STARTED', current_phase: 'setup'}`

**Call 2: Execute setup**
- Execute 'setup' phase → passes
- State updated: `current_phase_id = 'answer'` (moved to next)
- State saved
- Response: `{status: 'OK', current_phase: 'answer', message: '<answer description>'}`

**Call 3: Execute answer**
- Execute 'answer' phase → passes
- State updated: `current_phase_id = 'check'` (moved to next)
- State saved
- Response: `{status: 'OK', current_phase: 'check', message: '<check description>'}`

**Call 4: Execute check**
- Execute 'check' phase → passes
- State updated: `current_phase_id = None` (no more phases)
- State saved
- Check `can_complete_task()` → True
- Call `complete_task()` → `status = 'completed'`
- Response: `{status: 'COMPLETED', message: '🎉 Task completed!'}`

**Call 5: After completion**
- Load state: `status = 'completed'`
- Handler checks at line 119: `if state.status == TaskStatus.COMPLETED`
- Response: `{status: 'COMPLETED', message: '🎉 Task completed!'}`

## Actual Buggy Flow (User Reports)

**Call 1: Start task**
- ✅ Works correctly

**Call 2: Execute setup**
- ✅ Setup passes
- ❌ But shows "All phases completed!" instead of answer description?

**Call 3: Try to continue**
- ❌ Goes back to check phase?

## Hypothesis

The user says "this bug happen in all stages one by one". This could mean:

1. **After EVERY phase**, it shows "All phases completed!" (wrong message)
2. **After EVERY phase**, the next call tries to re-execute the same phase (wrong phase)

## Root Cause Analysis

### Issue 1: Wrong Message
`phase_passed_response` line 271:
```python
next_phase = manifest.get_next_phase(state.current_phase_id) if state.current_phase_id else None
```

After 'setup' passes, `current_phase_id` is updated to 'answer'.
So `get_next_phase('answer')` returns 'check'.
Message should be check description, not "All phases completed!".

**This should work correctly!**

### Issue 2: Re-executing Same Phase
After 'setup' passes, `current_phase_id = 'answer'`.
Next call should execute 'answer', not 'setup'.

**This should also work correctly!**

## Possible Issues

1. **State not being saved properly** - DynamoDB write fails?
2. **State being loaded incorrectly** - Reading old state?
3. **Race condition** - Multiple API calls at same time?
4. **Caching issue** - Lambda caching old state?
5. **Logic error in get_next_phase** - Returns wrong phase?

## Need More Information

To debug, we need to see:
1. The exact sequence of API responses
2. The DynamoDB state after each call
3. CloudWatch logs showing state transitions
