# Load Testing Operations Guide

Operational procedures for running and maintaining load testing infrastructure.

## Table of Contents

1. [Pre-Test Checklist](#pre-test-checklist)
2. [Running Tests](#running-tests)
3. [Monitoring During Tests](#monitoring-during-tests)
4. [Analyzing Results](#analyzing-results)
5. [Post-Test Activities](#post-test-activities)
6. [Incident Response](#incident-response)
7. [Maintenance](#maintenance)

## Pre-Test Checklist

### Environment Verification

```bash
#!/bin/bash
# Pre-test verification script

echo "=== Environment Verification ==="

# Check API health
echo "Checking API health..."
if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✓ API is healthy"
else
    echo "✗ API is not responding"
    exit 1
fi

# Check database connectivity
echo "Checking database..."
docker-compose exec postgres pg_isready -U devstack
if [ $? -eq 0 ]; then
    echo "✓ Database is ready"
else
    echo "✗ Database is not ready"
    exit 1
fi

# Check Redis
echo "Checking Redis..."
redis-cli ping
if [ $? -eq 0 ]; then
    echo "✓ Redis is ready"
else
    echo "✗ Redis is not responding"
    exit 1
fi

# Check disk space
DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo "✓ Disk space OK ($DISK_USAGE%)"
else
    echo "⚠️  Low disk space ($DISK_USAGE%)"
fi

# Check memory
FREE_MEM=$(free -m | awk 'NR==2 {print $7}')
if [ "$FREE_MEM" -gt 1000 ]; then
    echo "✓ Memory available (${FREE_MEM}MB)"
else
    echo "⚠️  Low memory (${FREE_MEM}MB)"
fi

echo ""
echo "Environment ready for load testing!"
```

### Resource Cleanup

```bash
# Clear previous test data
docker-compose exec postgres psql -U devstack -d devstack -c "TRUNCATE TABLE generation_tasks CASCADE;"

# Clear Redis cache
redis-cli FLUSHDB

# Clear old reports
rm -rf load_test_reports/*

# Verify cleanup
echo "✓ Environment cleaned"
```

### Load Test Configuration Review

```bash
# Review current settings
cat .env.load-testing

# Key settings to verify:
# - LOAD_TEST_HOST: Correct API endpoint
# - LOAD_TEST_USERS_MAX: Appropriate user count
# - LOAD_TEST_DURATION_SECONDS: Test duration
# - Threshold values: Match acceptance criteria
```

## Running Tests

### Method 1: Automated Script (Recommended)

```bash
# Basic test with defaults
./scripts/run_load_tests.sh

# Custom configuration
./scripts/run_load_tests.sh \
    --host https://staging.example.com \
    --users-max 500 \
    --spawn-rate 5 \
    --duration 600 \
    --output ./test_reports
```

### Method 2: Interactive Locust UI

```bash
# Start Locust web UI
locust -f load_tests/locustfile.py -H http://localhost:8000

# Access at http://localhost:8089
# Configure users and spawn rate in web UI
# Click "Start swarming"
```

### Method 3: Direct Headless Execution

```bash
python3 -m locust \
    -f load_tests/locustfile.py \
    -H http://localhost:8000 \
    --headless \
    --users 1000 \
    --spawn-rate 10 \
    --run-time 300s \
    --csv=load_test_results \
    --html=load_test_report.html
```

### Method 4: Distributed Load Testing

```bash
# Terminal 1: Start master
locust -f load_tests/locustfile.py \
    -H http://localhost:8000 \
    --master \
    --expect-workers 4

# Terminal 2-5: Start workers (on same or different machines)
locust -f load_tests/locustfile.py \
    -H http://localhost:8000 \
    --worker \
    --master-host=127.0.0.1
```

## Monitoring During Tests

### Real-Time Metrics

```bash
# Open a second terminal to monitor system resources
watch -n 1 'free -h; echo "---"; df -h; echo "---"; top -bn1 | head -20'

# Or use individual commands
# Monitor CPU and memory
top -b -u devstack | head -20

# Monitor disk I/O
iostat -x 1

# Monitor network
iftop -n

# Monitor database connections
docker-compose exec postgres \
    psql -U devstack -d devstack \
    -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"
```

### API Metrics Collection

```bash
# Monitor API response times in real time
watch -n 2 'tail -20 load_test_reports/load_test.log | grep -E "requests|response"'

# Monitor specific endpoints
docker-compose logs -f backend | grep -E "generation|auth|payment"
```

### Locust Metrics

During interactive testing:
- **Current Users**: Real-time user count
- **Requests/sec**: Current throughput
- **Failures/sec**: Current failure rate
- **Response Times**: Live p50, p95, p99 graphs
- **Total Requests**: Cumulative count

### Early Warning Signs

```
⚠️ WARNING SIGNS:
- Response time trending upward (latency increase)
- Error rate climbing (failures increase)
- CPU > 85%
- Memory > 85%
- Database connections at pool limit
- Redis memory > 80%
```

## Analyzing Results

### Quick Analysis

```bash
# View summary statistics
tail -50 load_test_reports/load_test.log | grep -E "Locust|requests|failures"

# Extract key metrics
grep -E "response|failures|requests" load_test_reports/load_test_stats.csv
```

### Detailed Analysis

```bash
# Parse CSV results with Python
python3 << 'EOF'
import csv
import statistics

with open('load_test_reports/load_test_stats.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    
    # Analyze each endpoint
    for row in rows:
        if row.get('Name') and row['Name'] != 'Total':
            requests = int(row.get('Requests', 0))
            failures = int(row.get('Failures', 0))
            median = float(row.get('Median', 0))
            p95 = float(row.get('95%', 0))
            
            success_rate = ((requests - failures) / requests * 100) if requests > 0 else 0
            
            print(f"\n{row['Name']}")
            print(f"  Requests: {requests}")
            print(f"  Failures: {failures}")
            print(f"  Success Rate: {success_rate:.2f}%")
            print(f"  Median (ms): {median}")
            print(f"  P95 (ms): {p95}")
EOF
```

### HTML Report Review

1. Open `load_test_reports/locust_report.html`
2. Check sections:
   - **Response Times** - Look for trends
   - **Number of Requests** - Verify steady load
   - **Failures** - Should be near zero
   - **Response Time Percentiles** - Check p95, p99

### Comparison Against Baselines

```bash
# Compare with previous baseline
python3 << 'EOF'
import json

# Load current results
with open('load_test_reports/results.json') as f:
    current = json.load(f)

# Load baseline
with open('docs/baselines/baseline.json') as f:
    baseline = json.load(f)

# Compare
for metric in ['success_rate', 'p95_latency']:
    current_val = current.get(metric)
    baseline_val = baseline.get(metric)
    
    if current_val and baseline_val:
        diff = current_val - baseline_val
        pct_change = (diff / baseline_val) * 100 if baseline_val else 0
        
        status = "✓" if abs(pct_change) < 5 else "⚠️"
        print(f"{status} {metric}: {current_val} (baseline: {baseline_val}, {pct_change:+.1f}%)")
EOF
```

## Post-Test Activities

### Results Archival

```bash
#!/bin/bash
# Archive test results

TEST_DATE=$(date +"%Y-%m-%d_%H-%M-%S")
ARCHIVE_DIR="load_test_reports/archive/$TEST_DATE"

mkdir -p "$ARCHIVE_DIR"

# Copy reports
cp -r load_test_reports/*.html "$ARCHIVE_DIR/"
cp -r load_test_reports/*.csv "$ARCHIVE_DIR/"
cp -r load_test_reports/*.json "$ARCHIVE_DIR/"
cp load_test_reports/load_test.log "$ARCHIVE_DIR/" 2>/dev/null

echo "Results archived to: $ARCHIVE_DIR"
```

### Data Cleanup

```bash
# Remove test data from database
docker-compose exec postgres psql -U devstack -d devstack << EOF
    DELETE FROM generation_tasks WHERE created_by IN (
        SELECT id FROM users WHERE email LIKE 'loadtest%'
    );
    DELETE FROM users WHERE email LIKE 'loadtest%';
EOF

# Vacuum database
docker-compose exec postgres \
    psql -U devstack -d devstack -c "VACUUM ANALYZE;"

# Clear Redis
redis-cli FLUSHDB

echo "✓ Data cleaned"
```

### Reporting

```bash
# Generate summary report
cat > load_test_reports/RESULTS_SUMMARY.md << 'EOF'
# Load Test Results

**Date**: $(date)
**Environment**: $(cat .env.load-testing | grep LOAD_TEST_HOST)
**Duration**: 300 seconds

## Key Metrics
- Auth API Success Rate: X%
- Generation API Success Rate: X%
- Generation API P95 Latency: Xms
- Payments API Success Rate: X%

## Pass/Fail: PASS/FAIL

## Notes
- [Add observations]
- [Add issues if any]
- [Recommendations]

EOF
```

## Incident Response

### High Error Rate (>5%)

```bash
# 1. Stop the test
# Ctrl+C in Locust terminal

# 2. Check API logs
docker-compose logs backend --tail=100

# 3. Check for specific errors
docker-compose logs backend | grep -i "error\|exception\|500"

# 4. Check database
docker-compose logs postgres --tail=50

# 5. Check system resources
free -h && df -h && top -b -n 1 | head -10

# 6. Investigate root cause
# - Database connection pool exhaustion?
# - Out of memory?
# - Slow queries?
# - API bugs?
```

### High Latency (P95 > 1s)

```bash
# 1. Check database query performance
docker-compose exec postgres psql -U devstack -d devstack << EOF
    SELECT query, calls, total_time, mean_time 
    FROM pg_stat_statements 
    ORDER BY mean_time DESC 
    LIMIT 10;
EOF

# 2. Check for slow queries
docker-compose logs postgres | grep "duration"

# 3. Check API metrics
curl http://localhost:9090/api/v1/metrics | grep latency

# 4. Check resource saturation
# CPU: top
# Memory: free -h
# Disk I/O: iostat -x 1
```

### Service Crash

```bash
# 1. Check service status
docker-compose ps

# 2. View error logs
docker-compose logs backend --tail=200

# 3. Check resource limits
docker stats

# 4. Restart service
docker-compose restart backend

# 5. Verify recovery
curl http://localhost:8000/health
```

## Maintenance

### Regular Tasks

#### Weekly
```bash
# Review baseline metrics
cat docs/PERFORMANCE_BASELINES.md

# Check for performance regressions
# Compare last week's test results
```

#### Monthly
```bash
# Run full stress test
./scripts/run_load_tests.sh --users-max 2000 --duration 600

# Run soak test
./scripts/run_load_tests.sh --users-max 500 --duration 3600

# Archive all results
./scripts/archive_results.sh
```

#### Quarterly
```bash
# Comprehensive performance review
# Compare all metrics over 3 months
# Document trends and changes

# Update baselines if improvements made
# Update documentation with lessons learned
```

### Dependency Updates

```bash
# Check for Locust updates
pip index versions locust

# Update if available
pip install --upgrade locust

# Test with new version
locust --version
./scripts/run_load_tests.sh --users-max 100 --duration 60
```

### CI/CD Integration

```bash
# Monitor CI/CD load test runs
# Check GitHub Actions artifacts
# Review failed tests
# Update thresholds if needed

# Example: Retrieve latest artifact
gh run list --workflow=load-testing.yml --limit=5

# Download results
gh run download <RUN_ID> -n load-test-reports
```

## Troubleshooting Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Connection refused" | API not running | Start services: `docker-compose up -d` |
| High error rate | Rate limiting | Reduce spawn rate or users |
| Memory issues | Test process leaking | Reduce user count, restart Locust |
| Slow results | Network latency | Use local/private network |
| No reports generated | Permission denied | Check directory permissions |
| Database errors | Connection pool exhausted | Check `max_connections` setting |

## Support Contacts

- Platform Team: platform@example.com
- DevOps Team: devops@example.com
- Performance Optimization Team: perf@example.com

## References

- [Locust Documentation](https://locust.io/)
- [Performance Baselines](./PERFORMANCE_BASELINES.md)
- [Load Testing Guide](./LOAD_TESTING.md)
- [API Documentation](../README.md)
