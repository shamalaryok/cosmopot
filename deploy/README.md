# Production Deployment - Docker Swarm Stack

Complete production deployment package for the prodstack application on Docker Swarm.

## Quick Start

```bash
# 1. Configure environment
cp .env.prod.template .env.prod
# Edit .env.prod with your values

# 2. Initialize secrets and configs
chmod +x scripts/*.sh
./scripts/deploy.sh init-secrets
./scripts/deploy.sh init-configs

# 3. Deploy stack
./scripts/deploy.sh deploy

# 4. Monitor deployment
watch 'docker stack ps prodstack'

# 5. Verify health
./scripts/deploy.sh health-check
```

## Directory Structure

```
deploy/
├── README.md                          # This file
├── .env.prod.template                 # Environment configuration template
├── docker-compose.prod.yml            # Main stack definition
│
├── scripts/
│   ├── deploy.sh                      # Main deployment script
│   ├── autoscale.sh                   # Autoscaling controller
│   ├── backup.sh                      # Backup script
│   └── restore.sh                     # Restore script
│
├── nginx/
│   └── nginx.prod.conf                # Production Nginx config
│
├── prometheus/
│   └── prometheus.prod.yml            # Prometheus metrics config
│
├── grafana/
│   ├── datasources.yml                # Grafana datasources
│   └── dashboards.yml                 # Grafana dashboards
│
├── postgres/
│   └── init.sql                       # Database initialization
│
├── DEPLOYMENT_RUNBOOK.md              # Operational procedures
├── ZERO_DOWNTIME_DEPLOYMENT.md        # Zero-downtime deployment
├── AUTOSCALING_STRATEGY.md            # Scaling policies & tuning
├── BACKUP_RESTORE_PROCEDURES.md       # Backup & disaster recovery
└── TROUBLESHOOTING_GUIDE.md           # Troubleshooting reference
```

## Core Services

### Application Tier
- **backend** (5-20 replicas) - FastAPI application server
- **worker** (10-50 replicas) - Celery background job workers
- **frontend** (3-10 replicas) - Next.js frontend + reverse proxy

### Infrastructure Tier
- **postgres** - PostgreSQL database
- **redis** - In-memory cache
- **rabbitmq** - Message broker for Celery
- **minio** - Object storage (S3-compatible)

### Monitoring Tier
- **prometheus** - Metrics collection
- **grafana** - Metrics visualization
- **sentry-relay** - Error tracking relay

### Networking Tier
- **nginx** - Reverse proxy, SSL termination, load balancing

## Quick Commands

```bash
# Deployment
./scripts/deploy.sh deploy              # Deploy/update stack
./scripts/deploy.sh status              # Show service status
./scripts/deploy.sh health-check        # Run health checks
./scripts/deploy.sh logs backend        # Stream service logs

# Scaling
./scripts/deploy.sh scale backend 10    # Scale backend to 10 replicas
./scripts/deploy.sh scale worker 30     # Scale worker to 30 replicas
./scripts/deploy.sh scale frontend 5    # Scale frontend to 5 replicas

# Maintenance
./scripts/deploy.sh rollback            # Rollback to previous version
./scripts/backup.sh                     # Backup databases & volumes
./scripts/restore.sh backup_20240101    # Restore from backup

# Autoscaling
./scripts/autoscale.sh                  # Start autoscaler (runs continuously)
```

## Configuration

### Required Environment Variables

Edit `.env.prod`:

```bash
# Container Registry
REGISTRY=docker.io/yourorg              # Your Docker registry
VERSION=latest                          # Image tag

# Database
DATABASE__HOST=postgres
DATABASE__PORT=5432
DATABASE__NAME=prodstack

# Cache
REDIS_URL=redis://redis:6379

# Message Queue
CELERY_BROKER_URL=amqp://rabbitmq:5672

# Object Storage
MINIO_ENDPOINT=http://minio:9000

# Secrets (handled by Docker Swarm secrets)
# Automatically injected into containers
```

### Scaling Configuration

```bash
# Backend API server
BACKEND_MIN=5
BACKEND_MAX=20
BACKEND_CPU_THRESHOLD=70
BACKEND_MEMORY_THRESHOLD=75

# Celery worker
WORKER_MIN=10
WORKER_MAX=50
WORKER_CPU_THRESHOLD=65
WORKER_MEMORY_THRESHOLD=70

# Frontend
FRONTEND_MIN=3
FRONTEND_MAX=10
```

