# Documentation Index

Essential documentation for the K8s Grader API.

## Core Documentation

### [README.md](README.md)
**Start here!** Project overview, quick start, and key concepts.

### [ARCHITECTURE.md](ARCHITECTURE.md)
System architecture and design:
- Architecture diagram
- Core components
- Data flow
- Security model
- Scalability considerations

### [QUICK_START.md](QUICK_START.md)
Fast-track guide to get up and running in minutes.

## Deployment

### [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
Complete deployment instructions, configuration, and troubleshooting.

### [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)
How to generate and manage the SECRET_HASH for API key encryption.

## Development

### [DATABASE_GUIDE.md](DATABASE_GUIDE.md)
Database layer using repository pattern:
- Repository classes overview
- Usage examples
- Best practices
- Testing strategies

### [TESTING_GUIDE.md](TESTING_GUIDE.md)
Complete testing guide covering:
- Unit tests (mocked, fast)
- Integration tests (real API)
- Encrypted API keys
- Running tests
- CI/CD integration

### [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)
Task manifest configuration guide:
- Manifest structure
- Phase configuration
- Auto-generation
- Examples

## Integration Tests

### [tests/integration/README.md](tests/integration/README.md)
Detailed integration test documentation:
- Prerequisites
- Setup
- Running tests
- Test categories
- Troubleshooting

### [tests/integration/QUICK_START.md](tests/integration/QUICK_START.md)
Quick reference for running integration tests.

## Quick Reference

### Deploy
```bash
./deploy.sh
```

### Run Unit Tests
```bash
./run_tests.sh
```

### Run Integration Tests
```bash
# 1. Generate encrypted API key
./generate_test_api_key.sh

# 2. Set environment variable
export TEST_API_KEY="your-generated-key"

# 3. Run tests
./run_integration_tests.sh
```

### Generate API Key
```bash
./generate_test_api_key.sh
```

## File Organization

```
k8s-grader-api/
├── README.md                    # Project overview
├── QUICK_START.md               # Fast-track guide
├── DEPLOYMENT_GUIDE.md          # Deployment instructions
├── SECRET_HASH_GUIDE.md         # SECRET_HASH management
├── TESTING_GUIDE.md             # Complete testing guide
├── MANIFEST_GUIDE.md            # Task manifest guide
├── DOCS_INDEX.md                # This file
├── tests/
│   └── integration/
│       ├── README.md            # Integration test guide
│       └── QUICK_START.md       # Integration test quick start
└── ...
```

## Getting Help

1. **Quick Start**: Read [QUICK_START.md](QUICK_START.md)
2. **Deployment Issues**: Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
3. **Testing Issues**: Check [TESTING_GUIDE.md](TESTING_GUIDE.md)
4. **API Keys**: Read [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)
5. **Task Configuration**: Read [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)
