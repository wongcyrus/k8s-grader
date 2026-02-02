# Changelog

## Recent Changes (February 2026)

### 1. Answer Phase Skip in Production 🎮
**Issue:** Answer phase was auto-deploying solutions, allowing players to complete tasks without doing any work.

**Root Cause:** The answer phase (test_03_answer.py) automatically deploys the solution, which defeats the purpose of learning.

**Fix:** Added direct phase check in `pytest.py` to skip answer phase in production:
```python
if test_phase == GamePhrase.ANSWER:
    logger.info(f"Skipping answer phase for {game}/{task} - answer phase is for development only")
    return TestResult.NO_TESTS_COLLECTED
```

**Files Modified:**
- `common-layer/common/pytest.py` - Skip answer phase
- `common-layer/common/state_machine/task_state_machine.py` - Handle NO_TESTS_COLLECTED as success
- `tests/test_answer_phase_skip.py` - Added 8 behavior tests

**Impact:** Players must do actual work to earn points. Answer phase is skipped, check phase validates player's work.

---

### 2. Instruction Rendering with Jinja2 Templates 📝
**Issue:** Instructions contained template variables like `{{namespace}}` that weren't being replaced with actual values.

**Fix:** Added Jinja2 template rendering in all response functions:
```python
def render_template(template: str, session_data: Dict[str, Any]) -> str:
    env = Environment()
    jinja_template = env.from_string(template)
    return jinja_template.render(session_data)
```

**Files Modified:**
- `task-handler/app.py` - Added render_template function and applied to all responses
- `common-layer/common/models/task_manifest.py` - Read instruction.md for real task instructions

**Impact:** Players see personalized instructions with actual values (e.g., `{{namespace}}` → `blissfularyabhata2developer`).

---

### 3. Duplicate Points Bug Fix 🔥
**Issue:** Users could receive duplicate points by re-executing already-passed phases.

**Root Cause:** `can_execute_phase()` didn't check if a phase was already passed before allowing re-execution.

**Fix:** Added check to prevent re-execution of passed phases:
```python
phase_state = self.state.get_phase_state(phase_id)
if phase_state and phase_state.status == PhaseStatus.PASSED:
    return False, f"Phase '{phase_id}' already passed"
```

**Files Modified:**
- `common-layer/common/state_machine/task_state_machine.py` - Added passed phase check
- `tests/test_task_state_machine.py` - Added test for duplicate prevention

**Impact:** Prevents unfair scoring advantages and data integrity issues.

---

### 4. Reset Game Auto-Confirm for Dev Stacks 🚀
**Issue:** Development workflow required manual confirmation for every game reset during testing.

**Fix:** Automatically skip confirmation for stacks ending with `-dev`:
```python
if not stack_name.endswith("-dev"):
    confirm = input("⚠️  This will delete ALL game state...")
else:
    print("ℹ️  Development stack detected - skipping confirmation prompt")
```

**Files Modified:**
- `tools/reset_game.py` - Added auto-confirm logic for dev stacks

**Impact:** Faster development workflow while preserving safety for production stacks.

---

### 5. Easter Egg Encouragement Feature 🎉
**Issue:** Failed tests only showed report URLs without encouragement, reducing player motivation.

**Fix:** Added easter egg links to failed and abandoned responses:
- Fetches motivational links from Google Sheets
- Returns random encouragement link based on test result
- Fixed UnboundLocalError in `get_easter_egg_link()`

**Files Modified:**
- `task-handler/app.py` - Added easter_egg_url to failure responses
- `common-layer/common/google_spreadsheet.py` - Fixed error handling

**Impact:** Players receive encouragement when facing failures, improving motivation.

---

### 6. S3 Report Upload Optimization 💰
**Issue:** Test reports were uploaded to S3 even when tests passed, wasting storage and bandwidth.

**Fix:** Only upload reports when tests fail:
```python
if test_result != TestResult.OK:
    report_url = self._upload_report(...)
else:
    logger.info(f"Phase {phase.id} passed: {test_result.name}")
```

**Files Modified:**
- `common-layer/common/services/test_runner.py` - Conditional S3 upload
- `tests/test_test_runner.py` - Added tests for upload behavior

**Impact:** Reduced S3 costs, faster response times for successful tests, cleaner S3 bucket.

---

### 7. Cache Invalidation for Game Source Changes 🔄
**Issue:** Lambda continued using cached tests even after game source URL changed in database.

**Fix:** Added cache invalidation logic:
- Store source URL in `/tmp/{game}_source.txt`
- Compare on each invocation
- Clear cache if source changed
- Download fresh tests from new source

**Files Modified:**
- `common-layer/common/pytest.py` - Added cache invalidation logic

**Impact:** Automatic cache updates when game source changes, no manual intervention needed.

---

### 8. Pytest Warnings Fix 🧹
**Issues:**
- `PytestConfigWarning: Unknown config option: timeout`
- `PytestUnknownMarkWarning: Unknown pytest.mark.integration`

