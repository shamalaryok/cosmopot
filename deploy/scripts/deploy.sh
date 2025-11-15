#!/bin/bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
ENV_FILE="${DEPLOY_DIR}/.env.prod"
STACK_NAME="${STACK_NAME:-prodstack}"
REGISTRY="${REGISTRY:-localhost}"
VERSION="${VERSION:-latest}"

# Parse command line arguments
COMMAND="${1:-help}"
ACTION="${2:-}"

usage() {
    cat << EOF
Usage: $(basename "$0") <command> [options]

Commands:
    deploy          Deploy or update the Swarm stack
    rollback        Rollback to previous version
    scale           Scale services (backend, worker, frontend)
    status          Show stack status
    logs            Stream service logs
    backup          Backup databases and volumes
    restore         Restore from backup
    init-secrets    Initialize secrets on Swarm
    init-configs   Initialize configs on Swarm
    health-check   Perform health checks
    help            Show this help message

Examples:
    $(basename "$0") deploy
    $(basename "$0") scale backend 15
    $(basename "$0") scale worker 30
    $(basename "$0") status
    $(basename "$0") health-check

EOF
}

# Load environment
load_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error "Environment file not found: $ENV_FILE"
        log_info "Please copy and configure: $DEPLOY_DIR/.env.prod.template"
        exit 1
    fi
    
    # shellcheck source=/dev/null
    set -a
    source "$ENV_FILE"
    set +a
    
    log_info "Environment loaded from $ENV_FILE"
}

# Check prerequisites
check_prerequisites() {
    local required_cmds=("docker" "curl")
    
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done
    
    # Check if Docker daemon is running
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker daemon is not running or not accessible"
        exit 1
    fi
    
    # Check if in Swarm mode
    if ! docker info | grep -q "Swarm: active"; then
        log_error "Docker is not in Swarm mode. Initialize with: docker swarm init"
        exit 1
    fi
    
    log_success "All prerequisites met"
}

# Initialize secrets on Swarm
init_secrets() {
    log_info "Initializing secrets on Docker Swarm..."
    
    local secrets=(
        "db_password:$(openssl rand -base64 32)"
        "db_user:prodstack"
        "redis_password:$(openssl rand -base64 32)"
        "rabbitmq_password:$(openssl rand -base64 32)"
        "minio_root_password:$(openssl rand -base64 32)"
        "minio_secret_key:$(openssl rand -base64 32)"
        "encryption_key:$(openssl rand -base64 32)"
        "stripe_api_key:sk_live_$(openssl rand -hex 32)"
        "stripe_webhook_secret:whsec_$(openssl rand -hex 32)"
        "sentry_dsn:https://key@sentry.io/123456"
        "grafana_password:$(openssl rand -base64 32)"
    )
    
    for secret_pair in "${secrets[@]}"; do
        secret_name="${secret_pair%:*}"
        secret_value="${secret_pair#*:}"
        
        # Check if secret already exists
        if docker secret inspect "$secret_name" > /dev/null 2>&1; then
            log_warning "Secret already exists: $secret_name (skipping)"
        else
            echo -n "$secret_value" | docker secret create "$secret_name" -
            log_success "Created secret: $secret_name"
        fi
    done
}

# Initialize configs on Swarm
init_configs() {
    log_info "Initializing configs on Docker Swarm..."
    
    local config_files=(
        "nginx_conf:${DEPLOY_DIR}/nginx/nginx.prod.conf"
        "prometheus_conf:${DEPLOY_DIR}/prometheus/prometheus.prod.yml"
        "grafana_datasources:${DEPLOY_DIR}/grafana/datasources.yml"
        "grafana_dashboards:${DEPLOY_DIR}/grafana/dashboards.yml"
        "postgres_init:${DEPLOY_DIR}/postgres/init.sql"
    )
    
    for config_pair in "${config_files[@]}"; do
        config_name="${config_pair%:*}"
        config_file="${config_pair#*:}"
        
        if [[ ! -f "$config_file" ]]; then
            log_error "Config file not found: $config_file"
            continue
        fi
        
        # Check if config already exists
        if docker config inspect "$config_name" > /dev/null 2>&1; then
            log_warning "Config already exists: $config_name (removing old version)"
            docker config rm "$config_name"
        fi
        
        docker config create "$config_name" "$config_file"
        log_success "Created config: $config_name"
    done
}

