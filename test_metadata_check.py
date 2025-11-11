#!/usr/bin/env python3
"""Test script to verify metadata changes work correctly."""
from sqlalchemy import MetaData

# Test 1: Verify the mixin itself
from src.common.sqlalchemy.metadata_mixin import MetadataAliasMixin
print("✓ MetadataAliasMixin imported successfully")

# Test 2: Verify user_service models
from src.user_service.models import Base, Payment, Subscription
print("✓ User service models imported successfully")

# Test 3: Verify class-level metadata is MetaData
assert isinstance(Base.metadata, MetaData)
print("✓ Base.metadata is MetaData")

assert isinstance(Payment.metadata, MetaData)
print("✓ Payment.metadata is MetaData")

assert isinstance(Subscription.metadata, MetaData)
print("✓ Subscription.metadata is MetaData")

assert Payment.metadata is Base.metadata
print("✓ Payment.metadata is Base.metadata")

# Test 4: Verify instance creation with metadata
payment = Payment(
    user_id=1,
    subscription_id=10,
    amount=100.00,
    currency="USD",
    metadata={"test": "data"},
)
print("✓ Payment instance created with metadata argument")

# Test 5: Verify metadata_dict property works
assert payment.metadata_dict == {"test": "data"}
print("✓ payment.metadata_dict returns correct dict")

# Test 6: Verify metadata_dict setter works
payment.metadata_dict = {"updated": "value"}
assert payment.metadata_dict == {"updated": "value"}
print("✓ payment.metadata_dict setter works")

# Test 7: Verify meta_data column is updated
assert payment.meta_data == {"updated": "value"}
print("✓ payment.meta_data column is correct")

print("\n✓ All metadata tests passed!")
