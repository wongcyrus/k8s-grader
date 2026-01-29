# SECRET_HASH Guide

## What is SECRET_HASH?

The SECRET_HASH is a **Fernet encryption key** used to encrypt and decrypt API keys. It's critical for the security of your K8s Grader API.

## How It Works

### 1. API Key Generation
When a user requests an API key:
```python
# In keygen function
fernet = Fernet(SECRET_HASH)
api_key = fernet.encrypt(email.encode()).decode()
# Returns encrypted API key to user
```

### 2. Email Extraction
When a user makes an API request:
```python
# In task handler
fernet = Fernet(SECRET_HASH)
email = fernet.decrypt(api_key.encode()).decode()
# Extracts email from encrypted API key
```

### 3. Security Flow
```
User Email: "user@example.com"
    ↓ (encrypt with SECRET_HASH)
API Key: "gAAAAABh..."
    ↓ (user includes in requests)
API Request with x-api-key header
    ↓ (decrypt with SECRET_HASH)
User Email: "user@example.com"
```

## Why You Need It

1. **Security**: Encrypts user emails in API keys
2. **Authentication**: Verifies API key validity
3. **User Identification**: Extracts email from API key
4. **Data Isolation**: Ensures users only access their own data

## Default vs Custom Key

### Default Key (Testing Only)
```yaml
# In template.yaml
SecretHash:
  Default: "hyKOuny4vy94RUiYe3pB6CCwtaJeW6B_fOtqbK1PXrQ="
```

**⚠️ WARNING**: 
- This is a **public key** in the repository
- Anyone can decrypt API keys generated with this key
- **NEVER use in production!**
- Only for local testing and development

### Custom Key (Production)
Generate your own unique key:
```bash
python3 generate_secret_hash.py
```

**Benefits**:
- ✅ Unique to your deployment
- ✅ Not publicly known
- ✅ Secure API key encryption
- ✅ Production-ready

## Generating a Custom Key

### Method 1: Helper Script (Recommended)
```bash
cd k8s-grader/k8s-grader-api
python3 generate_secret_hash.py
```

Output:
```
============================================================
K8s Grader API - Secret Hash Generator
============================================================

Generating new SECRET_HASH...

Your new SECRET_HASH:
------------------------------------------------------------
Zx9K3mP7qR2tY5wN8vB1cF4gH6jL0sD3eA7iO9uM2pQ=
------------------------------------------------------------

IMPORTANT:
1. Save this key securely
2. Use this key when deploying
3. Use this key when generating API keys
...
```

### Method 2: Python One-Liner
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Method 3: Python Script
```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

## Using Your Custom Key

### During Deployment
```bash
sam deploy --guided

