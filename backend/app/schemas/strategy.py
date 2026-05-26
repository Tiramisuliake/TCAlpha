"""策略 DTO。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    class_name: str
    symbol: str
    params: dict[str, Any]
    state: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class StrategyCreate(BaseModel):
    name: str
    class_name: str
    symbol: str
    params: dict[str, Any] = {}
