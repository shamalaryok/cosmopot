# Analytics Implementation Guide

This guide covers the comprehensive analytics tracking system implemented for the platform, including both backend and frontend components.

## Overview

The analytics system provides:
- **Event Tracking**: Track user actions and system events
- **User Properties**: Store and update user characteristics
- **Aggregated Metrics**: Calculate DAU/MAU, conversion rates, churn, LTV/CAC
- **Multi-Provider Support**: Amplitude and Mixpanel integration
- **Privacy Compliance**: PII filtering and data retention policies
- **Batch Processing**: Efficient event delivery with retry logic
- **Real-time Dashboard**: Live analytics metrics and KPIs

## Architecture

### Backend Components

#### Core Services
- **AnalyticsService**: Main service for event tracking and provider communication
- **AnalyticsAggregationService**: Calculates aggregated metrics (DAU/MAU, conversion, churn)
- **AnalyticsScheduler**: Background task processing and periodic calculations

#### Data Layer
- **AnalyticsEvent**: Stores individual events with processing status
- **AggregatedMetrics**: Stores calculated metrics (daily/weekly/monthly)
- **AnalyticsRepository**: Database operations for analytics data

#### API Integration
- **AnalyticsMiddleware**: Automatic API request tracking
- **Analytics Decorators**: Manual event tracking with validation
- **Analytics Routes**: REST API for analytics data and configuration

#### Configuration
```python
# backend/.env.analytics
ANALYTICS__ENABLED=true
ANALYTICS__AMPLITUDE_API_KEY=your_amplitude_api_key_here
ANALYTICS__MIXPANEL_TOKEN=your_mixpanel_token_here
ANALYTICS__ENABLE_PII_TRACKING=false
ANALYTICS__SANDBOX_MODE=false
ANALYTICS__BATCH_SIZE=100
ANALYTICS__FLUSH_INTERVAL_SECONDS=60
ANALYTICS__DATA_RETENTION_DAYS=365
```

### Frontend Components

#### Client Implementation
- **AnalyticsClient**: Browser SDK wrapper for Amplitude/Mixpanel
- **AnalyticsPlugin**: Vue.js plugin for automatic tracking
- **Analytics Composables**: Vue composables for easy event tracking

#### Configuration
```typescript
// frontend/.env.analytics
VITE_ANALYTICS_ENABLED=true
VITE_AMPLITUDE_API_KEY=your_amplitude_api_key_here
VITE_MIXPANEL_TOKEN=your_mixpanel_token_here
VITE_ANALYTICS_PII_TRACKING=false
VITE_ANALYTICS_SANDBOX_MODE=false
VITE_ANALYTICS_BATCH_SIZE=10
VITE_ANALYTICS_FLUSH_INTERVAL=5000
```

## Event Types

### Authentication Events
- `signup_started`: User begins registration process
- `signup_completed`: User successfully registers
- `email_verified`: User verifies email address
- `login`: User logs in
- `logout`: User logs out
- `session_created`: New user session created

### Generation Events
- `generation_started`: User starts content generation
- `generation_completed`: Generation completes successfully
- `generation_failed`: Generation fails
- `generation_cancelled`: User cancels generation

### Payment Events
- `payment_initiated`: Payment process starts
- `payment_completed`: Payment succeeds
- `payment_failed`: Payment fails
- `subscription_created`: New subscription created
- `subscription_cancelled`: Subscription cancelled
- `subscription_upgraded`: Subscription upgraded
- `subscription_downgraded`: Subscription downgraded

### Referral Events
- `referral_sent`: User shares referral code
- `referral_accepted`: Referral is used successfully
- `referral_milestone_reached`: User hits referral milestone
- `referral_earnings_withdrawn`: User withdraws referral earnings

### Engagement Events
- `page_view`: User views a page
- `feature_used`: User interacts with a feature
- `session_duration`: Session length tracking
- `user_profile_updated`: User updates profile
- `settings_changed`: User modifies settings

## Integration Examples

### Backend Event Tracking

#### Manual Tracking with Decorators
```python
from backend.analytics.decorators import track_analytics_event, AnalyticsEvent

@track_analytics_event(
    event_type=AnalyticsEvent.GENERATION_STARTED,
    event_data_mapper=lambda *args, **kwargs: {
        "generation_type": kwargs.get("generation_type", "unknown"),
        "prompt_length": len(kwargs.get("prompt", "")),
    },
    include_user=True,
)
async def generate_content(prompt: str, generation_type: str):
    # Your generation logic here
    pass
```

