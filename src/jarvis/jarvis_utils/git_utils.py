# -*- coding: utf-8 -*-
"""
Git工具模块
该模块提供了与Git仓库交互的工具。
包含以下功能：
- 查找Git仓库的根目录
- 检查是否有未提交的更改
- 获取两个哈希值之间的提交历史
- 获取最新提交的哈希值
- 从Git差异中提取修改的行范围
"""
import datetime
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Set, Tuple

from jarvis.jarvis_utils.config import get_data_dir, is_confirm_before_apply_patch
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.utils import is_rag_installed


def find_git_root_and_cd(start_dir: str = ".") -> str:
    """
    切换到给定路径的Git根目录，如果不是Git仓库则初始化。

    参数:
        start_dir (str): 起始查找目录，默认为当前目录。

    返回:
        str: Git仓库根目录路径。如果目录不是Git仓库，则会初始化一个新的Git仓库。
    """
    os.chdir(start_dir)
    try:
        git_root = os.popen("git rev-parse --show-toplevel").read().strip()
        if not git_root:
            subprocess.run(["git", "init"], check=True)
            git_root = os.path.abspath(".")
    except subprocess.CalledProcessError:
        # 如果不是Git仓库，初始化一个新的
        subprocess.run(["git", "init"], check=True)
        git_root = os.path.abspath(".")
    os.chdir(git_root)
    return git_root


