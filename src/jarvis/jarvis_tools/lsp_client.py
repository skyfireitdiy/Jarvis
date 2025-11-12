# -*- coding: utf-8 -*-
"""LSP客户端工具。

连接到Language Server Protocol服务器，获取代码补全、悬停信息、定义跳转等功能，
辅助CodeAgent进行代码分析和生成。
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


@dataclass
class LSPServerConfig:
    """LSP服务器配置。"""
    name: str
    command: List[str]
    language_ids: List[str]
    file_extensions: List[str]
    initialization_options: Optional[Dict] = None
    check_command: Optional[List[str]] = None  # 用于检测服务器是否可用的命令


# 预定义的LSP服务器配置
LSP_SERVERS = {
    "python": LSPServerConfig(
        name="pylsp",
        command=["pylsp"],
        language_ids=["python"],
        file_extensions=[".py", ".pyw", ".pyi"],
        check_command=["pylsp", "--version"],
        initialization_options={
            "pylsp": {
                "plugins": {
                    "pycodestyle": {"enabled": False},
                    "pyflakes": {"enabled": True},
                    "pylint": {"enabled": False},
                    "autopep8": {"enabled": False},
                }
            }
        }
    ),
    "typescript": LSPServerConfig(
        name="typescript-language-server",
        command=["typescript-language-server", "--stdio"],
        language_ids=["typescript", "javascript"],
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
        check_command=["typescript-language-server", "--version"],
    ),
    "javascript": LSPServerConfig(
        name="typescript-language-server",
        command=["typescript-language-server", "--stdio"],
        language_ids=["javascript"],
        file_extensions=[".js", ".jsx", ".mjs", ".cjs"],
        check_command=["typescript-language-server", "--version"],
    ),
    "c": LSPServerConfig(
        name="clangd",
        command=["clangd"],
        language_ids=["c"],
        file_extensions=[".c", ".h"],
        check_command=["clangd", "--version"],
    ),
    "cpp": LSPServerConfig(
        name="clangd",
        command=["clangd"],
        language_ids=["cpp", "c"],
        file_extensions=[".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h"],
        check_command=["clangd", "--version"],
    ),
    "rust": LSPServerConfig(
        name="rust-analyzer",
        command=["rust-analyzer"],
        language_ids=["rust"],
        file_extensions=[".rs"],
        check_command=["rust-analyzer", "--version"],
    ),
    "go": LSPServerConfig(
        name="gopls",
        command=["gopls"],
        language_ids=["go"],
        file_extensions=[".go"],
        check_command=["gopls", "version"],
    ),
    "java": LSPServerConfig(
        name="jdtls",
        command=["jdtls"],
        language_ids=["java"],
        file_extensions=[".java"],
        check_command=["jdtls", "--version"],
    ),
}


class LSPClient:
    """LSP客户端，用于与LSP服务器通信。"""
    
    def __init__(self, project_root: str, server_config: LSPServerConfig):
        """初始化LSP客户端。
        
        Args:
            project_root: 项目根目录
            server_config: LSP服务器配置
            
        Raises:
            RuntimeError: 如果LSP服务器不可用
        """
        self.project_root = os.path.abspath(project_root)
        self.server_config = server_config
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        
        # 验证LSP服务器是否可用
        if not self._check_server_available():
            raise RuntimeError(
                f"LSP服务器 {server_config.name} 不可用。"
                f"请确保已安装并配置了 {server_config.name}。"
                f"命令: {' '.join(server_config.command)}"
            )
        
        self._initialize()
    
    def _check_server_available(self) -> bool:
        """检查LSP服务器是否可用。
        
        Returns:
            bool: 如果服务器可用返回True，否则返回False
        """
        # 如果没有配置检测命令，尝试直接运行主命令
        check_cmd = self.server_config.check_command or self.server_config.command
        
        try:
            # 尝试运行检测命令
            subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            
            # 某些LSP服务器即使返回非零退出码也可能可用（如clangd --version）
            # 只要命令能执行（不是FileNotFoundError），就认为可用
            return True
            
        except FileNotFoundError:
            PrettyOutput.print(
                f"LSP服务器 {self.server_config.name} 未找到。"
                f"命令: {' '.join(check_cmd)}",
                OutputType.WARNING
            )
            return False
        except subprocess.TimeoutExpired:
            PrettyOutput.print(
                f"LSP服务器 {self.server_config.name} 检测超时。"
                f"命令: {' '.join(check_cmd)}",
                OutputType.WARNING
            )
            return False
        except Exception as e:
            PrettyOutput.print(
                f"检测LSP服务器 {self.server_config.name} 时出错: {e}",
                OutputType.WARNING
            )
            return False
    
    def _initialize(self):
        """初始化LSP连接。"""
        try:
            # 启动LSP服务器进程
            self.process = subprocess.Popen(
                self.server_config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.project_root,
                text=True,
                bufsize=0
            )
            
            # 发送初始化请求
            self._send_request("initialize", {
                "processId": os.getpid(),
                "rootPath": self.project_root,
                "rootUri": Path(self.project_root).as_uri(),
                "capabilities": {
                    "textDocument": {
                        "completion": {"completionItem": {}},
                        "hover": {},
                        "definition": {},
                        "references": {},
                        "documentSymbol": {},
                    },
                    "workspace": {}
                },
                "initializationOptions": self.server_config.initialization_options or {}
            })
            
            # 发送initialized通知
            self._send_notification("initialized", {})
            
            PrettyOutput.print(f"LSP client initialized for {self.server_config.name}", OutputType.INFO)
        except Exception as e:
            PrettyOutput.print(f"Failed to initialize LSP client: {e}", OutputType.ERROR)
            raise
    
    def _send_request(self, method: str, params: Dict) -> Optional[Dict]:
        """发送LSP请求。
        
        Args:
            method: 方法名
            params: 参数
            
        Returns:
            响应结果
        """
        if not self.process:
            return None
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        try:
            # 发送请求
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str)
            self.process.stdin.flush()
            
            # 读取响应（简化实现，实际应该使用异步或线程）
            # 这里使用超时读取
            import threading
            import queue
            
            # 使用队列在线程中读取响应
            response_queue = queue.Queue()
            
            def read_response():
                try:
                    response_line = self.process.stdout.readline()
                    if response_line:
                        response = json.loads(response_line)
                        response_queue.put(response)
                except Exception as e:
                    PrettyOutput.print(f"Error reading LSP response: {e}", OutputType.ERROR)
                    response_queue.put(None)
            
            # 启动读取线程
            read_thread = threading.Thread(target=read_response, daemon=True)
            read_thread.start()
            read_thread.join(timeout=5.0)
            
            try:
                response = response_queue.get(timeout=0.1)
                if response and "result" in response:
                    return response["result"]
            except queue.Empty:
                pass
            
            return None
        except Exception as e:
            PrettyOutput.print(f"Error sending LSP request: {e}", OutputType.ERROR)
            return None
    
    def _send_notification(self, method: str, params: Dict):
        """发送LSP通知（无响应）。
        
        Args:
            method: 方法名
            params: 参数
        """
        if not self.process:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            notification_str = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_str)
            self.process.stdin.flush()
        except Exception as e:
            PrettyOutput.print(f"Error sending LSP notification: {e}", OutputType.ERROR)
    
    def get_completion(self, file_path: str, line: int, character: int) -> List[Dict]:
        """获取代码补全。
        
        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）
            
        Returns:
            补全项列表
        """
        uri = Path(file_path).as_uri()
        result = self._send_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        })
        
        if result and "items" in result:
            return result["items"]
        return []
    
    def get_hover(self, file_path: str, line: int, character: int) -> Optional[Dict]:
        """获取悬停信息。
        
        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）
            
        Returns:
            悬停信息
        """
        uri = Path(file_path).as_uri()
        return self._send_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        })
    
    def get_definition(self, file_path: str, line: int, character: int) -> Optional[Dict]:
        """获取定义位置。
        
        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）
            
        Returns:
            定义位置
        """
        uri = Path(file_path).as_uri()
        return self._send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        })
    
    def get_references(self, file_path: str, line: int, character: int) -> List[Dict]:
        """获取引用位置。
        
        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）
            
        Returns:
            引用位置列表
        """
        uri = Path(file_path).as_uri()
        result = self._send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": False}
        })
        
        if result:
            return result
        return []
    
    def get_document_symbols(self, file_path: str) -> List[Dict]:
        """获取文档符号。
        
        Args:
            file_path: 文件路径
            
        Returns:
            符号列表
        """
        uri = Path(file_path).as_uri()
        result = self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri}
        })
        
        if result:
            return result
        return []
    
    def notify_did_open(self, file_path: str, content: str):
        """通知文档打开。
        
        Args:
            file_path: 文件路径
            content: 文件内容
        """
        uri = Path(file_path).as_uri()
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": self._detect_language(file_path),
                "version": 1,
                "text": content
            }
        })
    
    def notify_did_change(self, file_path: str, content: str):
        """通知文档变更。
        
        Args:
            file_path: 文件路径
            content: 文件内容
        """
        uri = Path(file_path).as_uri()
        self._send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 1},
            "contentChanges": [{"text": content}]
        })
    
    def _detect_language(self, file_path: str) -> str:
        """检测文件语言ID。"""
        ext = Path(file_path).suffix.lower()
        for lang_id, config in LSP_SERVERS.items():
            if ext in config.file_extensions:
                return config.language_ids[0]
        return "plaintext"
    
    def close(self):
        """关闭LSP连接。"""
        if self.process:
            try:
                self._send_notification("shutdown", {})
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                PrettyOutput.print(f"Error closing LSP client: {e}", OutputType.WARNING)
                if self.process:
                    self.process.kill()


class LSPClientTool:
    """LSP客户端工具，供CodeAgent使用。"""
    
    name = "lsp_client"
    description = """LSP客户端工具，连接到Language Server Protocol服务器获取代码信息，仅在CodeAgent模式下可用。
    
