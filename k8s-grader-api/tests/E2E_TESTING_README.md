# End-to-End Game Flow Testing

Automated tests to verify the complete game flow works correctly from start to finish.

## Available NPCs

- Aiden
- AI
- Alice
- Carl
- El
- Herl

## Test Scripts

### 1. Bash Script (Quick & Simple)

**File:** `test_game_flow.sh`

**Usage:**
```bash
# Set environment variables
export API_BASE_URL='https://xxx.execute-api.us-east-1.amazonaws.com/Prod'
export API_KEY='your-api-key-here'

# Optional
export EMAIL='test@example.com'
export GAME='game01'
export TASK='01_default_namespace'
export NPC='Aiden'

# Run test
./test_game_flow.sh
```

**What it tests:**
- ✅ Task starts correctly
- ✅ Phases execute in order (setup → answer → check)
- ✅ No re-execution of already passed phases
- ✅ Task completes after all phases pass
- ✅ Task stays completed on subsequent calls
- ❌ Detects bugs in phase transitions

### 2. Python Script (Detailed & Flexible)

**File:** `tests/test_game_flow_e2e.py`

**Usage:**
```bash
# Set environment variables
export API_BASE_URL='https://xxx.execute-api.us-east-1.amazonaws.com/Prod'
export API_KEY='your-api-key-here'
export TEST_EMAIL='test@example.com'

# Run test
python tests/test_game_flow_e2e.py
```

**Features:**
- Detailed logging of each API call
- JSON response analysis
- Multiple NPC testing
- Comprehensive bug detection
- Easy to extend for more test cases

## What the Tests Detect

### Bug 1: "All phases completed" but task not COMPLETED
**Symptom:** API returns message "All phases completed!" but status is 'OK' instead of 'COMPLETED'

**Expected:** After last phase passes, status should be 'COMPLETED'

### Bug 2: Re-executing already passed phases
**Symptom:** After a phase passes, the next API call tries to execute the same phase again

**Expected:** Each phase should only execute once, then move to next phase

### Bug 3: Task not completing
**Symptom:** All phases pass but task never reaches COMPLETED status

**Expected:** After all required phases pass, task should be marked as COMPLETED

### Bug 4: Wrong phase after completion
**Symptom:** After task is COMPLETED, subsequent calls return FAILED or try to execute phases

**Expected:** After COMPLETED, all subsequent calls should return COMPLETED status

## Expected Flow

```
Call 1: {status: 'STARTED', current_phase: 'setup'}
Call 2: {status: 'OK', current_phase: 'answer', message: '<answer description>'}
Call 3: {status: 'OK', current_phase: 'check', message: '<check description>'}
Call 4: {status: 'COMPLETED', message: '🎉 Task completed! You earned X points!'}
Call 5: {status: 'COMPLETED', message: '🎉 Task completed! You earned X points!'}
```

## Debugging

If tests fail, check:

1. **CloudWatch Logs:**
   ```bash
   aws logs tail /aws/lambda/k8s-grader-api-dev-TaskHandlerFunction-XXX --follow
   ```

2. **DynamoDB State:**
   ```bash
   aws dynamodb get-item \
     --table-name TaskStateTable-dev \
     --key '{"email":{"S":"test@example.com"},"gameTask":{"S":"game01#01_default_namespace"}}'
   ```

3. **API Response:**
   Look at the detailed JSON responses in the test output

## Common Issues

### Issue: "Phase already passed" error
**Cause:** `current_phase_id` not updated after phase passes
**Fix:** Ensure `execute_phase` updates `current_phase_id` to next phase

### Issue: Task stays "in_progress" after all phases pass
**Cause:** `complete_task()` not being called or failing
**Fix:** Check `can_complete_task()` logic and ensure state is passed correctly

### Issue: Random chat responses
**Note:** The API has a 30% chance of returning random chat ("..."). The test scripts handle this by retrying.

## Running After Deployment

```bash
# 1. Deploy the fix
cd k8s-grader/k8s-grader-api
./deploy.sh

# 2. Get API URL and key from CloudFormation outputs
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs'

# 3. Set environment variables
export API_BASE_URL='<BaseUrl from outputs>'
export API_KEY='<generate using keygen endpoint>'

# 4. Run test
./test_game_flow.sh
```

## Success Criteria

✅ All phases execute in order without re-execution
✅ Task completes after last phase passes
✅ Task stays completed on subsequent calls
✅ No FAILED status after successful completion
✅ No "Phase already passed" errors

## Extending Tests

To add more test cases, edit `test_game_flow_e2e.py`:

```python
# Test different tasks
tester.test_complete_task_flow(game="game01", task_id="02_create_namespace", npc="Alice")

# Test multiple NPCs
tester.test_multiple_npcs(game="game01")

# Test error scenarios
# ... add custom test methods
```
