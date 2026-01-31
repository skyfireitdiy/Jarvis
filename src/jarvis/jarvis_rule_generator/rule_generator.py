"""规则自动生成器

该模块提供从代码模式、项目实践中自动生成规则的功能。
包含以下核心功能：
- 检测代码模式
- 生成符合标准格式的规则内容
- 检测规则冲突
- 评估规则质量
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CodePattern:
    """代码模式数据类

    存储从代码中检测到的模式信息。
    """

    pattern_type: str = ""  # design_pattern, coding_style, architecture, best_practice
    pattern_name: str = ""  # 模式名称
    description: str = ""  # 模式描述
    code_examples: List[str] = field(default_factory=list)  # 代码示例
    file_paths: List[str] = field(default_factory=list)  # 相关文件路径
    occurrence_count: int = 0  # 出现次数
    context: str = ""  # 上下文信息


@dataclass
class RuleGenerationContext:
    """规则生成上下文

    存储规则生成所需的上下文信息。
    """

    source_type: str = ""  # code_pattern, best_practice, user_request
    pattern: Optional[CodePattern] = None  # 关联的代码模式
    description: str = ""  # 规则描述
    scope: str = "project"  # project 或 global


@dataclass
class RuleQualityScore:
    """规则质量评分

    包含各维度的评分和总分。
    """

    completeness: int = 0  # 完整性（25分）
    executability: int = 0  # 可执行性（25分）
    generality: int = 0  # 通用性（20分）
    uniqueness: int = 0  # 独特性（15分）
    code_examples: int = 0  # 代码示例（15分）

    @property
    def total(self) -> int:
        """计算总分"""
        return (
            self.completeness
            + self.executability
            + self.generality
            + self.uniqueness
            + self.code_examples
        )

    def is_qualified(self, threshold: int = 70) -> bool:
        """判断是否达到质量阈值"""
        return self.total >= threshold


class RuleGenerator:
    """规则自动生成器

    从代码模式、项目实践中自动生成规则，
    并评估规则质量。
    """

    # 规则模板
    RULE_TEMPLATE = """# {rule_name}

## 规则简介
{introduction}

## 你必须遵循的工作流程
{workflow}

## 你必须遵守的原则
{principles}

## 实践指导
{guidance}

## 代码示例
{code_examples}

