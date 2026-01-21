# -*- coding: utf-8 -*-
import os
import re
from typing import Any
from typing import Callable
from typing import Optional
from typing import Tuple
from typing import Union
from typing import Dict

from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.config import calculate_token_limit, get_max_input_token_count

# 语言提取器注册表（导出供其他模块使用）
_LANGUAGE_EXTRACTORS: dict[str, Callable[[], Optional[Any]]] = {}


def is_text_file(filepath: str) -> bool:
    """
    Check if a file is a text file.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            f.read(1024)  # Try to read a small chunk
        return True
    except (UnicodeDecodeError, IOError):
        return False


def count_lines(filepath: str) -> int:
    """
    Count the number of lines in a file.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except IOError:
        return 0


def register_language_extractor(
    extensions: Union[str, list[str]],
    extractor_factory: Optional[Callable[[], Optional[Any]]] = None,
) -> Optional[Callable[[Callable[[], Optional[Any]]], Callable[[], Optional[Any]]]]:
    """
    Register a symbol extractor for one or more file extensions.

    Can be used as a decorator or as a regular function.

    Args:
        extensions: List of file extensions (e.g., ['.py', '.pyw']) or single extension string.
                   If used as decorator, this is the first argument.
        extractor_factory: A callable that returns an extractor instance or None if unavailable.
                          The extractor must have an extract_symbols(file_path: str, content: str) method
                          that returns a list of Symbol objects.
                          If used as decorator, this is the decorated function.

    Examples:
        # As decorator:
        @register_language_extractor(['.py', '.pyw'])
        def create_python_extractor():
            from jarvis.jarvis_code_agent.code_analyzer.languages.python_language import PythonSymbolExtractor
            return PythonSymbolExtractor()

        # As regular function:
        def create_java_extractor():
            # ... create extractor ...
            return JavaExtractor()

        register_language_extractor('.java', create_java_extractor)
    """
    # Support both decorator and function call syntax
    if extractor_factory is None:
        # Used as decorator: @register_language_extractor(['.ext'])
        def decorator(func: Callable[[], Optional[Any]]) -> Callable[[], Optional[Any]]:
            if isinstance(extensions, str):
                exts = [extensions]
            else:
                exts = extensions

            for ext in exts:
                ext_lower = ext.lower()
                if not ext_lower.startswith("."):
                    ext_lower = "." + ext_lower
                _LANGUAGE_EXTRACTORS[ext_lower] = func

            return func

        return decorator
    else:
        # Used as regular function: register_language_extractor(['.ext'], factory)
        if isinstance(extensions, str):
            extensions = [extensions]

        for ext in extensions:
            ext_lower = ext.lower()
            if not ext_lower.startswith("."):
                ext_lower = "." + ext_lower
            _LANGUAGE_EXTRACTORS[ext_lower] = extractor_factory
        return None


def _get_symbol_extractor(filepath: str) -> Optional[Any]:
    """Get appropriate symbol extractor for the file based on extension"""
    ext = os.path.splitext(filepath)[1].lower()

    # Check registered extractors
    if ext in _LANGUAGE_EXTRACTORS:
        try:
            return _LANGUAGE_EXTRACTORS[ext]()
        except Exception:
            return None

    return None


# Initialize built-in extractors on module load
# Import language_extractors module to trigger automatic registration
try:
    import jarvis.jarvis_agent.language_extractors  # noqa: F401
except (ImportError, Exception):
    pass


def extract_symbols_from_file(filepath: str) -> list[dict[str, Any]]:
    """Extract symbols from a file using tree-sitter or AST"""
    extractor = _get_symbol_extractor(filepath)
    if not extractor:
        return []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        symbols = extractor.extract_symbols(filepath, content)

        # Convert Symbol objects to dict format
        result = []
        for symbol in symbols:
            result.append(
                {
                    "name": symbol.name,
                    "type": symbol.kind,
                    "line": symbol.line_start,
                    "signature": symbol.signature or f"{symbol.kind} {symbol.name}",
                }
            )

        return result
    except Exception:
        return []


