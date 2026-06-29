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

# 内存释放（UAF源）
FREE_SOURCES = [
    TaintSource("free", "memory_free", "释放内存", ["free"]),
    TaintSource("delete", "memory_free", "删除对象", ["delete"]),
]

# 指针解引用（UAF汇）
DEREF_SINKS = [
    TaintSink(
        "pointer_deref",
        "pointer_access",
        TaintSeverity.CRITICAL,
        "指针解引用",
        ["->", "*", "[]"],
    ),
]

# Double Free汇
FREE_SINKS = [
    TaintSink(
        "free",
        "memory_free",
        TaintSeverity.CRITICAL,
        "释放内存",
        ["free"],
    ),
]

# 内存分配源（malloc_null_check）
ALLOC_SOURCES = [
    TaintSource("malloc", "memory_alloc", "分配内存", ["malloc"]),
    TaintSource("calloc", "memory_alloc", "分配内存", ["calloc"]),
    TaintSource("realloc", "memory_alloc", "重新分配内存", ["realloc"]),
    TaintSource("new", "memory_alloc", "创建对象", ["new"]),
]

# NULL检查汇（用于检测malloc后是否有NULL检查）
NULL_CHECK_SINKS = [
    TaintSink(
        "null_check",
        "null_check",
        TaintSeverity.LOW,
        "NULL检查",
        ["if", "while", "?"],
    ),
]

# realloc返回值汇（用于检测realloc返回值是否被使用）
REALLOC_USE_SINKS = [
    TaintSink(
        "realloc_use",
        "realloc_use",
        TaintSeverity.HIGH,
        "realloc返回值使用",
        ["=", "return"],
    ),
]

# IO返回值检查汇（用于检测IO函数返回值是否被检查）
IO_CHECK_SINKS = [
    TaintSink(
        "io_check",
        "io_check",
        TaintSeverity.LOW,
        "IO返回值检查",
        ["if", "while", "<", ">", "==", "!=", "<=", ">="],
    ),
]

# getenv返回值检查汇（用于检测getenv返回值是否被检查NULL）
GETENV_CHECK_SINKS = [
    TaintSink(
        "getenv_check",
        "getenv_check",
        TaintSeverity.LOW,
        "getenv返回值检查",
        ["if", "while", "NULL", "0"],
    ),
]

# realloc源（realloc返回值）
REALLOC_SOURCES = [
    TaintSource("realloc", "realloc_return", "realloc返回值", ["realloc"]),
]

# IO函数源（IO返回值）
IO_SOURCES = [
    TaintSource("read", "io_return", "读取返回值", ["read", "fread", "recv"]),
    TaintSource("write", "io_return", "写入返回值", ["write", "fwrite", "send"]),
    TaintSource("fopen", "io_return", "打开文件返回值", ["fopen", "open"]),
]

# getenv源（getenv返回值）
GETENV_SOURCES = [
    TaintSource("getenv", "getenv_return", "getenv返回值", ["getenv"]),
]

# ============================================================================
# Rust特定污点源
# ============================================================================

# Rust用户输入源
RUST_USER_INPUT_SOURCES = [
    TaintSource(
        "stdin",
        "user_input",
        "从标准输入读取",
        ["stdin", "io::stdin", "std::io::stdin"],
    ),
    TaintSource(
        "read_line", "user_input", "读取一行输入", ["read_line", "read_to_string"]
    ),
    TaintSource(
        "args", "command_line", "命令行参数", ["args", "env::args", "std::env::args"]
    ),
    TaintSource("var", "environment", "环境变量", ["var", "env::var", "std::env::var"]),
    TaintSource(
        "vars", "environment", "所有环境变量", ["vars", "env::vars", "std::env::vars"]
    ),
]

# Rust网络输入源
RUST_NETWORK_SOURCES = [
    TaintSource(
        "tcp_read", "network", "TCP读取", ["TcpStream::read", "read", "read_exact"]
    ),
    TaintSource("udp_recv", "network", "UDP接收", ["recv", "recv_from"]),
    TaintSource(
        "http_request", "network", "HTTP请求体", ["body", "into_body", "bytes"]
    ),
]