#### Manual Tracking with Service
```python
from backend.analytics.decorators import AnalyticsTracker

async def some_endpoint():
    analytics_tracker = AnalyticsTracker(analytics_service, session)
    
    await analytics_tracker.track_generation(
        user_id=str(user.id),
        generation_type="image",
        status="started",
        prompt_length=len(prompt),
    )
    
    try:
        # Your logic here
        result = await do_something()
        
        await analytics_tracker.track_generation(
            user_id=str(user.id),
            generation_type="image",
            status="completed",
            result_id=result.id,
        )
    except Exception as e:
        await analytics_tracker.track_generation(
            user_id=str(user.id),
            generation_type="image",
            status="failed",
            error=str(e),
        )
        raise
```

### Frontend Event Tracking

#### Using Composables
```vue
<script setup lang="ts">
import { useAnalytics } from '@/composables/useAnalytics';

const { trackFeatureUsage, trackFormInteraction } = useAnalytics();

const handleGenerateClick = () => {
  trackFeatureUsage('image_generator', {
    action: 'click',
    source: 'main_page',
  });
};

const handleFormSubmit = () => {
  trackFormInteraction('generation_form', 'submit', {
    prompt_length: prompt.value.length,
    selected_model: selectedModel.value,
  });
};
</script>
```

#### Manual Tracking
```typescript
import { getAnalytics } from '@/services/analytics';

const analytics = getAnalytics();

if (analytics) {
  analytics.track({
    event_type: 'custom_event',
    event_data: {
      custom_property: 'value',
      timestamp: new Date().toISOString(),
    },
  });
}
```

#### Auto-Tracking with Data Attributes
```html
<!-- Track clicks automatically -->
<button data-analytics-track="feature_click" data-analytics-feature="generate">
  Generate
</button>

<!-- Track form interactions automatically -->
<form data-analytics-form="contact_form">
  <input type="email" name="email" required>
  <button type="submit">Submit</button>
</form>
```

## Aggregated Metrics

### Daily Metrics
- **DAU** (Daily Active Users): Unique users active per day
- **New Registrations**: New user signups per day
- **Generations Completed**: Successful generations per day
- **Generations Failed**: Failed generations per day
- **Revenue**: Total revenue generated per day
- **Successful Payments**: Completed payments per day
- **Failed Payments**: Failed payments per day
- **New Subscriptions**: New subscriptions created per day
- **Cancelled Subscriptions**: Subscriptions cancelled per day
- **Referrals Sent**: Referral codes shared per day
- **Referrals Accepted**: Referral codes used per day
- **Signup to Payment Conversion**: % of signups that convert to payments

### Weekly Metrics
- **WAU** (Weekly Active Users): Unique users active per week
- **Weekly Revenue**: Total revenue per week
- **Weekly New Users**: New user signups per week

### Monthly Metrics
- **MAU** (Monthly Active Users): Unique users active per month
- **Monthly Revenue**: Total revenue per month
- **Monthly New Users**: New user signups per month
- **Churn Rate**: % of users who stop using the service
- **LTV/CAC Ratio**: Lifetime value to customer acquisition cost ratio

## API Endpoints

### Event Tracking
```http
POST /api/v1/analytics/events
Content-Type: application/json

{
  "event_type": "feature_used",
  "event_data": {
    "feature_name": "image_generator",
    "action": "click"
  },
  "user_properties": {
    "subscription_level": "pro"
  }
}
```

### Dashboard Metrics
```http
GET /api/v1/analytics/metrics/dashboard

Response:
{
  "daily_active_users": 150,
  "monthly_active_users": 2500,
  "new_registrations_today": 12,
  "revenue_today": 599.97,
  "conversion_rate": 25.0,
  "churn_rate": 5.5,
  "ltv_cac_ratio": 3.2
}
```

### Aggregated Metrics
```http
GET /api/v1/analytics/metrics/aggregated?metric_type=dau&period=daily&start_date=2024-01-01&end_date=2024-01-31

Response:
[
  {
    "id": "metric-id",
    "metric_date": "2024-01-01",
    "metric_type": "dau",
    "period": "daily",
    "value": 150.0,
    "metadata": {
      "calculated_at": "2024-01-02T00:00:00Z"
    }
  }
]
```

## Privacy and PII

