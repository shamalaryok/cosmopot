# Security Operations Guide

This guide provides operational procedures for maintaining security baselines in production environments.

## 1. Rate Limiting Operations

### Monitoring Rate Limits

```bash
# Connect to Redis and check rate limit statistics
redis-cli

# View all rate limit keys
> KEYS rate_limit:*

# Check how many requests from a specific IP
> ZCARD rate_limit:192.168.1.100

# View request timestamps
> ZRANGE rate_limit:192.168.1.100 0 -1 WITHSCORES

# Cleanup old entries
> DEL rate_limit:192.168.1.100
```

### Adjusting Rate Limits

1. **Update Environment Variable**:
   ```bash
   # Edit your deployment configuration
   RATE_LIMIT__GLOBAL_REQUESTS_PER_MINUTE=200
   RATE_LIMIT__GENERATION_REQUESTS_PER_MINUTE=20
   ```

2. **Redeploy Backend**:
   ```bash
   # Docker Compose
   docker-compose restart backend

   # Kubernetes
   kubectl set env deployment/backend RATE_LIMIT__GLOBAL_REQUESTS_PER_MINUTE=200
   kubectl rollout status deployment/backend
   ```

3. **Verify Changes**:
   ```bash
   # Check logs for rate limit configuration
   docker logs backend | grep RATE_LIMIT
   ```

### Whitelisting IPs (Optional)

For internal services or trusted IPs, consider adding to the rate limiter:

```python
# apps/backend/src/backend/security/rate_limit.py
TRUSTED_IPS = {
    "10.0.0.0/8",      # Internal network
    "203.0.113.0/24",  # Partner API
}
```

## 2. TLS/SSL Certificate Management

### Certificate Renewal

**For Let's Encrypt (Production)**:

```bash
# Automatic renewal via cron (recommended)
# Add to /etc/crontab (runs twice daily)
0 3,15 * * * /usr/bin/certbot renew --quiet --post-hook "systemctl reload nginx"

# Manual renewal if needed
certbot certonly --standalone -d yourdomain.com --renew

# Verify certificate
certbot certificates
```

**For Self-Signed (Development)**:

```bash
# Regenerate self-signed certificate
bash nginx/generate-certs.sh

# Verify certificate details
openssl x509 -in nginx/certs/server.crt -text -noout

# Check expiration date
openssl x509 -in nginx/certs/server.crt -noout -dates
```

### Certificate Deployment

```bash
# After updating certificates, reload Nginx
docker exec nginx nginx -s reload

# Or for Kubernetes
kubectl rollout restart deployment/nginx
kubectl rollout status deployment/nginx

# Verify TLS is working
openssl s_client -connect yourdomain.com:443 -tls1_3
```

### Monitoring Certificate Expiration

```bash
# Create a monitoring script (monitor_certs.sh)
#!/bin/bash

CERT_FILE="/path/to/cert.crt"
EXPIRY=$(openssl x509 -in $CERT_FILE -noout -dates | grep notAfter)
DAYS_LEFT=$(( ($(date -d "${EXPIRY#*=}" +%s) - $(date +%s)) / 86400 ))

if [ $DAYS_LEFT -lt 30 ]; then
    # Alert: Certificate expiring soon
    echo "WARNING: Certificate expires in $DAYS_LEFT days"
    # Send alert to monitoring system
fi
```

## 3. Encryption Key Management

### Key Rotation Procedure

**Phase 1: Prepare New Key**

```bash
# Generate new encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Store securely in key management system (Vault, AWS Secrets Manager, etc.)
# Never commit to version control
```

**Phase 2: Create Migration**

```python
# migrations/versions/xxx_rotate_encryption_key.py
from alembic import op
from backend.security import EncryptionManager
from backend.core.config import get_settings

def upgrade():
    """Re-encrypt data with new key."""
    settings = get_settings()
    old_manager = EncryptionManager(settings.encryption.key)
    new_manager = EncryptionManager(new_key)  # New key from config
    
    # Iterate through encrypted fields and re-encrypt
    # This is database-specific implementation
    pass

def downgrade():
    # Reverse rotation if needed
    pass
```

**Phase 3: Deploy and Rotate**

