# -*- coding: utf-8 -*-
"""规则生成工具

将规则生成器功能暴露给Agent使用，支持检测代码模式、生成规则内容、保存规则文件。
"""

import os
from typing import Any, Dict, List, Optional

from jarvis.jarvis_rule_generator.rule_generator import (
    CodePattern,
    RuleGenerationContext,
    RuleGenerator,
)
from jarvis.jarvis_utils.output import PrettyOutput


class GenerateRuleTool:
    """规则生成工具

    支持以下操作：
    - detect_patterns: 检测代码模式
    - generate_rule: 生成规则内容
    - save_rule: 保存规则文件
    """

    name = "generate_rule"
    description = """生成项目规则，支持检测代码模式、生成规则内容、保存规则文件。

操作说明：
- detect_patterns: 分析指定文件，检测代码中的设计模式、编码风格等模式
- generate_rule: 根据描述和模式类型生成规则内容
- save_rule: 将规则内容保存到文件"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["detect_patterns", "generate_rule", "save_rule"],
                "description": "操作类型：detect_patterns（检测代码模式）、generate_rule（生成规则内容）、save_rule（保存规则文件）",
            },
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要分析的文件路径列表（detect_patterns时使用）",
            },
            "pattern_type": {
                "type": "string",
                "enum": [
                    "design_pattern",
                    "coding_style",
                    "architecture",
                    "best_practice",
                ],
                "description": "模式类型（detect_patterns和generate_rule时使用），默认为best_practice",
            },
            "rule_name": {
                "type": "string",
                "description": "规则名称（generate_rule和save_rule时使用）",
            },
            "description": {
                "type": "string",
                "description": "规则描述（generate_rule时使用）",
            },
            "rule_content": {
                "type": "string",
                "description": "规则内容（save_rule时使用）",
            },
            "scope": {
                "type": "string",
                "enum": ["project", "global"],
                "description": "规则作用域：project（项目级）或global（全局），默认为project",
            },
        },
        "required": ["operation"],
    }

    def __init__(self) -> None:
        """初始化规则生成工具"""
        self._generator: Optional[RuleGenerator] = None

    def _get_generator(self) -> RuleGenerator:
        """获取规则生成器实例（延迟初始化）"""
        if self._generator is None:
            self._generator = RuleGenerator()
        return self._generator

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行规则生成操作

        Args:
            args: 包含操作参数的字典

        Returns:
            Dict[str, Any]: 包含执行结果的字典
        """
        operation = args.get("operation", "").strip()

        if not operation:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: operation",
            }

        try:
            if operation == "detect_patterns":
                return self._detect_patterns(args)
            elif operation == "generate_rule":
                return self._generate_rule(args)
            elif operation == "save_rule":
                return self._save_rule(args)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作类型: {operation}",
                }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}",
            }

    def _detect_patterns(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """检测代码模式

        Args:
            args: 包含file_paths和pattern_type的参数字典

        Returns:
            Dict[str, Any]: 检测结果
        """
        file_paths = args.get("file_paths", [])
        pattern_type = args.get("pattern_type", "best_practice")

        if not file_paths:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: file_paths",
            }

        # 验证文件路径
        valid_paths: List[str] = []
        invalid_paths: List[str] = []
        for path in file_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                invalid_paths.append(path)

        if not valid_paths:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"所有文件路径都无效: {invalid_paths}",
            }

        generator = self._get_generator()
        patterns = generator.detect_patterns(valid_paths, pattern_type)

        if not patterns:
            result = "未检测到代码模式"
            if invalid_paths:
                result += f"\n\n警告: 以下文件不存在: {invalid_paths}"
            return {
                "success": True,
                "stdout": result,
                "stderr": "",
            }

        # 格式化输出
        output_lines = [f"检测到 {len(patterns)} 个代码模式:\n"]
        for i, pattern in enumerate(patterns, 1):
            output_lines.append(f"## 模式 {i}: {pattern.pattern_name}")
            output_lines.append(f"- 类型: {pattern.pattern_type}")
            output_lines.append(f"- 描述: {pattern.description}")
            output_lines.append(f"- 出现次数: {pattern.occurrence_count}")
            output_lines.append(f"- 相关文件: {', '.join(pattern.file_paths)}")
            if pattern.context:
                output_lines.append(f"- 上下文: {pattern.context}")
            output_lines.append("")

        if invalid_paths:
            output_lines.append(f"\n警告: 以下文件不存在: {invalid_paths}")

        return {
            "success": True,
            "stdout": "\n".join(output_lines),
            "stderr": "",
        }

    def _generate_rule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """生成规则内容

        Args:
            args: 包含rule_name、description、pattern_type的参数字典

        Returns:
            Dict[str, Any]: 生成的规则内容
        """
        rule_name = args.get("rule_name", "").strip()
        description = args.get("description", "").strip()
        pattern_type = args.get("pattern_type", "best_practice")
        scope = args.get("scope", "project")

        if not rule_name:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: rule_name",
            }

        if not description:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: description",
            }

        # 创建代码模式
        pattern = CodePattern(
            pattern_type=pattern_type,
            pattern_name=rule_name,
            description=description,
            code_examples=[],
            file_paths=[],
            occurrence_count=0,
            context=pattern_type,
        )

        # 创建生成上下文
        context = RuleGenerationContext(
            source_type="user_request",
            pattern=pattern,
            description=description,
            scope=scope,
        )

        generator = self._get_generator()
        content = generator.generate_rule_content(context)

        # 评估质量
        quality_score = generator.evaluate_rule_quality(content)

        output_lines = [
            f"# 生成的规则: {rule_name}\n",
            f"质量评分: {quality_score.total}/100",
            f"- 完整性: {quality_score.completeness}/25",
            f"- 可执行性: {quality_score.executability}/25",
            f"- 通用性: {quality_score.generality}/20",
            f"- 独特性: {quality_score.uniqueness}/15",
            f"- 代码示例: {quality_score.code_examples}/15",
            f"\n是否达标: {'是' if quality_score.is_qualified() else '否'}\n",
            "---\n",
            content,
        ]

        return {
            "success": True,
            "stdout": "\n".join(output_lines),
            "stderr": "",
        }

    def _save_rule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """保存规则文件

        Args:
            args: 包含rule_name、rule_content、scope的参数字典

        Returns:
            Dict[str, Any]: 保存结果
        """
        rule_name = args.get("rule_name", "").strip()
        rule_content = args.get("rule_content", "").strip()
        scope = args.get("scope", "project")

        if not rule_name:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: rule_name",
            }

        if not rule_content:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: rule_content",
            }

        generator = self._get_generator()

        try:
            file_path = generator.save_rule(rule_name, rule_content, scope)
            scope_name = "全局" if scope == "global" else "项目"
            PrettyOutput.auto_print(f"ℹ️ 已保存{scope_name}规则到 {file_path}")

            return {
                "success": True,
                "stdout": f"规则已保存到: {file_path}",
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"保存规则失败: {str(e)}",
            }
