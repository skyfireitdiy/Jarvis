# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, List

import typer
import yaml  # type: ignore
from prompt_toolkit import prompt  # type: ignore

from jarvis.jarvis_agent import (
    Agent,
    OutputType,
    PrettyOutput,
    get_multiline_input,
    origin_agent_system_prompt,
    user_confirm,
)
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Jarvis AI 助手")


def _load_tasks() -> Dict[str, str]:
    """Load tasks from .jarvis files in user home and current directory."""
    tasks: Dict[str, str] = {}

    # Check pre-command in data directory
    data_dir = get_data_dir()
    pre_command_path = os.path.join(data_dir, "pre-command")
    if os.path.exists(pre_command_path):
        print(f"🔍 从{pre_command_path}加载预定义任务...")
        try:
            with open(pre_command_path, "r", encoding="utf-8", errors="ignore") as f:
                user_tasks = yaml.safe_load(f)
            if isinstance(user_tasks, dict):
                for name, desc in user_tasks.items():
                    if desc:
                        tasks[str(name)] = str(desc)
            print(f"✅ 预定义任务加载完成 {pre_command_path}")
        except (yaml.YAMLError, OSError):
            print(f"❌ 预定义任务加载失败 {pre_command_path}")

    # Check .jarvis/pre-command in current directory
    pre_command_path = ".jarvis/pre-command"
    if os.path.exists(pre_command_path):
        abs_path = os.path.abspath(pre_command_path)
        print(f"🔍 从{abs_path}加载预定义任务...")
        try:
            with open(pre_command_path, "r", encoding="utf-8", errors="ignore") as f:
                local_tasks = yaml.safe_load(f)
            if isinstance(local_tasks, dict):
                for name, desc in local_tasks.items():
                    if desc:
                        tasks[str(name)] = str(desc)
            print(f"✅ 预定义任务加载完成 {pre_command_path}")
        except (yaml.YAMLError, OSError):
            print(f"❌ 预定义任务加载失败 {pre_command_path}")

    return tasks


def _select_task(tasks: Dict[str, str]) -> str:
    """Let user select a task from the list or skip. Returns task description if selected."""
    if not tasks:
        return ""

    task_names = list(tasks.keys())
    task_list = ["可用任务:"]
    for i, name in enumerate(task_names, 1):
        task_list.append(f"[{i}] {name}")
    task_list.append("[0] 跳过预定义任务")
    PrettyOutput.print("\n".join(task_list), OutputType.INFO)

    while True:
        try:
            choice_str = prompt("\n请选择一个任务编号（0 跳过预定义任务）：").strip()
            if not choice_str:
                return ""

            choice = int(choice_str)
            if choice == 0:
                return ""
            if 1 <= choice <= len(task_names):
                selected_task = tasks[task_names[choice - 1]]
                PrettyOutput.print(f"将要执行任务:\n {selected_task}", OutputType.INFO)
                # 询问是否需要补充信息
                need_additional = user_confirm(
                    "需要为此任务添加补充信息吗？", default=False
                )
                if need_additional:
                    additional_input = get_multiline_input("请输入补充信息：")
                    if additional_input:
                        selected_task = (
                            f"{selected_task}\n\n补充信息:\n{additional_input}"
                        )
                return selected_task
            PrettyOutput.print(
                "无效的选择。请选择列表中的一个号码。", OutputType.WARNING
            )

        except (KeyboardInterrupt, EOFError):
            return ""
        except ValueError as val_err:
            PrettyOutput.print(f"选择任务失败: {str(val_err)}", OutputType.ERROR)


