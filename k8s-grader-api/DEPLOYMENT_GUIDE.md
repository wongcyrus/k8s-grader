# Deployment Guide

## Overview
This guide walks through deploying the refactored K8s Grader API to AWS using SAM CLI.

## Pre-Deployment Checklist

Before deploying, ensure you have completed:

### Code Readiness
- [x] All 93 tests passing (`./run_tests.sh`)
- [x] Code coverage at 61% overall
- [x] No syntax errors or linting issues
- [x] All dependencies listed in requirements.txt files

### Infrastructure Readiness
- [x] SAM template validated (`sam validate`)
- [x] New resources defined (TaskStateTable, NpcAssignmentTable, TaskHandlerFunction)
- [x] Legacy resources removed (5 tables/functions cleaned up)
- [x] IAM policies configured with least privilege

### Configuration Readiness
- [ ] AWS credentials configured (`aws configure`)
- [ ] SAM CLI installed (`sam --version`)
- [ ] Docker installed and running (for `sam build`)
- [ ] Python 3.11+ installed
- [ ] Virtual environment activated

### Security Readiness
- [ ] Custom SECRET_HASH generated (use `generate_secret_hash.py`)
- [ ] SECRET_HASH stored securely (password manager or AWS Secrets Manager)
- [ ] Never commit SECRET_HASH to version control
- [ ] Understand that losing SECRET_HASH invalidates all API keys

### Documentation Readiness
- [x] README.md updated with project overview
- [x] MANIFEST_GUIDE.md created for task configuration
- [x] SECRET_HASH_GUIDE.md created for security
- [x] DEPLOYMENT_GUIDE.md (this file) complete

### Testing Readiness
- [ ] Sample manifest.json files created (2 samples exist)
- [ ] Test data prepared for verification
- [ ] API testing tools ready (curl, Postman, etc.)

**Once all items are checked, proceed with deployment!**

## Prerequisites

### 1. AWS CLI Configured
```bash
# Check AWS CLI is installed
aws --version

# Configure credentials (if not already done)
aws configure
```

### 2. SAM CLI Installed
```bash
# Check SAM CLI is installed
sam --version

# If not installed, install it:
# https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
```

### 3. Python Environment
```bash
# Activate virtual environment
cd k8s-grader/k8s-grader-api
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

## Deployment Steps

### Step 1: Validate Template

```bash
cd k8s-grader/k8s-grader-api
sam validate
```

**Expected**: Warnings about API Gateway (safe to ignore), no errors

---

### Step 2: Build

```bash
sam build
```

**What happens**:
- Builds all Lambda functions
- Builds layers (LibLayer, CommonLayer)
- Packages dependencies
- Creates `.aws-sam/build/` directory

**Expected output**:
```
Build Succeeded

Built Artifacts  : .aws-sam/build
Built Template   : .aws-sam/build/template.yaml
```

**If build fails**:
- Check Python version matches template (python3.14)
- Verify all requirements.txt files exist
- Check for syntax errors in Python files

---

### Step 3: Deploy (First Time)

#### Generate Custom Secret Hash (Recommended for Production)

The SECRET_HASH is used to encrypt/decrypt API keys. For production, generate your own:

**Option 1: Use the helper script (easiest)**
```bash
python3 generate_secret_hash.py
```

**Option 2: Generate manually**
```bash
python3 << 'EOF'
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(f"Your SECRET_HASH: {key.decode()}")
EOF
```

**Save this key securely!** You'll need it for:
- Deployment (as SecretHash parameter)
- Generating API keys
- All API key operations

**⚠️ IMPORTANT**: 
- Never commit this key to version control
- Store it in a password manager or AWS Secrets Manager
- If you lose this key, all existing API keys will be invalid

#### Deploy Command

```bash
sam deploy --guided
```

**Configuration prompts**:

1. **Stack Name**: `k8s-grader-api-dev` (or your choice)
2. **AWS Region**: Your preferred region (e.g., `us-east-1`)
3. **Parameter SecretHash**: 
   - **IMPORTANT**: For production, generate a new key!
   - Press Enter to use default (for testing only)
   - Or provide your own Fernet key (see below)
4. **Parameter StageName**: `Prod` or `Dev`
5. **Parameter EasterEggSheetId**: Press Enter for default
6. **Parameter NCPBackgroundSheetId**: Press Enter for default
7. **Parameter PythonVersion**: `python3.14`
8. **Confirm changes before deploy**: `Y`
9. **Allow SAM CLI IAM role creation**: `Y`
10. **Disable rollback**: `N` (keep rollback enabled)
11. **TaskHandlerFunction has no authorization**: `Y` (API key required)
12. **SaveK8sAccountFunction has no authorization**: `Y` (intentional)
13. **KeygenFunction has no authorization**: `Y` (intentional)
14. **Save arguments to configuration file**: `Y`
15. **SAM configuration file**: `samconfig.toml` (default)
16. **SAM configuration environment**: `default`

**Deployment time**: 5-10 minutes

---

### Step 4: Deploy (Subsequent Times)

After first deployment, simply run:

```bash
sam deploy
```

Uses saved configuration from `samconfig.toml`

---

## Post-Deployment Verification

### 1. Check Stack Status

```bash
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].StackStatus' \
  --output text
