"""
污点分析框架 - 统一的污点分析器抽象接口和数据结构

支持多种分析器后端（Joern、PhASAR、SVF），提供可扩展的规则配置机制。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class TaintSeverity(Enum):
    """污点问题严重程度"""

    CRITICAL = "critical"  # 严重漏洞（命令注入、SQL注入等）
    HIGH = "high"  # 高危漏洞（路径遍历、格式化字符串等）
    MEDIUM = "medium"  # 中危漏洞（信息泄露等）
    LOW = "low"  # 低危问题


@dataclass
class TaintPath:
    """污点传播路径"""

    source: str  # 污点源（如：getenv、read、recv）
    sink: str  # 污点汇（如：system、exec、sprintf）
    path: List[str] = field(default_factory=list)  # 传播路径（节点列表）
    confidence: float = 1.0  # 置信度（0.0-1.0）
    severity: TaintSeverity = TaintSeverity.HIGH  # 严重程度
    description: str = ""  # 问题描述
    file_path: str = ""  # 文件路径
    line_number: int = 0  # 行号
    code_snippet: str = ""  # 代码片段

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "source": self.source,
            "sink": self.sink,
            "path": self.path,
            "confidence": self.confidence,
            "severity": self.severity.value,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
        }


@dataclass
class TaintSource:
    """污点源定义"""

    name: str  # 污点源名称（如：getenv）
    category: str  # 分类（如：user_input、environment、network）
    description: str = ""  # 描述
    patterns: List[str] = field(default_factory=list)  # 匹配模式（函数名、变量名等）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "patterns": self.patterns,
        }


@dataclass
class TaintSink:
    """污点汇定义"""

    name: str  # 污点汇名称（如：system）
    category: str  # 分类（如：command_execution、file_operation）
    severity: TaintSeverity = TaintSeverity.HIGH  # 严重程度
    description: str = ""  # 描述
    patterns: List[str] = field(default_factory=list)  # 匹配模式

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "severity": self.severity.value,
            "description": self.description,
            "patterns": self.patterns,
        }


class TaintAnalyzer(ABC):
    """污点分析器抽象基类"""

    def __init__(self):
        self.sources: List[TaintSource] = []
        self.sinks: List[TaintSink] = []
        self.sanitizers: List[str] = []  # 净化函数列表

    @abstractmethod
    def analyze(self, source_code: str, file_path: str = "") -> List[TaintPath]:
        """
        执行污点分析

        Args:
            source_code: 源代码内容
            file_path: 文件路径（可选）

        Returns:
            污点传播路径列表
        """
        pass

    @abstractmethod
    def analyze_file(self, file_path: str) -> List[TaintPath]:
        """
        分析文件

        Args:
            file_path: 文件路径

        Returns:
            污点传播路径列表
        """
        pass

    def configure_sources(self, sources: List[TaintSource]):
        """配置污点源"""
        self.sources = sources

    def configure_sinks(self, sinks: List[TaintSink]):
        """配置污点汇"""
        self.sinks = sinks

    def configure_sanitizers(self, sanitizers: List[str]):
        """配置净化函数"""
        self.sanitizers = sanitizers

    def add_source(self, source: TaintSource):
        """添加污点源"""
        self.sources.append(source)

    def add_sink(self, sink: TaintSink):
        """添加污点汇"""
        self.sinks.append(sink)

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查分析器是否可用

        Returns:
            True如果分析器已安装并可用
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取分析器名称"""
        pass

    @abstractmethod
    def get_version(self) -> str:
        """获取分析器版本"""
        pass


