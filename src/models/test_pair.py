from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TestPair(BaseModel):
    """A canonical test case specification from test_pairs.json."""
    __test__ = False
    model_config = ConfigDict(extra="allow")

    test_id: str
    trigger_id: str
    merchant_id: str
    customer_id: Optional[str] = None


class TestSuite(BaseModel):
    """Collection of canonical test cases."""
    __test__ = False
    model_config = ConfigDict(extra="allow")

    pairs: list[TestPair] = Field(default_factory=list)