```

**Expected**: `CREATE_COMPLETE` or `UPDATE_COMPLETE`

---

### 2. Get Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs' \
  --output table
```

**Important outputs**:
- `BaseUrl` - API base URL
- `TaskHandlerApi` - New /task endpoint
- `TaskStateTable` - New task state table name
- `NpcAssignmentTable` - New NPC assignment table name

---

### 3. Verify New Tables

```bash
# Get table names from outputs
TASK_STATE_TABLE=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`TaskStateTable`].OutputValue' \
  --output text)

NPC_ASSIGNMENT_TABLE=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`NpcAssignmentTable`].OutputValue' \
  --output text)

# Verify tables exist
aws dynamodb describe-table --table-name $TASK_STATE_TABLE
aws dynamodb describe-table --table-name $NPC_ASSIGNMENT_TABLE
```

**Expected**: Table descriptions returned successfully

---

### 4. Verify New Function

```bash
# Get function name
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`TaskHandlerApi`].OutputValue' \
  --output text | cut -d'/' -f4)

# Check function exists
aws lambda get-function --function-name k8s-grader-api-dev-TaskHandlerFunction
```

**Expected**: Function configuration returned

---

### 5. Test New Endpoint

First, you need an API key. Get it from the keygen endpoint:

```bash
# Get base URL
BASE_URL=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`BaseUrl`].OutputValue' \
  --output text)

# Get secret hash
SECRET_HASH=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretHash`].OutputValue' \
  --output text)

# Generate API key (replace YOUR_EMAIL)
curl "${BASE_URL}keygen?secret=${SECRET_HASH}&email=YOUR_EMAIL@example.com"
```

**Save the API key** from the response.

Now test the new /task endpoint:

```bash
# Test task endpoint (replace YOUR_API_KEY)
curl -H "x-api-key: YOUR_API_KEY" \
  "${BASE_URL}task?action=start&game=game01&task=01&npc=npc01"
```

**Expected response**:
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

---

## Monitoring

### CloudWatch Logs

```bash
# View TaskHandlerFunction logs
aws logs tail /aws/lambda/k8s-grader-api-dev-TaskHandlerFunction --follow

# View specific log group
aws logs tail /aws/lambda/k8s-grader-api-dev-TaskHandlerFunction \
  --since 10m \
  --format short
```

### CloudWatch Metrics

```bash
# Get Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=k8s-grader-api-dev-TaskHandlerFunction \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

---

## Troubleshooting

### Build Fails

**Error**: `ModuleNotFoundError`
```bash
# Check requirements.txt exists
ls -la */requirements.txt

# Verify Python version
python --version
```

**Error**: Permission denied on .aws-sam
```bash
# Clean and rebuild
rm -rf .aws-sam
sam build
```

---

### Deploy Fails

**Error**: `CREATE_FAILED` - IAM permissions
```bash
# Check your AWS credentials have required permissions:
# - CloudFormation
# - Lambda
# - DynamoDB
# - S3
# - IAM
# - API Gateway
```