### PII Filtering
When `enable_pii_tracking` is false, the following fields are automatically filtered:
- `email`, `name`, `full_name`, `first_name`, `last_name`, `phone`
- IP addresses and user agents (unless explicitly enabled)

### Data Retention
- Events are automatically deleted after `data_retention_days`
- Aggregated metrics are retained indefinitely
- Users can request data deletion per GDPR requirements

### User Consent
- Frontend respects user consent for tracking
- Events are not tracked if user opts out
- Privacy settings are stored locally and respected across sessions

## Testing

### Backend Tests
```bash
# Run analytics service tests
pytest apps/backend/tests/test_analytics_service.py -v

# Run aggregation tests
pytest apps/backend/tests/test_analytics_aggregation.py -v

# Run API tests
pytest apps/backend/tests/test_analytics_api.py -v
```

### Frontend Tests
```bash
# Run analytics composables tests
pnpm test composables/useAnalytics.test.ts
```

### Integration Testing
```bash
# Test analytics pipeline end-to-end
# 1. Configure sandbox mode
ANALYTICS__SANDBOX_MODE=true

# 2. Trigger events
curl -X POST http://localhost:8000/api/v1/analytics/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "test_event", "event_data": {}}'

# 3. Verify event processing
curl http://localhost:8000/api/v1/analytics/process-events

# 4. Check aggregated metrics
curl http://localhost:8000/api/v1/analytics/metrics/dashboard
```

## Configuration Guide

### Production Setup
1. **Configure Analytics Providers**
   ```python
   # backend/.env.analytics
   ANALYTICS__ENABLED=true
   ANALYTICS__AMPLITUDE_API_KEY=prod_amplitude_key
   ANALYTICS__MIXPANEL_TOKEN=prod_mixpanel_token
   ANALYTICS__SANDBOX_MODE=false
   ANALYTICS__ENABLE_PII_TRACKING=false
   ```

2. **Frontend Configuration**
   ```typescript
   // frontend/.env.analytics
   VITE_ANALYTICS_ENABLED=true
   VITE_AMPLITUDE_API_KEY=prod_amplitude_key
   VITE_MIXPANEL_TOKEN=prod_mixpanel_token
   VITE_ANALYTICS_PII_TRACKING=false
   VITE_ANALYTICS_SANDBOX_MODE=false
   ```

3. **Database Migration**
   ```bash
   # Apply analytics tables migration
   alembic upgrade head
   ```

4. **Background Processing**
   ```bash
   # Start analytics scheduler (included in main app)
   # Events are processed automatically every 60 seconds
   # Metrics are calculated daily at 1:00 AM UTC
   ```

### Development Setup
1. **Sandbox Mode**
   ```python
   ANALYTICS__SANDBOX_MODE=true
   # Events are logged locally instead of sent to providers
   ```

2. **Local Testing**
   ```bash
   # Test analytics with mock data
   python -m backend.analytics.tasks
   ```

## Monitoring and Debugging

### Log Levels
- `INFO`: Normal operation, event tracking, metric calculation
- `WARNING`: Provider errors, retry attempts
- `ERROR`: Critical failures, configuration issues

### Health Checks
```http
GET /api/v1/analytics/config

Response:
{
  "enabled": true,
  "amplitude_configured": true,
  "mixpanel_configured": true,
  "pii_tracking_enabled": false,
  "sandbox_mode": false,
  "batch_size": 100,
  "flush_interval_seconds": 60
}
```

### Common Issues
1. **Events Not Appearing**
   - Check analytics configuration
   - Verify provider API keys
   - Check scheduler is running
   - Review error logs

2. **High Memory Usage**
   - Reduce batch size
   - Increase flush interval
   - Check event processing backlog

3. **Missing PII Filtering**
   - Ensure `enable_pii_tracking=false` in production
   - Verify event schemas don't include PII fields
   - Check frontend PII settings

## Best Practices

### Event Design
- Use descriptive event names
- Include relevant context in event data
- Avoid sensitive information in event properties
- Use consistent data types and formats

### Performance
- Batch events when possible
- Use appropriate flush intervals
- Monitor provider rate limits
- Implement client-side caching for user properties

### Privacy
- Always filter PII in production
- Implement user consent mechanisms
- Provide data export/deletion options
- Follow GDPR and CCPA requirements

### Monitoring
- Set up alerts for analytics failures
- Monitor event processing backlogs
- Track provider API errors
- Regular metric validation

This analytics system provides comprehensive tracking capabilities while maintaining privacy standards and performance requirements.