class TaintRule:
    """污点分析规则"""

    def __init__(
        self,
        name: str,
        sources: List[TaintSource],
        sinks: List[TaintSink],
        sanitizers: Optional[List[str]] = None,
        severity: TaintSeverity = TaintSeverity.HIGH,
        description: str = "",
    ):
        self.name = name
        self.sources = sources
        self.sinks = sinks
        self.sanitizers = sanitizers or []
        self.severity = severity
        self.description = description

    def check(
        self, analyzer: TaintAnalyzer, code: str, file_path: str = ""
    ) -> List[TaintPath]:
        """
        使用污点分析器检查规则

        Args:
            analyzer: 污点分析器实例
            code: 源代码
            file_path: 文件路径

        Returns:
            污点路径列表
        """
        # 配置分析器
        analyzer.configure_sources(self.sources)
        analyzer.configure_sinks(self.sinks)
        analyzer.configure_sanitizers(self.sanitizers)

        # 执行分析
        paths = analyzer.analyze(code, file_path)

        # 设置严重程度和描述
        for path in paths:
            path.severity = self.severity
            if not path.description:
                path.description = (
                    f"{self.name}: 污点从 {path.source} 传播到 {path.sink}"
                )

        return paths

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "sources": [s.to_dict() for s in self.sources],
            "sinks": [s.to_dict() for s in self.sinks],
            "sanitizers": self.sanitizers,
            "severity": self.severity.value,
            "description": self.description,
        }


# ============================================================================
# 预定义污点源
# ============================================================================

# 用户输入
USER_INPUT_SOURCES = [
    TaintSource("getenv", "environment", "从环境变量获取数据", ["getenv"]),
    TaintSource("read", "user_input", "从文件描述符读取", ["read", "recv", "recvfrom"]),
    TaintSource("scanf", "user_input", "从标准输入读取", ["scanf", "fscanf", "sscanf"]),
    TaintSource("gets", "user_input", "从标准输入读取字符串", ["gets", "fgets"]),
    TaintSource("argv", "command_line", "命令行参数", ["argv", "argc"]),
]

# 网络输入
NETWORK_SOURCES = [
    TaintSource("recv", "network", "从网络接收数据", ["recv", "recvfrom", "recvmsg"]),
    TaintSource("accept", "network", "接受网络连接", ["accept", "accept4"]),
]

# 文件输入
FILE_SOURCES = [
    TaintSource("fread", "file", "从文件读取", ["fread", "fgets", "fgetc"]),
    TaintSource("mmap", "file", "内存映射文件", ["mmap", "mmap64"]),
]

# ============================================================================
# 预定义污点汇
# ============================================================================

# 命令执行
COMMAND_SINKS = [
    TaintSink(
        "system",
        "command_execution",
        TaintSeverity.CRITICAL,
        "执行系统命令",
        ["system", "popen"],
    ),
    TaintSink(
        "execve",
        "command_execution",
        TaintSeverity.CRITICAL,
        "执行程序",
        ["execve", "execl", "execlp", "execvp", "execv"],
    ),
]

# 文件操作
FILE_SINKS = [
    TaintSink(
        "open", "file_operation", TaintSeverity.HIGH, "打开文件", ["open", "openat"]
    ),
    TaintSink(
        "fopen",
        "file_operation",
        TaintSeverity.HIGH,
        "打开文件流",
        ["fopen", "freopen"],
    ),
    TaintSink(
        "access",
        "file_operation",
        TaintSeverity.MEDIUM,
        "检查文件权限",
        ["access", "faccessat"],
    ),
]

# 格式化字符串
FORMAT_SINKS = [
    TaintSink(
        "printf",
        "format_string",
        TaintSeverity.HIGH,
        "格式化输出",
        ["printf", "fprintf", "sprintf", "snprintf"],
    ),
]

# SQL操作
SQL_SINKS = [
    TaintSink(
        "sqlite3_exec",
        "sql_injection",
        TaintSeverity.CRITICAL,
        "执行SQL语句",
        ["sqlite3_exec", "mysql_query"],
    ),
]

# 内存操作
MEMORY_SINKS = [
    TaintSink(
        "memcpy",
        "memory_operation",
        TaintSeverity.MEDIUM,
        "内存复制",
        ["memcpy", "memmove"],
    ),
    TaintSink(
        "strcpy",
        "memory_operation",
        TaintSeverity.HIGH,
        "字符串复制",
        ["strcpy", "strcat"],
    ),
]

