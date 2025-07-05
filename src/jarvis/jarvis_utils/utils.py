# -*- coding: utf-8 -*-
import hashlib
import json
import os
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml  # type: ignore

from jarvis import __version__
from jarvis.jarvis_utils.config import (
    get_data_dir,
    get_max_big_content_size,
    set_global_env_data,
)
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.globals import get_in_chat, get_interrupt, set_interrupt
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

g_config_file = None


def _setup_signal_handler() -> None:
    """设置SIGINT信号处理函数"""
    original_sigint = signal.getsignal(signal.SIGINT)

    def sigint_handler(signum, frame):
        if get_in_chat():
            set_interrupt(True)
            if get_interrupt() > 5 and original_sigint and callable(original_sigint):
                original_sigint(signum, frame)
        else:
            if original_sigint and callable(original_sigint):
                original_sigint(signum, frame)

    signal.signal(signal.SIGINT, sigint_handler)


def _show_welcome_message(welcome_str: str) -> None:
    """显示欢迎信息

    参数:
        welcome_str: 欢迎信息字符串
    """
    if not welcome_str:
        return

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
    PrettyOutput.print_gradient_text(jarvis_ascii_art, (0, 120, 255), (0, 255, 200))


def _check_git_updates() -> bool:
    """检查并更新git仓库

    返回:
        bool: 是否需要重启进程
    """
    script_dir = Path(os.path.dirname(os.path.dirname(__file__)))
    from jarvis.jarvis_utils.git_utils import check_and_update_git_repo

    return check_and_update_git_repo(str(script_dir))


def init_env(welcome_str: str, config_file: Optional[str] = None) -> None:
    """初始化Jarvis环境

    参数:
        welcome_str: 欢迎信息字符串
        config_file: 配置文件路径，默认为None(使用~/.jarvis/config.yaml)
    """
    # 1. 设置信号处理
    _setup_signal_handler()

    # 2. 统计命令使用
    count_cmd_usage()

    # 3. 显示欢迎信息
    if welcome_str:
        _show_welcome_message(welcome_str)

    # 4. 设置配置文件
    global g_config_file
    g_config_file = config_file
    load_config()

    # 5. 检查git更新
    if _check_git_updates():
        os.execv(sys.executable, [sys.executable] + sys.argv)
        sys.exit(0)


def load_config():
    config_file = g_config_file
    config_file_path = (
        Path(config_file)
        if config_file is not None
        else Path(os.path.expanduser("~/.jarvis/config.yaml"))
    )

    # 加载配置文件
    if not config_file_path.exists():
        old_config_file = config_file_path.parent / "env"
        if old_config_file.exists():  # 旧的配置文件存在
            _read_old_config_file(old_config_file)
        else:
            # 生成默认配置文件
            schema_path = (
                Path(__file__).parent.parent / "jarvis_data" / "config_schema.json"
            )
            if schema_path.exists():
                try:
                    config_file_path.parent.mkdir(parents=True, exist_ok=True)
                    generate_default_config(str(schema_path), str(config_file_path))
                    PrettyOutput.print(
                        f"已生成默认配置文件: {config_file_path}", OutputType.INFO
                    )
                except Exception as e:
                    PrettyOutput.print(f"生成默认配置文件失败: {e}", OutputType.ERROR)
    else:
        _load_and_process_config(str(config_file_path.parent), str(config_file_path))


from typing import Tuple


def _load_config_file(config_file: str) -> Tuple[str, dict]:
    """读取并解析YAML格式的配置文件

    参数:
        config_file: 配置文件路径

    返回:
        Tuple[str, dict]: (文件原始内容, 解析后的配置字典)
    """
    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
        config_data = yaml.safe_load(content) or {}
        return content, config_data


