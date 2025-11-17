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

# 延迟导入，避免循环依赖
_treesitter_available = None
_symbol_extractor_module = None

def _check_treesitter_available():
    """检查 Tree-sitter 是否可用"""
    global _treesitter_available, _symbol_extractor_module
    if _treesitter_available is None:
        try:
            from jarvis.jarvis_code_agent.code_analyzer import language_support
            _symbol_extractor_module = language_support
            _treesitter_available = True
        except ImportError:
            _treesitter_available = False
    return _treesitter_available


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
    
    def find_symbol_by_name(self, file_path: str, symbol_name: str) -> Optional[Dict]:
        """通过符号名称查找符号位置（适合大模型使用）。
        
        Args:
            file_path: 文件路径
            symbol_name: 符号名称（函数名、类名等）
            
        Returns:
            符号信息，包含位置和详细信息，如果未找到返回None
        """
        # 先获取文件中的所有符号
        symbols = self.get_document_symbols(file_path)
        if not symbols:
            return None
        
        # 精确匹配
        for symbol in symbols:
            if symbol.get("name") == symbol_name:
                return symbol
        
        # 模糊匹配（不区分大小写）
        symbol_name_lower = symbol_name.lower()
        for symbol in symbols:
            if symbol.get("name", "").lower() == symbol_name_lower:
                return symbol
        
        # 部分匹配（包含关系）
        for symbol in symbols:
            name = symbol.get("name", "").lower()
            if symbol_name_lower in name or name in symbol_name_lower:
                return symbol
        
        return None
    
    def get_symbol_info(self, file_path: str, symbol_name: str) -> Optional[Dict]:
        """获取符号的完整信息（定义、悬停、引用等，适合大模型使用）。
        
        Args:
            file_path: 文件路径
            symbol_name: 符号名称
            
        Returns:
            包含符号完整信息的字典，如果未找到返回None
        """
        # 查找符号位置
        symbol = self.find_symbol_by_name(file_path, symbol_name)
        if not symbol:
            return None
        
        # 获取符号的位置
        range_info = symbol.get("range", {})
        start = range_info.get("start", {})
        line = start.get("line", 0)
        character = start.get("character", 0)
        
        # 获取悬停信息
        hover_info = self.get_hover(file_path, line, character)
        
        # 获取定义位置
        definition = self.get_definition(file_path, line, character)
        
        # 获取引用
        references = self.get_references(file_path, line, character)
        
        return {
            "name": symbol.get("name"),
            "kind": symbol.get("kind"),
            "location": {
                "file": file_path,
                "line": line + 1,  # 转换为1-based
                "character": character + 1
            },
            "range": range_info,
            "hover": hover_info,
            "definition": definition,
            "references": references,
            "reference_count": len(references) if references else 0
        }
    
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
                # 尝试优雅关闭
                try:
                    self._send_notification("shutdown", {})
                except Exception:
                    pass  # 如果发送失败，直接终止进程
                
                # 关闭标准输入，通知服务器可以退出
                if self.process.stdin:
                    try:
                        self.process.stdin.close()
                    except Exception:
                        pass
                
                # 等待进程退出
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 超时后强制终止
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
            except Exception as e:
                PrettyOutput.print(f"Error closing LSP client: {e}", OutputType.WARNING)
                if self.process:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            finally:
                # 确保进程对象被清理
                if self.process:
                    try:
                        # 确保所有文件描述符都被关闭
                        if self.process.stdin:
                            try:
                                self.process.stdin.close()
                            except Exception:
                                pass
                        if self.process.stdout:
                            try:
                                self.process.stdout.close()
                            except Exception:
                                pass
                        if self.process.stderr:
                            try:
                                self.process.stderr.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
                self.process = None
    
    def __del__(self):
        """析构函数，确保资源被释放。"""
        self.close()
    
    def __enter__(self):
        """上下文管理器入口。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动关闭连接。"""
        self.close()
        return False


