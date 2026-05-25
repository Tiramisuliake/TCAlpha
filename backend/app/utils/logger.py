"""loguru 配置（统一时区 / 格式 / sink）。"""
from __future__ import annotations

import sys
from datetime import datetime

import pytz
from loguru import logger

_CN_TZ = pytz.timezone("Asia/Shanghai")


def _to_cn_time(record):
    record["extra"]["cn_time"] = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return record


def setup_logger() -> None:
    logger.remove()
    logger.configure(patcher=_to_cn_time)
    logger.add(
        sys.stderr,
        format="<green>{extra[cn_time]}</green> | <level>{level:<7}</level> | "
               "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
        level="INFO",
    )
