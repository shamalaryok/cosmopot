# Autoscaling Strategy & Architecture

This document outlines the autoscaling approach for the prodstack, including Docker Swarm implementations and migration path to Kubernetes with KEDA.

## Table of Contents

1. [Overview](#overview)
2. [Docker Swarm Autoscaling](#docker-swarm-autoscaling)
3. [Kubernetes/KEDA Migration Path](#kuberneteskeda-migration-path)
4. [Scaling Policies](#scaling-policies)
5. [Implementation](#implementation)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Testing & Tuning](#testing--tuning)

---

## Overview

Autoscaling ensures the system can handle variable load while minimizing costs. The architecture supports two levels:

1. **Horizontal Pod Autoscaling (HPA)** - Scales replica count based on metrics
2. **Vertical Pod Autoscaling (VPA)** - Adjusts resource requests/limits

Current focus: Horizontal autoscaling for cost optimization.

---

## Docker Swarm Autoscaling

### Implementation

The `deploy/scripts/autoscale.sh` script provides metric-based autoscaling for Docker Swarm:

**How it works:**
1. Queries Prometheus for current resource usage
2. Compares against configured thresholds
3. Scales services up/down via Docker API
4. Includes cooldown periods to prevent flapping

**Thresholds:**

| Service | Min | Max | CPU↑ | Memory↑ | CPU↓ | Memory↓ |
|---------|-----|-----|------|---------|------|---------|
| backend | 5 | 20 | 70% | 75% | 30% | 40% |
| worker | 10 | 50 | 65% | 70% | 20% | 30% |
| worker (queue) | 10 | 50 | N/A | N/A | Queue > 1000 | Queue < 100 |
| frontend | 3 | 10 | 50% | 60% | 20% | 30% |

### Running Autoscaler

**Manual (Development):**
```bash
./deploy/scripts/autoscale.sh
```

**Production (Daemonized):**
```bash
# Via systemd service
sudo cp deploy/systemd/autoscale.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable autoscale
sudo systemctl start autoscale

# Or via supervisor
cp deploy/supervisor/autoscale.conf /etc/supervisor/conf.d/
supervisorctl reread
supervisorctl update
supervisorctl start autoscale
```

**Via Docker service (Meta-level orchestration):**
```bash
# Run autoscaler itself as managed Docker service
docker service create \
  --name autoscale-controller \
  --mode global \
  -e STACK_NAME=prodstack \
  $REGISTRY/autoscaler:latest
```

### Configuration

Environment variables in `deploy/.env.prod`:

```bash
# Backend scaling
BACKEND_MIN=5
BACKEND_MAX=20
BACKEND_CPU_THRESHOLD=70
BACKEND_MEMORY_THRESHOLD=75

# Worker scaling
WORKER_MIN=10
WORKER_MAX=50
WORKER_CPU_THRESHOLD=65
WORKER_MEMORY_THRESHOLD=70
WORKER_QUEUE_LENGTH_THRESHOLD=1000

# Frontend scaling
FRONTEND_MIN=3
FRONTEND_MAX=10
FRONTEND_CPU_THRESHOLD=50
FRONTEND_MEMORY_THRESHOLD=60

# General
CHECK_INTERVAL=30           # Seconds between checks
SCALE_DOWN_COOLDOWN=300     # Seconds before scaling down again
```

---

## Kubernetes/KEDA Migration Path

### Why Migrate?

**Docker Swarm limitations:**
- Metrics gathering requires external tools
- No native autoscaling mechanisms
- Limited scheduling flexibility
- Smaller ecosystem

**Kubernetes/KEDA advantages:**
- Native HPA with built-in metrics server
- KEDA for advanced scalers (RabbitMQ, Redis, etc.)
- Better node affinity and pod disruption budgets
- Richer ecosystem

### Migration Steps (Future)

#### Phase 1: Prepare (Week 1-2)
```bash
# 1. Create Kubernetes cluster
minikube start --cpus=4 --memory=8192
# or managed service (EKS, GKE, AKS)

# 2. Install required operators
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace

# 3. Create namespaces
kubectl create namespace prodstack
kubectl create namespace monitoring
```

#### Phase 2: Convert Swarm Compose to K8s (Week 2-3)
```bash
# Use Kompose for initial conversion
kompose convert -f docker-compose.prod.yml -o k8s/

# Manual adjustments needed for:
# - Secrets management (use K8s Secrets)
# - ConfigMaps (use K8s ConfigMaps)
# - Persistent volumes (use K8s PVCs)
# - Health checks (use K8s Probes)
```

#### Phase 3: Deploy to Kubernetes (Week 3)
```bash
# Apply manifests
kubectl apply -f k8s/

# Verify
kubectl get pods -n prodstack
```

#### Phase 4: Enable KEDA Autoscaling (Week 4)
```bash
# Apply KEDA ScaledObjects
kubectl apply -f k8s/keda/
```

### KEDA Scalers

**RabbitMQ Scaler (for Celery workers):**
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: celery-worker-scaler
  namespace: prodstack
spec:
  scaleTargetRef:
    name: worker
  minReplicaCount: 10
  maxReplicaCount: 50
  triggers:
  - type: rabbitmq
    metadata:
      queueName: celery
      host: rabbitmq
      port: "5672"
      vhostName: /
      mode: QueueLength
      value: "30"  # Scale when 30 msgs per replica
    authenticationRef:
      name: rabbitmq-creds
```

**CPU/Memory Scaler (for Backend):**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
  namespace: prodstack
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 5
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 75
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100  # Double replicas
        periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300  # 5 min cooldown
      policies:
      - type: Percent
        value: 50  # Half replicas
        periodSeconds: 15
```

---

## Scaling Policies

### Backend (API Server)

**Purpose:** Handle incoming HTTP requests

**Triggers:**
- CPU > 70% for 2+ minutes
- Memory > 75% for 2+ minutes
- Queue depth > 100 pending requests

**Policy:**
```yaml
Replicas: 5-20
Scale Up: +1 replica per 2 minutes
Scale Down: -1 replica per 5 minutes
Max Rate: 1 replica per check interval
```

**Rationale:**
- Min 5: Redundancy + failover
- Max 20: Cost control, usually adequate
- CPU 70%: Allows headroom for spikes
- Memory 75%: Prevents OOM crashes
- Slower scale-down: Captures temporary spikes

### Worker (Celery)

**Purpose:** Process background jobs

**Triggers:**
- CPU > 65% for 2+ minutes
- Memory > 70% for 2+ minutes
- Queue length > 1000 messages
- Queue length per replica > 30

**Policy:**
```yaml
Replicas: 10-50
Scale Up: +1-3 replicas (varies by queue size)
Scale Down: -1 replica per 5 minutes
Max Rate: 3 replicas per check interval
```

**Rationale:**
- Min 10: Ensures always processing
- Max 50: Cost limit for bursty workloads
- Queue-based: Primary trigger for workers
- Aggressive scale-up: Handle job spikes quickly
- Slow scale-down: Keep capacity for next spike

### Frontend

**Purpose:** Serve static assets + reverse proxy

**Triggers:**
- CPU > 50% for 2+ minutes
- Memory > 60% for 2+ minutes
- Connection count > 1000

**Policy:**
```yaml
Replicas: 3-10
Scale Up: +1 replica per 2 minutes
Scale Down: -1 replica per 5 minutes
Max Rate: 1 replica per check interval
```

**Rationale:**
- Min 3: Redundancy
- Max 10: Usually fine for typical traffic
- Lower thresholds: Frontend more stateless
- Primarily CPU-driven for this service

---

## Implementation

### Swarm Autoscaling Architecture

```
┌─────────────────────────────────────────┐
│   autoscale.sh (Check every 30s)        │
├─────────────────────────────────────────┤
│ 1. Query Prometheus /api/v1/query       │
│    - Get CPU usage per service          │
│    - Get Memory usage per service       │
│    - Get RabbitMQ queue length          │
├─────────────────────────────────────────┤
│ 2. Compare against thresholds           │
│    - Check if scale-up/down needed      │
│    - Check cooldown period              │
├─────────────────────────────────────────┤
│ 3. Execute scaling                      │
│    - docker service scale service=N     │
│    - Log action + metrics               │
├─────────────────────────────────────────┤
│ 4. Monitor and alert                    │
│    - Alert if hitting min/max limits    │
│    - Alert if errors occur              │
└─────────────────────────────────────────┘
```

### Kubernetes/KEDA Architecture

```
┌────────────────────────────────────────┐
│   Kubernetes HPA/KEDA Controllers      │
├────────────────────────────────────────┤
│ 1. Metrics Server (collects metrics)   │
│    - CPU, Memory from node metrics      │
│    - Custom metrics from applications   │
├────────────────────────────────────────┤
│ 2. KEDA Scalers (external sources)    │
│    - RabbitMQ queue length             │
│    - Redis queue depth                 │
│    - HTTP metrics                      │
├────────────────────────────────────────┤
│ 3. HPA Controller (makes decisions)    │
│    - Evaluates thresholds              │
│    - Updates replica counts            │
│    - Respects stabilization window     │
└────────────────────────────────────────┘
```

---

## Monitoring & Alerts

### Key Metrics to Track

```prometheus
# Replica counts
count(container_last_seen{service_name="prodstack_backend"})
count(container_last_seen{service_name="prodstack_worker"})
count(container_last_seen{service_name="prodstack_frontend"})

# Resource usage
rate(container_cpu_usage_seconds_total{service_name="prodstack_backend"}[5m])
container_memory_usage_bytes{service_name="prodstack_backend"}

# Queue depth
rabbitmq_queue_messages_ready{queue="celery"}

# Request rates
rate(http_requests_total{service="backend"}[5m])
rate(http_requests_total{status=~"5.."}[5m])

# Response times
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

### Alert Rules

```yaml
# alerts.yml
groups:
  - name: autoscaling
    rules:
      # Backend at min replicas and high load
      - alert: BackendMinReplicasHighLoad
        expr: |
          (count(container_last_seen{service_name="prodstack_backend"}) == 5)
          and
          (rate(container_cpu_usage_seconds_total{service_name="prodstack_backend"}[5m]) > 0.7)
        for: 5m
        annotations:
          summary: "Backend at min replicas with high load"
          
      # Worker queue backing up
      - alert: WorkerQueueBackingUp
        expr: rabbitmq_queue_messages_ready{queue="celery"} > 10000
        for: 5m
        annotations:
          summary: "Worker queue has {{ $value }} pending tasks"
          
      # Scaling failed
      - alert: ScalingActionFailed
        expr: increase(autoscale_failed_attempts_total[5m]) > 0
        annotations:
          summary: "Autoscaling action failed"
```

### Monitoring Dashboard

Create Grafana dashboard with:
- Replica count trends per service
- CPU/Memory usage per service
- Scaling action history (up/down events)
- Queue length trends
- Request rate correlation with scaling

---

## Testing & Tuning

### Load Testing

```bash
# Generate load to test scaling
./deploy/scripts/run_load_tests.sh --users 500 --spawn-rate 50 --duration 600

# Monitor scaling in real-time
watch -n 2 'docker service ls | grep prodstack'

# Review metrics
curl 'http://prometheus:9090/api/v1/query?query=up'
```

### Scaling Simulation

```bash
# Test scale-up trigger
# Simulate high CPU with stress-ng in backend container
docker exec <backend-container> stress-ng --cpu 1 --timeout 120s &

# Monitor autoscaling response
watch -n 5 'docker service ps prodstack_backend | tail -10'

# Should see new replicas starting within 1-2 minutes

# Test scale-down
# Stop load
pkill stress-ng

# Wait for cooldown + scale-down check
watch -n 5 'docker service ps prodstack_backend'

# Should see replicas terminating after 5+ minutes
```

### Threshold Tuning

**If scaling too aggressively (thrashing):**
```bash
# Increase thresholds
export BACKEND_CPU_THRESHOLD=80        # was 70
export SCALE_DOWN_COOLDOWN=600         # was 300
```

**If not scaling enough (bottlenecks):**
```bash
# Decrease thresholds
export BACKEND_CPU_THRESHOLD=60        # was 70
export BACKEND_MAX=30                  # was 20
```

**If scale-up too slow:**
```bash
# Decrease check interval and delay
export CHECK_INTERVAL=15               # was 30
export SCALE_UP_DELAY=15               # was 30
```

### Historical Analysis

```bash
# Query scaling events over last week
curl 'http://prometheus:9090/api/v1/query_range' \
  --data-urlencode 'query=increase(container_last_seen{service_name="prodstack_backend"}[1h])' \
  --data-urlencode 'start=2024-01-01T00:00:00Z' \
  --data-urlencode 'end=2024-01-08T00:00:00Z' \
  --data-urlencode 'step=3600s' | jq .

# Analyze patterns:
# - Peak hours
# - Sudden spikes
# - Slow burn increases
# - Off-hours baseline
```

---

## Cost Optimization

### Right-sizing

```bash
# Before tuning
Min: 5 + 10 + 3 = 18 replicas (baseline)
Max: 20 + 50 + 10 = 80 replicas (peak)

# Calculate monthly cost
18 * 24 * 30 * $per_replica_hour = baseline_cost
# Example: 18 * 24 * 30 * $0.05 = $648/month

# After tuning with autoscaling
Average: 15 replicas (instead of 18)
Savings: 3 * 24 * 30 * $0.05 = $108/month
```

### Reserved Capacity

For predictable workloads:

```bash
# Identify baseline from metrics
p50_replicas = 10  # Median replica count
reserve_this = 10

# Use on-demand for above baseline
on_demand_max = 80 - 10 = 70
```

---

## Related Documentation

- [Deployment Runbook](./DEPLOYMENT_RUNBOOK.md)
- [Zero-Downtime Deployment](./ZERO_DOWNTIME_DEPLOYMENT.md)
- [Monitoring Guide](./MONITORING_GUIDE.md)
- [Performance Baselines](../docs/PERFORMANCE_BASELINES.md)
