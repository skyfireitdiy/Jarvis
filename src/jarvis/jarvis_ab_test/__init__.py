"""Jarvis A/B测试机制

提供实验分组、指标收集和结果分析功能。

主要功能：
- 实验管理：创建、启动、停止实验
- 用户分组：基于用户ID的一致性分组
- 指标收集：收集实验指标数据
- 结果分析：统计分析实验结果
"""

from jarvis.jarvis_ab_test.ab_test_manager import (
    ABTestManager,
    Experiment,
    ExperimentStatus,
    Variant,
    MetricType,
)

__all__ = [
    "ABTestManager",
    "Experiment",
    "ExperimentStatus",
    "Variant",
    "MetricType",
]
