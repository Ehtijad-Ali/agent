"""Shared Pydantic base.

snake_case in Python, camelCase on the wire -- the frontend's Zod schemas are
the contract and must not change (docs/frontend-api-mapping.md §3).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