**Fixes:**
- Added `pytest-timeout==2.2.0` to `requirements-dev.txt`
- Registered `integration` marker in `tests/integration/pytest.ini`
- Kept `pytest-timeout` in production (needed for k8s-game-rule tests)

**Files Modified:**
- `requirements-dev.txt` - Added pytest-timeout
- `tests/integration/pytest.ini` - Registered integration marker
- `REQUIREMENTS.md` - Documented requirements separation

**Impact:** Clean test output, no warnings, proper separation of production vs development requirements.

---

### 9. Requirements Separation 📦
**Issue:** Production and development requirements were mixed, bloating Lambda deployment.

**Fix:** Separated into two files:
- `common-layer/requirements.txt` - 11 production packages
- `requirements-dev.txt` - Additional development tools

**Production packages:** cfnresponse, requests, kubernetes, boto3, names_generator, Jinja2, requests-toolbelt, cryptography, pytest, pytest-html, pytest-timeout

**Development packages:** pytest-cov, pytest-mock, pytest-order, pytest-xdist, moto, black, flake8, mypy, ipython

**Files Modified:**
- `common-layer/requirements.txt` - Production only
- `requirements-dev.txt` - Development tools
- `REQUIREMENTS.md` - Comprehensive documentation

**Impact:** Smaller Lambda deployment, faster cold starts, proper separation of concerns.

---

## Previous Bug Fixes (2026-02-01)

### 1. Race Condition in NPC Assignment 🔥 CRITICAL
**Issue:** When a player quickly chatted with 2 NPCs (e.g., NPC-A and NPC-B), both NPCs could try to assign tasks simultaneously, resulting in incorrect locking behavior where the second NPC would overwrite the first NPC's assignment.

**Root Cause:** Classic **check-then-act** pattern without atomic operations:
```python
# Step 1: Check (not atomic)
assigned_npc = get_assigned_npc(email, game)
if assigned_npc and assigned_npc != npc:
    return False

# Step 2: Act (separate operation - race condition!)
assign_task(email, game, npc, task_id)
```

**Fix:** Implemented 3-layer protection:

1. **Backend - Atomic DynamoDB writes**: Used conditional expressions to ensure only one NPC can assign at a time
   ```python
   self.assignment_table.put_item(
       Item={...},
       ConditionExpression='attribute_not_exists(email) AND attribute_not_exists(game)'
   )
   ```

2. **Backend - Assign-first pattern**: Changed flow to assign NPC atomically BEFORE creating task state, with proper rollback on failure

3. **Frontend - Request debouncing**: Added `pendingRequest` flag to prevent multiple simultaneous AJAX calls

**Files Modified:**
- `common-layer/common/database/repositories.py` - Added atomic conditional write to `assign_task()`
- `common-layer/common/services/task_service.py` - Changed `start_task()` to assign-first pattern with rollback
- `k8s-isekai/js/plugins/NpcK8sPluginCommand.js` - Added `pendingRequest` flag
- `tests/test_repositories.py` - Added atomic operation tests
- `tests/test_task_service.py` - Added race condition prevention test
- `GAME_LOGIC.md` - Added comprehensive race condition documentation

**User Experience:**
- Before: Second NPC could overwrite first NPC's assignment, causing confusion ❌
- After: Only first NPC succeeds, second gets clear error: "Complete task from NPC-A first!" ✅

**Test Coverage:**
- `test_race_condition_prevention` - Verifies two NPCs cannot assign simultaneously
- `test_assign_task_atomic_operation` - Tests atomic DynamoDB operation
- `test_reassign_npc` - Confirms atomic operation prevents overwrites
- All 116 unit tests passing ✅

---

## Previous Bug Fixes (2026-01-31)

### 1. Missing Task Instructions in Game 🎮
**Issue:** Players received no instructions when starting a task. The `$instruction` field was empty, leaving players confused about what to do.

**Root Cause:** The task description from the manifest was never added to the session data. The `$instruction` field was expected but never populated.

**Fix:** Added task description from manifest to session data when starting a task:
```python
session_data['$instruction'] = manifest.description
```

**Files Modified:**
- `common-layer/common/services/task_service.py` - Added instruction to session data

**User Experience:**
- Before: No instructions shown, players confused ❌
- After: Clear task description shown when task starts ✅

---

### 2. Task Stuck Forever After Max Attempts Reached 🔥 CRITICAL
**Issue:** When a phase (like setup) failed the maximum number of times, the task would get stuck forever and the NPC would remain locked permanently. Users had no way to retry.

**Root Cause:** The state machine detected `max_attempts_reached` but there was no handling for this condition. The task remained in IN_PROGRESS status and the NPC assignment was never cleared.

**Fix:** Added complete task abandonment and retry flow:
1. Detect when max attempts are reached
2. Mark task as ABANDONED
3. Clear NPC assignment (no lock - allows immediate retry)
4. Return clear message to user that they can try again
5. **When player retries:** Detect ABANDONED status, delete old state, start fresh

