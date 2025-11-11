# Finance Domain Entity Overview

```
+----------------------+        +--------------------------+
|   subscription_plans |        |        users             |
|----------------------|        |--------------------------|
| id (PK)              |<-------| id (PK)                  |
| name (UNIQUE)        |        | subscription_id (FK)     |
| level                |        | ...                      |
| monthly_cost         |        +----+---------------------+
| created_at           |             |
| updated_at           |             |
+----------------------+             |
                                      v
                               +--------------+
                               | subscriptions|
                               |--------------|
                               | id (PK)      |
                               | user_id (FK) |
                               | tier (Enum)  |
                               | status (Enum)|
                               | auto_renew   |
                               | quota_limit  |
                               | quota_used   |
                               | provider_*   |
                               | metadata     |
                               | period_start |
                               | period_end   |
                               | canceled_at  |
                               | created_at   |
                               | updated_at   |
                               +------+-------+
                                      |
                    +-----------------+------------------+
                    |                                    |
                    v                                    v
         +-----------------------+          +--------------------------+
         | subscription_history  |          |        payments          |
         |-----------------------|          |--------------------------|
         | id (PK)               |          | id (PK)                  |
         | subscription_id (FK)  |          | user_id (FK)             |
         | recorded_at           |          | subscription_id (FK)     |
         | reason                |          | amount, currency         |
         | tier/status (Enums)   |          | status (Enum)            |
         | auto_renew            |          | provider_* / metadata    |
         | quota_limit / used    |          | paid_at / created_at     |
         | provider_* / metadata |          +-----------+--------------+
         | period_start / end    |                      |
         +-----------^-----------+                      v
                     |                     +---------------------------+
                     |                     |       transactions        |
                     |                     |---------------------------|
                     +---------------------| id (PK)                   |
                                           | payment_id (FK)           |
                                           | subscription_id (FK)      |
                                           | user_id (FK)              |
                                           | amount / currency         |
                                           | type (Enum)               |
                                           | description               |
                                           | provider_reference        |
                                           | metadata                  |
                                           | created_at                |
                                           +---------------------------+
```

## Enumerations

| Enum | Values | Purpose |
|------|--------|---------|
| `subscription_tier`, `subscription_history_tier` | `free`, `standard`, `pro`, `enterprise` | Commercial tier for subscription offerings. |
| `subscription_status`, `subscription_history_status` | `trialing`, `active`, `inactive`, `past_due`, `canceled`, `expired` | Lifecycle phases of a subscription. |
| `payment_status` | `pending`, `completed`, `failed`, `refunded` | Settlement state of a payment entry. |
| `transaction_type` | `charge`, `refund`, `credit` | High-level ledger classification for transactions. |

## Table Dictionary

### `subscription_plans`
Baseline catalogue of purchasable plans. Users maintain an optional pointer to their preferred plan for UI defaults. Plan records are immutable reference data.

| Column | Notes |
|--------|-------|
| `name` | Unique display label for the plan. |
| `level` | Free-form categorisation (e.g. "gold", "enterprise"). |
| `monthly_cost` | Monetised cost, stored with two-decimal precision. |

### `subscriptions`
Concrete subscription agreements per user. A partial unique index (`uq_subscriptions_user_active`) enforces at most one `active`/`trialing` subscription per user. Quota counters carry database check constraints so usage cannot exceed configured limits.

| Column | Notes |
|--------|-------|
| `user_id` | Owning account (cascade deletes remove subscriptions). |
| `tier`, `status` | String-backed enums capturing tier and lifecycle state. |
| `auto_renew` | Flag toggled off when cancellations occur. |
| `quota_limit`, `quota_used` | Integer counters guarded by `CHECK` constraints. |
| `provider_subscription_id` | External system handle (Stripe/Chargebee/etc.). |
| `provider_data`, `metadata` | JSON blobs for provider payloads and internal annotations. |
| `current_period_start`, `current_period_end` | Timeboxed billing window in UTC. |
| `canceled_at` | Recorded when status transitions to `canceled`. |

### `subscription_history`
Append-only snapshots emitted whenever the service mutates subscription state (activation, renewal, cancellation, payment events). Captures the full set of trackable attributes for audit and analytics.

| Column | Notes |
|--------|-------|
| `subscription_id` | Back-reference to the parent subscription (cascade delete). |
| `recorded_at` | UTC timestamp when the snapshot was written. |
| `reason` | Free-form descriptor (e.g. `activated`, `renewal`, `transaction-recorded`). |
| `tier`, `status`, `auto_renew`, `quota_*`, provider/meta fields, `current_period_*` | Value copies from the parent subscription at the moment of capture. |

### `payments`
Represents settlement attempts. Each payment belongs to a user and optionally a subscription. Unique provider identifiers prevent duplicate ingestion of the same upstream event. Child transactions cascade on delete to keep ledger data coherent.

| Column | Notes |
|--------|-------|
| `amount`, `currency` | Normalised monetary amount (two decimal places). |
| `status` | Tracks processor acknowledgement. |
| `provider_payment_id` | External reference, unique when supplied. |
| `paid_at` | Processor confirmation timestamp. |

### `transactions`
Ledger line items derived from payments. Transactions reference the originating payment, the affected subscription (if applicable), and the user for reporting. Provider references allow reconciliation against upstream exports.

| Column | Notes |
|--------|-------|
| `type` | Enum classification (charge, refund, credit). |
| `provider_reference` | Optional unique identifier from processors/ERP. |
| `metadata` | JSON envelope for accounting annotations and source traces. |

## Business Rules

* One active or trialing subscription per user at any time (partial unique index).
* Quota usage cannot exceed configured limits (database `CHECK` constraints plus service guardrails).
* Subscription snapshots are written for every lifecycle mutation, enabling full historical replay.
* Payments and transactions cascade with their parent subscription for predictable cleanup without orphaned ledger rows.
