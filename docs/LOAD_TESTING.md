# Load Testing Suite

## Overview

This document provides comprehensive information about the load testing suite for the Platform API, covering auth, generation, and payments endpoints.

## Architecture

### Load Testing Framework

We use **Locust**, a Python-based distributed load testing tool because it:

- Is Python-based, consistent with the project stack
- Supports distributed load testing with multiple processes
- Provides extensible task scheduling and parametrization
- Generates realistic user behavior patterns
- Integrates well with CI/CD pipelines
- Has built-in reporting and metrics collection

### Test Scenarios

The suite implements three independent load test user classes targeting different APIs:

#### 1. AuthUser - Authentication API
- **Endpoints**: `/api/v1/auth/register`, `/api/v1/auth/login`, `/health`
- **Success Rate Threshold**: ≥ 99%
- **P95 Latency Threshold**: ≤ 200ms
- **Tasks**:
  - Register new users (30% weight)
  - Login with existing credentials (50% weight)
  - Health checks (20% weight)

#### 2. GenerationUser - Generation API
- **Endpoints**: `/api/v1/generation/create`, `/api/v1/generation/list`, `/api/v1/generation/{id}`
- **Success Rate Threshold**: ≥ 95%
- **P95 Latency Threshold**: ≤ 500ms
- **Target**: 10 generations/second across all concurrent users
- **Tasks**:
  - Create generation tasks (70% weight)
  - List generation tasks (30% weight)
  - Get task status (20% weight)

#### 3. PaymentUser - Payments API
- **Endpoints**: `/api/v1/payments/create`, `/api/v1/payments`
- **Success Rate Threshold**: ≥ 95%
- **P95 Latency Threshold**: ≤ 300ms
- **Tasks**:
  - Create payments (60% weight)
  - List payments (40% weight)

## Performance Baselines

### Target Metrics

| Metric | Auth | Generation | Payments |
|--------|------|------------|----------|
| Success Rate | ≥ 99% | ≥ 95% | ≥ 95% |
| P95 Latency | ≤ 200ms | ≤ 500ms | ≤ 300ms |
| Error Rate | ≤ 1% | ≤ 5% | ≤ 5% |

### Concurrent Load Levels

- **Minimum Users**: 100 concurrent
- **Maximum Users**: 1000 concurrent
- **Spawn Rate**: 10 users/second
- **Ramp-up Time**: 100 seconds (1000 users / 10 users/sec)
- **Steady State Duration**: 300 seconds (configurable)

### Expected Request Volume

- **Generation API**: 10 req/sec × 70% of users = ~70 generation requests/sec at max load
- **Authentication API**: Variable based on user lifecycle events
- **Payments API**: Variable based on user actions

## Installation & Setup

### Prerequisites

- Python 3.11+
- pip package manager
- Running API instance (local, Docker Compose, or staging)
- PostgreSQL (for data seeding, optional)
- Redis (for testing, optional)

### Install Dependencies

```bash
pip install -r load_tests/requirements.txt
```

Or for development:

```bash
pip install locust>=2.15.0 python-dotenv>=1.0.0 faker>=20.0.0
```

### Environment Configuration

Copy and configure the environment file:

```bash
cp .env.load-testing .env.load-testing.local
# Edit .env.load-testing.local with your settings
```

Key environment variables:

```bash
# API Configuration
LOAD_TEST_HOST=http://localhost:8000
LOAD_TEST_TIMEOUT=30

# Load Parameters
LOAD_TEST_USERS_MIN=100
LOAD_TEST_USERS_MAX=1000
LOAD_TEST_SPAWN_RATE=10
LOAD_TEST_DURATION_SECONDS=300

# Success Thresholds
AUTH_SUCCESS_RATE_THRESHOLD=0.99
GENERATION_SUCCESS_RATE_THRESHOLD=0.95
PAYMENTS_SUCCESS_RATE_THRESHOLD=0.95

# Latency Thresholds (milliseconds)
AUTH_P95_LATENCY_MS=200
GENERATION_P95_LATENCY_MS=500
PAYMENTS_P95_LATENCY_MS=300

# Report Configuration
LOAD_TEST_REPORT_DIR=./load_test_reports
```

