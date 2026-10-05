# -*- coding: utf-8 -*-
"""轻量级 5 段 cron 表达式解析与下一匹配时间计算（零第三方依赖）。

支持标准 5 段格式：``分 时 日 月 周``

- 分：0-59
- 时：0-23
- 日：1-31
- 月：1-12
- 周：0-7（0 与 7 均表示周日）

字段语法支持：

- ``*``：任意值
- 数字：如 ``5``
- 范围：如 ``1-5``
- 步进：如 ``*/15``、``1-59/2``
- 列表：如 ``1,15,30``（可混合上述形式）

语义：**日与周为 OR 关系**（与标准 cron 一致），即日期字段或星期字段任一匹配即触发。
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import List, Optional


# 各字段的取值范围（用于校验）
_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 7),
}

# 扫描上限：最多向前扫描 5 年（分钟粒度），足以覆盖任意 cron 表达式的下一匹配点。
_MAX_SCAN_MINUTES = 5 * 366 * 24 * 60


class CronParseError(ValueError):
    """cron 表达式解析错误。"""


def _parse_field(field: str, field_name: str) -> List[int]:
    """解析单个 cron 字段，返回其匹配的取值集合（升序去重）。"""
    lo, hi = _FIELD_RANGES[field_name]
    values: set[int] = set()

    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronParseError(f"empty field part in '{field_name}'")
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                raise CronParseError(f"invalid step '{step_str}' in '{field_name}'")
            if step <= 0:
                raise CronParseError(f"step must be > 0 in '{field_name}'")
        else:
            base = part

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            start_str, end_str = base.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                raise CronParseError(f"invalid range '{base}' in '{field_name}'")
        else:
            try:
                start = int(base)
            except ValueError:
                raise CronParseError(f"invalid value '{base}' in '{field_name}'")
            end = start

        if start < lo or end > hi:
            raise CronParseError(
                f"value out of range in '{field_name}': {base} (allowed {lo}-{hi})"
            )
        if start > end:
            raise CronParseError(f"range start > end in '{field_name}': {base}")

        values.update(range(start, end + 1, step))

    if not values:
        raise CronParseError(f"no valid values in '{field_name}'")
    return sorted(values)


class CronSchedule:
    """解析后的 cron 表达式。"""

    def __init__(self, expression: str) -> None:
        self.expression = expression
        fields = expression.split()
        if len(fields) != 5:
            raise CronParseError(
                f"cron expression must have 5 fields (minute hour day month weekday), got {len(fields)}: {expression!r}"
            )
        self.minutes = _parse_field(fields[0], "minute")
        self.hours = _parse_field(fields[1], "hour")
        self.days = _parse_field(fields[2], "day")
        self.months = _parse_field(fields[3], "month")
        # 周字段 0-7：0 与 7 均为周日。转换为 Python weekday（0=周一..6=周日）：
        # cron 值 w -> (w - 1) % 7，即 1->0(周一) ... 7->6(周日)，0->6(周日)。
        self.weekdays = sorted(
            {(w - 1) % 7 for w in _parse_field(fields[4], "weekday")}
        )
        # 记录日/周字段是否受限（非 *），用于日与周的 Vixie cron 语义：
        # 若一个字段为 *、另一个受限，则 * 字段被忽略，只按受限字段匹配；
        # 若两者都受限，则取 OR（任一匹配即触发）；两者都 * 则每天。
        self._day_restricted = fields[2].strip() != "*"
        self._weekday_restricted = fields[4].strip() != "*"

    def matches(self, dt: datetime) -> bool:
        """判断给定时间是否匹配该 cron 表达式。"""
        if dt.minute not in self.minutes:
            return False
        if dt.hour not in self.hours:
            return False
        if dt.month not in self.months:
            return False
        day_match = dt.day in self.days
        weekday_match = dt.weekday() in self.weekdays
        if self._day_restricted and self._weekday_restricted:
            # 两者都受限：OR 语义
            return day_match or weekday_match
        if self._day_restricted:
            # 仅日字段受限：只按日匹配
            return day_match
        if self._weekday_restricted:
            # 仅周字段受限：只按周匹配
            return weekday_match
        # 两者都 *：每天
        return True

    def _day_matches(self, dt: datetime) -> bool:
        """判断给定日期（忽略分/时）是否满足 cron 的日级条件。

        与 :meth:`matches` 中除 minute/hour 外的判定逻辑保持一致。
        """
        if dt.month not in self.months:
            return False
        day_match = dt.day in self.days
        weekday_match = dt.weekday() in self.weekdays
        if self._day_restricted and self._weekday_restricted:
            return day_match or weekday_match
        if self._day_restricted:
            return day_match
        if self._weekday_restricted:
            return weekday_match
        return True

    def _first_match_in_day(
        self, day: datetime, from_candidate: datetime
    ) -> Optional[datetime]:
        """返回 ``day`` 当天内 ``>= from_candidate`` 的第一个匹配时刻；无则返回 None。

        前提：``day`` 的日级条件已满足（``_day_matches(day)`` 为 True）。
        """
        for hour in self.hours:
            for minute in self.minutes:
                dt = day.replace(hour=hour, minute=minute)
                if dt >= from_candidate and self.matches(dt):
                    return dt
        return None

    def next_match(self, from_ts: float) -> float:
        """返回严格大于 from_ts 的下一个匹配时间戳。"""
        base = datetime.fromtimestamp(from_ts)
        # 从 from_ts 的下一个整分钟开始扫描
        candidate = (base + timedelta(minutes=1)).replace(second=0, microsecond=0)

        # 按天跳跃扫描：同一天内 month/day/weekday 不变，只有 minute/hour 变化。
        # 对每个"日级条件满足"的天，直接计算该天第一个匹配时刻，避免逐分钟扫描；
        # 对"日级条件不满足"的天（如 2 月 30 日），整段跳过，避免扫描 5 年。
        scanned = 0
        while scanned < _MAX_SCAN_MINUTES:
            if not self._day_matches(candidate):
                next_day = (candidate + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                scanned += int((next_day - candidate).total_seconds() // 60)
                candidate = next_day
                continue
            # 日级条件满足：计算当天第一个匹配时刻
            day_start = candidate.replace(hour=0, minute=0, second=0, microsecond=0)
            first = self._first_match_in_day(day_start, candidate)
            if first is not None and first >= candidate:
                return first.timestamp()
            # 当天无匹配或匹配时刻已过，跳到下一天
            next_day = (day_start + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            scanned += int((next_day - candidate).total_seconds() // 60)
            candidate = next_day
        raise CronParseError(
            f"no matching time found within scan window for cron: {self.expression!r}"
        )


def parse_cron(expression: str) -> CronSchedule:
    """解析 cron 表达式，非法时抛 :class:`CronParseError`。"""
    if not isinstance(expression, str) or not expression.strip():
        raise CronParseError("cron expression must be a non-empty string")
    return CronSchedule(expression)


def cron_next_match(expression: str, from_ts: float) -> float:
    """便捷函数：返回 cron 表达式在 from_ts 之后的下一个匹配时间戳。"""
    return parse_cron(expression).next_match(from_ts)
