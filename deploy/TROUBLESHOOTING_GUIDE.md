# Troubleshooting Guide

Quick reference for common issues and solutions.

## Service Issues

### Services Won't Start

**Symptoms:**
- Services showing as `New` or `Preparing` for > 2 minutes
- Services constantly restarting

**Diagnosis:**

```bash
# Check service logs
docker service logs prodstack_backend

# Inspect service definition
docker service inspect prodstack_backend | jq '.Spec'

# Check node resources
docker node inspect <node> | jq '.Description.Resources'

# Check if image exists
docker image ls | grep backend
```

**Solutions:**

| Issue | Fix |
|-------|-----|
| Image not found | `docker pull $REGISTRY/backend:$VERSION` |
| Out of memory | `docker service update --limit-memory 1g prodstack_backend` |
| No available nodes | Check node labels: `docker node inspect <node>` |
| Port already in use | Scale down conflicting service |
| Config/Secret missing | `./scripts/deploy.sh init-configs` |

---

## Database Issues

### PostgreSQL Connection Errors

**Symptoms:**
```
FATAL: too many connections
ERROR: the database system is shutting down
```

**Diagnosis:**

```bash
# Check connection count
docker exec postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check max connections setting
docker exec postgres psql -U postgres -c "SHOW max_connections;"

# List active connections
docker exec postgres psql -U postgres -c "SELECT datname, usename, state FROM pg_stat_activity;"
```

**Solutions:**

```bash
# Increase connection limit
docker exec postgres psql -U postgres <<EOF
ALTER SYSTEM SET max_connections = 250;
SELECT pg_reload_conf();
EOF

# Kill idle connections
docker exec postgres psql -U postgres <<EOF
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'prodstack' AND state = 'idle';
EOF

# Increase backend connection pool
# Edit .env.prod: DATABASE_POOL_SIZE=30
# Restart backend: docker service update --force prodstack_backend
```

### PostgreSQL Slow Queries

**Diagnosis:**

```bash
# Enable slow query logging
docker exec postgres psql -U postgres <<EOF
ALTER SYSTEM SET log_min_duration_statement = 1000;
SELECT pg_reload_conf();
EOF

# View slow queries
docker service logs postgres | grep 'duration:'

# Top slowest queries
docker exec postgres psql -U postgres -d prodstack <<EOF
SELECT query, mean_time, calls FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;
EOF
```

**Solutions:**

```bash
# Add indexes for slow queries
docker exec postgres psql -U postgres -d prodstack <<EOF
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_tasks_status ON tasks(status);
EOF

# Analyze query plan
docker exec postgres psql -U postgres -d prodstack <<EOF
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'test@example.com';
EOF

# Update statistics
docker exec postgres psql -U postgres -d prodstack -c "ANALYZE;"
```

### Database Disk Space Full

**Diagnosis:**

```bash
# Check volume usage
docker exec postgres df /var/lib/postgresql/data

# Check database size
docker exec postgres psql -U postgres <<EOF
SELECT datname, pg_size_pretty(pg_database_size(datname)) 
FROM pg_database;
EOF

# Check table sizes
docker exec postgres psql -U postgres -d prodstack <<EOF
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
EOF
```

**Solutions:**

```bash
# Clean up old WAL files
docker exec postgres psql -U postgres <<EOF
SELECT pg_wal_lsn_diff(CASE WHEN pg_is_wal_replay_in_progress() 
  THEN pg_last_wal_receive_lsn() ELSE pg_current_wal_lsn() END, '0/0') 
AS wal_size_bytes;
EOF

# Vacuum and analyze
docker exec postgres psql -U postgres -d prodstack -c "VACUUM ANALYZE;"

# Remove old backups
rm -rf /backups/backup_* # Keep only recent ones

# Expand volume (NFS-based)
# Increase NFS mount size and remount
```

---

## Cache (Redis) Issues

### Redis Memory Full

