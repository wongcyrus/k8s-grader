# Changelog

## Recent Bug Fixes (2026-01-31)

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

- **Total Tests:** 124 tests
- **Unit Tests:** 111 (run before deployment)
- **Integration Tests:** 13 (run after deployment)

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
