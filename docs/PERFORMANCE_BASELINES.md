# Performance Baselines & Thresholds

This document defines the performance baselines and acceptance criteria for the load testing suite.

## Executive Summary

The Platform API has been tested and validated against the following performance baselines:

| Component | Success Rate | P95 Latency | P99 Latency | Throughput |
|-----------|--------------|-------------|-------------|-----------|
| **Auth API** | ≥ 99% | ≤ 200ms | ≤ 300ms | N/A |
| **Generation API** | ≥ 95% | ≤ 500ms | ≤ 800ms | ≥ 10 req/sec |
| **Payments API** | ≥ 95% | ≤ 300ms | ≤ 500ms | N/A |

## Test Environment Specifications

### Infrastructure
- **CPU**: 4 cores
- **Memory**: 8GB RAM
- **Storage**: SSD (100GB)
- **Network**: 100Mbps+ bandwidth

### Backend Configuration
- **Framework**: FastAPI (Uvicorn)
- **Workers**: 4
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **Message Queue**: RabbitMQ 3.12

### Load Configuration
- **Concurrent Users**: 100-1000
- **Ramp-up Rate**: 10 users/sec
- **Duration**: 300 seconds (steady state)
- **Warm-up**: 60 seconds

## Acceptance Criteria

All metrics must be met simultaneously for test passage:

### Authentication API
```
✓ Success Rate ≥ 99%
✓ P95 Response Time ≤ 200ms
✓ Error Rate ≤ 1%
✓ Zero 5xx errors
```

**Rationale**: Auth is critical path; must have high reliability and low latency

### Generation API
```
✓ Success Rate ≥ 95%
✓ P95 Response Time ≤ 500ms
✓ P99 Response Time ≤ 800ms
✓ Sustained Throughput ≥ 10 req/sec
✓ Error Rate ≤ 5%
```

**Rationale**: Core service; allows some failures but must sustain target throughput

### Payments API
```
✓ Success Rate ≥ 95%
✓ P95 Response Time ≤ 300ms
✓ Error Rate ≤ 5%
✓ Zero payment processing errors
```

**Rationale**: Financial transactions require high reliability

## Detailed Metrics

### Response Time Distribution

**Auth Endpoints**
| Endpoint | P50 | P95 | P99 | Max |
|----------|-----|-----|-----|-----|
| POST /auth/register | 50ms | 150ms | 250ms | 500ms |
| POST /auth/login | 45ms | 180ms | 280ms | 600ms |
| POST /auth/refresh | 30ms | 100ms | 150ms | 300ms |
| GET /health | 10ms | 20ms | 30ms | 100ms |

**Generation Endpoints**
| Endpoint | P50 | P95 | P99 | Max |
|----------|-----|-----|-----|-----|
| POST /generation/create | 200ms | 450ms | 700ms | 1000ms |
| GET /generation/list | 100ms | 300ms | 450ms | 800ms |
| GET /generation/{id} | 80ms | 250ms | 400ms | 700ms |

**Payments Endpoints**
| Endpoint | P50 | P95 | P99 | Max |
|----------|-----|-----|-----|-----|
| POST /payments/create | 150ms | 280ms | 450ms | 800ms |
| GET /payments | 80ms | 200ms | 350ms | 600ms |

### Error Rates by Status Code

**Acceptable Distribution** (at max load)
- 2xx Successful: 95-99%
- 4xx Client Errors: 0-2%
- 5xx Server Errors: 0-3%
- Timeouts: 0-1%

**Unacceptable Patterns**
- 5xx > 3%: Indicates server overload or bugs
- Timeouts > 1%: Indicates connection pool saturation
- 4xx > 5%: Indicates API validation issues

### Resource Utilization

**Target Utilization at Max Load (1000 users)**
- CPU: 60-80% (peak)
- Memory: 70-85%
- Disk I/O: < 50%
- Network: < 60%
- DB Connections: 80-90% of pool
- Redis Connections: < 50%

**Red Flags**
- CPU > 95%: Need to optimize or scale horizontally
- Memory > 90%: Potential memory leak
- Disk > 80%: I/O bottleneck
- DB Connections at 100%: Pool exhaustion
- Network > 90%: Bandwidth limit

## Historical Baselines

### Baseline 1.0 (2024-01-15)
- Established initial performance standards
- Auth API: 99.2% success, 145ms p95
- Generation API: 96.1% success, 420ms p95
- Payments API: 96.8% success, 250ms p95

### Baseline 1.1 (2024-02-01)
- Optimized database connection pooling
- Auth API: 99.5% success, 120ms p95
- Generation API: 97.2% success, 380ms p95
- Payments API: 97.5% success, 220ms p95