def format_symbols_output(filepath: str, symbols: list[dict[str, Any]]) -> str:
    """Format symbols list as output string"""
    if not symbols:
        return ""

    # Group symbols by type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        symbol_type = symbol["type"]
        if symbol_type not in by_type:
            by_type[symbol_type] = []
        by_type[symbol_type].append(symbol)

    # Sort symbols within each type by line number
    for symbol_type in by_type:
        by_type[symbol_type].sort(key=lambda x: x["line"])

    output_lines = [f"\n📋 文件符号: {filepath}"]
    output_lines.append("─" * 60)

    # Type names in Chinese
    type_names = {
        "function": "函数",
        "async_function": "异步函数",
        "class": "类",
        "struct": "结构体",
        "enum": "枚举",
        "interface": "接口",
        "trait": "特征",
        "variable": "变量",
        "constant": "常量",
    }

    for symbol_type, type_symbols in sorted(by_type.items()):
        type_name = type_names.get(symbol_type, symbol_type)
        output_lines.append(f"\n{type_name} ({len(type_symbols)} 个):")
        for symbol in type_symbols:
            line_info = f"  行 {symbol['line']:4d}: {symbol['name']}"
            if "signature" in symbol and symbol["signature"]:
                sig = symbol["signature"].strip()
                if len(sig) > 50:
                    sig = sig[:47] + "..."
                line_info += f" - {sig}"
            output_lines.append(line_info)

    output_lines.append("─" * 60)
    output_lines.append("")

    return "\n".join(output_lines)


def _parse_quoted_reference(ref: str) -> Dict[str, Any]:
    """
    解析单引号内的引用，支持以下格式：
    - 'file.py' - 完整文件引用（提取符号）
    - 'file.py:100-200' - 行号范围引用
    - 'file.py:summary' - 摘要模式（只显示符号信息）
    - 'folder/' - 目录引用

    Args:
        ref: 引用字符串，例如 "file.py:100-200"

    Returns:
        Dict包含:
            - filepath: 文件路径
            - start_line: 起始行号（可选）
            - end_line: 结束行号（可选）
            - mode: 'symbols', 'range', 'summary', 'directory'
    """
    ref = ref.strip()

    # 检查是否是目录引用（以 / 结尾）
    if ref.endswith("/") or (os.path.exists(ref) and os.path.isdir(ref)):
        return {
            "filepath": ref.rstrip("/"),
            "mode": "directory",
        }

    # 检查是否有行号范围或摘要模式
    if ":" in ref:
        filepath, spec = ref.split(":", 1)
        filepath = filepath.strip()

        # 检查是否是摘要模式
        if spec.strip().lower() == "summary":
            return {
                "filepath": filepath,
                "mode": "summary",
            }

        # 解析行号范围
        if "-" in spec:
            try:
                start_str, end_str = spec.split("-", 1)
                start_line = int(start_str.strip())
                end_line = int(end_str.strip())
                return {
                    "filepath": filepath,
                    "start_line": start_line,
                    "end_line": end_line,
                    "mode": "range",
                }
            except ValueError:
                pass

    # 默认符号提取模式（原有功能）
    return {
        "filepath": ref,
        "mode": "symbols",
    }


def _get_max_token_limit(agent: Optional[Any] = None) -> int:
    """获取基于剩余token数量的token限制"""
    try:
        # 优先使用剩余token数量
        if agent and hasattr(agent, "model"):
            try:
                remaining_tokens = agent.model.get_remaining_token_count()
                # 使用剩余token的2/3或64k的最小值
                limit_tokens = calculate_token_limit(remaining_tokens)
                if limit_tokens > 0:
                    return limit_tokens
            except Exception:
                pass

        # 回退方案：使用输入窗口的1/2
        max_input_tokens = get_max_input_token_count()
        return int(max_input_tokens * 0.5)
    except Exception:
        # 默认值
        return 20000


