import sys
import time
import threading
from typing import Optional
from enum import Enum
from datetime import datetime
import colorama
from colorama import Fore, Style

# 初始化colorama
colorama.init()

class Spinner:
    """加载动画类"""
    def __init__(self, message: str = "思考中"):
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.message = message
        self.running = False
        self.spinner_thread = None

    def _spin(self):
        i = 0
        while self.running:
            sys.stdout.write(f"\r{Fore.BLUE}{self.spinner_chars[i]} {self.message}...{Style.RESET_ALL}")
            sys.stdout.flush()
            time.sleep(0.1)
            i = (i + 1) % len(self.spinner_chars)
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.spinner_thread = threading.Thread(target=self._spin)
        self.spinner_thread.start()

    def stop(self):
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()

class OutputType(Enum):
    SYSTEM = "system"
    CODE = "code"
    RESULT = "result"
    ERROR = "error"
    INFO = "info"

class PrettyOutput:
    """美化输出类"""
    @staticmethod
    def format(text: str, output_type: OutputType, timestamp: bool = True) -> str:
        # 颜色映射
        colors = {
            OutputType.SYSTEM: Fore.CYAN,
            OutputType.CODE: Fore.GREEN,
            OutputType.RESULT: Fore.BLUE,
            OutputType.ERROR: Fore.RED,
            OutputType.INFO: Fore.YELLOW
        }

        # 图标映射
        icons = {
            OutputType.SYSTEM: "🤖",
            OutputType.CODE: "📝",
            OutputType.RESULT: "✨",
            OutputType.ERROR: "❌",
            OutputType.INFO: "ℹ️"
        }

        color = colors.get(output_type, "")
        icon = icons.get(output_type, "")
        
        # 添加时间戳
        time_str = f"[{datetime.now().strftime('%H:%M:%S')}] " if timestamp else ""
        
        # 格式化输出
        formatted_text = f"{color}{time_str}{icon} {text}{Style.RESET_ALL}"
        
        return formatted_text

    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True):
        print(PrettyOutput.format(text, output_type, timestamp)) 