## Running Load Tests

### Local Execution (Interactive Mode)

```bash
# Start Locust web UI
locust -f load_tests/locustfile.py -H http://localhost:8000

# Open http://localhost:8089 in your browser
# Configure number of users, spawn rate, and run the test
```

### Automated Execution (Headless Mode)

```bash
# Using the provided script (recommended)
./scripts/run_load_tests.sh

# With custom parameters
./scripts/run_load_tests.sh \
    --host https://staging.example.com \
    --users-max 500 \
    --duration 600 \
    --output ./test_reports
```

### Direct Locust Invocation

```bash
python3 -m locust \
    -f load_tests/locustfile.py \
    -H http://localhost:8000 \
    --headless \
    -u 1000 \
    -r 10 \
    -t 300s \
    --csv=load_test_results \
    --html=load_test_report.html
```

### Docker Compose Testing

```bash
# Start services
docker-compose up -d

# Wait for services to be healthy
sleep 30

# Run load tests
./scripts/run_load_tests.sh --host http://localhost:8000

# View results
open load_test_reports/locust_report.html
```

## Synthetic Data Seeding

The data seeder creates isolated test data for load testing:

```python
from load_tests.data_seeder import seed_test_data

# Seed 100 test users
result = await seed_test_data(
    database_url="postgresql://user:pass@localhost/load_test_db",
    test_user_count=100
)

print(f"Created {result['users_created']} users")
```

Or via command line:

```bash
LOAD_TEST_DATABASE_URL="postgresql://devstack:devstack@localhost:5432/load_test_db" \
python3 load_tests/data_seeder.py
```

## Report Generation

### HTML Reports

Locust automatically generates HTML reports:

```bash
# Report location after test completion
./load_test_reports/locust_report.html
```

Features:
- Visual metrics dashboard
- Request/response time charts
- Error distribution
- Response code breakdown
- Failure log

### JSON Reports

For CI/CD integration:

```bash
./load_test_reports/load_test_metrics.json
```

Contains:
- All metrics in machine-readable format
- Threshold comparisons
- Pass/fail status
- Timestamps and test metadata

## CI/CD Integration

### GitHub Actions Workflow

Manual trigger workflow in `.github/workflows/load-testing.yml`:

```yaml
name: Load Testing

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: 'staging'
        type: choice
        options:
          - staging
          - performance

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Run load tests
        env:
          LOAD_TEST_HOST: ${{ env.LOAD_TEST_HOST }}
        run: ./scripts/run_load_tests.sh
      
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: load-test-reports
          path: load_test_reports/
```

### Acceptance Criteria

Tests pass when ALL criteria are met:

```
✓ Auth API success rate ≥ 99%
✓ Generation API success rate ≥ 95%
✓ Generation API P95 latency ≤ 500ms
✓ Payments API success rate ≥ 95%
```

## Troubleshooting

### Common Issues

#### "Connection refused" / API unreachable

```bash
# Check if API is running
curl http://localhost:8000/health

# Check API logs
docker-compose logs backend

# Verify correct host in environment
echo $LOAD_TEST_HOST
```

#### High error rates or timeouts

1. **Check API performance first**:
   ```bash
   curl -w "\nResponse time: %{time_total}s\n" http://localhost:8000/health
   ```

2. **Reduce concurrent users**:
   ```bash
   ./scripts/run_load_tests.sh --users-max 100
   ```

3. **Check API logs for errors**:
   ```bash
   docker-compose logs backend --tail=100
   ```

4. **Verify database connections**:
   ```bash
   docker-compose logs postgres
   ```

#### Memory issues during load test

- Reduce `--users-max` to lower concurrent connections
- Run in separate terminal session
- Monitor system resources: `watch -n1 free -h`

#### Missing reports

```bash
# Check reports directory
ls -la load_test_reports/

# Create directory if needed
mkdir -p load_test_reports
```

## Performance Optimization Tips

### API Optimization

1. **Database Connection Pooling**
   - Verify connection pool settings in `backend/app/db.py`
   - Monitor active connections during load tests

2. **Response Caching**
   - Consider caching read-heavy endpoints
   - Implement Redis caching for generation task listings