```bash
# 1. Deploy migration
alembic upgrade head

# 2. Update environment variable with new key
# Wait for all services to pick up new config

# 3. Verify encryption is working
curl http://api/v1/users/me -H "Authorization: Bearer $TOKEN"

# 4. Monitor for errors
docker logs backend | grep -i encrypt
```

**Phase 4: Archive Old Key**

```bash
# Store old key securely for emergency recovery
# Never discard - may need for forensics or recovery
echo "$OLD_KEY" > /secure/backup/encryption_key_$(date +%Y%m%d)
chmod 600 /secure/backup/encryption_key_*
```

### Encryption Verification

```bash
# Check that encryption is enabled
curl http://api/v1/health -s | grep -i security

# Verify encrypted fields are not plaintext
docker exec postgres psql -U postgres -d backend \
  -c "SELECT phone_number FROM user_profiles LIMIT 1 WHERE phone_number IS NOT NULL;"

# Result should start with 'gAAAAAB' (Fernet format), not digits
```

## 4. GDPR and Data Retention Operations

### Monitoring Data Export

```bash
# Check S3 for exported data
aws s3 ls s3://your-bucket/gdpr-exports/ --recursive

# Count exported datasets
aws s3 ls s3://your-bucket/gdpr-exports/ --recursive | wc -l

# Check size of exports
aws s3 ls s3://your-bucket/gdpr-exports/ --recursive --summarize
```

### Monitoring S3 Purge Task

```bash
# Check task execution in Celery
celery -A backend.app.celery_app inspect active

# View task history
celery -A backend.app.celery_app inspect history

# Check logs for purge execution
docker logs worker | grep "s3_purge"

# Example log output:
# 2024-01-01 01:00:05 INFO s3_purge_started cutoff_time=2023-10-03...
# 2024-01-01 01:00:15 INFO s3_purge_completed deleted_count=1234...
```

### Manual Data Purge

```bash
# Purge assets older than 90 days
python3 << 'EOF'
import asyncio
from backend.security import GDPRDataExporter
from backend.core.config import get_settings

async def purge():
    settings = get_settings()
    exporter = GDPRDataExporter(settings)
    result = await exporter.purge_old_assets(90)
    print(f"Deleted {result['deleted_count']} objects")

asyncio.run(purge())
EOF
```

### Compliance Verification

```bash
# Verify purge policy is working
# 1. List files older than retention period
aws s3api list-objects-v2 --bucket your-bucket \
  --query 'Contents[?LastModified<`2023-10-01`]' --output table

# 2. After purge task, verify they're gone
# The above query should return no results

# 3. Generate compliance report
aws s3api list-objects-v2 --bucket your-bucket --query 'Contents[].LastModified' \
  | jq 'map(split("T")[0]) | group_by(.) | map({date: .[0], count: length})'
```

## 5. Security Incident Response

### Rate Limit Attack Response

```bash
# 1. Identify attacking IP
docker logs backend | grep "rate_limit_exceeded" | head -20

# 2. Check intensity
redis-cli -c "KEYS rate_limit:* | XREAD" | sort | uniq -c | sort -rn

# 3. Immediate mitigation options:

# Option A: Block IP at Nginx
# Add to nginx/nginx.conf:
# deny 192.168.1.100;

# Option B: Temporarily increase rate limit
RATE_LIMIT__GLOBAL_REQUESTS_PER_MINUTE=500

# Option C: Enable WAF/DDoS protection
# Configure at cloud provider (CloudFront, Cloudflare, etc.)

# 4. Restore normal limits after attack subsides
```

### Encryption Failure Response

```bash
# 1. Check error logs
docker logs backend | grep -i "encryption"

# 2. Common issues:
# - Invalid key format
# - Corrupted encrypted data
# - Missing ENCRYPTION__KEY environment variable

# 3. Recovery steps:
# a. Verify key is valid Fernet format
python3 -c "from cryptography.fernet import Fernet; Fernet('$ENCRYPTION_KEY')"

# b. If key is invalid, restore from backup
# (Make sure to have encrypted backups!)

# c. Check database for orphaned encrypted values
docker exec postgres psql -U postgres -d backend \
  -c "SELECT COUNT(*) FROM user_profiles WHERE phone_number IS NOT NULL;"

# d. Manual re-encryption if needed
# (Run migration script)
```

