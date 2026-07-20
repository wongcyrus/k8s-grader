# K8s Grader Tools

Utility scripts for managing the K8s Grader system.

## Setup

Before using these tools, ensure you have the required dependencies:

```bash
# From k8s-grader directory
cd k8s-grader

# Recreate virtual environment (if needed)
bash recreate_venv.sh

# Or manually install dependencies
source venv/bin/activate
pip install -r tools/requirements.txt
```

## Available Tools

### 1. reset_game.py

Reset game state by clearing DynamoDB tables. Useful for testing or resetting player progress.

**Features:**
- Reset all users or specific user
- Reset specific game or all games
- Preserves user accounts and API keys
- Safe confirmation prompts

**Usage:**

```bash
# Activate virtual environment first
source venv/bin/activate

# Reset all data for all users (requires confirmation)
python tools/reset_game.py

# Reset specific stack
python tools/reset_game.py k8s-grader-api-prod

# Reset specific user's data
python tools/reset_game.py --email user@example.com

# Reset specific game for specific user
python tools/reset_game.py --email user@example.com --game game01

# Use custom region
python tools/reset_game.py --region us-west-2
```

**What gets deleted:**
- ✅ TaskStateTable (task progress)
- ✅ NpcAssignmentTable (NPC assignments)
- ✅ NpcLockTable (NPC locks)
- ✅ TestRecordTable (test execution history)

**What is preserved:**
- ❌ AccountTable (user K8s credentials)
- ❌ ApiKeyTable (encrypted API keys)
- ❌ NpcBackgroundTable (NPC character data)
- ❌ GameSourceTable (game source URLs)

**Safety:**
- Requires "yes" confirmation for full reset
- Filtered operations (--email) don't require confirmation
- Uses batch operations for efficiency
- Handles pagination automatically

### 2. genkey.py

Generate API keys for testing (deprecated - use keygen Lambda function instead).

**Usage:**
```bash
python tools/genkey.py
```

## Requirements

See `requirements.txt` for Python dependencies:
- `boto3>=1.43.51`

## AWS Credentials

These tools require AWS credentials with permissions to:
- Read CloudFormation stack outputs
- Read/Write DynamoDB tables

Configure credentials using:
```bash
aws configure
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

## Troubleshooting

### ModuleNotFoundError: No module named 'boto3'

The virtual environment needs to be recreated:
```bash
bash recreate_venv.sh
```

### Permission Denied

Ensure your AWS credentials have the necessary permissions:
```bash
aws sts get-caller-identity
```

### Stack Not Found

Verify the stack name:
```bash
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
```

## Development

When adding new tools:
1. Add dependencies to `requirements.txt`
2. Document usage in this README
3. Include help text in the script (`--help`)
4. Add error handling and user-friendly messages
5. Test with different scenarios

## Related Documentation

- [k8s-grader-api/README.md](../k8s-grader-api/README.md) - Main API documentation
- [k8s-grader-api/DEPLOYMENT_GUIDE.md](../k8s-grader-api/DEPLOYMENT_GUIDE.md) - Deployment guide
- [k8s-grader-api/DATABASE_GUIDE.md](../k8s-grader-api/DATABASE_GUIDE.md) - Database structure
