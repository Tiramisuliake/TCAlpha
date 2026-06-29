"""通知中心 DTO（Phase 5 Step 1）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 已注册的事件类型（用于前端 select 下拉 + 文档）
KNOWN_EVENT_TYPES: list[dict[str, str]] = [
    {"type": "strategy.started", "desc": "策略启动"},
    {"type": "strategy.stopped", "desc": "策略正常停止"},
    {"type": "strategy.crashed", "desc": "策略异常退出"},
    {"type": "sim.order_submitted", "desc": "模拟订单已提交"},
    {"type": "sim.order_filled", "desc": "模拟订单已成交"},
    {"type": "sim.order_cancelled", "desc": "模拟订单已取消"},
    {"type": "backtest.started", "desc": "回测开始"},
    {"type": "backtest.done", "desc": "回测完成"},
    {"type": "backtest.failed", "desc": "回测失败"},
    {"type": "api.exception", "desc": "API 未处理异常"},
    {"type": "ai.alert.info", "desc": "AI 盯盘 - 提示（Step 3）"},
    {"type": "ai.alert.warn", "desc": "AI 盯盘 - 预警（Step 3）"},
    {"type": "ai.alert.danger", "desc": "AI 盯盘 - 紧急（Step 3）"},
    {"type": "quote.surge", "desc": "行情急涨/急跌（Step 2）"},
    {"type": "quote.limit_up", "desc": "涨停（Step 2）"},
    {"type": "screen.short_term", "desc": "短线选股命中（每日收盘自动扫描）"},
    {"type": "screen.factor", "desc": "多因子选股 top（每日收盘综合打分）"},
]

CHANNELS = ["feishu"]  # v0.5.1 only


class NotifyRuleBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    match_types: list[str] = Field(default_factory=list, max_length=32)
    match_filters: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list, max_length=8)
    feishu_webhook: str = Field(default="", max_length=512)
    feishu_secret: str = Field(default="", max_length=128)
    quiet_hours: str = Field(default="", max_length=16)
    enabled: bool = True


class NotifyRuleCreate(NotifyRuleBase):
    pass


class NotifyRuleUpdate(NotifyRuleBase):
    pass


class NotifyRuleOut(NotifyRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class NotifyLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int | None
    event_type: str
    channel: str
    payload: dict[str, Any]
    success: bool
    error_msg: str
    created_at: datetime


class NotifyTestRequest(BaseModel):
    """测试推送：直接调飞书，不走 event_bus，便于用户验证 webhook。"""

    rule_id: int | None = None  # 若指定则用该规则的 webhook
    feishu_webhook: str = ""
    feishu_secret: str = ""
    content: str = "TCAlpha 通知测试"
