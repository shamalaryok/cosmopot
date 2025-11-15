# Zero-Downtime Deployment Guide

This guide describes how to deploy updates to production without interrupting service.

## Overview

Zero-downtime deployments in Docker Swarm are achieved through:

1. **Rolling Updates** - Services update replicas one at a time
2. **Health Checks** - Services only receive traffic when healthy
3. **Graceful Shutdown** - Services have time to finish in-flight requests
4. **Load Balancing** - Nginx distributes traffic away from restarting services

---

## Pre-Deployment Checklist

- [ ] Code changes tested in staging environment
- [ ] Database migrations backwards-compatible
- [ ] All new dependencies documented and installed
- [ ] Rollback plan documented
- [ ] Team notified of deployment window
- [ ] Monitoring dashboards active
- [ ] Backup created: `./deploy/scripts/backup.sh`
- [ ] Current metrics baseline recorded

---

## Deployment Strategies

### 1. Blue-Green Deployment

Maintain two identical environments and switch traffic between them.

**Setup:**

```bash
# Create two named stacks
STACK_VERSION=blue ./deploy/scripts/deploy.sh deploy
STACK_VERSION=green ./deploy/scripts/deploy.sh deploy
```

**Switch Traffic:**

```bash
# Update Nginx to route to green
# Edit nginx.prod.conf, update upstream backend target
docker config rm nginx_conf
docker config create nginx_conf deploy/nginx/nginx.prod.conf
docker service update --force prodstack_nginx

# If issues, switch back to blue (seconds)
```

**Pros:** Instant rollback, full parallel testing  
**Cons:** Requires 2x resources

---

### 2. Canary Deployment

Gradually roll out to a subset of replicas first.

**Process:**

```bash
# 1. Start with 1 replica of new version (canary)
VERSION=v2.0.0 docker service update \
  --image $REGISTRY/backend:v2.0.0 \
  --replicas 1 \
  --update-parallelism 1 \
  --update-delay 30s \
  prodstack_backend

# 2. Monitor metrics for this replica
./deploy/scripts/deploy.sh logs backend | grep v2.0.0

# 3. If healthy, increase replicas
./deploy/scripts/deploy.sh scale backend 10

# 4. Complete rollout
VERSION=v2.0.0 ./deploy/scripts/deploy.sh deploy
```

**Pros:** Risk-limited, catches issues early  
**Cons:** Slower deployment

---

### 3. Rolling Deployment (Recommended)

Gradually replace old replicas with new ones, one at a time.

**Configuration (in docker-compose.prod.yml):**

```yaml
services:
  backend:
    deploy:
      update_config:
        parallelism: 1           # Update 1 replica at a time
        delay: 30s               # Wait 30s between replicas
        failure_action: rollback # Rollback on failure
        order: start-first       # Start new before stopping old
```

**Deployment:**

```bash
# Update image
VERSION=v2.0.0 docker service update \
  --image $REGISTRY/backend:v2.0.0 \
  prodstack_backend

# Monitor progress
watch 'docker service ps prodstack_backend'

# Show status
./deploy/scripts/deploy.sh status
```

**Pros:** Simple, requires no extra resources, automated  
**Cons:** Longer deployment time

---

## Database Migrations

### Strategy 1: Expand-Contract Pattern (Recommended)

For backwards-incompatible schema changes:

**Phase 1: Expand (Prepare)**
```sql
-- Add new column/table, keep old one
ALTER TABLE users ADD COLUMN user_id_new UUID;
CREATE INDEX idx_users_user_id_new ON users(user_id_new);
```

**Phase 2: Contract (Migrate)**
```sql
-- Copy data
UPDATE users SET user_id_new = user_id;

-- New code writes to both columns
-- Old code still works with old column
```

**Phase 3: Cleanup**
```sql
-- Drop old column once all replicas running new code
ALTER TABLE users DROP COLUMN user_id;
RENAME COLUMN user_id_new TO user_id;
```

### Safe Migration Process