## Prerequisites

### Software
- Docker Engine 20.10+
- Docker CLI with Swarm support
- `curl`, `openssl`, `tar`, `gzip`
- `aws-cli` (optional, for S3 backups)

### Hardware
- **Manager nodes**: 2-3 with 4 CPU, 8GB RAM each
- **Worker nodes**: 3+ with 8 CPU, 16GB RAM each
- **Storage**: NFS for persistent volumes (500GB+ for data)

### Network
- Swarm ports: 2377, 7946, 4789
- Application ports: 80, 443
- Monitoring ports: 9090 (Prometheus), 3000 (Grafana)

## Cluster Setup

### 1. Initialize Swarm

```bash
# On first manager node
docker swarm init --advertise-addr <manager-ip>

# Get tokens for joining
docker swarm join-token manager   # For additional managers
docker swarm join-token worker    # For worker nodes
```

### 2. Add Nodes

```bash
# On each additional node
docker swarm join --token <token> <manager-ip>:2377

# Verify from manager
docker node ls
```

### 3. Label Nodes

```bash
# For workload placement
docker node update --label-add workload=backend <node-id>
docker node update --label-add workload=worker <node-id>
docker node update --label-add workload=frontend <node-id>
```

### 4. Configure Storage

```bash
# Setup NFS on storage server
mkdir -p /exports/{postgres,redis,rabbitmq,minio}
# Add to /etc/exports and run: exportfs -a

# Verify from worker nodes
mount -t nfs <nfs-server>:/exports /mnt/test
umount /mnt/test
```

## Deployment Workflow

### Initial Deployment

```bash
# 1. Prepare configuration
cp .env.prod.template .env.prod
vim .env.prod

# 2. Make scripts executable
chmod +x scripts/*.sh

# 3. Initialize secrets
./scripts/deploy.sh init-secrets
# Follow prompts to set passwords

# 4. Initialize configs
./scripts/deploy.sh init-configs

# 5. Deploy
./scripts/deploy.sh deploy

# 6. Monitor
watch 'docker stack ps prodstack'

# 7. Verify
./scripts/deploy.sh health-check
```

### Updates / Redeployment

```bash
# Update application code
git pull origin main
docker build -f backend/Dockerfile -t $REGISTRY/backend:v2 .
docker push $REGISTRY/backend:v2

# Redeploy
export VERSION=v2
./scripts/deploy.sh deploy

# Automatic rolling update with health checks
watch 'docker service ps prodstack_backend'
```

### Zero-Downtime Deployment

See [ZERO_DOWNTIME_DEPLOYMENT.md](./ZERO_DOWNTIME_DEPLOYMENT.md) for:
- Rolling updates (recommended)
- Blue-green deployments
- Canary releases
- Database migrations safely

## Monitoring

### Prometheus Metrics
```
http://<cluster-ip>:9090
```

### Grafana Dashboards
```
https://<cluster-ip>/grafana
Username: admin
Password: (from .env.prod)
```

### View Logs
```bash
./scripts/deploy.sh logs backend     # API server logs
./scripts/deploy.sh logs worker      # Worker logs
./scripts/deploy.sh logs postgres    # Database logs
```

### Key Metrics
- Request latency (p50, p95, p99)
- Error rates (4xx, 5xx)
- CPU/Memory per service
- Database connections
- Job queue length

## Scaling

### Manual Scaling

```bash
# Scale backend to 10 replicas
./scripts/deploy.sh scale backend 10

# Scale worker to 30 replicas
./scripts/deploy.sh scale worker 30

# Scale frontend to 5 replicas
./scripts/deploy.sh scale frontend 5
```

### Automatic Scaling

```bash
# Start autoscaler (runs continuously)
./scripts/autoscale.sh &

# Configure via environment (in .env.prod)
export BACKEND_CPU_THRESHOLD=70
export WORKER_QUEUE_LENGTH_THRESHOLD=1000

# Scaling policy documentation
cat AUTOSCALING_STRATEGY.md
```

See [AUTOSCALING_STRATEGY.md](./AUTOSCALING_STRATEGY.md) for:
- Scaling policies and thresholds
- Docker Swarm autoscaling
- Kubernetes/KEDA migration path
- Performance tuning

## Backup & Recovery

### Regular Backups

