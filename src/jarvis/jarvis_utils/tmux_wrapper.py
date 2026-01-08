# -*- coding: utf-8 -*-
"""Tmux 自动启动封装模块

检测系统是否安装tmux，如果不在tmux环境中运行，自动创建tmux会话并重新执行命令。
"""

import getpass
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from typing import List, Optional

from jarvis.jarvis_utils.output import PrettyOutput, OutputType


def _get_username() -> str:
    """获取当前用户名。

    优先使用getpass.getuser()，降级到环境变量USER，
    最后返回'unknown'作为兜底。

    Returns:
        str: 用户名
    """
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "unknown")


def _generate_session_name() -> str:
    """生成带用户名前缀的tmux session名称。

    统一格式：{username}-jarvis-{uuid}
    使用UUID确保唯一性，支持多用户环境。

    Returns:
        str: 生成的session名称
    """
    username = _get_username()
    unique_suffix = uuid.uuid4().hex[:8]
    return f"{username}-jarvis-{unique_suffix}"


def dispatch_to_tmux_window(
    task_arg: Optional[str], argv: list[str], window_name: str = "jarvis-dispatch"
) -> bool:
    """将任务派发到新的 tmux 窗格（pane）中执行。

    Args:
        task_arg: 任务内容（已废弃，保留用于兼容）
        argv: 当前命令行参数（需要过滤 --dispatch）
        window_name: 窗口名称前缀（已废弃，保留用于兼容）

    Returns:
        bool: 是否成功派发（True表示成功，False表示失败）

    注意:
        在 tmux 环境中直接在当前窗口创建新窗格。
        如果不在 tmux 环境中，会查找 jarvis 创建的 tmux session
        并在其中创建窗格作为降级方案。
        使用水平分割（split-window -h）创建新窗格，适合代码任务。
    """
    # 检查配置中是否启用了tmux
    from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

    if not GLOBAL_CONFIG_DATA.get("enable_tmux", True):
        return False

    # 检查tmux是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return False

    # 检查是否已在tmux环境中运行
    if "TMUX" not in os.environ:
        # 不在tmux中，尝试查找jarvis创建的session作为降级方案
        return _dispatch_to_existing_jarvis_session(task_arg, argv)

    # 生成窗口名称（使用任务内容的前20个字符）
    if task_arg and str(task_arg).strip():
        # 清理任务内容，移除换行和特殊字符
        clean_task = str(task_arg).strip()[:20].replace("\n", " ").replace("\r", " ")
        window_name = f"{window_name}-{clean_task}"

    # 过滤 --dispatch/-d 参数，避免循环派发
    # 由于 --dispatch/-d 是布尔参数，通常不会带值
    # 但为了健壮性，处理所有可能的格式
    filtered_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--dispatch" or arg == "-d":
            # 情况1: --dispatch/-d（无值），直接跳过
            continue
        elif arg.startswith("--dispatch=") or arg.startswith("-d="):
            # 情况2: --dispatch=value/-d=value，整个参数跳过
            continue
        else:
            # 保留其他参数
            filtered_argv.append(arg)

    # 获取当前窗口标识，用于后续布局切换
    # tmux select-layout 支持 session_name:window_index 格式的目标参数
    current_window = None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}:#{window_index}"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_window = result.stdout.strip()
        # 验证格式是否正确（应包含冒号分隔符）
        if not current_window or ":" not in current_window:
            PrettyOutput.print(
                f"⚠️ Invalid window format: '{current_window}'",
                OutputType.WARNING,
                timestamp=False,
            )
            current_window = None
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to get current window: {e}",
            OutputType.WARNING,
            timestamp=False,
        )

    # 构造 tmux split-window 命令（在当前窗口创建新的窗格）
    # split-window -h "<command>" - 水平分割（左右布局）
    executable = sys.executable
    # 使用 shlex.quote() 安全地转义每个参数，防止 shell 注入
    quoted_args = [shlex.quote(arg) for arg in filtered_argv]
    # 获取用户的默认shell，主命令结束后启动shell保持panel活动
    user_shell = os.environ.get("SHELL", "/bin/sh")
    # 先切换到当前工作目录，再执行命令
    cwd = os.getcwd()
    command = f'cd {shlex.quote(cwd)} && {executable} {" ".join(quoted_args)}; exec "{user_shell}"'

    tmux_args = [
        "tmux",
        "split-window",
        "-h",  # 水平分割（左右布局），适合代码任务
        command,
    ]

    # 执行tmux命令
    try:
        subprocess.run(tmux_args, check=True)
        return True
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to dispatch to tmux window: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return False