def _read_file_content(
    filepath: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    agent: Optional[Any] = None,
) -> Tuple[str, bool, str]:
    """
    读取文件内容，支持行号范围

    Args:
        filepath: 文件路径
        start_line: 起始行号（可选）
        end_line: 结束行号（可选）
        agent: Agent实例，用于获取token限制

    Returns:
        Tuple[content, success, error_msg]
    """
    try:
        expanded_path = os.path.expanduser(filepath)
        abs_path = os.path.abspath(expanded_path)

        # 文件存在性检查
        if not os.path.exists(abs_path):
            return "", False, f"文件不存在: {abs_path}"

        # 文件大小限制检查（10MB）
        if os.path.getsize(abs_path) > 10 * 1024 * 1024:
            return (
                "",
                False,
                f"文件过大 (>10MB): {abs_path}，请使用行号范围引用（如 '{filepath}:100-200'）或摘要模式（如 '{filepath}:summary'）",
            )

        # 读取文件内容
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        total_lines = len(lines)

        # 处理空文件
        if total_lines == 0:
            return f"\n📄 文件: {abs_path}\n文件为空 (0行)\n", True, ""

        # 处理行号范围
        if start_line is not None and end_line is not None:
            # 规范化行号
            start_line = max(1, min(start_line, total_lines))
            end_line = max(1, min(end_line, total_lines))
            if start_line > end_line:
                start_line, end_line = end_line, start_line

            selected_lines = lines[start_line - 1 : end_line]
            content = "".join(selected_lines)

            # 检查token限制
            content_tokens = get_context_token_count(content)
            max_tokens = _get_max_token_limit(agent)

            if content_tokens > max_tokens:
                # 自动截断
                safe_ratio = max_tokens / content_tokens
                safe_lines = max(1, int(len(selected_lines) * safe_ratio * 0.9))
                safe_end = start_line + safe_lines - 1
                truncated_lines = lines[start_line - 1 : safe_end]
                truncated_content = "".join(truncated_lines)

                warning = (
                    f"\n⚠️ 警告: 内容超出token限制，仅显示前 {safe_lines} 行 "
                    f"(请求范围: {start_line}-{end_line}, 共 {end_line - start_line + 1} 行)\n"
                    f"💡 如需继续读取，请使用: '{filepath}:{safe_end + 1}-{end_line}'\n"
                )
                return (
                    f"\n📄 文件: {abs_path} (行 {start_line}-{safe_end})\n"
                    f"{warning}\n"
                    f"{truncated_content}\n",
                    True,
                    "",
                )

            # 为每行添加行号
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start_line):
                line_number_str = f"{i:4d}"
                line_content = line.rstrip("\n\r")
                numbered_lines.append(f"{line_number_str}:{line_content}")

            numbered_content = "\n".join(numbered_lines)

            return (
                f"\n📄 文件: {abs_path} (行 {start_line}-{end_line})\n"
                f"{'=' * 80}\n"
                f"{numbered_content}\n"
                f"{'=' * 80}\n",
                True,
                "",
            )
        else:
            # 完整文件
            content = "".join(lines)

            # 检查token限制
            content_tokens = get_context_token_count(content)
            max_tokens = _get_max_token_limit(agent)

            if content_tokens > max_tokens:
                return (
                    "",
                    False,
                    f"文件内容过大 ({content_tokens} tokens > {max_tokens} tokens): {abs_path}，"
                    f"请使用行号范围引用（如 '{filepath}:1-100'）或摘要模式（如 '{filepath}:summary'）",
                )

            # 为每行添加行号
            numbered_lines = []
            for i, line in enumerate(lines, start=1):
                line_number_str = f"{i:4d}"
                line_content = line.rstrip("\n\r")
                numbered_lines.append(f"{line_number_str}:{line_content}")

            numbered_content = "\n".join(numbered_lines)

            return (
                f"\n📄 文件: {abs_path}\n"
                f"📊 总行数: {total_lines}\n"
                f"{'=' * 80}\n"
                f"{numbered_content}\n"
                f"{'=' * 80}\n",
                True,
                "",
            )

    except Exception as e:
        return "", False, f"读取文件失败: {str(e)}"


