"""
Jarvis工具模块
该模块提供了Jarvis系统中使用的各种实用函数和类。
包含多种辅助函数、配置管理和常见操作。
该模块组织为以下几个子模块：
- config: 配置管理
- embedding: 文本嵌入工具
- git_utils: Git仓库操作
- input: 用户输入处理
- methodology: 方法论管理
- output: 输出格式化
- utils: 通用工具
"""
import os
import colorama
from rich.traceback import install as install_rich_traceback
# 从新模块重新导出
# 这些导入是项目功能所必需的，可能会被动态使用
# 初始化colorama以支持跨平台的彩色文本
colorama.init()
# 禁用tokenizers并行以避免多进程问题
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# 安装rich traceback处理器以获得更好的错误信息
install_rich_traceback()

