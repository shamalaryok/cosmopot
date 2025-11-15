# Production Deployment Runbook

This document provides operational procedures for deploying and managing the prodstack on Docker Swarm.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Cluster Setup](#initial-cluster-setup)
3. [Deployment](#deployment)
4. [Scaling](#scaling)
5. [Monitoring](#monitoring)
6. [Backup & Recovery](#backup--recovery)
7. [Troubleshooting](#troubleshooting)
8. [Disaster Recovery](#disaster-recovery)

---

## Prerequisites

### Hardware Requirements

- **Manager Nodes**: Minimum 2, recommended 3+
  - CPU: 4 cores per node
  - Memory: 8GB per node
  - Storage: 50GB per node (system + Swarm metadata)

- **Worker Nodes**: Minimum 3
  - CPU: 8+ cores per node
  - Memory: 16GB+ per node
  - Storage: 100GB+ per node (application data)

- **Dedicated Storage**: NFS or similar for persistent volumes
  - 500GB+ for databases
  - 1TB+ for object storage (MinIO)

### Software Requirements

```bash
# Docker Engine 20.10+
docker --version

# Docker CLI with Swarm support
docker swarm init --advertise-addr <manager-ip>

# Required utilities
curl, wget, openssl, tar, gzip
aws-cli (for S3 backups, optional)
```

### Network Requirements

- Swarm communication ports: 2377 (TCP), 7946 (TCP/UDP), 4789 (UDP)
- Application ports: 80 (HTTP), 443 (HTTPS)
- Monitoring ports: 9090 (Prometheus), 3000 (Grafana)
- Internal overlay networks: 10.10.0.0/24, 10.11.0.0/24

---

## Initial Cluster Setup

### 1. Initialize Docker Swarm Manager

On the primary manager node:

```bash
# Initialize Swarm
docker swarm init --advertise-addr <manager-node-ip>

# Get manager token for adding additional managers
docker swarm join-token manager

# Get worker token for adding worker nodes
docker swarm join-token worker
```

### 2. Add Manager Nodes (Optional)

On additional manager nodes:

```bash
# Join as manager (use token from step above)
docker swarm join --token <manager-token> <manager-ip>:2377

# Verify
docker node ls
```

### 3. Add Worker Nodes

On each worker node:

```bash
# Join as worker
docker swarm join --token <worker-token> <manager-ip>:2377

# Verify from manager
docker node ls
```

### 4. Label Nodes for Workload Placement

```bash
# Label nodes for backend services
docker node update --label-add workload=backend <node-id>

# Label nodes for worker services
docker node update --label-add workload=worker <node-id>

# Label nodes for frontend
docker node update --label-add workload=frontend <node-id>

# Verify labels
docker node inspect <node-id> | grep -A 5 Labels
```

### 5. Configure NFS Storage

On NFS server:

```bash
# Create export directories
mkdir -p /exports/{postgres,redis,rabbitmq,minio,prometheus,grafana}
chmod 777 /exports/*

# Add to /etc/exports
/exports *(rw,sync,no_subtree_check,no_all_squash)

# Export
exportfs -a
```

On Swarm nodes:

```bash
# Install NFS client
apt-get install nfs-common

# Mount test
mount -t nfs <nfs-server>:/exports /mnt/test
umount /mnt/test
```

---

## Deployment

### 1. Prepare Environment

```bash
# Clone configuration
cd /path/to/prodstack
git clone <repo>

# Configure environment
cp deploy/.env.prod.template deploy/.env.prod
# Edit deploy/.env.prod with actual values
```

### 2. Make Scripts Executable

```bash
chmod +x deploy/scripts/*.sh
```

### 3. Initialize Secrets and Configs

```bash
# Generate and create secrets
./deploy/scripts/deploy.sh init-secrets

# Create configs from files
./deploy/scripts/deploy.sh init-configs

# Verify
docker secret ls
docker config ls
```

### 4. Build and Push Images

```bash
# Build images
docker build -f backend/Dockerfile -t $REGISTRY/backend:$VERSION .
docker build -f worker/Dockerfile -t $REGISTRY/worker:$VERSION .
docker build -f frontend/Dockerfile -t $REGISTRY/frontend:$VERSION .

# Push to registry
docker push $REGISTRY/backend:$VERSION
docker push $REGISTRY/worker:$VERSION
docker push $REGISTRY/frontend:$VERSION
```

### 5. Deploy Stack

```bash
# Deploy
./deploy/scripts/deploy.sh deploy

# Monitor deployment
watch 'docker stack ps prodstack'

# Wait for all services to reach Running state (usually 2-5 minutes)
```

### 6. Verify Deployment

```bash
# Check stack status
./deploy/scripts/deploy.sh status

# Perform health checks
./deploy/scripts/deploy.sh health-check

# Check logs
./deploy/scripts/deploy.sh logs backend
./deploy/scripts/deploy.sh logs worker
```

---

## Scaling

### Manual Scaling

```bash
# Scale backend to 10 replicas
./deploy/scripts/deploy.sh scale backend 10

# Scale worker to 30 replicas
./deploy/scripts/deploy.sh scale worker 30

# Scale frontend to 5 replicas
./deploy/scripts/deploy.sh scale frontend 5

# Verify scaling
docker stack services prodstack
```

### Autoscaling

For automatic scaling based on metrics:

```bash
# Start autoscaler (runs continuously)
nohup ./deploy/scripts/autoscale.sh > logs/autoscale.log 2>&1 &

# Configure thresholds via environment variables
export BACKEND_MIN=5 BACKEND_MAX=20 BACKEND_CPU_THRESHOLD=70
export WORKER_MIN=10 WORKER_MAX=50 WORKER_CPU_THRESHOLD=65

# Monitor autoscaler
tail -f logs/autoscale.log
```

### Scaling Policies

**Backend (API Server)**
- Minimum: 5 replicas
- Maximum: 20 replicas
- CPU threshold: 70%
- Memory threshold: 75%
- Scale-up increment: 1 replica

**Worker (Celery)**
- Minimum: 10 replicas
- Maximum: 50 replicas
- CPU threshold: 65%
- Memory threshold: 70%
- Queue threshold: 1000 pending tasks
- Scale-up increment: 1-3 replicas (varies by queue size)

**Frontend**
- Minimum: 3 replicas
- Maximum: 10 replicas
- CPU threshold: 50%
- Memory threshold: 60%

---

## Monitoring

### Access Monitoring Dashboards

```bash
# Prometheus (raw metrics)
http://prod-cluster:9090

# Grafana (visualized dashboards)
https://prod-cluster/grafana
  - Username: admin
  - Password: (from .env.prod)

# Application logs
./deploy/scripts/deploy.sh logs <service>

# Docker metrics
docker stats prodstack_backend
```

### Key Metrics to Monitor

**Backend**
- Request latency (p50, p95, p99)
- Error rate (4xx, 5xx)
- Database connection pool usage
- Memory usage growth

**Worker**
- Task processing time
- Queue length
- Task failure rate
- Concurrency usage

**Database**
- Connection count
- Query time
- Transaction time
- Replication lag

**Infrastructure**
- CPU usage per node
- Memory usage per node
- Network I/O
- Disk I/O and usage

### Setting Up Alerts

Create alert rules in Prometheus (`prometheus/rules/alerts.yml`):

```yaml
groups:
  - name: backend
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"
```

---

## Backup & Recovery

### Regular Backups

```bash
# Manual backup
./deploy/scripts/backup.sh

# Scheduled backups (add to crontab)
0 2 * * * cd /path/to/prodstack && ./deploy/scripts/backup.sh

# Backup with encryption
ENCRYPT_BACKUP=true ENCRYPTION_KEY="$(cat /secure/key)" ./deploy/scripts/backup.sh

# Backup to S3
S3_BACKUP_PATH=s3://backups/prodstack ./deploy/scripts/backup.sh
```

### Backup Contents

- PostgreSQL full dump
- Redis RDB file
- All volume data (postgres, redis, rabbitmq, minio)
- Configuration and secrets metadata
- Stack compose file reference

### Recovery Procedures

```bash
# List available backups
ls -la /backups/backup_*

# Restore from backup
./deploy/scripts/restore.sh backup_20240101_120000

# Restore specific components
./deploy/scripts/restore.sh backup_20240101_120000 --skip-redis --skip-volumes

# Verify restoration
./deploy/scripts/deploy.sh health-check
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check service logs
docker service logs prodstack_backend

# Inspect service definition
docker service inspect prodstack_backend

# Check resource constraints
docker stats prodstack_backend

# Verify dependencies are healthy
docker service ls prodstack_*
```

### High Memory Usage

```bash
# Check container memory
docker stats prodstack_backend --no-stream

# Check for leaks in logs
docker service logs prodstack_backend | grep -i memory

# Restart service with higher limit
docker service update --limit-memory 1g prodstack_backend

# Scale to distribute load
./deploy/scripts/deploy.sh scale backend 15
```

### Database Connection Pool Exhausted

```bash
# Check current connections
docker exec <postgres-container> psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Adjust pool size
# Edit docker-compose.prod.yml: DATABASE_POOL_SIZE=30
./deploy/scripts/deploy.sh deploy
```

### Redis Persistence Issues

```bash
# Check Redis logs
docker service logs prodstack_redis

# Force save
docker exec <redis-container> redis-cli SAVE

# Restart Redis
docker service update --force prodstack_redis
```

### Network Connectivity Issues

```bash
# Test overlay network
docker exec <container> ping <other-service>

# Check DNS resolution
docker exec <container> nslookup backend

# Inspect network
docker network inspect prodstack_core
```

---

## Disaster Recovery

### Cluster Member Failure

**If a worker node fails:**

```bash
# Mark node as down (optional, automatic after ~10m)
docker node rm <failed-node-id>

# Services automatically reschedule to healthy nodes
docker stack ps prodstack

# Replace node when online
docker swarm join --token <worker-token> <manager-ip>:2377
```

**If a manager node fails:**

```bash
# Verify remaining managers are still quorum
docker node ls

# If below quorum, add new manager or use backup
docker swarm join --token <manager-token> <manager-ip>:2377
```

### Complete Stack Recovery

```bash
# 1. Backup existing configs/secrets (if possible)
docker secret ls > /tmp/secrets_backup.txt
docker config ls > /tmp/configs_backup.txt

# 2. Redeploy from backups
./deploy/scripts/deploy.sh init-secrets
./deploy/scripts/deploy.sh init-configs
./deploy/scripts/deploy.sh deploy

# 3. Restore data
./deploy/scripts/restore.sh backup_<date>

# 4. Verify
./deploy/scripts/deploy.sh health-check
```

### Split Brain Recovery

If network partition occurs:

```bash
# Identify manager node in larger partition
docker node ls

# On isolated manager(s), check what happened
docker stack ps prodstack

# Once network heals, Swarm will self-heal
docker node ls  # should show all nodes

# Verify all services are running
docker stack ps prodstack
```

---

## Maintenance Tasks

### Rolling Restart

For applying kernel updates or security patches:

```bash
# Drain node (move services to other nodes)
docker node update --availability drain <node-id>

# Perform maintenance
sudo reboot

# Monitor service rescheduling
watch 'docker node ls'

# Resume node
docker node update --availability active <node-id>

# Verify services rescheduled back
docker stack ps prodstack
```

### Log Rotation

```bash
# Configure in docker compose via logging options
# Logs automatically rotate: max-size=50m, max-file=3

# Manual cleanup if needed
docker exec prodstack_backend rm /var/log/app/*.old
```

### Certificate Rotation

```bash
# Update SSL certificates in /deploy/nginx/certs/
cp /path/to/new/certs/* deploy/nginx/certs/

# Update config
docker config rm nginx_conf
docker config create nginx_conf deploy/nginx/nginx.prod.conf

# Restart nginx
docker service update --force prodstack_nginx
```

---

## Performance Tuning

### Database

```bash
# Monitor slow queries
docker exec <postgres> psql -U postgres -c "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Add indexes for frequently slow queries
docker exec <postgres> psql -U postgres prodstack < indexes.sql
```

### Redis

```bash
# Monitor memory usage
docker exec <redis> redis-cli INFO memory

# Configure eviction policy if needed
docker exec <redis> redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Nginx

```bash
# Monitor connection count
docker exec <nginx> ss -an | grep ESTABLISHED | wc -l

# Check for slow upstream responses
docker exec <nginx> tail -n 100 /var/log/nginx/access.log | grep -E 'rt=[0-9]+\.[0-9]{3}'
```

---

## Related Documentation

- [Zero-Downtime Deployment](./ZERO_DOWNTIME_DEPLOYMENT.md)
- [Auto-scaling Strategy](./AUTOSCALING_STRATEGY.md)
- [Monitoring Guide](./MONITORING_GUIDE.md)
- [Backup & Restore Procedures](./BACKUP_RESTORE_PROCEDURES.md)
- [Troubleshooting Guide](./TROUBLESHOOTING_GUIDE.md)
