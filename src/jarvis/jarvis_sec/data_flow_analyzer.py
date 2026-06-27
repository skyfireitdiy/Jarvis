# -*- coding: utf-8 -*-
"""内置数据流分析器 - 基于ProjectDatabase的数据流分析

不依赖外部工具（Joern等），直接使用DataCollector收集的数据进行污点传播分析。
数据来源：
- data_flow表：变量的定义和使用位置
- call_graph表：函数调用关系
- pointer_states表：指针状态追踪

核心算法：
1. 从污点源（sources）开始，识别受污染的变量
2. 沿数据流传播，追踪污染变量的使用
3. 检查是否到达污点汇（sinks）
4. 检查是否经过净化函数（sanitizers）
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
from dataclasses import dataclass

from jarvis.jarvis_sec.taint_analyzer import (
    TaintAnalyzer,
    TaintPath,
    TaintSource,
    TaintSink,
    TaintSeverity,
    TaintAnalyzerFactory,
)
from jarvis.jarvis_sec.project_database import ProjectDatabase


@dataclass
class TaintState:
    """污点状态追踪"""

    var_name: str
    source: str
    file_path: str
    line: int
    scope: str
    sanitized: bool = False


class BuiltinDataFlowAnalyzer(TaintAnalyzer):
    """内置数据流分析器 - 基于ProjectDatabase"""

    def __init__(
        self,
        database: Optional[ProjectDatabase] = None,
        project_path: Optional[str] = None,
    ):
        super().__init__()
        self.database = database
        self.project_path = project_path
        self._taint_states: Dict[str, List[TaintState]] = {}  # var_name -> states
        self._visited: Set[Tuple[str, str, int]] = set()  # (var_name, file, line)

    def is_available(self) -> bool:
        """始终可用，不依赖外部工具"""
        return True

    def get_name(self) -> str:
        return "builtin"

    def get_version(self) -> str:
        return "1.0.0"

    def analyze(self, source_code: str, file_path: str = "") -> List[TaintPath]:
        """分析源代码中的污点传播路径

        Args:
            source_code: 源代码内容
            file_path: 文件路径

        Returns:
            污点传播路径列表
        """
        if not self.database:
            # 尝试从project_path创建数据库连接
            if self.project_path:
                db_path = Path(self.project_path) / ".jarvis" / "jsec" / "analysis.db"
                if db_path.exists():
                    self.database = ProjectDatabase(
                        self.project_path, db_path=str(db_path)
                    )
            else:
                return []

        if not self.database:
            return []

        # 清理状态
        self._taint_states.clear()
        self._visited.clear()

        # 执行污点分析
        paths = self._analyze_taint_flow(file_path)
        return paths

    def analyze_file(self, file_path: str) -> List[TaintPath]:
        """分析单个文件"""
        if not self.database:
            return []

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source_code = f.read()

        rel_path = self._get_relative_path(file_path)
        return self.analyze(source_code, rel_path)

    def _get_relative_path(self, file_path: str) -> str:
        """获取相对路径"""
        if self.project_path:
            try:
                return str(Path(file_path).relative_to(self.project_path))
            except ValueError:
                pass
        return file_path

    def _analyze_taint_flow(self, file_path: str) -> List[TaintPath]:
        """执行污点流分析

        核心算法：
        1. 识别污点源（sources）
        2. 传播污点沿数据流
        3. 检查是否到达污点汇（sinks）
        4. 检查是否经过净化函数（sanitizers）
        """
        paths = []

        # 1. 识别污点源
        source_vars = self._identify_sources(file_path)

        # 2. 传播污点
        for var_name, source_info in source_vars.items():
            self._propagate_taint(var_name, source_info)

        # 3. 检查污点汇
        for var_name, states in self._taint_states.items():
            for state in states:
                if state.sanitized:
                    continue
                sink_hits = self._check_sinks(var_name, state)
                for sink_info in sink_hits:
                    path = TaintPath(
                        source=state.source,
                        sink=sink_info["sink"],
                        path=[var_name],
                        confidence=0.8,
                        severity=TaintSeverity.HIGH,
                        description=f"污点从 {state.source} 传播到 {sink_info['sink']}",
                        file_path=sink_info["file_path"],
                        line_number=sink_info["line"],
                        code_snippet=sink_info.get("code", ""),
                    )
                    paths.append(path)

        return paths

    def _identify_sources(self, file_path: str) -> Dict[str, Dict[str, Any]]:
        """识别污点源变量

        从数据库查询data_flow表，找出值来源为污点源的变量
        """
        source_vars = {}

        if not self.database:
            return source_vars

        # 获取文件的数据流节点
        flow_nodes = self.database.get_data_flow_by_file(file_path)

        # 检查每个定义节点是否来自污点源
        for node in flow_nodes:
            if node["node_type"] != "def":
                continue

            var_name = node["var_name"]
            value_source = node.get("value_source", "")

            # 检查value_source是否匹配配置的污点源
            for source in self.sources:
                for pattern in source.patterns:
                    if pattern in value_source or value_source == pattern:
                        source_vars[var_name] = {
                            "source": source.name,
                            "file_path": node["file_path"],
                            "line": node["line"],
                            "scope": node["scope"],
                        }
                        break

        # 也检查函数参数（param_in）
        for node in flow_nodes:
            if node["node_type"] == "param_in":
                var_name = node["var_name"]
                # 参数可能来自外部调用者，视为潜在污点源
                for source in self.sources:
                    if source.category in ("user_input", "network", "environment"):
                        # 检查调用者是否来自外部输入函数
                        if not self.database:
                            continue
                        callers = self.database.get_callers(node["scope"])
                        for caller in callers:
                            caller_name = caller["caller_name"]
                            for src in self.sources:
                                if caller_name in src.patterns:
                                    source_vars[var_name] = {
                                        "source": src.name,
                                        "file_path": node["file_path"],
                                        "line": node["line"],
                                        "scope": node["scope"],
                                    }

        return source_vars

    def _propagate_taint(self, var_name: str, source_info: Dict[str, Any]):
        """传播污点沿数据流

        从污点源变量开始，追踪其使用和传播
        """
        if not self.database:
            return

        # 初始污点状态
        initial_state = TaintState(
            var_name=var_name,
            source=source_info["source"],
            file_path=source_info["file_path"],
            line=source_info["line"],
            scope=source_info["scope"],
        )
        self._taint_states[var_name] = [initial_state]
        self._visited.add((var_name, source_info["file_path"], source_info["line"]))

        # 获取该变量的使用位置
        use_sites = self.database.get_use_sites(var_name, source_info["scope"])

        for use in use_sites:
            key = (var_name, use["file_path"], use["line"])
            if key in self._visited:
                continue
            self._visited.add(key)

            # 检查是否经过净化函数
            sanitized = self._check_sanitization(use)

            # 添加污点状态
            state = TaintState(
                var_name=var_name,
                source=source_info["source"],
                file_path=use["file_path"],
                line=use["line"],
                scope=use["scope"],
                sanitized=sanitized,
            )
            if var_name not in self._taint_states:
                self._taint_states[var_name] = []
            self._taint_states[var_name].append(state)

            # 继续传播（赋值给其他变量）
            self._propagate_assignment(var_name, source_info, use)

    def _propagate_assignment(
        self, source_var: str, source_info: Dict[str, Any], use_site: Dict[str, Any]
    ):
        """传播污点到赋值目标变量

        例如: char* p = user_input; 则p也被污染
        """
        if not self.database:
            return

        # 获取同一scope内的定义节点，检查是否有变量被赋值为source_var
        flow_nodes = self.database.get_data_flow_by_file(use_site["file_path"])

        for node in flow_nodes:
            if node["node_type"] != "def":
                continue
            if node["scope"] != use_site["scope"]:
                continue
            if node["line"] <= source_info["line"]:
                continue

            # 检查value_source是否包含source_var
            value_source = node.get("value_source", "")
            if source_var in value_source:
                target_var = node["var_name"]
                key = (target_var, node["file_path"], node["line"])
                if key in self._visited:
                    continue

                # 传播污点到目标变量
                self._propagate_taint(
                    target_var,
                    {
                        "source": source_info["source"],
                        "file_path": node["file_path"],
                        "line": node["line"],
                        "scope": node["scope"],
                    },
                )

    def _check_sanitization(self, use_site: Dict[str, Any]) -> bool:
        """检查是否经过净化函数"""
        if not self.database:
            return False

        # 获取调用关系，检查是否调用了净化函数
        callees = self.database.get_callees(use_site["scope"], use_site["file_path"])

        for callee in callees:
            callee_name = callee["callee_name"]
            if callee_name in self.sanitizers:
                return True

        return False

    def _check_sinks(self, var_name: str, state: TaintState) -> List[Dict[str, Any]]:
        """检查污点变量是否到达污点汇"""
        sink_hits = []

        if not self.database:
            return sink_hits

        # 获取变量的使用位置
        use_sites = self.database.get_use_sites(var_name, state.scope)

        for use in use_sites:
            # 检查使用位置是否匹配污点汇
            for sink in self.sinks:
                for pattern in sink.patterns:
                    # 检查是否在sink函数的参数中使用
                    if self._is_sink_use(use, pattern, var_name):
                        sink_hits.append(
                            {
                                "sink": sink.name,
                                "file_path": use["file_path"],
                                "line": use["line"],
                                "code": f"{var_name} used in {sink.name}",
                            }
                        )

        return sink_hits

    def _is_sink_use(
        self, use_site: Dict[str, Any], sink_pattern: str, var_name: str
    ) -> bool:
        """检查使用位置是否是污点汇

        sink_pattern可能是函数名（如system）或操作符（如->、*）
        """
        if not self.database:
            return False

        # 获取调用关系
        callees = self.database.get_callees(use_site["scope"], use_site["file_path"])

        for callee in callees:
            if callee["callee_name"] == sink_pattern:
                # 检查调用行是否在use_site附近
                if abs(callee["caller_line"] - use_site["line"]) <= 2:
                    return True

        # 对于操作符类型的sink（如解引用），检查use_site本身
        if sink_pattern in ("->", "*", "[]"):  # 解引用操作
            # 检查是否是解引用使用
            # 这里需要更精细的AST分析，暂时用启发式
            return True  # 简化处理

        return False


# 注册分析器
TaintAnalyzerFactory.register("builtin", BuiltinDataFlowAnalyzer)


# ---------------------------
# 数据流分析相关类（兼容c_checker导入）
# ---------------------------


@dataclass
class DataFlowResult:
    """数据流分析结果"""

    var_name: str
    def_sites: List[Dict[str, Any]]  # 定义位置列表
    use_sites: List[Dict[str, Any]]  # 使用位置列表
    flows_to: List[str]  # 流向的变量列表
    tainted: bool = False  # 是否被污染
    ownership_transfer: Optional[List[str]] = None  # 所有权转移的变量列表
    freed_vars: Optional[List[str]] = None  # 已释放的变量列表
    null_checked_vars: Optional[List[str]] = None  # 已检查NULL的变量列表
    dead_code_lines: Optional[List[int]] = None  # 死代码行号列表
    null_checks: Optional[List[str]] = None  # NULL检查的变量列表

    def __post_init__(self):
        if self.ownership_transfer is None:
            self.ownership_transfer = []
        if self.freed_vars is None:
            self.freed_vars = []
        if self.null_checked_vars is None:
            self.null_checked_vars = []
        if self.dead_code_lines is None:
            self.dead_code_lines = []
        if self.null_checks is None:
            self.null_checks = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "var_name": self.var_name,
            "def_sites": self.def_sites,
            "use_sites": self.use_sites,
            "flows_to": self.flows_to,
            "tainted": self.tainted,
            "ownership_transfer": self.ownership_transfer,
            "freed_vars": self.freed_vars,
            "null_checked_vars": self.null_checked_vars,
            "dead_code_lines": self.dead_code_lines,
            "null_checks": self.null_checks,
        }


@dataclass
class PointerState:
    """指针状态追踪"""

    var_name: str
    points_to: List[str]  # 指向的变量/内存位置
    is_null: bool = False  # 是否可能为NULL
    is_freed: bool = False  # 是否已释放
    is_tainted: bool = False  # 是否被污染
    file_path: str = ""
    line: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "var_name": self.var_name,
            "points_to": self.points_to,
            "is_null": self.is_null,
            "is_freed": self.is_freed,
            "is_tainted": self.is_tainted,
            "file_path": self.file_path,
            "line": self.line,
        }


class DataFlowAnalyzer:
    """数据流分析器 - 高级接口

    提供更丰富的数据流分析功能，包括指针分析、污点传播等。
    这是BuiltinDataFlowAnalyzer的高级封装。
    """

    def __init__(
        self,
        database: Optional[ProjectDatabase] = None,
        project_path: Optional[str] = None,
    ):
        self._analyzer = BuiltinDataFlowAnalyzer(
            database=database, project_path=project_path
        )
        self.database = database
        self.project_path = project_path
        self._pointer_states: Dict[str, PointerState] = {}

    def analyze(self, source_code: str, file_path: str = "") -> List[TaintPath]:
        """执行污点分析"""
        return self._analyzer.analyze(source_code, file_path)

    def analyze_file(self, file_path: str) -> List[TaintPath]:
        """分析单个文件"""
        return self._analyzer.analyze_file(file_path)

    def analyze_code(
        self,
        source_code: str,
        is_cpp: bool = False,
        database: Optional[ProjectDatabase] = None,
        file_path: str = "",
    ) -> "DataFlowResult":
        """分析源代码的数据流

        兼容c_checker的调用接口。

        Args:
            source_code: 源代码内容
            is_cpp: 是否为C++代码
            database: 项目数据库
            file_path: 文件路径

        Returns:
            DataFlowResult对象
        """
        # 更新数据库引用
        if database:
            self.database = database
            self._analyzer.database = database

        # 执行污点分析
        taint_paths = self._analyzer.analyze(source_code, file_path)

        # 返回一个默认的DataFlowResult
        # TODO: 根据实际分析结果填充
        return DataFlowResult(
            var_name="",
            def_sites=[],
            use_sites=[],
            flows_to=[],
            tainted=len(taint_paths) > 0,
        )

    def get_data_flow_result(
        self, var_name: str, scope: str = ""
    ) -> Optional[DataFlowResult]:
        """获取变量的数据流分析结果

        Args:
            var_name: 变量名
            scope: 作用域（函数名）

        Returns:
            DataFlowResult或None
        """
        if not self.database:
            return None

        def_sites = self.database.get_def_sites(var_name, scope)
        use_sites = self.database.get_use_sites(var_name, scope)

        if not def_sites and not use_sites:
            return None

        # 分析流向
        flows_to = []
        for use in use_sites:
            target = use.get("target_var")
            if target and target not in flows_to:
                flows_to.append(target)

        return DataFlowResult(
            var_name=var_name,
            def_sites=def_sites,
            use_sites=use_sites,
            flows_to=flows_to,
            tainted=False,
        )

    def get_pointer_state(
        self, var_name: str, file_path: str = "", line: int = 0
    ) -> Optional[PointerState]:
        """获取指针状态

        Args:
            var_name: 指针变量名
            file_path: 文件路径
            line: 行号

        Returns:
            PointerState或None
        """
        # 检查缓存
        cache_key = f"{var_name}@{file_path}:{line}"
        if cache_key in self._pointer_states:
            return self._pointer_states[cache_key]

        if not self.database:
            return None

        # 从数据库查询指针状态
        # TODO: 实现基于pointer_states表的查询
        state = PointerState(
            var_name=var_name,
            points_to=[],
            is_null=False,
            is_freed=False,
            is_tainted=False,
            file_path=file_path,
            line=line,
        )

        self._pointer_states[cache_key] = state
        return state

    def is_tainted(self, var_name: str, scope: str = "") -> bool:
        """检查变量是否被污染"""
        result = self.get_data_flow_result(var_name, scope)
        if result:
            return result.tainted
        return False

    def configure_sources(self, sources: List[TaintSource]):
        """配置污点源"""
        self._analyzer.configure_sources(sources)

    def configure_sinks(self, sinks: List[TaintSink]):
        """配置污点汇"""
        self._analyzer.configure_sinks(sinks)

    def configure_sanitizers(self, sanitizers: List[str]):
        """配置净化函数"""
        self._analyzer.configure_sanitizers(sanitizers)


# 辅助函数：创建分析器实例
def create_builtin_analyzer(
    project_path: str, database: Optional[ProjectDatabase] = None
) -> BuiltinDataFlowAnalyzer:
    """创建内置数据流分析器实例"""
    return BuiltinDataFlowAnalyzer(database=database, project_path=project_path)


# 辅助函数：使用内置分析器进行污点分析
def analyze_taint_builtin(
    project_path: str,
    file_path: str,
    sources: List[TaintSource],
    sinks: List[TaintSink],
    sanitizers: Optional[List[str]] = None,
    database: Optional[ProjectDatabase] = None,
) -> List[TaintPath]:
    """使用内置分析器进行污点分析"""
    analyzer = create_builtin_analyzer(project_path, database)
    analyzer.configure_sources(sources)
    analyzer.configure_sinks(sinks)
    if sanitizers:
        analyzer.configure_sanitizers(sanitizers)

    return analyzer.analyze_file(file_path)