功能包括：
- 代码补全：获取当前位置的代码补全建议
- 悬停信息：获取符号的详细信息（类型、文档等）
- 定义跳转：查找符号的定义位置
- 引用查找：查找符号的所有引用位置
- 文档符号：获取文件中的所有符号（函数、类等）

这些信息可以帮助CodeAgent更好地理解代码结构，生成更准确的代码。
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["completion", "hover", "definition", "references", "document_symbols"],
                "description": "要执行的LSP操作"
            },
            "file_path": {
                "type": "string",
                "description": "文件路径（相对或绝对路径）"
            },
            "line": {
                "type": "number",
                "description": "行号（1-based，会自动转换为0-based）"
            },
            "character": {
                "type": "number",
                "description": "列号（1-based，会自动转换为0-based）"
            }
        },
        "required": ["action", "file_path"]
    }
    
    # 全局LSP客户端缓存（按项目根目录和语言）
    _clients: Dict[Tuple[str, str], LSPClient] = {}
    
    @classmethod
    def check(cls) -> bool:
        """检查工具是否可用，仅在CodeAgent模式下启用"""
        # 检查是否在CodeAgent模式下
        if os.environ.get("JARVIS_CODE_AGENT", "") != "1":
            return False
        return True
    
    def _get_or_create_client(self, project_root: str, file_path: str) -> Optional[LSPClient]:
        """获取或创建LSP客户端。
        
        Args:
            project_root: 项目根目录
            file_path: 文件路径
            
        Returns:
            LSP客户端实例
        """
        # 检测文件语言
        ext = Path(file_path).suffix.lower()
        language = None
        
        for lang, config in LSP_SERVERS.items():
            if ext in config.file_extensions:
                language = lang
                break
        
        if not language:
            return None
        
        # 检查缓存（使用类变量）
        cache_key = (project_root, language)
        if cache_key in LSPClientTool._clients:
            return LSPClientTool._clients[cache_key]
        
        # 创建新客户端
        try:
            config = LSP_SERVERS[language]
            client = LSPClient(project_root, config)
            LSPClientTool._clients[cache_key] = client
            PrettyOutput.print(f"LSP客户端创建成功: {config.name} for {language}", OutputType.INFO)
            return client
        except RuntimeError as e:
            # LSP服务器不可用（已在_check_server_available中记录日志）
            PrettyOutput.print(f"LSP服务器不可用: {e}", OutputType.ERROR)
            return None
        except Exception as e:
            PrettyOutput.print(f"Failed to create LSP client: {e}", OutputType.ERROR)
            return None
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行LSP客户端工具。
        
        Args:
            args: 工具参数
            
        Returns:
            执行结果
        """
        try:
            # 检查是否在CodeAgent模式下
            if not self.check():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "lsp_client工具仅在CodeAgent模式下可用"
                }
            
            action = args.get("action")
            file_path = args.get("file_path")
            
            if not action or not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必需参数: action 和 file_path"
                }
            
            # 获取项目根目录（从agent获取，或使用文件所在目录）
            project_root = args.get("project_root") or os.path.dirname(os.path.abspath(file_path))
            
            # 获取或创建LSP客户端
            client = self._get_or_create_client(project_root, file_path)
            if not client:
                # 检测语言以提供更详细的错误信息
                ext = Path(file_path).suffix.lower()
                language = None
                for lang, config in LSP_SERVERS.items():
                    if ext in config.file_extensions:
                        language = lang
                        break
                
                if language:
                    server_name = LSP_SERVERS[language].name
                    error_msg = (
                        f"无法为文件 {file_path} 创建LSP客户端。\n"
                        f"语言: {language}, LSP服务器: {server_name}\n"
                        f"请确保已安装 {server_name} 并配置在PATH中。"
                    )
                else:
                    error_msg = f"无法为文件 {file_path} 创建LSP客户端（不支持该语言或LSP服务器未安装）"
                
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg
                }
            
            # 确保文件已打开
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                client.notify_did_open(file_path, content)
            
            # 执行操作
            line = args.get("line", 1) - 1  # 转换为0-based
            character = args.get("character", 1) - 1  # 转换为0-based
            
            result = None
            if action == "completion":
                items = client.get_completion(file_path, line, character)
                result = {
                    "items": items[:20],  # 限制数量
                    "count": len(items)
                }
            elif action == "hover":
                result = client.get_hover(file_path, line, character)
            elif action == "definition":
                result = client.get_definition(file_path, line, character)
            elif action == "references":
                refs = client.get_references(file_path, line, character)
                result = {
                    "references": refs,
                    "count": len(refs)
                }
            elif action == "document_symbols":
                symbols = client.get_document_symbols(file_path)
                result = {
                    "symbols": symbols,
                    "count": len(symbols)
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作: {action}"
                }
            
            if result is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "LSP服务器未返回结果"
                }
            
            # 格式化输出
            output = self._format_result(action, result)
            
            return {
                "success": True,
                "stdout": output,
                "stderr": ""
            }
            
        except Exception as e:
            PrettyOutput.print(f"LSP client tool error: {e}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"LSP客户端工具执行失败: {str(e)}"
            }
    
    def _format_result(self, action: str, result: Dict) -> str:
        """格式化LSP结果。
        
        Args:
            action: 操作类型
            result: 结果数据
            
        Returns:
            格式化后的字符串
        """
        if action == "completion":
            items = result.get("items", [])
            if not items:
                return "未找到补全建议"
            
            lines = [f"找到 {result.get('count', 0)} 个补全建议：\n"]
            for item in items[:10]:  # 只显示前10个
                label = item.get("label", "")
                kind = item.get("kind", "")
                detail = item.get("detail", "")
                lines.append(f"  - {label} ({kind})")
                if detail:
                    lines.append(f"    {detail}")
            return "\n".join(lines)
        
        elif action == "hover":
            if not result:
                return "未找到悬停信息"
            
            contents = result.get("contents", {})
            if isinstance(contents, dict):
                value = contents.get("value", "")
                return f"悬停信息:\n{value}"
            elif isinstance(contents, list):
                values = [c.get("value", "") if isinstance(c, dict) else str(c) for c in contents]
                return f"悬停信息:\n" + "\n".join(values)
            else:
                return f"悬停信息:\n{contents}"
        
        elif action == "definition":
            if not result:
                return "未找到定义"
            
            if isinstance(result, list):
                result = result[0]
            
            uri = result.get("uri", "")
            range = result.get("range", {})
            start = range.get("start", {})
            line = start.get("line", 0) + 1  # 转换为1-based
            
            file_path = Path(uri).path if uri.startswith("file://") else uri
            return f"定义位置: {file_path}:{line}"
        
        elif action == "references":
            refs = result.get("references", [])
            if not refs:
                return "未找到引用"
            
            lines = [f"找到 {result.get('count', 0)} 个引用：\n"]
            for ref in refs[:10]:  # 只显示前10个
                uri = ref.get("uri", "")
                range = ref.get("range", {})
                start = range.get("start", {})
                line = start.get("line", 0) + 1
                
                file_path = Path(uri).path if uri.startswith("file://") else uri
                lines.append(f"  - {file_path}:{line}")
            return "\n".join(lines)
        
        elif action == "document_symbols":
            symbols = result.get("symbols", [])
            if not symbols:
                return "未找到符号"
            
            lines = [f"找到 {result.get('count', 0)} 个符号：\n"]
            for symbol in symbols[:20]:  # 只显示前20个
                name = symbol.get("name", "")
                kind = symbol.get("kind", "")
                range = symbol.get("range", {})
                start = range.get("start", {})
                line = start.get("line", 0) + 1
                
                lines.append(f"  - {name} ({kind}) at line {line}")
            return "\n".join(lines)
        
        return str(result)