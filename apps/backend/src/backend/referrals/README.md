# Referral Module

A multi-tier referral system for the platform that rewards users for referring new customers.

## Features

- **Two-tier referral system**: 20% for direct referrals, 10% for indirect referrals
- **Automatic earnings**: Earnings are created automatically when payments succeed
- **Withdrawal system**: Users can request withdrawals of their earnings
- **Comprehensive API**: Full REST API for referral management
- **Rate limiting**: Protection against abuse
- **Audit trail**: Complete tracking of all referral activities

## Quick Start

### 1. Get Your Referral Code

```bash
curl -X GET "http://localhost:8000/api/v1/referrals/code" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "referral_code": "AB12CD34EF56",
  "referral_url": "https://example.com/signup?ref=AB12CD34EF56"
}
```

### 2. Share Your Referral Code

Share the `referral_url` with friends and colleagues. When they sign up using your link, they become your referral.

### 3. Track Your Earnings

```bash
curl -X GET "http://localhost:8000/api/v1/referrals/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "referral_code": "AB12CD34EF56",
  "total_earnings": "150.50",
  "available_balance": "125.50",
  "total_withdrawn": "25.00",
  "tier1_count": 5,
  "tier2_count": 12,
  "pending_withdrawals": 1
}
```

### 4. Withdraw Your Earnings

```bash
curl -X POST "http://localhost:8000/api/v1/referrals/withdraw" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": "50.00", "notes": "Monthly withdrawal"}'
```

## How It Works

### Referral Structure

1. **Tier 1 (Direct)**: Users you refer directly
   - **Reward**: 20% of their payment amounts
   - **Example**: If your referral pays $100, you earn $20

2. **Tier 2 (Indirect)**: Users referred by your direct referrals
   - **Reward**: 10% of their payment amounts  
   - **Example**: If your tier2 referral pays $100, you earn $10

### Payment Flow Integration

The system automatically creates earnings when:

1. A referred user makes a payment
2. The payment status changes to "succeeded"
3. The system looks up the referral chain
4. Earnings are created for eligible referrers
5. All earnings are tracked in the user's balance

### Withdrawal Process

1. User requests withdrawal from available balance
2. Request is created with "pending" status
3. Admin reviews and approves/rejects requests
4. Approved requests are marked as "processed"
5. User's available balance is reduced accordingly

## API Endpoints

| Method | Endpoint | Description |
|---------|-----------|-------------|
| GET | `/api/v1/referrals/code` | Get your referral code |
| GET | `/api/v1/referrals/stats` | Get referral statistics |
| POST | `/api/v1/referrals/withdraw` | Request withdrawal |
| GET | `/api/v1/referrals/withdrawals` | Get withdrawal history |
| POST | `/api/v1/referrals/apply/{code}` | Apply referral code |

## Security Features

- **Rate limiting**: All endpoints are rate-limited
- **Balance validation**: Cannot withdraw more than available balance
- **Unique codes**: Cryptographically secure referral code generation
- **Audit trail**: Complete tracking of all activities
- **Authentication**: All endpoints require valid authentication

## Testing

Run the test suite:

```bash
# Unit tests
pytest apps/backend/tests/test_referrals.py -v

# API tests  
pytest apps/backend/tests/test_referrals_api.py -v
```

## Documentation

See [docs/REFERRAL_MODULE.md](../../docs/REFERRAL_MODULE.md) for detailed documentation.

## Support

For issues or questions about the referral module, please check the documentation or create an issue in the project repository.