# ============================================================================
# 预定义规则库
# ============================================================================

TAINT_RULES: Dict[str, TaintRule] = {
    "command_injection": TaintRule(
        "command_injection",
        USER_INPUT_SOURCES + NETWORK_SOURCES,
        COMMAND_SINKS,
        ["escapeshellarg", "escapeshellcmd"],
        TaintSeverity.CRITICAL,
        "命令注入：用户输入直接用于执行系统命令",
    ),
    "format_string": TaintRule(
        "format_string",
        USER_INPUT_SOURCES,
        FORMAT_SINKS,
        [],
        TaintSeverity.HIGH,
        "格式化字符串漏洞：用户输入用作格式化字符串",
    ),
    "path_traversal": TaintRule(
        "path_traversal",
        USER_INPUT_SOURCES + NETWORK_SOURCES,
        FILE_SINKS,
        ["realpath", "basename", "dirname"],
        TaintSeverity.HIGH,
        "路径遍历：用户输入用于文件路径操作",
    ),
    "sql_injection": TaintRule(
        "sql_injection",
        USER_INPUT_SOURCES,
        SQL_SINKS,
        ["sqlite3_prepare_v2", "mysql_real_escape_string"],
        TaintSeverity.CRITICAL,
        "SQL注入：用户输入直接拼接到SQL语句",
    ),
    "buffer_overflow": TaintRule(
        "buffer_overflow",
        USER_INPUT_SOURCES + NETWORK_SOURCES,
        MEMORY_SINKS,
        ["strncpy", "snprintf"],
        TaintSeverity.HIGH,
        "缓冲区溢出：用户输入用于不安全的内存操作",
    ),
}


def get_rule(name: str) -> Optional[TaintRule]:
    """获取指定名称的规则"""
    return TAINT_RULES.get(name)


def get_all_rules() -> List[TaintRule]:
    """获取所有规则"""
    return list(TAINT_RULES.values())


def register_rule(rule: TaintRule):
    """注册自定义规则"""
    TAINT_RULES[rule.name] = rule


# ============================================================================
# 分析器工厂
# ============================================================================


class TaintAnalyzerFactory:
    """污点分析器工厂"""

    _analyzers: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, analyzer_class: type):
        """注册分析器"""
        cls._analyzers[name] = analyzer_class

    @classmethod
    def create(cls, name: str, **kwargs) -> Optional[TaintAnalyzer]:
        """创建分析器实例"""
        analyzer_class = cls._analyzers.get(name)
        if analyzer_class:
            return analyzer_class(**kwargs)
        return None

    @classmethod
    def list_available(cls) -> List[str]:
        """列出所有可用的分析器"""
        available = []
        for name, analyzer_class in cls._analyzers.items():
            try:
                analyzer = analyzer_class()
                if analyzer.is_available():
                    available.append(name)
            except Exception:
                pass
        return available


# ============================================================================
# 辅助函数
# ============================================================================


def analyze_with_best_analyzer(
    code: str, rules: Optional[List[str]] = None, file_path: str = ""
) -> List[TaintPath]:
    """
    使用最佳可用分析器进行分析

    Args:
        code: 源代码
        rules: 要检查的规则名称列表（None表示所有规则）
        file_path: 文件路径

    Returns:
        污点路径列表
    """
    # 获取可用分析器
    available = TaintAnalyzerFactory.list_available()
    if not available:
        return []

    # 选择第一个可用分析器
    analyzer = TaintAnalyzerFactory.create(available[0])
    if not analyzer:
        return []

    # 获取要检查的规则
    if rules:
        rule_objects = [get_rule(r) for r in rules if get_rule(r)]
    else:
        rule_objects = get_all_rules()

    # 执行检查
    all_paths = []
    for rule in rule_objects:
        if rule:  # 确保规则不为None
            paths = rule.check(analyzer, code, file_path)
            all_paths.extend(paths)

    return all_paths