**Files Modified:**
- `common-layer/common/state_machine/task_state_machine.py` - Added `fail_task()` method
- `common-layer/common/services/task_service.py` - Added `abandon_task()` method
- `task-handler/app.py` - Added max attempts detection, abandonment handling, and retry logic

**User Experience:**
- Before: Task stuck forever, NPC locked, no way to retry ❌
- After: Clear message, NPC unlocked, can retry immediately with fresh start ✅

**Retry Flow:**
1. Task abandoned → Status = ABANDONED, NPC unlocked
2. Player talks to same NPC → System detects ABANDONED status
3. Old state deleted → Fresh task started
4. Player can try again from the beginning

---

### 2. TypeError: run_tests() Unexpected Keyword Argument 'timeout'
**Issue:** Test execution failed with `TypeError: run_tests() got an unexpected keyword argument 'timeout'`.

**Root Cause:** The `test_runner.py` was calling `run_tests()` with a `timeout` parameter from the phase configuration, but the function didn't accept this parameter. It only used a hardcoded `PYTEST_TIMEOUT_SECONDS` constant.

**Fix:** Added optional `timeout` parameter to `run_tests()` function that defaults to `PYTEST_TIMEOUT_SECONDS` if not provided.

**Files Modified:**
- `common-layer/common/pytest.py` - Added `timeout` parameter with default value

---

### 2. Missing K8s Credentials in Session Data
**Issue:** New tasks failed with "No endpoint in session data" error during first phase execution.

**Root Cause:** K8s credentials (endpoint, certificates, keys) were not being added to session data when starting new tasks.

**Fix:** Credentials are now **always** added to session data on every request, whether starting a new task or continuing an existing one.

**Files Modified:**
- `task-handler/app.py` - Always inject credentials and save state
- `common-layer/common/handler.py` - Better API key error handling

---

### 2. KeyError: '$instruction' in Test Execution
**Issue:** Test execution failed with `KeyError: '$instruction'` when trying to delete a non-existent key.

**Root Cause:** The `create_json_input()` function unconditionally tried to delete `$instruction` even when it didn't exist.

**Fix:** Changed to filter ALL metadata keys (starting with `$`) safely using list comprehension.

**Files Modified:**
- `common-layer/common/file.py` - Filter all `$` keys safely
- `tests/test_file.py` - Added 5 new unit tests

---

### 3. Deploy Script Improvements
**Issues:**
- Coverage report required pressing 'q' to continue
- AWS CLI output required pressing a key to continue (pager)
- Integration tests not running after deployment
- Stack name extraction bug (concatenating multiple names)

**Fixes:**
- Added `:skip-covered` to coverage report (no pager)
- Added `--no-cli-pager` to AWS CLI commands (no pager)
- Integration tests now run automatically after deployment (if TEST_API_KEY is set)
- Fixed stack name extraction with `head -n 1`
- Better messaging when TEST_API_KEY is not set

**Files Modified:**
- `deploy.sh` - Added `--no-cli-pager`, improved integration test handling
- `run_tests.sh` - Added `:skip-covered` option

**New Deploy Options:**
```bash
./deploy.sh                    # Full automated deployment
./deploy.sh --skip-integration # Skip integration tests
./deploy.sh --skip-tests       # Skip unit tests
./deploy.sh --guided           # Interactive setup
```

---

### 4. Test Separation
**Issue:** Unit tests and integration tests were mixed, causing confusion about when to run them.

**Fix:** Proper test markers and separation:
- Unit tests (111 tests) - Run before deployment with `-m "not integration"`
- Integration tests (13 tests) - Run after deployment with `@pytest.mark.integration`

**Files Modified:**
- `run_tests.sh` - Exclude integration tests
- `tests/integration/test_api_integration.py` - Added markers to all test classes

---

### 5. Invalid API Key Error Messages
**Issue:** Invalid API keys showed cryptic "Internal error" messages.

**Fix:** Now shows user-friendly message: "Invalid or expired API key. Please generate a new one."

**Files Modified:**
- `task-handler/app.py` - Better ValueError handling
- `common-layer/common/handler.py` - Catch all decryption errors
- `tests/integration/test_api_integration.py` - Updated test expectations

---

## Deployment

### Quick Deploy
```bash
cd k8s-grader/k8s-grader-api
./deploy.sh
```

This will:
1. Run 111 unit tests
2. Build application
3. Deploy to AWS
4. Run 13 integration tests
5. Show next steps

### Manual Steps
```bash
bash run_tests.sh              # Unit tests only
sam build && sam deploy        # Build and deploy
bash run_integration_tests.sh  # Integration tests
```

---

## Test Summary

- **Total Tests:** 153 tests
- **Unit Tests:** 138 (run before deployment)
- **Integration Tests:** 15 (run after deployment)

---

## Files Changed Summary

### Core Fixes
- `task-handler/app.py`
- `common-layer/common/handler.py`
- `common-layer/common/file.py`
- `common-layer/common/pytest.py`

### Tests
- `tests/test_file.py` (new)
- `tests/integration/test_api_integration.py`

### Scripts
- `deploy.sh`
- `run_tests.sh`
