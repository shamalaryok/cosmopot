# Referral Module Documentation

## Overview

The referral module implements a multi-tier referral system that rewards users for referring new customers to the platform. The system supports two tiers of rewards:

- **Tier 1**: Direct referrals - 20% of referred user's payment amount
- **Tier 2**: Indirect referrals (referred by your direct referrals) - 10% of payment amount

## Architecture

### Core Components

1. **Models**: Database entities for referrals, earnings, and withdrawals
2. **Service**: Business logic for referral operations
3. **API**: RESTful endpoints for referral functionality
4. **Integration**: Payment flow integration for automatic earnings

### Database Schema

#### Referrals Table
- Tracks referral relationships between users
- Supports tier1 and tier2 relationships
- Stores referral codes and status

#### Referral Earnings Table  
- Records earnings from successful payments
- Links earnings to specific payments and referrals
- Tracks percentage and tier for each earning

#### Referral Withdrawals Table
- Manages withdrawal requests
- Tracks status (pending, approved, rejected, processed)
- Stores processing timestamps and notes

## API Endpoints

### GET /api/v1/referrals/code
Get the current user's referral code and referral URL.

**Response:**
```json
{
  "referral_code": "AB12CD34EF56",
  "referral_url": "https://example.com/signup?ref=AB12CD34EF56"
}
```

### GET /api/v1/referrals/stats
Get comprehensive referral statistics for the current user.

**Response:**
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

### POST /api/v1/referrals/withdraw
Request a withdrawal of available referral earnings.

**Request:**
```json
{
  "amount": "50.00",
  "notes": "Monthly withdrawal"
}
```

**Response:**
```json
{
  "id": "uuid",
  "amount": "50.00",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z",
  "notes": "Monthly withdrawal",
  "processed_at": null
}
```

### GET /api/v1/referrals/withdrawals
Get the user's withdrawal request history.

**Query Parameters:**
- `limit`: Number of withdrawals to return (default: 50, max: 100)
- `offset`: Number of withdrawals to skip (default: 0)

**Response:**
```json
{
  "withdrawals": [
    {
      "id": "uuid",
      "amount": "25.00",
      "status": "processed",
      "created_at": "2024-01-10T15:20:00Z",
      "notes": "Test withdrawal",
      "processed_at": "2024-01-11T09:15:00Z"
    }
  ],
  "total": 3,
  "pending_count": 1
}
```

### POST /api/v1/referrals/apply/{referral_code}
Apply a referral code during user registration.

**Path Parameters:**
- `referral_code`: The referral code to apply

**Response:** 204 No Content

## Integration with Payment Flow

The referral system automatically creates earnings when payments succeed:

1. **Payment Processing**: When a payment is marked as successful
2. **Referral Lookup**: System checks if the paying user was referred
3. **Earnings Creation**: Creates earnings for referrers based on tier structure
4. **Tier1 Earning**: 20% of payment amount goes to direct referrer
5. **Tier2 Earning**: 10% of payment amount goes to indirect referrer (if exists)

### Example Flow

```
User A refers User B (Tier1)
User B refers User C (Tier2) 
User C makes payment of $100

Earnings:
- User A (Tier1): $20 (20% of $100)
- User B (Tier2): $10 (10% of $100)
```

## Referral Code Management

### Code Generation
- Automatically generated when first requested
- 12-character alphanumeric string
- Unique per user
- Case-insensitive

### Code Application
- Can be applied during registration
- One-time use per referred user
- Creates both tier1 and tier2 relationships automatically

## Withdrawal System

### Withdrawal Process
1. User requests withdrawal of available balance
2. Request is created with "pending" status
3. Admin reviews and approves/rejects requests
4. Approved requests are marked as "processed"
5. User's available balance is reduced

### Withdrawal Rules
- Cannot withdraw more than available balance
- Multiple pending withdrawals allowed
- Withdrawal amounts must be positive
- Optional notes can be provided

## Rate Limiting

All referral endpoints are rate-limited to prevent abuse:
- `referrals:get_code`: 10 requests per minute
- `referrals:get_stats`: 10 requests per minute  
- `referrals:withdraw`: 5 requests per minute
- `referrals:get_withdrawals`: 10 requests per minute
- `referrals:apply_code`: 3 requests per minute