## 执行检查清单
{checklist}
"""

    # 必需的章节
    REQUIRED_SECTIONS = [
        "规则简介",
        "你必须遵循的工作流程",
        "你必须遵守的原则",
    ]

    # 可选的章节
    OPTIONAL_SECTIONS = [
        "实践指导",
        "代码示例",
        "执行检查清单",
    ]

    def __init__(
        self,
        existing_rules: Optional[List[str]] = None,
        rules_dir: Optional[str] = None,
    ):
        """初始化规则生成器

        Args:
            existing_rules: 现有规则内容列表，用于去重和独特性评估
            rules_dir: 规则存储目录，默认为 .jarvis/rules/
        """
        self.existing_rules = existing_rules or []
        self.rules_dir = rules_dir or ".jarvis/rules/"

    def extract_rule_from_code(
        self, file_paths: List[str], pattern_type: str = "best_practice"
    ) -> Optional[Dict[str, Any]]:
        """从代码中提取规则

        Args:
            file_paths: 要分析的文件路径列表
            pattern_type: 模式类型

        Returns:
            提取的规则字典，包含rule_name和content，
            如果无法提取则返回None
        """
        # 检测代码模式
        patterns = self.detect_patterns(file_paths, pattern_type)
        if not patterns:
            return None

        # 使用第一个检测到的模式
        pattern = patterns[0]

        # 创建生成上下文
        context = RuleGenerationContext(
            source_type="code_pattern",
            pattern=pattern,
            description=pattern.description,
            scope="project",
        )

        # 生成规则内容
        content = self.generate_rule_content(context)

        # 检测冲突
        conflicts = self.detect_rule_conflict(content)
        if conflicts:
            # 如果有原则矛盾，返回None
            for conflict in conflicts:
                if conflict.get("type") == "principle_conflict":
                    return None

        # 评估质量
        quality_score = self.evaluate_rule_quality(content)
        if not quality_score.is_qualified():
            return None

        return {
            "rule_name": pattern.pattern_name,
            "content": content,
            "quality_score": quality_score.total,
            "conflicts": conflicts,
        }

    def detect_patterns(
        self, file_paths: List[str], pattern_type: str = "best_practice"
    ) -> List[CodePattern]:
        """检测代码模式

        Args:
            file_paths: 要分析的文件路径列表
            pattern_type: 模式类型

        Returns:
            检测到的代码模式列表
        """
        patterns: List[CodePattern] = []

        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (IOError, UnicodeDecodeError):
                continue

            # 简单的模式检测逻辑
            detected = self._detect_pattern_in_content(content, file_path, pattern_type)
            if detected:
                # 检查是否已存在相同模式
                existing = next(
                    (p for p in patterns if p.pattern_name == detected.pattern_name),
                    None,
                )
                if existing:
                    existing.occurrence_count += 1
                    existing.file_paths.append(file_path)
                else:
                    patterns.append(detected)

        return patterns

    def generate_rule_content(self, context: RuleGenerationContext) -> str:
        """生成规则内容

        Args:
            context: 规则生成上下文

        Returns:
            生成的规则内容（Markdown格式）
        """
        pattern = context.pattern

        # 生成规则名称
        if pattern and pattern.pattern_name:
            rule_name = pattern.pattern_name
        else:
            rule_name = "自动生成规则"

        # 生成简介
        introduction = self._generate_introduction(context)

        # 生成工作流程
        workflow = self._generate_workflow(context)

        # 生成原则
        principles = self._generate_principles(context)

        # 生成实践指导
        guidance = self._generate_guidance(context)

        # 生成代码示例
        code_examples = self._generate_code_examples(context)

        # 生成检查清单
        checklist = self._generate_checklist(context)

        # 使用模板生成内容
        content = self.RULE_TEMPLATE.format(
            rule_name=rule_name,
            introduction=introduction,
            workflow=workflow,
            principles=principles,
            guidance=guidance,
            code_examples=code_examples,
            checklist=checklist,
        )

        return content.strip()

    def detect_rule_conflict(self, rule_content: str) -> List[Dict[str, Any]]:
        """检测规则冲突

        Args:
            rule_content: 规则内容

        Returns:
            冲突列表，每个冲突包含type和description
        """
        conflicts: List[Dict[str, Any]] = []

        # 提取规则名称
        rule_name = self._extract_rule_name(rule_content)

        for i, existing in enumerate(self.existing_rules):
            existing_name = self._extract_rule_name(existing)

            # 检测名称冲突
            if rule_name and existing_name and rule_name == existing_name:
                conflicts.append(
                    {
                        "type": "name_conflict",
                        "description": f"规则名称 '{rule_name}' 已存在",
                        "suggestion": "自动添加后缀",
                        "existing_index": i,
                    }
                )

            # 检测内容相似
            similarity = self._calculate_similarity(rule_content, existing)
            if similarity >= 0.7:
                conflicts.append(
                    {
                        "type": "content_similar",
                        "description": f"与现有规则相似度为 {similarity:.0%}",
                        "suggestion": "建议合并或覆盖",
                        "similarity": similarity,
                        "existing_index": i,
                    }
                )

            # 检测原则矛盾
            if self._detect_principle_conflict(rule_content, existing):
                conflicts.append(
                    {
                        "type": "principle_conflict",
                        "description": "与现有规则存在原则矛盾",
                        "suggestion": "拒绝生成",
                        "existing_index": i,
                    }
                )

        return conflicts

    def evaluate_rule_quality(self, content: str) -> RuleQualityScore:
        """评估规则质量

        Args:
            content: 规则内容

        Returns:
            质量评分对象
        """
        score = RuleQualityScore()

        # 评估完整性（25分）
        score.completeness = self._evaluate_completeness(content)

        # 评估可执行性（25分）
        score.executability = self._evaluate_executability(content)

        # 评估通用性（20分）
        score.generality = self._evaluate_generality(content)

        # 评估独特性（15分）
        score.uniqueness = self._evaluate_uniqueness(content)

        # 评估代码示例（15分）
        score.code_examples = self._evaluate_code_examples(content)

        return score

    def save_rule(
        self, rule_name: str, rule_content: str, scope: str = "project"
    ) -> str:
        """保存规则文件

        Args:
            rule_name: 规则名称
            rule_content: 规则内容
            scope: 作用域（project 或 global）

        Returns:
            保存的文件路径
        """
        # 确定保存目录
        if scope == "global":
            save_dir = os.path.expanduser("~/.jarvis/rules/")
        else:
            save_dir = self.rules_dir

        # 创建目录
        os.makedirs(save_dir, exist_ok=True)

        # 生成文件名
        file_name = self._sanitize_filename(rule_name) + ".md"
        file_path = os.path.join(save_dir, file_name)

        # 处理名称冲突
        counter = 1
        while os.path.exists(file_path):
            file_name = f"{self._sanitize_filename(rule_name)}_{counter}.md"
            file_path = os.path.join(save_dir, file_name)
            counter += 1

        # 保存文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(rule_content)

        return file_path

    def _detect_pattern_in_content(
        self, content: str, file_path: str, pattern_type: str
    ) -> Optional[CodePattern]:
        """在内容中检测模式"""
        patterns_detected: List[CodePattern] = []

        # 检测设计模式
        if pattern_type in ("design_pattern", "best_practice"):
            # 单例模式
            if re.search(r"_instance\s*=\s*None|__new__.*cls\._instance", content):
                patterns_detected.append(
                    CodePattern(
                        pattern_type="design_pattern",
                        pattern_name="单例模式",
                        description="确保类只有一个实例",
                        code_examples=[
                            self._extract_code_snippet(content, "_instance")
                        ],
                        file_paths=[file_path],
                        occurrence_count=1,
                        context="设计模式",
                    )
                )

            # 工厂模式
            if re.search(r"def\s+create_\w+|class\s+\w+Factory", content):
                patterns_detected.append(
                    CodePattern(
                        pattern_type="design_pattern",
                        pattern_name="工厂模式",
                        description="使用工厂方法创建对象",
                        code_examples=[self._extract_code_snippet(content, "create_")],
                        file_paths=[file_path],
                        occurrence_count=1,
                        context="设计模式",
                    )
                )

        # 检测编码风格
        if pattern_type in ("coding_style", "best_practice"):
            # 类型注解
            if re.search(r"def\s+\w+\([^)]*:\s*\w+", content):
                patterns_detected.append(
                    CodePattern(
                        pattern_type="coding_style",
                        pattern_name="类型注解规范",
                        description="使用类型注解提高代码可读性",
                        code_examples=[self._extract_code_snippet(content, "def ")],
                        file_paths=[file_path],
                        occurrence_count=1,
                        context="编码风格",
                    )
                )

        return patterns_detected[0] if patterns_detected else None

    def _extract_code_snippet(self, content: str, keyword: str, lines: int = 10) -> str:
        """提取代码片段"""
        lines_list = content.split("\n")
        for i, line in enumerate(lines_list):
            if keyword in line:
                start = max(0, i - 2)
                end = min(len(lines_list), i + lines)
                return "\n".join(lines_list[start:end])
        return ""

    def _generate_introduction(self, context: RuleGenerationContext) -> str:
        """生成规则简介"""
        if context.pattern:
            return f"本规则定义了{context.pattern.pattern_name}的标准实践方式。{context.pattern.description}"
        return f"本规则提供了{context.description}的标准化指导。"

    def _generate_workflow(self, context: RuleGenerationContext) -> str:
        """生成工作流程"""
        if context.pattern and context.pattern.pattern_type == "design_pattern":
            return """1. **分析需求**：确定是否需要使用该模式