# When prompted:
Parameter SecretHash [hyKOuny4vy94RUiYe3pB6CCwtaJeW6B_fOtqbK1PXrQ=]: 
# Paste your custom key here: Zx9K3mP7qR2tY5wN8vB1cF4gH6jL0sD3eA7iO9uM2pQ=
```

### In samconfig.toml
After first deployment, your key is saved:
```toml
[default.deploy.parameters]
stack_name = "k8s-grader-api-dev"
parameter_overrides = "SecretHash=\"Zx9K3mP7qR2tY5wN8vB1cF4gH6jL0sD3eA7iO9uM2pQ=\" ..."
```

### For API Key Generation
```bash
# Get your deployed SECRET_HASH
SECRET_HASH=$(aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Parameters[?ParameterKey==`SecretHash`].ParameterValue' \
  --output text)

# Use it to generate API keys
curl "${BASE_URL}keygen?secret=${SECRET_HASH}&email=user@example.com"
```

## Security Best Practices

### ✅ DO:
- Generate a unique key for each environment (dev, staging, prod)
- Store keys in AWS Secrets Manager or password manager
- Rotate keys periodically (requires regenerating all API keys)
- Use different keys for different deployments
- Keep keys out of version control

### ❌ DON'T:
- Use the default key in production
- Commit keys to Git
- Share keys in plain text (email, Slack, etc.)
- Reuse keys across environments
- Store keys in code or config files

## Key Storage Options

### Option 1: AWS Secrets Manager (Recommended)
```bash
# Store the key
aws secretsmanager create-secret \
  --name k8s-grader-api/secret-hash \
  --secret-string "Zx9K3mP7qR2tY5wN8vB1cF4gH6jL0sD3eA7iO9uM2pQ="

# Retrieve the key
aws secretsmanager get-secret-value \
  --secret-id k8s-grader-api/secret-hash \
  --query SecretString \
  --output text
```

### Option 2: AWS Systems Manager Parameter Store
```bash
# Store the key
aws ssm put-parameter \
  --name /k8s-grader-api/secret-hash \
  --value "Zx9K3mP7qR2tY5wN8vB1cF4gH6jL0sD3eA7iO9uM2pQ=" \
  --type SecureString

# Retrieve the key
aws ssm get-parameter \
  --name /k8s-grader-api/secret-hash \
  --with-decryption \
  --query Parameter.Value \
  --output text
```

### Option 3: Password Manager
- 1Password
- LastPass
- Bitwarden
- KeePass

## Key Rotation

If you need to rotate the SECRET_HASH:

### Step 1: Generate New Key
```bash
python3 generate_secret_hash.py
```

### Step 2: Update Deployment
```bash
sam deploy --parameter-overrides SecretHash="NEW_KEY_HERE"
```

### Step 3: Regenerate All API Keys
All existing API keys will be invalid. Users must:
1. Request new API keys from `/keygen` endpoint
2. Update their applications with new keys

### Step 4: Notify Users
- Send email notification
- Update documentation
- Provide grace period if possible

## Troubleshooting

### Error: "Invalid API key format"
**Cause**: API key was encrypted with a different SECRET_HASH

**Solution**: 
- Verify you're using the correct SECRET_HASH
- Check if key was rotated
- Regenerate API key with current SECRET_HASH

### Error: "API key is required"
**Cause**: Missing x-api-key header

**Solution**: Include API key in request header

### Error: Fernet decryption failed
**Cause**: SECRET_HASH mismatch or corrupted API key

**Solution**:
- Verify SECRET_HASH matches deployment
- Regenerate API key
- Check for key truncation or modification

## Environment-Specific Keys

### Development
```bash
# Generate dev key
python3 generate_secret_hash.py > dev-secret-hash.txt

# Deploy with dev key
sam deploy --config-env dev --parameter-overrides SecretHash="$(cat dev-secret-hash.txt)"
```

### Staging
```bash
# Generate staging key
python3 generate_secret_hash.py > staging-secret-hash.txt

# Deploy with staging key
sam deploy --config-env staging --parameter-overrides SecretHash="$(cat staging-secret-hash.txt)"
```

### Production
```bash
# Generate production key
python3 generate_secret_hash.py > prod-secret-hash.txt

# Deploy with production key
sam deploy --config-env prod --parameter-overrides SecretHash="$(cat prod-secret-hash.txt)"
```

## Summary

- **SECRET_HASH** encrypts/decrypts API keys
- **Default key** is for testing only
- **Generate custom key** for production
- **Store securely** in Secrets Manager
- **Rotate periodically** for security
- **Never commit** to version control

## Quick Commands

```bash
# Generate new key
python3 generate_secret_hash.py

# Deploy with custom key
sam deploy --guided
# (paste key when prompted)

# Get deployed key
aws cloudformation describe-stacks \
  --stack-name k8s-grader-api-dev \
  --query 'Stacks[0].Parameters[?ParameterKey==`SecretHash`].ParameterValue' \
  --output text

# Generate API key
curl "${BASE_URL}keygen?secret=${SECRET_HASH}&email=user@example.com"
```

---

**Remember**: The SECRET_HASH is the master key for your API. Protect it like a password!
