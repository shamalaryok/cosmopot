# Security Baseline Implementation

This document describes the implemented security baseline measures for the platform, including rate limiting, TLS encryption, database field encryption, GDPR compliance, and data retention policies.

## 1. Rate Limiting

### Global Rate Limiting

**Purpose**: Protect the API from brute force attacks and DDoS attempts.

**Configuration**:
- **Limit**: 100 requests per minute per IP address
- **Backend**: Redis-backed sliding window algorithm
- **Implementation**: FastAPI middleware (`RateLimitMiddleware`)

**Environment Variables**:
```bash
RATE_LIMIT__GLOBAL_REQUESTS_PER_MINUTE=100
RATE_LIMIT__WINDOW_SECONDS=60
```

**How It Works**:
1. Each request is identified by the client IP (respecting X-Forwarded-For header)
2. A Redis sorted set tracks request timestamps in a rolling window
3. If requests exceed the limit, a 429 (Too Many Requests) response is returned
4. The `Retry-After` header indicates when the client can retry

**Testing**:
```bash
# Run rate limiting tests
pytest apps/backend/tests/test_rate_limiting.py -v
```

### Generation-Specific Rate Limiting

**Purpose**: Limit resource-intensive operations per user.

**Configuration**:
- **Limit**: 10 requests per minute per user
- **Implementation**: Dependency injection pattern
- **Usage**: Applied to generation endpoints

**Environment Variables**:
```bash
RATE_LIMIT__GENERATION_REQUESTS_PER_MINUTE=10
```

## 2. TLS/SSL Encryption

### Development Environment

For development, self-signed certificates are used with TLS 1.3 support.

**Generate Self-Signed Certificates**:
```bash
# Generate certificates (valid for 365 days)
bash nginx/generate-certs.sh

# Certificates will be created at:
# - nginx/certs/server.crt
# - nginx/certs/server.key
```

**Nginx Configuration**:
- **HTTP Port**: 80 (redirects to HTTPS)
- **HTTPS Port**: 443 (TLS 1.3 with fallback to TLS 1.2)
- **Certificate Location**: `/etc/nginx/certs/server.crt`
- **Key Location**: `/etc/nginx/certs/server.key`

**Docker Compose Setup**:
```yaml
nginx:
  volumes:
    - ./nginx/certs:/etc/nginx/certs:ro  # Mount certificates
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
```

### Production Environment

For production deployment:

1. **Use Let's Encrypt**:
   ```bash
   # Use Certbot for automated certificate management
   certbot certonly --standalone -d yourdomain.com
   ```

2. **Update Nginx Configuration**:
   ```nginx
   ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
   ```

3. **Enable HSTS** (uncomment in nginx.conf):
   ```nginx
   add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
   ```

4. **Certificate Renewal**:
   - Let's Encrypt certificates expire after 90 days
   - Configure cron job for automatic renewal:
   ```bash
   0 12 * * * /usr/bin/certbot renew --quiet
   ```

## 3. Database Field Encryption

### Application-Layer Encryption

**Purpose**: Encrypt sensitive data at rest using Fernet (symmetric encryption).

**Supported Fields**:
- Email addresses
- Phone numbers
- Payment metadata
- Personal identification data

**Implementation**:
- **Algorithm**: Fernet (symmetric encryption using AES)
- **Key Format**: Base64-encoded 32-byte key
- **Module**: `backend.security.encryption.EncryptionManager`

**Configuration**:
```bash
# Generate a new encryption key
python -c "from backend.security.encryption import generate_encryption_key; print(generate_encryption_key())"

# Set environment variable
export ENCRYPTION__KEY="<base64-encoded-key>"
export ENCRYPTION__ENABLED=true
```

**Usage Example**:
```python
from backend.security import EncryptionManager
from backend.core.config import get_settings

settings = get_settings()
manager = EncryptionManager(settings.encryption.key)

# Encrypt
email = "user@example.com"
encrypted_email = manager.encrypt(email)

# Decrypt
decrypted_email = manager.decrypt(encrypted_email)
```

**Key Rotation**:
1. Generate a new encryption key
2. Create a migration to re-encrypt existing data with the new key
3. Update the `ENCRYPTION__KEY` environment variable
4. Deploy the migration

**Testing**:
```bash
# Run encryption tests
pytest apps/backend/tests/test_encryption.py -v
```

## 4. GDPR Compliance

### Data Export Endpoint

**Endpoint**: `POST /api/v1/users/me/data-export`

**Response**:
```json
{
  "status": "scheduled",
  "requested_at": "2024-01-01T12:00:00Z",
  "reference": "export-uuid",
  "note": "Your data export has been scheduled..."
}
```

**Behavior**:
- Exports user data to S3 in JSON format
- File path: `gdpr-exports/{user_id}/{timestamp}.json`
- User can download their data for portability

### Data Deletion Endpoint

**Endpoint**: `POST /api/v1/users/me/data-delete`

**Response**:
```json
{
  "status": "scheduled",
  "requested_at": "2024-01-01T12:00:00Z",
  "reference": "delete-uuid",
  "note": "Your account deletion has been scheduled..."
}
```

