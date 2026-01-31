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

### [CHANGELOG.md](CHANGELOG.md) 🆕
Recent bug fixes and improvements:
- Session credentials fix
- Metadata key filtering
- Deploy script improvements
- Test separation
- Error message improvements

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
- Unit tests (111 tests, mocked, fast)
- Integration tests (13 tests, real API)
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

## Quick Reference

### Deploy (Automated)
```bash
./deploy.sh                    # Full deployment with tests
./deploy.sh --skip-integration # Skip integration tests
./deploy.sh --guided           # Interactive setup
```

### Run Unit Tests
```bash
./run_tests.sh                 # 111 unit tests
```

### Run Integration Tests
```bash
./run_integration_tests.sh    # 13 integration tests
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
├── CHANGELOG.md                 # Recent changes & bug fixes
├── DEPLOYMENT_GUIDE.md          # Deployment instructions
├── SECRET_HASH_GUIDE.md         # SECRET_HASH management
├── TESTING_GUIDE.md             # Complete testing guide
├── MANIFEST_GUIDE.md            # Task manifest guide
├── DOCS_INDEX.md                # This file
├── deploy.sh                    # Automated deployment script
├── run_tests.sh                 # Unit test runner
├── run_integration_tests.sh     # Integration test runner
└── tests/
    ├── test_*.py                # Unit tests (111 tests)
    └── integration/
        ├── README.md            # Integration test guide
        └── test_*.py            # Integration tests (13 tests)
```

## Getting Help

1. **Quick Start**: Read [QUICK_START.md](QUICK_START.md)
2. **Recent Changes**: Check [CHANGELOG.md](CHANGELOG.md)
3. **Deployment Issues**: Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
4. **Testing Issues**: Check [TESTING_GUIDE.md](TESTING_GUIDE.md)
5. **API Keys**: Read [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)
6. **Task Configuration**: Read [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)