# Rust文件输入源
RUST_FILE_SOURCES = [
    TaintSource(
        "file_read", "file", "文件读取", ["File::open", "read_to_string", "read_to_end"]
    ),
    TaintSource("fs_read", "file", "文件系统读取", ["fs::read", "fs::read_to_string"]),
]

# Rust FFI输入源（从C代码传入的数据）
RUST_FFI_SOURCES = [
    TaintSource(
        "ffi_ptr",
        "ffi",
        "FFI指针数据",
        ["from_raw", "from_raw_parts", "CStr::from_ptr"],
    ),
    TaintSource(
        "ffi_cstring", "ffi", "FFI字符串", ["CString::from_raw", "CStr::from_ptr"]
    ),
]

# Rust unsafe块输出源
RUST_UNSAFE_SOURCES = [
    TaintSource("unsafe_deref", "unsafe_op", "unsafe解引用", ["deref", "*"]),
    TaintSource(
        "unsafe_cast", "unsafe_op", "unsafe类型转换", ["transmute", "from_raw_parts"]
    ),
]

# ============================================================================
# Rust特定污点汇
# ============================================================================

# Rust命令执行汇
RUST_COMMAND_SINKS = [
    TaintSink(
        "Command::new",
        "command_execution",
        TaintSeverity.CRITICAL,
        "执行系统命令",
        ["Command::new", "process::Command", "std::process::Command"],
    ),
    TaintSink(
        "output",
        "command_execution",
        TaintSeverity.CRITICAL,
        "获取命令输出",
        ["output", "status", "spawn"],
    ),
]

# Rust文件操作汇
RUST_FILE_SINKS = [
    TaintSink(
        "File::create",
        "file_operation",
        TaintSeverity.HIGH,
        "创建文件",
        ["File::create", "OpenOptions::new", "fs::write"],
    ),
    TaintSink(
        "fs::remove",
        "file_operation",
        TaintSeverity.HIGH,
        "删除文件",
        ["fs::remove_file", "fs::remove_dir"],
    ),
    TaintSink(
        "fs::copy",
        "file_operation",
        TaintSeverity.MEDIUM,
        "复制文件",
        ["fs::copy", "fs::rename"],
    ),
]

# Rust内存操作汇
RUST_MEMORY_SINKS = [
    TaintSink(
        "write",
        "memory_operation",
        TaintSeverity.HIGH,
        "内存写入",
        ["write", "write_bytes", "copy", "copy_nonoverlapping"],
    ),
    TaintSink(
        "from_raw_parts",
        "memory_operation",
        TaintSeverity.HIGH,
        "从原始指针构造",
        ["from_raw_parts", "from_raw_parts_mut", "from_raw"],
    ),
]

# Rust格式化字符串汇
RUST_FORMAT_SINKS = [
    TaintSink(
        "format!",
        "format_string",
        TaintSeverity.MEDIUM,
        "格式化字符串",
        ["format!", "print!", "println!", "eprint!", "eprintln!"],
    ),
]

# Rust panic汇（可能导致状态不一致）
RUST_PANIC_SINKS = [
    TaintSink(
        "panic!",
        "panic",
        TaintSeverity.MEDIUM,
        "panic终止程序",
        ["panic!", "unreachable!", "todo!", "unimplemented!"],
    ),
]