def _handle_edit_mode(edit: bool, config_file: Optional[str]) -> None:
    """If edit flag is set, open config file in editor and exit."""
    if not edit:
        return

    config_file_path = (
        Path(config_file)
        if config_file
        else Path(os.path.expanduser("~/.jarvis/config.yaml"))
    )
    # 根据操作系统选择合适的编辑器
    import platform

    if platform.system() == "Windows":
        # 优先级：终端工具 -> 代码编辑器 -> 通用文本编辑器
        editors = ["nvim", "vim", "nano", "code", "notepad++", "notepad"]
    else:
        # 优先级：终端工具 -> 代码编辑器 -> 通用文本编辑器
        editors = ["nvim", "vim", "vi", "nano", "emacs", "code", "gedit", "kate"]

    editor = next((e for e in editors if shutil.which(e)), None)

    if editor:
        try:
            subprocess.run([editor, str(config_file_path)], check=True)
            raise typer.Exit(code=0)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            PrettyOutput.print(f"Failed to open editor: {e}", OutputType.ERROR)
            raise typer.Exit(code=1)
    else:
        PrettyOutput.print(
            f"No suitable editor found. Tried: {', '.join(editors)}", OutputType.ERROR
        )
        raise typer.Exit(code=1)


def _initialize_agent(
    llm_type: str,
    model_group: Optional[str],
    tool_group: Optional[str],
    restore_session: bool,
) -> Agent:
    """Initialize the agent and restore session if requested."""
    # 如果提供了 tool_group 参数，设置到配置中
    if tool_group:
        from jarvis.jarvis_utils.config import set_config

        set_config("JARVIS_TOOL_GROUP", tool_group)

    agent = Agent(
        system_prompt=origin_agent_system_prompt,
        llm_type=llm_type,
        model_group=model_group,
        input_handler=[shell_input_handler, builtin_input_handler],
        output_handler=[ToolRegistry()],  # type: ignore
        need_summary=False,
    )

    # 尝试恢复会话
    if restore_session:
        if agent.restore_session():
            PrettyOutput.print("会话已成功恢复。", OutputType.SUCCESS)
        else:
            PrettyOutput.print("无法恢复会话。", OutputType.WARNING)
    return agent


def _get_and_run_task(agent: Agent, task_content: Optional[str] = None) -> None:
    """Get task from various sources and run it."""
    # 优先处理命令行直接传入的任务
    if task_content:
        agent.run(task_content)
        raise typer.Exit(code=0)

    if agent.first:
        tasks = _load_tasks()
        if tasks and (selected_task := _select_task(tasks)):
            PrettyOutput.print(f"开始执行任务: \n{selected_task}", OutputType.INFO)
            agent.run(selected_task)
            raise typer.Exit(code=0)

    user_input = get_multiline_input("请输入你的任务（输入空行退出）:")
    if user_input:
        agent.run(user_input)
    raise typer.Exit(code=0)


def _parse_selection(selection_str: str, max_value: int) -> List[int]:
    """解析用户输入的选择字符串，支持逗号分隔和范围选择

    例如: "1,2,3,4-9,20" -> [1, 2, 3, 4, 5, 6, 7, 8, 9, 20]
    """
    selected: set[int] = set()
    parts = selection_str.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            # 处理范围选择
            try:
                start_str, end_str = part.split("-")
                start_num = int(start_str.strip())
                end_num = int(end_str.strip())
                if 1 <= start_num <= max_value and 1 <= end_num <= max_value:
                    selected.update(range(start_num, end_num + 1))
            except ValueError:
                continue
        else:
            # 处理单个数字
            try:
                num = int(part)
                if 1 <= num <= max_value:
                    selected.add(num)
            except ValueError:
                continue

    return sorted(list(selected))