def _format_summary_output(filepath: str, symbols: list[dict[str, Any]]) -> str:
    """格式化文件摘要输出"""
    output_lines = [f"\n📋 文件摘要: {filepath}"]

    if symbols:
        output_lines.append(format_symbols_output(filepath, symbols))
    else:
        # 如果没有符号，至少显示文件基本信息
        try:
            line_count = count_lines(filepath)
            file_size = os.path.getsize(filepath)
            output_lines.append(f"📊 文件信息:")
            output_lines.append(f"   - 总行数: {line_count}")
            output_lines.append(f"   - 文件大小: {file_size / 1024:.2f} KB")
            output_lines.append(f"   - 无法提取符号信息（可能不是支持的代码文件）")
        except Exception:
            pass

    return "\n".join(output_lines) + "\n"


def _format_directory_output(dirpath: str) -> str:
    """格式化目录引用输出"""
    try:
        abs_dir = os.path.abspath(os.path.expanduser(dirpath))
        if not os.path.isdir(abs_dir):
            return f"\n⚠️ 目录不存在: {abs_dir}\n"

        output_lines = [f"\n📁 目录: {abs_dir}"]
        output_lines.append("─" * 60)

        # 列出文件
        files = []
        dirs = []
        for item in sorted(os.listdir(abs_dir)):
            item_path = os.path.join(abs_dir, item)
            if os.path.isfile(item_path) and is_text_file(item_path):
                files.append(item)
            elif os.path.isdir(item_path):
                dirs.append(item)

        if dirs:
            output_lines.append(f"\n目录 ({len(dirs)} 个):")
            for d in dirs[:20]:  # 限制显示数量
                output_lines.append(f"  📁 {d}/")
            if len(dirs) > 20:
                output_lines.append(f"  ... 还有 {len(dirs) - 20} 个目录")

        if files:
            output_lines.append(f"\n文件 ({len(files)} 个):")
            for f in files[:30]:  # 限制显示数量
                try:
                    line_count = count_lines(os.path.join(abs_dir, f))
                    output_lines.append(f"  📄 {f} ({line_count} 行)")
                except Exception:
                    output_lines.append(f"  📄 {f}")
            if len(files) > 30:
                output_lines.append(f"  ... 还有 {len(files) - 30} 个文件")

        output_lines.append("─" * 60)
        output_lines.append("")

        return "\n".join(output_lines)
    except Exception as e:
        return f"\n⚠️ 读取目录失败: {str(e)}\n"


def file_context_handler(user_input: str, agent_: Any) -> Tuple[str, bool]:
    """
    处理用户输入中的文件/目录引用，支持以下语法（使用单引号）：
    - 'filename' - 完整文件引用（提取符号，原有功能）
    - 'file.py:100-200' - 行号范围引用（读取指定行范围）
    - 'file.py:summary' - 摘要模式（只显示符号信息）
    - 'folder/' - 目录引用（列出目录内容）

    Args:
        user_input: The user's input string.
        agent_: The agent instance.

    Returns:
        A tuple containing the modified user input and a boolean indicating if
        further processing should be skipped.
    """
    # Regex to find paths in single quotes
    raw_paths = re.findall(r"'([^']+)'", user_input)

    if not raw_paths:
        return user_input, False

    added_context = ""

    for raw_path in raw_paths:
        parsed = _parse_quoted_reference(raw_path)

        if parsed["mode"] == "directory":
            # 目录引用
            dir_output = _format_directory_output(parsed["filepath"])
            added_context += dir_output
        elif parsed["mode"] == "summary":
            # 摘要模式
            filepath = parsed["filepath"]
            abs_path = os.path.abspath(os.path.expanduser(filepath))

            if os.path.isfile(abs_path) and is_text_file(abs_path):
                # 检查文件大小
                if os.path.getsize(abs_path) > 10 * 1024 * 1024:
                    added_context += (
                        f"\n⚠️ 文件过大 (>10MB): {abs_path}，无法生成摘要\n"
                    )
                else:
                    symbols = extract_symbols_from_file(abs_path)
                    added_context += _format_summary_output(abs_path, symbols)
            else:
                added_context += f"\n⚠️ 文件不存在或不是文本文件: {filepath}\n"
        elif parsed["mode"] == "range":
            # 行号范围引用
            filepath = parsed["filepath"]
            start_line = parsed.get("start_line")
            end_line = parsed.get("end_line")
            content, success, error_msg = _read_file_content(
                filepath, start_line, end_line, agent_
            )
            if success:
                added_context += content
            else:
                added_context += f"\n⚠️ {error_msg}\n"
        else:
            # 符号提取模式（原有功能）
            filepath = parsed["filepath"]
            abs_path = os.path.abspath(os.path.expanduser(filepath))

            if os.path.isfile(abs_path) and is_text_file(abs_path):
                # Extract symbols from the file (原有功能)
                symbols = extract_symbols_from_file(abs_path)
                if symbols:
                    added_context += format_symbols_output(abs_path, symbols)

    if added_context:
        user_input = user_input.strip() + added_context

    return user_input, False


