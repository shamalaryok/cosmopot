# Stripe Payment Integration

This document describes the Stripe payment provider integration alongside the existing YooKassa provider.

## Overview

The payment system now supports both YooKassa (for RUB payments) and Stripe (for international payments) as payment providers. The implementation ensures:

- **Dual-provider coexistence**: Both providers can be used simultaneously
- **Provider abstraction**: Unified interface through `PaymentGateway` protocol
- **Idempotency**: All payments are idempotent through `idempotency_key`
- **Webhook handling**: Provider-specific webhook processing with signature verification
- **Currency support**: International currency support through Stripe

## Configuration

### Environment Variables

```bash
# Stripe Configuration
STRIPE__API_KEY=sk_test_... or sk_live_...
STRIPE__WEBHOOK_SECRET=whsec_...
STRIPE__ENABLED=true
```

### Settings

Stripe settings are configured in `backend.core.config`:

```python
class StripeSettings(BaseSettings):
    api_key: SecretStr | None = None
    webhook_secret: SecretStr | None = None
    enabled: bool = False
```

## Architecture

### Payment Flow

#### 1. Payment Creation

```
Client → POST /api/v1/payments/create
  {
    "plan_code": "basic",
    "success_url": "https://example.com/success",
    "provider": "stripe",  # or "yookassa" (default)
    "currency": "USD"  # optional for international
  }
→ PaymentService.create_payment()
  → Select gateway based on provider
  → Build provider-specific payload
  → Gateway creates payment
  → Store payment record with provider info
→ Response includes provider and confirmation URL
```

#### 2. Webhook Processing

```
Stripe → POST /api/v1/webhooks/stripe
  (with Stripe-Signature header)
→ Verify signature (provider-specific)
→ Parse webhook payload
→ Lock payment record for update
→ Map event to payment status
→ If succeeded: activate subscription, add balance
→ Notify user
```

### Gateway Selection

The `PaymentService` automatically selects the correct gateway based on the `provider` field in `PaymentRequest`:

```python
@dataclass
class PaymentRequest:
    plan_code: str
    success_url: str
    cancel_url: str | None = None
    idempotency_key: str | None = None
    provider: PaymentProvider = PaymentProvider.YOOKASSA
    currency: str | None = None  # For international payments
```

### Provider-Specific Status Mapping

Each provider has different status values. The service maps them to a unified enum:

**YooKassa Statuses:**
- `pending` → `PaymentStatus.PENDING`
- `waiting_for_capture` → `PaymentStatus.WAITING_FOR_CAPTURE`
- `succeeded` → `PaymentStatus.SUCCEEDED`
- `canceled` → `PaymentStatus.CANCELED`
- `refunded` → `PaymentStatus.REFUNDED`
- `failed` → `PaymentStatus.FAILED`

**Stripe Statuses:**
- `requires_payment_method` → `PaymentStatus.PENDING`
- `requires_confirmation` → `PaymentStatus.PENDING`
- `requires_action` → `PaymentStatus.WAITING_FOR_CAPTURE`
- `processing` → `PaymentStatus.WAITING_FOR_CAPTURE`
- `succeeded` → `PaymentStatus.SUCCEEDED`
- `requires_capture` → `PaymentStatus.WAITING_FOR_CAPTURE`
- `canceled` → `PaymentStatus.CANCELED`

## API Endpoints

### Create Payment

**Endpoint:** `POST /api/v1/payments/create`

**Request:**
```json
{
  "plan_code": "basic",
  "success_url": "https://example.com/success",
  "cancel_url": "https://example.com/cancel",
  "idempotency_key": "unique-key-for-retry",
  "provider": "stripe",
  "currency": "USD"
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "provider": "stripe",
  "provider_payment_id": "pi_test_stripe_1",
  "status": "pending",
  "confirmation_url": "pi_test_stripe_1#secret",
  "amount": "9.99",
  "currency": "USD"
}
```

### YooKassa Webhook

**Endpoint:** `POST /api/v1/webhooks/yukassa`

**Headers:**
```
Content-Hmac: sha256=<signature>
```

### Stripe Webhook

**Endpoint:** `POST /api/v1/webhooks/stripe`

**Headers:**
```
Stripe-Signature: t=<timestamp>,v1=<signature>
```

## Database Schema

### Payment Model

The `Payment` model includes a new `provider` field:

```python
class Payment(...):
    user_id: int
    subscription_id: int
    provider: PaymentProvider  # NEW: YOOKASSA or STRIPE
    provider_payment_id: str
    idempotency_key: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    confirmation_url: str | None
    ...
```

**Migration:** `0008_add_stripe_payment_provider`

## Idempotency & Conflict Resolution

### Idempotency Key

All payment creation requests include an `idempotency_key` to ensure safety during retries:

- **Client-supplied:** Passed in request body
- **Auto-generated:** If not provided, generated as `{user_id}-{uuid}`
- **Lookup:** Before creating payment, check for existing payment with same key
- **Deduplication:** Return existing payment if idempotency key match found

### Conflict Resolution

When processing webhooks:

1. **Lock payment record:** `SELECT ... FOR UPDATE` prevents race conditions
2. **Check status transitions:** Ensure state changes are valid
3. **Preserve previous state:** Store cancellation/failure details
4. **Subscription activation:** Only activate once, on first success

## Status Transitions

