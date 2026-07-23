# K8s Grader API Documentation

Welcome to the K8s Grader API documentation! All documentation has been organized in this `docs/` folder for easy navigation.

## 📖 Start Here

- **[DOCS_INDEX.md](DOCS_INDEX.md)** - Complete documentation index (your map!)
- **[QUICK_START.md](QUICK_START.md)** - Get started in minutes
- **[../README.md](../README.md)** - Project overview (in root folder)

## 📚 Core Documentation

### Getting Started
- [QUICK_START.md](QUICK_START.md) - Fast-track guide
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deploy to AWS
- [SECRET_HASH_GUIDE.md](SECRET_HASH_GUIDE.md) - API key encryption

### Architecture & Design
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [EXAM_DURABLE_FLOW.md](EXAM_DURABLE_FLOW.md) - Exam WebSocket and durable Lambda flow
- [GAME_LOGIC.md](GAME_LOGIC.md) - Game WebSocket flow and player-facing message rules
- [DATABASE_GUIDE.md](DATABASE_GUIDE.md) - Database layer

### Development
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Unit and integration tests
- [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md) - Task configuration
- [CHANGELOG.md](CHANGELOG.md) - Recent changes

### Integration Tests
- [INTEGRATION_TEST_IMPROVEMENTS.md](INTEGRATION_TEST_IMPROVEMENTS.md) - Test improvements summary
- [../tests/integration/README.md](../tests/integration/README.md) - Complete integration test guide
- [../tests/integration/CLEANUP_SCRIPT.md](../tests/integration/CLEANUP_SCRIPT.md) - Cleanup script docs

### Meta Documentation
- [DOCUMENTATION_CONSOLIDATION.md](DOCUMENTATION_CONSOLIDATION.md) - Consolidation report
- [DOCS_INDEX.md](DOCS_INDEX.md) - Complete index

## 🚀 Quick Commands

```bash
# Deploy with automatic tests
./deploy.sh

# Run unit tests
./run_tests.sh

# Run integration tests
./run_integration_tests.sh
```

## 📊 Project Status

- ✅ Exam mode documented as WebSocket + durable Lambda
- ✅ Game mode documented as WebSocket + durable Lambda
- ✅ Shared account storage and current RPG UX rules documented
- ✅ Self-contained tests available for backend changes

## 🗺️ Documentation Map

```
docs/
├── README.md (this file)           # Documentation overview
├── DOCS_INDEX.md                   # Complete index
├── QUICK_START.md                  # Get started fast
├── DEPLOYMENT_GUIDE.md             # Deploy to AWS
├── TESTING_GUIDE.md                # Testing guide
├── ARCHITECTURE.md                 # System design
├── EXAM_DURABLE_FLOW.md            # Exam durable flow
├── GAME_LOGIC.md                   # Game durable WebSocket flow
├── DATABASE_GUIDE.md               # Database layer
├── MANIFEST_GUIDE.md               # Task configuration
├── SECRET_HASH_GUIDE.md            # Security
├── CHANGELOG.md                    # Recent changes
├── INTEGRATION_TEST_IMPROVEMENTS.md # Test improvements
└── DOCUMENTATION_CONSOLIDATION.md  # Consolidation report
```

## 💡 Tips

1. **New to the project?** Start with [QUICK_START.md](QUICK_START.md)
2. **Deploying?** Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
3. **Writing tests?** Check [TESTING_GUIDE.md](TESTING_GUIDE.md)
4. **Need the big picture?** See [ARCHITECTURE.md](ARCHITECTURE.md)
5. **Looking for something specific?** Use [DOCS_INDEX.md](DOCS_INDEX.md)

## 🔄 Recent Updates

**July 2026**:
- ✅ Documented game WebSocket durable flow
- ✅ Documented current RPG player-message mapping
- ✅ Documented shared account storage and no-lockout retry behavior

**February 2026**:
- ✅ Moved all documentation to `docs/` folder
- ✅ Self-contained integration tests (no manual setup)
- ✅ Automatic API key generation
- ✅ Comprehensive cleanup (9 tables + API Gateway)

See [CHANGELOG.md](CHANGELOG.md) for detailed changes.

---

**Need help?** Check [DOCS_INDEX.md](DOCS_INDEX.md) for the complete documentation map!
