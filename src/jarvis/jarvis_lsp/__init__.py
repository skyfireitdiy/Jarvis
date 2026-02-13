"""jarvis_lsp - LSP 客户端工具

该模块提供命令行 LSP（Language Server Protocol）客户端功能，
支持与各种语言服务器通信并获取代码分析结果。

主要功能：
    - 配置管理：从 ~/.jarvis/config.yaml 读取 LSP 服务器配置
    - LSP 客户端：实现基础的 LSP 协议通信
    - 符号查询：列出文件中的定义、引用、符号等
    - CLI 接口：提供命令行工具 jarvis-lsp 和 jlsp

使用示例：
    >>> from jarvis.jarvis_lsp import LSPClient
    >>> client = LSPClient(command="python", args=["-m", "pylsp"])
    >>> symbols = await client.document_symbol("test.py")

命令行使用：
    $ jarvis-lsp symbols test.py
    $ jlsp symbols test.py --json
"""

__version__ = "0.1.0"

from jarvis.jarvis_lsp.config import LSPConfigReader
from jarvis.jarvis_lsp.client import LSPClient

__all__ = ["LSPConfigReader", "LSPClient", "__version__"]