**Symptoms:**
```
OOM command not allowed when used memory > 'maxmemory'
```

**Diagnosis:**

```bash
# Check memory usage
docker exec redis redis-cli INFO memory

# Check eviction policy
docker exec redis redis-cli CONFIG GET maxmemory-policy

# List largest keys
docker exec redis redis-cli --bigkeys
```

**Solutions:**

```bash
# Clear expired keys
docker exec redis redis-cli EVICT

# Change eviction policy (allow LRU cleanup)
docker exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Increase Redis memory limit
docker service update --limit-memory 1g prodstack_redis

# Clear specific key patterns
docker exec redis redis-cli KEYS "session:*" | xargs redis-cli DEL
```

### Redis Persistence Issues

**Symptoms:**
- Data lost after restart
- Slow disk I/O

**Diagnosis:**

```bash
# Check AOF status
docker exec redis redis-cli CONFIG GET appendonly

# Check dump.rdb status
docker exec redis ls -lah /data/dump.rdb

# Check disk I/O
docker exec redis redis-cli --latency
```

**Solutions:**

```bash
# Force save
docker exec redis redis-cli SAVE

# Enable AOF (append-only file)
docker exec redis redis-cli CONFIG SET appendonly yes

# Restart to apply
docker service update --force prodstack_redis

# Check persistence
docker exec redis redis-cli LASTSAVE
```

---

## Message Queue (RabbitMQ) Issues

### RabbitMQ Queue Backing Up

**Symptoms:**
- Messages not processing
- Queue length growing
- Worker services scaling to max

**Diagnosis:**

```bash
# Check queue status
docker exec rabbitmq rabbitmq-diagnostics -q queues

# Check consumer status
docker exec rabbitmq rabbitmq-diagnostics -q consumers

# Check memory
docker exec rabbitmq rabbitmq-diagnostics -q memory_breakdown

# Check connections
docker exec rabbitmq rabbitmq-diagnostics -q connections
```

**Solutions:**

```bash
# Increase worker replicas
./scripts/deploy.sh scale worker 40

# Purge stuck queue
docker exec rabbitmq rabbitmqctl purge_queue celery

# Check worker logs for errors
./scripts/deploy.sh logs worker

# Restart RabbitMQ
docker service update --force prodstack_rabbitmq

# Monitor queue processing
watch -n 2 'docker exec rabbitmq rabbitmq-diagnostics -q queues | head -5'
```

### RabbitMQ Out of Memory

**Diagnosis:**

```bash
docker exec rabbitmq rabbitmq-diagnostics memory_breakdown
```

**Solutions:**

```bash
# Increase limit
docker service update --limit-memory 1g prodstack_rabbitmq

# Clear old messages (WARNING: data loss)
docker exec rabbitmq rabbitmqctl purge_queue celery

# Check for memory leaks
docker service logs rabbitmq | grep -i "memory\|leak"
```

---

## Nginx/Reverse Proxy Issues

### High Error Rate (502/503)

**Symptoms:**
- 502 Bad Gateway errors
- 503 Service Unavailable
- Requests timing out

**Diagnosis:**

```bash
# Check access logs
docker service logs nginx | tail -20

# Check backend connectivity
docker exec nginx curl http://backend:8000/health

# Check backend replicas
docker service ls | grep backend

# Check resource usage
docker stats prodstack_nginx
```

**Solutions:**

```bash
# Increase backend replicas
./scripts/deploy.sh scale backend 15

# Increase Nginx worker connections
# Edit nginx.prod.conf: worker_connections 8192
docker config rm nginx_conf
docker config create nginx_conf deploy/nginx/nginx.prod.conf
docker service update --force prodstack_nginx

# Increase timeouts
# Edit nginx.prod.conf: proxy_connect_timeout 60s
# Restart nginx

# Check if backend is down
./scripts/deploy.sh health-check
```

### SSL Certificate Issues

