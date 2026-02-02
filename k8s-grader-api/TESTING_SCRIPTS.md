# Testing Scripts

This directory contains E2E test scripts for verifying the k8s-grader-api functionality.

## Available Scripts

### 1. test_complete_flow.sh ⭐ **RECOMMENDED**

**Fully self-contained E2E test** - Tests the complete fail → fix → pass flow.

**Features:**
- ✅ Automatically gets API URL from CloudFormation
- ✅ Automatically gets API key from DynamoDB
- ✅ Automatically cleans up test namespaces
- ✅ Automatically resets game state
- ✅ Tests Task #1 (01_default_namespace)
- ✅ Tests Task #2 fail (namespace doesn't exist)
- ✅ Automatically creates namespace
- ✅ Tests Task #2 pass (namespace exists)
- ✅ Shows all user-facing messages
- ✅ Cleans up after test

**Usage:**
```bash
cd k8s-grader/k8s-grader-api
./test_complete_flow.sh
```

**Configuration (optional):**
```bash
# Override defaults if needed
EMAIL="your-email@example.com" \
GAME="game01" \
STACK_NAME="k8s-grader-api-dev" \
REGION="us-east-1" \
./test_complete_flow.sh
```

**What It Tests:**
1. Task completion when all phases pass ✅
2. Task failure when requirements not met ✅
3. Task retry after fixing issues ✅
4. State management across attempts ✅
5. **Bug 4 fix:** No misleading "All phases completed!" on failure ✅

---

### 2. test_multiple_tasks.sh

**Multi-task E2E test** - Completes multiple tasks with different NPCs.

**Features:**
- Tests 5 tasks in sequence
- Uses different NPCs for each task
- Verifies task completion across multiple scenarios

**Usage:**
```bash
cd k8s-grader/k8s-grader-api

# Set environment variables
export API_BASE_URL="https://your-api.execute-api.us-east-1.amazonaws.com/Prod"
export API_KEY="your-api-key"
export EMAIL="developer@example.com"

# Run test
./test_multiple_tasks.sh
```

**Note:** This script requires manual configuration. For automatic setup, use `test_complete_flow.sh` instead.

---

## Test Output

All scripts show:
- ✅ Status of each API call
- 📝 User-facing messages
- 🎉 Task completion
- ❌ Failures with clear messages
- 📊 Final summary

### Example Output:

```
╔════════════════════════════════════════════════════════════════╗
║  Step 4: Task #1 - 01_default_namespace (NPC: Aiden)          ║
╚════════════════════════════════════════════════════════════════╝

  Call #1
    Status: STARTED
    Message: "Initialize the task environment"
    ✅ Task started
    
  Call #2
    Status: OK
    Message: "Continue to next phase"
    ✅ Phase passed
    
  Call #3
    Status: COMPLETED
    Message: "🎉 Task completed! You earned 20 points!"
    🎉 Task #1 completed!
```

---

## Troubleshooting

### API Key Not Found

If you see:
```
❌ No API key found for developer@example.com
```

Generate an API key:
```bash
cd k8s-grader/k8s-grader-api
./generate_test_api_key.sh
```

### CloudFormation Stack Not Found

If you see:
```
❌ Failed to get API URL from stack
```

Check your stack name:
```bash
aws cloudformation list-stacks --region us-east-1 | grep k8s-grader
```

Then set the correct stack name:
```bash
STACK_NAME="your-stack-name" ./test_complete_flow.sh
```

### Namespace Already Exists

The scripts automatically clean up namespaces. If you see issues, manually delete:
```bash
kubectl delete namespace blissfularyabhata2developer
```

---

## What These Tests Verify

### Bug Fixes Verified

All test scripts verify the 4 critical bug fixes:

1. **Bug 1:** Handler uses updated state (not stale) ✅
2. **Bug 2:** No database eventual consistency issues ✅
3. **Bug 3:** Phase IDs cleared after completion ✅
4. **Bug 4:** No misleading "All phases completed!" when tests fail ✅

### Game Flow Verified

- ✅ Tasks start correctly
- ✅ Phases execute in order
- ✅ Tasks complete after all phases pass
- ✅ Tasks fail when requirements not met
- ✅ Tasks can be retried after fixing issues
- ✅ State management works across attempts
- ✅ NPCs lock correctly after completion
- ✅ Different NPCs can assign next tasks

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Setup kubectl
        uses: azure/setup-kubectl@v1
      
      - name: Run E2E Test
        run: |
          cd k8s-grader/k8s-grader-api
          ./test_complete_flow.sh
```

---

## Best Practices

### For Development

Use `test_complete_flow.sh` - it's fully automated and requires no setup.

### For CI/CD

Use `test_complete_flow.sh` in your pipeline - it handles everything automatically.

### For Manual Testing

Use `test_complete_flow.sh` and watch the output to see all user-facing messages.

### For Load Testing

Use `test_multiple_tasks.sh` to test multiple tasks in sequence.

---

## Related Documentation

- [CHANGELOG.md](docs/CHANGELOG.md) - All bug fixes and changes
- [TESTING_GUIDE.md](docs/TESTING_GUIDE.md) - Complete testing guide
- [Bug Fix Archive](docs/bug-fixes-feb-2026/) - Detailed bug analysis

---

**Last Updated:** February 2, 2026  
**Status:** All tests passing ✅
