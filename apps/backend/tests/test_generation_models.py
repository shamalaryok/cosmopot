from __future__ import annotations

from sqlalchemy import MetaData

from backend.db.base import Base
from backend.generation.models import GenerationTask


def test_generation_task_metadata_descriptor_behaviour() -> None:
    class_metadata = GenerationTask.metadata

    assert isinstance(class_metadata, MetaData)
    assert class_metadata is Base.metadata

    payload = {"foo": "bar"}
    task = GenerationTask(
        user_id=1,
        prompt="example prompt",
        parameters={},
        subscription_tier="basic",
        s3_bucket="bucket",
        s3_key="key",
        metadata=payload,
    )

    assert task.metadata == payload
    assert task.meta_data == payload

    new_payload = {"baz": "qux"}
    task.metadata = new_payload

    assert task.meta_data == new_payload
