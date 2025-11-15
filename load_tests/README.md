# Load Testing Suite

Distributed load testing suite for the Platform API using Locust.

## Quick Start

```bash
# Install dependencies
pip install -r load_tests/requirements.txt

# Run tests
./scripts/run_load_tests.sh

# View results
open load_test_reports/locust_report.html
```

## What's Included

- **locustfile.py** - Main load test scenarios for auth, generation, and payments APIs
- **utils.py** - Utility functions for token generation, test data, and metrics
- **config.py** - Configuration management
- **data_seeder.py** - Synthetic data generation for isolated testing
- **report_generator.py** - HTML and JSON report generation
- **conftest.py** - Pytest fixtures for load testing
- **requirements.txt** - Python dependencies

## Usage Examples

### Interactive Testing (Web UI)
```bash
locust -f load_tests/locustfile.py
# Open http://localhost:8089
```

### Automated Testing
```bash
# Basic run
./scripts/run_load_tests.sh

# Custom parameters
./scripts/run_load_tests.sh \
  --host https://api.example.com \
  --users-max 500 \
  --duration 600
```

### Direct Locust
```bash
python3 -m locust \
  -f load_tests/locustfile.py \
  -H http://localhost:8000 \
  --headless \
  -u 1000 \
  -r 10 \
  -t 300s
```

## Performance Targets

| Component | Metric | Target |
|-----------|--------|--------|
| Auth API | Success Rate | ≥ 99% |
| Auth API | P95 Latency | ≤ 200ms |
| Generation API | Success Rate | ≥ 95% |
| Generation API | P95 Latency | ≤ 500ms |
| Generation API | Throughput | ≥ 10 req/sec |
| Payments API | Success Rate | ≥ 95% |
| Payments API | P95 Latency | ≤ 300ms |

## Load Profiles

### Standard Load (Default)
- **Users**: 100 - 1000 concurrent
- **Spawn Rate**: 10 users/sec
- **Duration**: 300 seconds (5 minutes)

### Stress Test
- **Users**: 1000 - 2000 concurrent
- **Spawn Rate**: 20 users/sec
- **Duration**: 600 seconds (10 minutes)

### Soak Test
- **Users**: 500 concurrent
- **Spawn Rate**: 5 users/sec
- **Duration**: 3600 seconds (1 hour)

## Configuration

See `.env.load-testing` for all available settings:

```bash
# API endpoint
LOAD_TEST_HOST=http://localhost:8000

# Concurrent user range
LOAD_TEST_USERS_MIN=100
LOAD_TEST_USERS_MAX=1000

# Ramp-up rate (users per second)
LOAD_TEST_SPAWN_RATE=10

# Test duration (seconds)
LOAD_TEST_DURATION_SECONDS=300

# Success rate thresholds
AUTH_SUCCESS_RATE_THRESHOLD=0.99
GENERATION_SUCCESS_RATE_THRESHOLD=0.95
PAYMENTS_SUCCESS_RATE_THRESHOLD=0.95

# Latency thresholds (milliseconds)
AUTH_P95_LATENCY_MS=200
GENERATION_P95_LATENCY_MS=500
PAYMENTS_P95_LATENCY_MS=300

# Report output
LOAD_TEST_REPORT_DIR=./load_test_reports
LOAD_TEST_REPORT_FORMAT=html
```

## Reports

### HTML Report
Generated automatically by Locust. Features:
- Request/response statistics
- Response time distribution
- Error breakdown
- Failure logs
- Charts and graphs

**Location**: `load_test_reports/locust_report.html`

### JSON Report
Machine-readable metrics for CI/CD integration.

**Location**: `load_test_reports/load_test_metrics.json`

### CSV Results
Detailed per-endpoint statistics.

**Location**: `load_test_reports/load_test_*.csv`

## CI/CD Integration

Manual-trigger workflow: `.github/workflows/load-testing.yml`

```bash
# Trigger via GitHub Actions
gh workflow run load-testing.yml -f environment=staging
```

## Documentation

- **LOAD_TESTING.md** - Comprehensive guide
- **LOAD_TESTING_QUICKSTART.md** - 5-minute quickstart
- **README.md** - This file

## Troubleshooting

### Connection Issues
```bash
# Check if API is running
curl http://localhost:8000/health

# Check API host in environment
echo $LOAD_TEST_HOST

# Start Docker services if needed
docker-compose up -d
```

### High Error Rates
```bash
# Reduce concurrent users
./scripts/run_load_tests.sh --users-max 100

# Check API logs
docker-compose logs backend

# Monitor system resources
top
```

### Memory Issues
```bash
# Reduce users or increase spawn time
./scripts/run_load_tests.sh --users-max 100 --spawn-rate 5
```

## Performance Optimization

1. **Test in dedicated environment** - Use staging or test environment
2. **Warm up before steady state** - Allow time for connection pooling
3. **Monitor resource usage** - CPU, memory, disk I/O
4. **Scale incrementally** - Start low, gradually increase load
5. **Run multiple times** - Ensure consistent results
6. **Profile the API** - Find actual bottlenecks
7. **Baseline comparisons** - Track improvements over time

## Advanced Features

### Custom Test Scenarios
Edit `locustfile.py` to add custom user behaviors:

```python
class CustomUser(HttpUser):
    @task(5)
    def custom_endpoint(self):
        self.client.get("/api/custom")
```

### Distributed Testing
Run on multiple machines:

```bash
# Master
locust -f locustfile.py -H http://api --master --expect-workers 4

# Worker (on different machine)
locust -f locustfile.py -H http://api --worker --master-host=master_ip
```

### Custom Metrics
Extend MetricsCollector in utils.py for additional analytics.

## Dependencies

- **locust** ≥ 2.15.0 - Load testing framework
- **python-dotenv** ≥ 1.0.0 - Environment configuration
- **requests** ≥ 2.31.0 - HTTP client
- **faker** ≥ 20.0.0 - Test data generation

## License

See root project license.

## Support

For issues or questions, refer to:
1. Troubleshooting section above
2. LOAD_TESTING.md documentation
3. Locust documentation: https://locust.io/
4. Project repository issues
