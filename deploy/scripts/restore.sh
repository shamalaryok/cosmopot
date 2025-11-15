#!/bin/bash
set -euo pipefail

# Production Restore Script for Docker Swarm Stack
# Restores from backups created by backup.sh

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
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_NAME="${1:-}"

usage() {
    cat << EOF
Usage: $(basename "$0") <backup_name> [options]

Arguments:
    backup_name     Name of the backup to restore (e.g., backup_20240101_120000)

Options:
    --skip-postgres     Skip PostgreSQL restore
    --skip-redis        Skip Redis restore
    --skip-volumes      Skip volume restore
    --no-confirm        Skip confirmation prompt

Examples:
    $(basename "$0") backup_20240101_120000
    $(basename "$0") backup_20240101_120000 --no-confirm

EOF
}

if [[ -z "$BACKUP_NAME" ]]; then
    log_error "Backup name required"
    usage
    exit 1
fi

# Parse options
SKIP_POSTGRES=false
SKIP_REDIS=false
SKIP_VOLUMES=false
NO_CONFIRM=false

shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-postgres) SKIP_POSTGRES=true ;;
        --skip-redis) SKIP_REDIS=true ;;
        --skip-volumes) SKIP_VOLUMES=true ;;
        --no-confirm) NO_CONFIRM=true ;;
        *) log_error "Unknown option: $1"; usage; exit 1 ;;
    esac
    shift
done

# Determine backup path
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
if [[ -d "$BACKUP_PATH" ]]; then
    # Uncompressed backup
    :
elif [[ -f "${BACKUP_PATH}.tar.gz" ]]; then
    # Compressed backup - extract first
    log_info "Extracting compressed backup..."
    tar -xzf "${BACKUP_PATH}.tar.gz" -C "$BACKUP_DIR"
elif [[ -f "${BACKUP_PATH}.tar.gz.enc" ]]; then
    # Encrypted backup - decrypt and extract
    log_info "Decrypting backup..."
    local encryption_key="${ENCRYPTION_KEY:-}"
    if [[ -z "$encryption_key" ]]; then
        log_error "Encrypted backup found but ENCRYPTION_KEY not set"
        exit 1
    fi
    
    if ! command -v openssl &> /dev/null; then
        log_error "openssl not found"
        exit 1
    fi
    
    openssl enc -aes-256-cbc -d -in "${BACKUP_PATH}.tar.gz.enc" -out "${BACKUP_PATH}.tar.gz" -k "$encryption_key"
    log_info "Extracting decrypted backup..."
    tar -xzf "${BACKUP_PATH}.tar.gz" -C "$BACKUP_DIR"
else
    log_error "Backup not found: $BACKUP_PATH"
    exit 1
fi

if [[ ! -d "$BACKUP_PATH" ]]; then
    log_error "Backup path not accessible: $BACKUP_PATH"
    exit 1
fi

# Confirmation
if [[ "$NO_CONFIRM" != "true" ]]; then
    log_warning "This will restore from backup: $BACKUP_NAME"
    log_warning "Existing data will be overwritten"
    read -p "Continue? (yes/no): " -r confirm
    if [[ "$confirm" != "yes" ]]; then
        log_info "Restore cancelled"
        exit 0
    fi
fi

# Get database container
get_postgres_container() {
    docker ps --filter "label=service=postgres" -q | head -1
}

# Get Redis container
get_redis_container() {
    docker ps --filter "label=service=redis" -q | head -1
}

# Restore PostgreSQL
restore_postgres() {
    if [[ "$SKIP_POSTGRES" == "true" ]]; then
        log_info "Skipping PostgreSQL restore"
        return
    fi
    
    local db_backup="${BACKUP_PATH}/postgres_dump.sql"
    
    if [[ ! -f "$db_backup" ]]; then
        log_warning "PostgreSQL dump not found: $db_backup"
        return 1
    fi
    
    log_info "Restoring PostgreSQL..."
    
    local db_container=$(get_postgres_container)
    if [[ -z "$db_container" ]]; then
        log_error "PostgreSQL container not found"
        return 1
    fi
    
    # Drop and recreate database
    docker exec "$db_container" psql -U postgres -c "DROP DATABASE IF EXISTS prodstack;" || true
    docker exec "$db_container" psql -U postgres -c "CREATE DATABASE prodstack;"
    
    # Restore from dump
    docker exec -i "$db_container" psql -U postgres prodstack < "$db_backup"
    
    log_success "PostgreSQL restored"
}

# Restore Redis
restore_redis() {
    if [[ "$SKIP_REDIS" == "true" ]]; then
        log_info "Skipping Redis restore"
        return
    fi
    
    local redis_backup="${BACKUP_PATH}/redis_dump.rdb"
    
    if [[ ! -f "$redis_backup" ]]; then
        log_warning "Redis dump not found: $redis_backup"
        return 1
    fi
    
    log_info "Restoring Redis..."
    
    local redis_container=$(get_redis_container)
    if [[ -z "$redis_container" ]]; then
        log_error "Redis container not found"
        return 1
    fi
    
    # Stop Redis to safely replace dump
    docker exec "$redis_container" redis-cli SHUTDOWN
    sleep 2
    
    # Copy new dump
    docker cp "$redis_backup" "$redis_container:/data/dump.rdb"
    
    # Restart Redis
    docker restart "$redis_container"
    sleep 2
    
    log_success "Redis restored"
}

# Restore volumes
restore_volumes() {
    if [[ "$SKIP_VOLUMES" == "true" ]]; then
        log_info "Skipping volume restore"
        return
    fi
    
    log_info "Restoring application volumes..."
    
    local volumes_backup="${BACKUP_PATH}/volumes"
    
    if [[ ! -d "$volumes_backup" ]]; then
        log_warning "Volumes backup directory not found: $volumes_backup"
        return 1
    fi
    
    local volumes=("postgres_data" "redis_data" "rabbitmq_data" "minio_data")
    
    for volume in "${volumes[@]}"; do
        local volume_backup="${volumes_backup}/${volume}.tar.gz"
        
        if [[ ! -f "$volume_backup" ]]; then
            log_warning "Volume backup not found: $volume_backup"
            continue
        fi
        
        log_info "  Restoring volume: $volume"
        
        # Remove existing volume
        docker volume rm "${STACK_NAME}_${volume}" 2>/dev/null || true
        
        # Create new volume and restore
        docker volume create "${STACK_NAME}_${volume}"
        
        docker run --rm \
            -v "${STACK_NAME}_${volume}:/target" \
            -v "$volumes_backup:/backup" \
            alpine tar xzf "/backup/${volume}.tar.gz" -C /target
        
        log_success "  Volume restored: $volume"
    done
}

# Main restore workflow
main() {
    log_info "Starting restore from backup: $BACKUP_NAME"
    log_info "Stack: $STACK_NAME"
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker command not found"
        exit 1
    fi
    
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker daemon not accessible"
        exit 1
    fi
    
    # Perform restores
    restore_postgres || log_warning "PostgreSQL restore failed"
    restore_redis || log_warning "Redis restore failed"
    restore_volumes || log_warning "Volume restore failed"
    
    log_success "Restore completed"
    log_info "Verify data and run health checks: ./deploy.sh health-check"
}

# Handle errors
trap 'log_error "Restore failed"; exit 1' ERR

main "$@"