3. **Rate Limiting**
   - Current rate limits may need adjustment for load tests
   - Verify rate limit settings in `.env.docker`

### Load Test Optimization

1. **Use Locust Masters/Slaves for Distributed Testing**
   ```bash
   # Master
   locust -f locustfile.py -H http://api --master --expect-workers 4
   
   # Worker (run on 4 different machines)
   locust -f locustfile.py -H http://api --worker --master-host=master_ip
   ```

2. **Increase Spawn Rate Gradually**
   - Start with lower spawn rates to avoid connection storms
   - Gradually increase to find the actual breaking point

3. **Use Weighted Tasks Appropriately**
   - Adjust task weights based on real usage patterns
   - Profile production to match realistic load distribution

## Advanced Usage

### Custom Load Test Scenarios

Create custom test user classes in `locustfile.py`:

```python
from locust import HttpUser, task, between

class CustomUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(10)
    def my_custom_test(self):
        self.client.get("/api/endpoint")
```

### Parametrized Testing

Test with different parameter combinations:

```bash
for users in 100 250 500 1000; do
    ./scripts/run_load_tests.sh --users-max $users \
        --output "./reports/users_$users"
done
```

### Comparative Analysis

Generate baseline reports and compare against:

```bash
# Baseline
./scripts/run_load_tests.sh --output ./baseline

# After optimization
./scripts/run_load_tests.sh --output ./optimized

# Compare metrics
diff baseline/load_test_metrics.json optimized/load_test_metrics.json
```

## Monitoring & Observability

### Real-time Metrics

During test execution, Locust provides real-time statistics:

- Request rate (RPS)
- Response times (min/avg/max/p50/p95/p99)
- Failure count and rate
- Active users count

### Post-Test Analysis

Review the HTML report:

1. **Response time distribution**: Identify slow endpoints
2. **Error patterns**: Check for specific failure modes
3. **Resource usage**: Monitor CPU/memory during tests
4. **Throughput**: Measure maximum sustainable RPS

### Integration with Observability Stacks

#### Prometheus Integration

Export metrics to Prometheus:

```python
from prometheus_client import Counter, Histogram

request_counter = Counter('load_test_requests_total', 'Total requests')
response_time = Histogram('load_test_response_time_seconds', 'Response time')
```

#### ELK Stack Integration

Send structured logs to Elasticsearch:

```python
import structlog

structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
)
```

## Best Practices

1. **Test in Isolation**: Use dedicated environment for load tests
2. **Seed Data Consistently**: Use deterministic data generation
3. **Warm Up**: Run ramp-up phase before steady state
4. **Monitor Resources**: Track CPU, memory, and disk during tests
5. **Document Baselines**: Store baseline metrics for comparison
6. **Regular Testing**: Run load tests as part of release process
7. **Gradual Ramp-up**: Don't spike to max users instantly
8. **Clean Up**: Remove test data after tests complete

## Files Reference

| File | Purpose |
|------|---------|
| `load_tests/__init__.py` | Package initialization |
| `load_tests/locustfile.py` | Main load test scenarios |
| `load_tests/utils.py` | Utility functions (token gen, metrics, etc.) |
| `load_tests/config.py` | Configuration management |
| `load_tests/data_seeder.py` | Synthetic data generation |
| `load_tests/report_generator.py` | HTML/JSON report generation |
| `load_tests/requirements.txt` | Python dependencies |
| `.env.load-testing` | Environment configuration |
| `scripts/run_load_tests.sh` | Execution script |
| `docs/LOAD_TESTING.md` | This documentation |

## Support & Issues

For issues or questions:

1. Check troubleshooting section above
2. Review API logs: `docker-compose logs backend`
3. Check load test logs: `cat load_test_reports/load_test.log`
4. Verify environment configuration: `env | grep LOAD_TEST`
5. Run health check: `curl http://localhost:8000/health`

## Future Enhancements

- [ ] WebSocket load testing for real-time APIs
- [ ] Database load testing (connection pool saturation)
- [ ] Multi-region load testing
- [ ] Custom metrics dashboard
- [ ] Automated performance regression detection
- [ ] Cost analysis per request
- [ ] Load test scheduling and automation