### Payment Lifecycle

```
PENDING
  ↓ (on payment processed)
WAITING_FOR_CAPTURE (or direct to SUCCEEDED)
  ├→ SUCCEEDED (user gets access, balance added)
  ├→ FAILED (error occurred)
  ├→ CANCELED (user cancelled)
  └→ REFUNDED (refund issued)
```

### Subscription Activation

- Triggered on transition to `SUCCEEDED` status
- **Idempotent:** Only activates once per payment
- **Captures timestamp:** `payment.captured_at`
- **Updates user:** Sets `subscription_id`, adds to `balance`
- **Creates earnings:** If referral links exist

## Error Handling

### Configuration Errors

```
PaymentConfigurationError: Stripe integration is not configured
```

**Handling:** Return `HTTP 503 Service Unavailable`

### Gateway Errors

```
PaymentGatewayError: Stripe API error message
```

**Handling:** Return `HTTP 502 Bad Gateway`

### Signature Verification Errors

```
PaymentSignatureError: Webhook signature mismatch
```

**Handling:** Return `HTTP 400 Bad Request`

### Payment Not Found

```
PaymentNotFoundError: Payment not found with provider id
```

**Handling:** Return `HTTP 404 Not Found`

## Webhook Retries

Both YooKassa and Stripe implement webhook retries on failure:

- **YooKassa:** Retries with exponential backoff
- **Stripe:** Retries with exponential backoff (up to 24 hours)

**Idempotency:** Duplicate webhooks are safe - same payment record is updated

## Currency Conversion

### Supported Currencies

- **YooKassa:** Primarily RUB
- **Stripe:** Any currency supported by Stripe (USD, EUR, GBP, JPY, etc.)

### Request Format

```json
{
  "plan_code": "basic",
  "provider": "stripe",
  "currency": "EUR"
}
```

### Amount Handling

- **YooKassa:** Amount in major units (9.99 = 9.99 RUB)
- **Stripe:** Amount in minor units (9.99 USD = 999 cents)

The service automatically converts:

```python
# YooKassa
"amount": {"value": "9.99", "currency": "RUB"}

# Stripe
"amount": 999,  # cents
"currency": "usd"  # lowercase
```

## Testing

### Unit Tests

Located in `apps/backend/tests/test_stripe_payments.py`

Coverage includes:

- Payment creation with Stripe
- International currency support
- Idempotency key handling
- Webhook success flow
- Webhook failure scenarios
- Webhook cancellation
- Signature verification
- Missing payment handling
- Dual-provider coexistence

### Integration Tests

Run against test environment:

```bash
pytest apps/backend/tests/test_stripe_payments.py -v
```

### Mocking

Stripe webhook verification is mocked in `conftest.py`:

```python
@patch("stripe.Webhook.construct_event")
def mock_stripe_webhook(mock_construct):
    mock_construct.return_value = {"type": "test", "data": {}}
    yield
```

## Sandbox Testing

### Stripe Test Mode

Use these test card numbers:

- **Success:** 4242 4242 4242 4242
- **Declined:** 4000 0000 0000 0002
- **3D Secure:** 4000 0025 0000 3155

### Test Credentials

```bash
STRIPE__API_KEY=sk_test_YOUR_TEST_KEY
STRIPE__WEBHOOK_SECRET=whsec_YOUR_TEST_SECRET
```

## Monitoring & Logging

### Log Messages

Payment events are logged with structured logging:

```
payment_idempotency_hit: Duplicate payment request detected
stripe_webhook_signature_error: Webhook signature verification failed
stripe_webhook_processed: Stripe webhook successfully processed
referral_earnings_created: Referral earnings calculated
```

### Metrics

Track via analytics:

- `payment.initiated` - Payment creation started
- `payment.succeeded` - Payment successful
- `payment.failed` - Payment failed
- `payment.canceled` - Payment cancelled

## FAQ

### Q: Can I use both providers simultaneously?

**A:** Yes. Users can choose their preferred provider at payment time.

### Q: What happens if Stripe is down?

**A:** If Stripe API is unavailable, payment creation returns `HTTP 502 Bad Gateway`. YooKassa payments are unaffected.

### Q: Can I migrate payments between providers?

**A:** The `provider` field tracks which service processed each payment. Historical payments remain associated with their original provider.

### Q: How do I handle currency conversion?

**A:** Currency is specified per payment request. The subscription plan amount is used; currency override allows international pricing.

### Q: What if idempotency key is reused?

**A:** The service returns the existing payment record. The payment is not created twice.

## Troubleshooting

### Stripe Webhook Not Received

1. Check webhook endpoint is registered in Stripe Dashboard
2. Verify `STRIPE__WEBHOOK_SECRET` matches Dashboard secret
3. Check firewall allows Stripe IP range
4. Review logs for signature verification errors

### Payment Stuck in PENDING

1. Check webhook was delivered (Stripe Dashboard → Events)
2. Verify webhook signature verification passed
3. Check database for payment record
4. Monitor application logs

### Configuration Error

```
ERROR Stripe integration is not configured
```

**Solution:** Set `STRIPE__API_KEY` environment variable

## See Also

- [Payment Service Documentation](./PAYMENTS.md)
- [YooKassa Integration](./YOOKASSA_INTEGRATION.md)
- [Webhook Documentation](./WEBHOOKS.md)