## Error Handling

### Common Error Responses

**400 Bad Request**
```json
{
  "detail": "Insufficient balance. Available: 25.00, Requested: 50.00"
}
```

**404 Not Found**
```json
{
  "detail": "Referral code 'INVALIDCODE' not found"
}
```

**422 Validation Error**
```json
{
  "detail": [
    {
      "loc": ["body", "amount"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt"
    }
  ]
}
```

## Testing

The referral module includes comprehensive tests:

### Unit Tests
- Referral code generation and retrieval
- Referral relationship creation
- Earnings calculation and creation
- Withdrawal request processing
- Statistics calculation

### Integration Tests  
- API endpoint functionality
- Payment flow integration
- Error handling
- Rate limiting
- Authentication and authorization

### Test Coverage
- Service layer: >90% coverage
- API layer: >85% coverage
- Multi-tier reward scenarios
- Edge cases and error conditions

Run tests:
```bash
pytest apps/backend/tests/test_referrals.py -v
pytest apps/backend/tests/test_referrals_api.py -v
```

## Security Considerations

### Referral Code Security
- Codes are randomly generated using `secrets.token_urlsafe()`
- No predictable patterns or sequential numbers
- Case-insensitive to reduce user error

### Withdrawal Security
- Users can only withdraw from their own earnings
- Balance validation prevents overdrafts
- Admin approval process for withdrawals
- Full audit trail in database

### Rate Limiting
- Prevents referral code enumeration
- Limits withdrawal request frequency
- Protects against automated abuse

## Monitoring and Analytics

### Key Metrics
- Referral conversion rate
- Earnings per referral
- Withdrawal processing time
- Tier1 vs Tier2 referral distribution

### Logging
- Referral code generation
- Earnings creation events
- Withdrawal requests
- Error conditions

## Configuration

The referral module uses the following configuration:

```python
# Rate limiting (in requests per minute)
RATE_LIMIT__REFERRALS_GET_CODE_PER_MINUTE=10
RATE_LIMIT__REFERRALS_GET_STATS_PER_MINUTE=10
RATE_LIMIT__REFERRALS_WITHDRAW_PER_MINUTE=5
RATE_LIMIT__REFERRALS_GET_WITHDRAWALS_PER_MINUTE=10
RATE_LIMIT__REFERRALS_APPLY_CODE_PER_MINUTE=3

# Referral percentages (can be customized)
REFERRAL__TIER1_PERCENTAGE=20
REFERRAL__TIER2_PERCENTAGE=10

# Withdrawal settings
REFERRAL__MIN_WITHDRAWAL_AMOUNT=1.00
REFERRAL__MAX_WITHDRAWAL_AMOUNT=10000.00
```

## Future Enhancements

### Planned Features
1. **Referral Analytics Dashboard**: Detailed analytics for referrers
2. **Automated Withdrawal Processing**: Integration with payment providers
3. **Referral Campaigns**: Time-limited bonus campaigns
4. **Multi-level Referrals**: Support for more than 2 tiers
5. **Referral Leaderboards**: Gamification elements

### Scalability Considerations
- Database indexing for high-volume referral lookups
- Caching of frequently accessed referral statistics
- Batch processing of earnings for bulk payments
- Asynchronous withdrawal processing

## Troubleshooting

### Common Issues

**Referral code not working**
- Verify code exists and is active
- Check if code has already been used
- Ensure user is not trying to self-refer

**Missing earnings after payment**
- Confirm payment status is "succeeded"
- Check if referral relationship exists
- Verify payment metadata contains referral information

**Withdrawal request failing**
- Verify sufficient available balance
- Check withdrawal amount limits
- Ensure no pending withdrawal issues

### Debugging Commands

```sql
-- Check user's referral code
SELECT referral_code FROM referrals WHERE referrer_id = 'user_uuid';

-- Check user's earnings
SELECT amount, tier, created_at FROM referral_earnings 
WHERE user_id = 'user_uuid' ORDER BY created_at DESC;

-- Check withdrawal status
SELECT amount, status, created_at, processed_at FROM referral_withdrawals 
WHERE user_id = 'user_uuid' ORDER BY created_at DESC;
```