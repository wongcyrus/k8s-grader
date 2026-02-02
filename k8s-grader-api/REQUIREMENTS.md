# Requirements Management

## Overview

This project separates production and development requirements to keep Lambda deployments lean and secure.

## Requirements Files

### Production Requirements

**File**: `common-layer/requirements.txt`

**Purpose**: Packages deployed to AWS Lambda

**Contents**:
- Runtime dependencies
- **pytest and pytest-html** (Lambda runs tests to validate player's work)
- No development-only tools (moto, black, flake8, etc.)
- Optimized for Lambda size limits

**Packages**:
```
cfnresponse      # AWS CloudFormation responses
requests         # HTTP client
kubernetes       # K8s API client
boto3            # AWS SDK
names_generator  # Random name generation
Jinja2           # Template rendering
requests-toolbelt # HTTP utilities
cryptography     # Encryption/decryption
pytest           # Test framework (Lambda runs tests)
pytest-html      # HTML test reports
pytest-timeout   # Test timeout support (k8s-game-rule tests use timeout=300)
```

**Install**:
```bash
pip install -r common-layer/requirements.txt
```

---

### Development Requirements

**File**: `requirements-dev.txt`

**Purpose**: Local development and testing

**Contents**:
- All production requirements (via `-r common-layer/requirements.txt`)
- Testing frameworks (pytest, moto)
- Code quality tools (black, flake8, mypy)
- Development utilities (ipython)

**Packages**:
```
# Production (inherited)
+ All packages from common-layer/requirements.txt

# Testing utilities
pytest-cov==4.1.0       # Code coverage
pytest-mock==3.12.0     # Mocking utilities
pytest-order==1.2.0     # Test execution order
pytest-xdist==3.5.0     # Parallel test execution
pytest-timeout==2.2.0   # Test timeout support
moto==4.2.9             # AWS service mocking

# Code Quality
black==23.12.1          # Code formatter
flake8==7.0.0           # Linter
mypy==1.8.0             # Type checker

# Development
ipython==8.19.0         # Interactive shell
```

**Install**:
```bash
pip install -r requirements-dev.txt
```

---

### Test Requirements

**File**: `tests/requirements.txt`

**Purpose**: Running tests (references dev requirements)

**Contents**:
```
-r ../requirements-dev.txt
```

**Install**:
```bash
pip install -r tests/requirements.txt
```

---

## Why Separate Requirements?

### 1. Lambda Size Limits
- Lambda has deployment package size limits (250 MB unzipped)
- Development tools (moto, black, flake8) add significant size
- Production needs pytest (to run tests) but not dev tools

### 2. Security
- Fewer dependencies = smaller attack surface
- Development-only tools shouldn't be in production
- Reduces vulnerability exposure

### 3. Performance
- Faster cold starts with fewer packages
- Less memory usage
- Quicker deployments

### 4. Cost
- Smaller packages = faster uploads
- Less storage in Lambda layers
- Reduced bandwidth costs

---

## What Goes Where?

### Production (Lambda) ✅
- pytest, pytest-html, pytest-timeout (Lambda runs k8s-game-rule tests which use timeout=300)
- Runtime dependencies (boto3, kubernetes, Jinja2, etc.)

### Development Only ❌
- pytest-cov, pytest-mock, pytest-order, pytest-xdist (testing utilities - local only)
- moto (AWS mocking - not needed in Lambda)
- black, flake8, mypy (code quality - local only)
- ipython (development convenience - local only)

---

## Installation Guide

### For Production Deployment

```bash
# Install only production requirements
pip install -r common-layer/requirements.txt

# Deploy to Lambda
sam build
sam deploy
```

### For Local Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development requirements (includes production)
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run specific test
pytest tests/test_answer_phase_skip.py -v

# Run with coverage
pytest --cov=common --cov-report=html
```

### For CI/CD Pipeline

```bash
# Install dev requirements for testing
pip install -r requirements-dev.txt

# Run tests
pytest tests/ --cov=common --cov-report=xml

# Check code quality
black --check .
flake8 .
mypy common-layer/common/
```

---

## Package Versions

### Why Pin Versions?

- **Reproducibility**: Same versions across environments
- **Stability**: Avoid breaking changes from updates
- **Security**: Control when to update vulnerable packages

### Updating Packages

```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade pytest==7.4.4

# Update requirements file
pip freeze | grep pytest >> requirements-dev.txt
```

---

## Common Issues

### Issue: "Module not found" in Lambda

**Cause**: Package in dev requirements but not production

**Solution**: Add to `common-layer/requirements.txt`

```bash
# Check what's in Lambda layer
sam build
ls .aws-sam/build/CommonLayer/python/lib/python3.*/site-packages/
```

### Issue: Lambda deployment too large

**Cause**: Too many packages in production requirements

**Solution**: Remove unnecessary packages, use Lambda layers

```bash
# Check layer size
du -sh .aws-sam/build/CommonLayer/
```

### Issue: Tests fail locally but pass in CI

**Cause**: Different package versions

**Solution**: Use exact versions in requirements

```bash
# Generate exact versions
pip freeze > requirements-dev.txt
```

---

## Best Practices

### ✅ DO

- Keep production requirements minimal
- Pin exact versions for stability
- Use `-r` to inherit requirements
- Document why each package is needed
- Regularly update and test packages

### ❌ DON'T

- Don't put test frameworks in production
- Don't use `>=` for version ranges (use `==`)
- Don't install packages globally (use venv)
- Don't commit `pip freeze` output directly
- Don't ignore security vulnerabilities

---

## Summary

| File | Purpose | Size | Deploy to Lambda |
|------|---------|------|------------------|
| `common-layer/requirements.txt` | Production | Small | ✅ Yes |
| `requirements-dev.txt` | Development | Large | ❌ No |
| `tests/requirements.txt` | Testing | Large | ❌ No |

**Production**: Lean and secure  
**Development**: Full-featured and convenient