**Symptoms:**
```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Diagnosis:**

```bash
# Check cert validity
openssl x509 -in deploy/nginx/certs/tls.crt -text -noout | grep -A 2 "Validity"

# Check cert on server
echo | openssl s_client -servername prod-cluster -connect prod-cluster:443
```

**Solutions:**

```bash
# Renew certificate
certbot renew --dry-run

# Copy new cert
cp /etc/letsencrypt/live/prod-cluster/fullchain.pem deploy/nginx/certs/tls.crt
cp /etc/letsencrypt/live/prod-cluster/privkey.pem deploy/nginx/certs/tls.key

# Update config
docker config rm nginx_conf
docker config create nginx_conf deploy/nginx/nginx.prod.conf

# Restart nginx
docker service update --force prodstack_nginx
```

---

## Network Issues

### Service Cannot Connect to Another Service

**Diagnosis:**

```bash
# Test connectivity
docker exec <container> ping <other-service>

# Check DNS resolution
docker exec <container> nslookup <other-service>

# Check network
docker network inspect prodstack_core

# Check firewall
docker exec <container> curl <other-service>:8000
```

**Solutions:**

```bash
# If service not resolving:
# 1. Check service exists: docker service ls
# 2. Check service has IP: docker service inspect <service>
# 3. Check network: docker network ls

# If firewall issue:
# Check ports: docker service inspect <service> | jq '.Endpoint.Ports'
# Allow port: ufw allow <port>/tcp

# Restart service
docker service update --force prodstack_<service>
```

### Network Overlay Issues

**Symptoms:**
- Intermittent connectivity
- High latency

**Diagnosis:**

```bash
# Check network status
docker network inspect prodstack_core | jq '.Containers'

# Monitor network
iftop -i docker0

# Check routing
docker exec <container> ip route
```

**Solutions:**

```bash
# Restart network (WARNING: service disruption)
docker network disconnect prodstack_core <container>
docker network connect prodstack_core <container>

# For persistent issues, recreate network:
docker network rm prodstack_core
docker service update --force prodstack_<service>  # Will recreate
```

---

## Monitoring Issues

### Prometheus Not Scraping Metrics

**Diagnosis:**

```bash
# Check Prometheus logs
docker service logs prometheus

# Check targets
curl http://prometheus:9090/api/v1/targets

# Check config
docker config inspect prometheus_conf
```

**Solutions:**

```bash
# Update prometheus config
docker config rm prometheus_conf
docker config create prometheus_conf deploy/prometheus/prometheus.prod.yml

# Restart Prometheus
docker service update --force prodstack_prometheus

# Verify targets
curl 'http://prometheus:9090/api/v1/targets' | jq '.data.activeTargets'
```

### Grafana Not Showing Data

**Diagnosis:**

```bash
# Check datasources
curl http://grafana:3000/api/datasources

# Check Grafana logs
docker service logs grafana | tail -20

# Verify Prometheus connectivity from Grafana container
docker exec <grafana> curl http://prometheus:9090/-/healthy
```

**Solutions:**

```bash
# Update datasource config
docker config rm grafana_datasources
docker config create grafana_datasources deploy/grafana/datasources.yml

# Restart Grafana
docker service update --force prodstack_grafana

# Login and verify: https://prod-cluster/grafana
```

---

## Deployment Issues

### Deployment Hanging/Stuck

**Symptoms:**
- Service update not progressing
- Stuck in "Preparing" state

**Diagnosis:**

```bash
# Check service tasks
docker service ps prodstack_backend

# Check logs
docker service logs prodstack_backend

# Check resource constraints
docker node inspect <node> | jq '.Description.Resources'
```

**Solutions:**

```bash
# Force service restart
docker service update --force prodstack_backend

# Check if node is healthy
docker node ls
docker node inspect <node-id> | grep -i state