# Rust错误忽略汇（let _ = ...）
RUST_ERROR_IGNORE_SINKS = [
    TaintSink(
        "let _",
        "error_ignore",
        TaintSeverity.MEDIUM,
        "忽略错误结果",
        ["let _", "drop"],
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
    "use_after_free": TaintRule(
        "use_after_free",
        FREE_SOURCES,
        DEREF_SINKS,
        [],  # 无净化函数
        TaintSeverity.CRITICAL,
        "Use-After-Free：释放后的内存被解引用使用",
    ),
    "double_free": TaintRule(
        "double_free",
        FREE_SOURCES,
        FREE_SINKS,
        [],  # 无净化函数
        TaintSeverity.CRITICAL,
        "Double Free：同一内存被重复释放",
    ),
    "malloc_null_check": TaintRule(
        "malloc_null_check",
        ALLOC_SOURCES,
        DEREF_SINKS,  # 分配后直接解引用，未检查NULL
        ["if", "while", "?"],  # NULL检查作为净化
        TaintSeverity.HIGH,
        "内存分配后未检查NULL：分配结果直接使用未检查是否成功",
    ),
    "null_deref": TaintRule(
        "null_deref",
        USER_INPUT_SOURCES + ALLOC_SOURCES,
        DEREF_SINKS,
        ["if", "while", "?"],  # NULL检查作为净化
        TaintSeverity.HIGH,
        "空指针解引用：可能为NULL的指针被直接解引用",
    ),
    "realloc_assign_back": TaintRule(
        "realloc_assign_back",
        REALLOC_SOURCES,
        REALLOC_USE_SINKS,
        [],  # 无净化函数
        TaintSeverity.HIGH,
        "realloc返回值未使用：realloc返回值未赋值回原指针可能导致内存泄漏",
    ),
    "unchecked_io": TaintRule(
        "unchecked_io",
        IO_SOURCES,
        IO_CHECK_SINKS,
        [],  # 无净化函数
        TaintSeverity.MEDIUM,
        "IO返回值未检查：IO函数返回值未检查可能导致错误处理缺失",
    ),
    "getenv_unchecked": TaintRule(
        "getenv_unchecked",
        GETENV_SOURCES,
        GETENV_CHECK_SINKS,
        [],  # 无净化函数
        TaintSeverity.MEDIUM,
        "getenv返回值未检查：getenv返回值未检查NULL可能导致空指针解引用",
    ),
    # ============================================================================
    # Rust特定污点规则
    # ============================================================================
    "rust_command_injection": TaintRule(
        "rust_command_injection",
        RUST_USER_INPUT_SOURCES + RUST_NETWORK_SOURCES,
        RUST_COMMAND_SINKS,
        ["shlex::split", "shell_words::split"],  # Rust命令净化
        TaintSeverity.CRITICAL,
        "Rust命令注入：用户输入直接用于执行系统命令",
    ),
    "rust_path_traversal": TaintRule(
        "rust_path_traversal",
        RUST_USER_INPUT_SOURCES + RUST_NETWORK_SOURCES,
        RUST_FILE_SINKS,
        ["Path::canonicalize", "PathBuf::canonicalize"],  # Rust路径净化
        TaintSeverity.HIGH,
        "Rust路径遍历：用户输入用于文件路径操作",
    ),
    "rust_format_string": TaintRule(
        "rust_format_string",
        RUST_USER_INPUT_SOURCES,
        RUST_FORMAT_SINKS,
        [],
        TaintSeverity.MEDIUM,
        "Rust格式化字符串：用户输入用作格式化字符串",
    ),
    "rust_memory_safety": TaintRule(
        "rust_memory_safety",
        RUST_FFI_SOURCES + RUST_UNSAFE_SOURCES,
        RUST_MEMORY_SINKS,
        [],
        TaintSeverity.HIGH,
        "Rust内存安全：FFI/unsafe数据用于内存操作",
    ),
    "rust_panic_usage": TaintRule(
        "rust_panic_usage",
        RUST_USER_INPUT_SOURCES,
        RUST_PANIC_SINKS,
        [],
        TaintSeverity.MEDIUM,
        "Rust panic使用：用户输入可能导致panic",
    ),
    "rust_error_ignore": TaintRule(
        "rust_error_ignore",
        RUST_USER_INPUT_SOURCES + RUST_NETWORK_SOURCES,
        RUST_ERROR_IGNORE_SINKS,
        [],
        TaintSeverity.MEDIUM,
        "Rust错误忽略：可能忽略错误结果",
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
    code: str,
    rules: Optional[List[str]] = None,
    file_path: str = "",
    database: Optional[Any] = None,
) -> List[TaintPath]:
    """
    使用最佳可用分析器进行分析

    Args:
        code: 源代码
        rules: 要检查的规则名称列表（None表示所有规则）
        file_path: 文件路径
        database: 项目数据库实例（可选，传递给builtin分析器）

    Returns:
        污点路径列表
    """
    # 获取可用分析器
    available = TaintAnalyzerFactory.list_available()
    if not available:
        return []

    # 选择第一个可用分析器，传入database参数
    analyzer = TaintAnalyzerFactory.create(available[0], database=database)
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
