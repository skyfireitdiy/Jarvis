# -*- coding: utf-8 -*-
"""LSP 语义查询工具。

用途：
- 为 CodeAgent 提供基于语言服务器的语义能力（定义/引用/实现/诊断/修复建议）；
- 复用 jarvis_lsp 已有的守护进程客户端，不重复实现 LSP 协议。

设计要点：
- 单工具 + action 枚举分派，避免为每个 LSP 方法注册一个工具污染工具列表；
- 参数面向 LLM 友好：优先使用符号名（symbol_name），而非精确行列号；
- 语言与项目根自动推断，省略时按文件扩展名与所在目录推导；
- 统一返回 {"success": bool, "stdout": str, "stderr": str}；
- 任何异常均降级为 success=False，不中断 Agent。

参数：
- action (str): 查询类型，见 parameters 中的枚举
- file_path (str): 目标文件路径（相对或绝对）
- symbol_name (str): 符号名（find_*/code_action 使用）
- query (str): workspace_symbols 的搜索词
- line / column (int): 仅 hover 需要（1-based，column 默认 0）
- language (str): 语言名，省略时按扩展名推断
- project_path (str): 项目根目录，省略时取文件所在目录

返回：
- success (bool)
- stdout (str): JSON 文本
- stderr (str)
"""

import asyncio
import dataclasses
import json
import os
import threading
from typing import Any, Dict, List, Optional

from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_lsp.daemon_client import LSPDaemonClient
from jarvis.jarvis_utils.config import save_exception
from jarvis.jarvis_utils.output import PrettyOutput


def _run_async(coro: Any) -> Any:
    """在同步上下文中执行协程，兼容当前线程已有事件循环的场景。

    - 当前线程无运行中的事件循环：直接用 asyncio.run；
    - 当前线程已有运行中的事件循环（如 Web 网关内）：另起线程执行，
      避免 "RuntimeError: This event loop is already running"。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Dict[str, Any] = {}

    def _worker() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001 - 需原样回传异常
            result["error"] = e

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]
    return result.get("value")


def _to_jsonable(obj: Any) -> Any:
    """把 dataclass / 列表 / 元组等转换为可 JSON 序列化的结构。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