def has_uncommitted_changes() -> bool:
    """检查Git仓库中是否有未提交的更改

    返回:
        bool: 如果有未提交的更改返回True，否则返回False
    """
    # 静默添加所有更改
    subprocess.run(
        ["git", "add", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # 检查工作目录更改
    working_changes = (
        subprocess.run(
            ["git", "diff", "--exit-code"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    )

    # 检查暂存区更改
    staged_changes = (
        subprocess.run(
            ["git", "diff", "--cached", "--exit-code"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    )

    # 静默重置更改
    subprocess.run(
        ["git", "reset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    return working_changes or staged_changes


def get_commits_between(start_hash: str, end_hash: str) -> List[Tuple[str, str]]:
    """获取两个提交哈希值之间的提交列表

    参数：
        start_hash: 起始提交哈希值（不包含）
        end_hash: 结束提交哈希值（包含）

    返回：
        List[Tuple[str, str]]: (提交哈希值, 提交信息) 元组列表
    """
    try:
        # 使用git log和pretty格式获取哈希值和信息
        result = subprocess.run(
            ["git", "log", f"{start_hash}..{end_hash}", "--pretty=format:%H|%s"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,  # 禁用自动文本解码
        )
        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")
            PrettyOutput.print(f"获取commit历史失败: {error_msg}", OutputType.ERROR)
            return []

        output = result.stdout.decode("utf-8", errors="replace")
        commits = []
        for line in output.splitlines():
            if "|" in line:
                commit_hash, message = line.split("|", 1)
                commits.append((commit_hash, message))
        return commits

    except Exception as e:
        PrettyOutput.print(f"获取commit历史异常: {str(e)}", OutputType.ERROR)
        return []


# 修改后的获取差异函数


def get_diff() -> str:
    """使用git获取工作区差异，包括修改和新增的文件内容

    返回:
        str: 差异内容或错误信息
    """
    try:
        # 检查是否为空仓库
        head_check = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        confirm_add_new_files()
        if head_check.returncode != 0:
            # 空仓库情况，直接获取工作区差异
            result = subprocess.run(
                ["git", "diff"], capture_output=True, text=False, check=True
            )
        else:
            # 暂存新增文件
            subprocess.run(["git", "add", "-N", "."], check=True)

            # 获取所有差异（包括新增文件）
            result = subprocess.run(
                ["git", "diff", "HEAD"], capture_output=True, text=False, check=True
            )

            # 重置暂存区
            subprocess.run(["git", "reset"], check=True)

        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return result.stdout.decode("utf-8", errors="replace")

    except subprocess.CalledProcessError as e:
        return f"获取差异失败: {str(e)}"
    except Exception as e:
        return f"发生意外错误: {str(e)}"


def revert_file(filepath: str) -> None:
    """增强版git恢复，处理新文件"""
    import subprocess

    try:
        # 检查文件是否在版本控制中
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", filepath],
            stderr=subprocess.PIPE,
            text=False,  # 禁用自动文本解码
        )
        if result.returncode == 0:
            subprocess.run(["git", "checkout", "HEAD", "--", filepath], check=True)
        else:
            if os.path.exists(filepath):
                os.remove(filepath)
        subprocess.run(["git", "clean", "-f", "--", filepath], check=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        PrettyOutput.print(f"恢复文件失败: {error_msg}", OutputType.ERROR)


# 修改后的恢复函数


def revert_change() -> None:
    """恢复所有未提交的修改到HEAD状态"""
    import subprocess

    try:
        # 检查是否为空仓库
        head_check = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        if head_check.returncode == 0:
            subprocess.run(["git", "reset", "--hard", "HEAD"], check=True)
        subprocess.run(["git", "clean", "-fd"], check=True)
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(f"恢复更改失败: {str(e)}", OutputType.ERROR)


def handle_commit_workflow() -> bool:
    """Handle the git commit workflow and return the commit details.

    Returns:
        bool: 提交是否成功
    """
    if is_confirm_before_apply_patch() and not user_confirm(
        "是否要提交代码？", default=True
    ):
        revert_change()
        return False

    import subprocess

    try:
        confirm_add_new_files()

        if not has_uncommitted_changes():
            return False

        # 获取当前分支的提交总数
        commit_result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True
        )
        if commit_result.returncode != 0:
            return False

        commit_count = int(commit_result.stdout.strip())

        # 暂存所有修改
        subprocess.run(["git", "add", "."], check=True)

        # 提交变更
        subprocess.run(
            ["git", "commit", "-m", f"CheckPoint #{commit_count + 1}"], check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_latest_commit_hash() -> str:
    """获取当前Git仓库的最新提交哈希值

    返回：
        str: 提交哈希值，如果不在Git仓库、空仓库或发生错误则返回空字符串
    """
    try:
        # 首先检查是否存在HEAD引用
        head_check = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        if head_check.returncode != 0:
            return ""  # 空仓库或无效HEAD

        # 获取HEAD的完整哈希值
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        return (
            result.stdout.decode("utf-8", errors="replace").strip()
            if result.returncode == 0
            else ""
        )
    except Exception:
        return ""


def get_modified_line_ranges() -> Dict[str, List[Tuple[int, int]]]:
    """从Git差异中获取所有更改文件的修改行范围

    返回：
        字典，将文件路径映射到包含修改部分的（起始行, 结束行）范围元组。
        行号从1开始。
    """
    # 获取所有文件的Git差异
    diff_output = os.popen("git show").read()

    # 解析差异以获取修改的文件及其行范围
    result: Dict[str, List[Tuple[int, int]]] = {}
    current_file = None

    for line in diff_output.splitlines():
        # 匹配类似"+++ b/path/to/file"的行
        file_match = re.match(r"^\+\+\+ b/(.*)", line)
        if file_match:
            current_file = file_match.group(1)
            continue

        # 匹配类似"@@ -100,5 +100,7 @@"的行，其中+部分显示新行
        range_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if range_match and current_file:
            start_line = int(range_match.group(1))  # 保持从1开始
            line_count = int(range_match.group(2)) if range_match.group(2) else 1
            end_line = start_line + line_count - 1
            if current_file not in result:
                result[current_file] = []
            result[current_file].append((start_line, end_line))

    return result


def is_file_in_git_repo(filepath: str) -> bool:
    """检查文件是否在当前Git仓库中"""
    import subprocess

    try:
        # 获取Git仓库根目录
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
        ).stdout.strip()

        # 检查文件路径是否在仓库根目录下
        return os.path.abspath(filepath).startswith(os.path.abspath(repo_root))
    except:
        return False


def check_and_update_git_repo(repo_path: str) -> bool:
    """检查并更新git仓库

    参数:
        repo_path: 仓库路径

    返回:
        bool: 是否执行了更新
    """
    # 检查上次检查日期
    last_check_file = os.path.join(get_data_dir(), "last_git_check")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if os.path.exists(last_check_file):
        with open(last_check_file, "r") as f:
            last_check_date = f.read().strip()
        if last_check_date == today_str:
            return False

    curr_dir = os.path.abspath(os.getcwd())
    git_root = find_git_root_and_cd(repo_path)
    if git_root is None:
        return False

    try:
        # 检查是否有未提交的修改
        if has_uncommitted_changes():
            return False

        # 获取远程tag更新
        subprocess.run(["git", "fetch", "--tags"], cwd=git_root, check=True)
        # 获取最新本地tag
        local_tag_result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=git_root,
            capture_output=True,
            text=True,
        )
        # 获取最新远程tag
        remote_tag_result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", "origin"],
            cwd=git_root,
            capture_output=True,
            text=True,
        )
        if remote_tag_result.returncode == 0:
            # 提取最新的tag名称
            tags = [ref.split("/")[-1] for ref in remote_tag_result.stdout.splitlines()]
            tags = sorted(
                tags,
                key=lambda x: [
                    int(i) if i.isdigit() else i for i in re.split(r"([0-9]+)", x)
                ],
            )
            remote_tag = tags[-1] if tags else ""
            remote_tag_result.stdout = remote_tag

        if (
            local_tag_result.returncode == 0
            and remote_tag_result.returncode == 0
            and local_tag_result.stdout.strip() != remote_tag_result.stdout.strip()
        ):
            PrettyOutput.print(
                f"检测到新版本tag {remote_tag_result.stdout.strip()}，正在更新Jarvis...",
                OutputType.INFO,
            )
            subprocess.run(
                ["git", "checkout", remote_tag_result.stdout.strip()],
                cwd=git_root,
                check=True,
            )
            PrettyOutput.print(
                f"Jarvis已更新到tag {remote_tag_result.stdout.strip()}",
                OutputType.SUCCESS,
            )

            # 执行pip安装更新代码
            try:
                PrettyOutput.print("正在安装更新后的代码...", OutputType.INFO)

                # 检查是否在虚拟环境中
                in_venv = hasattr(sys, "real_prefix") or (
                    hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
                )

                is_uv_env = False
                if in_venv:
                    # 检查是否在uv创建的虚拟环境内
                    if sys.platform == "win32":
                        uv_path = os.path.join(sys.prefix, "Scripts", "uv.exe")
                    else:
                        uv_path = os.path.join(sys.prefix, "bin", "uv")
                    if os.path.exists(uv_path):
                        is_uv_env = True

                # 根据环境选择安装命令
                # 检测是否安装了 RAG 特性（更精确）
                rag_installed = is_rag_installed()

                # 根据环境和 RAG 特性选择安装命令
                if rag_installed:
                    if is_uv_env:
                        install_cmd = ["uv", "pip", "install", "-e", ".[rag]"]
                    else:
                        install_cmd = [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "-e",
                            ".[rag]",
                        ]
                else:
                    if is_uv_env:
                        install_cmd = ["uv", "pip", "install", "-e", "."]
                    else:
                        install_cmd = [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "-e",
                            ".",
                        ]

                # 尝试安装
                result = subprocess.run(
                    install_cmd, cwd=git_root, capture_output=True, text=True
                )

                if result.returncode == 0:
                    PrettyOutput.print("代码更新安装成功", OutputType.SUCCESS)
                    return True

                # 处理权限错误
                error_msg = result.stderr.strip()
                if not in_venv and (
                    "Permission denied" in error_msg or "not writeable" in error_msg
                ):
                    if user_confirm(
                        "检测到权限问题，是否尝试用户级安装(--user)？", True
                    ):
                        user_result = subprocess.run(
                            install_cmd + ["--user"],
                            cwd=git_root,
                            capture_output=True,
                            text=True,
                        )
                        if user_result.returncode == 0:
                            PrettyOutput.print("用户级代码安装成功", OutputType.SUCCESS)
                            return True
                        error_msg = user_result.stderr.strip()

                PrettyOutput.print(f"代码安装失败: {error_msg}", OutputType.ERROR)
                return False
            except Exception as e:
                PrettyOutput.print(
                    f"安装过程中发生意外错误: {str(e)}", OutputType.ERROR
                )
                return False
        # 更新检查日期文件
        with open(last_check_file, "w") as f:
            f.write(today_str)
        return False
    except Exception as e:
        PrettyOutput.print(f"Git仓库更新检查失败: {e}", OutputType.WARNING)
        return False
    finally:
        os.chdir(curr_dir)


def get_diff_file_list() -> List[str]:
    """获取HEAD到当前变更的文件列表，包括修改和新增的文件

    返回:
        List[str]: 修改和新增的文件路径列表
    """
    try:
        confirm_add_new_files()

        # 暂存新增文件
        subprocess.run(["git", "add", "-N", "."], check=True)

        # 获取所有差异文件（包括新增文件）
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True
        )

        # 重置暂存区
        subprocess.run(["git", "reset"], check=True)

        if result.returncode != 0:
            PrettyOutput.print(
                f"获取差异文件列表失败: {result.stderr}", OutputType.ERROR
            )
            return []

        return [f for f in result.stdout.splitlines() if f]

    except subprocess.CalledProcessError as e:
        PrettyOutput.print(f"获取差异文件列表失败: {str(e)}", OutputType.ERROR)
        return []
    except Exception as e:
        PrettyOutput.print(f"获取差异文件列表异常: {str(e)}", OutputType.ERROR)
        return []


def get_recent_commits_with_files() -> List[Dict[str, Any]]:
    """获取最近5次提交的commit信息和文件清单

    返回:
        List[Dict[str, Any]]: 包含commit信息和文件清单的字典列表，格式为:
            [
                {
                    'hash': str,
                    'message': str,
                    'author': str,
                    'date': str,
                    'files': List[str]  # 修改的文件列表 (最多20个文件)
                },
                ...
            ]
            失败时返回空列表
    """
    try:
        # 获取当前git用户名
        current_author = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
        ).stdout.strip()

        # 获取当前用户最近5次提交的基本信息
        result = subprocess.run(
            [
                "git",
                "log",
                "-5",
                "--author=" + current_author,
                "--pretty=format:%H%n%s%n%an%n%ad",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or result.stdout is None:
            return []

        # 解析提交信息
        commits: List[Dict[str, Any]] = []
        lines = result.stdout.splitlines()
        for i in range(0, len(lines), 4):
            if i + 3 >= len(lines):
                break
            commit: Dict[str, Any] = {
                "hash": lines[i],
                "message": lines[i + 1],
                "author": lines[i + 2],
                "date": lines[i + 3],
                "files": [],
            }
            commits.append(commit)

        # 获取每个提交的文件修改清单
        for commit in commits:
            files_result = subprocess.run(
                ["git", "show", "--name-only", "--pretty=format:", commit["hash"]],
                capture_output=True,
                text=True,
            )
            if files_result.returncode == 0:
                file_lines = files_result.stdout.splitlines()
                unique_files: Set[str] = set(filter(None, file_lines))
                commit["files"] = list(unique_files)[:20]  # type: ignore[list-item] # 限制最多20个文件

        return commits

    except subprocess.CalledProcessError:
        return []


def _get_new_files() -> List[str]:
    """获取新增文件列表"""
    return subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


def confirm_add_new_files() -> None:
    """确认新增文件、代码行数和二进制文件"""

    def _get_added_lines() -> int:
        """获取新增代码行数"""
        diff_stats = subprocess.run(
            ["git", "diff", "--numstat"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()

        added_lines = 0
        for stat in diff_stats:
            parts = stat.split()
            if len(parts) >= 1:
                try:
                    added_lines += int(parts[0])
                except ValueError:
                    pass
        return added_lines

    def _get_binary_files(files: List[str]) -> List[str]:
        """从文件列表中识别二进制文件"""
        binary_files = []
        for file in files:
            try:
                with open(file, "rb") as f:
                    if b"\x00" in f.read(1024):
                        binary_files.append(file)
            except (IOError, PermissionError):
                continue
        return binary_files

    def _check_conditions(
        new_files: List[str], added_lines: int, binary_files: List[str]
    ) -> bool:
        """检查各种条件并打印提示信息"""
        need_confirm = False
        output_lines = []

        if len(new_files) > 20:
            output_lines.append(f"检测到{len(new_files)}个新增文件(选择N将重新检测)")
            output_lines.append("新增文件列表:")
            output_lines.extend(f"  - {file}" for file in new_files)
            need_confirm = True

        if added_lines > 500:
            output_lines.append(f"检测到{added_lines}行新增代码(选择N将重新检测)")
            need_confirm = True

        if binary_files:
            output_lines.append(
                f"检测到{len(binary_files)}个二进制文件(选择N将重新检测)"
            )
            output_lines.append("二进制文件列表:")
            output_lines.extend(f"  - {file}" for file in binary_files)
            need_confirm = True

        if output_lines:
            PrettyOutput.print(
                "\n".join(output_lines),
                OutputType.WARNING if need_confirm else OutputType.INFO,
            )

        return need_confirm

    while True:
        new_files = _get_new_files()
        added_lines = _get_added_lines()
        binary_files = _get_binary_files(new_files)

        if not _check_conditions(new_files, added_lines, binary_files):
            break

        if not user_confirm(
            "是否要添加这些变更（如果不需要请修改.gitignore文件以忽略不需要的文件）？",
            False,
        ):
            continue

        break
