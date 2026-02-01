# Test Data Cleanup Script

## Purpose

Clean up any leftover test API keys and data from integration test runs.

## When to Use

- After failed test runs (if cleanup didn't complete)
- To verify cleanup is working
- To manually clean up old test data
- Before important deployments

## Usage

### 1. Dry Run (Recommended First)

See what would be deleted without actually deleting:

```bash
python tests/integration/cleanup_test_keys.py --dry-run
```

Output:
```
🔍 Searching for test API keys...
📋 Found 3 test API keys in API Gateway:
   • integration-test-abc@example.com (ID: xyz123)
   • integration-test-def@example.com (ID: abc456)
   • integration-test-ghi@example.com (ID: def789)

🔍 DRY RUN - No keys will be deleted

🔍 Searching for test data in DynamoDB...
📋 Found 3 test users:
   • integration-test-abc@example.com
   • integration-test-def@example.com
   • integration-test-ghi@example.com

🔍 DRY RUN - No data will be deleted

SUMMARY
🔍 DRY RUN: Would clean up 6 items
```

### 2. Actual Cleanup

Delete the test data:

```bash
python tests/integration/cleanup_test_keys.py
```

Output:
```
🗑️  Deleting 3 API keys...
   ✓ Deleted: integration-test-abc@example.com
   ✓ Deleted: integration-test-def@example.com
   ✓ Deleted: integration-test-ghi@example.com

🗑️  Cleaning up 3 test users...
   Cleaning: integration-test-abc@example.com
      ✓ Cleaned AccountTable
      ✓ Cleaned ApiKeyTable
   ...

SUMMARY
✅ Cleaned up 6 items
All test data has been removed!
```

## Options

### Clean Only API Gateway

```bash
python tests/integration/cleanup_test_keys.py --api-gateway-only
```

### Clean Only DynamoDB

```bash
python tests/integration/cleanup_test_keys.py --dynamodb-only
```

### Custom Stack Name

```bash
python tests/integration/cleanup_test_keys.py --stack-name my-custom-stack
```

### Custom Region

```bash
python tests/integration/cleanup_test_keys.py --region us-west-2
```

### Combined Options

```bash
python tests/integration/cleanup_test_keys.py \
  --stack-name my-stack \
  --region us-west-2 \
  --dry-run
```

## What Gets Cleaned

### API Gateway
- All API keys with names starting with `integration-test-`

### DynamoDB Tables
- **AccountTable**: Test user accounts
- **ApiKeyTable**: API key mappings

## Safety Features

1. **Dry Run Mode**: Always test first with `--dry-run`
2. **Pattern Matching**: Only deletes items matching `integration-test-*`
3. **Error Handling**: Continues even if some deletions fail
4. **Detailed Output**: Shows exactly what's being deleted

## Verification

After cleanup, verify no test data remains:

```bash
# Check API Gateway
aws apigateway get-api-keys --name-query "integration-test-"
# Should return: []

# Check DynamoDB
aws dynamodb scan --table-name AccountTable \
  --filter-expression "begins_with(email, :prefix)" \
  --expression-attribute-values '{":prefix":{"S":"integration-test-"}}'
# Should return: {"Items": [], "Count": 0}
```

## When Cleanup Isn't Needed

The integration tests have **automatic cleanup** that runs after each test session. You only need this script if:

- Tests were interrupted (Ctrl+C, crash, etc.)
- Cleanup failed due to permissions
- You want to verify cleanup is working
- You're debugging cleanup issues

## Troubleshooting

### "Stack not found"

```bash
# Check stack name
aws cloudformation describe-stacks --stack-name k8s-grader-api-dev

# Use correct stack name
python tests/integration/cleanup_test_keys.py --stack-name correct-name
```

### "Access Denied"

Ensure your AWS credentials have permissions for:
- `apigateway:GetApiKeys`
- `apigateway:DeleteApiKey`
- `dynamodb:Scan`
- `dynamodb:DeleteItem`
- `cloudformation:DescribeStacks`

### "No test data found"

This is good! It means:
- Automatic cleanup is working
- No leftover test data exists

## Examples

### Check for leftover data

```bash
python tests/integration/cleanup_test_keys.py --dry-run
```

### Clean everything

```bash
python tests/integration/cleanup_test_keys.py
```

### Clean only API Gateway (faster)

```bash
python tests/integration/cleanup_test_keys.py --api-gateway-only
```

### Clean from different region

```bash
python tests/integration/cleanup_test_keys.py --region eu-west-1
```

## Integration with CI/CD

Add to your CI/CD pipeline for cleanup:

```yaml
# GitHub Actions
- name: Cleanup Test Data
  if: always()  # Run even if tests fail
  run: |
    cd k8s-grader-api
    python tests/integration/cleanup_test_keys.py
```

```bash
# Jenkins
post {
    always {
        sh 'python tests/integration/cleanup_test_keys.py'
    }
}
```

## Manual Cleanup (Alternative)

If the script doesn't work, clean up manually:

```bash
# List all test API keys
aws apigateway get-api-keys --name-query "integration-test-" \
  --query 'items[*].[id,name]' --output table

# Delete specific key
aws apigateway delete-api-key --api-key <key-id>

# Delete all test keys (bash)
aws apigateway get-api-keys --name-query "integration-test-" \
  --query 'items[*].id' --output text | \
  xargs -I {} aws apigateway delete-api-key --api-key {}

# Clean DynamoDB
aws dynamodb delete-item --table-name AccountTable \
  --key '{"email":{"S":"integration-test-xxx@example.com"}}'
```

## Summary

- ✅ Safe to run anytime
- ✅ Dry run mode available
- ✅ Only deletes test data
- ✅ Detailed output
- ✅ Error handling
- ✅ Multiple options

**Recommended workflow:**
1. Run with `--dry-run` first
2. Review what will be deleted
3. Run without `--dry-run` to clean up
4. Verify cleanup completed

```bash
# Quick cleanup
python tests/integration/cleanup_test_keys.py --dry-run  # Check
python tests/integration/cleanup_test_keys.py            # Clean
```
