# Changelog

## Recent Bug Fixes (2026-01-31)

### 1. Missing K8s Credentials in Session Data
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
- Integration tests not running after deployment
- Stack name extraction bug (concatenating multiple names)

**Fixes:**
- Added `:skip-covered` to coverage report (no pager)
- Integration tests now run automatically after deployment
- Fixed stack name extraction with `head -n 1`

**Files Modified:**
- `deploy.sh` - Added integration test execution, fixed stack name
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

### Tests
- `tests/test_file.py` (new)
- `tests/integration/test_api_integration.py`

### Scripts
- `deploy.sh`
- `run_tests.sh`
