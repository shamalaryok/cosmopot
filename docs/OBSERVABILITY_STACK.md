# Observability Stack Implementation

This document provides a comprehensive overview of the enhanced observability stack implemented for monitoring, alerting, and error tracking.

## Overview

The observability stack includes:
- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and notification
- **Sentry**: Error tracking and performance monitoring
- **Synthetic Monitoring**: Uptime checks and SLA verification

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Backend      │    │   Prometheus    │    │   Grafana       │
│   Services     │───▶│   Collection    │───▶│   Dashboards    │
│                │    │                 │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │                       ▼                       │
         │              ┌──────────────────┐            │
         │              │  Alertmanager   │            │
         │              │  Routing        │            │
         └──────────────▶│  Notifications │◀───────────┘
                        └──────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │   PagerDuty/    │
                        │   Email         │
                        └──────────────────┘

┌─────────────────┐    ┌──────────────────┐
│   Backend      │    │     Sentry      │
│   Services     │───▶│   Error        │
│                │    │   Tracking     │
└─────────────────┘    │                 │
         │              └──────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌──────────────────┐
│  Synthetic     │    │   Sentry        │
│  Monitoring    │    │   Dashboard    │
│  Uptime       │    │                 │
└─────────────────┘    └──────────────────┘
```

## Components

### 1. Prometheus Metrics

#### Business Metrics
- `generation_requests_total`: Total generation requests by status and model type
- `generation_duration_seconds`: Generation processing time distribution
- `active_generations`: Currently active generation tasks
- `payment_requests_total`: Payment requests by provider and status
- `payment_amount_total`: Total payment amounts processed
- `user_registrations_total`: User registrations by source
- `active_users`: Active users by timeframe

#### Infrastructure Metrics
- `http_requests_total`: HTTP requests by method, handler, and status
- `http_request_duration_seconds`: HTTP request latency distribution
- `queue_depth`: Queue size by queue name
- `database_connections_*`: Database connection pool metrics
- `cache_*_total`: Cache hit/miss metrics
- `system_*`: System resource usage

#### Configuration
```python
# backend/core/config.py
class PrometheusSettings(BaseSettings):
    enabled: bool = True
    metrics_path: str = "/metrics"
    excluded_handlers: list[str] = ["/metrics", "/health", "/docs", "/redoc"]
    default_buckets: list[float] = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, ...]
```

### 2. Grafana Dashboards

#### API Performance Dashboard
- Request rate by endpoint
- Response time heatmap
- P95 response time with thresholds
- Error rate monitoring
- Status code distribution

#### Business KPIs Dashboard
- Generation requests and success rate
- Active generations and duration trends
- Payment revenue tracking
- User registration metrics

#### Infrastructure Dashboard
- CPU, memory, disk usage
- Database connection pools
- Queue depth monitoring
- Cache hit rates

### 3. Alertmanager Configuration

#### Alert Routing
- **Critical alerts**: PagerDuty + Email
- **Warning alerts**: Email
- **Info alerts**: Email (business hours only)

#### Alert Groups
- API alerts (error rate, response time, service down)
- Business alerts (generation failures, queue depth, payments)
- Infrastructure alerts (CPU, memory, disk, connections)
- SLA alerts (availability, error rate thresholds)

#### Inhibition Rules
- Suppress lower severity alerts when critical alerts fire
- Prevent alert spam during widespread issues

### 4. Sentry Integration

#### Features
- Error tracking with context
- Performance monitoring
- Release tracking
- Environment tagging
- Custom breadcrumbs
- Transaction naming

#### Configuration
```python
# backend/core/config.py
class SentrySettings(BaseSettings):
    enabled: bool = True
    dsn: SecretStr | None = None
    environment: str | None = None
    sample_rate: float = 1.0
    enable_tracing: bool = True
    traces_sample_rate: float = 0.1
```

### 5. Synthetic Monitoring

#### Uptime Checks
- API health endpoint
- Detailed health endpoint
- Documentation endpoint
- Custom endpoints as needed

#### SLA Monitoring
- 99.5% availability target
- <1% error rate target
- <1s average response time target
- Continuous compliance verification

## Deployment

### Docker Services

```yaml
# Monitoring stack
services:
  prometheus:      # Metrics collection
  grafana:         # Visualization
  alertmanager:    # Alert routing
  postgres_exporter:  # DB metrics
  redis_exporter:     # Cache metrics
  node_exporter:      # Host metrics
  nginx_exporter:      # Proxy metrics
  sentry-relay:       # Error tracking relay
