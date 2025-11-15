# User Domain Entity Overview

```
+------------------------+     +--------------------+
|  subscription_plans  |<---+     |     user_profiles  |
|----------------------|    |     |--------------------|
| id (PK)              |    |     | id (PK)            |
| name (UNIQUE)        |    |     | user_id (FK, uniq) |
| level                |    +-----| telegram_id (uniq) |
| monthly_cost         |          | ...                |
| created_at           |          | created_at         |
| updated_at           |          | updated_at         |
+----------------------+          | deleted_at         |
                                  +---------^----------+
                                       |
                                       |
+-----------------+           +--------+----------+
|      users      |1---------n|     user_sessions  |
|-----------------|           |--------------------|
| id (PK)         |           | id (PK)            |
| email (UNIQUE)  |           | user_id (FK)       |
| hashed_password |           | session_token uniq |
| role (Enum)     |           | expires_at         |
| balance         |           | created_at         |
| subscription_id |-----------| revoked_at         |
| is_active       |           | ended_at           |
| created_at      |           +--------------------+
| updated_at      |
| deleted_at      |
+-----------------+
```

* **Subscription Plans** represent purchasable tiers. Users may reference a plan, and the reference is nulled if the plan is removed.
* **Users** own a single profile and many sessions. Soft deletion is handled via `deleted_at`.
* **User Profiles** extend the main user entity with optional contact data. The `telegram_id` column is globally unique.
* **User Sessions** track issued auth tokens, cascading away when the owning user is deleted.

Key business rules validated by the automated tests:

- `users.email` and `user_profiles.telegram_id` are unique.
- Deleting a user removes related profiles and sessions (via database cascades).
- Balance adjustments preserve two-decimal precision.
- Session lifecycle helpers (create/revoke/expire) update timestamps consistently.
```

## Telegram Authentication Flow

Telegram Login is handled by the backend service via the `/api/v1/auth/telegram` endpoint. The service performs the following actions:

1. Rebuilds the `data_check_string` from the payload and validates the `hash` using the bot token as described in the official Telegram documentation.
2. Ensures the payload `auth_date` is recent (within the configured replay window) and not in the future.
3. Locates an existing user by `user_profiles.telegram_id`, or creates a new user + profile if none exists. Creation is idempotent to avoid duplicate records.
4. Rejects logins for inactive or soft-deleted users to protect access for banned accounts.
5. Issues a signed JWT access token and records a matching `user_sessions` row (user agent, IP, expiry) for auditing.

### Required Environment Variables

The following settings must be provided for Telegram authentication to operate:

- `TELEGRAM__BOT_TOKEN` – the bot token supplied by BotFather.
- `TELEGRAM__LOGIN_TTL_SECONDS` – maximum age for accepting Telegram login payloads (default 86400 seconds).
- `JWT__SECRET_KEY` – secret used to sign issued JWT access tokens.
- `JWT__ALGORITHM` – JWT signing algorithm (default `HS256`).
- `JWT__ACCESS_TTL_SECONDS` – lifetime in seconds for issued access tokens.

All variables can also be supplied without the double-underscore namespace (e.g. `TELEGRAM_BOT_TOKEN`) if preferred.
