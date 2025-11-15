# Load Testing Documentation Index

Complete index of all load testing documentation and resources.

## Quick Navigation

### 🚀 Getting Started (5 minutes)
**Start here if you're new to load testing**
- [Load Testing Quickstart](./LOAD_TESTING_QUICKSTART.md) - 5-minute quick start guide
- [Installation & Setup](#installation--setup) - Prerequisites and first steps

### 📚 Complete Documentation
- [Load Testing Guide](./LOAD_TESTING.md) - Comprehensive guide covering all aspects
- [Performance Baselines](./PERFORMANCE_BASELINES.md) - Thresholds and acceptance criteria
- [Operations Guide](./LOAD_TESTING_OPS_GUIDE.md) - Procedures and troubleshooting

### 🏃 Execute Tests
- [Running Load Tests](#running-tests) - Quick reference for test execution
- [Monitoring & Analysis](#monitoring--analysis) - Real-time metrics and post-test analysis

### 📖 Implementation Details
- [Load Tests Directory](../load_tests/README.md) - Test framework components
- [Implementation Summary](../LOAD_TESTING_SUMMARY.md) - What was delivered

---

## Installation & Setup

### Prerequisites

```bash
# Check Python version (3.11+)
python3 --version

# Check if Docker is available (for Docker Compose testing)
docker --version
docker-compose --version
```

### Installation

```bash
# 1. Install load testing dependencies
pip install -r load_tests/requirements.txt

# 2. Verify installation
locust --version

# 3. Copy environment configuration
cp .env.load-testing .env.load-testing.local
# Edit .env.load-testing.local if needed for custom settings
```

### Validate Setup

```bash
# Check API is running
curl http://localhost:8000/health

# Check Python can import load test modules
python3 -c "from load_tests import locustfile; print('✓ Load tests available')"
```

---

## Running Tests

### Method 1: Automated Script (Recommended)

```bash
# Basic run with default settings
./scripts/run_load_tests.sh

# Custom parameters
./scripts/run_load_tests.sh \
    --host https://staging.example.com \
    --users-max 500 \
    --spawn-rate 5 \
    --duration 600
```

### Method 2: Interactive Web UI

```bash
# Start Locust interface
locust -f load_tests/locustfile.py -H http://localhost:8000

# Open browser to http://localhost:8089
# Configure users, spawn rate, and start test
```

### Method 3: Headless CLI

```bash
# Direct Locust execution
python3 -m locust \
    -f load_tests/locustfile.py \
    -H http://localhost:8000 \
    --headless \
    -u 1000 \
    -r 10 \
    -t 300s \
    --csv=results
```

### Method 4: Docker Compose

```bash
# Start services
docker-compose up -d

# Wait for services to be ready
sleep 30

# Run tests
./scripts/run_load_tests.sh

# Cleanup
docker-compose down
```

### Method 5: Makefile Target

```bash
# Quick command
make load-test

# Equivalent to ./scripts/run_load_tests.sh
```

---

## Test Scenarios

### Scenario 1: Standard Load (Default)
- **Users**: 100-1000 concurrent
- **Duration**: 300 seconds
- **Expected**: All thresholds met

```bash
./scripts/run_load_tests.sh
```

### Scenario 2: Stress Test
- **Users**: 1000-2000 concurrent
- **Duration**: 600 seconds
- **Expected**: Find breaking point

```bash
./scripts/run_load_tests.sh \
    --users-max 2000 \
    --spawn-rate 20 \
    --duration 600
```

### Scenario 3: Soak Test
- **Users**: 500 concurrent
- **Duration**: 3600 seconds (1 hour)
- **Expected**: Detect memory leaks

```bash
./scripts/run_load_tests.sh \
    --users-max 500 \
    --spawn-rate 5 \
    --duration 3600
```

---

## Monitoring & Analysis

### During Test Execution

```bash
# Terminal 1: Run tests
./scripts/run_load_tests.sh

# Terminal 2: Monitor system resources
watch -n 1 'free -h; echo "---"; df -h; echo "---"; top -bn1 | head -15'

# Terminal 3: Monitor API logs
docker-compose logs -f backend | grep -E "ERROR|WARNING|latency"

# Terminal 4: Monitor database
docker-compose exec postgres \
    psql -U devstack -d devstack \
    -c "SELECT count(*) FROM pg_stat_activity WHERE state='active';"
```

### After Test Completion

```bash
# View HTML report
open load_test_reports/locust_report.html

# Analyze CSV data
head -20 load_test_reports/load_test_stats.csv

# Check JSON metrics
cat load_test_reports/load_test_metrics.json | python3 -m json.tool

# View test log
tail -100 load_test_reports/load_test.log
```

---

## Performance Baselines

### Success Rate Thresholds
| Component | Threshold | Purpose |
|-----------|-----------|---------|
| Auth API | ≥ 99% | Critical authentication |
| Generation API | ≥ 95% | Core functionality |
| Payments API | ≥ 95% | Financial transactions |

### Response Time Thresholds
| Component | P95 | P99 | Purpose |
|-----------|-----|-----|---------|
| Auth API | ≤ 200ms | ≤ 300ms | Fast auth required |
| Generation API | ≤ 500ms | ≤ 800ms | Sustained throughput |
| Payments API | ≤ 300ms | ≤ 500ms | User experience |

### Resource Thresholds at Max Load (1000 users)
- CPU: 60-80% (peak)
- Memory: 70-85%
- Database connections: 80-90% of pool
- Network bandwidth: < 60%

See [Performance Baselines](./PERFORMANCE_BASELINES.md) for detailed metrics.

---

## CI/CD Integration

### Workflow Trigger

```bash
# Trigger via GitHub CLI
gh workflow run load-testing.yml -f environment=staging

# Or via GitHub Web UI:
# 1. Go to Actions tab
# 2. Select "Load Testing" workflow
# 3. Click "Run workflow"
# 4. Select environment and parameters
```

### Workflow Parameters

- **environment**: choose `compose` or `staging`
- **users_max**: maximum concurrent users (default: 1000)
- **duration**: test duration in seconds (default: 300)
- **spawn_rate**: users per second (default: 10)

### Results & Artifacts

```bash
# Download latest test results
gh run download <RUN_ID> -n load-test-reports-<api>-<RUN_ID>

# View in GitHub Actions:
# 1. Go to Actions tab
# 2. Select completed run
# 3. Download artifacts
# 4. Expand "Summary" for results overview
```

---

## Test Configuration

### Environment Variables

Key settings in `.env.load-testing`:

```bash
# API endpoint
LOAD_TEST_HOST=http://localhost:8000

# User concurrency
LOAD_TEST_USERS_MIN=100
LOAD_TEST_USERS_MAX=1000
LOAD_TEST_SPAWN_RATE=10

# Test duration (seconds)
LOAD_TEST_DURATION_SECONDS=300

# Success thresholds
AUTH_SUCCESS_RATE_THRESHOLD=0.99
GENERATION_SUCCESS_RATE_THRESHOLD=0.95
PAYMENTS_SUCCESS_RATE_THRESHOLD=0.95

# Latency thresholds (milliseconds)
AUTH_P95_LATENCY_MS=200
GENERATION_P95_LATENCY_MS=500
PAYMENTS_P95_LATENCY_MS=300

# Report output
LOAD_TEST_REPORT_DIR=./load_test_reports
```

---

## Troubleshooting

### API Not Responding
```bash
# Check if API is running
curl http://localhost:8000/health

# If using Docker Compose
docker-compose ps
docker-compose logs backend

# Start services if needed
docker-compose up -d
```

### High Error Rates
```bash
# Reduce load
./scripts/run_load_tests.sh --users-max 100

# Check API logs for errors
docker-compose logs backend | grep ERROR

# Check database
docker-compose logs postgres | tail -50
```

### Memory Issues
```bash
# Reduce concurrent users
./scripts/run_load_tests.sh --users-max 50

# Check system resources
free -h
```

See [Operations Guide](./LOAD_TESTING_OPS_GUIDE.md) for more troubleshooting.

---

## Key Files & Directories

### Source Code
- `load_tests/` - Test framework implementation
- `load_tests/locustfile.py` - Test scenarios
- `load_tests/utils.py` - Utilities
- `load_tests/config.py` - Configuration
- `load_tests/data_seeder.py` - Test data

### Configuration
- `.env.load-testing` - Test environment defaults
- `.env.load-testing.local` - Your local overrides (create as needed)

### Scripts
- `scripts/run_load_tests.sh` - Main execution script

### CI/CD
- `.github/workflows/load-testing.yml` - GitHub Actions workflow

### Documentation
- `docs/LOAD_TESTING.md` - Complete guide
- `docs/LOAD_TESTING_QUICKSTART.md` - Quick start
- `docs/PERFORMANCE_BASELINES.md` - Baselines
- `docs/LOAD_TESTING_OPS_GUIDE.md` - Operations
- `docs/LOAD_TESTING_INDEX.md` - This file

### Output
- `load_test_reports/` - Test results (HTML, CSV, JSON, logs)

---

## Common Tasks

### Run a quick test
```bash
./scripts/run_load_tests.sh
```

### Test specific host
```bash
./scripts/run_load_tests.sh --host https://api.example.com
```

### Compare with baseline
```bash
# See docs/PERFORMANCE_BASELINES.md for comparison process
```

### Archive results
```bash
mkdir -p load_test_reports/archive/$(date +%Y-%m-%d)
cp load_test_reports/*.html load_test_reports/archive/$(date +%Y-%m-%d)/
```

### Generate custom load profile
```bash
for users in 100 250 500 1000; do
    ./scripts/run_load_tests.sh --users-max $users \
        --output load_test_reports/profile_$users
done
```

---

## Next Steps

1. **First Time**: Read [Quickstart Guide](./LOAD_TESTING_QUICKSTART.md)
2. **Ready to Test**: Run `./scripts/run_load_tests.sh`
3. **Review Results**: Open `load_test_reports/locust_report.html`
4. **Understand Baselines**: Read [Performance Baselines](./PERFORMANCE_BASELINES.md)
5. **Operational Use**: Review [Operations Guide](./LOAD_TESTING_OPS_GUIDE.md)

---

## Support & References

### Documentation
- [Locust Official Docs](https://locust.io/)
- [FastAPI Performance](https://fastapi.tiangolo.com/)
- [PostgreSQL Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)

### Getting Help
1. Check [Troubleshooting section](#troubleshooting)
2. Review [Operations Guide](./LOAD_TESTING_OPS_GUIDE.md)
3. Check GitHub Issues
4. Contact platform team

### Feedback & Improvements
- Report issues or suggestions
- Contribute improvements
- Share performance insights
- Update documentation as needed