def _handle_share_tool(config_file: Optional[str] = None) -> None:
    """处理工具分享功能"""
    from jarvis.jarvis_utils.config import (
        get_central_tool_repo,
        get_data_dir,
    )
    import glob
    import shutil

    # 获取中心工具仓库配置
    central_repo = get_central_tool_repo()
    if not central_repo:
        PrettyOutput.print(
            "错误：未配置中心工具仓库（JARVIS_CENTRAL_TOOL_REPO）",
            OutputType.ERROR,
        )
        PrettyOutput.print("请在配置文件中设置中心工具仓库的Git地址", OutputType.INFO)
        raise typer.Exit(code=1)

    # 克隆或更新中心工具仓库
    central_repo_path = os.path.join(get_data_dir(), "central_tool_repo")
    if not os.path.exists(central_repo_path):
        PrettyOutput.print(f"正在克隆中心工具仓库...", OutputType.INFO)
        subprocess.run(["git", "clone", central_repo, central_repo_path], check=True)
    else:
        PrettyOutput.print(f"正在更新中心工具仓库...", OutputType.INFO)
        # 检查是否是空仓库
        try:
            # 先尝试获取远程分支信息
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin"],
                cwd=central_repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            # 如果有远程分支，执行pull
            if result.stdout.strip():
                subprocess.run(["git", "pull"], cwd=central_repo_path, check=True)
            else:
                PrettyOutput.print(
                    "中心工具仓库是空的，将初始化为新仓库", OutputType.INFO
                )
        except subprocess.CalledProcessError:
            # 如果命令失败，可能是网络问题或其他错误
            PrettyOutput.print("无法连接到远程仓库，将跳过更新", OutputType.WARNING)

    # 获取中心仓库中已有的工具文件名
    existing_tools = set()
    for filepath in glob.glob(os.path.join(central_repo_path, "*.py")):
        existing_tools.add(os.path.basename(filepath))

    # 只从数据目录的tools目录获取工具
    local_tools_dir = os.path.join(get_data_dir(), "tools")
    if not os.path.exists(local_tools_dir):
        PrettyOutput.print(
            f"本地工具目录不存在: {local_tools_dir}",
            OutputType.WARNING,
        )
        raise typer.Exit(code=0)

    # 收集本地工具文件（排除已存在的）
    tool_files = []
    for filepath in glob.glob(os.path.join(local_tools_dir, "*.py")):
        filename = os.path.basename(filepath)
        # 跳过__init__.py和已存在的文件
        if filename == "__init__.py" or filename in existing_tools:
            continue

        # 尝试获取工具名称（通过简单解析）
        tool_name = filename[:-3]  # 移除.py后缀
        tool_files.append(
            {
                "path": filepath,
                "filename": filename,
                "tool_name": tool_name,
            }
        )

    if not tool_files:
        PrettyOutput.print(
            "没有找到新的工具文件（所有工具可能已存在于中心仓库）",
            OutputType.WARNING,
        )
        raise typer.Exit(code=0)

    # 显示可选的工具
    tool_list = ["\n可分享的工具（已排除中心仓库中已有的）："]
    for i, tool in enumerate(tool_files, 1):
        tool_list.append(f"[{i}] {tool['tool_name']} ({tool['filename']})")

    # 一次性打印所有工具
    PrettyOutput.print("\n".join(tool_list), OutputType.INFO)

    # 让用户选择要分享的工具
    while True:
        try:
            choice_str = prompt(
                "\n请选择要分享的工具编号（支持格式: 1,2,3,4-9,20 或 all）："
            ).strip()
            if choice_str == "0":
                raise typer.Exit(code=0)

            selected_tools = []
            if choice_str.lower() == "all":
                selected_tools = tool_files
            else:
                selected_indices = _parse_selection(choice_str, len(tool_files))
                if not selected_indices:
                    PrettyOutput.print("无效的选择", OutputType.WARNING)
                    continue
                selected_tools = [tool_files[i - 1] for i in selected_indices]

            # 确认操作
            share_list = [
                "\n将要分享以下工具到中心仓库（注意：文件将被移动而非复制）："
            ]
            for tool in selected_tools:
                share_list.append(f"- {tool['tool_name']} ({tool['filename']})")
            PrettyOutput.print("\n".join(share_list), OutputType.WARNING)

            if not user_confirm("确认移动这些工具到中心仓库吗？（原文件将被删除）"):
                continue

            # 移动选中的工具到中心仓库
            moved_list = []
            for tool in selected_tools:
                src_file = tool["path"]
                dst_file = os.path.join(central_repo_path, tool["filename"])
                shutil.move(src_file, dst_file)  # 使用move而不是copy
                moved_list.append(f"已移动: {tool['tool_name']}")

            # 一次性显示所有移动结果
            if moved_list:
                PrettyOutput.print("\n".join(moved_list), OutputType.SUCCESS)

            # 提交并推送更改
            PrettyOutput.print("\n正在提交更改...", OutputType.INFO)
            subprocess.run(["git", "add", "."], cwd=central_repo_path, check=True)

            commit_msg = f"Add {len(selected_tools)} tool(s) from local collection"
            subprocess.run(
                ["git", "commit", "-m", commit_msg], cwd=central_repo_path, check=True
            )

            PrettyOutput.print("正在推送到远程仓库...", OutputType.INFO)
            # 检查是否需要设置上游分支（空仓库的情况）
            try:
                # 先尝试普通推送
                subprocess.run(["git", "push"], cwd=central_repo_path, check=True)
            except subprocess.CalledProcessError:
                # 如果失败，可能是空仓库，尝试设置上游分支
                try:
                    subprocess.run(
                        ["git", "push", "-u", "origin", "main"],
                        cwd=central_repo_path,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    # 如果main分支不存在，尝试master分支
                    subprocess.run(
                        ["git", "push", "-u", "origin", "master"],
                        cwd=central_repo_path,
                        check=True,
                    )

            PrettyOutput.print("\n工具已成功分享到中心仓库！", OutputType.SUCCESS)
            PrettyOutput.print(
                f"原文件已从 {local_tools_dir} 移动到中心仓库", OutputType.INFO
            )
            break

        except ValueError:
            PrettyOutput.print("请输入有效的数字", OutputType.WARNING)
        except subprocess.CalledProcessError as e:
            PrettyOutput.print(f"Git操作失败: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)
        except Exception as e:
            PrettyOutput.print(f"分享工具时出错: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)


def _handle_share_methodology(config_file: Optional[str] = None) -> None:
    """处理方法论分享功能"""
    from jarvis.jarvis_utils.config import (
        get_central_methodology_repo,
        get_methodology_dirs,
        get_data_dir,
    )
    import glob
    import json
    import shutil

    # 获取中心方法论仓库配置
    central_repo = get_central_methodology_repo()
    if not central_repo:
        PrettyOutput.print(
            "错误：未配置中心方法论仓库（JARVIS_CENTRAL_METHODOLOGY_REPO）",
            OutputType.ERROR,
        )
        PrettyOutput.print("请在配置文件中设置中心方法论仓库的Git地址", OutputType.INFO)
        raise typer.Exit(code=1)

    # 克隆或更新中心方法论仓库
    central_repo_path = os.path.join(get_data_dir(), "central_methodology_repo")
    if not os.path.exists(central_repo_path):
        PrettyOutput.print(f"正在克隆中心方法论仓库...", OutputType.INFO)
        subprocess.run(["git", "clone", central_repo, central_repo_path], check=True)
    else:
        PrettyOutput.print(f"正在更新中心方法论仓库...", OutputType.INFO)
        # 检查是否是空仓库
        try:
            # 先尝试获取远程分支信息
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin"],
                cwd=central_repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            # 如果有远程分支，执行pull
            if result.stdout.strip():
                subprocess.run(["git", "pull"], cwd=central_repo_path, check=True)
            else:
                PrettyOutput.print(
                    "中心方法论仓库是空的，将初始化为新仓库", OutputType.INFO
                )
        except subprocess.CalledProcessError:
            # 如果命令失败，可能是网络问题或其他错误
            PrettyOutput.print("无法连接到远程仓库，将跳过更新", OutputType.WARNING)

    # 获取中心仓库中已有的方法论
    existing_methodologies = {}  # 改为字典，存储 problem_type -> content 的映射
    for filepath in glob.glob(os.path.join(central_repo_path, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                methodology = json.load(f)
                problem_type = methodology.get("problem_type", "")
                content = methodology.get("content", "")
                if problem_type and content:
                    existing_methodologies[problem_type] = content
        except Exception:
            pass

    # 获取所有方法论目录
    from jarvis.jarvis_utils.methodology import _get_methodology_directory

    methodology_dirs = [_get_methodology_directory()] + get_methodology_dirs()

    # 收集所有方法论文件（排除中心仓库目录和已存在的方法论）
    all_methodologies = {}
    methodology_files = []
    seen_problem_types = set()  # 用于去重

    for directory in set(methodology_dirs):
        # 跳过中心仓库目录
        if os.path.abspath(directory) == os.path.abspath(central_repo_path):
            continue

        if not os.path.isdir(directory):
            continue

        for filepath in glob.glob(os.path.join(directory, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    methodology = json.load(f)
                    problem_type = methodology.get("problem_type", "")
                    content = methodology.get("content", "")
                    # 基于内容判断是否已存在于中心仓库
                    is_duplicate = False
                    if problem_type in existing_methodologies:
                        # 如果problem_type相同，比较内容
                        if (
                            content.strip()
                            == existing_methodologies[problem_type].strip()
                        ):
                            is_duplicate = True

                    # 排除已存在于中心仓库的方法论（基于内容），以及本地重复的方法论
                    if (
                        problem_type
                        and content
                        and not is_duplicate
                        and problem_type not in seen_problem_types
                    ):
                        methodology_files.append(
                            {
                                "path": filepath,
                                "problem_type": problem_type,
                                "directory": directory,
                            }
                        )
                        all_methodologies[problem_type] = methodology
                        seen_problem_types.add(problem_type)
            except Exception:
                pass

    if not methodology_files:
        PrettyOutput.print(
            "没有找到新的方法论文件（所有方法论可能已存在于中心仓库）",
            OutputType.WARNING,
        )
        raise typer.Exit(code=0)

    # 显示可选的方法论
    methodology_list = ["\n可分享的方法论（已排除中心仓库中已有的）："]
    for i, meth in enumerate(methodology_files, 1):
        dir_name = os.path.basename(meth["directory"])
        methodology_list.append(f"[{i}] {meth['problem_type']} (来自: {dir_name})")

    # 一次性打印所有方法论
    PrettyOutput.print("\n".join(methodology_list), OutputType.INFO)

    # 让用户选择要分享的方法论
    while True:
        try:
            choice_str = prompt(
                "\n请选择要分享的方法论编号（支持格式: 1,2,3,4-9,20 或 all）："
            ).strip()
            if choice_str == "0":
                raise typer.Exit(code=0)

            selected_methodologies = []
            if choice_str.lower() == "all":
                selected_methodologies = methodology_files
            else:
                selected_indices = _parse_selection(choice_str, len(methodology_files))
                if not selected_indices:
                    PrettyOutput.print("无效的选择", OutputType.WARNING)
                    continue
                selected_methodologies = [
                    methodology_files[i - 1] for i in selected_indices
                ]

            # 确认操作
            share_list = ["\n将要分享以下方法论到中心仓库："]
            for meth in selected_methodologies:
                share_list.append(f"- {meth['problem_type']}")
            PrettyOutput.print("\n".join(share_list), OutputType.INFO)

            if not user_confirm("确认分享这些方法论吗？"):
                continue

            # 复制选中的方法论到中心仓库
            copied_list = []
            for meth in selected_methodologies:
                src_file = meth["path"]
                dst_file = os.path.join(central_repo_path, os.path.basename(src_file))
                shutil.copy2(src_file, dst_file)
                copied_list.append(f"已复制: {meth['problem_type']}")

            # 一次性显示所有复制结果
            if copied_list:
                PrettyOutput.print("\n".join(copied_list), OutputType.SUCCESS)

            # 提交并推送更改
            PrettyOutput.print("\n正在提交更改...", OutputType.INFO)
            subprocess.run(["git", "add", "."], cwd=central_repo_path, check=True)

            commit_msg = f"Add {len(selected_methodologies)} methodology(ies) from local collection"
            subprocess.run(
                ["git", "commit", "-m", commit_msg], cwd=central_repo_path, check=True
            )

            PrettyOutput.print("正在推送到远程仓库...", OutputType.INFO)
            # 检查是否需要设置上游分支（空仓库的情况）
            try:
                # 先尝试普通推送
                subprocess.run(["git", "push"], cwd=central_repo_path, check=True)
            except subprocess.CalledProcessError:
                # 如果失败，可能是空仓库，尝试设置上游分支
                try:
                    subprocess.run(
                        ["git", "push", "-u", "origin", "main"],
                        cwd=central_repo_path,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    # 如果main分支不存在，尝试master分支
                    subprocess.run(
                        ["git", "push", "-u", "origin", "master"],
                        cwd=central_repo_path,
                        check=True,
                    )

            PrettyOutput.print("\n方法论已成功分享到中心仓库！", OutputType.SUCCESS)
            break

        except ValueError:
            PrettyOutput.print("请输入有效的数字", OutputType.WARNING)
        except subprocess.CalledProcessError as e:
            PrettyOutput.print(f"Git操作失败: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)
        except Exception as e:
            PrettyOutput.print(f"分享方法论时出错: {str(e)}", OutputType.ERROR)
            raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def run_cli(
    ctx: typer.Context,
    llm_type: str = typer.Option(
        "normal",
        "--llm_type",
        help="使用的LLM类型，可选值：'normal'（普通）或 'thinking'（思考模式）",
    ),
    task: Optional[str] = typer.Option(
        None, "-t", "--task", help="从命令行直接输入任务内容"
    ),
    model_group: Optional[str] = typer.Option(
        None, "--llm_group", help="使用的模型组，覆盖配置文件中的设置"
    ),
    tool_group: Optional[str] = typer.Option(
        None, "--tool_group", help="使用的工具组，覆盖配置文件中的设置"
    ),
    config_file: Optional[str] = typer.Option(
        None, "-f", "--config", help="自定义配置文件路径"
    ),
    restore_session: bool = typer.Option(
        False,
        "--restore-session",
        help="从 .jarvis/saved_session.json 恢复会话",
    ),
    edit: bool = typer.Option(False, "-e", "--edit", help="编辑配置文件"),
    share_methodology: bool = typer.Option(
        False, "--share-methodology", help="分享本地方法论到中心方法论仓库"
    ),
    share_tool: bool = typer.Option(
        False, "--share-tool", help="分享本地工具到中心工具仓库"
    ),
) -> None:
    """Jarvis AI assistant command-line interface."""
    if ctx.invoked_subcommand is not None:
        return

    _handle_edit_mode(edit, config_file)

    # 处理方法论分享
    if share_methodology:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        _handle_share_methodology(config_file)
        raise typer.Exit(code=0)

    # 处理工具分享
    if share_tool:
        init_env("", config_file=config_file)  # 初始化配置但不显示欢迎信息
        _handle_share_tool(config_file)
        raise typer.Exit(code=0)

    init_env(
        "欢迎使用 Jarvis AI 助手，您的智能助理已准备就绪！", config_file=config_file
    )

    try:
        agent = _initialize_agent(llm_type, model_group, tool_group, restore_session)
        _get_and_run_task(agent, task)
    except typer.Exit:
        raise
    except Exception as err:  # pylint: disable=broad-except
        PrettyOutput.print(f"初始化错误: {str(err)}", OutputType.ERROR)
        raise typer.Exit(code=1)


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()
