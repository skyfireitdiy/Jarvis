# -*- coding: utf-8 -*-
import hashlib
import os
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

import yaml

from jarvis import __version__
from jarvis.jarvis_utils.config import get_data_dir, get_max_big_content_size
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
    env_file = jarvis_dir / "env"

    # 如果env文件不存在，创建并写入schema声明
    if not env_file.exists():
        # 计算从env文件到env_schema.json的相对路径
        schema_path = Path(os.path.relpath(
            Path(__file__).parent.parent / "jarvis_data" / "env_schema.json",
            start=jarvis_dir
        ))
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"# yaml-language-server: $schema={schema_path}\n")

    script_dir = Path(os.path.dirname(os.path.dirname(__file__)))
    hf_archive = script_dir / "jarvis_data" / "huggingface.tar.gz"

    # 检查jarvis_data目录是否存在
    if not jarvis_dir.exists():
        jarvis_dir.mkdir(parents=True)

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

    if env_file.exists():
        try:
            # 首先尝试作为YAML文件读取
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    env_data = yaml.safe_load(content) or {}
                    if isinstance(env_data, dict):
                        # 检查是否已有schema声明，没有则添加
                        if "# yaml-language-server: $schema=" not in content:
                            schema_path = Path(os.path.relpath(
                                Path(__file__).parent.parent / "jarvis_data" / "env_schema.json",
                                start=jarvis_dir
                            ))
                            with open(env_file, "w", encoding="utf-8") as f:
                                f.write(f"# yaml-language-server: $schema={schema_path}\n")
                                f.write(content)
                        os.environ.update({str(k): str(v) for k, v in env_data.items() if v is not None})
                        return
            except yaml.YAMLError:
                pass
            
            # 如果不是YAML格式，按旧格式处理
            current_key = None
            current_value = []
            env_data = {}
            with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip()
                    if not line or line.startswith(("#", ";")):
                        continue
                    if "=" in line and not line.startswith((" ", "\t")):
                        # 处理之前收集的多行值
                        if current_key is not None:
                            env_data[current_key] = "\n".join(current_value).strip().strip("'").strip('"')
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
                env_data[current_key] = "\n".join(current_value).strip().strip("'").strip('"')
            
            # 更新环境变量
            os.environ.update(env_data)
            
            # 如果是旧格式，转换为YAML并备份
            backup_file = env_file.with_name(f"env.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
            env_file.rename(backup_file)
            schema_path = Path(os.path.relpath(
                Path(__file__).parent.parent / "jarvis_data" / "env_schema.json",
                start=jarvis_dir
            ))
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(f"# yaml-language-server: $schema={schema_path}\n")
                yaml.dump(env_data, f, default_flow_style=False, allow_unicode=True)
            
            PrettyOutput.print(f"检测到旧格式配置文件，已自动转换为YAML格式并备份到 {backup_file}", OutputType.INFO)
            
        except Exception as e:
            PrettyOutput.print(f"警告: 读取 {env_file} 失败: {e}", OutputType.WARNING)

        # 检查是否是git仓库并更新
    from jarvis.jarvis_utils.git_utils import check_and_update_git_repo

    check_and_update_git_repo(str(script_dir))

    
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
            yaml.safe_dump(stats, f)
    except Exception as e:
        PrettyOutput.print(
            f"保存命令调用统计失败: {str(e)}", OutputType.WARNING
        )

def count_cmd_usage() -> None:
    """统计当前命令的使用次数"""
    import sys
    if len(sys.argv) > 1:
        cmd_name = sys.argv[1]
        _update_cmd_stats(cmd_name)

def is_context_overflow(content: str) -> bool:
    """判断文件内容是否超出上下文限制"""
    return get_context_token_count(content) > get_max_big_content_size() 