class TreeSitterFallback:
    """Tree-sitter 后备客户端，当 LSP 不可用时使用。
    
    提供类似 LSP 的接口，但使用 Tree-sitter 进行符号提取。
    """
    
    def __init__(self, project_root: str, language: str):
        """初始化 Tree-sitter 后备客户端。
        
        Args:
            project_root: 项目根目录
            language: 语言名称
        """
        self.project_root = os.path.abspath(project_root)
        self.language = language
        self._extractor = None
        self._symbols_cache: Dict[str, List[Dict]] = {}  # 文件路径 -> 符号列表
    
    def _get_extractor(self):
        """获取符号提取器（延迟加载）"""
        if self._extractor is None and _symbol_extractor_module:
            self._extractor = _symbol_extractor_module.get_symbol_extractor(self.language)
        return self._extractor
    
    def get_document_symbols(self, file_path: str) -> List[Dict]:
        """获取文档符号（使用 Tree-sitter）。
        
        Args:
            file_path: 文件路径
            
        Returns:
            符号列表
        """
        # 检查缓存
        if file_path in self._symbols_cache:
            return self._symbols_cache[file_path]
        
        extractor = self._get_extractor()
        if not extractor:
            return []
        
        try:
            # 读取文件内容
            if not os.path.exists(file_path):
                return []
            
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # 提取符号
            symbols = extractor.extract_symbols(file_path, content)
            
            # 转换为 LSP 格式
            lsp_symbols = []
            for symbol in symbols:
                lsp_symbol = {
                    "name": symbol.name,
                    "kind": self._map_kind_to_lsp(symbol.kind),
                    "range": {
                        "start": {
                            "line": symbol.line_start - 1,  # 转换为0-based
                            "character": 0
                        },
                        "end": {
                            "line": symbol.line_end - 1,  # 转换为0-based
                            "character": 0
                        }
                    },
                    "detail": symbol.signature or "",
                    "documentation": symbol.docstring or ""
                }
                lsp_symbols.append(lsp_symbol)
            
            # 缓存结果
            self._symbols_cache[file_path] = lsp_symbols
            return lsp_symbols
        except Exception as e:
            PrettyOutput.print(f"Tree-sitter 提取符号失败: {e}", OutputType.WARNING)
            return []
    
    def _map_kind_to_lsp(self, kind: str) -> int:
        """将符号类型映射到 LSP 符号类型。
        
        LSP SymbolKind 枚举值：
        1 = File, 2 = Module, 3 = Namespace, 4 = Package, 5 = Class,
        6 = Method, 7 = Property, 8 = Field, 9 = Constructor, 10 = Enum,
        11 = Interface, 12 = Function, 13 = Variable, 14 = Constant,
        15 = String, 16 = Number, 17 = Boolean, 18 = Array, 19 = Object,
        20 = Key, 21 = Null, 22 = EnumMember, 23 = Struct, 24 = Event,
        25 = Operator, 26 = TypeParameter
        """
        kind_lower = kind.lower()
        if kind_lower in ["class", "struct"]:
            return 5  # Class
        elif kind_lower in ["function", "method"]:
            return 12  # Function
        elif kind_lower == "variable":
            return 13  # Variable
        elif kind_lower == "constant":
            return 14  # Constant
        elif kind_lower == "module":
            return 2  # Module
        elif kind_lower == "namespace":
            return 3  # Namespace
        elif kind_lower == "interface":
            return 11  # Interface
        elif kind_lower == "enum":
            return 10  # Enum
        else:
            return 13  # 默认 Variable
    
    def find_symbol_by_name(self, file_path: str, symbol_name: str) -> Optional[Dict]:
        """通过符号名称查找符号位置。
        
        Args:
            file_path: 文件路径
            symbol_name: 符号名称
            
        Returns:
            符号信息，如果未找到返回None
        """
        symbols = self.get_document_symbols(file_path)
        if not symbols:
            return None
        
        # 精确匹配
        for symbol in symbols:
            if symbol.get("name") == symbol_name:
                return symbol
        
        # 模糊匹配（不区分大小写）
        symbol_name_lower = symbol_name.lower()
        for symbol in symbols:
            if symbol.get("name", "").lower() == symbol_name_lower:
                return symbol
        
        # 部分匹配
        for symbol in symbols:
            name = symbol.get("name", "").lower()
            if symbol_name_lower in name or name in symbol_name_lower:
                return symbol
        
        return None
    
    def get_symbol_info(self, file_path: str, symbol_name: str) -> Optional[Dict]:
        """获取符号的完整信息。
        
        Args:
            file_path: 文件路径
            symbol_name: 符号名称
            
        Returns:
            包含符号完整信息的字典，如果未找到返回None
        """
        symbol = self.find_symbol_by_name(file_path, symbol_name)
        if not symbol:
            return None
        
        range_info = symbol.get("range", {})
        start = range_info.get("start", {})
        
        return {
            "name": symbol.get("name"),
            "kind": symbol.get("kind"),
            "location": {
                "file": file_path,
                "line": start.get("line", 0) + 1,  # 转换为1-based
                "character": start.get("character", 0) + 1
            },
            "range": range_info,
            "hover": {
                "contents": {
                    "value": symbol.get("documentation") or symbol.get("detail") or ""
                }
            },
            "definition": {
                "uri": Path(file_path).as_uri(),
                "range": range_info
            },
            "references": [],  # Tree-sitter 不支持引用查找
            "reference_count": 0
        }
    
    def get_definition(self, file_path: str, line: int, character: int) -> Optional[Dict]:
        """获取定义位置（Tree-sitter 版本，实际上就是当前符号的位置）。
        
        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）
            
        Returns:
            定义位置
        """
        # Tree-sitter 无法精确查找定义，返回当前位置
        return {
            "uri": Path(file_path).as_uri(),
            "range": {
                "start": {"line": line, "character": character},
                "end": {"line": line, "character": character}
            }
        }
    
    def get_references(self, file_path: str, line: int, character: int) -> List[Dict]:
        """获取引用位置（Tree-sitter 不支持，返回空列表）。
        
        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）
            
        Returns:
            引用位置列表（Tree-sitter 不支持，返回空列表）
        """
        # Tree-sitter 不支持引用查找
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
        # 查找该位置的符号
        symbols = self.get_document_symbols(file_path)
        for symbol in symbols:
            range_info = symbol.get("range", {})
            start = range_info.get("start", {})
            range_info.get("end", {})
            sym_line = start.get("line", 0)
            if sym_line == line:
                return {
                    "contents": {
                        "value": symbol.get("documentation") or symbol.get("detail") or symbol.get("name", "")
                    }
                }
        return None


