"""代码审查建议生成模块。

整合架构分析和代码分析能力，生成代码审查建议。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReviewSeverity(Enum):
    """审查建议严重程度"""

    CRITICAL = "critical"  # 严重问题，必须修复
    WARNING = "warning"  # 警告，建议修复
    INFO = "info"  # 信息，可选改进
    SUGGESTION = "suggestion"  # 建议，最佳实践


class ReviewCategory(Enum):
    """审查建议类别"""

    SECURITY = "security"  # 安全问题
    PERFORMANCE = "performance"  # 性能问题
    MAINTAINABILITY = "maintainability"  # 可维护性
    RELIABILITY = "reliability"  # 可靠性
    CODE_STYLE = "code_style"  # 代码风格
    BEST_PRACTICE = "best_practice"  # 最佳实践
    ARCHITECTURE = "architecture"  # 架构问题


@dataclass
class ReviewSuggestion:
    """代码审查建议

    Attributes:
        title: 建议标题
        description: 详细描述
        severity: 严重程度
        category: 建议类别
        file_path: 相关文件路径
        line_number: 相关行号（可选）
        code_snippet: 相关代码片段（可选）
        fix_suggestion: 修复建议（可选）
        references: 参考资料链接
    """

    title: str
    description: str
    severity: ReviewSeverity
    category: ReviewCategory
    file_path: str = ""
    line_number: Optional[int] = None
    code_snippet: str = ""
    fix_suggestion: str = ""
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "category": self.category.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "fix_suggestion": self.fix_suggestion,
            "references": self.references,
        }


@dataclass
class ReviewReport:
    """代码审查报告

    Attributes:
        project_path: 项目路径
        suggestions: 审查建议列表
        summary: 摘要
        overall_score: 总体评分（0-100）
        stats: 统计信息
    """

    project_path: str
    suggestions: List[ReviewSuggestion] = field(default_factory=list)
    summary: str = ""
    overall_score: float = 100.0
    stats: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "project_path": self.project_path,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "summary": self.summary,
            "overall_score": self.overall_score,
            "stats": self.stats,
        }

    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        lines = []
        lines.append("# 代码审查报告\n")
        lines.append(f"**项目路径**: {self.project_path}\n")
        lines.append(f"**总体评分**: {self.overall_score:.1f}/100\n")

        if self.summary:
            lines.append(f"\n## 摘要\n\n{self.summary}\n")

        if self.stats:
            lines.append("\n## 统计\n")
            for key, value in self.stats.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        if self.suggestions:
            lines.append("\n## 审查建议\n")

            # 按严重程度分组
            by_severity: Dict[ReviewSeverity, List[ReviewSuggestion]] = {}
            for s in self.suggestions:
                if s.severity not in by_severity:
                    by_severity[s.severity] = []
                by_severity[s.severity].append(s)

            severity_order = [
                ReviewSeverity.CRITICAL,
                ReviewSeverity.WARNING,
                ReviewSeverity.INFO,
                ReviewSeverity.SUGGESTION,
            ]

            for severity in severity_order:
                if severity in by_severity:
                    emoji = {
                        ReviewSeverity.CRITICAL: "🔴",
                        ReviewSeverity.WARNING: "🟡",
                        ReviewSeverity.INFO: "🔵",
                        ReviewSeverity.SUGGESTION: "💡",
                    }.get(severity, "")

                    lines.append(f"\n### {emoji} {severity.value.upper()}\n")

                    for s in by_severity[severity]:
                        lines.append(f"#### {s.title}\n")
                        lines.append(f"{s.description}\n")

                        if s.file_path:
                            loc = s.file_path
                            if s.line_number:
                                loc += f":{s.line_number}"
                            lines.append(f"**位置**: `{loc}`\n")

                        if s.code_snippet:
                            lines.append(f"```\n{s.code_snippet}\n```\n")

                        if s.fix_suggestion:
                            lines.append(f"**修复建议**: {s.fix_suggestion}\n")

                        if s.references:
                            lines.append("**参考资料**:")
                            for ref in s.references:
                                lines.append(f"- {ref}")
                            lines.append("")

        return "\n".join(lines)


class ReviewAdvisor:
    """代码审查建议生成器

    整合架构分析和代码分析能力，生成代码审查建议。
    """

    # 代码模式检测规则
    CODE_PATTERNS: Dict[str, Dict[str, Any]] = {
        # 安全问题
        "hardcoded_password": {
            "pattern": r"(password|passwd|pwd|secret|api_key|apikey)\s*=\s*[\"'][^\"']+[\"']",
            "severity": ReviewSeverity.CRITICAL,
            "category": ReviewCategory.SECURITY,
            "title": "硬编码密码/密钥",
            "description": "代码中发现硬编码的密码或密钥，这是严重的安全风险。",
            "fix_suggestion": "使用环境变量或配置文件存储敏感信息。",
        },
        "sql_injection": {
            "pattern": r"(execute|cursor\.execute)\s*\(\s*[\"'].*%s.*[\"']\s*%",
            "severity": ReviewSeverity.CRITICAL,
            "category": ReviewCategory.SECURITY,
            "title": "潜在SQL注入风险",
            "description": "使用字符串格式化构建SQL查询可能导致SQL注入攻击。",
            "fix_suggestion": "使用参数化查询代替字符串格式化。",
        },
        # 性能问题
        "n_plus_one": {
            "pattern": r"for\s+\w+\s+in\s+\w+.*:\s*\n.*\.(get|filter|query)",
            "severity": ReviewSeverity.WARNING,
            "category": ReviewCategory.PERFORMANCE,
            "title": "潜在N+1查询问题",
            "description": "在循环中执行数据库查询可能导致N+1查询问题。",
            "fix_suggestion": "考虑使用批量查询或预加载相关数据。",
        },
        # 可维护性问题
        "long_function": {
            "pattern": r"def\s+\w+\s*\([^)]*\)\s*:.*?(?=\ndef\s|\nclass\s|$)",
            "severity": ReviewSeverity.INFO,
            "category": ReviewCategory.MAINTAINABILITY,
            "title": "函数过长",
            "description": "函数超过50行，建议拆分为更小的函数。",
            "fix_suggestion": "将函数拆分为多个职责单一的小函数。",
        },
        # 代码风格
        "todo_comment": {
            "pattern": r"#\s*(TODO|FIXME|XXX|HACK)\s*:?",
            "severity": ReviewSeverity.INFO,
            "category": ReviewCategory.CODE_STYLE,
            "title": "待处理注释",
            "description": "代码中存在TODO/FIXME等待处理注释。",
            "fix_suggestion": "评估并处理这些待办事项，或创建issue跟踪。",
        },
        # 最佳实践
        "bare_except": {
            "pattern": r"except\s*:",
            "severity": ReviewSeverity.WARNING,
            "category": ReviewCategory.BEST_PRACTICE,
            "title": "裸异常捕获",
            "description": "使用裸except会捕获所有异常，包括系统退出等。",
            "fix_suggestion": "明确指定要捕获的异常类型，如 except Exception:。",
        },
        "magic_number": {
            "pattern": r"(?<!\d)[0-9]{2,}(?!\d)(?!\s*[\]\)\}])",
            "severity": ReviewSeverity.SUGGESTION,
            "category": ReviewCategory.BEST_PRACTICE,
            "title": "魔法数字",
            "description": "代码中存在未命名的数字常量。",
            "fix_suggestion": "将数字提取为命名常量，提高代码可读性。",
        },
    }

    def __init__(self, project_dir: str = "."):
        """初始化审查建议生成器

        Args:
            project_dir: 项目目录路径
        """
        self.project_dir = Path(project_dir)
        self._arch_analyzer: Optional[Any] = None

    @property
    def arch_analyzer(self):
        """懒加载架构分析器"""
        if self._arch_analyzer is None:
            from jarvis.jarvis_arch_analyzer import ArchitectureAnalyzer

            self._arch_analyzer = ArchitectureAnalyzer(str(self.project_dir))
        return self._arch_analyzer

    def review_code(self, code: str, file_path: str = "") -> List[ReviewSuggestion]:
        """审查代码并生成建议

        Args:
            code: 代码内容
            file_path: 文件路径（可选）

        Returns:
            审查建议列表
        """
        suggestions = []

        # 基于模式检测
        for pattern_name, pattern_info in self.CODE_PATTERNS.items():
            matches = list(
                re.finditer(pattern_info["pattern"], code, re.IGNORECASE | re.MULTILINE)
            )

            for match in matches:
                # 计算行号
                line_number = code[: match.start()].count("\n") + 1

                # 获取代码片段（匹配行及上下文）
                lines = code.split("\n")
                start_line = max(0, line_number - 2)
                end_line = min(len(lines), line_number + 2)
                code_snippet = "\n".join(lines[start_line:end_line])

                suggestion = ReviewSuggestion(
                    title=pattern_info["title"],
                    description=pattern_info["description"],
                    severity=pattern_info["severity"],
                    category=pattern_info["category"],
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=code_snippet,
                    fix_suggestion=pattern_info.get("fix_suggestion", ""),
                )
                suggestions.append(suggestion)

        # 检查函数长度
        suggestions.extend(self._check_function_length(code, file_path))

        return suggestions

    def _check_function_length(
        self, code: str, file_path: str = ""
    ) -> List[ReviewSuggestion]:
        """检查函数长度"""
        suggestions = []

        # 简单的函数检测（Python）
        func_pattern = r"^(\s*)def\s+(\w+)\s*\([^)]*\)\s*:"
        lines = code.split("\n")

        i = 0
        while i < len(lines):
            match = re.match(func_pattern, lines[i])
            if match:
                indent = len(match.group(1))
                func_name = match.group(2)
                func_start = i

                # 找到函数结束
                j = i + 1
                while j < len(lines):
                    line = lines[j]
                    if line.strip() and not line.startswith(" " * (indent + 1)):
                        # 检查是否是同级或更高级的定义
                        if re.match(r"^\s*(def|class)\s", line):
                            current_indent = len(line) - len(line.lstrip())
                            if current_indent <= indent:
                                break
                    j += 1

                func_length = j - func_start
                if func_length > 50:
                    suggestions.append(
                        ReviewSuggestion(
                            title=f"函数 {func_name} 过长",
                            description=f"函数 {func_name} 有 {func_length} 行，超过建议的50行限制。",
                            severity=ReviewSeverity.INFO,
                            category=ReviewCategory.MAINTAINABILITY,
                            file_path=file_path,
                            line_number=func_start + 1,
                            fix_suggestion="考虑将函数拆分为多个职责单一的小函数。",
                        )
                    )

                i = j
            else:
                i += 1

        return suggestions

    def review_file(self, file_path: str) -> List[ReviewSuggestion]:
        """审查文件并生成建议

        Args:
            file_path: 文件路径

        Returns:
            审查建议列表
        """
        path = Path(file_path)
        if not path.exists():
            return []

        try:
            code = path.read_text(encoding="utf-8")
            return self.review_code(code, str(path))
        except Exception:
            return []

    def review_project(
        self, include_patterns: Optional[List[str]] = None
    ) -> ReviewReport:
        """审查整个项目并生成报告

        Args:
            include_patterns: 包含的文件模式（如 ["*.py", "*.js"]）

        Returns:
            审查报告
        """
        if include_patterns is None:
            include_patterns = ["*.py"]

        all_suggestions: List[ReviewSuggestion] = []

        # 遍历项目文件
        for pattern in include_patterns:
            for file_path in self.project_dir.rglob(pattern):
                # 跳过隐藏目录和常见的排除目录
                if any(
                    part.startswith(".")
                    or part in ["node_modules", "venv", "__pycache__", "dist", "build"]
                    for part in file_path.parts
                ):
                    continue

                suggestions = self.review_file(str(file_path))
                all_suggestions.extend(suggestions)

        # 计算统计信息
        stats = {
            "total_suggestions": len(all_suggestions),
            "critical": sum(
                1 for s in all_suggestions if s.severity == ReviewSeverity.CRITICAL
            ),
            "warning": sum(
                1 for s in all_suggestions if s.severity == ReviewSeverity.WARNING
            ),
            "info": sum(
                1 for s in all_suggestions if s.severity == ReviewSeverity.INFO
            ),
            "suggestion": sum(
                1 for s in all_suggestions if s.severity == ReviewSeverity.SUGGESTION
            ),
        }

        # 计算总体评分
        score = 100.0
        score -= stats["critical"] * 10
        score -= stats["warning"] * 5
        score -= stats["info"] * 2
        score -= stats["suggestion"] * 1
        score = max(0.0, score)

        # 生成摘要
        summary_parts = []
        if stats["critical"] > 0:
            summary_parts.append(f"{stats['critical']} 个严重问题需要立即修复")
        if stats["warning"] > 0:
            summary_parts.append(f"{stats['warning']} 个警告建议修复")
        if stats["info"] > 0:
            summary_parts.append(f"{stats['info']} 个信息提示")
        if stats["suggestion"] > 0:
            summary_parts.append(f"{stats['suggestion']} 个改进建议")

        summary = (
            "；".join(summary_parts)
            if summary_parts
            else "代码质量良好，未发现明显问题。"
        )

        return ReviewReport(
            project_path=str(self.project_dir),
            suggestions=all_suggestions,
            summary=summary,
            overall_score=score,
            stats=stats,
        )

    def review_diff(self, diff_content: str) -> List[ReviewSuggestion]:
        """审查diff内容并生成建议

        Args:
            diff_content: git diff输出内容

        Returns:
            审查建议列表
        """
        suggestions = []

        # 解析diff，提取新增的代码
        current_file = ""
        added_lines: List[str] = []
        line_numbers: List[int] = []
        current_line = 0

        for line in diff_content.split("\n"):
            # 检测文件名
            if line.startswith("+++ b/"):
                # 处理之前文件的代码
                if current_file and added_lines:
                    code = "\n".join(added_lines)
                    file_suggestions = self.review_code(code, current_file)
                    suggestions.extend(file_suggestions)

                current_file = line[6:]
                added_lines = []
                line_numbers = []
                current_line = 0

            # 检测行号
            elif line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1))

            # 收集新增的行
            elif line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
                line_numbers.append(current_line)
                current_line += 1

            elif not line.startswith("-"):
                current_line += 1

        # 处理最后一个文件
        if current_file and added_lines:
            code = "\n".join(added_lines)
            file_suggestions = self.review_code(code, current_file)
            suggestions.extend(file_suggestions)

        return suggestions
