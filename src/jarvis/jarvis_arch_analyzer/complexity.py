"""代码复杂度分析模块。

提供圈复杂度和认知复杂度的计算功能。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FunctionComplexity:
    """函数复杂度数据类。

    Attributes:
        file_path: 文件路径
        function_name: 函数名称
        line_no: 起始行号
        cyclomatic: 圈复杂度
        cognitive: 认知复杂度
        is_high_complexity: 是否为高复杂度函数
    """

    file_path: str
    function_name: str
    line_no: int
    cyclomatic: int = 0
    cognitive: int = 0
    is_high_complexity: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "file_path": self.file_path,
            "function_name": self.function_name,
            "line_no": self.line_no,
            "cyclomatic": self.cyclomatic,
            "cognitive": self.cognitive,
            "is_high_complexity": self.is_high_complexity,
        }


@dataclass
class ComplexityReport:
    """复杂度分析报告。

    Attributes:
        total_functions: 总函数数
        high_complexity_functions: 高复杂度函数列表
        average_cyclomatic: 平均圈复杂度
        average_cognitive: 平均认知复杂度
        max_cyclomatic: 最大圈复杂度
        max_cognitive: 最大认知复杂度
    """

    total_functions: int = 0
    high_complexity_functions: list[FunctionComplexity] = field(default_factory=list)
    average_cyclomatic: float = 0.0
    average_cognitive: float = 0.0
    max_cyclomatic: int = 0
    max_cognitive: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "total_functions": self.total_functions,
            "high_complexity_functions": [
                f.to_dict() for f in self.high_complexity_functions
            ],
            "average_cyclomatic": self.average_cyclomatic,
            "average_cognitive": self.average_cognitive,
            "max_cyclomatic": self.max_cyclomatic,
            "max_cognitive": self.max_cognitive,
        }


class ComplexityVisitor(ast.NodeVisitor):
    """AST访问器，用于计算函数复杂度。"""

    def __init__(self) -> None:
        """初始化访问器。"""
        self.cyclomatic: int = 1  # 圈复杂度基础值
        self.cognitive: int = 0  # 认知复杂度基础值
        self.nesting_level: int = 0  # 当前嵌套层级

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """访问函数定义。"""
        # 遍历函数体
        for child in ast.walk(node):
            # 跳过嵌套函数
            if isinstance(child, ast.FunctionDef) and child != node:
                continue

            # 圈复杂度计算
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.While,
                    ast.Try,
                    ast.With,
                    ast.ExceptHandler,
                ),
            ):
                self.cyclomatic += 1

            # 圈复杂度：逻辑运算符
            if isinstance(child, ast.BoolOp):
                self.cyclomatic += len(child.values) - 1

            # 圈复杂度：lambda表达式
            if isinstance(child, ast.Lambda):
                self.cyclomatic += 1

        # 认知复杂度计算
        self._calculate_cognitive(node)

    def _calculate_cognitive(self, node: ast.FunctionDef) -> None:
        """计算认知复杂度。

        认知复杂度规则：
        - 基础值：0
        - 嵌套层级：每层 +2
        - 逻辑运算符(and/or)：每个 +1
        - 分支跳转(break/continue)：每个 +1
        """
        self.cognitive = 0
        self.nesting_level = 0

        for child in ast.iter_child_nodes(node):
            self._cognitive_visit(child)

    def _cognitive_visit(self, node: ast.AST) -> None:
        """递归访问节点计算认知复杂度。"""
        # 逻辑运算符 +1
        if isinstance(node, ast.BoolOp):
            self.cognitive += len(node.values) - 1
            for value in node.values:
                self._cognitive_visit(value)
            return

        # break/continue +1
        if isinstance(node, (ast.Break, ast.Continue)):
            self.cognitive += 1
            return

        # 控制流语句
        if isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.While,
                ast.With,
                ast.Try,
                ast.ExceptHandler,
            ),
        ):
            # 嵌套层级增加
            self.nesting_level += 1
            self.cognitive += self.nesting_level + 1

            # 递归访问子节点
            for child in ast.iter_child_nodes(node):
                self._cognitive_visit(child)

            # 嵌套层级减少
            self.nesting_level -= 1
            return

        # 其他节点递归访问
        for child in ast.iter_child_nodes(node):
            self._cognitive_visit(child)


class ComplexityAnalyzer:
    """代码复杂度分析器。

    分析Python代码的圈复杂度和认知复杂度。

    示例：
        analyzer = ComplexityAnalyzer()
        report = analyzer.analyze_directory("src/jarvis")
        print(f"高复杂度函数数量: {len(report.high_complexity_functions)}")
    """

    def __init__(self, high_complexity_threshold: int = 10) -> None:
        """初始化分析器。

        Args:
            high_complexity_threshold: 高复杂度阈值（默认10）
        """
        self.high_complexity_threshold = high_complexity_threshold

    def analyze_directory(self, path: str | Path) -> ComplexityReport:
        """分析目录中所有Python文件的复杂度。

        Args:
            path: 目录路径

        Returns:
            复杂度分析报告
        """
        target_path = Path(path)
        if not target_path.is_dir():
            raise ValueError(f"路径不是目录: {target_path}")

        all_functions: list[FunctionComplexity] = []

        # 遍历所有Python文件
        for py_file in target_path.rglob("*.py"):
            # 跳过测试文件和__pycache__
            if (
                "test" in py_file.name
                or "__pycache__" in str(py_file)
                or ".pyc" in str(py_file)
            ):
                continue

            functions = self.analyze_file(py_file)
            all_functions.extend(functions)

        return self._generate_report(all_functions)

    def analyze_file(self, file_path: str | Path) -> list[FunctionComplexity]:
        """分析单个文件的复杂度。

        Args:
            file_path: 文件路径

        Returns:
            函数复杂度列表
        """
        target_path = Path(file_path)
        if not target_path.is_file():
            raise ValueError(f"路径不是文件: {target_path}")

        try:
            source_code = target_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ValueError(f"无法读取文件 {target_path}: {e}")

        return self.analyze_code(source_code, str(target_path))

    def analyze_code(
        self, source_code: str, file_path: str = "<string>"
    ) -> list[FunctionComplexity]:
        """分析代码字符串的复杂度。

        Args:
            source_code: Python源代码
            file_path: 文件路径（用于报告）

        Returns:
            函数复杂度列表
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise ValueError(f"语法错误: {e}")

        functions: list[FunctionComplexity] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                visitor = ComplexityVisitor()
                visitor.visit(node)

                func_complexity = FunctionComplexity(
                    file_path=file_path,
                    function_name=node.name,
                    line_no=node.lineno,
                    cyclomatic=visitor.cyclomatic,
                    cognitive=visitor.cognitive,
                    is_high_complexity=(
                        visitor.cyclomatic > self.high_complexity_threshold
                    ),
                )
                functions.append(func_complexity)

        return functions

    def _generate_report(self, functions: list[FunctionComplexity]) -> ComplexityReport:
        """生成复杂度分析报告。

        Args:
            functions: 函数复杂度列表

        Returns:
            复杂度报告
        """
        if not functions:
            return ComplexityReport()

        # 统计数据
        total_functions = len(functions)
        high_complexity_functions = [f for f in functions if f.is_high_complexity]

        avg_cyclomatic = sum(f.cyclomatic for f in functions) / total_functions
        avg_cognitive = sum(f.cognitive for f in functions) / total_functions

        max_cyclomatic = max(f.cyclomatic for f in functions)
        max_cognitive = max(f.cognitive for f in functions)

        return ComplexityReport(
            total_functions=total_functions,
            high_complexity_functions=high_complexity_functions,
            average_cyclomatic=avg_cyclomatic,
            average_cognitive=avg_cognitive,
            max_cyclomatic=max_cyclomatic,
            max_cognitive=max_cognitive,
        )