class LSPClientTool:
    """LSP客户端工具，供CodeAgent使用。"""
    
    name = "lsp_client"
    description = "LSP客户端工具，基于符号名称获取代码信息（定义、引用等），无需行列号。仅在CodeAgent模式下可用。"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "get_symbol_info",   # 通过符号名获取完整信息
                    "search_symbol",      # 搜索符号（模糊匹配）
                    "document_symbols",   # 获取所有符号列表
                    "definition",         # 查找定义位置
                    "references"          # 查找所有引用
                ],
                "description": "要执行的LSP操作。所有操作都基于符号名称，无需行列号。"
            },
            "file_path": {
                "type": "string",
                "description": "文件路径（相对或绝对路径）"
            },
            "symbol_name": {
                "type": "string",
                "description": "符号名称（函数名、类名、变量名等）。get_symbol_info/definition/references必需；search_symbol可选；document_symbols不需要。支持模糊匹配。"
            }
        },
        "required": ["action", "file_path"]
    }
    
    # 全局LSP客户端缓存（按项目根目录和语言）
    _clients: Dict[Tuple[str, str], LSPClient] = {}
    # Tree-sitter 后备客户端缓存
    _treesitter_clients: Dict[Tuple[str, str], TreeSitterFallback] = {}
    # 最大缓存大小，防止内存和文件句柄泄露
    _max_cache_size = 10
    
    @staticmethod
    def check() -> bool:
        """检查工具是否可用。
        
        检查CodeAgent模块是否可用，因为此工具仅在CodeAgent模式下可用。
        
        Returns:
            bool: 如果CodeAgent可用返回True，否则返回False
        """
        try:
            from jarvis.jarvis_code_agent.code_agent import CodeAgent
            return True
        except ImportError:
            return False
    
    @staticmethod
    def cleanup_all_clients():
        """清理所有缓存的LSP客户端，释放资源。"""
        # 关闭所有LSP客户端
        for client in list(LSPClientTool._clients.values()):
            try:
                client.close()
            except Exception:
                pass
        LSPClientTool._clients.clear()
        
        # Tree-sitter 客户端不需要特殊清理（没有进程）
        LSPClientTool._treesitter_clients.clear()
    
    def _get_or_create_client(self, project_root: str, file_path: str) -> Optional[Any]:
        """获取或创建LSP客户端，如果LSP不可用则使用Tree-sitter后备。
        
        Args:
            project_root: 项目根目录
            file_path: 文件路径
            
        Returns:
            LSP客户端或Tree-sitter后备客户端实例
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
        
        # 检查LSP客户端缓存
        cache_key = (project_root, language)
        if cache_key in LSPClientTool._clients:
            client = LSPClientTool._clients[cache_key]
            # 检查客户端是否仍然有效（进程是否还在运行）
            if client.process and client.process.poll() is None:
                return client
            else:
                # 进程已退出，从缓存中移除并关闭
                try:
                    client.close()
                except Exception:
                    pass
                del LSPClientTool._clients[cache_key]
        
        # 如果缓存过大，清理最旧的客户端
        if len(LSPClientTool._clients) >= LSPClientTool._max_cache_size:
            # 关闭并移除最旧的客户端（FIFO）
            oldest_key = next(iter(LSPClientTool._clients))
            oldest_client = LSPClientTool._clients.pop(oldest_key)
            try:
                oldest_client.close()
            except Exception:
                pass
        
        # 尝试创建LSP客户端
        try:
            config = LSP_SERVERS[language]
            client = LSPClient(project_root, config)
            LSPClientTool._clients[cache_key] = client
            PrettyOutput.print(f"LSP客户端创建成功: {config.name} for {language}", OutputType.INFO)
            return client
        except RuntimeError:
            # LSP服务器不可用，尝试使用Tree-sitter后备
            if _check_treesitter_available():
                # 检查Tree-sitter后备缓存
                if cache_key in LSPClientTool._treesitter_clients:
                    fallback = LSPClientTool._treesitter_clients[cache_key]
                    PrettyOutput.print(f"使用Tree-sitter后备客户端: {language}", OutputType.INFO)
                    return fallback
                
                # 检查是否有该语言的符号提取器
                if _symbol_extractor_module:
                    extractor = _symbol_extractor_module.get_symbol_extractor(language)
                    if extractor:
                        fallback = TreeSitterFallback(project_root, language)
                        LSPClientTool._treesitter_clients[cache_key] = fallback
                        PrettyOutput.print(f"创建Tree-sitter后备客户端: {language}", OutputType.INFO)
                        return fallback
                    else:
                        PrettyOutput.print(f"Tree-sitter不支持语言: {language}", OutputType.WARNING)
                        return None
                else:
                    PrettyOutput.print(f"Tree-sitter不可用，且LSP服务器 {config.name} 也不可用", OutputType.WARNING)
                    return None
            else:
                PrettyOutput.print(f"LSP服务器 {config.name} 不可用，且Tree-sitter也不可用", OutputType.WARNING)
                return None
        except Exception as e:
            PrettyOutput.print(f"Failed to create LSP client: {e}", OutputType.ERROR)
            # 尝试使用Tree-sitter后备
            if _check_treesitter_available() and _symbol_extractor_module:
                extractor = _symbol_extractor_module.get_symbol_extractor(language)
                if extractor:
                    if cache_key not in LSPClientTool._treesitter_clients:
                        fallback = TreeSitterFallback(project_root, language)
                        LSPClientTool._treesitter_clients[cache_key] = fallback
                        PrettyOutput.print(f"创建Tree-sitter后备客户端: {language}", OutputType.INFO)
                        return fallback
                    return LSPClientTool._treesitter_clients[cache_key]
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
            
            # 确保文件已打开（仅对 LSP 客户端需要）
            if isinstance(client, LSPClient) and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                client.notify_did_open(file_path, content)
            
            # 执行操作（完全基于符号名称，无需行列号）
            symbol_name = args.get("symbol_name")
            
            result = None
            if action == "get_symbol_info":
                # 通过符号名获取完整信息
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "get_symbol_info 操作需要提供 symbol_name 参数"
                    }
                result = client.get_symbol_info(file_path, symbol_name)
                if not result:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"未找到符号: {symbol_name}。请使用 document_symbols 操作查看文件中的所有符号。"
                }
            elif action == "search_symbol":
                # 搜索符号（支持模糊匹配）
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "search_symbol 操作需要提供 symbol_name 参数"
                    }
                all_symbols = client.get_document_symbols(file_path)
                symbol_name_lower = symbol_name.lower()
                matches = []
                for sym in all_symbols:
                    name = sym.get("name", "").lower()
                    if symbol_name_lower in name or name in symbol_name_lower:
                        matches.append(sym)
                result = {
                    "symbols": matches[:20],  # 限制数量
                    "count": len(matches),
                    "query": symbol_name
                }
            elif action == "document_symbols":
                # 获取所有符号
                symbols = client.get_document_symbols(file_path)
                result = {
                    "symbols": symbols,
                    "count": len(symbols)
                }
            elif action == "definition":
                # 查找定义位置（通过符号名）
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "definition 操作需要提供 symbol_name 参数"
                    }
                symbol = client.find_symbol_by_name(file_path, symbol_name)
                if not symbol:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"未找到符号: {symbol_name}。请使用 document_symbols 操作查看文件中的所有符号。"
                    }
                range_info = symbol.get("range", {})
                start = range_info.get("start", {})
                line = start.get("line", 0)
                character = start.get("character", 0)
                result = client.get_definition(file_path, line, character)
            elif action == "references":
                # 查找所有引用（通过符号名）
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "references 操作需要提供 symbol_name 参数"
                    }
                symbol = client.find_symbol_by_name(file_path, symbol_name)
                if not symbol:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"未找到符号: {symbol_name}。请使用 document_symbols 操作查看文件中的所有符号。"
                    }
                range_info = symbol.get("range", {})
                start = range_info.get("start", {})
                line = start.get("line", 0)
                character = start.get("character", 0)
                refs = client.get_references(file_path, line, character)
                result = {
                    "references": refs,
                    "count": len(refs) if refs else 0
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
        if action == "get_symbol_info":
            # 格式化符号完整信息
            if not result:
                return "未找到符号信息"
            
            lines = [f"符号: {result.get('name', '')} ({result.get('kind', '')})"]
            
            location = result.get("location", {})
            if location:
                lines.append(f"位置: {location.get('file', '')}:{location.get('line', 0)}")
            
            hover = result.get("hover", {})
            if hover:
                contents = hover.get("contents", {})
                if isinstance(contents, dict):
                    value = contents.get("value", "")
                    if value:
                        lines.append(f"信息: {value}")
                elif isinstance(contents, list):
                    values = [c.get("value", "") if isinstance(c, dict) else str(c) for c in contents]
                    if values:
                        lines.append(f"信息: {' '.join(values)}")
            
            definition = result.get("definition", {})
            if definition:
                if isinstance(definition, list):
                    definition = definition[0] if definition else {}
                uri = definition.get("uri", "")
                if uri:
                    file_path = Path(uri).path if uri.startswith("file://") else uri
                    range_info = definition.get("range", {})
                    start = range_info.get("start", {})
                    line = start.get("line", 0) + 1
                    lines.append(f"定义: {file_path}:{line}")
            
            ref_count = result.get("reference_count", 0)
            if ref_count > 0:
                lines.append(f"引用数量: {ref_count}")
            
            return "\n".join(lines)
        
        elif action == "search_symbol":
            # 格式化搜索结果
            symbols = result.get("symbols", [])
            query = result.get("query", "")
            count = result.get("count", 0)
            
            if not symbols:
                return f"未找到匹配 '{query}' 的符号"
            
            lines = [f"找到 {count} 个匹配 '{query}' 的符号：\n"]
            for symbol in symbols[:10]:  # 只显示前10个
                name = symbol.get("name", "")
                kind = symbol.get("kind", "")
                range_info = symbol.get("range", {})
                start = range_info.get("start", {})
                line = start.get("line", 0) + 1
                lines.append(f"  - {name} ({kind}) at line {line}")
            
            if count > 10:
                lines.append(f"  ... 还有 {count - 10} 个结果")
            
            return "\n".join(lines)
        
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