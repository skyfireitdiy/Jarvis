"""经验积累器模块。

负责记录和复用经验，支持经验分类和检索。
与memory模块集成，实现经验的持久化存储。
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from jarvis.jarvis_digital_twin.continuous_learning.types import (
    Experience,
    ExperienceMatcherProtocol,
    ExperienceType,
    LearningStatus,
)


@dataclass
class ExperienceRecord:
    """经验记录数据类。

    用于内部存储经验及其状态。
    """

    experience: Experience
    status: LearningStatus = LearningStatus.LEARNED
    content_hash: str = ""
    apply_count: int = 0
    success_count: int = 0
    last_applied_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """初始化后计算内容哈希。"""
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """计算经验内容的哈希值。"""
        content = f"{self.experience.type.value}:{self.experience.context}:{self.experience.outcome}"
        return hashlib.md5(content.encode()).hexdigest()


class KeywordMatcher:
    """基于关键词的经验匹配器。"""

    def __init__(self, min_keyword_length: int = 3) -> None:
        self._min_keyword_length = min_keyword_length
        self._experiences: List[Experience] = []

    def set_experiences(self, experiences: List[Experience]) -> None:
        self._experiences = experiences

    def match(self, context: str) -> List[Experience]:
        if not context or not self._experiences:
            return []
        keywords = self._extract_keywords(context)
        if not keywords:
            return []
        results: List[tuple[Experience, int]] = []
        for exp in self._experiences:
            match_count = 0
            exp_text = f"{exp.context} {exp.outcome} {' '.join(exp.lessons)}".lower()
            for keyword in keywords:
                if keyword in exp_text:
                    match_count += 1
            if match_count > 0:
                results.append((exp, match_count))
        results.sort(key=lambda x: x[1], reverse=True)
        return [exp for exp, _ in results]

    def _extract_keywords(self, text: str) -> Set[str]:
        words = re.split(r'[\s,;.!?()\[\]{}"\':]+', text.lower())
        return {w for w in words if len(w) >= self._min_keyword_length and w.isalnum()}


class ContextSimilarityMatcher:
    """基于上下文相似度的经验匹配器。"""

    def __init__(self, similarity_threshold: float = 0.3) -> None:
        self._threshold = similarity_threshold
        self._experiences: List[Experience] = []

    def set_experiences(self, experiences: List[Experience]) -> None:
        self._experiences = experiences

    def match(self, context: str) -> List[Experience]:
        if not context or not self._experiences:
            return []
        results: List[tuple[Experience, float]] = []
        for exp in self._experiences:
            similarity = self._compute_similarity(context, exp.context)
            if similarity >= self._threshold:
                results.append((exp, similarity))
        results.sort(key=lambda x: x[1], reverse=True)
        return [exp for exp, _ in results]

    def _compute_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        words1 = set(re.split(r"\W+", text1.lower()))
        words2 = set(re.split(r"\W+", text2.lower()))
        words1 = {w for w in words1 if w}
        words2 = {w for w in words2 if w}
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0


class OutcomeMatcher:
    """基于结果类型的经验匹配器。"""

    def __init__(self) -> None:
        self._experiences: List[Experience] = []

    def set_experiences(self, experiences: List[Experience]) -> None:
        self._experiences = experiences

    def match(self, context: str) -> List[Experience]:
        if not context or not self._experiences:
            return []
        context_lower = context.lower()
        type_priority: Dict[ExperienceType, int] = {
            ExperienceType.SUCCESS: 4,
            ExperienceType.FAILURE: 3,
            ExperienceType.INSIGHT: 2,
            ExperienceType.LESSON: 1,
        }
        if any(
            w in context_lower
            for w in ["错误", "失败", "问题", "error", "fail", "problem"]
        ):
            type_priority[ExperienceType.FAILURE] = 5
            type_priority[ExperienceType.LESSON] = 4
        elif any(
            w in context_lower
            for w in ["成功", "完成", "解决", "success", "complete", "solve"]
        ):
            type_priority[ExperienceType.SUCCESS] = 5
        return sorted(
            self._experiences, key=lambda e: type_priority.get(e.type, 0), reverse=True
        )


class ExperienceAccumulator:
    """经验积累器。

    负责记录和复用经验，支持经验分类和检索。
    """

    def __init__(
        self,
        memory_manager: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        """初始化经验积累器。

        Args:
            memory_manager: 记忆管理器实例（可选）
            llm_client: LLM客户端（可选）
        """
        self._llm_client = llm_client
        self._memory_manager = memory_manager
        self._experience_store: Dict[str, ExperienceRecord] = {}
        self._content_hash_index: Dict[str, str] = {}
        self._tag_index: Dict[str, Set[str]] = {}
        self._matchers: List[ExperienceMatcherProtocol] = []
        self._keyword_matcher = KeywordMatcher()
        self._similarity_matcher = ContextSimilarityMatcher()
        self._outcome_matcher = OutcomeMatcher()

    def register_matcher(self, matcher: ExperienceMatcherProtocol) -> None:
        """注册经验匹配器。"""
        if matcher not in self._matchers:
            self._matchers.append(matcher)

    def unregister_matcher(self, matcher: ExperienceMatcherProtocol) -> bool:
        """取消注册经验匹配器。"""
        if matcher in self._matchers:
            self._matchers.remove(matcher)
            return True
        return False

    def record_experience(
        self,
        context: str,
        outcome: str,
        exp_type: ExperienceType,
        lessons: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Experience:
        """记录经验。"""
        experience = Experience(
            id=str(uuid.uuid4()),
            type=exp_type,
            context=context,
            outcome=outcome,
            lessons=lessons or [],
            created_at=datetime.now(),
            metadata=metadata or {},
        )
        if tags:
            experience.metadata["tags"] = tags
        self._store_experience(experience)
        self._update_matchers()
        return experience

    def extract_methodology(self, experiences: List[Experience]) -> Dict[str, Any]:
        """从经验中提取方法论。"""
        if not experiences:
            return {
                "patterns": [],
                "best_practices": [],
                "anti_patterns": [],
                "lessons": [],
            }
        patterns: List[str] = []
        best_practices: List[str] = []
        anti_patterns: List[str] = []
        all_lessons: List[str] = []
        success_exp = [e for e in experiences if e.type == ExperienceType.SUCCESS]
        failure_exp = [e for e in experiences if e.type == ExperienceType.FAILURE]
        insight_exp = [e for e in experiences if e.type == ExperienceType.INSIGHT]
        for exp in success_exp:
            if exp.outcome:
                best_practices.append(f"成功案例: {exp.outcome}")
            all_lessons.extend(exp.lessons)
        for exp in failure_exp:
            if exp.outcome:
                anti_patterns.append(f"避免: {exp.outcome}")
            all_lessons.extend(exp.lessons)
        for exp in insight_exp:
            if exp.outcome:
                patterns.append(exp.outcome)
            all_lessons.extend(exp.lessons)
        return {
            "patterns": list(dict.fromkeys(patterns)),
            "best_practices": list(dict.fromkeys(best_practices)),
            "anti_patterns": list(dict.fromkeys(anti_patterns)),
            "lessons": list(dict.fromkeys(all_lessons)),
            "experience_count": len(experiences),
            "success_rate": len(success_exp) / len(experiences) if experiences else 0,
        }

    def find_similar_experience(self, context: str, limit: int = 5) -> List[Experience]:
        """查找相似经验。"""
        if not context:
            return []
        all_matches: Dict[str, tuple[Experience, float]] = {}
        for i, exp in enumerate(self._keyword_matcher.match(context)):
            score = 1.0 - (i * 0.1)
            if exp.id not in all_matches or all_matches[exp.id][1] < score:
                all_matches[exp.id] = (exp, score)
        for i, exp in enumerate(self._similarity_matcher.match(context)):
            score = 0.9 - (i * 0.1)
            if exp.id not in all_matches or all_matches[exp.id][1] < score:
                all_matches[exp.id] = (exp, score)
        for i, exp in enumerate(self._outcome_matcher.match(context)):
            score = 0.8 - (i * 0.1)
            if exp.id not in all_matches or all_matches[exp.id][1] < score:
                all_matches[exp.id] = (exp, score)
        for matcher in self._matchers:
            try:
                for i, exp in enumerate(matcher.match(context)):
                    score = 0.7 - (i * 0.1)
                    if exp.id not in all_matches or all_matches[exp.id][1] < score:
                        all_matches[exp.id] = (exp, score)
            except Exception:
                pass
        sorted_results = sorted(all_matches.values(), key=lambda x: x[1], reverse=True)
        return [exp for exp, _ in sorted_results[:limit]]

    def get_experience(self, experience_id: str) -> Optional[Experience]:
        """获取经验。"""
        record = self._experience_store.get(experience_id)
        return record.experience if record else None

    def search_experiences(
        self, query: str, exp_type: Optional[ExperienceType] = None, limit: int = 10
    ) -> List[Experience]:
        """搜索经验。"""
        if not query:
            return []
        results: List[Experience] = []
        query_lower = query.lower()
        for record in self._experience_store.values():
            if record.status == LearningStatus.DEPRECATED:
                continue
            if exp_type and record.experience.type != exp_type:
                continue
            text = f"{record.experience.context} {record.experience.outcome} {' '.join(record.experience.lessons)}".lower()
            if query_lower in text:
                results.append(record.experience)
            if len(results) >= limit:
                break
        return results[:limit]

    def add_lesson(self, experience_id: str, lesson: str) -> bool:
        """添加教训到经验。"""
        record = self._experience_store.get(experience_id)
        if not record:
            return False
        if lesson and lesson not in record.experience.lessons:
            record.experience.lessons.append(lesson)
            record.experience.metadata["updated_at"] = datetime.now().isoformat()
            return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取经验统计信息。"""
        type_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        total_lessons = 0
        total_apply = 0
        for record in self._experience_store.values():
            type_name = record.experience.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            status_name = record.status.value
            status_counts[status_name] = status_counts.get(status_name, 0) + 1
            total_lessons += len(record.experience.lessons)
            total_apply += record.apply_count
        return {
            "total_count": len(self._experience_store),
            "type_distribution": type_counts,
            "status_distribution": status_counts,
            "total_lessons": total_lessons,
            "total_apply_count": total_apply,
            "registered_matchers": len(self._matchers),
        }

    def apply_experience(self, experience: Experience, context: str) -> Dict[str, Any]:
        """应用经验到新场景。"""
        result: Dict[str, Any] = {
            "applicable": False,
            "suggestions": [],
            "warnings": [],
            "lessons": [],
        }
        if not experience or not context:
            return result
        similarity = self._similarity_matcher._compute_similarity(
            context, experience.context
        )
        if similarity >= 0.2:
            result["applicable"] = True
            if experience.type == ExperienceType.SUCCESS:
                result["suggestions"].append(f"参考成功经验: {experience.outcome}")
            elif experience.type == ExperienceType.FAILURE:
                result["warnings"].append(f"注意避免: {experience.outcome}")
            elif experience.type == ExperienceType.INSIGHT:
                result["suggestions"].append(f"洞察: {experience.outcome}")
            result["lessons"] = list(experience.lessons)
            record = self._experience_store.get(experience.id)
            if record:
                record.apply_count += 1
                record.last_applied_at = datetime.now()
        return result

    def get_experiences_by_type(self, exp_type: ExperienceType) -> List[Experience]:
        """按类型获取经验。"""
        return [
            r.experience
            for r in self._experience_store.values()
            if r.experience.type == exp_type and r.status != LearningStatus.DEPRECATED
        ]

    def get_experiences_by_tag(self, tag: str) -> List[Experience]:
        """按标签获取经验。"""
        exp_ids = self._tag_index.get(tag.lower(), set())
        results: List[Experience] = []
        for exp_id in exp_ids:
            record = self._experience_store.get(exp_id)
            if record and record.status != LearningStatus.DEPRECATED:
                results.append(record.experience)
        return results

    def get_all_experiences(self, include_deprecated: bool = False) -> List[Experience]:
        """获取所有经验。"""
        results: List[Experience] = []
        for record in self._experience_store.values():
            if not include_deprecated and record.status == LearningStatus.DEPRECATED:
                continue
            results.append(record.experience)
        return results

    def get_experience_count(self) -> int:
        """获取经验数量。"""
        return sum(
            1
            for r in self._experience_store.values()
            if r.status != LearningStatus.DEPRECATED
        )

    def verify_experience(self, experience_id: str) -> bool:
        """验证经验。"""
        record = self._experience_store.get(experience_id)
        if not record:
            return False
        record.status = LearningStatus.VERIFIED
        record.experience.metadata["verified_at"] = datetime.now().isoformat()
        return True

    def deprecate_experience(self, experience_id: str) -> bool:
        """废弃经验。"""
        record = self._experience_store.get(experience_id)
        if not record:
            return False
        record.status = LearningStatus.DEPRECATED
        record.experience.metadata["deprecated_at"] = datetime.now().isoformat()
        return True

    def clear_all(self) -> None:
        """清除所有经验。"""
        self._experience_store.clear()
        self._content_hash_index.clear()
        self._tag_index.clear()
        self._update_matchers()

    def _store_experience(self, experience: Experience) -> bool:
        """存储经验。"""
        record = ExperienceRecord(experience=experience)
        if record.content_hash in self._content_hash_index:
            existing_id = self._content_hash_index[record.content_hash]
            if existing_id in self._experience_store:
                existing = self._experience_store[existing_id]
                for lesson in experience.lessons:
                    if lesson not in existing.experience.lessons:
                        existing.experience.lessons.append(lesson)
                existing.experience.metadata["updated_at"] = datetime.now().isoformat()
            return False
        self._experience_store[experience.id] = record
        self._content_hash_index[record.content_hash] = experience.id
        tags = experience.metadata.get("tags", [])
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in self._tag_index:
                self._tag_index[tag_lower] = set()
            self._tag_index[tag_lower].add(experience.id)
        return True

    def _update_matchers(self) -> None:
        """更新内置匹配器的经验列表。"""
        experiences = self.get_all_experiences()
        self._keyword_matcher.set_experiences(experiences)
        self._similarity_matcher.set_experiences(experiences)
        self._outcome_matcher.set_experiences(experiences)