def _ensure_schema_declaration(
    jarvis_dir: str, config_file: str, content: str, config_data: dict
) -> None:
    """确保配置文件包含schema声明

    参数:
        jarvis_dir: Jarvis数据目录路径
        config_file: 配置文件路径
        content: 配置文件原始内容
        config_data: 解析后的配置字典
    """
    if (
        isinstance(config_data, dict)
        and "# yaml-language-server: $schema=" not in content
    ):
        schema_path = Path(
            os.path.relpath(
                Path(__file__).parent.parent / "jarvis_data" / "config_schema.json",
                start=jarvis_dir,
            )
        )
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(f"# yaml-language-server: $schema={schema_path}\n")
            f.write(content)


def _process_env_variables(config_data: dict) -> None:
    """处理配置中的环境变量

    参数:
        config_data: 解析后的配置字典
    """
    if "ENV" in config_data and isinstance(config_data["ENV"], dict):
        os.environ.update(
            {str(k): str(v) for k, v in config_data["ENV"].items() if v is not None}
        )


def _load_and_process_config(jarvis_dir: str, config_file: str) -> None:
    """加载并处理配置文件

    功能：
    1. 读取配置文件
    2. 确保schema声明存在
    3. 保存配置到全局变量
    4. 处理环境变量

    参数:
        jarvis_dir: Jarvis数据目录路径
        config_file: 配置文件路径
    """
    content, config_data = _load_config_file(config_file)
    _ensure_schema_declaration(jarvis_dir, config_file, content, config_data)
    set_global_env_data(config_data)
    _process_env_variables(config_data)


def generate_default_config(schema_path: str, output_path: str) -> None:
    """从schema文件生成默认的YAML格式配置文件

    功能：
    1. 从schema文件读取配置结构
    2. 根据schema中的default值生成默认配置
    3. 自动添加schema声明
    4. 处理嵌套的schema结构
    5. 保留注释和格式

    参数:
        schema_path: schema文件路径
        output_path: 生成的配置文件路径
    """
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    def _generate_from_schema(schema_dict: Dict[str, Any]) -> Dict[str, Any]:
        config = {}
        if "properties" in schema_dict:
            for key, value in schema_dict["properties"].items():
                if "default" in value:
                    config[key] = value["default"]
                elif "properties" in value:  # 处理嵌套对象
                    config[key] = _generate_from_schema(value)
                elif value.get("type") == "array":  # 处理列表类型
                    config[key] = []
        return config

    default_config = _generate_from_schema(schema)

    # 添加schema声明
    rel_schema_path = Path(
        os.path.relpath(
            Path(schema_path),
            start=Path(output_path).parent,
        )
    )
    content = f"# yaml-language-server: $schema={rel_schema_path}\n"
    content += yaml.dump(default_config, allow_unicode=True, sort_keys=False)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


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
        os.environ.update(
            {str(k): str(v) for k, v in config_data.items() if v is not None}
        )
        set_global_env_data(config_data)
    PrettyOutput.print(
        f"检测到旧格式配置文件，旧格式以后将不再支持，请尽快迁移到新格式",
        OutputType.WARNING,
    )


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
            PrettyOutput.print(
                f"执行失败: {str(e)}, 等待 {sleep_time}s...", OutputType.WARNING
            )
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


def get_file_md5(filepath: str) -> str:
    """计算文件内容的MD5哈希值

    参数:
        filepath: 要计算哈希的文件路径

    返回:
        str: 文件内容的MD5哈希值
    """
    return hashlib.md5(open(filepath, "rb").read(100 * 1024 * 1024)).hexdigest()


def user_confirm(tip: str, default: bool = True) -> bool:
    """提示用户确认是/否问题

    参数:
        tip: 显示给用户的消息
        default: 用户直接回车时的默认响应

    返回:
        bool: 用户确认返回True，否则返回False
    """
    try:
        suffix = "[Y/n]" if default else "[y/N]"
        ret = get_single_line_input(f"{tip} {suffix}: ")
        return default if ret == "" else ret.lower() == "y"
    except KeyboardInterrupt:
        return False


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
            PrettyOutput.print(f"加载命令调用统计失败: {str(e)}", OutputType.WARNING)
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
        PrettyOutput.print(f"保存命令调用统计失败: {str(e)}", OutputType.WARNING)


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
        result = subprocess.run(["loc"], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        return ""