# If node unhealthy, drain and repair
docker node update --availability drain <node-id>
# Fix issue
docker node update --availability active <node-id>
```

### Insufficient Disk Space for Deployment

**Diagnosis:**

```bash
# Check disk usage on all nodes
docker node ls -q | xargs -I {} sh -c 'echo "Node: {}"; docker node inspect {} | jq ".Status.State"'

# Check Docker system usage
docker system df
```

**Solutions:**

```bash
# Clean up Docker
docker system prune -a

# Remove old images
docker image rm $(docker image ls | grep '<none>')

# Increase disk allocation on volume
# Stop Docker, extend volume, restart

# Monitor disk usage
df -h /var/lib/docker
```

---

## Performance Issues

### High CPU Usage

**Diagnosis:**

```bash
# Identify service
docker stats --no-stream | head -10

# Check process CPU
docker exec <container> top -bn1 | head -15
```

**Solutions:**

```bash
# Scale service
./scripts/deploy.sh scale backend 10

# Check for inefficient queries
./scripts/deploy.sh logs backend | grep -i "slow\|timeout"

# Increase resource limit
docker service update --limit-cpus 2 prodstack_backend

# Profile with pprof (if available)
curl http://backend:8000/debug/pprof/profile?seconds=30 > profile.prof
```

### High Memory Usage

**Diagnosis:**

```bash
docker exec <container> free -h
docker exec <container> top -bn1 | grep -i mem
```

**Solutions:**

```bash
# Check for leaks
./scripts/deploy.sh logs backend | grep -i "memory\|leak"

# Increase memory limit
docker service update --limit-memory 1g prodstack_backend

# Restart service
docker service update --force prodstack_backend

# Monitor with gc logs
# (language/runtime specific)
```

---

## Quick Reference

### Essential Commands

```bash
# Status
docker stack ps prodstack
docker service ls
docker node ls

# Logs
docker service logs prodstack_backend
docker service logs prodstack_worker

# Scale
docker service scale prodstack_backend=10
docker service scale prodstack_worker=30

# Update
docker service update --image $REGISTRY/backend:v2 prodstack_backend

# Inspect
docker service inspect prodstack_backend
docker node inspect <node-id>

# Health
./scripts/deploy.sh health-check

# Backup/Restore
./scripts/backup.sh
./scripts/restore.sh backup_20240101_120000
```

### Log Levels

```bash
# All logs
docker service logs prodstack_backend

# Follow logs
docker service logs -f prodstack_backend

# Recent logs
docker service logs --tail 50 prodstack_backend

# Grep for errors
docker service logs prodstack_backend | grep -i error
```

### Common Fixes (In Order)

1. Check logs: `docker service logs <service>`
2. Check status: `./scripts/deploy.sh status`
3. Health check: `./scripts/deploy.sh health-check`
4. Restart service: `docker service update --force <service>`
5. Scale up: `./scripts/deploy.sh scale <service> +1`
6. Rollback: `./scripts/deploy.sh rollback`
7. Restore: `./scripts/restore.sh backup_<date>`

---

## Getting Help

If issues persist:

1. **Gather information:**
   ```bash
   docker stack ps prodstack > debug_stack.txt
   docker stats --no-stream > debug_resources.txt
   docker service logs prodstack_backend > debug_logs.txt
   ```

2. **Check documentation:**
   - [DEPLOYMENT_RUNBOOK.md](./DEPLOYMENT_RUNBOOK.md)
   - [AUTOSCALING_STRATEGY.md](./AUTOSCALING_STRATEGY.md)
   - [BACKUP_RESTORE_PROCEDURES.md](./BACKUP_RESTORE_PROCEDURES.md)

3. **Contact support with:**
   - Specific error message
   - Steps to reproduce
   - Debug files from above

---

## Related Documentation

- [Deployment Runbook](./DEPLOYMENT_RUNBOOK.md)
- [Monitoring Guide](./MONITORING_GUIDE.md)
- [Performance Baselines](../docs/PERFORMANCE_BASELINES.md)
