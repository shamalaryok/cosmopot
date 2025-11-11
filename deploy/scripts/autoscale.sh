#!/bin/bash
set -euo pipefail

# Docker Swarm Auto-scaling Controller Script
# This script monitors service metrics and scales services accordingly
# For production, consider using KEDA or Kubernetes HPA alternatives

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Configuration
STACK_NAME="${STACK_NAME:-prodstack}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"  # seconds
METRICS_URL="${METRICS_URL:-http://prometheus:9090}"

# Scaling policies (can be overridden via environment)
BACKEND_MIN=${BACKEND_MIN:-5}
BACKEND_MAX=${BACKEND_MAX:-20}
BACKEND_CPU_THRESHOLD=${BACKEND_CPU_THRESHOLD:-70}
BACKEND_MEMORY_THRESHOLD=${BACKEND_MEMORY_THRESHOLD:-75}

WORKER_MIN=${WORKER_MIN:-10}
WORKER_MAX=${WORKER_MAX:-50}
WORKER_CPU_THRESHOLD=${WORKER_CPU_THRESHOLD:-65}
WORKER_MEMORY_THRESHOLD=${WORKER_MEMORY_THRESHOLD:-70}
WORKER_QUEUE_LENGTH_THRESHOLD=${WORKER_QUEUE_LENGTH_THRESHOLD:-1000}

FRONTEND_MIN=${FRONTEND_MIN:-3}
FRONTEND_MAX=${FRONTEND_MAX:-10}
FRONTEND_CPU_THRESHOLD=${FRONTEND_CPU_THRESHOLD:-50}
FRONTEND_MEMORY_THRESHOLD=${FRONTEND_MEMORY_THRESHOLD:-60}

# Scale-down cooldown (prevent flapping)
SCALE_DOWN_COOLDOWN=${SCALE_DOWN_COOLDOWN:-300}  # 5 minutes
declare -A last_scale_down_time

# Get current service replicas
get_replicas() {
    local service="$1"
    docker service ls --filter "name=${STACK_NAME}_${service}" --format "{{.Replicas}}" | grep -o '^[0-9]*'
}

# Get CPU usage percentage from Prometheus
get_cpu_usage() {
    local service="$1"
    local query="100 * sum(rate(container_cpu_usage_seconds_total{service_name=\"${STACK_NAME}_${service}\"}[5m])) / on() ignoring(cpu) group_left sum(machine_cpu_cores)"
    
    curl -s "${METRICS_URL}/api/v1/query?query=${query}" | \
        grep -o '"value":\[[^,]*,[^]]*\]' | tail -1 | grep -o '[0-9.]*$' || echo "0"
}

# Get memory usage percentage from Prometheus
get_memory_usage() {
    local service="$1"
    local query="100 * sum(container_memory_usage_bytes{service_name=\"${STACK_NAME}_${service}\"}) / sum(machine_memory_bytes)"
    
    curl -s "${METRICS_URL}/api/v1/query?query=${query}" | \
        grep -o '"value":\[[^,]*,[^]]*\]' | tail -1 | grep -o '[0-9.]*$' || echo "0"
}

# Get RabbitMQ queue length
get_queue_length() {
    local queue="${1:-default}"
    
    curl -s "http://rabbitmq:15672/api/queues/%2F/${queue}" \
        -u "guest:guest" 2>/dev/null | \
        grep -o '"messages_ready":[0-9]*' | grep -o '[0-9]*$' || echo "0"
}

# Scale service up
scale_up() {
    local service="$1"
    local current_replicas="$2"
    local max_replicas="$3"
    local increment="${4:-1}"
    
    local new_replicas=$((current_replicas + increment))
    if (( new_replicas > max_replicas )); then
        new_replicas=$max_replicas
    fi
    
    if (( new_replicas > current_replicas )); then
        docker service scale "${STACK_NAME}_${service}=${new_replicas}"
        log_success "Scaled $service UP: $current_replicas -> $new_replicas replicas"
        return 0
    fi
    
    return 1
}

# Scale service down
scale_down() {
    local service="$1"
    local current_replicas="$2"
    local min_replicas="$3"
    local decrement="${4:-1}"
    
    # Check cooldown period
    local last_scale="${last_scale_down_time[$service]:-0}"
    local now=$(date +%s)
    if (( now - last_scale < SCALE_DOWN_COOLDOWN )); then
        log_warning "$service scale-down still in cooldown period"
        return 1
    fi
    
    local new_replicas=$((current_replicas - decrement))
    if (( new_replicas < min_replicas )); then
        new_replicas=$min_replicas
    fi
    
    if (( new_replicas < current_replicas )); then
        docker service scale "${STACK_NAME}_${service}=${new_replicas}"
        log_success "Scaled $service DOWN: $current_replicas -> $new_replicas replicas"
        last_scale_down_time[$service]=$(date +%s)
        return 0
    fi
    
    return 1
}