# Deploy stack
deploy() {
    load_env
    check_prerequisites
    
    log_info "Deploying $STACK_NAME stack..."
    
    # Initialize secrets and configs if needed
    if ! docker secret inspect db_password > /dev/null 2>&1; then
        log_info "Secrets not found, initializing..."
        init_secrets
    fi
    
    if ! docker config inspect nginx_conf > /dev/null 2>&1; then
        log_info "Configs not found, initializing..."
        init_configs
    fi
    
    # Pull latest images
    log_info "Pulling latest images..."
    docker pull "${REGISTRY}/backend:${VERSION}" || log_warning "Could not pull backend image"
    docker pull "${REGISTRY}/worker:${VERSION}" || log_warning "Could not pull worker image"
    docker pull "${REGISTRY}/frontend:${VERSION}" || log_warning "Could not pull frontend image"
    
    # Deploy stack
    REGISTRY="$REGISTRY" VERSION="$VERSION" docker stack deploy \
        -c "${DEPLOY_DIR}/docker-compose.prod.yml" \
        "$STACK_NAME"
    
    log_success "Stack deployment initiated"
    
    # Wait for services to stabilize
    log_info "Waiting for services to stabilize..."
    sleep 10
    
    # Show status
    docker stack services "$STACK_NAME"
}

# Rollback to previous version
rollback() {
    load_env
    check_prerequisites
    
    local previous_version="${VERSION}-previous"
    
    log_warning "Rolling back to version: $previous_version"
    
    REGISTRY="$REGISTRY" VERSION="$previous_version" docker stack deploy \
        -c "${DEPLOY_DIR}/docker-compose.prod.yml" \
        "$STACK_NAME"
    
    log_success "Rollback initiated"
}

# Scale services
scale() {
    check_prerequisites
    
    local service="${1:-}"
    local replicas="${2:-}"
    
    if [[ -z "$service" ]] || [[ -z "$replicas" ]]; then
        log_error "Usage: $(basename "$0") scale <service> <replicas>"
        log_error "Services: backend, worker, frontend"
        exit 1
    fi
    
    case "$service" in
        backend)
            docker service scale "${STACK_NAME}_backend=${replicas}"
            log_success "Scaled backend to $replicas replicas"
            ;;
        worker)
            docker service scale "${STACK_NAME}_worker=${replicas}"
            log_success "Scaled worker to $replicas replicas"
            ;;
        frontend)
            docker service scale "${STACK_NAME}_frontend=${replicas}"
            log_success "Scaled frontend to $replicas replicas"
            ;;
        *)
            log_error "Unknown service: $service"
            exit 1
            ;;
    esac
}

# Show stack status
show_status() {
    check_prerequisites
    
    log_info "=== Stack Status ==="
    docker stack ps "$STACK_NAME" -q | head -20
    
    log_info "\n=== Service Status ==="
    docker stack services "$STACK_NAME"
    
    log_info "\n=== Task Status ==="
    docker stack ps "$STACK_NAME"
}

# Stream logs
stream_logs() {
    local service="${1:-}"
    
    if [[ -z "$service" ]]; then
        log_error "Usage: $(basename "$0") logs <service>"
        log_error "Services: backend, worker, frontend, postgres, redis, rabbitmq, minio, nginx, prometheus, grafana"
        exit 1
    fi
    
    log_info "Streaming logs for: $service"
    docker service logs -f "${STACK_NAME}_${service}"
}

# Perform health checks
health_check() {
    check_prerequisites
    
    log_info "=== Performing Health Checks ==="
    
    local checks=(
        "backend:8000:/health"
        "frontend:8080:/"
        "postgres:5432:pg_isready"
        "redis:6379:PING"
        "rabbitmq:5672:rabbitmq-diagnostics"
        "prometheus:9090:/-/healthy"
        "grafana:3000:/api/health"
    )
    
    for check in "${checks[@]}"; do
        local service="${check%:*}"
        local port="${check#*:}"
        port="${port%:*}"
        local path="${check##*:}"
        
        log_info "Checking $service on port $port..."
        
        # Get service IP
        local task_id=$(docker stack ps "$STACK_NAME" --filter "service=${STACK_NAME}_${service}" --no-trunc -q | head -1)
        
        if [[ -z "$task_id" ]]; then
            log_error "No running task found for $service"
            continue
        fi
        
        # Simple health check (would need more sophisticated approach for prod)
        if docker exec "$task_id" curl -f "http://localhost:${port}${path}" > /dev/null 2>&1; then
            log_success "$service is healthy"
        else
            log_warning "$service health check failed"
        fi
    done
}

# Main command handler
case "$COMMAND" in
    deploy)
        deploy
        ;;
    rollback)
        rollback
        ;;
    scale)
        scale "$ACTION" "${3:-}"
        ;;
    status)
        show_status
        ;;
    logs)
        stream_logs "$ACTION"
        ;;
    init-secrets)
        init_secrets
        ;;
    init-configs)
        init_configs
        ;;
    health-check)
        health_check
        ;;
    help)
        usage
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
