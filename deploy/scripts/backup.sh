#!/bin/bash
set -euo pipefail

# Production Backup Script for Docker Swarm Stack
# Backs up databases, configs, and sensitive data

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
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_${BACKUP_DATE}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPRESS_BACKUP="${COMPRESS_BACKUP:-true}"
ENCRYPT_BACKUP="${ENCRYPT_BACKUP:-false}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-}"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Get database container
get_postgres_container() {
    docker ps --filter "label=service=postgres" -q | head -1
}

# Get Redis container
get_redis_container() {
    docker ps --filter "label=service=redis" -q | head -1
}

# Backup PostgreSQL
backup_postgres() {
    local db_container=$(get_postgres_container)
    
    if [[ -z "$db_container" ]]; then
        log_error "PostgreSQL container not found"
        return 1
    fi
    
    log_info "Backing up PostgreSQL..."
    
    local db_backup="${BACKUP_PATH}/postgres_dump.sql"
    mkdir -p "$(dirname "$db_backup")"
    
    docker exec "$db_container" pg_dump \
        -U postgres \
        --format=plain \
        --verbose \
        prodstack > "$db_backup"
    
    local size=$(du -h "$db_backup" | cut -f1)
    log_success "PostgreSQL backup completed: $size"
}

# Backup Redis
backup_redis() {
    local redis_container=$(get_redis_container)
    
    if [[ -z "$redis_container" ]]; then
        log_warning "Redis container not found"
        return 1
    fi
    
    log_info "Backing up Redis..."
    
    local redis_backup="${BACKUP_PATH}/redis_dump.rdb"
    mkdir -p "$(dirname "$redis_backup")"
    
    docker exec "$redis_container" redis-cli BGSAVE
    sleep 2
    
    docker cp "$redis_container:/data/dump.rdb" "$redis_backup"
    
    local size=$(du -h "$redis_backup" | cut -f1)
    log_success "Redis backup completed: $size"
}

# Backup application configs and secrets metadata
backup_configs() {
    log_info "Backing up configs and secrets metadata..."
    
    local configs_backup="${BACKUP_PATH}/configs"
    mkdir -p "$configs_backup"
    
    # Export secrets list (not the actual values for security)
    docker secret ls --format "table {{.Name}}\t{{.Version}}" > "$configs_backup/secrets_list.txt"
    
    # Export configs
    docker config ls --format "table {{.Name}}\t{{.Version}}" > "$configs_backup/configs_list.txt"
    
    # Export stack compose file reference
    cp "${BACKUP_PATH%/*}/../docker-compose.prod.yml" "$configs_backup/" 2>/dev/null || true
    
    log_success "Configs backup completed"
}

# Backup application volumes
backup_volumes() {
    log_info "Backing up application volumes..."
    
    local volumes_backup="${BACKUP_PATH}/volumes"
    mkdir -p "$volumes_backup"
    
    # Create tar of each volume
    local volumes=("postgres_data" "redis_data" "rabbitmq_data" "minio_data")
    
    for volume in "${volumes[@]}"; do
        if docker volume inspect "${STACK_NAME}_${volume}" > /dev/null 2>&1; then
            log_info "  Backing up volume: $volume"
            
            docker run --rm \
                -v "${STACK_NAME}_${volume}:/source:ro" \
                -v "$volumes_backup:/backup" \
                alpine tar czf "/backup/${volume}.tar.gz" -C /source .
            
            local size=$(du -h "$volumes_backup/${volume}.tar.gz" | cut -f1)
            log_success "  Volume backed up: $volume ($size)"
        else
            log_warning "  Volume not found: $volume"
        fi
    done
}

# Compress backup
compress_backup() {
    if [[ "$COMPRESS_BACKUP" != "true" ]]; then
        return
    fi
    
    log_info "Compressing backup..."
    
    local backup_tar="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    tar -czf "$backup_tar" -C "$BACKUP_DIR" "$BACKUP_NAME"
    
    local original_size=$(du -sh "$BACKUP_PATH" | cut -f1)
    local compressed_size=$(du -h "$backup_tar" | cut -f1)
    
    log_success "Backup compressed: $original_size -> $compressed_size"
    
    # Remove uncompressed directory
    rm -rf "$BACKUP_PATH"
}

# Encrypt backup
encrypt_backup() {
    if [[ "$ENCRYPT_BACKUP" != "true" ]] || [[ -z "$ENCRYPTION_KEY" ]]; then
        return
    fi
    
    log_info "Encrypting backup..."
    
    local backup_tar="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    local backup_enc="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz.enc"
    
    if ! command -v openssl &> /dev/null; then
        log_error "openssl not found, skipping encryption"
        return 1
    fi
    
    openssl enc -aes-256-cbc -salt -in "$backup_tar" -out "$backup_enc" -k "$ENCRYPTION_KEY"
    
    local size=$(du -h "$backup_enc" | cut -f1)
    log_success "Backup encrypted: $size"
    
    rm -f "$backup_tar"
}

# Upload to S3 (optional)
upload_to_s3() {
    local s3_path="${S3_BACKUP_PATH:-}"
    
    if [[ -z "$s3_path" ]]; then
        return
    fi
    
    if ! command -v aws &> /dev/null; then
        log_warning "AWS CLI not found, skipping S3 upload"
        return 1
    fi
    
    log_info "Uploading backup to S3: $s3_path"
    
    local backup_file="${BACKUP_DIR}/${BACKUP_NAME}"
    [[ "$COMPRESS_BACKUP" == "true" ]] && backup_file="${backup_file}.tar.gz"
    [[ "$ENCRYPT_BACKUP" == "true" ]] && backup_file="${backup_file}.enc"
    
    aws s3 cp "$backup_file" "${s3_path}/" --storage-class GLACIER
    
    log_success "Backup uploaded to S3"
}

# Cleanup old backups
cleanup_old_backups() {
    log_info "Cleaning up backups older than $RETENTION_DAYS days..."
    
    find "$BACKUP_DIR" -maxdepth 1 -name "backup_*" -mtime +${RETENTION_DAYS} -delete
    
    log_success "Cleanup completed"
}

# Generate backup report
generate_report() {
    local report_file="${BACKUP_DIR}/backup_report_${BACKUP_DATE}.txt"
    
    cat > "$report_file" << EOF
Backup Report
=============
Date: $(date)
Stack: $STACK_NAME
Backup Name: $BACKUP_NAME
Retention: $RETENTION_DAYS days

Backup Contents:
- PostgreSQL dump
- Redis dump
- Application volumes
- Configs and secrets metadata

Backup Location: $BACKUP_PATH
Compression: $COMPRESS_BACKUP
Encryption: $ENCRYPT_BACKUP

Total Size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

EOF
    
    log_success "Report generated: $report_file"
}

# Main backup workflow
main() {
    log_info "Starting backup for stack: $STACK_NAME"
    log_info "Backup directory: $BACKUP_DIR"
    
    mkdir -p "$BACKUP_PATH"
    
    # Perform backups
    backup_postgres || log_warning "PostgreSQL backup failed"
    backup_redis || log_warning "Redis backup failed"
    backup_configs || log_warning "Config backup failed"
    backup_volumes || log_warning "Volume backup failed"
    
    # Post-processing
    compress_backup
    encrypt_backup
    upload_to_s3
    cleanup_old_backups
    generate_report
    
    log_success "Backup completed successfully"
}

# Handle errors
trap 'log_error "Backup failed"; exit 1' ERR

main "$@"
