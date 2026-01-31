"""Jarvis灰度发布机制

提供渐进式发布、流量分配和回滚功能。

主要功能：
- 流量分配：按比例分配流量到不同版本
- 渐进式发布：逐步增加新版本流量
- 回滚机制：快速回滚到稳定版本
- 规则路由：基于规则的流量控制
"""

from jarvis.jarvis_canary.canary_manager import (
    CanaryManager,
    CanaryRelease,
    ReleaseStage,
    TrafficRule,
    RolloutStrategy,
)

__all__ = [
    "CanaryManager",
    "CanaryRelease",
    "ReleaseStage",
    "TrafficRule",
    "RolloutStrategy",
]
