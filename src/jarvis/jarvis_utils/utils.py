# -*- coding: utf-8 -*-
import hashlib
import os
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any, Callable, Dict

import yaml

from jarvis import __version__
from jarvis.jarvis_utils.config import get_data_dir, get_max_big_content_size, set_global_env_data
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput



def init_env(welcome_str: str) -> None:
    """初始化环境变量从jarvis_data/env文件
    功能：
    1. 创建不存在的jarvis_data目录
    2. 加载环境变量到os.environ
    3. 处理文件读取异常
    4. 检查git仓库状态并在落后时更新
    5. 统计当前命令使用次数
    """
    count_cmd_usage()

    jarvis_ascii_art = f"""
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
██╗██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
 {welcome_str}

 https://github.com/skyfireitdiy/Jarvis
 v{__version__}
"""
    if welcome_str:
        PrettyOutput.print_gradient_text(jarvis_ascii_art, (0, 120, 255), (0, 255, 200))

    jarvis_dir = Path(get_data_dir())
    config_file = jarvis_dir / "config.yaml"

    # 检查jarvis_data目录是否存在
    if not jarvis_dir.exists():
        jarvis_dir.mkdir(parents=True)

    script_dir = Path(os.path.dirname(os.path.dirname(__file__)))
    hf_archive = script_dir / "jarvis_data" / "huggingface.tar.gz"


    # 检查并解压huggingface模型
    hf_dir = jarvis_dir / "huggingface" / "hub"
    if not hf_dir.exists() and hf_archive.exists():
        try:
            PrettyOutput.print("正在解压HuggingFace模型...", OutputType.INFO)
            with tarfile.open(hf_archive, "r:gz") as tar:
                tar.extractall(path=jarvis_dir)
            PrettyOutput.print("HuggingFace模型解压完成", OutputType.SUCCESS)
        except Exception as e:
            PrettyOutput.print(f"解压HuggingFace模型失败: {e}", OutputType.ERROR)


    if not config_file.exists():
        old_config_file = jarvis_dir / "env"
        if old_config_file.exists():# 旧的配置文件存在
            _read_old_config_file(old_config_file)
    else:
        _read_config_file(jarvis_dir, config_file)        

        # 检查是否是git仓库并更新
    from jarvis.jarvis_utils.git_utils import check_and_update_git_repo

    check_and_update_git_repo(str(script_dir))

def _read_config_file(jarvis_dir, config_file):
    """读取并解析YAML格式的配置文件
    
    功能：
    1. 读取配置文件内容
    2. 检查并添加schema声明(如果缺失)
    3. 将配置数据保存到全局变量
    4. 设置环境变量(如果配置中有ENV字段)
    
    参数:
        jarvis_dir: Jarvis数据目录路径
        config_file: 配置文件路径
    """
    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
        config_data = yaml.safe_load(content) or {}
        if isinstance(config_data, dict):
                # 检查是否已有schema声明，没有则添加
            if "# yaml-language-server: $schema=" not in content:
                schema_path = Path(os.path.relpath(
                        Path(__file__).parent.parent / "jarvis_data" / "config_schema.json",
                        start=jarvis_dir
                    ))
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(f"# yaml-language-server: $schema={schema_path}\n")
                    f.write(content)
            # 保存到全局变量
        set_global_env_data(config_data)
            # 如果配置中有ENV键值对，则设置环境变量
        if "ENV" in config_data and isinstance(config_data["ENV"], dict):
            os.environ.update({str(k): str(v) for k, v in config_data["ENV"].items() if v is not None})

def _read_old_config_file(config_file):
    """读取并解析旧格式的env配置文件
    
    功能：
    1. 解析键值对格式的旧配置文件
    2. 支持多行值的处理
    3. 自动去除值的引号和空格
    4. 将配置数据保存到全局变量
    5. 设置环境变量并显示迁移警告
    
    参数:
        config_file: 旧格式配置文件路径
    """
    config_data = {}
    current_key = None
    current_value = []
    with open(config_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" in line and not line.startswith((" ", "\t")):
                        # 处理之前收集的多行值
                if current_key is not None:
                    value = "\n".join(current_value).strip().strip("'").strip('"')
                    # 将字符串"true"/"false"转换为bool类型
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    config_data[current_key] = value
                    current_value = []
                        # 解析新的键值对
                key, value = line.split("=", 1)
                current_key = key.strip()
                current_value.append(value.strip())
            elif current_key is not None:
                        # 多行值的后续行
                current_value.append(line.strip())
                # 处理最后一个键值对
        if current_key is not None:
            value = "\n".join(current_value).strip().strip("'").strip('"')
            # 将字符串"true"/"false"转换为bool类型
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            config_data[current_key] = value
        os.environ.update({str(k): str(v) for k, v in config_data.items() if v is not None})
        set_global_env_data(config_data)
    PrettyOutput.print(f"检测到旧格式配置文件，旧格式以后将不再支持，请尽快迁移到新格式", OutputType.WARNING)

    
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
            PrettyOutput.print(f"执行失败: {str(e)}, 等待 {sleep_time}s...", OutputType.WARNING)
            time.sleep(sleep_time)
            continue
def while_true(func: Callable[[], bool], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到返回True
    
    参数:
        func: 要执行的函数，必须返回布尔值
        sleep_time: 每次失败后的等待时间(秒)
        
    返回:
        函数最终返回的True值
        
    注意:
        与while_success不同，此函数只检查返回是否为True，
        不捕获异常，异常会直接抛出
    """
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



def _get_cmd_stats() -> Dict[str, int]:
    """从数据目录获取命令调用统计"""
    stats_file = Path(get_data_dir()) / "cmd_stat.yaml"
    if stats_file.exists():
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            PrettyOutput.print(
                f"加载命令调用统计失败: {str(e)}", OutputType.WARNING
            )
    return {}

def _update_cmd_stats(cmd_name: str) -> None:
    """更新命令调用统计"""
    stats = _get_cmd_stats()
    stats[cmd_name] = stats.get(cmd_name, 0) + 1
    stats_file = Path(get_data_dir()) / "cmd_stat.yaml"
    try:
        with open(stats_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(stats, f, allow_unicode=True)
    except Exception as e:
        PrettyOutput.print(
            f"保存命令调用统计失败: {str(e)}", OutputType.WARNING
        )

def count_cmd_usage() -> None:
    """统计当前命令的使用次数"""
    import sys
    _update_cmd_stats(sys.argv[0])

def is_context_overflow(content: str) -> bool:
    """判断文件内容是否超出上下文限制"""
    return get_context_token_count(content) > get_max_big_content_size() 

def get_loc_stats() -> str:
    """使用loc命令获取当前目录的代码统计信息
    
    返回:
        str: loc命令输出的原始字符串，失败时返回空字符串
    """
    try:
        result = subprocess.run(
            ['loc'],
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        return ""