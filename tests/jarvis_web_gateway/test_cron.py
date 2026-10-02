# -*- coding: utf-8 -*-
"""cron 表达式解析与下一匹配时间计算测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from jarvis.jarvis_web_gateway.cron import CronParseError
from jarvis.jarvis_web_gateway.cron import cron_next_match
from jarvis.jarvis_web_gateway.cron import parse_cron


def _ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute).timestamp()


def _next(expr: str, from_ts: float) -> datetime:
    return datetime.fromtimestamp(cron_next_match(expr, from_ts))


def test_every_minute() -> None:
    n = _next("* * * * *", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 2, 13, 55)


def test_daily_at_nine() -> None:
    n = _next("0 9 * * *", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 3, 9, 0)


def test_weekly_monday_nine() -> None:
    # 2026-10-02 为周五；日字段为 *，周字段受限 -> 只按周一匹配
    n = _next("0 9 * * 1", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 5, 9, 0)
    assert n.weekday() == 0  # Monday


def test_weekday_zero_is_sunday() -> None:
    # 2026-10-04 是周日
    n = _next("0 0 * * 0", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 4, 0, 0)
    assert n.weekday() == 6  # Sunday


def test_weekday_seven_is_sunday() -> None:
    n = _next("0 0 * * 7", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 4, 0, 0)


def test_day_of_month() -> None:
    n = _next("0 0 1 * *", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 11, 1, 0, 0)


def test_day_or_weekday_both_restricted() -> None:
    # 日字段与周字段都受限 -> OR：每月 1 号 或 周日
    n = _next("0 0 1 * 0", _ts(2026, 10, 2, 13, 54))
    # 2026-10-04 是周日，早于 11-01
    assert n == datetime(2026, 10, 4, 0, 0)


def test_step_minutes() -> None:
    n = _next("*/15 * * * *", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 2, 14, 0)


def test_range_with_step() -> None:
    # 1-59/2 分钟 -> 奇数分钟
    n = _next("1-59/2 * * * *", _ts(2026, 10, 2, 13, 54))
    assert n.minute == 55


def test_list_field() -> None:
    n = _next("5,10,15 * * * *", _ts(2026, 10, 2, 13, 54))
    assert n.minute == 5


def test_leap_year_feb_29() -> None:
    # 2028 是闰年
    n = _next("0 0 29 2 *", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2028, 2, 29, 0, 0)


def test_invalid_month_day_skipped() -> None:
    # 每月 31 号：没有 31 号的月份（如 4 月）会被跳过，直到下一个有 31 号的月份
    n = _next("0 0 31 * *", _ts(2026, 10, 2, 13, 54))
    assert n == datetime(2026, 10, 31, 0, 0)


def test_feb_30_never_matches() -> None:
    # 2 月 30 日永远不存在，应抛 CronParseError
    with pytest.raises(CronParseError):
        cron_next_match("0 0 30 2 *", _ts(2026, 10, 2, 13, 54))


@pytest.mark.parametrize(
    "bad",
    [
        "* * * *",  # 只有 4 段
        "60 * * * *",  # 分越界
        "a * * * *",  # 非法字符
        "0 0 0 * *",  # 日越界
        "*/0 * * * *",  # 步进为 0
        "",  # 空
    ],
)
def test_invalid_expressions_raise(bad: str) -> None:
    with pytest.raises(CronParseError):
        parse_cron(bad)


def test_parse_cron_returns_schedule() -> None:
    schedule = parse_cron("0 9 * * 1")
    assert schedule.expression == "0 9 * * 1"
    assert schedule.minutes == [0]
    assert schedule.hours == [9]
    assert schedule.weekdays == [0]  # 周一