**Behavior**:
- Marks user account for deletion
- Hard deletion occurs after retention period (default: 90 days)
- Soft deletion allows for dispute/recovery within retention period

## 5. Data Retention and S3 Asset Purging

### Retention Policy

**Configuration**:
```bash
GDPR__INPUT_RETENTION_DAYS=7      # Purge input files after 7 days
GDPR__RESULT_RETENTION_DAYS=90    # Purge result files after 90 days
GDPR__PURGE_SCHEDULE="0 1 * * *"  # Daily at 1 AM UTC
```

### Scheduled Purging

**Celery Beat Task**: `app.tasks.purge_old_s3_assets`

**Schedule**:
- **Frequency**: Daily at 1:00 AM UTC
- **Retention**: 90 days (configurable)
- **Scope**: All S3 objects older than retention period

**Monitoring**:
```bash
# Check task execution in logs
docker logs <worker-container> | grep "s3_purge"
```

**Manual Execution**:
```python
from backend.security import GDPRDataExporter
from backend.core.config import get_settings

settings = get_settings()
exporter = GDPRDataExporter(settings)

# Purge assets older than 30 days
result = await exporter.purge_old_assets(older_than_days=30)
print(result)
```

**Testing**:
```bash
# Run GDPR tests
pytest apps/backend/tests/test_gdpr.py -v
```

## 6. Security Testing

### Unit Tests

**Rate Limiting**:
```bash
pytest apps/backend/tests/test_rate_limiting.py -v
```

**Encryption**:
```bash
pytest apps/backend/tests/test_encryption.py -v
```

**GDPR**:
```bash
pytest apps/backend/tests/test_gdpr.py -v
```

### Integration Tests

**Run all security tests**:
```bash
pytest apps/backend/tests/test_rate_limiting.py \
        apps/backend/tests/test_encryption.py \
        apps/backend/tests/test_gdpr.py -v --cov
```

## 7. Threat Model

### Identified Threats and Mitigations

| Threat | Impact | Mitigation |
|--------|--------|-----------|
| Brute Force Attacks | Account compromise | Global rate limiting (100 req/min per IP) |
| DDoS Attacks | Service unavailability | Rate limiting + Nginx protection |
| Data in Transit | Eavesdropping | TLS 1.3 encryption |
| Data at Rest | Unauthorized access | Application-layer encryption (Fernet/AES) |
| Unauthorized Data Access | GDPR violation | Encryption + access controls |
| Data Retention Violations | Legal liability | Automated purging policy (90 days) |
| Account Takeover | Identity theft | Session management + rate limiting |
| SQL Injection | Database compromise | Parameterized queries (SQLAlchemy) |

### Security Best Practices

1. **Environment Variables**:
   - Never commit secrets to version control
   - Use `.env.local` for local development (add to `.gitignore`)
   - Use secrets management in production (Vault, AWS Secrets Manager)

2. **Encryption Keys**:
   - Rotate keys periodically (recommend: annually)
   - Store in secure key management system
   - Use different keys per environment

3. **TLS Certificates**:
   - Use trusted CAs in production (Let's Encrypt recommended)
   - Enable certificate pinning for sensitive APIs
   - Monitor certificate expiration

4. **Rate Limiting**:
   - Monitor rate limit metrics
   - Adjust limits based on legitimate traffic patterns
   - Consider IP whitelisting for internal services

5. **Data Retention**:
   - Document retention policies
   - Ensure automatic purging is operational
   - Audit S3 bucket regularly

## 8. Operations Guide

### Monitoring

**Check Rate Limit Health**:
```bash
# Connect to Redis and inspect rate limit keys
redis-cli
> KEYS rate_limit:*
> TTL rate_limit:<identifier>
```

**Check Encryption Status**:
```bash
# Verify encryption is enabled
curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN"
```

**Check GDPR Tasks**:
```bash
# View Celery Beat schedule
celery -A backend.app.celery_app beat --loglevel=info

# Inspect task results
celery -A backend.app.celery_app events
```

### Troubleshooting

**Rate Limit Not Working**:
1. Verify Redis connectivity: `redis-cli ping`
2. Check rate limit configuration in `.env`
3. Ensure RateLimitMiddleware is registered in `app.py`

**Encryption Issues**:
1. Verify `ENCRYPTION__KEY` is set and valid
2. Check that key is Base64-encoded Fernet key
3. Ensure `ENCRYPTION__ENABLED=true`

**GDPR Purge Not Running**:
1. Check Celery Beat is running: `docker logs <beat-container>`
2. Verify S3 credentials
3. Check bucket permissions
4. Review logs: `docker logs <worker-container> | grep s3_purge`

## 9. References

- [Fernet Encryption](https://cryptography.io/en/latest/fernet/)
- [OWASP Rate Limiting](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Prevention_Cheat_Sheet.html)
- [GDPR Compliance](https://gdpr-info.eu/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Nginx TLS 1.3](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