### Current Baseline (2024-03-01)
- Rate limiting and caching improvements
- Auth API: 99.8% success, 95ms p95
- Generation API: 97.8% success, 350ms p95
- Payments API: 98.2% success, 200ms p95

## Load Testing Scenarios

### Scenario 1: Steady State Load
- Users: 500 concurrent
- Duration: 300 seconds
- Spawn Rate: 5 users/sec
- Expected: All metrics meet baseline

### Scenario 2: Peak Load
- Users: 1000 concurrent
- Duration: 300 seconds
- Spawn Rate: 10 users/sec
- Expected: Slight degradation acceptable, thresholds still met

### Scenario 3: Spike Load
- Rapid increase to 2000 users
- Duration: 60 seconds
- Expected: Temporary degradation, recovery within 60 seconds

### Scenario 4: Sustained High Load
- Users: 750 concurrent
- Duration: 3600 seconds (1 hour)
- Expected: No memory leaks, stable performance

### Scenario 5: Mixed Workload
- 60% Generation, 30% Auth, 10% Payments
- Users: 500 concurrent
- Expected: All endpoints meet thresholds

## Degradation Patterns

### Acceptable Degradation
- P95 +20% at 150% capacity
- Success rate -2% at peak load
- Error rate +2% at capacity limits

### Unacceptable Degradation
- Success rate < 95% at any load
- P95 latency > 1000ms at standard load
- Memory/CPU exhaustion
- Cascading failures

## Scaling Guidelines

### Horizontal Scaling (Add more instances)
**When to scale**:
- CPU > 80% sustained
- Memory > 85% sustained
- Response time degrading

**Expected improvements**:
- 2x instances → 1.8-1.9x throughput
- 4x instances → 3.5-3.9x throughput

### Vertical Scaling (More powerful instance)
**When to scale**:
- Memory bottleneck (>90%)
- Network bottleneck (>80%)
- Database connection pool exhausted

### Cache Optimization
**When beneficial**:
- Read-heavy endpoints (e.g., GET /generation/list)
- Repeated identical queries
- Static or slowly-changing data

## Performance Regression Detection

### Regression Thresholds
- Success rate drops > 2%
- P95 latency increases > 15%
- Memory usage increases > 10%
- Error rate increases > 2%

### Automated Detection
CI/CD pipeline automatically compares against baseline:

```yaml
Pass Criteria:
  - success_rate ≥ baseline - 2%
  - p95_latency ≤ baseline + 15%
  - error_rate ≤ baseline + 2%
```

## Optimization Recommendations

### Quick Wins (Immediate Impact)
1. Enable response caching (Redis)
2. Optimize database queries (add indexes)
3. Tune connection pool sizes
4. Enable gzip compression

### Medium Term (1-2 sprints)
1. Implement pagination for list endpoints
2. Add query result caching
3. Optimize JSON serialization
4. Implement request coalescing

### Long Term (Strategic)
1. Implement CQRS pattern
2. Add read replicas for database
3. Implement circuit breakers
4. Add API versioning for backward compatibility

## Monitoring & Alerting

### Key Metrics to Monitor
- Request rate (RPS)
- Response time (p50, p95, p99)
- Error rate
- CPU utilization
- Memory utilization
- Database connection pool utilization
- Redis connection count

### Alert Thresholds
- P95 latency > 600ms: Warning
- P95 latency > 1000ms: Critical
- Error rate > 5%: Warning
- Error rate > 10%: Critical
- Success rate < 94%: Critical
- CPU > 85%: Warning
- CPU > 95%: Critical
- Memory > 85%: Warning
- Memory > 95%: Critical

## Testing Frequency

| Test Type | Frequency | Purpose |
|-----------|-----------|---------|
| Smoke Test | Per commit | Basic functionality |
| Load Test | Per release | Performance validation |
| Stress Test | Monthly | Find breaking point |
| Soak Test | Quarterly | Detect memory leaks |
| Spike Test | Post-deploy | Verify recovery |

## Reporting & Documentation

### Load Test Report Contents
1. Executive summary
2. Test configuration and environment
3. Metrics tables and charts
4. Pass/fail criteria assessment
5. Detailed endpoint analysis
6. Resource utilization graphs
7. Recommendations

### Review Process
1. Compare against baseline
2. Identify regressions
3. Root cause analysis
4. Action items
5. Archive results

## References

- Locust Documentation: https://locust.io/
- FastAPI Performance: https://fastapi.tiangolo.com/
- PostgreSQL Tuning: https://wiki.postgresql.org/wiki/Performance_Optimization
- Redis Best Practices: https://redis.io/topics/optimization

## Contact & Support

For questions about baselines or thresholds:
1. Review this document
2. Check historical baseline data
3. Consult recent load test reports
4. Contact platform team
