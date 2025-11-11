#!/bin/bash
# Observability Stack Deployment Script
# Part of the production deployment automation

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/deploy/docker-compose.prod.yml"

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Pre-flight checks
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Swarm
    if ! docker info | grep -q "Swarm: active"; then
        log_error "Docker Swarm is not initialized"
        exit 1
    fi
    
    # Check secrets
    local required_secrets=(
        "sentry_dsn"
        "pagerduty_service_key" 
        "grafana_password"
        "alertmanager_config"
    )
    
    for secret in "${required_secrets[@]}"; do
        if ! docker secret ls | grep -q "$secret"; then
            log_error "Secret $secret is not available"
            log_info "Create it with: echo 'value' | docker secret create $secret -"
            exit 1
        fi
    done
    
    log_success "Prerequisites check passed"
}

# Deploy observability stack
deploy_observability() {
    log_info "Deploying observability stack..."
    
    cd "$PROJECT_ROOT"
    
    # Deploy monitoring services
    docker stack deploy -c "$COMPOSE_FILE" prodstack \
        prometheus \
        grafana \
        alertmanager \
        postgres_exporter \
        redis_exporter \
        node_exporter \
        nginx_exporter \
        sentry-relay
    
    log_success "Observability stack deployed"
}

# Wait for services to be ready
wait_for_services() {
    log_info "Waiting for services to be ready..."
    
    local services=(
        "prometheus:9090"
        "grafana:3000"
        "alertmanager:9093"
    )
    
    for service in "${services[@]}"; do
        local name=$(echo "$service" | cut -d: -f1)
        local port=$(echo "$service" | cut -d: -f2)
        local max_attempts=30
        local attempt=1
        
        log_info "Waiting for $name..."
        
        while [ $attempt -le $max_attempts ]; do
            if curl -f -s "http://localhost:$port/-/healthy" > /dev/null 2>&1; then
                log_success "$name is ready"
                break
            fi
            
            if [ $attempt -eq $max_attempts ]; then
                log_error "$name failed to become ready"
                return 1
            fi
            
            sleep 10
            ((attempt++))
        done
    done
}

# Verify configuration
verify_configuration() {
    log_info "Verifying configuration..."
    
    # Check Prometheus targets
    log_info "Checking Prometheus targets..."
    local targets=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null | jq -r '.data.activeTargets | length' 2>/dev/null || echo "0")
    
    if [ "$targets" -gt 0 ]; then
        log_success "Prometheus is scraping $targets targets"
    else
        log_warning "Prometheus is not scraping any targets"
    fi
    
    # Check Grafana datasources
    log_info "Checking Grafana datasources..."
    local datasources=$(curl -s -u admin:$(docker secret inspect grafana_password --format '{{.Secret.Payload}}' | base64 -d) \
        http://localhost:3000/api/datasources 2>/dev/null | jq -r '. | length' 2>/dev/null || echo "0")
    
    if [ "$datasources" -gt 0 ]; then
        log_success "Grafana has $datasources datasources configured"
    else
        log_warning "Grafana has no datasources configured"
    fi
    
    # Check Alertmanager config
    log_info "Checking Alertmanager configuration..."
    if curl -f -s http://localhost:9093/api/v1/status > /dev/null 2>&1; then
        log_success "Alertmanager is configured and accessible"
    else
        log_warning "Alertmanager may not be properly configured"
    fi
}

# Test metrics collection
test_metrics() {
    log_info "Testing metrics collection..."
    
    # Test backend metrics
    local metrics=$(curl -s http://localhost:8000/metrics 2>/dev/null | grep -c "http_requests_total" || echo "0")
    
    if [ "$metrics" -gt 0 ]; then
        log_success "Backend metrics are being collected"
    else
        log_warning "Backend metrics may not be available"
    fi
    
    # Test Prometheus query
    local query_result=$(curl -s 'http://localhost:9090/api/v1/query?query=up' 2>/dev/null | jq -r '.data.result | length' 2>/dev/null || echo "0")
    
    if [ "$query_result" -gt 0 ]; then
        log_success "Prometheus queries are working"
    else
        log_warning "Prometheus queries may not be working"
    fi
}

# Test alerting
test_alerting() {
    log_info "Testing alerting configuration..."
    
    # Check Alertmanager routes
    local routes=$(curl -s http://localhost:9093/api/v1/routes 2>/dev/null | jq -r '.data | length' 2>/dev/null || echo "0")
    
    if [ "$routes" -gt 0 ]; then
        log_success "Alertmanager has $routes routes configured"
    else
        log_warning "Alertmanager has no routes configured"
    fi
    
    # Check Prometheus rules
    local rules=$(curl -s http://localhost:9090/api/v1/rules 2>/dev/null | jq -r '.data.groups | length' 2>/dev/null || echo "0")
    
    if [ "$rules" -gt 0 ]; then
        log_success "Prometheus has $rules rule groups configured"
    else
        log_warning "Prometheus has no rules configured"
    fi
}

# Show access information
show_access_info() {
    log_info "Observability stack access information:"
    echo
    echo "Grafana Dashboard:"
    echo "  URL: http://localhost:3000"
    echo "  User: admin"
    echo "  Password: (check grafana_password secret)"
    echo
    echo "Prometheus:"
    echo "  URL: http://localhost:9090"
    echo "  Targets: http://localhost:9090/targets"
    echo "  Rules: http://localhost:9090/rules"
    echo
    echo "Alertmanager:"
    echo "  URL: http://localhost:9093"
    echo "  Status: http://localhost:9093/#/status"
    echo "  Alerts: http://localhost:9093/#/alerts"
    echo
    echo "Backend Metrics:"
    echo "  URL: http://localhost:8000/metrics"
    echo "  Health: http://localhost:8000/health"
    echo "  SLA: http://localhost:8000/sla/status"
    echo
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    # Add any cleanup tasks here
}

# Main execution
main() {
    case "${1:-deploy}" in
        "deploy")
            check_prerequisites
            deploy_observability
            wait_for_services
            verify_configuration
            test_metrics
            test_alerting
            show_access_info
            ;;
        "verify")
            verify_configuration
            test_metrics
            test_alerting
            ;;
        "test")
            test_metrics
            test_alerting
            ;;
        "access")
            show_access_info
            ;;
        *)
            echo "Usage: $0 {deploy|verify|test|access}"
            echo
            echo "Commands:"
            echo "  deploy  - Deploy and configure observability stack"
            echo "  verify  - Verify existing configuration"
            echo "  test    - Test metrics and alerting"
            echo "  access  - Show access information"
            exit 1
            ;;
    esac
}

# Trap cleanup
trap cleanup EXIT

# Run main function
main "$@"