```

### Secrets Management
```bash
# Required secrets
sentry_dsn
pagerduty_service_key
grafana_password
alertmanager_config
```

## Usage

### Accessing Dashboards
- **Grafana**: `https://monitoring.local/grafana`
- **Prometheus**: `http://prometheus:9090`
- **Alertmanager**: `http://alertmanager:9093`

### Metrics Endpoint
- **Backend**: `http://backend:8000/metrics`
- **Health**: `http://backend:8000/health`

### SLA Monitoring
- **Status**: `http://backend:8000/sla/status`
- **Uptime**: `http://backend:8000/sla/uptime`

## Alert Thresholds

### SLA Targets
- **Availability**: ≥99.5%
- **Error Rate**: ≤1%
- **Response Time**: P95 ≤500ms

### Critical Alerts
- Service down
- Error rate >5%
- Payment failure rate >10%
- Memory usage >95%
- SLA violation

### Warning Alerts
- Response time P95 >500ms
- Queue depth >500
- CPU usage >90%
- Disk usage >90%
- Generation success rate <95%

## Incident Response

### Alert Tiers
1. **Critical**: Immediate response (<5 min)
2. **Warning**: Response within 30 minutes
3. **Info**: Response within 2 hours

### Runbooks
- [API Errors](https://runbooks.prodstack.local/api-errors)
- [High Latency](https://runbooks.prodstack.local/api-latency)
- [Service Down](https://runbooks.prodstack.local/service-down)
- [Generation Failures](https://runbooks.prodstack.local/generation-failures)
- [Payment Issues](https://runbooks.prodstack.local/payment-failures)
- [Infrastructure Issues](https://runbooks.prodstack.local/infrastructure)

## Testing

### Metrics Tests
```bash
# Run observability tests
pytest apps/backend/tests/test_observability_metrics.py -v

# Test synthetic monitoring
pytest apps/backend/tests/test_synthetic_monitoring.py -v

# Test Sentry integration
pytest apps/backend/tests/test_sentry_integration.py -v
```

### Manual Verification
```bash
# Check metrics endpoint
curl http://localhost:8000/metrics

# Check health endpoint
curl http://localhost:8000/health

# Check SLA status
curl http://localhost:8000/sla/status

# Verify Prometheus scraping
curl http://prometheus:9090/api/v1/targets
```

## Maintenance

### Metrics Retention
- Prometheus: 15 days default
- Grafana: 30 days default
- Alertmanager: 7 days default

### Backup Strategy
- Prometheus data: Daily snapshots
- Grafana dashboards: Version controlled
- Alertmanager config: Version controlled

### Scaling Considerations
- Prometheus: Remote storage for >1TB data
- Grafana: HA mode for critical dashboards
- Alertmanager: Cluster mode for high availability

## Troubleshooting

### Common Issues

#### Metrics Not Available
1. Check Prometheus targets: `curl http://prometheus:9090/api/v1/targets`
2. Verify backend metrics: `curl http://backend:8000/metrics`
3. Check network connectivity between services

#### Alerts Not Firing
1. Verify Alertmanager config: `curl http://alertmanager:9093/api/v1/status`
2. Check Prometheus rules: `curl http://prometheus:9090/api/v1/rules`
3. Verify notification channels

#### High Memory Usage
1. Check Prometheus memory: `curl http://prometheus:9090/api/v1/series?match[]=up`
2. Review retention settings
3. Consider remote storage

#### Dashboards Not Loading
1. Check Grafana datasource: Verify Prometheus URL
2. Check dashboard provisioning: `/var/lib/grafana/dashboards`
3. Verify user permissions

### Debug Commands
```bash
# Check service health
docker service ls
docker service ps prometheus

# View logs
docker service logs prometheus
docker service logs grafana

# Access service shell
docker exec -it $(docker ps -q -f name=prometheus) sh

# Test metrics manually
curl -s http://backend:8000/metrics | grep http_requests
```

## Future Enhancements

### Planned Improvements
- [ ] Distributed tracing with Jaeger
- [ ] Log aggregation with ELK stack
- [ ] Advanced anomaly detection
- [ ] Automated incident response
- [ ] Capacity planning analytics
- [ ] Cost optimization insights

### Integration Opportunities
- [ ] CI/CD pipeline monitoring
- [ ] Business intelligence integration
- [ ] Customer experience metrics
- [ ] Security event correlation