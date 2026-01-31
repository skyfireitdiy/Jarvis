"""灰度发布管理器

提供渐进式发布、流量分配和回滚功能。
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class ReleaseStage(Enum):
    """发布阶段"""

    CREATED = "created"
    CANARY = "canary"
    ROLLING = "rolling"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    PAUSED = "paused"


class RolloutStrategy(Enum):
    """发布策略"""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    MANUAL = "manual"


@dataclass
class TrafficRule:
    """流量规则"""

    name: str
    condition: Callable[[dict[str, Any]], bool]
    target_version: str
    priority: int = 0
    enabled: bool = True


@dataclass
class CanaryRelease:
    """灰度发布配置"""

    name: str
    stable_version: str
    canary_version: str
    traffic_percentage: float = 0.0
    stage: ReleaseStage = ReleaseStage.CREATED
    strategy: RolloutStrategy = RolloutStrategy.LINEAR
    step_percentage: float = 10.0
    max_percentage: float = 100.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    rules: list[TrafficRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CanaryManager:
    """灰度发布管理器"""

    def __init__(self) -> None:
        self._releases: dict[str, CanaryRelease] = {}
        self._handlers: dict[str, dict[str, Callable[..., Any]]] = {}

    def create_release(
        self,
        name: str,
        stable_version: str,
        canary_version: str,
        strategy: RolloutStrategy = RolloutStrategy.LINEAR,
        step_percentage: float = 10.0,
    ) -> CanaryRelease:
        """创建灰度发布"""
        release = CanaryRelease(
            name=name,
            stable_version=stable_version,
            canary_version=canary_version,
            strategy=strategy,
            step_percentage=step_percentage,
        )
        self._releases[name] = release
        return release

    def get_release(self, name: str) -> CanaryRelease | None:
        """获取发布配置"""
        return self._releases.get(name)

    def start_canary(self, name: str, initial_percentage: float = 5.0) -> None:
        """开始灰度发布"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        release.traffic_percentage = initial_percentage
        release.stage = ReleaseStage.CANARY
        release.updated_at = datetime.now()

    def increase_traffic(self, name: str, percentage: float | None = None) -> float:
        """增加灰度流量"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        if percentage is None:
            if release.strategy == RolloutStrategy.LINEAR:
                percentage = release.step_percentage
            elif release.strategy == RolloutStrategy.EXPONENTIAL:
                percentage = release.traffic_percentage
            else:
                percentage = release.step_percentage

        new_percentage = min(
            release.traffic_percentage + percentage, release.max_percentage
        )
        release.traffic_percentage = new_percentage
        release.updated_at = datetime.now()

        if new_percentage >= release.max_percentage:
            release.stage = ReleaseStage.ROLLING

        return new_percentage

    def complete_release(self, name: str) -> None:
        """完成发布"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        release.traffic_percentage = 100.0
        release.stage = ReleaseStage.COMPLETED
        release.updated_at = datetime.now()

    def rollback(self, name: str) -> None:
        """回滚发布"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        release.traffic_percentage = 0.0
        release.stage = ReleaseStage.ROLLED_BACK
        release.updated_at = datetime.now()

    def pause(self, name: str) -> None:
        """暂停发布"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        release.stage = ReleaseStage.PAUSED
        release.updated_at = datetime.now()

    def resume(self, name: str) -> None:
        """恢复发布"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        if release.traffic_percentage < release.max_percentage:
            release.stage = ReleaseStage.CANARY
        else:
            release.stage = ReleaseStage.ROLLING
        release.updated_at = datetime.now()

    def add_rule(self, name: str, rule: TrafficRule) -> None:
        """添加流量规则"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        release.rules.append(rule)
        release.rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str, rule_name: str) -> None:
        """移除流量规则"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        release.rules = [r for r in release.rules if r.name != rule_name]

    def register_handler(
        self, name: str, version: str, handler: Callable[..., Any]
    ) -> None:
        """注册版本处理器"""
        if name not in self._handlers:
            self._handlers[name] = {}
        self._handlers[name][version] = handler

    def route(self, name: str, context: dict[str, Any] | None = None) -> str:
        """路由请求到目标版本"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        context = context or {}

        for rule in release.rules:
            if rule.enabled and rule.condition(context):
                return rule.target_version

        if random.random() * 100 < release.traffic_percentage:
            return release.canary_version
        return release.stable_version

    def call(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """调用路由后的处理器"""
        version = self.route(name, context)

        if name not in self._handlers:
            raise ValueError(f"No handlers registered for '{name}'")

        if version not in self._handlers[name]:
            raise ValueError(f"Handler for version '{version}' not found")

        return self._handlers[name][version](*args, **kwargs)

    def get_status(self, name: str) -> dict[str, Any]:
        """获取发布状态"""
        release = self._releases.get(name)
        if release is None:
            raise ValueError(f"Release '{name}' not found")

        return {
            "name": release.name,
            "stable_version": release.stable_version,
            "canary_version": release.canary_version,
            "traffic_percentage": release.traffic_percentage,
            "stage": release.stage.value,
            "strategy": release.strategy.value,
            "rules_count": len(release.rules),
            "created_at": release.created_at.isoformat(),
            "updated_at": release.updated_at.isoformat(),
        }

    def list_releases(self) -> list[str]:
        """列出所有发布"""
        return list(self._releases.keys())

    def delete_release(self, name: str) -> None:
        """删除发布"""
        if name in self._releases:
            del self._releases[name]
        if name in self._handlers:
            del self._handlers[name]
