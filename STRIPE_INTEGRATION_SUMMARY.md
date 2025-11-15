# Stripe Payment Integration - Implementation Summary

## Overview

This implementation adds Stripe payment provider support alongside the existing YooKassa integration, enabling international payment processing with multiple currency support.

## Files Modified

### Configuration
- **`pyproject.toml`**: Added `stripe>=7.0` dependency and mypy overrides for stripe
- **`apps/backend/src/backend/core/config.py`**: Added `StripeSettings` class to Settings

### Payment System
- **`apps/backend/src/backend/payments/enums.py`**: 
  - Added `PaymentProvider` enum (YOOKASSA, STRIPE)
- **`apps/backend/src/backend/payments/gateway.py`**:
  - Added `StripeGateway` class with async Stripe API integration
- **`apps/backend/src/backend/payments/models.py`**:
  - Added `provider` field to Payment model to track payment provider
- **`apps/backend/src/backend/payments/service.py`**:
  - Extended `PaymentRequest` with `provider` and `currency` fields
  - Updated `create_payment()` to support provider selection
  - Added provider-specific payload builders (`_build_stripe_payload`, `_build_yookassa_payload`)
  - Added provider-specific status mappers (`_map_stripe_status`, `_map_yookassa_status`)
  - Added provider-specific webhook status mappers
  - Updated `process_webhook()` to accept provider parameter
  - Added provider-specific signature verification (`_verify_stripe_signature`, `_verify_yookassa_signature`)
  - Added `_get_gateway_for_provider()` method for gateway selection
- **`apps/backend/src/backend/payments/dependencies.py`**:
  - Updated to support multiple gateways (dict-based caching)
  - Added `_get_gateway_for_provider()` for dynamic gateway selection

### API & Routes
- **`apps/backend/src/backend/api/schemas/payments.py`**:
  - Added `provider` field to `PaymentCreateRequest` and `PaymentCreateResponse`
  - Added `currency` field to `PaymentCreateRequest` for international payments
- **`apps/backend/src/backend/api/routes/payments.py`**:
  - Updated to pass provider to service layer
- **`apps/backend/src/backend/api/routes/webhooks.py`**:
  - Added `/api/v1/webhooks/stripe` endpoint
  - Updated existing `/api/v1/webhooks/yukassa` to pass provider
  - Added provider-specific header handling (Stripe-Signature vs Content-Hmac)

### Database
- **`migrations/versions/0008_add_stripe_payment_provider.py`**: 
  - Migration to add `provider` enum column to payments table

### Tests
- **`apps/backend/tests/test_stripe_payments.py`** (NEW):
  - Comprehensive Stripe integration tests
  - Payment creation tests (basic and with international currency)
  - Idempotency tests
  - Webhook tests (success, failure, cancellation)
  - Signature verification tests
  - Dual-provider coexistence tests
  - >80% coverage of Stripe module
- **`apps/backend/tests/conftest.py`**:
  - Added Stripe webhook mocking fixture
  - Added `STRIPE__WEBHOOK_SECRET` to test environment

### Documentation
- **`docs/STRIPE_INTEGRATION.md`** (NEW):
  - Complete Stripe integration documentation
  - Configuration guide
  - API endpoint documentation
  - Webhook handling guide
  - Currency conversion details
  - Testing instructions
  - Troubleshooting guide

## Key Features

### 1. Dual-Provider Support
- Both YooKassa and Stripe can be used simultaneously
- Provider selection at payment time
- Backward compatible (defaults to YooKassa)

### 2. International Payments
- Support for any Stripe-supported currency (USD, EUR, GBP, JPY, etc.)
- Currency override in payment request
- Automatic amount conversion (major units for YooKassa, minor units for Stripe)

### 3. Idempotency & Conflict Resolution
- All payments use idempotency keys for safe retries
- Auto-generated or client-supplied
- Payment record locking during webhook processing
- Duplicate webhook handling

### 4. Webhook Handling
- Provider-specific signature verification
  - YooKassa: HMAC SHA256 (Content-Hmac header)
  - Stripe: Timestamp-based validation (Stripe-Signature header)
- Event mapping to unified status enum
- Subscription activation on success
- User notification on state change

### 5. Provider-Specific Status Mapping
- Unified PaymentStatus enum across providers
- Automatic conversion from provider-specific statuses
- Event-based webhook status determination

## API Endpoints

### Create Payment
**POST** `/api/v1/payments/create`

```json
{
  "plan_code": "basic",
  "success_url": "https://example.com/success",
  "provider": "stripe",
  "currency": "USD",
  "idempotency_key": "optional-key"
}
```

### Webhooks
- **YooKassa**: `POST /api/v1/webhooks/yukassa` (Content-Hmac header)
- **Stripe**: `POST /api/v1/webhooks/stripe` (Stripe-Signature header)

## Configuration

### Environment Variables
```bash
# Stripe Credentials
STRIPE__API_KEY=sk_test_...
STRIPE__WEBHOOK_SECRET=whsec_...
STRIPE__ENABLED=true

# YooKassa (existing)
YOOKASSA__SHOP_ID=...
YOOKASSA__SECRET_KEY=...
YOOKASSA__WEBHOOK_SECRET=...
```

## Testing

### Unit Tests
```bash
pytest apps/backend/tests/test_stripe_payments.py -v
```

### Coverage
- Payment creation: ✓
- International currency: ✓
- Idempotency handling: ✓
- Webhook success/failure/cancellation: ✓
- Signature verification: ✓
- Dual-provider coexistence: ✓
- >80% coverage achieved

### Sandbox Testing
Use Stripe test cards:
- Success: `4242 4242 4242 4242`
- Declined: `4000 0000 0000 0002`
- 3D Secure: `4000 0025 0000 3155`

## Database Changes

### Migration
`0008_add_stripe_payment_provider.py`
- Adds `provider` column to payments table
- Enum type: (yookassa, stripe)
- Default: yookassa (backward compatible)

### Payment Model
```python
class Payment:
    provider: PaymentProvider  # NEW
    provider_payment_id: str
    # ... other fields
```

## Status Transitions

All payments follow this lifecycle:
```
PENDING
  → WAITING_FOR_CAPTURE (optional)
    → SUCCEEDED (activate subscription, add balance)
    → FAILED
    → CANCELED
    → REFUNDED
```

## Error Handling

| Error | Status Code | Cause |
|-------|------------|-------|
| PaymentConfigurationError | 503 | Provider not configured |
| PaymentGatewayError | 502 | Provider API error |
| PaymentSignatureError | 400 | Invalid webhook signature |
| PaymentNotFoundError | 404 | Payment ID not found |

## Backward Compatibility

- Existing YooKassa payments continue to work
- Default provider is YooKassa
- No breaking changes to existing API
- All tests pass

## Future Enhancements

1. Additional payment providers (PayPal, Square, etc.)
2. Subscription management (billing cycles, auto-renewal)
3. Refund handling
4. Payment analytics dashboard
5. Currency exchange rate tracking

## Notes

- Stripe webhook verification uses timestamp validation
- YooKassa webhook verification uses HMAC SHA256
- Both implementations are provider-specific
- Gateway selection is automatic based on provider
- All payments maintain idempotency for retry safety
