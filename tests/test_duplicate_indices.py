"""Regression test to prevent duplicate index definitions."""

from __future__ import annotations

from collections import Counter

# Import model modules directly to avoid circular import issues
import backend.analytics.models  # noqa: F401
import backend.auth.models  # noqa: F401
import backend.payments.models  # noqa: F401
import backend.referrals.models  # noqa: F401


def test_no_duplicate_indices():
    """Ensure no duplicate index names exist across all tables."""
    from backend.db.base import Base

    # Collect all index names across all tables
    all_index_names = []
    for table_name, table in Base.metadata.tables.items():
        for idx in table.indexes:
            all_index_names.append((idx.name, table_name))

    # Check for duplicate index names
    name_counter = Counter([name for name, _ in all_index_names])
    duplicates = {name: count for name, count in name_counter.items() if count > 1}

    # Assert no duplicates
    assert not duplicates, (
        f"Duplicate index names found: {duplicates}. "
        "This typically happens when a column has both 'index=True' "
        "and an explicit Index() object in __table_args__. "
        "Use only one method to define each index."
    )


def test_no_duplicate_indices_per_table():
    """Ensure no table has duplicate index names."""
    from backend.db.base import Base

    errors = []

    for table_name, table in Base.metadata.tables.items():
        table_index_names = [idx.name for idx in table.indexes]
        name_counter = Counter(table_index_names)
        duplicates = {name: count for name, count in name_counter.items() if count > 1}

        if duplicates:
            errors.append(f"Table '{table_name}' has duplicate indices: {duplicates}")

    assert not errors, "\n".join(errors)


def test_no_overlapping_column_and_explicit_indices():
    """Ensure columns don't have both index=True and explicit Index objects."""
    from backend.db.base import Base

    errors = []

    for table_name, table in Base.metadata.tables.items():
        for column in table.columns:
            if not column.index:
                continue

            single_column_indexes = [
                idx
                for idx in table.indexes
                if len(idx.columns) == 1 and idx.columns[0].name == column.name
            ]

            if len(single_column_indexes) > 1:
                index_names = [idx.name for idx in single_column_indexes]
                errors.append(
                    f"Table '{table_name}' has multiple single-column indices for "
                    f"'{column.name}': {index_names}. Remove column-level index or "
                    f"duplicate Index definitions."
                )

    assert not errors, "\n".join(errors)


def test_specific_tables_have_expected_indices():
    """Verify specific tables have the expected indices defined."""
    from backend.db.base import Base

    # Test referrals table
    if "referrals" in Base.metadata.tables:
        referrals_table = Base.metadata.tables["referrals"]
        index_names = {idx.name for idx in referrals_table.indexes}

        expected_indices = {
            "ix_referrals_referrer_id",
            "ix_referrals_referred_user_id",
            "ix_referrals_referral_code",
        }

        assert expected_indices.issubset(index_names), (
            f"Referrals table missing expected indices. "
            f"Expected: {expected_indices}, Found: {index_names}"
        )

    # Test analytics_aggregated_metrics table
    if "analytics_aggregated_metrics" in Base.metadata.tables:
        metrics_table = Base.metadata.tables["analytics_aggregated_metrics"]
        index_names = {idx.name for idx in metrics_table.indexes}

        expected_indices = {
            "ix_analytics_aggregated_metrics_date",
            "ix_analytics_aggregated_metrics_type",
            "ix_analytics_aggregated_metrics_period",
        }

        assert expected_indices.issubset(index_names), (
            f"Analytics aggregated metrics table missing expected indices. "
            f"Expected: {expected_indices}, Found: {index_names}"
        )