**Error**: `ROLLBACK_COMPLETE`
```bash
# Check CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name k8s-grader-api-dev \
  --max-items 20

# Delete failed stack and retry
aws cloudformation delete-stack --stack-name k8s-grader-api-dev
# Wait for deletion, then redeploy
```

---

### Function Errors

**Error**: `Task execution failed`
```bash
# Check CloudWatch logs
aws logs tail /aws/lambda/k8s-grader-api-dev-TaskHandlerFunction \
  --since 30m

# Check function configuration
aws lambda get-function-configuration \
  --function-name k8s-grader-api-dev-TaskHandlerFunction
```

**Error**: `AccessDenied` on DynamoDB
```bash
# Verify IAM policies in template.yaml
# Check function has DynamoDBCrudPolicy for new tables
```

---

### API Errors

**Error**: `403 Forbidden`
```bash
# Verify API key is valid
# Check API key is associated with usage plan
aws apigateway get-usage-plans
```

**Error**: `404 Not Found`
```bash
# Verify endpoint URL is correct
# Check API Gateway stage is deployed
aws apigateway get-stages --rest-api-id YOUR_API_ID
```

---

## Rollback

### Rollback to Previous Version

```bash
# CloudFormation automatically rolls back on failure
# To manually rollback:
aws cloudformation update-stack \
  --stack-name k8s-grader-api-dev \
  --use-previous-template
```

### Delete Stack

```bash
# Complete removal
aws cloudformation delete-stack --stack-name k8s-grader-api-dev

# Wait for deletion
aws cloudformation wait stack-delete-complete \
  --stack-name k8s-grader-api-dev
```

---

## Cost Estimation

### Monthly Costs (Approximate)

**DynamoDB** (On-Demand):
- 9 tables × $1.25/million writes = ~$5-10/month
- Read costs: ~$5-10/month

**Lambda**:
- 4 functions × 1M requests = Free tier
- Compute: ~$5-15/month

**API Gateway**:
- 1M requests = Free tier
- Additional: $3.50/million

**S3**:
- Storage: ~$1-5/month
- Requests: Minimal

**Total**: ~$15-40/month (depending on usage)

---

## Security Checklist

- [ ] API keys required for protected endpoints
- [ ] IAM roles follow least privilege
- [ ] DynamoDB tables use on-demand billing
- [ ] CloudWatch logs enabled
- [ ] CORS configured properly
- [ ] Secrets not hardcoded
- [ ] Environment variables used for config

---

## Next Steps After Deployment

1. **Test End-to-End**
   - Create API key
   - Start a task
   - Execute phases
   - Verify state transitions

2. **Monitor Performance**
   - Check CloudWatch metrics
   - Review logs for errors
   - Monitor DynamoDB usage

3. **Create More Manifests**
   - Add manifest.json to more tasks
   - Test with different task types

4. **Update Frontend**
   - Modify RPG Maker plugin
   - Use new /task endpoint
   - Test in game

5. **Documentation**
   - Update API documentation
   - Create user guide
   - Document new features

---

## Success Criteria

- [x] Stack deployed successfully
- [ ] All new resources created
- [ ] New /task endpoint responds correctly
- [ ] No errors in CloudWatch logs
- [ ] All tests pass in deployed environment
- [ ] Monitoring configured

---

## Quick Reference

### Useful Commands

```bash
# Build
sam build

# Deploy
sam deploy

# Validate
sam validate

# Delete
sam delete

# Logs
sam logs -n TaskHandlerFunction --tail

# Local testing
sam local invoke TaskHandlerFunction -e events/event.json
```

### Important URLs

After deployment, save these:
- Base URL: From `BaseUrl` output
- Task Endpoint: From `TaskHandlerApi` output
- Keygen: `{BaseUrl}keygen?secret={SecretHash}&email={email}`

---

## Summary

This guide covers:
- ✅ Prerequisites and setup
- ✅ Build and deployment steps
- ✅ Post-deployment verification
- ✅ Monitoring and troubleshooting
- ✅ Rollback procedures
- ✅ Cost estimation
- ✅ Security checklist
- ✅ Next steps

Follow these steps to successfully deploy the refactored K8s Grader API to AWS!
