# Backup & Restore Procedures

Comprehensive guide for backing up and restoring the production Docker Swarm stack.

## Table of Contents

1. [Overview](#overview)
2. [Backup Strategy](#backup-strategy)
3. [Backup Procedures](#backup-procedures)
4. [Restore Procedures](#restore-procedures)
5. [Verification](#verification)
6. [Disaster Recovery](#disaster-recovery)
7. [Automation](#automation)

---

## Overview

### What We Backup

| Component | Type | Frequency | Retention | Location |
|-----------|------|-----------|-----------|----------|
| PostgreSQL | Database Dump | Daily @ 2 AM | 30 days | /backups/ |
| Redis | RDB Snapshot | Daily @ 2 AM | 30 days | /backups/ |
| Volumes | Tar Archive | Daily @ 2 AM | 30 days | /backups/ |
| Configs | Version Control | On change | ∞ | Git |
| Secrets | Metadata | On change | ∞ | Secure Store |

### Backup Characteristics

- **Incremental:** Only changed data backed up (via storage)
- **Compressed:** Gzip compression reduces size by ~70%
- **Encrypted:** Optional AES-256 encryption for sensitive data
- **Offsite:** S3/remote storage for disaster recovery
- **Verified:** Checksums and restoration tests

---

## Backup Strategy

### Recovery Time Objective (RTO)

- **Acceptable downtime:** 1-4 hours
- **Data loss acceptable:** < 1 hour (last backup to failure)

### Backup Points

**Tier 1: Point-in-Time (Database)**
- Frequency: Every 4 hours
- Retention: 7 days
- Purpose: Recover from data corruption

**Tier 2: Daily (Full Stack)**
- Frequency: Daily @ 2 AM (off-peak)
- Retention: 30 days
- Purpose: Major recovery scenarios

**Tier 3: Offsite (Archive)**
- Frequency: Weekly → S3 Glacier
- Retention: 1 year
- Purpose: Disaster recovery

### Storage

```
/backups/
├── backup_20240101_020000/          # Daily full backup
│   ├── postgres_dump.sql            # ~500MB
│   ├── redis_dump.rdb               # ~100MB
│   ├── volumes/
│   │   ├── postgres_data.tar.gz     # ~2GB
│   │   ├── redis_data.tar.gz        # ~1GB
│   │   └── minio_data.tar.gz        # ~10GB
│   └── configs/
│       ├── secrets_list.txt
│       ├── configs_list.txt
│       └── docker-compose.prod.yml
├── backup_20240101_020000.tar.gz    # Compressed
├── backup_20240101_020000.tar.gz.enc # Encrypted
└── backup_report_20240101_020000.txt
```

---

## Backup Procedures

### Manual Backup

**Full backup (all components):**

```bash
./deploy/scripts/backup.sh
```

**Backup specific components:**

```bash
# PostgreSQL only
SKIP_REDIS=true SKIP_VOLUMES=true ./deploy/scripts/backup.sh

# Database + Volumes (skip configs)
./deploy/scripts/backup.sh
```

**With encryption:**

```bash
ENCRYPT_BACKUP=true \
ENCRYPTION_KEY="your-256-bit-key" \
./deploy/scripts/backup.sh
```

**Upload to S3:**

```bash
S3_BACKUP_PATH=s3://company-backups/prodstack \
./deploy/scripts/backup.sh
```

### Database Point-in-Time Recovery

For granular recovery:

```bash
# PostgreSQL WAL archiving setup
docker exec <postgres-container> psql -U postgres <<EOF
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET archive_mode = 'on';
ALTER SYSTEM SET archive_command = 'test ! -f /pg_wal_archive/%f && cp %p /pg_wal_archive/%f';
SELECT pg_reload_conf();
EOF

# Backup WAL files
tar -czf /backups/postgres_wal.tar.gz /pg_wal_archive/

# Enables recovery to any specific timestamp
```

### Volume-Level Backups

For MaxIO and critical data:

```bash
# Snapshot volumes at filesystem level
docker exec -u root <postgres> \
  lvcreate -L5G -s -n postgres_snapshot /dev/vg0/postgres_data

# Mount and backup
mkdir -p /mnt/snapshot
mount /dev/vg0/postgres_snapshot /mnt/snapshot
tar -czf /backups/postgres_snapshot.tar.gz /mnt/snapshot

# Unmount and cleanup
umount /mnt/snapshot
lvremove -f /dev/vg0/postgres_snapshot
```

### Pre-Backup Verification

```bash
# Check all services healthy
./deploy/scripts/deploy.sh health-check

# Check disk space available
df -h /backups

# Check connectivity to backup destination
aws s3 ls s3://backups/prodstack 2>/dev/null || echo "S3 unreachable"
```

### Scheduled Backups (Cron)

```bash
# Edit crontab
crontab -e

# Add backup job
# Daily full backup at 2 AM
0 2 * * * cd /home/deploy && ./scripts/backup.sh > logs/backup.log 2>&1

# Weekly S3 upload at 3 AM Sunday
0 3 * * 0 cd /home/deploy && \
  S3_BACKUP_PATH=s3://backups/prodstack \
  ./scripts/backup.sh >> logs/backup.log 2>&1

# Verify cron jobs
crontab -l
```

### Monitoring Backups

```bash
# Check last backup
ls -lh /backups/backup_* | head -1

# Verify backup integrity
tar -tzf /backups/backup_*.tar.gz > /dev/null && echo "OK" || echo "CORRUPTED"

# Monitor backup job
tail -f logs/backup.log
```

---

## Restore Procedures

### Before Restoring

**Critical checks:**

```bash
# 1. Identify correct backup
ls -lh /backups/backup_*
# Choose appropriate backup point

# 2. Verify backup integrity
tar -tzf /backups/backup_*.tar.gz | head -20

# 3. Check current data is safe
./deploy/scripts/backup.sh  # Create latest backup

# 4. Notify stakeholders
echo "Starting restore from backup_20240101_020000 - expect 30min downtime"
```

### Full Stack Restore

**Restore everything:**

```bash
# 1. Restore from backup (non-interactive)
./deploy/scripts/restore.sh backup_20240101_020000 --no-confirm

# 2. Verify services restarting
docker stack ps prodstack

# 3. Run health checks
./deploy/scripts/deploy.sh health-check

# 4. Spot-check data
curl https://prod-cluster/api/v1/health
```

### Selective Restore

**Restore only database:**

```bash
./deploy/scripts/restore.sh backup_20240101_020000 --skip-redis --skip-volumes
```

**Restore only volumes:**

```bash
./deploy/scripts/restore.sh backup_20240101_020000 --skip-postgres --skip-redis
```

**Restore only cache:**

```bash
./deploy/scripts/restore.sh backup_20240101_020000 --skip-postgres --skip-volumes
```

### Point-in-Time Recovery (PostgreSQL)

For precise timestamp recovery:

```bash
# 1. Restore base backup
./deploy/scripts/restore.sh backup_20240101_020000 --skip-redis --skip-volumes

# 2. Restore WAL files
cd /pg_wal_archive
tar -xzf /backups/postgres_wal.tar.gz

# 3. Start PostgreSQL in recovery mode
docker exec postgres psql -U postgres <<EOF
SELECT pg_start_backup('point-in-time-recovery', true);
-- Copy WAL files to archive_status
-- (handled by PostgreSQL recovery process)
SELECT pg_stop_backup(false);
EOF

# 4. Restore to specific point
docker exec postgres psql -U postgres <<EOF
ALTER SYSTEM SET recovery_target_timeline = 'latest';
ALTER SYSTEM SET recovery_target_xid = '12345678';  -- or timestamp
SELECT pg_reload_conf();
EOF

docker restart <postgres>

# 5. Verify
docker exec postgres psql -U postgres -d prodstack -c "SELECT count(*) FROM users;"
```

### Encrypted Backup Restore

For encrypted backups:

```bash
# 1. Provide encryption key
export ENCRYPTION_KEY="your-256-bit-key"

# 2. Restore (auto-decrypts)
./deploy/scripts/restore.sh backup_20240101_020000.tar.gz.enc --no-confirm

# 3. Verify
docker stack ps prodstack
```

### Remote Backup Restore

From S3:

```bash
# 1. Download backup
aws s3 cp s3://backups/prodstack/backup_20240101_020000.tar.gz /backups/

# 2. Restore
./deploy/scripts/restore.sh backup_20240101_020000 --no-confirm

# 3. Cleanup
rm /backups/backup_20240101_020000.tar.gz
```

---

## Verification

### Post-Restore Checks

**Automated verification:**

```bash
# 1. Health check
./deploy/scripts/deploy.sh health-check

# 2. Database connectivity
docker exec postgres psql -U postgres -d prodstack -c "SELECT count(*) FROM users;" | grep -E '[0-9]+'

# 3. API functionality
curl -s https://prod-cluster/api/v1/health | jq .

# 4. Task processing
docker exec rabbitmq rabbitmq-diagnostics -q queues | head -5

# 5. Cache access
docker exec redis redis-cli ping | grep -i pong
```

**Manual verification:**

```bash
# 1. Login to application
# Verify user accounts present

# 2. Check recent data
# Confirm last expected records exist

# 3. Test critical workflows
# Generate new content
# Process tasks
# Query analytics

# 4. Monitor for errors
./deploy/scripts/deploy.sh logs backend | grep -i error
```

### Backup Test Restore

**Monthly restore test (non-production):**

```bash
# 1. Create test environment
docker-compose -f docker-compose.test.yml up -d

# 2. Restore backup to test
./deploy/scripts/restore.sh backup_20240101_020000 --no-confirm

# 3. Run comprehensive tests
pytest tests/integration/

# 4. Document results
echo "Restore test completed - all checks passed" >> BACKUP_LOG.md

# 5. Cleanup
docker-compose -f docker-compose.test.yml down -v
```

### Data Integrity Checks

```bash
# Check for corruption
docker exec postgres pg_dump -U postgres prodstack | \
  pg_restore --analyze | grep -i error

# Check foreign keys
docker exec postgres psql -U postgres prodstack <<EOF
SELECT constraint_name FROM information_schema.table_constraints 
WHERE constraint_type = 'FOREIGN KEY';
EOF

# Check sequences
docker exec postgres psql -U postgres prodstack -c "\ds"
```

---

## Disaster Recovery

### Scenarios

#### 1. Data Corruption

```bash
# Issue: Users report corrupted data
# Impact: Database integrity compromised
# RTO: 4 hours

# Steps:
1. Identify corruption point (when did it start?)
2. Find last good backup before corruption
3. Restore: ./deploy/scripts/restore.sh backup_<date>
4. Run integrity checks
5. Notify users of data recovery
```

#### 2. Ransomware / Data Loss

```bash
# Issue: All data encrypted or deleted
# Impact: Complete data loss
# RTO: 4 hours

# Steps:
1. Isolate infrastructure (disconnect network if needed)
2. Access offsite backup (S3 Glacier)
3. Download to recovery environment
4. Restore: ./deploy/scripts/restore.sh backup_<date>
5. Verify no malware in recovery environment
6. Resume operations on fresh infrastructure
```

#### 3. Service Outage (Hard Failure)

```bash
# Issue: Services won't start, containers crash
# Impact: Complete downtime
# RTO: 1 hour

# Steps:
1. Stop all services: docker stack rm prodstack
2. Check logs for errors
3. If unrecoverable, restore latest backup
4. Redeploy stack
5. Verify functionality
```

#### 4. Entire Cluster Loss

```bash
# Issue: All nodes lost (hardware failure, datacenter down)
# Impact: Complete system loss
# RTO: 2-4 hours

# Steps:
1. Provision new infrastructure
2. Initialize Docker Swarm on new nodes
3. Download offsite backup
4. Restore to new cluster
5. Update DNS/load balancer to new cluster
6. Verify all systems operational
```

### Recovery Priority

```
1. PostgreSQL (critical business data)
2. Redis (cache - can rebuild if needed)
3. Volumes (attachments, logs)
4. RabbitMQ (queue state - loses messages, OK)
5. MinIO (object storage - can rebuild)
```

### Communication Plan

During recovery:

```
T+0min:   - Issue identified and acknowledged internally
T+5min:   - Status page updated: "Investigating"
T+15min:  - Customers notified via email/Slack
T+30min:  - Recovery started, ETA communicated
T+120min: - "Restoring from backup" status update
T+180min: - Services coming online, partial functionality
T+240min: - Full recovery, detailed postmortem starts
```

---

## Automation

### CI/CD Integration

```yaml
# .github/workflows/backup.yml
name: Daily Backup
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run backup
        run: ./deploy/scripts/backup.sh
        env:
          BACKUP_DIR: /mnt/backups
          S3_BACKUP_PATH: s3://backups/prodstack
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_KEY }}
      
      - name: Verify backup
        run: |
          tar -tzf /mnt/backups/backup_*.tar.gz > /dev/null || exit 1
          echo "Backup verified"
      
      - name: Notify on failure
        if: failure()
        run: |
          curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
            -d '{"text":"Backup failed!"}'
```

### Backup Status Monitoring

```bash
#!/bin/bash
# monitor_backups.sh - Check backup health

BACKUP_DIR="/backups"
WARN_AGE=25  # hours
ALERT_AGE=30 # hours

latest_backup=$(ls -t $BACKUP_DIR/backup_* 2>/dev/null | head -1)

if [[ -z "$latest_backup" ]]; then
  echo "CRITICAL: No backups found"
  exit 2
fi

age_hours=$(($(date +%s) - $(date -r "$latest_backup" +%s)) / 3600)

if (( age_hours > ALERT_AGE )); then
  echo "CRITICAL: Backup is $age_hours hours old"
  exit 2
elif (( age_hours > WARN_AGE )); then
  echo "WARNING: Backup is $age_hours hours old"
  exit 1
else
  echo "OK: Latest backup is $age_hours hours old"
  exit 0
fi
```

### Restore Testing Automation

```bash
#!/bin/bash
# test_restore.yml - Monthly restore drill

0 3 1 * *  # First day of month at 3 AM

# 1. Pull latest backup
backup=$(ls -t /backups/backup_*.tar.gz | head -1)

# 2. Create test environment
docker-compose -f docker-compose.test.yml up -d

# 3. Perform restore
./deploy/scripts/restore.sh $(basename $backup .tar.gz) --no-confirm

# 4. Run tests
pytest tests/integration/ -v

# 5. Report results
if [ $? -eq 0 ]; then
  echo "Restore test PASSED" | mail -s "Monthly Backup Test OK" ops@company.com
else
  echo "Restore test FAILED" | mail -s "Monthly Backup Test FAILED" ops@company.com
fi

# 6. Cleanup
docker-compose -f docker-compose.test.yml down -v
```

---

## Related Documentation

- [Deployment Runbook](./DEPLOYMENT_RUNBOOK.md)
- [Disaster Recovery Plan](./DISASTER_RECOVERY_PLAN.md)
- [Troubleshooting Guide](./TROUBLESHOOTING_GUIDE.md)
