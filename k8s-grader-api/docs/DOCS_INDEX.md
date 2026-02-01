# Documentation Index

Essential documentation for the K8s Grader API.

## Core Documentation

### [../README.md](../README.md)
**Start here!** Project overview, quick start, and key concepts.
- 106 unit tests, 15 integration tests (all passing)
- Self-contained integration tests (no manual setup)
- Deployment and testing instructions

### [QUICK_START.md](QUICK_START.md) ⚡
Fast-track guide to get up and running in minutes.
- Deploy with `./deploy.sh` (includes automatic tests)
- Run tests locally
- Common tasks and debugging

### [ARCHITECTURE.md](ARCHITECTURE.md)
System architecture and design:
- Architecture diagram
- Core components
- Data flow
- Security model
- Scalability considerations

### [GAME_LOGIC.md](GAME_LOGIC.md) 🎮
Complete game flow and mechanics:
- Player journey with diagrams
- Task and phase state machines
- NPC management system
- Session personalization
- Abandonment and retry flow
- Points and progress system
- API response types
- **Race condition prevention** 🔥

### [CHANGELOG.md](CHANGELOG.md) 🆕
Recent bug fixes and improvements:
- **Integration tests fixed** (2026-02-01) ✅
- **Race condition in NPC assignment** (2026-02-01) 🔥
- Task abandonment and retry flow
- Session credentials fix
- Metadata key filtering
- Deploy script improvements
- Test separation
- Error message improvements

## Deployment

### [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
Complete deployment instructions, configuration, and troubleshooting.
- Step-by-step deployment process
- Post-deployment verification
- **Automatic integration tests** ✅
- Monitoring and troubleshooting

### [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)
How to generate and manage the SECRET_HASH for API key encryption.
- Security best practices
- Key generation
- Key rotation

## Development

### [DATABASE_GUIDE.md](DATABASE_GUIDE.md)
Database layer using repository pattern:
- Repository classes overview
- Usage examples
- Best practices
- Testing strategies

### [TESTING_GUIDE.md](TESTING_GUIDE.md)
Complete testing guide covering:
- Unit tests (106 tests, mocked, fast)
- **Integration tests (15 tests, self-contained, automatic)** ✅
- No manual API key setup required
- Running tests
- CI/CD integration

### [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)
Task manifest configuration guide:
- Manifest structure
- Phase configuration
- Auto-generation
- Examples

## Integration Tests

### [../tests/integration/README.md](../tests/integration/README.md)
Self-contained integration test documentation:
- **Automatic setup and cleanup** ✅
- **No manual API key generation needed** ✅
- Prerequisites
- Running tests (just run `./deploy.sh` or `./run_integration_tests.sh`)
- Test coverage (15 tests)
- Troubleshooting

### [INTEGRATION_TEST_IMPROVEMENTS.md](INTEGRATION_TEST_IMPROVEMENTS.md)
Summary of integration test improvements:
- Self-contained architecture
- Automatic user and API key generation
- Comprehensive cleanup
- Before/after comparison
- **All 15 tests passing** ✅

## Quick Reference

### Deploy (Automated)
```bash
./deploy.sh                    # Full deployment with tests
./deploy.sh --skip-integration # Skip integration tests
./deploy.sh --guided           # Interactive setup
```

### Run Unit Tests
```bash
./run_tests.sh                 # 106 unit tests
```

### Run Integration Tests
```bash
./run_integration_tests.sh    # 15 integration tests (self-contained, automatic)
# No manual API key setup needed!
```

### Generate API Key (Optional)
```bash
# Only needed for manual testing, not for integration tests
# Integration tests generate keys automatically
curl "${API_ENDPOINT}/keygen/?secret=${SECRET_HASH}&email=your@email.com"
```

## File Organization

```
k8s-grader-api/
├── README.md                    # Project overview (root level)
├── docs/                        # 📁 All documentation
│   ├── DOCS_INDEX.md            # Documentation index (start here!)
│   ├── QUICK_START.md           # Fast-track guide ✅
│   ├── CHANGELOG.md             # Recent changes & bug fixes
│   ├── ARCHITECTURE.md          # System architecture
│   ├── GAME_LOGIC.md            # Game flow and mechanics
│   ├── DEPLOYMENT_GUIDE.md      # Deployment instructions ✅
│   ├── TESTING_GUIDE.md         # Complete testing guide ✅
│   ├── INTEGRATION_TEST_IMPROVEMENTS.md  # Integration test summary ✅
│   ├── MANIFEST_GUIDE.md        # Task manifest guide
│   ├── DATABASE_GUIDE.md        # Database layer guide
│   ├── SECRET_HASH_GUIDE.md     # SECRET_HASH management
│   └── DOCUMENTATION_CONSOLIDATION.md  # Consolidation report
├── deploy.sh                    # Automated deployment script
├── run_tests.sh                 # Unit test runner
├── run_integration_tests.sh     # Integration test runner
└── tests/
    ├── test_*.py                # Unit tests (106 tests)
    └── integration/
        ├── README.md            # Integration test guide ✅
        ├── CLEANUP_SCRIPT.md    # Cleanup script docs
        ├── test_*.py            # Integration tests (15 tests)
        └── cleanup_test_keys.py # Manual cleanup script
```

**Legend**: ✅ = Recently updated with self-contained integration test improvements

## Getting Help

1. **Quick Start**: Read [QUICK_START.md](QUICK_START.md)
2. **Recent Changes**: Check [CHANGELOG.md](CHANGELOG.md)
3. **Deployment Issues**: Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
4. **Testing Issues**: Check [TESTING_GUIDE.md](TESTING_GUIDE.md)
5. **API Keys**: Read [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md)
6. **Task Configuration**: Read [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)

## Recent Improvements ✨

### Integration Tests (February 2026)
- ✅ **Self-contained** - No manual setup required
- ✅ **Automatic API key generation** - Tests generate their own keys
- ✅ **Automatic cleanup** - 9 DynamoDB tables + API Gateway
- ✅ **All 15 tests passing** - Fixed email length issue
- ✅ **Runs automatically** - After every deployment

See [INTEGRATION_TEST_IMPROVEMENTS.md](INTEGRATION_TEST_IMPROVEMENTS.md) for details.

### Test Statistics
- **Unit Tests**: 106 tests, 63% coverage, < 5s execution
- **Integration Tests**: 15 tests, self-contained, ~66s execution
- **Total**: 121 tests, all passing ✅

## Documentation Status

All documentation is **up-to-date** as of February 1, 2026:
- ✅ Integration tests working and documented
- ✅ Cross-references verified
- ✅ Duplicate content removed
- ✅ Outdated information updated
- ✅ File organization optimized