# ============================================================================
# 如何添加新语言支持
# ============================================================================
#
# 推荐方式：在 language_extractors/ 目录下创建新文件
#
# 1. 创建新文件：jarvis_agent/language_extractors/java_extractor.py
#
#    # -*- coding: utf-8 -*-
#    """Java language symbol extractor."""
#
#    from typing import Optional, Any, List
#    from jarvis.jarvis_agent.file_context_handler import register_language_extractor
#    from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol
#
#    def create_java_extractor() -> Optional[Any]:
#        try:
#            from tree_sitter import Language, Parser
#            import tree_sitter_java
#
#            JAVA_LANGUAGE = tree_sitter_java.language()
#            JAVA_SYMBOL_QUERY = """
#            (method_declaration
#              name: (identifier) @method.name)
#
#            (class_declaration
#              name: (identifier) @class.name)
#            """
#
#            class JavaSymbolExtractor:
#                def __init__(self):
#                    self.language = JAVA_LANGUAGE
#                    self.parser = Parser()
#                    self.parser.set_language(self.language)
#                    self.symbol_query = JAVA_SYMBOL_QUERY
#
#                def extract_symbols(self, file_path: str, content: str) -> List[Any]:
#                    try:
#                        tree = self.parser.parse(bytes(content, "utf8"))
#                        query = self.language.query(self.symbol_query)
#                        captures = query.captures(tree.root_node)
#
#                        symbols = []
#                        for node, name in captures:
#                            kind_map = {
#                                "method.name": "method",
#                                "class.name": "class",
#                            }
#                            symbol_kind = kind_map.get(name)
#                            if symbol_kind:
#                                symbols.append(Symbol(
#                                    name=node.text.decode('utf8'),
#                                    kind=symbol_kind,
#                                    file_path=file_path,
#                                    line_start=node.start_point[0] + 1,
#                                    line_end=node.end_point[0] + 1,
#                                ))
#                        return symbols
#                    except Exception:
#                        return []
#
#            return JavaSymbolExtractor()
#        except (ImportError, Exception):
#            return None
#
#    def register_java_extractor() -> None:
#        register_language_extractor(['.java', '.jav'], create_java_extractor)
#
#
# 2. 在 language_extractors/__init__.py 中添加导入和注册：
#
#    try:
#        from .java_extractor import register_java_extractor
#        register_java_extractor()
#    except (ImportError, Exception):
#        pass
#
#
# 方法2: 在运行时动态注册（不推荐，但可用）
#
# from jarvis.jarvis_agent.file_context_handler import register_language_extractor
#
# def create_ruby_extractor():
#     # ... 实现提取器 ...
#     return RubyExtractor()
#
# register_language_extractor('.rb', create_ruby_extractor)
#
# ============================================================================