```bash
# 1. Create backup before migrations
./deploy/scripts/backup.sh

# 2. Apply "expand" migration
docker exec postgres psql -U postgres prodstack < migrations/expand.sql

# 3. Deploy new code
./deploy/scripts/deploy.sh deploy

# 4. Monitor for errors
./deploy/scripts/deploy.sh logs backend | grep -i error

# 5. Once stable, apply "contract" migration
docker exec postgres psql -U postgres prodstack < migrations/contract.sql
```

---

## Deployment Steps (Production)

### 1. Pre-Deployment

```bash
# Create backup
echo "Creating backup..."
./deploy/scripts/backup.sh

# Verify backup
ls -lah /backups/backup_*/

# Record current metrics
echo "Recording baseline metrics..."
curl -s http://prometheus:9090/api/v1/query?query='up' | jq .

# Notify team
echo "Deployment starting in 5 minutes..."
```

### 2. Prepare New Version

```bash
# Build and push images
echo "Building images..."
docker build -f backend/Dockerfile -t $REGISTRY/backend:v2.0.0 .
docker build -f worker/Dockerfile -t $REGISTRY/worker:v2.0.0 .
docker build -f frontend/Dockerfile -t $REGISTRY/frontend:v2.0.0 .

echo "Pushing images..."
docker push $REGISTRY/backend:v2.0.0
docker push $REGISTRY/worker:v2.0.0
docker push $REGISTRY/frontend:v2.0.0
```

### 3. Database Migrations

```bash
# Only if needed
if [[ -f migrations/migrate.sql ]]; then
  echo "Running migrations..."
  docker exec <postgres-container> psql -U postgres prodstack < migrations/migrate.sql
fi
```

### 4. Start Rolling Update

```bash
# Deploy new version
export VERSION=v2.0.0
./deploy/scripts/deploy.sh deploy

# Monitor progress
watch -n 2 './deploy/scripts/deploy.sh status'

# Should show progression like:
# backend.1  RUNNING  (old)
# backend.2  RUNNING  (new)
# backend.3  RUNNING  (new)
# ...
```

### 5. Monitor During Deployment

```bash
# In one terminal, watch deployment progress
watch 'docker stack ps prodstack'

# In another, monitor errors
./deploy/scripts/deploy.sh logs backend | tail -f

# In another, check metrics
# Open Grafana: https://prod-cluster/grafana
```

### 6. Verify Successful Deployment

```bash
# Check all services running
./deploy/scripts/deploy.sh status

# Run health checks
./deploy/scripts/deploy.sh health-check

# Test API endpoints
curl https://prod-cluster/api/v1/health

# Monitor error rate (should be 0%)
curl -s http://prometheus:9090/api/v1/query?query='rate(http_requests_total{status=~"5.."}[5m])'

# Check response times (should be normal)
curl -s http://prometheus:9090/api/v1/query?query='histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))'
```

---

## Rollback Procedures

### Quick Rollback (Within 5 minutes)

If critical issue detected during deployment:

```bash
# Immediate - revert to previous image
docker service update \
  --image $REGISTRY/backend:v1.9.0 \
  prodstack_backend

# Monitor recovery
watch 'docker service ps prodstack_backend'

# Verify
./deploy/scripts/deploy.sh health-check
```

### Full Rollback (Using Backup)

If severe issues persist:

```bash
# 1. Stop current stack
docker stack rm prodstack

# 2. Restore from backup
./deploy/scripts/restore.sh backup_20240101_120000

# 3. Redeploy previous version
export VERSION=v1.9.0
./deploy/scripts/deploy.sh deploy

# 4. Verify
./deploy/scripts/deploy.sh health-check
```

---

## Monitoring Deployment Health

### Key Metrics to Watch

**Before Deployment:**
```bash
# Record baseline
curl 'http://prometheus:9090/api/v1/query' \
  --data-urlencode 'query=rate(http_requests_total[5m])' | jq '.data.result'

curl 'http://prometheus:9090/api/v1/query' \
  --data-urlencode 'query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))' | jq '.data.result'
```

**During Deployment:**
```bash
# Error rate (should stay < 0.1%)
rate(http_requests_total{status=~"5.."}[5m])

# Response time p95 (should be normal)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Database connections (should be stable)
pg_stat_activity

# Task queue length (should be normal)
celery_queue_length
```

