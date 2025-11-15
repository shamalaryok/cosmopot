# Observability Quick Start Guide

This guide helps you get the enhanced observability stack running quickly.

## Prerequisites

- Docker Swarm cluster
- Required secrets configured
- Access to production environment

## 1. Setup Secrets

Create required secrets for the observability stack:

```bash
# Sentry DSN
echo 'https://your-dsn@sentry.io/project-id' | docker secret create sentry_dsn -

# PagerDuty service key
echo 'your-pagerduty-service-key' | docker secret create pagerduty_service_key -

# Grafana password
echo 'your-secure-password' | docker secret create grafana_password -

# Alertmanager configuration
cat <<EOF | docker secret create alertmanager_config -
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@prodstack.local'
  smtp_auth_username: 'alerts@prodstack.local'
  smtp_auth_password: 'smtp_password'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'default'

receivers:
  - name: 'default'
    email_configs:
      - to: 'alerts@prodstack.local'
EOF
```

## 2. Deploy Observability Stack

```bash
cd deploy
./scripts/deploy-observability.sh deploy
```

This will deploy:
- Prometheus (metrics collection)
- Grafana (dashboards)
- Alertmanager (alert routing)
- Exporters (PostgreSQL, Redis, Node, Nginx)
- Sentry Relay (error tracking)

## 3. Verify Deployment

### Check Service Status
```bash
docker service ls | grep -E "(prometheus|grafana|alertmanager)"
```

### Access Dashboards

1. **Grafana**: http://localhost:3000
   - Username: `admin`
   - Password: Check `grafana_password` secret

2. **Prometheus**: http://localhost:9090
   - View targets: http://localhost:9090/targets
   - View rules: http://localhost:9090/rules

3. **Alertmanager**: http://localhost:9093
   - View alerts: http://localhost:9093/#/alerts
   - View status: http://localhost:9093/#/status

### Check Metrics
```bash
# Backend metrics
curl http://localhost:8000/metrics

# Health check
curl http://localhost:8000/health

# SLA status
curl http://localhost:8000/sla/status
```

## 4. Configure Alerting

### PagerDuty Integration
1. Update Alertmanager config with your PagerDuty service key
2. Configure escalation policies in PagerDuty
3. Test alert routing

### Email Notifications
1. Update SMTP settings in Alertmanager config
2. Configure email routing rules
3. Test email delivery

## 5. Verify Dashboards

### Import Dashboards
The following dashboards are automatically provisioned:
- API Performance Dashboard
- Business KPIs Dashboard  
- Infrastructure Monitoring Dashboard

### Custom Dashboards
1. Login to Grafana
2. Click "+" → "Dashboard"
3. Add panels using Prometheus queries
4. Save dashboard

## 6. Test Alerting

### Trigger Test Alerts
```bash
# High error rate alert
curl -s http://localhost:8000/nonexistent -w "%{http_code}" > /dev/null

# Check Alertmanager
curl http://localhost:9093/api/v1/alerts
```

### Verify Notifications
- Check PagerDuty for critical alerts
- Check email for warning alerts
- Verify alert content and formatting

## 7. Monitor SLA

### Check SLA Compliance
```bash
curl http://localhost:8000/sla/status | jq '.'
```

Expected response:
```json
{
  "status": "compliant",
  "availability_percent": 99.8,
  "avg_response_time_seconds": 0.45,
  "target_availability": 99.5,
  "target_response_time": 1.0,
  "sla_met": true
}
```

## 8. Troubleshooting

### Common Issues

#### Services Not Starting
```bash
# Check service logs
docker service logs prometheus
docker service logs grafana
docker service logs alertmanager

# Check service status
docker service ps prometheus
```

#### Metrics Not Available
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check backend metrics
curl http://localhost:8000/metrics

# Check network connectivity
docker network inspect prodstack_monitoring
```

#### Alerts Not Firing
```bash
# Check Alertmanager config
curl http://localhost:9093/api/v1/status

# Check Prometheus rules
curl http://localhost:9090/api/v1/rules

# Test rule evaluation
curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=up{job="backend"}==0'
```

#### Grafana Issues
```bash
# Check datasource configuration
curl -u admin:$(docker secret inspect grafana_password --format '{{.Secret.Payload}}' | base64 -d) \
  http://localhost:3000/api/datasources

# Restart Grafana
docker service update --force grafana
```

## 9. Maintenance

### Update Configuration
```bash
# Update Alertmanager config
echo 'new config' | docker secret create alertmanager_config -

# Update Prometheus rules
# Edit deploy/prometheus/rules/alerts.yml
docker stack deploy -c docker-compose.prod.yml prodstack
```

### Scale Services
```bash
# Scale Prometheus for high availability
docker service scale prometheus=2

# Scale Grafana
docker service scale grafana=2
```

### Backup Data
```bash
# Backup Prometheus data
docker exec $(docker ps -q -f name=prometheus) tar -czf - /prometheus | \
  ssh backup@storage "cat > /backup/prometheus-$(date +%Y%m%d).tar.gz"

# Backup Grafana data
docker exec $(docker ps -q -f name=grafana) tar -czf - /var/lib/grafana | \
  ssh backup@storage "cat > /backup/grafana-$(date +%Y%m%d).tar.gz"
```

## 10. Monitoring Best Practices

### Alert Configuration
- Set appropriate thresholds for your environment
- Use different severity levels appropriately
- Configure escalation policies
- Test alert routing regularly

### Dashboard Design
- Include key performance indicators
- Use consistent time ranges
- Add meaningful descriptions
- Organize panels logically

### Performance Optimization
- Monitor Prometheus memory usage
- Use appropriate retention periods
- Optimize metric cardinality
- Consider remote storage for scale

### Security
- Restrict access to monitoring endpoints
- Use authentication for dashboards
- Encrypt sensitive configuration
- Regularly update monitoring tools

## Next Steps

1. **Custom Dashboards**: Create dashboards for your specific use cases
2. **Advanced Alerting**: Set up more sophisticated alert rules
3. **Integration**: Connect with other monitoring tools
4. **Automation**: Automate incident response procedures
5. **Capacity Planning**: Use metrics for capacity planning

## Support

For issues with the observability stack:
1. Check the troubleshooting section
2. Review service logs
3. Consult the documentation
4. Contact the infrastructure team

## Documentation

- [Full Observability Documentation](OBSERVABILITY_STACK.md)
- [Deployment Runbook](../deploy/DEPLOYMENT_RUNBOOK.md)
- [Troubleshooting Guide](../deploy/TROUBLESHOOTING_GUIDE.md)
- [Alerting Rules](../deploy/prometheus/rules/alerts.yml)