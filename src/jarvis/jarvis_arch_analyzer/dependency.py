"""依赖关系分析模块。

提供模块依赖关系分析、循环依赖检测和耦合度计算功能。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DependencyNode:
    """依赖节点数据类。

    Attributes:
        module_name: 模块名称
        file_path: 文件路径
        dependencies: 依赖的模块列表
        dependents: 被依赖的模块列表
        level: 依赖层级（0表示顶层）
    """

    module_name: str
    file_path: str
    dependencies: set[str] = field(default_factory=set)
    dependents: set[str] = field(default_factory=set)
    level: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "module_name": self.module_name,
            "file_path": self.file_path,
            "dependencies": sorted(self.dependencies),
            "dependents": sorted(self.dependents),
            "level": self.level,
        }


@dataclass
class CircularDependency:
    """循环依赖数据类。

    Attributes:
        cycle_path: 循环路径
        severity: 严重程度（warning/error）
    """

    cycle_path: list[str]
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "cycle_path": self.cycle_path,
            "severity": self.severity,
            "cycle_str": " -> ".join(self.cycle_path + [self.cycle_path[0]]),
        }


@dataclass
class CouplingMetrics:
    """耦合度指标数据类。

    Attributes:
        afferent_coupling: 入度耦合（Ca）- 被依赖的数量
        efferent_coupling: 出度耦合（Ce）- 依赖的数量
        instability: 不稳定性指标（I = Ce / (Ca + Ce)）
        abstractness: 抽象度（0-1）
        distance: 距离主序列的距离
    """

    module_name: str
    afferent_coupling: int = 0
    efferent_coupling: int = 0
    instability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "module_name": self.module_name,
            "afferent_coupling": self.afferent_coupling,
            "efferent_coupling": self.efferent_coupling,
            "instability": self.instability,
        }


@dataclass
class DependencyReport:
    """依赖关系分析报告。

    Attributes:
        total_modules: 总模块数
        dependency_graph: 依赖图
        circular_dependencies: 循环依赖列表
        coupling_metrics: 耦合度指标列表
        max_depth: 最大依赖深度
        average_coupling: 平均耦合度
    """

    total_modules: int = 0
    dependency_graph: dict[str, DependencyNode] = field(default_factory=dict)
    circular_dependencies: list[CircularDependency] = field(default_factory=list)
    coupling_metrics: list[CouplingMetrics] = field(default_factory=list)
    max_depth: int = 0
    average_coupling: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "total_modules": self.total_modules,
            "dependency_graph": {
                k: v.to_dict() for k, v in self.dependency_graph.items()
            },
            "circular_dependencies": [c.to_dict() for c in self.circular_dependencies],
            "coupling_metrics": [m.to_dict() for m in self.coupling_metrics],
            "max_depth": self.max_depth,
            "average_coupling": self.average_coupling,
        }


class ImportVisitor(ast.NodeVisitor):
    """AST访问器，用于提取import语句。"""

    def __init__(self, module_name: str) -> None:
        """初始化访问器。

        Args:
            module_name: 当前模块名称
        """
        self.module_name = module_name
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        """访问import语句。"""
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """访问from...import语句。"""
        if node.module:
            self.imports.add(node.module.split(".")[0])


class DependencyAnalyzer:
    """依赖关系分析器。

    分析Python项目的模块依赖关系，检测循环依赖和计算耦合度。

    示例：
        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory("src/jarvis")
        print(f"发现 {len(report.circular_dependencies)} 个循环依赖")
    """

    def __init__(self, exclude_patterns: list[str] | None = None) -> None:
        """初始化分析器。

        Args:
            exclude_patterns: 排除模式列表（如"test_*", "__pycache__"）
        """
        self.exclude_patterns = exclude_patterns or [
            "test_*",
            "__pycache__",
            ".pyc",
            "conftest",
        ]
        self._graph: dict[str, DependencyNode] = {}

    def analyze_directory(self, path: str | Path) -> DependencyReport:
        """分析目录中所有Python文件的依赖关系。

        Args:
            path: 目录路径

        Returns:
            依赖关系分析报告
        """
        target_path = Path(path)
        if not target_path.is_dir():
            raise ValueError(f"路径不是目录: {target_path}")

        self._graph.clear()

        # 构建依赖图
        self._build_dependency_graph(target_path)

        # 计算依赖层级
        self._calculate_dependency_levels()

        # 检测循环依赖
        circular_deps = self._detect_circular_dependencies()

        # 计算耦合度
        coupling_metrics = self._calculate_coupling_metrics()

        # 计算最大深度
        max_depth = max((node.level for node in self._graph.values()), default=0)

        # 计算平均耦合度
        avg_coupling = (
            sum(m.efferent_coupling for m in coupling_metrics) / len(coupling_metrics)
            if coupling_metrics
            else 0.0
        )

        return DependencyReport(
            total_modules=len(self._graph),
            dependency_graph=self._graph,
            circular_dependencies=circular_deps,
            coupling_metrics=coupling_metrics,
            max_depth=max_depth,
            average_coupling=avg_coupling,
        )

    def _build_dependency_graph(self, root_path: Path) -> None:
        """构建依赖图。

        Args:
            root_path: 项目根路径
        """
        # 第一步：收集所有模块
        all_modules: dict[str, Path] = {}
        for py_file in root_path.rglob("*.py"):
            # 应用排除模式
            if self._should_exclude(py_file, root_path):
                continue

            # 获取模块名称
            module_name = self._get_module_name(py_file, root_path)
            all_modules[module_name] = py_file

        # 第二步：分析依赖关系
        for module_name, py_file in all_modules.items():
            # 创建或更新节点
            if module_name not in self._graph:
                self._graph[module_name] = DependencyNode(
                    module_name=module_name, file_path=str(py_file)
                )

            # 分析文件依赖（只保留项目内模块）
            dependencies = self._analyze_file_dependencies(
                py_file, set(all_modules.keys())
            )

            # 更新依赖关系
            self._graph[module_name].dependencies.update(dependencies)

            # 更新被依赖关系
            for dep in dependencies:
                if dep not in self._graph:
                    self._graph[dep] = DependencyNode(
                        module_name=dep, file_path=str(all_modules.get(dep, ""))
                    )
                self._graph[dep].dependents.add(module_name)

    def _should_exclude(self, file_path: Path, root_path: Path) -> bool:
        """判断文件是否应该被排除。

        Args:
            file_path: 文件路径
            root_path: 根路径

        Returns:
            是否排除
        """
        relative_path = file_path.relative_to(root_path)

        for pattern in self.exclude_patterns:
            # 简单模式匹配
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                if file_path.name.startswith(prefix):
                    return True
            elif pattern in str(relative_path):
                return True

        return False

    def _get_module_name(self, file_path: Path, root_path: Path) -> str:
        """获取模块名称。

        Args:
            file_path: 文件路径
            root_path: 根路径

        Returns:
            模块名称
        """
        relative_path = file_path.relative_to(root_path)
        parts = list(relative_path.parts[:-1])  # 去掉文件名

        # 添加.py文件的模块名（去掉.py扩展名）
        if file_path.name != "__init__.py":
            parts.append(file_path.stem)

        return ".".join(parts) if parts else file_path.stem

    def _analyze_file_dependencies(
        self, file_path: Path, internal_modules: set[str]
    ) -> set[str]:
        """分析文件的依赖关系。

        Args:
            file_path: 文件路径
            internal_modules: 项目内部模块集合

        Returns:
            依赖的模块集合
        """
        try:
            source_code = file_path.read_text(encoding="utf-8")
        except Exception:
            return set()

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return set()

        module_name = self._get_module_name(file_path, file_path.parent)
        visitor = ImportVisitor(module_name)
        visitor.visit(tree)

        # 只保留项目内模块
        return visitor.imports & internal_modules

    def _is_stdlib(self, module_name: str) -> bool:
        """判断是否为标准库模块。

        Args:
            module_name: 模块名称

        Returns:
            是否为标准库
        """
        # 常见标准库列表
        stdlib_modules = {
            "os",
            "sys",
            "re",
            "json",
            "pathlib",
            "datetime",
            "collections",
            "itertools",
            "functools",
            "typing",
            "dataclasses",
            "enum",
            "logging",
            "unittest",
            "pytest",
            "math",
            "random",
            "hashlib",
            "base64",
            "urllib",
            "http",
            "io",
            "string",
            "textwrap",
        }
        return module_name in stdlib_modules or module_name.startswith("_")

    def _calculate_dependency_levels(self) -> None:
        """计算模块的依赖层级。

        层级定义：
        - 层级0：不被任何模块依赖（顶层模块）
        - 层级N：依赖层级N-1的模块
        """
        # 使用迭代方法计算层级
        # 先初始化所有模块的层级为0
        changed = True
        max_iterations = len(self._graph) + 1  # 防止无限循环
        iteration = 0

        while changed and iteration < max_iterations:
            changed = False
            iteration += 1

            for module_name, node in self._graph.items():
                # 计算当前模块的层级：max(所有被依赖模块的层级) + 1
                if not node.dependencies:
                    # 没有依赖，保持层级0
                    new_level = 0
                else:
                    # 有依赖，层级 = max(被依赖模块的层级) + 1
                    max_dep_level = 0
                    for dep in node.dependencies:
                        if dep in self._graph:
                            dep_level = self._graph[dep].level
                            max_dep_level = max(max_dep_level, dep_level)
                    new_level = max_dep_level + 1

                if node.level != new_level:
                    node.level = new_level
                    changed = True

    def _detect_circular_dependencies(self) -> list[CircularDependency]:
        """检测循环依赖。

        Returns:
            循环依赖列表
        """
        circular_deps: list[CircularDependency] = []
        visited: set[str] = set()
        rec_stack: dict[str, int] = {}  # 节点到在路径中索引的映射
        path: list[str] = []  # 当前路径

        def dfs(node: str) -> list[str] | None:
            """深度优先搜索检测环。

            Args:
                node: 当前节点

            Returns:
                如果发现环，返回环路径；否则返回None
            """
            if node not in self._graph:
                return None

            visited.add(node)
            rec_stack[node] = len(path)
            path.append(node)

            for neighbor in self._graph[node].dependencies:
                if neighbor not in self._graph:
                    continue

                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
                elif neighbor in rec_stack:
                    # 找到环：从neighbor在路径中的位置到当前节点
                    cycle_start_idx = rec_stack[neighbor]
                    cycle = path[cycle_start_idx:] + [neighbor]
                    return cycle

            # 回溯
            path.pop()
            rec_stack.pop(node, None)
            return None

        # 对每个未访问的节点执行DFS
        for module_name in self._graph:
            if module_name not in visited:
                cycle = dfs(module_name)
                if cycle:
                    # 去重并添加
                    cycle_tuple = tuple(cycle)
                    if not any(
                        tuple(c.cycle_path) == cycle_tuple for c in circular_deps
                    ):
                        circular_deps.append(
                            CircularDependency(cycle_path=cycle, severity="warning")
                        )

        return circular_deps

    def _calculate_coupling_metrics(self) -> list[CouplingMetrics]:
        """计算耦合度指标。

        Returns:
            耦合度指标列表
        """
        metrics: list[CouplingMetrics] = []

        for module_name, node in self._graph.items():
            # Afferent Coupling (Ca): 有多少其他模块依赖此模块
            ca = len(node.dependents)

            # Efferent Coupling (Ce): 此模块依赖多少其他模块
            ce = len(node.dependencies)

            # Instability (I) = Ce / (Ca + Ce)
            # I=0: 最稳定（完全被依赖，不依赖他人）
            # I=1: 最不稳定（完全依赖他人，无人依赖）
            instability = ce / (ca + ce) if (ca + ce) > 0 else 0.0

            metrics.append(
                CouplingMetrics(
                    module_name=module_name,
                    afferent_coupling=ca,
                    efferent_coupling=ce,
                    instability=instability,
                )
            )

        return metrics