class lsp:
    """LSP 语义查询工具（定义/引用/实现/诊断/修复建议）。"""

    name = "lsp"
    description = (
        "通过语言服务器（LSP）做代码语义查询，比文本搜索更准确。"
        "action 可选值：document_symbols（列出文件符号）、"
        "find_definition（按符号名查定义）、find_references（按符号名查引用）、"
        "find_implementation（按符号名查实现）、find_type_definition（按符号名查类型定义）、"
        "find_callers（谁调用了该符号）、find_callees（该符号调用了谁）、"
        "hover（类型/文档信息，需 line）、diagnostic（错误与警告）、"
        "code_action（按符号名获取修复建议）、workspace_symbols（全工作区搜索符号，需 query）。"
        "优先使用符号名（symbol_name）而非行列号；纯文本搜索请改用 rg/grep。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "document_symbols",
                    "find_definition",
                    "find_references",
                    "find_implementation",
                    "find_type_definition",
                    "find_callers",
                    "find_callees",
                    "hover",
                    "diagnostic",
                    "code_action",
                    "workspace_symbols",
                ],
                "description": "要执行的 LSP 查询类型",
            },
            "file_path": {
                "type": "string",
                "description": "目标文件路径（相对或绝对），除 workspace_symbols 外均必填",
            },
            "symbol_name": {
                "type": "string",
                "description": "符号名（find_*/code_action 使用，推荐优先于行列号）",
            },
            "query": {
                "type": "string",
                "description": "workspace_symbols 的符号搜索词",
            },
            "line": {
                "type": "number",
                "description": "行号（1-based，仅 hover 需要）",
            },
            "column": {
                "type": "number",
                "description": "列号（1-based，仅 hover 需要，默认 1）",
            },
            "language": {
                "type": "string",
                "description": "语言名（如 python/go/rust），省略时按文件扩展名自动推断",
            },
            "project_path": {
                "type": "string",
                "description": "项目根目录，省略时取 file_path 所在目录",
            },
        },
        "required": ["action"],
    }

    @staticmethod
    def check() -> bool:
        """工具可用性检查：按需自动拉起守护进程，始终可用。"""
        return True

    def _fail(self, message: str) -> Dict[str, Any]:
        return {"success": False, "stdout": "", "stderr": message}

    @staticmethod
    def _resolve_path(path: str) -> str:
        return os.path.abspath(os.path.expanduser(path))

    def _resolve_language(
        self, reader: LSPConfigReader, language: Optional[str], file_path: Optional[str]
    ) -> Optional[str]:
        """确定语言：显式指定优先，否则按文件扩展名推断。"""
        if language and str(language).strip():
            return str(language).strip()
        if file_path:
            return reader.detect_language(file_path)
        return None

    def _supported_languages(self, reader: LSPConfigReader) -> List[str]:
        try:
            config = reader.load_config()
            return sorted(config.languages.keys())
        except Exception as e:  # noqa: BLE001
            save_exception(
                e, module="jarvis_tools.lsp", function="_supported_languages"
            )
            return []

    def _install_hint(self, reader: LSPConfigReader, language: str) -> str:
        try:
            lang_config = reader.get_language_config(language)
            if lang_config and lang_config.install_hint:
                return f" 安装提示: {lang_config.install_hint}"
        except Exception as e:  # noqa: BLE001
            save_exception(e, module="jarvis_tools.lsp", function="_install_hint")
        return ""

    def _dispatch(
        self,
        client: LSPDaemonClient,
        action: str,
        language: str,
        project_path: str,
        file_path: Optional[str],
        symbol_name: Optional[str],
        query: Optional[str],
        line: Optional[int],
        column: Optional[int],
    ) -> Any:
        """按 action 分派到对应的 LSPDaemonClient 方法（返回协程）。"""
        if action == "document_symbols":
            return client.document_symbol(language, project_path, file_path or "")
        if action == "find_definition":
            return client.definition_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "find_references":
            return client.references_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "find_implementation":
            return client.implementation_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "find_type_definition":
            return client.type_definition_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "find_callers":
            return client.incoming_calls_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "find_callees":
            return client.outgoing_calls_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "hover":
            # LSP 协议与 client 使用 0-based 行列；工具对外暴露 1-based 行号，此处转换
            # （与 cli.py 的 hover 命令保持一致）
            line_1based = int(line) if line is not None else 1
            column_1based = int(column) if column is not None else 1
            return client.hover(
                language,
                project_path,
                file_path or "",
                max(line_1based - 1, 0),
                max(column_1based - 1, 0),
            )
        if action == "diagnostic":
            return client.diagnostic(language, project_path, file_path or "")
        if action == "code_action":
            return client.code_action_by_name(
                language, project_path, file_path or "", symbol_name or ""
            )
        if action == "workspace_symbols":
            return client.workspace_symbol(language, project_path, query or "")
        raise ValueError(f"不支持的 action: {action}")

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # v1.0 协议下 agent 会被注入到 args，忽略之
        if isinstance(args, dict):
            args = {k: v for k, v in args.items() if k != "agent"}

        try:
            action = args.get("action")
            if not isinstance(action, str) or not action.strip():
                return self._fail("缺少或无效的 action 参数")
            action = action.strip()

            file_path_arg = args.get("file_path")
            symbol_name = args.get("symbol_name")
            query = args.get("query")
            language_arg = args.get("language")
            project_path_arg = args.get("project_path")
            line = args.get("line")
            column = args.get("column")

            reader = LSPConfigReader()

            # workspace_symbols 不要求 file_path
            file_path: Optional[str] = None
            if isinstance(file_path_arg, str) and file_path_arg.strip():
                file_path = self._resolve_path(file_path_arg)

            if action != "workspace_symbols" and not file_path:
                return self._fail("缺少 file_path 参数")

            language = self._resolve_language(reader, language_arg, file_path)
            if not language:
                supported = self._supported_languages(reader)
                return self._fail(
                    "无法识别语言，请用 language 参数显式指定。"
                    f"当前支持的语言: {', '.join(supported) if supported else '（无）'}"
                )

            # project_path：显式指定优先，否则取文件所在目录（workspace_symbols 需显式指定）
            if isinstance(project_path_arg, str) and project_path_arg.strip():
                project_path = self._resolve_path(project_path_arg)
            elif file_path:
                project_path = os.path.dirname(file_path)
            else:
                project_path = os.getcwd()

            # 需要符号名的 action 做前置校验
            if action in (
                "find_definition",
                "find_references",
                "find_implementation",
                "find_type_definition",
                "find_callers",
                "find_callees",
                "code_action",
            ) and (not isinstance(symbol_name, str) or not symbol_name.strip()):
                return self._fail(f"action={action} 需要 symbol_name 参数")

            if action == "workspace_symbols" and (
                not isinstance(query, str) or not query.strip()
            ):
                return self._fail("action=workspace_symbols 需要 query 参数")

            client = LSPDaemonClient()
            coro = self._dispatch(
                client,
                action,
                language,
                project_path,
                file_path,
                symbol_name,
                query,
                line,
                column,
            )
            result = _run_async(coro)

            out_obj: Dict[str, Any] = {
                "action": action,
                "language": language,
                "project_path": project_path,
                "file_path": file_path,
                "result": _to_jsonable(result),
            }
            stdout = json.dumps(out_obj, ensure_ascii=False, indent=2)
            return {"success": True, "stdout": stdout, "stderr": ""}

        except Exception as e:  # noqa: BLE001 - 任何异常均降级
            save_exception(e, module="jarvis_tools.lsp", function="execute")
            message = str(e)
            hint = ""
            try:
                lang = locals().get("language")
                if lang:
                    hint = self._install_hint(LSPConfigReader(), lang)
            except Exception as inner:  # noqa: BLE001
                save_exception(inner, module="jarvis_tools.lsp", function="execute")
            PrettyOutput.auto_print(f"❌ LSP 查询失败: {message}")
            return self._fail(f"LSP 查询失败: {message}{hint}")
