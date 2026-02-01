"""服务编排器模块。

负责管理多个服务的优先级和冲突解决，生成执行计划。
支持与NeedInferrer集成进行智能编排。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from jarvis.jarvis_digital_twin.prediction import (
    InferenceResult,
    NeedInferrer,
    PredictionContext,
)
from jarvis.jarvis_digital_twin.proactive_service.types import (
    ConflictResolution,
    ExecutionPlan,
    ServiceDefinition,
    ServicePriority,
    ServiceType,
    TriggerContext,
)


# 优先级权重映射
PRIORITY_WEIGHTS: Dict[ServicePriority, int] = {
    ServicePriority.CRITICAL: 100,
    ServicePriority.HIGH: 80,
    ServicePriority.MEDIUM: 60,
    ServicePriority.LOW: 40,
    ServicePriority.BACKGROUND: 20,
}


@dataclass
class ConflictRule:
    """冲突规则数据类。

    定义两种服务类型之间的冲突解决规则。
    """

    # 服务类型A
    service_type_a: ServiceType
    # 服务类型B
    service_type_b: ServiceType
    # 解决策略
    resolution: ConflictResolution
    # 创建时间
    created_at: datetime = field(default_factory=datetime.now)


class ServiceOrchestrator:
    """服务编排器。

    负责管理多个服务的优先级和冲突解决，生成执行计划。
    支持与NeedInferrer集成进行智能编排。
    """

    # 默认冲突规则：同类型服务默认保留最高优先级
    DEFAULT_SAME_TYPE_RESOLUTION = ConflictResolution.KEEP_HIGHEST_PRIORITY

    # 互斥服务类型对
    MUTUALLY_EXCLUSIVE_TYPES: Set[Tuple[ServiceType, ServiceType]] = {
        (ServiceType.AUTO_ACTION, ServiceType.CLARIFICATION),
        (ServiceType.SUGGESTION, ServiceType.AUTO_ACTION),
    }

    def __init__(self, need_inferrer: Optional[NeedInferrer] = None) -> None:
        """初始化编排器。

        Args:
            need_inferrer: 需求推理器（来自阶段5.2）
        """
        self._need_inferrer = need_inferrer
        # 冲突规则
        self._conflict_rules: Dict[Tuple[ServiceType, ServiceType], ConflictRule] = {}
        # 初始化默认冲突规则
        self._init_default_conflict_rules()

    def _init_default_conflict_rules(self) -> None:
        """初始化默认冲突规则。"""
        # 互斥类型默认取消两者
        for type_a, type_b in self.MUTUALLY_EXCLUSIVE_TYPES:
            self._conflict_rules[(type_a, type_b)] = ConflictRule(
                service_type_a=type_a,
                service_type_b=type_b,
                resolution=ConflictResolution.CANCEL_BOTH,
            )
            # 双向注册
            self._conflict_rules[(type_b, type_a)] = ConflictRule(
                service_type_a=type_b,
                service_type_b=type_a,
                resolution=ConflictResolution.CANCEL_BOTH,
            )

    @property
    def conflict_rules(self) -> Dict[Tuple[ServiceType, ServiceType], ConflictRule]:
        """获取冲突规则。"""
        return self._conflict_rules.copy()

    def set_need_inferrer(self, need_inferrer: NeedInferrer) -> None:
        """设置需求推理器。

        Args:
            need_inferrer: 需求推理器
        """
        self._need_inferrer = need_inferrer

    def register_conflict_rule(
        self,
        service_type_a: ServiceType,
        service_type_b: ServiceType,
        resolution: ConflictResolution,
    ) -> None:
        """注册冲突解决规则。

        Args:
            service_type_a: 服务类型A
            service_type_b: 服务类型B
            resolution: 解决策略
        """
        rule = ConflictRule(
            service_type_a=service_type_a,
            service_type_b=service_type_b,
            resolution=resolution,
        )
        self._conflict_rules[(service_type_a, service_type_b)] = rule
        # 双向注册（除非是同类型）
        if service_type_a != service_type_b:
            reverse_rule = ConflictRule(
                service_type_a=service_type_b,
                service_type_b=service_type_a,
                resolution=resolution,
            )
            self._conflict_rules[(service_type_b, service_type_a)] = reverse_rule

    def unregister_conflict_rule(
        self,
        service_type_a: ServiceType,
        service_type_b: ServiceType,
    ) -> bool:
        """取消注册冲突规则。

        Args:
            service_type_a: 服务类型A
            service_type_b: 服务类型B

        Returns:
            是否成功取消
        """
        key = (service_type_a, service_type_b)
        reverse_key = (service_type_b, service_type_a)

        removed = False
        if key in self._conflict_rules:
            del self._conflict_rules[key]
            removed = True
        if reverse_key in self._conflict_rules:
            del self._conflict_rules[reverse_key]
            removed = True

        return removed

    def orchestrate(
        self,
        triggered_services: List[ServiceDefinition],
        context: TriggerContext,
    ) -> List[ServiceDefinition]:
        """编排服务执行顺序。

        Args:
            triggered_services: 已触发的服务列表
            context: 触发上下文

        Returns:
            排序后的服务执行列表
        """
        if not triggered_services:
            return []

        # 1. 解决冲突
        resolved_services = self.resolve_conflicts(triggered_services)

        # 2. 按优先级排序
        prioritized_services = self.prioritize(resolved_services, context)

        # 3. 如果有NeedInferrer，进行智能调整
        if self._need_inferrer:
            prioritized_services = self._apply_intelligent_ordering(
                prioritized_services, context
            )

        return prioritized_services

    def resolve_conflicts(
        self,
        services: List[ServiceDefinition],
    ) -> List[ServiceDefinition]:
        """解决服务冲突。

        Args:
            services: 服务列表

        Returns:
            去除冲突后的服务列表
        """
        if len(services) <= 1:
            return services.copy()

        # 按服务类型分组
        type_groups: Dict[ServiceType, List[ServiceDefinition]] = {}
        for service in services:
            if service.service_type not in type_groups:
                type_groups[service.service_type] = []
            type_groups[service.service_type].append(service)

        # 处理同类型冲突
        resolved_by_type: Dict[ServiceType, List[ServiceDefinition]] = {}
        for service_type, group in type_groups.items():
            if len(group) > 1:
                # 同类型冲突，保留最高优先级
                resolved = self._resolve_same_type_conflict(group)
                resolved_by_type[service_type] = resolved
            else:
                resolved_by_type[service_type] = group

        # 处理跨类型冲突
        all_resolved: List[ServiceDefinition] = []
        processed_types: Set[ServiceType] = set()

        for service_type, group in resolved_by_type.items():
            if service_type in processed_types:
                continue

            # 检查与其他类型的冲突
            conflicting_types = self._find_conflicting_types(
                service_type, set(resolved_by_type.keys()) - processed_types
            )

            if conflicting_types:
                # 有冲突，需要解决
                for conflict_type in conflicting_types:
                    if conflict_type in processed_types:
                        continue

                    conflict_group = resolved_by_type.get(conflict_type, [])
                    resolved = self._resolve_cross_type_conflict(
                        group, conflict_group, service_type, conflict_type
                    )
                    # 更新组
                    group = [s for s in resolved if s.service_type == service_type]
                    conflict_resolved = [
                        s for s in resolved if s.service_type == conflict_type
                    ]
                    # 添加冲突类型的解决结果
                    all_resolved.extend(conflict_resolved)
                    processed_types.add(conflict_type)

            all_resolved.extend(group)
            processed_types.add(service_type)

        # 添加未处理的类型
        for service_type, group in resolved_by_type.items():
            if service_type not in processed_types:
                all_resolved.extend(group)

        return all_resolved

    def _resolve_same_type_conflict(
        self,
        services: List[ServiceDefinition],
    ) -> List[ServiceDefinition]:
        """解决同类型服务冲突。

        Args:
            services: 同类型服务列表

        Returns:
            解决冲突后的服务列表
        """
        if len(services) <= 1:
            return services

        resolution = self.DEFAULT_SAME_TYPE_RESOLUTION

        if resolution == ConflictResolution.KEEP_FIRST:
            return [services[0]]
        elif resolution == ConflictResolution.KEEP_LAST:
            return [services[-1]]
        elif resolution == ConflictResolution.KEEP_HIGHEST_PRIORITY:
            # 按优先级排序，保留最高的
            sorted_services = sorted(
                services,
                key=lambda s: PRIORITY_WEIGHTS.get(s.priority, 0),
                reverse=True,
            )
            return [sorted_services[0]]
        elif resolution == ConflictResolution.MERGE:
            # 合并：保留所有
            return services
        elif resolution == ConflictResolution.CANCEL_BOTH:
            return []

        return services  # type: ignore[unreachable]

    def _find_conflicting_types(
        self,
        service_type: ServiceType,
        other_types: Set[ServiceType],
    ) -> Set[ServiceType]:
        """查找与指定类型冲突的其他类型。

        Args:
            service_type: 服务类型
            other_types: 其他类型集合

        Returns:
            冲突的类型集合
        """
        conflicting: Set[ServiceType] = set()

        for other_type in other_types:
            key = (service_type, other_type)
            if key in self._conflict_rules:
                conflicting.add(other_type)

        return conflicting

    def _resolve_cross_type_conflict(
        self,
        group_a: List[ServiceDefinition],
        group_b: List[ServiceDefinition],
        type_a: ServiceType,
        type_b: ServiceType,
    ) -> List[ServiceDefinition]:
        """解决跨类型服务冲突。

        Args:
            group_a: 类型A的服务列表
            group_b: 类型B的服务列表
            type_a: 服务类型A
            type_b: 服务类型B

        Returns:
            解决冲突后的服务列表
        """
        key = (type_a, type_b)
        rule = self._conflict_rules.get(key)

        if not rule:
            # 无冲突规则，保留所有
            return group_a + group_b

        resolution = rule.resolution

        if resolution == ConflictResolution.KEEP_FIRST:
            return group_a
        elif resolution == ConflictResolution.KEEP_LAST:
            return group_b
        elif resolution == ConflictResolution.KEEP_HIGHEST_PRIORITY:
            # 比较两组中最高优先级的服务
            all_services = group_a + group_b
            if not all_services:
                return []
            sorted_services = sorted(
                all_services,
                key=lambda s: PRIORITY_WEIGHTS.get(s.priority, 0),
                reverse=True,
            )
            highest_priority = sorted_services[0].priority
            return [s for s in sorted_services if s.priority == highest_priority]
        elif resolution == ConflictResolution.MERGE:
            return group_a + group_b
        elif resolution == ConflictResolution.CANCEL_BOTH:
            return []

        return group_a + group_b  # type: ignore[unreachable]

    def prioritize(
        self,
        services: List[ServiceDefinition],
        context: Optional[TriggerContext] = None,
    ) -> List[ServiceDefinition]:
        """按优先级排序服务。

        Args:
            services: 服务列表
            context: 触发上下文（可选，用于上下文感知排序）

        Returns:
            排序后的服务列表
        """
        if not services:
            return []

        # 计算每个服务的综合分数
        scored_services: List[Tuple[ServiceDefinition, float]] = []

        for service in services:
            score = self._calculate_priority_score(service, context)
            scored_services.append((service, score))

        # 按分数降序排序
        scored_services.sort(key=lambda x: x[1], reverse=True)

        return [service for service, _ in scored_services]

    def _calculate_priority_score(
        self,
        service: ServiceDefinition,
        context: Optional[TriggerContext] = None,
    ) -> float:
        """计算服务的优先级分数。

        Args:
            service: 服务定义
            context: 触发上下文

        Returns:
            优先级分数
        """
        # 基础分数：优先级权重
        base_score = float(PRIORITY_WEIGHTS.get(service.priority, 0))

        # 上下文调整
        context_bonus = 0.0
        if context:
            # 如果用户输入包含服务相关关键词，增加分数
            user_input_lower = context.user_input.lower()
            for condition in service.trigger_conditions:
                if condition.lower() in user_input_lower:
                    context_bonus += 5.0
                    break

            # 如果有用户画像，根据偏好调整
            if context.user_profile:
                # 简单的偏好匹配
                context_bonus += 2.0

        return base_score + context_bonus

    def _apply_intelligent_ordering(
        self,
        services: List[ServiceDefinition],
        context: TriggerContext,
    ) -> List[ServiceDefinition]:
        """应用智能排序（使用NeedInferrer）。

        Args:
            services: 服务列表
            context: 触发上下文

        Returns:
            智能排序后的服务列表
        """
        if not self._need_inferrer or not services:
            return services

        # 将TriggerContext转换为PredictionContext
        prediction_context = PredictionContext(
            current_message=context.user_input,
            conversation_history=context.conversation_history,
            user_profile=context.user_profile or {},
        )

        # 获取推理结果
        try:
            inferences = self._need_inferrer.infer_implicit_needs(
                prediction_context, context.user_input
            )
        except Exception:
            # 推理失败，返回原列表
            return services

        if not inferences:
            return services

        # 根据推理结果调整服务顺序
        return self._adjust_order_by_inferences(services, inferences)

    def _adjust_order_by_inferences(
        self,
        services: List[ServiceDefinition],
        inferences: List[InferenceResult],
    ) -> List[ServiceDefinition]:
        """根据推理结果调整服务顺序。

        Args:
            services: 服务列表
            inferences: 推理结果列表

        Returns:
            调整后的服务列表
        """
        # 提取推理内容关键词
        inference_keywords: Set[str] = set()
        for inference in inferences:
            # 将推理内容分词
            words = inference.content.lower().replace("_", " ").split()
            inference_keywords.update(words)

        # 计算每个服务与推理结果的相关性
        relevance_scores: Dict[str, float] = {}
        for service in services:
            score = 0.0
            # 检查服务名称和描述与推理关键词的匹配
            service_text = f"{service.name} {service.description}".lower()
            for keyword in inference_keywords:
                if keyword in service_text:
                    score += 1.0

            # 检查触发条件
            for condition in service.trigger_conditions:
                if condition.lower() in inference_keywords:
                    score += 2.0

            relevance_scores[service.service_id] = score

        # 按相关性分数排序（相关性高的优先）
        # 但保持原有优先级作为次要排序依据
        def sort_key(s: ServiceDefinition) -> Tuple[float, int]:
            relevance = relevance_scores.get(s.service_id, 0.0)
            priority = PRIORITY_WEIGHTS.get(s.priority, 0)
            return (relevance, priority)

        return sorted(services, key=sort_key, reverse=True)

    def get_execution_plan(
        self,
        services: List[ServiceDefinition],
    ) -> ExecutionPlan:
        """生成执行计划。

        Args:
            services: 服务列表

        Returns:
            执行计划
        """
        if not services:
            return ExecutionPlan()

        # 确定执行顺序
        execution_order = [s.service_id for s in services]

        # 确定可并行执行的组
        parallel_groups = self._determine_parallel_groups(services)

        # 估算执行时间
        estimated_duration = self._estimate_duration(services, parallel_groups)

        return ExecutionPlan(
            services=services.copy(),
            execution_order=execution_order,
            parallel_groups=parallel_groups,
            estimated_duration_ms=estimated_duration,
        )

    def _determine_parallel_groups(
        self,
        services: List[ServiceDefinition],
    ) -> List[List[str]]:
        """确定可并行执行的服务组。

        Args:
            services: 服务列表

        Returns:
            并行组列表
        """
        if not services:
            return []

        # 按服务类型分组
        type_groups: Dict[ServiceType, List[str]] = {}
        for service in services:
            if service.service_type not in type_groups:
                type_groups[service.service_type] = []
            type_groups[service.service_type].append(service.service_id)

        # 不同类型的服务可以并行执行（除非有冲突规则）
        parallel_groups: List[List[str]] = []
        processed_types: Set[ServiceType] = set()

        for service_type, service_ids in type_groups.items():
            if service_type in processed_types:
                continue

            # 查找可以与当前类型并行的其他类型
            parallel_type_ids = list(service_ids)
            processed_types.add(service_type)

            for other_type, other_ids in type_groups.items():
                if other_type in processed_types:
                    continue

                # 检查是否有冲突规则
                key = (service_type, other_type)
                if key not in self._conflict_rules:
                    # 无冲突，可以并行
                    parallel_type_ids.extend(other_ids)
                    processed_types.add(other_type)

            if parallel_type_ids:
                parallel_groups.append(parallel_type_ids)

        # 添加未处理的类型
        for service_type, service_ids in type_groups.items():
            if service_type not in processed_types:
                parallel_groups.append(service_ids)

        return parallel_groups

    def _estimate_duration(
        self,
        services: List[ServiceDefinition],
        parallel_groups: List[List[str]],
    ) -> int:
        """估算执行时间。

        Args:
            services: 服务列表
            parallel_groups: 并行组列表

        Returns:
            预估执行时间（毫秒）
        """
        if not services:
            return 0

        # 基础执行时间（每个服务100ms）
        base_time_per_service = 100

        # 如果有并行组，取最大组的时间
        if parallel_groups:
            max_group_size = max(len(group) for group in parallel_groups)
            # 并行执行时，时间取决于最大组
            total_time = len(parallel_groups) * base_time_per_service
            # 加上并行组内的额外开销
            total_time += max_group_size * 10
        else:
            # 串行执行
            total_time = len(services) * base_time_per_service

        return total_time

    def get_service_stats(
        self,
        services: List[ServiceDefinition],
    ) -> Dict[str, Any]:
        """获取服务统计信息。

        Args:
            services: 服务列表

        Returns:
            统计信息字典
        """
        type_counts: Dict[str, int] = {}
        priority_counts: Dict[str, int] = {}

        for service in services:
            # 按类型统计
            type_name = service.service_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            # 按优先级统计
            priority_name = service.priority.value
            priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1

        stats: Dict[str, Any] = {
            "total": len(services),
            "by_type": type_counts,
            "by_priority": priority_counts,
        }

        return stats
