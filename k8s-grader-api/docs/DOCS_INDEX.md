# Documentation Index

**Last Updated:** July 22, 2026

This directory contains all documentation for the k8s-grader-api project.

---

## Quick Links

- **[Quick Start Guide](QUICK_START.md)** - Get started in 5 minutes
- **[Bug Fix Summary](BUG_FIX_SUMMARY_FEB_2026.md)** - February 2026 bug fixes ⭐
- **[Testing Scripts](../TESTING_SCRIPTS.md)** - Automated E2E tests
- **[Changelog](CHANGELOG.md)** - All changes and updates

---

## Core Documentation

### Getting Started
- **[Quick Start Guide](QUICK_START.md)** - Installation and setup
- **[README](README.md)** - Project overview
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - How to deploy

### Development
- **[Architecture](ARCHITECTURE.md)** - System design and components
- **[Exam Durable Flow](EXAM_DURABLE_FLOW.md)** - Exam WebSocket + durable Lambda flow ⭐
- **[Game Logic](GAME_LOGIC.md)** - How the game works
- **[Database Guide](DATABASE_GUIDE.md)** - DynamoDB tables and schema
- **[Manifest Guide](MANIFEST_GUIDE.md)** - Task manifest format

### Testing
- **[Testing Guide](TESTING_GUIDE.md)** - Unit and integration tests
- **[Testing Scripts](../TESTING_SCRIPTS.md)** - Automated E2E tests ⭐
- **[Bug Fix Summary](BUG_FIX_SUMMARY_FEB_2026.md)** - February 2026 fixes

### Operations
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Deployment procedures
- **[Secret Hash Guide](SECRET_HASH_GUIDE.md)** - API key management
- **[Changelog](CHANGELOG.md)** - Version history

---

## Recent Updates

### Exam Durable Flow (July 2026) ⭐
- ✅ Added [Exam Durable Flow](EXAM_DURABLE_FLOW.md)
- ✅ Documented WebSocket → durable Lambda → browser push flow
- ✅ Documented exam action behavior: `start`, `reset`, `run`, `status`, `records`
- ✅ Documented runtime fixes for:
  - `elapsed_delta` / `timedelta` logging crash
  - nested durable-step serialization error

### Bug Fixes ⭐
- ✅ **Task Completion Bug** - All 4 bugs fixed and verified
  - See [Bug Fix Summary](BUG_FIX_SUMMARY_FEB_2026.md)
  - Run automated test: `./test_complete_flow.sh`

### Documentation Updates
- ✅ Updated test counts: 121 → 153 tests
- ✅ Added comprehensive bug fix documentation
- ✅ Created fully automated E2E test
- ✅ Consolidated and cleaned up documentation

---

## Documentation by Topic

### Architecture & Design
- [Architecture](ARCHITECTURE.md) - System components
- [Exam Durable Flow](EXAM_DURABLE_FLOW.md) - Exam-mode action flow and runtime fixes
- [Game Logic](GAME_LOGIC.md) - Game mechanics
- [Database Guide](DATABASE_GUIDE.md) - Data model

### Development
- [Manifest Guide](MANIFEST_GUIDE.md) - Task configuration
- [Testing Guide](TESTING_GUIDE.md) - How to test
- [Bug Fix Summary](BUG_FIX_SUMMARY_FEB_2026.md) - Recent fixes

### Deployment & Operations
- [Deployment Guide](DEPLOYMENT_GUIDE.md) - Deploy to AWS
- [Secret Hash Guide](SECRET_HASH_GUIDE.md) - Security
- [Changelog](CHANGELOG.md) - What's new
- `scripts/seed_exam_code.py` - Validate and seed exam code (dry-run + apply)
- `scripts/reset_task_stage.py` - Reset task phase/stage in TaskStateTable

---

## Test Documentation

### Automated Testing ⭐
- **[Testing Scripts](../TESTING_SCRIPTS.md)** - E2E test documentation
- **[test_complete_flow.sh](../test_complete_flow.sh)** - Self-contained E2E test
- **[test_multiple_tasks.sh](../test_multiple_tasks.sh)** - Multi-task test

### Test Guides
- **[Testing Guide](TESTING_GUIDE.md)** - Complete testing guide
- **[E2E Testing README](../tests/E2E_TESTING_README.md)** - E2E test details
- **[Integration Tests](../tests/integration/README.md)** - Integration test guide

---

## Need Help?

- **Quick Start:** [QUICK_START.md](QUICK_START.md)
- **Testing:** Run `./test_complete_flow.sh`
- **Deployment:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Bug Reports:** See [Bug Fix Summary](BUG_FIX_SUMMARY_FEB_2026.md)

---

**Documentation Status:** ✅ Up to date  
**Last Review:** February 2, 2026  
**Next Review:** March 2, 2026
