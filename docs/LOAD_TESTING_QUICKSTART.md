# Load Testing Quickstart Guide

Get up and running with load testing in 5 minutes.

## 1. Install Dependencies

```bash
pip install -r load_tests/requirements.txt
```

## 2. Start Your API (if not already running)

```bash
# Option A: Docker Compose
docker-compose up -d

# Option B: Direct run (if already configured)
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## 3. Run Load Tests

```bash
# Option A: Using the script (recommended)
./scripts/run_load_tests.sh

# Option B: Interactive Locust UI
locust -f load_tests/locustfile.py -H http://localhost:8000

# Option C: Custom parameters
./scripts/run_load_tests.sh --users-max 500 --duration 120
```

## 4. View Results

```bash
# Open HTML report
open load_test_reports/locust_report.html

# Or view in browser
# macOS: open load_test_reports/locust_report.html
# Linux: xdg-open load_test_reports/locust_report.html
# Windows: start load_test_reports/locust_report.html
```

## Next Steps

- Read the full documentation: `docs/LOAD_TESTING.md`
- Customize test scenarios in `load_tests/locustfile.py`
- Adjust thresholds in `.env.load-testing`
- Run against staging: `./scripts/run_load_tests.sh --host https://staging.example.com`

## Common Commands

```bash
# Test with 250 concurrent users for 5 minutes
./scripts/run_load_tests.sh --users-max 250 --duration 300

# Test a specific host
./scripts/run_load_tests.sh --host https://api.staging.com

# Generate only JSON report (for CI/CD)
./scripts/run_load_tests.sh --json-only

# Interactive testing (web UI)
locust -f load_tests/locustfile.py

# Help
./scripts/run_load_tests.sh --help
```

## Performance Baselines (Expected Results)

| Endpoint | Success Rate | P95 Latency |
|----------|--------------|-------------|
| Auth API | ≥ 99% | ≤ 200ms |
| Generation API | ≥ 95% | ≤ 500ms |
| Payments API | ≥ 95% | ≤ 300ms |

## Troubleshooting

**"Connection refused"**
```bash
# Check if API is running
curl http://localhost:8000/health

# Start Docker services
docker-compose up -d
```

**"High error rate"**
```bash
# Reduce concurrent users
./scripts/run_load_tests.sh --users-max 100

# Check API logs
docker-compose logs backend
```

**"Reports not generated"**
```bash
# Create reports directory
mkdir -p load_test_reports

# Check permissions
ls -la load_test_reports/
```

That's it! You're ready to load test. 🚀