def check_and_launch_tmux() -> None:
    """检测tmux并在需要时启动tmux会话。

    注意:
        此函数使用subprocess.execvp替换当前进程，如果成功则不会返回。
        Session名称统一使用 {username}-jarvis-{uuid} 格式。
    """
    # 检查配置中是否启用了tmux
    from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

    if not GLOBAL_CONFIG_DATA.get("enable_tmux", True):
        return

    # 检查tmux是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        # tmux未安装，正常继续执行
        return

    # 检查是否已在tmux环境中运行
    # tmux会设置TMUX环境变量
    if "TMUX" in os.environ:
        # 已在tmux中，正常继续执行
        return

    # tmux已安装且不在tmux中，优先查找现有 session
    existing_session = find_or_create_jarvis_session(force_create=False)

    # 如果找到现有 session，附加到该 session
    if existing_session:
        PrettyOutput.print(
            f"ℹ️ 找到现有 session: {existing_session}，正在附加...",
            OutputType.INFO,
            timestamp=False,
        )
        tmux_args = [
            "tmux",
            "attach",
            "-t",
            existing_session,
        ]
        try:
            os.execvp("tmux", tmux_args)
        except OSError as e:
            PrettyOutput.print(
                f"⚠️ Failed to attach to tmux session '{existing_session}': {e}",
                OutputType.WARNING,
                timestamp=False,
            )
            return

    # 未找到现有 session，创建新的 session
    # 为会话名称添加随机后缀，避免冲突
    session_name = _generate_session_name()
    # 构造tmux命令：new-session -s <session_name> -- <command>
    # -s: 指定会话名称
    # --: 后面的参数是要执行的命令

    # 获取当前可执行文件路径和参数
    executable = sys.executable
    argv = sys.argv

    # 获取用户的默认shell
    user_shell = os.environ.get("SHELL", "/bin/sh")

    # 构造tmux命令参数
    # 使用shell包装器来确保会话在主命令结束后继续运行
    # 参考 dispatch_to_tmux_window 的实现，使用 shlex.quote 安全转义参数
    quoted_args = [shlex.quote(arg) for arg in argv]
    command = f'{executable} {" ".join(quoted_args)}; exec "{user_shell}"'
    tmux_args = [
        "tmux",
        "new-session",
        "-s",
        session_name,
        command,
    ]

    # 替换当前进程为tmux
    # execvp会替换当前进程，不会返回
    try:
        os.execvp("tmux", tmux_args)
    except OSError as e:
        # 如果执行失败，输出警告并继续
        PrettyOutput.print(
            f"⚠️ Failed to launch tmux: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return


def _find_jarvis_session() -> Optional[str]:
    """查找 jarvis tmux session。

    Returns:
        Optional[str]: 找到的 session 名称，未找到返回 None

    注意:
        仅查找带用户名前缀的 "jarvis" session。
        格式：{username}-jarvis-{uuid}
    """
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        # 获取用户名用于构建前缀
        username = _get_username()
        # 解析 session 名称：格式为 "session-name: windows (created ...)"
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                # 提取 session 名称（冒号之前的部分）
                session_name = line.split(":")[0].strip()
                # 匹配带用户名前缀的会话：{username}-jarvis-{uuid}
                expected_prefix = f"{username}-jarvis-"
                if session_name.startswith(expected_prefix):
                    # 精确前缀匹配：检查去除前缀后的部分是否为数字或UUID
                    suffix = session_name[len(expected_prefix) :]
                    if suffix and (
                        suffix[0].isdigit() or suffix[0] in "abcdef0123456789"
                    ):
                        # 匹配成功：后缀以数字或UUID字符开头
                        return session_name
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # 正常情况：没有活动的 tmux 会话时不打印警告
        pass
    except Exception as e:
        # 保留真正的意外错误警告
        PrettyOutput.print(
            f"⚠️ Unexpected error while listing sessions: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
    return None


def list_session_windows(session_name: str) -> List[str]:
    """获取指定tmux session的window列表。

    Args:
        session_name: tmux session名称

    Returns:
        List[str]: window列表，格式为["index: name", ...]（如["1: bash", "2: editor"]）

    注意:
        如果session不存在或命令执行失败，返回空列表。
        window列表按索引顺序排列。
    """
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-windows",
                "-t",
                session_name,
                "-F",
                "#{window_index}: #{window_name}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        # 解析输出，过滤空行
        windows = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
        return windows
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # session不存在或命令执行失败，返回空列表
        return []
    except Exception as e:
        # 记录意外错误
        PrettyOutput.print(
            f"⚠️ Unexpected error while listing windows for session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return []


def get_window_pane_count(session_name: str, window_id: str) -> int:
    """获取指定tmux session的指定window的panel数量。

    Args:
        session_name: tmux session名称
        window_id: window标识（索引或名称，如 "1" 或 "1: bash"）

    Returns:
        int: panel数量，如果window不存在或命令执行失败返回0

    注意:
        window_id可以是完整的"index: name"格式（如"1: bash"），
        也可以仅是索引（如"1"）。
        如果session不存在或命令执行失败，返回0。
    """
    try:
        # 解析 window_id：支持 "index: name" 和 "index" 两种格式
        # 如果包含冒号，提取索引部分；否则直接使用
        target_window = (
            window_id.split(":")[0].strip() if ":" in window_id else window_id
        )

        # 构造 tmux 目标参数
        target = f"{session_name}:{target_window}"

        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-t",
                target,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        # 统计输出行数（每行代表一个 pane）
        panes = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
        return len(panes)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # window不存在或命令执行失败，返回0
        return 0
    except Exception as e:
        # 记录意外错误
        PrettyOutput.print(
            f"⚠️ Unexpected error while counting panes for window '{window_id}' in session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return 0


def create_window(
    session_name: str,
    window_name: Optional[str] = None,
    working_dir: Optional[str] = None,
    initial_command: Optional[str] = None,
) -> Optional[str]:
    """在指定的 tmux session 中创建一个新的 window。

    Args:
        session_name: tmux session 名称
        window_name: window 名称（可选）
        working_dir: 工作目录（可选，None表示使用当前工作目录）
        initial_command: 初始命令（可选，None表示只启动用户shell）

    Returns:
        Optional[str]: 新创建的 window ID，失败返回 None

    注意:
        创建的 window 是 detached 状态，不会自动切换到该 window。
        如果指定了 initial_command，命令执行结束后会启动用户的默认 shell 保持 window 活动。
    """
    # 确定工作目录
    if working_dir is None:
        working_dir = os.getcwd()

    # 获取用户的默认 shell
    user_shell = os.environ.get("SHELL", "/bin/sh")

    # 构造命令
    if initial_command:
        # 先切换到工作目录，执行初始命令，然后启动 shell 保持 window 活动
        command = (
            f'cd {shlex.quote(working_dir)} && {initial_command}; exec "{user_shell}"'
        )
    else:
        # 只切换到工作目录并启动 shell
        command = f'cd {shlex.quote(working_dir)}; exec "{user_shell}"'

    # 构造 tmux new-window 命令
    tmux_args = [
        "tmux",
        "new-window",
        "-d",  # 创建 detached window
        "-P",  # 打印新创建的 window 信息
        "-F",  # 指定输出格式（使用 window_index 以便后续 send-keys 调用）
        "#{window_index}",
        "-c",  # 指定工作目录
        working_dir,
    ]

    # 如果指定了 window 名称，添加 -n 参数
    if window_name:
        tmux_args.extend(["-n", window_name])

    # 添加目标 session 和命令
    tmux_args.extend(["-t", session_name, command])

    # 执行 tmux 命令
    try:
        result = subprocess.run(
            tmux_args,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        # 返回新创建的 window ID
        window_id = result.stdout.strip()
        if window_id:
            return window_id
        else:
            PrettyOutput.print(
                f"⚠️ tmux new-window returned empty window_id for session '{session_name}'",
                OutputType.WARNING,
                timestamp=False,
            )
            PrettyOutput.print(
                f"⚠️ stdout: {result.stdout}",
                OutputType.WARNING,
                timestamp=False,
            )
            return None
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to create window in session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return None
    except subprocess.TimeoutExpired:
        PrettyOutput.print(
            f"⚠️ Creating window in session '{session_name}' timed out",
            OutputType.WARNING,
            timestamp=False,
        )
        return None
    except Exception as e:
        PrettyOutput.print(
            f"⚠️ Unexpected error creating window in session '{session_name}': {type(e).__name__}: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return None


def create_panel(
    session_name: str,
    window_id: str,
    initial_command: str,
    split_direction: str = "h",
    working_dir: Optional[str] = None,
    pane_percentage: Optional[int] = None,
) -> Optional[str]:
    """在指定的 tmux session 和 window 中创建 panel 并执行初始命令。

    Args:
        session_name: tmux session 名称
        window_id: window 标识（索引或名称，如 "1" 或 "1: bash"）
        initial_command: panel 中执行的初始命令
        split_direction: 分割方向，"h"表示水平分割（左右），"v"表示垂直分割（上下）
        working_dir: 工作目录，None表示使用当前工作目录
        pane_percentage: pane 大小百分比（1-99），None表示默认大小

    Returns:
        Optional[str]: 新创建的 pane ID，失败返回 None

    注意:
        window_id 可以是完整的"index: name"格式，也可以仅是索引。
        创建 panel 后会在命令执行结束后启动用户的默认 shell 保持 panel 活动。
    """
    # 验证 split_direction 参数
    if split_direction not in ("h", "v"):
        PrettyOutput.print(
            f"⚠️ Invalid split_direction: '{split_direction}', must be 'h' or 'v'",
            OutputType.WARNING,
            timestamp=False,
        )
        return None

    # 验证 pane_percentage 参数
    if pane_percentage is not None and (pane_percentage < 1 or pane_percentage > 99):
        PrettyOutput.print(
            f"⚠️ Invalid pane_percentage: '{pane_percentage}', must be between 1 and 99",
            OutputType.WARNING,
            timestamp=False,
        )
        return None

    # 解析 window_id：支持 "index: name" 和 "index" 两种格式
    target_window = window_id.split(":")[0].strip() if ":" in window_id else window_id

    # 构造 tmux 目标参数
    target = f"{session_name}:{target_window}"

    # 确定工作目录
    if working_dir is None:
        working_dir = os.getcwd()

    # 获取用户的默认 shell
    user_shell = os.environ.get("SHELL", "/bin/sh")

    # 构造命令：先切换到工作目录，执行初始命令，然后启动 shell 保持 panel 活动
    command = f'cd {shlex.quote(working_dir)} && {initial_command}; exec "{user_shell}"'

    # 构造 tmux split-window 命令
    tmux_args = [
        "tmux",
        "split-window",
        "-d",  # 创建 detached pane，避免影响当前 pane
        f"-{split_direction}",  # -h 水平分割，-v 垂直分割
    ]

    # 如果指定了 pane 大小，添加 -p 参数
    if pane_percentage is not None:
        tmux_args.extend(["-p", str(pane_percentage)])

    # 添加目标和命令
    tmux_args.extend(["-t", target, command])

    # 执行 tmux 命令创建 pane
    try:
        subprocess.run(
            tmux_args,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

        # 获取新创建的 pane ID（通过 list-panes 找到最新的 pane）
        list_args = [
            "tmux",
            "list-panes",
            "-t",
            target,
            "-F",
            "#{pane_index}",
        ]
        list_result = subprocess.run(
            list_args,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )

        # 找到最新的 pane（索引最大的）
        panes = list_result.stdout.strip().split("\n")
        if not panes or not panes[0]:
            PrettyOutput.print(
                f"⚠️ Failed to list panes for target '{target}'",
                OutputType.WARNING,
                timestamp=False,
            )
            return None

        # 最后一个 pane 就是最新的
        latest_pane_index = panes[-1]

        # 获取完整的 pane_id
        get_id_args = [
            "tmux",
            "display-message",
            "-t",
            f"{target}.{latest_pane_index}",
            "-p",
            "#{pane_id}",
        ]
        id_result = subprocess.run(
            get_id_args,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )

        pane_id = id_result.stdout.strip()
        if pane_id:
            return pane_id
        else:
            PrettyOutput.print(
                f"⚠️ Failed to get pane_id for target '{target}'",
                OutputType.WARNING,
                timestamp=False,
            )
            PrettyOutput.print(
                f"⚠️ list-panes output: {list_result.stdout.strip()}",
                OutputType.WARNING,
                timestamp=False,
            )
            return None
    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr.strip() if e.stderr else "(no stderr output)"
        PrettyOutput.print(
            f"⚠️ Failed to create panel in window '{window_id}' of session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        PrettyOutput.print(
            f"⚠️ tmux stderr: {stderr_output}",
            OutputType.WARNING,
            timestamp=False,
        )
        return None
    except subprocess.TimeoutExpired:
        PrettyOutput.print(
            f"⚠️ Creating panel in window '{window_id}' of session '{session_name}' timed out",
            OutputType.WARNING,
            timestamp=False,
        )
        return None
    except Exception as e:
        PrettyOutput.print(
            f"⚠️ Unexpected error creating panel in window '{window_id}' of session '{session_name}': {type(e).__name__}: {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return None


def set_window_tiled_layout(session_name: str, window_id: Optional[str] = None) -> bool:
    """设置指定 tmux session 的 window 布局为 tiled（平铺）。

    Args:
        session_name: tmux session 名称
        window_id: window 标识（索引或名称，如 "1" 或 "1: bash"）
                     如果为 None，则设置 session 的当前 window

    Returns:
        bool: 是否成功设置布局（True表示成功，False表示失败）

    注意:
        window_id 可以是完整的"index: name"格式，也可以仅是索引。
        如果 window_id 为 None，则设置 session 中当前活跃的 window。
        tiled 布局会将所有 pane 平均分配空间。
    """
    # 构造 tmux 目标参数
    if window_id is None:
        # 设置 session 的当前 window
        target = session_name
    else:
        # 解析 window_id：支持 "index: name" 和 "index" 两种格式
        target_window = (
            window_id.split(":")[0].strip() if ":" in window_id else window_id
        )
        target = f"{session_name}:{target_window}"

    # 执行 tmux select-layout 命令
    try:
        subprocess.run(
            ["tmux", "select-layout", "-t", target, "tiled"],
            check=True,
            timeout=5,
        )
        return True
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to set tiled layout for window '{window_id or 'current'}' in session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return False
    except subprocess.TimeoutExpired:
        PrettyOutput.print(
            f"⚠️ Setting tiled layout for window '{window_id or 'current'}' in session '{session_name}' timed out",
            OutputType.WARNING,
            timestamp=False,
        )
        return False


def find_or_create_jarvis_session(force_create: bool = True) -> Optional[str]:
    """查找或创建 jarvis session。

    优先查找现有的 jarvis session，找到则返回 session 名称，
    未找到则创建新 session。

    Args:
        force_create: 未找到时是否创建新 session

    Returns:
        Optional[str]: 找到或创建的 session 名称，未找到且不创建则返回 None
    """
    # 先尝试查找现有 session
    existing_session = _find_jarvis_session()
    if existing_session:
        return existing_session

    # 未找到现有 session
    if not force_create:
        return None

    # 创建新的 session
    session_name = _generate_session_name()
    try:
        # 创建新的 detached session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            check=True,
            timeout=10,
        )
        return session_name
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(
            f"⚠️ Failed to create tmux session '{session_name}': {e}",
            OutputType.WARNING,
            timestamp=False,
        )
        return None
    except subprocess.TimeoutExpired:
        PrettyOutput.print(
            f"⚠️ Creating tmux session '{session_name}' timed out",
            OutputType.WARNING,
            timestamp=False,
        )
        return None


def get_session_current_window(session_name: str) -> Optional[str]:
    """获取指定 tmux session 的当前窗口索引。

    Args:
        session_name: tmux session 名称

    Returns:
        Optional[str]: 当前窗口索引（如 '0', '1'），如果失败则返回 None
    """
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return None

    try:
        # 获取 session 的所有窗口，当前窗口会带有 * 标记
        result = subprocess.run(
            [
                "tmux",
                "list-windows",
                "-t",
                session_name,
                "-F",
                "#{window_index}:#{window_flags}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        # 解析输出，查找带有 * 标记的窗口（当前窗口）
        for line in result.stdout.strip().split("\n"):
            if "*" in line:
                # 返回窗口索引部分（冒号之前）
                window_idx = line.split(":")[0].strip()
                return window_idx if window_idx else None
        return None
    except Exception:
        return None


def get_current_session_name() -> Optional[str]:
    """获取当前 tmux session 名称。

    Returns:
        Optional[str]: 当前 session 名称，如果不在 tmux 环境或失败则返回 None
    """
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return None

    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            session_name = result.stdout.strip()
            return session_name if session_name else None
        return None
    except Exception:
        return None


def get_current_window_index() -> Optional[str]:
    """获取当前 tmux 窗口的索引。

    Returns:
        Optional[str]: 当前窗口索引（如 '0', '1'），如果不在 tmux 环境或失败则返回 None
    """
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return None

    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{window_index}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            window_index = result.stdout.strip()
            return window_index if window_index else None
        return None
    except Exception:
        return None


def has_session(session_name: str) -> bool:
    """检查指定的 tmux session 是否存在。

    Args:
        session_name: session 名称

    Returns:
        bool: session 是否存在
    """
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return False

    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def send_command_to_window(
    session_name: str, window_id: str, command: list[str]
) -> bool:
    """向指定窗口的初始 pane 发送命令。

    Args:
        session_name: session 名称
        window_id: 窗口索引
        command: 命令列表（会被 shell 转义）

    Returns:
        bool: 是否成功发送
    """
    import shlex

    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        return False

    # 将命令转换为字符串并正确转义
    cmd_str = " ".join(shlex.quote(arg) for arg in command)

    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", f"{session_name}:{window_id}", cmd_str, "C-m"],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def dispatch_command_to_panel(
    shell_command: str, max_panes_per_window: int = 4
) -> Optional[str]:
    """智能调度命令到 tmux panel 中执行。"""
    # 检查 tmux 是否安装
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        PrettyOutput.print(
            "⚠️ tmux is not installed", OutputType.WARNING, timestamp=False
        )
        return None

    # 查找或创建 jarvis session
    session_name = find_or_create_jarvis_session(force_create=True)
    if not session_name:
        PrettyOutput.print(
            "⚠️ Failed to find or create jarvis session",
            OutputType.WARNING,
            timestamp=False,
        )
        return None

    # 获取 session 的所有 window
    windows = list_session_windows(session_name)

    # 查找 panel 数量 < max_panes_per_window 的 window
    target_window_id = None
    for window in windows:
        window_id = window.split(":")[0].strip()
        pane_count = get_window_pane_count(session_name, window_id)
        if pane_count < max_panes_per_window:
            target_window_id = window_id
            PrettyOutput.print(
                f"ℹ️ Found window {window_id} with {pane_count} panes, reusing it",
                OutputType.INFO,
                timestamp=False,
            )
            break

    # 创建 panel 或 window
    if target_window_id:
        # 在现有 window 创建 panel
        pane_id = create_panel(
            session_name=session_name,
            window_id=target_window_id,
            initial_command=shell_command,
            split_direction="h",
        )
        if pane_id:
            PrettyOutput.print(
                f"✅ Successfully created panel {pane_id} in window {target_window_id}",
                OutputType.SUCCESS,
                timestamp=False,
            )
            return session_name
        else:
            PrettyOutput.print(
                f"❌ Failed to create panel in window {target_window_id} of session '{session_name}'",
                OutputType.ERROR,
                timestamp=False,
            )
            PrettyOutput.print(
                f"🔍 Command: {shell_command[:100]}{'...' if len(shell_command) > 100 else ''}",
                OutputType.INFO,
                timestamp=False,
            )
    else:
        # 创建新 window
        new_window_id = create_window(
            session_name=session_name, initial_command=shell_command
        )
        if new_window_id:
            window_index = new_window_id.split(":")[0].strip()
            PrettyOutput.print(
                f"ℹ️ Created new window {window_index} for command",
                OutputType.INFO,
                timestamp=False,
            )
            return session_name
        else:
            PrettyOutput.print(
                f"❌ Failed to create new window in session '{session_name}'",
                OutputType.ERROR,
                timestamp=False,
            )
            PrettyOutput.print(
                f"🔍 Command: {shell_command[:100]}{'...' if len(shell_command) > 100 else ''}",
                OutputType.INFO,
                timestamp=False,
            )

    return None


def _dispatch_to_existing_jarvis_session(
    task_arg: Optional[str], argv: list[str]
) -> bool:
    """将任务派发到现有 jarvis tmux session 的 panel 中执行。

    这是一个降级方案：当不在 tmux 环境中时，尝试找到 jarvis 创建的 session
    并在其中创建 panel 执行命令。如果未找到 session，则创建一个新的 session。

    Args:
        task_arg: 任务内容（已废弃，保留用于兼容）
        argv: 当前命令行参数（需要过滤 --dispatch）

    Returns:
        bool: 是否成功派发（True表示成功，False表示失败）
    """
    # 查找或创建 jarvis session
    session_name = find_or_create_jarvis_session(force_create=True)
    if not session_name:
        PrettyOutput.print(
            "❌ 无法找到或创建 tmux session",
            OutputType.ERROR,
            timestamp=False,
        )
        return False

    PrettyOutput.print(
        f"ℹ️ 使用 tmux session: {session_name}",
        OutputType.INFO,
        timestamp=False,
    )

    # 过滤 --dispatch/-d 参数，避免循环派发
    filtered_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--dispatch" or arg == "-d":
            continue
        elif arg.startswith("--dispatch=") or arg.startswith("-d="):
            continue
        else:
            filtered_argv.append(arg)

    # 构造命令字符串
    executable = sys.executable
    quoted_args = [shlex.quote(arg) for arg in filtered_argv]
    user_shell = os.environ.get("SHELL", "/bin/sh")
    cwd = os.getcwd()
    command = f'cd {shlex.quote(cwd)} && {executable} {" ".join(quoted_args)}; exec "{user_shell}"'

    # 获取 session 的当前窗口
    current_window = get_session_current_window(session_name)
    if not current_window:
        PrettyOutput.print(
            f"⚠️ 无法获取 session '{session_name}' 的当前窗口",
            OutputType.WARNING,
            timestamp=False,
        )
        return False

    # 在当前窗口创建 panel
    pane_id = create_panel(
        session_name=session_name,
        window_id=current_window,
        initial_command=command,
        split_direction="h",
    )
    if not pane_id:
        PrettyOutput.print(
            f"⚠️ 在窗口 '{current_window}' 中创建 panel 失败",
            OutputType.WARNING,
            timestamp=False,
        )
        # 降级方案：尝试创建新window
        PrettyOutput.print(
            "ℹ️ 尝试降级方案：创建新window...",
            OutputType.INFO,
            timestamp=False,
        )
        new_window_id = create_window(
            session_name=session_name,
            initial_command=command,
        )
        if new_window_id:
            window_index = new_window_id.split(":")[0].strip()
            PrettyOutput.print(
                f"✅ 任务已派发到新window {window_index}",
                OutputType.SUCCESS,
                timestamp=False,
            )
            return True
        else:
            PrettyOutput.print(
                "❌ 创建新window失败，无法派发任务",
                OutputType.ERROR,
                timestamp=False,
            )
            return False

    # panel创建成功
    PrettyOutput.print(
        f"✅ 任务已派发到 tmux session '{session_name}' 的 panel 中",
        OutputType.SUCCESS,
        timestamp=False,
    )
    return True
