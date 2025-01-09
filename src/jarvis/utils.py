from pathlib import Path
import sys
import time
from typing import Dict, Optional
from enum import Enum
from datetime import datetime
import colorama
from colorama import Fore, Style
import os

# 初始化colorama
colorama.init()

class OutputType(Enum):
    SYSTEM = "system"      # AI助手消息
    CODE = "code"         # 代码相关
    RESULT = "result"     # 工具执行结果
    ERROR = "error"       # 错误信息
    INFO = "info"         # 系统提示
    PLANNING = "planning" # 任务规划
    PROGRESS = "progress" # 执行进度
    SUCCESS = "success"   # 成功信息
    WARNING = "warning"   # 警告信息
    DEBUG = "debug"       # 调试信息
    USER = "user"         # 用户输入
    TOOL = "tool"         # 工具调用

class PrettyOutput:
    """美化输出类"""
    
    # 颜色方案 - 只使用前景色
    COLORS = {
        OutputType.SYSTEM: Fore.CYAN,      # 青色 - AI助手
        OutputType.CODE: Fore.GREEN,       # 绿色 - 代码
        OutputType.RESULT: Fore.BLUE,      # 蓝色 - 结果
        OutputType.ERROR: Fore.RED,        # 红色 - 错误
        OutputType.INFO: Fore.YELLOW,      # 黄色 - 提示
        OutputType.PLANNING: Fore.MAGENTA, # 紫色 - 规划
        OutputType.PROGRESS: Fore.WHITE,   # 白色 - 进度
        OutputType.SUCCESS: Fore.GREEN,    # 绿色 - 成功
        OutputType.WARNING: Fore.YELLOW,   # 黄色 - 警告
        OutputType.DEBUG: Fore.BLUE,       # 蓝色 - 调试
        OutputType.USER: Fore.GREEN,       # 绿色 - 用户
        OutputType.TOOL: Fore.YELLOW,      # 黄色 - 工具
    }
    
    # 图标方案
    ICONS = {
        OutputType.SYSTEM: "🤖",    # 机器人 - AI助手
        OutputType.CODE: "📝",      # 记事本 - 代码
        OutputType.RESULT: "✨",    # 闪光 - 结果
        OutputType.ERROR: "❌",     # 错误 - 错误
        OutputType.INFO: "ℹ️",      # 信息 - 提示
        OutputType.PLANNING: "📋",  # 剪贴板 - 规划
        OutputType.PROGRESS: "⏳",  # 沙漏 - 进度
        OutputType.SUCCESS: "✅",   # 勾选 - 成功
        OutputType.WARNING: "⚠️",   # 警告 - 警告
        OutputType.DEBUG: "🔍",     # 放大镜 - 调试
        OutputType.USER: "👤",      # 用户 - 用户
        OutputType.TOOL: "🔧",      # 扳手 - 工具
    }
    
    # 前缀方案
    PREFIXES = {
        OutputType.SYSTEM: "Assistant",
        OutputType.CODE: "Code",
        OutputType.RESULT: "Result",
        OutputType.ERROR: "Error",
        OutputType.INFO: "Info",
        OutputType.PLANNING: "Plan",
        OutputType.PROGRESS: "Progress",
        OutputType.SUCCESS: "Success",
        OutputType.WARNING: "Warning",
        OutputType.DEBUG: "Debug",
        OutputType.USER: "User",
        OutputType.TOOL: "Tool",
    }

    @staticmethod
    def format(text: str, output_type: OutputType, timestamp: bool = True) -> str:
        """格式化输出文本"""
        color = PrettyOutput.COLORS.get(output_type, "")
        icon = PrettyOutput.ICONS.get(output_type, "")
        prefix = PrettyOutput.PREFIXES.get(output_type, "")
        
        # 添加时间戳 - 使用白色
        time_str = f"{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}]{Style.RESET_ALL} " if timestamp else ""
        
        # 格式化输出
        formatted_text = f"{time_str}{color}{icon} {prefix}: {text}{Style.RESET_ALL}"
        
        return formatted_text

    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True):
        """打印格式化的输出"""
        print(PrettyOutput.format(text, output_type, timestamp))

    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """打印带分隔线的段落标题"""
        width = 60
        color = PrettyOutput.COLORS.get(output_type, "")
        print(f"\n{color}" + "=" * width + f"{Style.RESET_ALL}")
        PrettyOutput.print(title.center(width - 10), output_type, timestamp=False)
        print(f"{color}" + "=" * width + f"{Style.RESET_ALL}\n")

    @staticmethod
    def print_stream(text: str, output_type: OutputType):
        """打印流式输出，不换行"""
        color = PrettyOutput.COLORS.get(output_type, "")
        sys.stdout.write(f"{color}{text}{Style.RESET_ALL}")
        sys.stdout.flush()

    @staticmethod
    def print_stream_end():
        """流式输出结束，打印换行"""
        sys.stdout.write("\n")
        sys.stdout.flush()

def get_multiline_input(tip: str) -> str:
    """获取多行输入"""
    PrettyOutput.print(tip + "\n", OutputType.INFO)
    lines = []
    
    while True:
        try:
            prompt = "... " if lines else ">>> "
            sys.stdout.write(f"{Fore.GREEN}{prompt}{Style.RESET_ALL}")
            sys.stdout.flush()
            
            line = input().strip()
            if not line:
                if not lines:  # 如果是第一行就输入空行
                    return ""
                break
            
            lines.append(line)
            
        except KeyboardInterrupt:
            PrettyOutput.print("\n输入已取消", OutputType.ERROR)
            return "__interrupt__"
    
    return "\n".join(lines).strip()

def load_env_from_file():
    """从~/.jarvis_env加载环境变量"""
    env_file = Path.home() / ".jarvis_env"
    
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        try:
                            key, value = line.split("=", 1)
                            os.environ[key.strip()] = value.strip().strip("'").strip('"')
                        except ValueError:
                            continue
        except Exception as e:
            PrettyOutput.print(f"Warning: Failed to read ~/.jarvis_env: {e}", OutputType.WARNING)
    
    