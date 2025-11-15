# Security Baseline - Quick Start Guide

This guide provides quick setup instructions for security features implemented in the platform.

## Prerequisites

- Docker and Docker Compose
- OpenSSL (for certificate generation)
- Python 3.11+

## 1. Quick Setup

### Generate Encryption Key

```bash
# Generate a new Fernet encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Output will look like:
# gAAAAABlXxQJ0-u8_8_v8_8_8_8_8_8_8_8_8_8_8_8=
```

Add to `.env.docker`:
```bash
ENCRYPTION__KEY=<generated-key>
```

### Generate TLS Certificates (Development)

```bash
# Generate self-signed certificates
bash nginx/generate-certs.sh

# Verify certificates exist
ls -la nginx/certs/
# -rw-r--r-- server.crt
# -rw------- server.key
```

### Start Docker Stack

```bash
# Build and start all services
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs
docker-compose logs backend    # FastAPI backend
docker-compose logs nginx      # Nginx with TLS
docker-compose logs worker     # Celery worker
```

## 2. Test Rate Limiting

```bash
# Test global rate limit (100 req/min per IP)
for i in {1..105}; do
  curl -i http://localhost:8080/api/v1/health
done

# After 100 requests, you should see:
# HTTP/1.1 429 Too Many Requests
# Retry-After: 60
```

## 3. Test Encryption

```bash
# Access the API with authentication
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}' | jq -r .access_token)

# Create user profile (uses encryption)
curl -X PATCH http://localhost:8080/api/v1/users/me/profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"John","phone_number":"+1234567890"}'

# Verify data is encrypted in database
docker exec devstack-postgres-1 psql -U devstack -d devstack \
  -c "SELECT id, phone_number FROM user_profiles LIMIT 1;"

# Should show encrypted value, not plaintext
```

## 4. Test GDPR Endpoints

### Data Export

```bash
curl -X POST http://localhost:8080/api/v1/users/me/data-export \
  -H "Authorization: Bearer $TOKEN"

# Response:
# {
#   "status": "scheduled",
#   "requested_at": "2024-01-01T12:00:00Z",
#   "reference": "export-uuid",
#   "note": "Your data export has been scheduled..."
# }
```

### Data Deletion

```bash
curl -X POST http://localhost:8080/api/v1/users/me/data-delete \
  -H "Authorization: Bearer $TOKEN"

# Response:
# {
#   "status": "scheduled",
#   "requested_at": "2024-01-01T12:00:00Z",
#   "reference": "delete-uuid",
#   "note": "Your account deletion has been scheduled..."
# }
```

## 5. Test S3 Asset Purging

### Manual Purge Task

```bash
# Run purge task manually
docker exec devstack-worker-1 celery -A app.tasks call app.tasks.purge_old_s3_assets

# Check task result
docker logs devstack-worker-1 | grep s3_purge_task_completed
```

### Verify Scheduled Task

```bash
# Check Celery Beat schedule
docker exec devstack-worker-1 celery -A app.celery_app beat --loglevel=info &

# Watch for scheduled execution at 1 AM UTC daily
docker logs -f devstack-worker-1 | grep "purge-old-s3-assets"
```

## 6. Verify TLS 1.3

```bash
# Check TLS protocol used
openssl s_client -connect localhost:443 -tls1_3 < /dev/null

# Should show:
# Protocol: TLSv1.3
# Cipher: TLS_AES_256_GCM_SHA384
```

## 7. Run Security Tests

### Rate Limiting Tests

```bash
pytest apps/backend/tests/test_rate_limiting.py -v
```

### Encryption Tests

```bash
pytest apps/backend/tests/test_encryption.py -v
```

### GDPR Tests

```bash
pytest apps/backend/tests/test_gdpr.py -v
```

### All Security Tests

```bash
pytest apps/backend/tests/test_rate_limiting.py \
        apps/backend/tests/test_encryption.py \
        apps/backend/tests/test_gdpr.py -v --cov
```

## 8. Configuration Reference

### Environment Variables

```bash
# Rate Limiting
RATE_LIMIT__GLOBAL_REQUESTS_PER_MINUTE=100
RATE_LIMIT__GENERATION_REQUESTS_PER_MINUTE=10
RATE_LIMIT__WINDOW_SECONDS=60

# Encryption
ENCRYPTION__KEY=<fernet-key>
ENCRYPTION__ENABLED=true

# GDPR & Data Retention
GDPR__INPUT_RETENTION_DAYS=7
GDPR__RESULT_RETENTION_DAYS=90
GDPR__PURGE_SCHEDULE=0 1 * * *  # Daily at 1 AM UTC

# Redis (for rate limiting backend)
REDIS_URL=redis://redis:6379/0

# S3 (for data export/purge)
S3__BUCKET=generation-inputs
S3__REGION=us-east-1
S3__ENDPOINT_URL=http://minio:9000
S3__ACCESS_KEY_ID=devstack
S3__SECRET_ACCESS_KEY=devstacksecret
```

## 9. Troubleshooting

### Rate Limiting Not Working

```bash
# Check Redis connection
redis-cli -h redis ping

# Check rate limit keys in Redis
redis-cli -h redis KEYS "rate_limit:*"

# Flush rate limits (for testing)
redis-cli -h redis FLUSHDB
```

### Encryption Issues

```bash
# Verify encryption key format
python3 -c "from cryptography.fernet import Fernet; Fernet('your-key-here')"

# Check if encryption is enabled
docker logs devstack-backend-1 | grep -i encryption
```

### TLS Certificate Issues

```bash
# Verify certificate validity
openssl x509 -in nginx/certs/server.crt -text -noout

# Check certificate expiration
openssl x509 -in nginx/certs/server.crt -noout -dates

# Regenerate certificates if expired
bash nginx/generate-certs.sh
docker-compose restart nginx
```

### GDPR Purge Not Running

```bash
# Check if Celery Beat is running
docker exec devstack-worker-1 ps aux | grep beat

# View scheduled tasks
docker exec devstack-worker-1 celery -A app.celery_app inspect scheduled

# Check task history
docker exec devstack-worker-1 celery -A app.celery_app inspect active
```

## 10. Production Checklist

- [ ] Update `ENCRYPTION__KEY` with production-grade key
- [ ] Replace self-signed certificates with Let's Encrypt or trusted CA
- [ ] Enable HSTS header in nginx.conf
- [ ] Configure certificate auto-renewal
- [ ] Set appropriate rate limits based on traffic patterns
- [ ] Monitor Redis connection health
- [ ] Configure S3 bucket versioning and lifecycle policies
- [ ] Set up log aggregation for security events
- [ ] Enable API authentication/authorization
- [ ] Configure backup strategy for encrypted data
- [ ] Document incident response procedures

## 11. Support Resources

- [Security Baseline Documentation](./SECURITY_BASELINE.md)
- [Cryptography Library](https://cryptography.io/)
- [OWASP Rate Limiting](https://cheatsheetseries.owasp.org/)
- [GDPR Compliance](https://gdpr-info.eu/)
- [Nginx TLS Configuration](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
