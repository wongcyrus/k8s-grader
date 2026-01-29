# Deployment Checklist

## Pre-Deployment Verification

### 1. Code Review ✓
- [x] All 93 tests passing
- [x] Code coverage > 60%
- [x] No syntax errors
- [x] All dependencies in requirements.txt

### 2. SAM Template Validation
- [x] template.yaml updated with new resources
- [x] All existing resources preserved
- [x] New tables defined (TaskStateTable, NpcAssignmentTable)
- [x] New function defined (TaskHandlerFunction)
- [x] Outputs section updated
- [ ] Run `sam validate` (requires SAM CLI)

### 3. Environment Variables Check
```bash
# Verify all required env vars are in template.yaml
TaskStateTable ✓
NpcAssignmentTable ✓
AccountTable ✓
ApiKeyTable ✓
TestRecordTable ✓
NpcBackgroundTable ✓
ConversationTable ✓
GameSourceTable ✓
TestResultBucket ✓
SecretHash ✓
EasterEggSheetId ✓
```

## Deployment Steps

### Step 1: Build
```bash
cd k8s-grader/k8s-grader-api
sam build
```

**Expected Output**:
- All Lambda functions built successfully
- Layers built successfully
- No build errors

### Step 2: Deploy (First Time)
```bash
sam deploy --guided
```

**Configuration Prompts**:
- Stack Name: `k8s-grader-api-dev` (or your choice)
- AWS Region: Your preferred region
- Parameter SecretHash: Use default or provide custom
- Parameter StageName: `Prod` or `Dev`
- Parameter EasterEggSheetId: Use default or provide custom
- Parameter NCPBackgroundSheetId: Use default or provide custom
- Parameter PythonVersion: `python3.14`
- Confirm changes before deploy: Y
- Allow SAM CLI IAM role creation: Y
- Disable rollback: N (keep rollback enabled)
- Save arguments to configuration file: Y
- SAM configuration file: `samconfig.toml`
- SAM configuration environment: `default`

### Step 3: Deploy (Subsequent Times)
```bash
sam deploy
```

## Post-Deployment Verification

### 1. Check Stack Status
```bash
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].StackStatus'
```

**Expected**: `CREATE_COMPLETE` or `UPDATE_COMPLETE`

### 2. Verify New Tables
```bash
# Get table names from outputs
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`TaskStateTable`].OutputValue' \
  --output text

# Verify table exists
aws dynamodb describe-table --table-name <TaskStateTable-name>
aws dynamodb describe-table --table-name <NpcAssignmentTable-name>
```

**Expected**: Table descriptions returned successfully

### 3. Verify New Function
```bash
# Get function name
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`TaskHandlerApi`].OutputValue' \
  --output text

# Test function exists
aws lambda get-function --function-name <stack-name>-TaskHandlerFunction
```

**Expected**: Function configuration returned

### 4. Test New Endpoint
```bash
# Get API endpoint from outputs
BASE_URL=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`BaseUrl`].OutputValue' \
  --output text)

# Test with API key (replace YOUR_API_KEY)
curl -H "x-api-key: YOUR_API_KEY" \
  "${BASE_URL}task?action=start&game=game01&task=01"
```

**Expected Response**:
```json
{
  "statusCode": 200,
  "body": {
    "status": "success",
    "data": {
      "taskId": "game01-01",
      "state": "SETUP",
      ...
    }
  }
}
```

### 5. Verify Legacy Endpoints Still Work
```bash
# Test old /game-task endpoint
curl -H "x-api-key: YOUR_API_KEY" \
  "${BASE_URL}game-task?game=game01&npc=npc01"

# Test old /grader endpoint
curl -H "x-api-key: YOUR_API_KEY" \
  "${BASE_URL}grader?game=game01&npc=npc01"
```

**Expected**: Both endpoints return successful responses

### 6. Check CloudWatch Logs
```bash
# View TaskHandlerFunction logs
aws logs tail /aws/lambda/<stack-name>-TaskHandlerFunction --follow

# View GameTaskFunction logs (legacy)
aws logs tail /aws/lambda/<stack-name>-GameTaskFunction --follow
```

**Expected**: No errors in logs

## Rollback Plan

### If Deployment Fails
```bash
# SAM will automatically rollback on failure
# Check rollback status
aws cloudformation describe-stack-events \
  --stack-name k8s-grader-api-dev \
  --max-items 20
```

### Manual Rollback
```bash
# Delete the failed stack
aws cloudformation delete-stack --stack-name k8s-grader-api-dev

# Redeploy previous version
git checkout <previous-commit>
sam deploy
```

## Monitoring

### CloudWatch Metrics to Watch
- Lambda invocations (TaskHandlerFunction)
- Lambda errors
- Lambda duration
- DynamoDB read/write capacity
- API Gateway 4xx/5xx errors

### Set Up Alarms
```bash
# Example: Alert on Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name TaskHandlerErrors \
  --alarm-description "Alert on TaskHandler errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=<stack-name>-TaskHandlerFunction
```

## Troubleshooting

### Issue: Build Fails
**Solution**: Check Python version, dependencies, and layer build

### Issue: Deploy Fails with IAM Errors
**Solution**: Ensure AWS credentials have CloudFormation, Lambda, DynamoDB, S3, IAM permissions

### Issue: Function Timeout
**Solution**: Check CloudWatch logs, increase timeout in template.yaml if needed

### Issue: DynamoDB Access Denied
**Solution**: Verify IAM policies in template.yaml include new tables

### Issue: API Returns 403
**Solution**: Check API key is valid and associated with usage plan

## Success Criteria

- [x] Stack deployed successfully
- [ ] All new resources created
- [ ] New /task endpoint responds correctly
- [ ] Legacy endpoints still work
- [ ] No errors in CloudWatch logs
- [ ] All tests pass in deployed environment
- [ ] Monitoring and alarms configured

## Next Steps After Deployment

1. Create sample manifest.json files for tasks
2. Update frontend plugin to use new /task endpoint
3. Migrate one task to test end-to-end flow
4. Monitor performance and errors
5. Gradually migrate remaining tasks
6. Plan deprecation of legacy endpoints