```bash
# Create backup
./scripts/backup.sh

# Backup includes:
# - PostgreSQL database dump
# - Redis snapshot
# - Application volumes
# - Configuration metadata

# Scheduled backups (add to crontab)
0 2 * * * cd /deploy && ./scripts/backup.sh
```

### Restore from Backup

```bash
# List available backups
ls /backups/backup_*

# Restore latest
./scripts/restore.sh backup_20240101_120000

# Restore specific components
./scripts/restore.sh backup_20240101_120000 --skip-redis

# Verify restoration
./scripts/deploy.sh health-check
```

See [BACKUP_RESTORE_PROCEDURES.md](./BACKUP_RESTORE_PROCEDURES.md) for:
- Backup strategies and automation
- Point-in-time recovery
- Disaster recovery procedures
- Data verification

## Troubleshooting

### Common Issues

**Services won't start:**
```bash
docker service logs prodstack_backend
docker service inspect prodstack_backend
```

**High memory usage:**
```bash
docker stats prodstack_backend --no-stream
./scripts/deploy.sh scale backend 15  # Add more replicas
```

**Database connection errors:**
```bash
docker exec postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
# Adjust DATABASE_POOL_SIZE in .env.prod
```

**Network connectivity:**
```bash
docker exec <container> ping backend
docker exec <container> nslookup redis
docker network inspect prodstack_core
```

See [TROUBLESHOOTING_GUIDE.md](./TROUBLESHOOTING_GUIDE.md) for:
- Common issues and solutions
- Debug techniques
- Performance optimization
- Log analysis

## Operational Procedures

See [DEPLOYMENT_RUNBOOK.md](./DEPLOYMENT_RUNBOOK.md) for:
- Initial cluster setup
- Node management
- Service monitoring
- Maintenance tasks
- Disaster recovery

## Architecture

### Service Dependencies

```
Frontend → Nginx ← Backend
                      ↓
                  RabbitMQ → Worker
                      ↓
                   Redis
                      ↓
                  Postgres
                      ↓
                    MinIO
```

### Network Architecture

```
┌─────────────────────────────────────────┐
│       External Internet (443/80)        │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│   Nginx (SSL Termination, LB)           │
└─────────────────────────────────────────┘
   ↓ (overlay network: core 10.10.0.0/24)
┌─────────────────────────────────────────┐
│ Backend  │ Worker  │ Frontend            │
│ Redis    │ RabbitMQ│ Postgres  │ MinIO   │
└─────────────────────────────────────────┘
   ↓ (overlay network: monitoring)
┌─────────────────────────────────────────┐
│ Prometheus  │  Grafana  │  Sentry-Relay │
└─────────────────────────────────────────┘
```

### Persistence

All persistent data stored on external NFS:
- PostgreSQL data volume
- Redis persistence
- RabbitMQ data
- MinIO data
- Prometheus TSDB
- Grafana dashboards

## Performance Baselines

See [../docs/PERFORMANCE_BASELINES.md](../docs/PERFORMANCE_BASELINES.md) for:
- Expected response times
- CPU/memory utilization
- Scalability limits
- Load test results

## Security Considerations

- All secrets managed via Docker Swarm secrets
- SSL/TLS termination at Nginx
- Container resource limits enforced
- Health checks on all services
- Log aggregation for audit trails
- Encryption at rest (backups)

## Support & Documentation

- **Deployment**: [DEPLOYMENT_RUNBOOK.md](./DEPLOYMENT_RUNBOOK.md)
- **Zero-Downtime**: [ZERO_DOWNTIME_DEPLOYMENT.md](./ZERO_DOWNTIME_DEPLOYMENT.md)
- **Scaling**: [AUTOSCALING_STRATEGY.md](./AUTOSCALING_STRATEGY.md)
- **Backup**: [BACKUP_RESTORE_PROCEDURES.md](./BACKUP_RESTORE_PROCEDURES.md)
- **Troubleshooting**: [TROUBLESHOOTING_GUIDE.md](./TROUBLESHOOTING_GUIDE.md)

## Related Documentation

- [Load Testing](../docs/LOAD_TESTING.md)
- [Performance Baselines](../docs/PERFORMANCE_BASELINES.md)
- [Security Implementation](../SECURITY_IMPLEMENTATION.md)

## Version History

- v1.0 (2024-01-XX) - Initial production deployment
  - Docker Swarm stack
  - Autoscaling framework
  - Backup/restore automation
  - Comprehensive documentation