### Certificate Expiration Response

```bash
# 1. Check current certificate status
openssl x509 -in nginx/certs/server.crt -noout -dates

# 2. If expired:
# For production (Let's Encrypt):
certbot renew --force-renewal

# For development (self-signed):
bash nginx/generate-certs.sh

# 3. Reload Nginx
docker exec nginx nginx -s reload

# 4. Verify TLS is working
openssl s_client -connect localhost:443 -tls1_3 </dev/null
```

## 6. Regular Maintenance Schedule

### Daily
- [ ] Monitor rate limit anomalies
- [ ] Check for encryption errors in logs
- [ ] Verify certificate hasn't expired

### Weekly
- [ ] Review security logs
- [ ] Check S3 purge task execution
- [ ] Verify GDPR export requests are being processed

### Monthly
- [ ] Certificate renewal status check
- [ ] Encryption key access audit
- [ ] Rate limit configuration review
- [ ] Generate security compliance report

### Quarterly
- [ ] Security audit
- [ ] Penetration testing
- [ ] Update threat model
- [ ] Review incident logs

### Annually
- [ ] Full encryption key rotation (if not rolling)
- [ ] Certificate provider review
- [ ] Rate limiting policy review
- [ ] GDPR retention policy review
- [ ] Update security documentation

## 7. Backup and Recovery

### Backup Strategy

```bash
# Backup encryption keys (CRITICAL)
# Store in secure, offline location
openssl rand -base64 32 > /secure/backup/encryption_key_backup
chmod 600 /secure/backup/encryption_key_backup

# Backup database (includes encrypted fields)
pg_dump -U postgres backend > /backup/db_$(date +%Y%m%d).sql

# Backup SSL certificates
tar czf /backup/certs_$(date +%Y%m%d).tar.gz nginx/certs/
```

### Recovery Procedures

```bash
# 1. Restore encryption key
# Copy from secure backup to environment
export ENCRYPTION__KEY=$(cat /secure/backup/encryption_key_backup)

# 2. Restart services
docker-compose restart backend

# 3. Verify encrypted fields are accessible
curl http://api/v1/users/me -H "Authorization: Bearer $TOKEN"

# 4. Check for recovery errors
docker logs backend | grep -i "error\|failed"
```

## 8. Audit and Compliance

### Security Audit Checklist

- [ ] Rate limiting is enforced
- [ ] TLS 1.3 is enabled
- [ ] Encryption is working for sensitive fields
- [ ] GDPR endpoints are functional
- [ ] S3 purge task is running on schedule
- [ ] All errors are being logged
- [ ] Certificates are valid and not expiring soon
- [ ] Access logs are being retained
- [ ] Backup procedures are tested
- [ ] Incident response procedures are documented

### Compliance Reporting

```bash
# Generate monthly compliance report
cat << 'EOF' > compliance_report.py
import asyncio
from datetime import datetime, timedelta
from backend.security import GDPRDataExporter
from backend.core.config import get_settings

async def generate_report():
    settings = get_settings()
    
    report = {
        "date": datetime.now().isoformat(),
        "encryption": {
            "enabled": settings.encryption.enabled,
            "key_length": len(settings.encryption.key) if settings.encryption.key else 0,
        },
        "rate_limits": {
            "global": settings.rate_limit.global_requests_per_minute,
            "generation": settings.rate_limit.generation_requests_per_minute,
        },
        "gdpr": {
            "input_retention": settings.gdpr.input_retention_days,
            "result_retention": settings.gdpr.result_retention_days,
            "purge_schedule": settings.gdpr.purge_schedule,
        },
    }
    
    print(json.dumps(report, indent=2))

asyncio.run(generate_report())
EOF

python3 compliance_report.py
```

## 9. References and Support

- [Security Baseline Documentation](./SECURITY_BASELINE.md)
- [Security Quick Start](./SECURITY_QUICKSTART.md)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Cryptography Library](https://cryptography.io/en/latest/)
- [Celery Beat Scheduler](https://docs.celeryproject.io/en/stable/userguide/periodic-tasks.html)
- [OWASP Security Checklists](https://cheatsheetseries.owasp.org/)