**After Deployment:**
```bash
# Should match or improve baseline
# Allow 5-10 minutes for stabilization
```

---

## Common Deployment Issues

### Issue: Replicas Keep Restarting

**Symptoms:** Services repeatedly crash and restart during update

**Troubleshooting:**
```bash
# Check logs
docker service logs prodstack_backend | tail -20

# Check resource limits
docker service inspect prodstack_backend | grep -A 20 'Resources'

# Potential causes:
# - Out of memory: increase limit
# - Crashing on startup: check logs
# - Configuration missing: verify secrets/configs

# Resolution:
docker service update --limit-memory 1g prodstack_backend
```

### Issue: High Error Rate During Deployment

**Symptoms:** Spike in 5xx errors during rolling update

**Cause:** Old code trying to use new database schema

**Prevention:**
- Use expand-contract pattern for schema changes
- Ensure old code still works with new schema
- Test canary with old clients

**Resolution:**
```bash
# Quick rollback
docker service update --image $REGISTRY/backend:v1.9.0 prodstack_backend

# Or migrate database back
docker exec postgres psql -U postgres prodstack < migrations/rollback.sql
```

### Issue: Slow Deployment / Timeouts

**Symptoms:** Update takes very long or times out

**Cause:**
- Health check too strict
- Startup takes too long
- Network issues

**Resolution:**
```bash
# Increase timeouts in docker-compose.prod.yml
deploy:
  update_config:
    delay: 60s  # Increase from 30s

# Increase health check start_period
healthcheck:
  start_period: 60s  # Increase from 30s
```

---

## Post-Deployment Steps

1. **Document Deployment:**
   ```bash
   echo "Deployment completed: $(date)" >> DEPLOYMENT_LOG.md
   echo "Version: v2.0.0" >> DEPLOYMENT_LOG.md
   echo "Deployment time: 15 minutes" >> DEPLOYMENT_LOG.md
   ```

2. **Notify Team:**
   - Message Slack/Teams
   - Update status page
   - Send deployment report

3. **Continue Monitoring:**
   - Monitor for 24 hours
   - Set up alerts for regressions
   - Gather performance metrics

4. **Review Deployment:**
   - Successful? Update runbook
   - Issues encountered? Document solutions
   - Improvements needed? Create tickets

---

## Deployment Checklist

### Before Deployment
- [ ] Code reviewed and approved
- [ ] Tests passing (unit, integration, smoke)
- [ ] Staging tested successfully
- [ ] Backup created and verified
- [ ] Release notes prepared
- [ ] Team notified
- [ ] Monitoring dashboards open
- [ ] Rollback plan documented

### During Deployment
- [ ] Image built and pushed
- [ ] Health checks passing
- [ ] Monitoring shows normal metrics
- [ ] No spike in errors
- [ ] Response times normal
- [ ] Database responsive
- [ ] Queue lengths normal

### After Deployment
- [ ] All services running
- [ ] Health checks passing
- [ ] No errors in logs
- [ ] Metrics stable
- [ ] Functionality verified
- [ ] Team notified completion
- [ ] Post-deployment checks passed
- [ ] Deployment logged

---

## Automation

For CI/CD integration:

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build images
        run: |
          docker build -f backend/Dockerfile -t $REGISTRY/backend:$VERSION .
          docker push $REGISTRY/backend:$VERSION
      
      - name: Deploy to Swarm
        env:
          REGISTRY: ${{ secrets.REGISTRY }}
          VERSION: ${{ github.sha }}
        run: |
          VERSION=$VERSION ./deploy/scripts/deploy.sh deploy
      
      - name: Health check
        run: ./deploy/scripts/deploy.sh health-check
      
      - name: Notify
        if: failure()
        run: echo "Deployment failed" | mail -s "Deploy Alert" ops@company.com
```

---

## Related Documentation

- [Deployment Runbook](./DEPLOYMENT_RUNBOOK.md)
- [Autoscaling Strategy](./AUTOSCALING_STRATEGY.md)
- [Monitoring Guide](./MONITORING_GUIDE.md)
