import os
import time
import hashlib
from pathlib import Path
from typing import List, Any, Callable
from jarvis.jarvis_utils.config import INPUT_WINDOW_REVERSE_SIZE, get_max_input_token_count, get_data_dir
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
def init_env() -> None:
    """初始化环境变量从jarvis_data/env文件

    功能：
    1. 创建不存在的jarvis_data目录
    2. 加载环境变量到os.environ
    3. 处理文件读取异常
    """
    jarvis_dir = Path(get_data_dir())
    env_file = jarvis_dir / "env"

    # 检查jarvis_data目录是否存在
    if not jarvis_dir.exists():
        jarvis_dir.mkdir(parents=True)
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith(("#", ";")):
                        try:
                            key, value = line.split("=", 1)
                            os.environ[key.strip()] = value.strip().strip("'").strip('"')
                        except ValueError:
                            continue
        except Exception as e:
            PrettyOutput.print(f"警告: 读取 {env_file} 失败: {e}", OutputType.WARNING)
def while_success(func: Callable[[], Any], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到成功

    参数：
    func -- 要执行的函数
    sleep_time -- 每次失败后的等待时间（秒）

    返回：
    函数执行结果
    """
    while True:
        try:
            return func()
        except Exception as e:
            PrettyOutput.print(f"执行失败: {str(e)}, 等待 {sleep_time}s...", OutputType.ERROR)
            time.sleep(sleep_time)
            continue
def while_true(func: Callable[[], bool], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到返回True"""
    while True:
        ret = func()
        if ret:
            break
        PrettyOutput.print(f"执行失败, 等待 {sleep_time}s...", OutputType.WARNING)
        time.sleep(sleep_time)
    return ret
def get_file_md5(filepath: str)->str:
    """计算文件内容的MD5哈希值

    参数:
        filepath: 要计算哈希的文件路径

    返回:
        str: 文件内容的MD5哈希值
    """
    return hashlib.md5(open(filepath, "rb").read(100*1024*1024)).hexdigest()
def user_confirm(tip: str, default: bool = True) -> bool:
    """提示用户确认是/否问题

    参数:
        tip: 显示给用户的消息
        default: 用户直接回车时的默认响应

    返回:
        bool: 用户确认返回True，否则返回False
    """
    suffix = "[Y/n]" if default else "[y/N]"
    ret = get_single_line_input(f"{tip} {suffix}: ")
    return default if ret == "" else ret.lower() == "y"

def get_file_line_count(filename: str) -> int:
    """计算文件中的行数

    参数:
        filename: 要计算行数的文件路径

    返回:
        int: 文件中的行数，如果文件无法读取则返回0
    """
    try:
        return len(open(filename, "r", encoding="utf-8", errors="ignore").readlines())
    except Exception as e:
        return 0


def is_long_context(files: List[str]) -> bool:
    """检查文件列表是否属于长上下文

    判断标准：
    当总token数超过最大上下文长度的80%时视为长上下文

    参数：
    files -- 要检查的文件路径列表

    返回：
    布尔值表示是否属于长上下文
    """
    max_input_token_count = get_max_input_token_count()
    threshold = max_input_token_count * 0.8
    total_tokens = 0

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors="ignore") as f:
                content = f.read()
                total_tokens += get_context_token_count(content)

                if total_tokens > threshold:
                    return True
        except Exception as e:
            PrettyOutput.print(f"读取文件 {file_path} 失败: {e}", OutputType.WARNING)
            continue

    return total_tokens > threshold


def is_context_overflow(file_content: str) -> bool:
    """判断文件内容是否超出上下文限制"""
    return get_context_token_count(file_content) > get_max_input_token_count() - INPUT_WINDOW_REVERSE_SIZE