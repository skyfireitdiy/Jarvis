"""持续学习管理器模块。

整合知识获取器、技能学习器、经验积累器和自适应引擎，
提供统一的持续学习接口。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from jarvis.jarvis_digital_twin.continuous_learning.adaptive_engine import (
    AdaptiveEngine,
)
from jarvis.jarvis_digital_twin.continuous_learning.experience_accumulator import (
    ExperienceAccumulator,
)
from jarvis.jarvis_digital_twin.continuous_learning.knowledge_acquirer import (
    KnowledgeAcquirer,
)
from jarvis.jarvis_digital_twin.continuous_learning.skill_learner import (
    SkillLearner,
)
from jarvis.jarvis_digital_twin.continuous_learning.types import (
    ExperienceType,
    KnowledgeType,
    SkillType,
)


class ContinuousLearningManager:
    """持续学习管理器。

    整合知识获取器、技能学习器、经验积累器和自适应引擎，
    提供统一的持续学习接口，实现Jarvis的持续学习能力。

    Attributes:
        _knowledge_acquirer: 知识获取器
        _skill_learner: 技能学习器
        _experience_accumulator: 经验积累器
        _adaptive_engine: 自适应引擎
        _enabled: 是否启用
        _learning_history: 学习历史记录
    """

    def __init__(
        self,
        knowledge_acquirer: Optional[KnowledgeAcquirer] = None,
        skill_learner: Optional[SkillLearner] = None,
        experience_accumulator: Optional[ExperienceAccumulator] = None,
        adaptive_engine: Optional[AdaptiveEngine] = None,
    ) -> None:
        """初始化持续学习管理器。

        Args:
            knowledge_acquirer: 知识获取器（可选，默认创建新实例）
            skill_learner: 技能学习器（可选，默认创建新实例）
            experience_accumulator: 经验积累器（可选，默认创建新实例）
            adaptive_engine: 自适应引擎（可选，默认创建新实例）
        """
        self._knowledge_acquirer = knowledge_acquirer or KnowledgeAcquirer()
        self._skill_learner = skill_learner or SkillLearner()
        self._experience_accumulator = experience_accumulator or ExperienceAccumulator()
        self._adaptive_engine = adaptive_engine or AdaptiveEngine()

        self._enabled = True
        self._learning_history: List[Dict[str, Any]] = []
        self._interaction_count = 0
        self._task_count = 0

    @property
    def enabled(self) -> bool:
        """获取管理器启用状态。"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """设置管理器启用状态。"""
        self._enabled = value

    @property
    def knowledge_acquirer(self) -> KnowledgeAcquirer:
        """获取知识获取器。"""
        return self._knowledge_acquirer

    @property
    def skill_learner(self) -> SkillLearner:
        """获取技能学习器。"""
        return self._skill_learner

    @property
    def experience_accumulator(self) -> ExperienceAccumulator:
        """获取经验积累器。"""
        return self._experience_accumulator

    @property
    def adaptive_engine(self) -> AdaptiveEngine:
        """获取自适应引擎。"""
        return self._adaptive_engine

    def learn_from_interaction(
        self,
        user_input: str,
        assistant_response: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """从交互中学习。

        分析用户输入和助手响应，提取知识、技能和经验。

        Args:
            user_input: 用户输入
            assistant_response: 助手响应
            context: 上下文信息（可选）

        Returns:
            学习结果字典，包含：
            - knowledge_learned: 学习到的知识列表
            - skills_learned: 学习到的技能列表
            - experience_recorded: 是否记录了经验
            - adaptations_made: 进行的适应调整
        """
        if not self._enabled:
            return {
                "knowledge_learned": [],
                "skills_learned": [],
                "experience_recorded": False,
                "adaptations_made": [],
            }

        self._interaction_count += 1
        context = context or {}
        result: Dict[str, Any] = {
            "knowledge_learned": [],
            "skills_learned": [],
            "experience_recorded": False,
            "adaptations_made": [],
        }

        # 1. 从交互中提取知识
        try:
            interaction_text = f"User: {user_input}\nAssistant: {assistant_response}"
            knowledge_list = self._knowledge_acquirer.extract_knowledge(
                interaction_text,
                source="interaction",
            )
            result["knowledge_learned"] = [
                {"type": k.type.value, "content": k.content[:100]}
                for k in knowledge_list
            ]
        except Exception:
            pass  # 知识提取失败不影响其他学习

        # 2. 学习使用的工具和模式
        try:
            # 检测响应中使用的工具
            if "<TOOL_CALL>" in assistant_response:
                tool_skill = self._skill_learner.learn_tool(
                    tool_name="tool_call",
                    usage_example=user_input[:200],
                    context="interaction",
                )
                if tool_skill:
                    result["skills_learned"].append(
                        {"type": "tool", "name": tool_skill.name}
                    )

            # 检测代码模式
            if "```" in assistant_response:
                pattern_skill = self._skill_learner.learn_pattern(
                    pattern_name="code_generation",
                    description="代码生成模式",
                    examples=[assistant_response[:200]],
                )
                if pattern_skill:
                    result["skills_learned"].append(
                        {"type": "pattern", "name": pattern_skill.name}
                    )
        except Exception:
            pass  # 技能学习失败不影响其他学习

        # 3. 记录交互经验
        try:
            experience = self._experience_accumulator.record_experience(
                context=f"user_input: {user_input[:500]}",
                outcome=f"response_length: {len(assistant_response)}",
                exp_type=ExperienceType.SUCCESS,
                lessons=[f"responded_to_{self._categorize_input(user_input)}"],
                tags=["interaction"],
                metadata=context,
            )
            result["experience_recorded"] = experience is not None
        except Exception:
            pass  # 经验记录失败不影响其他学习

        # 4. 记录学习历史
        self._learning_history.append(
            {
                "type": "interaction",
                "timestamp": datetime.now().isoformat(),
                "result": result,
            }
        )

        return result

    def learn_from_task_result(
        self,
        task: str,
        result: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """从任务结果中学习。

        分析任务执行结果，提取经验和改进方向。

        Args:
            task: 任务描述
            result: 任务结果
            success: 是否成功
            context: 上下文信息（可选）

        Returns:
            学习结果字典
        """
        if not self._enabled:
            return {
                "experience_recorded": False,
                "methodology_extracted": False,
                "adaptations_made": [],
            }

        self._task_count += 1
        context = context or {}
        learning_result: Dict[str, Any] = {
            "experience_recorded": False,
            "methodology_extracted": False,
            "adaptations_made": [],
        }

        # 1. 记录任务经验
        try:
            exp_type = ExperienceType.SUCCESS if success else ExperienceType.FAILURE
            experience = self._experience_accumulator.record_experience(
                context=f"task: {task[:500]}",
                outcome=result[:500],
                exp_type=exp_type,
                lessons=["execute_task"],
                tags=["task_execution"],
                metadata=context,
            )
            learning_result["experience_recorded"] = experience is not None

            # 2. 从成功任务中提取方法论
            if success and experience:
                # 获取相关经验并提取方法论
                similar_experiences = (
                    self._experience_accumulator.find_similar_experience(
                        context=task[:200],
                        limit=5,
                    )
                )
                if similar_experiences:
                    methodology = self._experience_accumulator.extract_methodology(
                        similar_experiences
                    )
                    learning_result["methodology_extracted"] = bool(
                        methodology.get("patterns") or methodology.get("best_practices")
                    )
        except Exception:
            pass  # 经验记录失败不影响其他学习

        # 3. 根据结果进行适应
        try:
            if not success:
                # 失败时调整策略（降低接受率阈值）
                adaptation = self._adaptive_engine.adapt_to_feedback(
                    feedback_type="acceptance_rate",
                    feedback_value=0.2,  # 低接受率触发调整
                    context="task_failure",
                )
                if adaptation and adaptation.success:
                    learning_result["adaptations_made"].append(
                        {
                            "type": adaptation.adaptation_type.value,
                            "reason": adaptation.reason,
                        }
                    )
        except Exception:
            pass  # 适应失败不影响其他学习

        # 4. 记录学习历史
        self._learning_history.append(
            {
                "type": "task_result",
                "timestamp": datetime.now().isoformat(),
                "success": success,
                "result": learning_result,
            }
        )

        return learning_result

    def get_relevant_knowledge(
        self,
        context: str,
        knowledge_type: Optional[KnowledgeType] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """获取与上下文相关的知识。

        Args:
            context: 查询上下文
            knowledge_type: 知识类型过滤（可选）
            limit: 返回数量限制

        Returns:
            相关知识字典
        """
        result: Dict[str, Any] = {
            "knowledge": [],
            "total_count": 0,
        }

        try:
            # 搜索相关知识
            knowledge_list = self._knowledge_acquirer.search_knowledge(
                query=context,
                limit=limit,
                knowledge_type=knowledge_type,
            )
            result["knowledge"] = [
                {
                    "id": k.id,
                    "type": k.type.value,
                    "content": k.content,
                    "confidence": k.confidence,
                }
                for k in knowledge_list
            ]
            result["total_count"] = len(knowledge_list)
        except Exception:
            pass

        return result

    def get_applicable_skills(
        self,
        context: str,
        skill_type: Optional[SkillType] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """获取适用于当前上下文的技能。

        Args:
            context: 查询上下文
            skill_type: 技能类型过滤（可选）
            limit: 返回数量限制

        Returns:
            适用技能列表
        """
        result: List[Dict[str, Any]] = []

        try:
            # 搜索相关技能
            skills = self._skill_learner.search_skills(
                query=context,
                skill_type=skill_type,
                limit=limit,
            )
            result = [
                {
                    "id": s.id,
                    "name": s.name,
                    "type": s.type.value,
                    "proficiency": s.proficiency,
                }
                for s in skills
            ]
        except Exception:
            pass

        return result

    def get_similar_experiences(
        self,
        context: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """获取与当前上下文相似的经验。

        Args:
            context: 查询上下文
            limit: 返回数量限制

        Returns:
            相似经验列表
        """
        result: List[Dict[str, Any]] = []

        try:
            # 搜索相似经验
            experiences = self._experience_accumulator.find_similar_experience(
                context=context,
                limit=limit,
            )
            result = [
                {
                    "id": e.id,
                    "type": e.type.value,
                    "context": e.context[:100] if e.context else None,
                    "outcome": e.outcome[:100] if e.outcome else None,
                }
                for e in experiences
            ]
        except Exception:
            pass

        return result

    def adapt_behavior(
        self,
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """根据反馈适应行为。

        Args:
            feedback: 反馈信息，包含：
                - type: 反馈类型（positive/negative/neutral）
                - data: 反馈数据

        Returns:
            适应结果字典
        """
        result: Dict[str, Any] = {
            "adapted": False,
            "adaptations": [],
        }

        if not self._enabled:
            return result

        try:
            feedback_type = feedback.get("type", "neutral")
            feedback_data = feedback.get("data", {})

            # 将反馈类型映射到适应引擎的参数
            feedback_value = 0.8 if feedback_type == "positive" else 0.2
            adaptation = self._adaptive_engine.adapt_to_feedback(
                feedback_type="acceptance_rate",
                feedback_value=feedback_value,
                context=str(feedback_data.get("context", "")),
            )

            if adaptation and adaptation.success:
                result["adapted"] = True
                result["adaptations"].append(
                    {
                        "type": adaptation.adaptation_type.value,
                        "reason": adaptation.reason,
                        "old_value": adaptation.old_value,
                        "new_value": adaptation.new_value,
                    }
                )
        except Exception:
            pass

        return result

    def get_learning_statistics(self) -> Dict[str, Any]:
        """获取学习统计信息。

        Returns:
            统计信息字典
        """
        stats: Dict[str, Any] = {
            "enabled": self._enabled,
            "interaction_count": self._interaction_count,
            "task_count": self._task_count,
            "learning_history_count": len(self._learning_history),
            "components": {},
        }

        # 获取各组件统计
        try:
            knowledge_stats = self._knowledge_acquirer.get_statistics()
            stats["components"]["knowledge"] = knowledge_stats
        except Exception:
            stats["components"]["knowledge"] = {"error": "unavailable"}

        try:
            skill_stats = self._skill_learner.get_statistics()
            stats["components"]["skill"] = skill_stats
        except Exception:
            stats["components"]["skill"] = {"error": "unavailable"}

        try:
            experience_stats = self._experience_accumulator.get_statistics()
            stats["components"]["experience"] = experience_stats
        except Exception:
            stats["components"]["experience"] = {"error": "unavailable"}

        try:
            adaptive_stats = self._adaptive_engine.get_statistics()
            stats["components"]["adaptive"] = adaptive_stats
        except Exception:
            stats["components"]["adaptive"] = {"error": "unavailable"}

        return stats

    def export_learnings(self) -> Dict[str, Any]:
        """导出所有学习成果。

        Returns:
            学习成果字典，包含知识、技能、经验和适应配置
        """
        export_data: Dict[str, Any] = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "statistics": self.get_learning_statistics(),
            "knowledge": [],
            "skills": [],
            "experiences": [],
            "adaptations": [],
        }

        # 导出知识
        try:
            all_knowledge = self._knowledge_acquirer.get_all_knowledge()
            export_data["knowledge"] = [
                {
                    "id": k.id,
                    "type": k.type.value,
                    "content": k.content,
                    "source": k.source,
                    "confidence": k.confidence,
                    "created_at": k.created_at.isoformat(),
                }
                for k in all_knowledge
            ]
        except Exception:
            pass

        # 导出技能
        try:
            all_skills = self._skill_learner.get_all_skills()
            export_data["skills"] = [
                {
                    "id": s.id,
                    "name": s.name,
                    "type": s.type.value,
                    "proficiency": s.proficiency,
                    "created_at": s.created_at.isoformat(),
                }
                for s in all_skills
            ]
        except Exception:
            pass

        # 导出经验
        try:
            all_experiences = self._experience_accumulator.get_all_experiences()
            export_data["experiences"] = [
                {
                    "id": e.id,
                    "type": e.type.value,
                    "context": e.context,
                    "outcome": e.outcome,
                    "lessons": e.lessons,
                    "created_at": e.created_at.isoformat(),
                }
                for e in all_experiences
            ]
        except Exception:
            pass

        # 导出适应配置
        try:
            adaptation_history = self._adaptive_engine.get_adaptation_history(limit=100)
            export_data["adaptations"] = [
                {
                    "id": a.id,
                    "type": a.adaptation_type.value,
                    "success": a.success,
                    "reason": a.reason,
                    "timestamp": a.timestamp.isoformat(),
                }
                for a in adaptation_history
            ]
        except Exception:
            pass

        return export_data

    def import_learnings(self, data: Dict[str, Any]) -> bool:
        """导入学习成果。

        Args:
            data: 学习成果数据（由export_learnings导出）

        Returns:
            是否导入成功
        """
        if not data or "version" not in data:
            return False

        success = True

        # 导入知识 - 使用extract_knowledge间接添加
        try:
            for k_data in data.get("knowledge", []):
                # 通过extract_knowledge添加知识
                self._knowledge_acquirer.extract_knowledge(
                    context=k_data["content"],
                    source=k_data.get("source", "import"),
                )
        except Exception:
            success = False

        # 导入技能 - 使用learn_tool或learn_pattern
        try:
            for s_data in data.get("skills", []):
                skill_type = s_data.get("type", "tool_usage")
                if skill_type == "tool_usage":
                    self._skill_learner.learn_tool(
                        tool_name=s_data["name"],
                        usage_example="imported",
                        context="import",
                    )
                else:
                    self._skill_learner.learn_pattern(
                        pattern_name=s_data["name"],
                        description=s_data.get("description", "imported pattern"),
                        examples=["imported"],
                    )
        except Exception:
            success = False

        # 导入经验
        try:
            for e_data in data.get("experiences", []):
                exp_type_str = e_data.get("type", "success")
                exp_type = ExperienceType(exp_type_str)
                self._experience_accumulator.record_experience(
                    context=e_data.get("context", ""),
                    outcome=e_data.get("outcome", ""),
                    exp_type=exp_type,
                    lessons=e_data.get("lessons", []),
                )
        except Exception:
            success = False

        return success

    def _categorize_input(self, user_input: str) -> str:
        """对用户输入进行分类。

        Args:
            user_input: 用户输入

        Returns:
            输入类别
        """
        user_input_lower = user_input.lower()

        if any(kw in user_input_lower for kw in ["fix", "bug", "error", "issue"]):
            return "bug_fix"
        elif any(
            kw in user_input_lower for kw in ["add", "create", "implement", "new"]
        ):
            return "feature_request"
        elif any(kw in user_input_lower for kw in ["refactor", "improve", "optimize"]):
            return "refactoring"
        elif any(kw in user_input_lower for kw in ["explain", "what", "how", "why"]):
            return "question"
        elif any(kw in user_input_lower for kw in ["test", "verify", "check"]):
            return "testing"
        else:
            return "general"