# Check and scale backend
check_backend() {
    local service="backend"
    local current=$(get_replicas "$service")
    
    if [[ -z "$current" ]]; then
        log_warning "Could not get replica count for $service"
        return
    fi
    
    log_info "Backend: $current/$BACKEND_MAX replicas"
    
    local cpu=$(get_cpu_usage "$service")
    local mem=$(get_memory_usage "$service")
    
    log_info "Backend metrics - CPU: ${cpu}%, Memory: ${mem}%"
    
    # Scale up if thresholds exceeded
    if (( ${cpu%.*} > BACKEND_CPU_THRESHOLD || ${mem%.*} > BACKEND_MEMORY_THRESHOLD )); then
        if (( current < BACKEND_MAX )); then
            scale_up "$service" "$current" "$BACKEND_MAX" 1
        else
            log_warning "Backend at max replicas but thresholds exceeded"
        fi
    # Scale down if low utilization
    elif (( ${cpu%.*} < 30 && ${mem%.*} < 40 )); then
        if (( current > BACKEND_MIN )); then
            scale_down "$service" "$current" "$BACKEND_MIN" 1
        fi
    fi
}

# Check and scale worker
check_worker() {
    local service="worker"
    local current=$(get_replicas "$service")
    
    if [[ -z "$current" ]]; then
        log_warning "Could not get replica count for $service"
        return
    fi
    
    log_info "Worker: $current/$WORKER_MAX replicas"
    
    local cpu=$(get_cpu_usage "$service")
    local mem=$(get_memory_usage "$service")
    local queue_length=$(get_queue_length "celery")
    
    log_info "Worker metrics - CPU: ${cpu}%, Memory: ${mem}%, Queue: ${queue_length}"
    
    # Scale up if thresholds exceeded
    if (( ${cpu%.*} > WORKER_CPU_THRESHOLD || ${mem%.*} > WORKER_MEMORY_THRESHOLD || queue_length > WORKER_QUEUE_LENGTH_THRESHOLD )); then
        if (( current < WORKER_MAX )); then
            # Scale more aggressively if queue is growing
            local increment=1
            if (( queue_length > WORKER_QUEUE_LENGTH_THRESHOLD * 2 )); then
                increment=3
            fi
            scale_up "$service" "$current" "$WORKER_MAX" "$increment"
        else
            log_warning "Worker at max replicas but thresholds exceeded (queue: $queue_length)"
        fi
    # Scale down if low utilization and queue empty
    elif (( ${cpu%.*} < 20 && ${mem%.*} < 30 && queue_length < 100 )); then
        if (( current > WORKER_MIN )); then
            scale_down "$service" "$current" "$WORKER_MIN" 1
        fi
    fi
}

# Check and scale frontend
check_frontend() {
    local service="frontend"
    local current=$(get_replicas "$service")
    
    if [[ -z "$current" ]]; then
        log_warning "Could not get replica count for $service"
        return
    fi
    
    log_info "Frontend: $current/$FRONTEND_MAX replicas"
    
    local cpu=$(get_cpu_usage "$service")
    local mem=$(get_memory_usage "$service")
    
    log_info "Frontend metrics - CPU: ${cpu}%, Memory: ${mem}%"
    
    # Scale up if thresholds exceeded
    if (( ${cpu%.*} > FRONTEND_CPU_THRESHOLD || ${mem%.*} > FRONTEND_MEMORY_THRESHOLD )); then
        if (( current < FRONTEND_MAX )); then
            scale_up "$service" "$current" "$FRONTEND_MAX" 1
        fi
    # Scale down if low utilization
    elif (( ${cpu%.*} < 20 && ${mem%.*} < 30 )); then
        if (( current > FRONTEND_MIN )); then
            scale_down "$service" "$current" "$FRONTEND_MIN" 1
        fi
    fi
}

# Main loop
run_autoscaler() {
    log_info "Starting autoscaler for stack: $STACK_NAME"
    log_info "Check interval: ${CHECK_INTERVAL}s"
    
    while true; do
        log_info "=== Autoscaling Check ==="
        
        check_backend
        check_worker
        check_frontend
        
        sleep "$CHECK_INTERVAL"
    done
}

# Handle signals
trap 'log_info "Autoscaler stopped"; exit 0' SIGTERM SIGINT

# Validation
validate() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker command not found"
        exit 1
    fi
    
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker daemon not accessible"
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        log_error "curl command not found"
        exit 1
    fi
}

# Main
validate
run_autoscaler
