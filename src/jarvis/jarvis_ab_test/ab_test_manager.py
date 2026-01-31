"""A/B测试管理器

提供实验分组、指标收集和结果分析功能。
"""

import hashlib
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExperimentStatus(Enum):
    """实验状态"""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MetricType(Enum):
    """指标类型"""

    COUNT = "count"
    SUM = "sum"
    AVERAGE = "average"
    RATIO = "ratio"


@dataclass
class Variant:
    """实验变体"""

    name: str
    weight: float = 1.0
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricData:
    """指标数据"""

    name: str
    metric_type: MetricType
    values: list[float] = field(default_factory=list)


@dataclass
class Experiment:
    """实验配置"""

    name: str
    variants: list[Variant]
    status: ExperimentStatus = ExperimentStatus.DRAFT
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metrics: dict[str, dict[str, MetricData]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ABTestManager:
    """A/B测试管理器"""

    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    def create_experiment(
        self,
        name: str,
        variants: list[Variant],
        description: str = "",
    ) -> Experiment:
        """创建实验"""
        experiment = Experiment(
            name=name,
            variants=variants,
            description=description,
        )
        self._experiments[name] = experiment
        return experiment

    def get_experiment(self, name: str) -> Experiment | None:
        """获取实验"""
        return self._experiments.get(name)

    def start_experiment(self, name: str) -> None:
        """启动实验"""
        experiment = self._experiments.get(name)
        if experiment is None:
            raise ValueError(f"Experiment '{name}' not found")

        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now()

    def pause_experiment(self, name: str) -> None:
        """暂停实验"""
        experiment = self._experiments.get(name)
        if experiment is None:
            raise ValueError(f"Experiment '{name}' not found")

        experiment.status = ExperimentStatus.PAUSED

    def resume_experiment(self, name: str) -> None:
        """恢复实验"""
        experiment = self._experiments.get(name)
        if experiment is None:
            raise ValueError(f"Experiment '{name}' not found")

        experiment.status = ExperimentStatus.RUNNING

    def complete_experiment(self, name: str) -> None:
        """完成实验"""
        experiment = self._experiments.get(name)
        if experiment is None:
            raise ValueError(f"Experiment '{name}' not found")

        experiment.status = ExperimentStatus.COMPLETED
        experiment.ended_at = datetime.now()

    def archive_experiment(self, name: str) -> None:
        """归档实验"""
        experiment = self._experiments.get(name)
        if experiment is None:
            raise ValueError(f"Experiment '{name}' not found")

        experiment.status = ExperimentStatus.ARCHIVED

    def assign_variant(self, experiment_name: str, user_id: str) -> Variant:
        """分配用户到变体（一致性哈希）"""
        experiment = self._experiments.get(experiment_name)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_name}' not found")

        if not experiment.variants:
            raise ValueError(f"Experiment '{experiment_name}' has no variants")

        hash_input = f"{experiment_name}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)

        total_weight = sum(v.weight for v in experiment.variants)
        normalized_value = (hash_value % 10000) / 10000.0 * total_weight

        cumulative_weight = 0.0
        for variant in experiment.variants:
            cumulative_weight += variant.weight
            if normalized_value < cumulative_weight:
                return variant

        return experiment.variants[-1]

    def record_metric(
        self,
        experiment_name: str,
        variant_name: str,
        metric_name: str,
        value: float,
        metric_type: MetricType = MetricType.COUNT,
    ) -> None:
        """记录指标"""
        experiment = self._experiments.get(experiment_name)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_name}' not found")

        if variant_name not in experiment.metrics:
            experiment.metrics[variant_name] = {}

        if metric_name not in experiment.metrics[variant_name]:
            experiment.metrics[variant_name][metric_name] = MetricData(
                name=metric_name,
                metric_type=metric_type,
            )

        experiment.metrics[variant_name][metric_name].values.append(value)

    def get_metric_summary(
        self, experiment_name: str, variant_name: str, metric_name: str
    ) -> dict[str, Any]:
        """获取指标摘要"""
        experiment = self._experiments.get(experiment_name)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_name}' not found")

        if variant_name not in experiment.metrics:
            return {"count": 0, "sum": 0, "average": 0, "min": 0, "max": 0}

        if metric_name not in experiment.metrics[variant_name]:
            return {"count": 0, "sum": 0, "average": 0, "min": 0, "max": 0}

        metric_data = experiment.metrics[variant_name][metric_name]
        values = metric_data.values

        if not values:
            return {"count": 0, "sum": 0, "average": 0, "min": 0, "max": 0}

        return {
            "count": len(values),
            "sum": sum(values),
            "average": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        }

    def compare_variants(
        self, experiment_name: str, metric_name: str
    ) -> dict[str, dict[str, Any]]:
        """比较变体指标"""
        experiment = self._experiments.get(experiment_name)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_name}' not found")

        results: dict[str, dict[str, Any]] = {}
        for variant in experiment.variants:
            results[variant.name] = self.get_metric_summary(
                experiment_name, variant.name, metric_name
            )

        return results

    def get_winner(
        self, experiment_name: str, metric_name: str, higher_is_better: bool = True
    ) -> str | None:
        """获取获胜变体"""
        comparison = self.compare_variants(experiment_name, metric_name)

        if not comparison:
            return None

        best_variant = None
        best_value = None

        for variant_name, summary in comparison.items():
            avg = summary.get("average", 0)
            if best_value is None:
                best_value = avg
                best_variant = variant_name
            elif higher_is_better and avg > best_value:
                best_value = avg
                best_variant = variant_name
            elif not higher_is_better and avg < best_value:
                best_value = avg
                best_variant = variant_name

        return best_variant

    def get_experiment_status(self, name: str) -> dict[str, Any]:
        """获取实验状态"""
        experiment = self._experiments.get(name)
        if experiment is None:
            raise ValueError(f"Experiment '{name}' not found")

        return {
            "name": experiment.name,
            "status": experiment.status.value,
            "variants": [v.name for v in experiment.variants],
            "created_at": experiment.created_at.isoformat(),
            "started_at": (
                experiment.started_at.isoformat() if experiment.started_at else None
            ),
            "ended_at": (
                experiment.ended_at.isoformat() if experiment.ended_at else None
            ),
        }

    def list_experiments(self, status: ExperimentStatus | None = None) -> list[str]:
        """列出实验"""
        if status is None:
            return list(self._experiments.keys())
        return [name for name, exp in self._experiments.items() if exp.status == status]

    def delete_experiment(self, name: str) -> None:
        """删除实验"""
        if name in self._experiments:
            del self._experiments[name]
