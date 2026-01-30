"""代码重复度分析模块。

提供重复代码检测和相似度计算功能。
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


@dataclass
class DuplicatedBlock:
    """重复代码块信息。

    Attributes:
        file_path: 文件路径
        start_line: 起始行号
        end_line: 结束行号
        lines_count: 代码行数
        function_name: 函数名称
        hash: 代码哈希值（用于快速比较）
    """

    file_path: str
    start_line: int
    end_line: int
    lines_count: int
    function_name: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "lines_count": self.lines_count,
            "function_name": self.function_name,
            "hash": self.hash,
        }


@dataclass
class DuplicationPair:
    """重复对信息。

    Attributes:
        block1: 第一个代码块
        block2: 第二个代码块
        similarity: 相似度（0-1）
        duplication_type: 重复类型（exact/similar）
    """

    block1: DuplicatedBlock
    block2: DuplicatedBlock
    similarity: float
    duplication_type: str  # "exact" or "similar"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "block1": self.block1.to_dict(),
            "block2": self.block2.to_dict(),
            "similarity": self.similarity,
            "duplication_type": self.duplication_type,
        }


@dataclass
class DuplicationReport:
    """重复度分析报告。

    Attributes:
        total_functions: 总函数数
        duplicated_functions: 重复函数数
        duplication_pairs: 重复对列表
        duplication_rate: 重复率（重复函数数/总函数数）
        total_duplicated_lines: 总重复代码行数
        average_similarity: 平均相似度
    """

    total_functions: int = 0
    duplicated_functions: int = 0
    duplication_pairs: list[DuplicationPair] = field(default_factory=list)
    duplication_rate: float = 0.0
    total_duplicated_lines: int = 0
    average_similarity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "total_functions": self.total_functions,
            "duplicated_functions": self.duplicated_functions,
            "duplication_pairs": [p.to_dict() for p in self.duplication_pairs],
            "duplication_rate": self.duplication_rate,
            "total_duplicated_lines": self.total_duplicated_lines,
            "average_similarity": self.average_similarity,
        }


class FunctionExtractor(ast.NodeVisitor):
    """AST访问器，用于提取函数定义。"""

    def __init__(self, source_lines: list[str], file_path: str) -> None:
        """初始化访问器。

        Args:
            source_lines: 源代码行列表
            file_path: 文件路径
        """
        self.source_lines = source_lines
        self.file_path = file_path
        self.functions: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """访问函数定义。"""
        # 获取函数的源代码
        start_line = node.lineno
        end_line = node.end_lineno if node.end_lineno else start_line

        # 提取函数体代码（跳过装饰器和文档字符串）
        function_lines = self.source_lines[start_line - 1 : end_line]
        function_code = "\n".join(function_lines)

        # 标准化代码（去除注释和空行）
        normalized_code = self._normalize_code(function_code)

        # 计算代码哈希（仅用于比较，不用于安全目的）
        code_hash = hashlib.md5(
            normalized_code.encode(), usedforsecurity=False
        ).hexdigest()

        self.functions.append(
            {
                "name": node.name,
                "start_line": start_line,
                "end_line": end_line,
                "lines_count": end_line - start_line + 1,
                "code": normalized_code,
                "hash": code_hash,
            }
        )

        # 继续遍历嵌套函数
        self.generic_visit(node)

    def _normalize_code(self, code: str) -> str:
        """标准化代码，去除注释和空行。

        Args:
            code: 原始代码

        Returns:
            标准化后的代码
        """
        lines = []
        for line in code.split("\n"):
            # 去除行尾注释
            if "#" in line:
                line = line[: line.index("#")]

            # 去除首尾空格
            stripped = line.strip()

            # 跳过空行
            if stripped:
                lines.append(stripped)

        return "\n".join(lines)


class DuplicationAnalyzer:
    """代码重复度分析器。

    提供函数级别的重复代码检测功能。

    示例：
        analyzer = DuplicationAnalyzer(min_similarity=0.85, min_lines=5)
        report = analyzer.analyze_directory("src/jarvis")
        print(f"重复率: {report.duplication_rate:.1%}")
    """

    def __init__(
        self,
        min_similarity: float = 0.85,
        min_lines: int = 5,
        max_pairs: int = 50,
    ) -> None:
        """初始化分析器。

        Args:
            min_similarity: 最小相似度阈值（0-1）
            min_lines: 最小函数行数阈值（忽略太短的函数）
            max_pairs: 最大报告重复对数量
        """
        self.min_similarity = min_similarity
        self.min_lines = min_lines
        self.max_pairs = max_pairs

    def analyze_directory(self, path: str | Path) -> DuplicationReport:
        """分析目录中的代码重复度。

        Args:
            path: 目录路径

        Returns:
            重复度分析报告
        """
        target_path = Path(path)
        if not target_path.exists():
            return DuplicationReport()

        # 收集所有函数
        all_functions: list[dict[str, Any]] = []
        for py_file in target_path.rglob("*.py"):
            # 跳过测试文件（test_*.py）和__pycache__
            if (
                py_file.name.startswith("test_")
                and py_file.suffix == ".py"
                or "__pycache__" in py_file.parts
                or ".pyc" in py_file.name
            ):
                continue

            file_functions = self._extract_functions_from_file(py_file)
            all_functions.extend(file_functions)

        # 查找重复对
        duplication_pairs = self._find_duplications(all_functions)

        # 计算统计信息
        function_names: set[str] = set()
        for pair in duplication_pairs:
            function_names.add(pair.block1.function_name)
            function_names.add(pair.block2.function_name)
        duplicated_functions = len(function_names)

        total_functions = len(all_functions)
        duplication_rate = (
            duplicated_functions / total_functions if total_functions > 0 else 0.0
        )

        total_duplicated_lines = sum(
            pair.block1.lines_count for pair in duplication_pairs
        )

        average_similarity = (
            sum(pair.similarity for pair in duplication_pairs) / len(duplication_pairs)
            if duplication_pairs
            else 0.0
        )

        return DuplicationReport(
            total_functions=total_functions,
            duplicated_functions=duplicated_functions,
            duplication_pairs=duplication_pairs[: self.max_pairs],
            duplication_rate=duplication_rate,
            total_duplicated_lines=total_duplicated_lines,
            average_similarity=average_similarity,
        )

    def _extract_functions_from_file(self, file_path: Path) -> list[dict[str, Any]]:
        """从文件中提取函数。

        Args:
            file_path: 文件路径

        Returns:
            函数列表
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                source = f.read()
        except Exception:
            return []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        source_lines = source.split("\n")
        extractor = FunctionExtractor(source_lines, str(file_path))
        extractor.visit(tree)

        # 过滤掉太短的函数
        return [
            func
            for func in extractor.functions
            if func["lines_count"] >= self.min_lines
        ]

    def _find_duplications(
        self, functions: list[dict[str, Any]]
    ) -> list[DuplicationPair]:
        """查找重复函数对。

        Args:
            functions: 函数列表

        Returns:
            重复对列表
        """
        duplication_pairs: list[DuplicationPair] = []
        checked_pairs: set[tuple[str, str]] = set()

        # 按哈希分组，快速查找完全重复
        hash_groups: dict[str, list[dict[str, Any]]] = {}
        for func in functions:
            hash_val = func["hash"]
            if hash_val not in hash_groups:
                hash_groups[hash_val] = []
            hash_groups[hash_val].append(func)

        # 查找重复
        for i, func1 in enumerate(functions):
            for func2 in functions[i + 1 :]:
                # 避免重复检查同一对
                pair_key = tuple(sorted([func1["name"], func2["name"]]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                # 跳过同一个文件的同一个函数
                if func1["name"] == func2["name"] and func1.get(
                    "file_path"
                ) == func2.get("file_path"):
                    continue

                # 检查是否完全重复（哈希相同）
                if func1["hash"] == func2["hash"]:
                    similarity = 1.0
                    duplication_type = "exact"
                else:
                    # 计算相似度
                    similarity = self._calculate_similarity(
                        func1["code"], func2["code"]
                    )

                    # 只保留高于阈值的相似度
                    if similarity < self.min_similarity:
                        continue

                    duplication_type = "similar"

                # 创建重复对
                block1 = DuplicatedBlock(
                    file_path=func1.get("file_path", "unknown"),
                    start_line=func1["start_line"],
                    end_line=func1["end_line"],
                    lines_count=func1["lines_count"],
                    function_name=func1["name"],
                    hash=func1["hash"],
                )

                block2 = DuplicatedBlock(
                    file_path=func2.get("file_path", "unknown"),
                    start_line=func2["start_line"],
                    end_line=func2["end_line"],
                    lines_count=func2["lines_count"],
                    function_name=func2["name"],
                    hash=func2["hash"],
                )

                duplication_pairs.append(
                    DuplicationPair(
                        block1=block1,
                        block2=block2,
                        similarity=similarity,
                        duplication_type=duplication_type,
                    )
                )

        # 按相似度排序
        duplication_pairs.sort(key=lambda p: p.similarity, reverse=True)

        return duplication_pairs

    def _calculate_similarity(self, code1: str, code2: str) -> float:
        """计算两段代码的相似度。

        Args:
            code1: 第一段代码
            code2: 第二段代码

        Returns:
            相似度（0-1）
        """
        return SequenceMatcher(None, code1, code2).ratio()