2. **设计结构**：按照模式定义设计类结构
3. **实现代码**：按照模式规范实现代码
4. **验证正确性**：确保实现符合模式要求"""

        return """1. **理解规则**：阅读并理解规则要求
2. **检查现状**：检查当前代码是否符合规则
3. **应用规则**：按照规则要求修改代码
4. **验证结果**：确保修改后符合规则"""

    def _generate_principles(self, context: RuleGenerationContext) -> str:
        """生成原则部分"""
        principles = []

        if context.pattern:
            if context.pattern.pattern_type == "design_pattern":
                principles.append("- **必须**：遵循设计模式的标准结构")
                principles.append("- **必须**：保持代码的可维护性")
                principles.append("- **禁止**：破坏模式的核心约束")
            elif context.pattern.pattern_type == "coding_style":
                principles.append("- **必须**：保持代码风格一致")
                principles.append("- **必须**：遵循项目编码规范")
                principles.append("- **禁止**：混用不同的编码风格")

        if not principles:
            principles = [
                "- **必须**：遵循规则要求",
                "- **必须**：保持代码质量",
                "- **禁止**：违反规则约束",
            ]

        return "\n".join(principles)

    def _generate_guidance(self, context: RuleGenerationContext) -> str:
        """生成实践指导"""
        guidance = []

        if context.pattern and context.pattern.context:
            guidance.append(f"- 在{context.pattern.context}场景下应用此规则")

        guidance.extend(
            [
                "- 在修改代码前先理解规则要求",
                "- 保持代码的可读性和可维护性",
                "- 及时验证修改是否符合规则",
            ]
        )

        return "\n".join(guidance)

    def _generate_code_examples(self, context: RuleGenerationContext) -> str:
        """生成代码示例"""
        if context.pattern and context.pattern.code_examples:
            examples = []
            for i, example in enumerate(context.pattern.code_examples[:3], 1):
                if example.strip():
                    examples.append(f"### 示例{i}\n\n```python\n{example}\n```")
            if examples:
                return "\n\n".join(examples)

        return "```python\n# 暂无代码示例\n```"

    def _generate_checklist(self, context: RuleGenerationContext) -> str:
        """生成检查清单"""
        checklist = [
            "- [ ] 代码符合规则要求",
            "- [ ] 代码通过静态检查",
            "- [ ] 代码风格一致",
        ]

        if context.pattern:
            if context.pattern.pattern_type == "design_pattern":
                checklist.append("- [ ] 设计模式实现正确")
            elif context.pattern.pattern_type == "coding_style":
                checklist.append("- [ ] 编码风格符合规范")

        return "\n".join(checklist)

    def _extract_rule_name(self, content: str) -> str:
        """从规则内容中提取规则名称"""
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度（Jaccard相似度）"""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _detect_principle_conflict(self, rule1: str, rule2: str) -> bool:
        """检测两个规则是否存在原则矛盾"""
        # 简单实现：检查是否有相反的关键词对
        conflict_pairs = [
            ("必须", "禁止"),
            ("允许", "禁止"),
            ("推荐", "禁止"),
        ]

        # 提取原则部分
        principles1 = self._extract_section(rule1, "原则")
        principles2 = self._extract_section(rule2, "原则")

        if not principles1 or not principles2:
            return False

        # 检查是否有相同主题但相反要求
        for must, forbid in conflict_pairs:
            must_items = re.findall(rf"{must}[：:]\s*(.+?)(?:\n|$)", principles1)
            forbid_items = re.findall(rf"{forbid}[：:]\s*(.+?)(?:\n|$)", principles2)

            for must_item in must_items:
                for forbid_item in forbid_items:
                    if self._calculate_similarity(must_item, forbid_item) > 0.8:
                        return True

        return False

    def _extract_section(self, content: str, section_name: str) -> str:
        """提取指定章节的内容"""
        # 匹配包含section_name的二级标题，然后提取到下一个二级标题之前的内容
        pattern = rf"##\s+[^\n]*{section_name}[^\n]*\n(.*?)(?=\n##|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _evaluate_completeness(self, content: str) -> int:
        """评估完整性（25分）"""
        score = 0

        # 检查必需章节（每个约8分）
        for section in self.REQUIRED_SECTIONS:
            if section in content:
                score += 8

        return min(score, 25)

    def _evaluate_executability(self, content: str) -> int:
        """评估可执行性（25分）"""
        score = 0

        # 检查是否有编号步骤（10分）
        if re.search(r"\d+\.\s+", content):
            score += 10

        # 检查是否有具体操作描述（15分）
        action_keywords = ["执行", "创建", "修改", "验证", "检查", "使用", "实现"]
        for keyword in action_keywords:
            if keyword in content:
                score += 2
                if score >= 25:
                    break

        return min(score, 25)

    def _evaluate_generality(self, content: str) -> int:
        """评估通用性（20分）"""
        score = 15  # 基础分

        # 检查是否避免了过于具体的内容
        specific_patterns = [
            r"\b[a-f0-9]{32}\b",  # MD5哈希
            r"\b\d{4}-\d{2}-\d{2}\b",  # 日期
            r"/home/\w+/",  # 绝对路径
            r"C:\\Users\\",  # Windows路径
        ]

        for pattern in specific_patterns:
            if re.search(pattern, content):
                score -= 5

        return max(score, 0)

    def _evaluate_uniqueness(self, content: str) -> int:
        """评估独特性（15分）"""
        if not self.existing_rules:
            return 12  # 没有现有规则时给予较高分数

        # 计算与现有规则的相似度
        max_similarity: float = 0.0
        for existing in self.existing_rules:
            similarity = self._calculate_similarity(content, existing)
            max_similarity = max(max_similarity, similarity)

        # 相似度越低，独特性越高
        if max_similarity > 0.8:
            return 0
        elif max_similarity > 0.6:
            return 5
        elif max_similarity > 0.4:
            return 10
        else:
            return 15

    def _evaluate_code_examples(self, content: str) -> int:
        """评估代码示例（15分）"""
        score = 0

        # 检查是否有代码块
        code_blocks = re.findall(r"```[\w]*\n.*?```", content, re.DOTALL)
        if code_blocks:
            score += 5

            # 检查代码块数量
            if len(code_blocks) >= 2:
                score += 5

            # 检查代码块是否有实际内容
            for block in code_blocks:
                if re.search(r"(?:def|class|import|from|if|for|while)\s+", block):
                    score += 5
                    break

        return min(score, 15)

    def _sanitize_filename(self, name: str) -> str:
        """清理文件名，移除非法字符"""
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
        sanitized = sanitized.strip()
        if not sanitized:
            sanitized = "unnamed_rule"
        return sanitized
