"""
方法论管理模块
该模块提供了加载和搜索方法论的实用工具。
包含以下功能：
- 加载和处理方法论数据
- 生成方法论临时文件
- 上传方法论文件到大模型
"""

import json
import os
import threading

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from jarvis.jarvis_utils.globals import console
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_central_methodology_repo
from jarvis.jarvis_utils.config import get_cheap_max_input_token_count
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_methodology_dirs
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.utils import daily_check_git_updates
from jarvis.jarvis_utils.git_utils import find_git_root_and_cd


def _get_project_methodology_directory() -> Optional[str]:
    """
    获取项目级方法论目录路径，如果不在Git仓库中则返回None

    返回：
        Optional[str]: 项目级方法论目录的路径，如果不在Git仓库中则返回None
    """
    try:
        # 获取Git仓库根目录
        git_root = find_git_root_and_cd(".")
        methodology_dir = os.path.join(git_root, ".jarvis", "methodologies")
        if not os.path.exists(methodology_dir):
            try:
                os.makedirs(methodology_dir, exist_ok=True)
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 创建项目级方法论目录失败: {str(e)}")
                return None
        return methodology_dir
    except Exception:
        # 如果不是Git仓库或获取失败，返回None
        return None


def _get_methodology_directory() -> str:
    """
    获取方法论目录路径，如果不存在则创建

    返回：
        str: 方法论目录的路径
    """
    methodology_dir = os.path.join(get_data_dir(), "methodologies")
    if not os.path.exists(methodology_dir):
        try:
            os.makedirs(methodology_dir, exist_ok=True)
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 创建方法论目录失败: {str(e)}")
    return methodology_dir


def _load_methodologies_from_dir(directory: str) -> Dict[str, str]:
    """
    从指定目录加载所有方法论文件。

    参数：
        directory: 方法论目录路径

    返回：
        Dict[str, str]: 方法论字典，键为问题类型，值为方法论内容。
    """
    all_methodologies: Dict[str, str] = {}

    if not os.path.isdir(directory):
        return all_methodologies

    import glob

    for filepath in glob.glob(os.path.join(directory, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                methodology = json.load(f)
                problem_type = methodology.get("problem_type", "")
                content = methodology.get("content", "")
                if problem_type and content:
                    all_methodologies[problem_type] = content
        except Exception:
            continue

    return all_methodologies


def _load_all_methodologies() -> List[Tuple[str, str]]:
    """
    从默认目录和配置的外部目录加载所有方法论文件。
    项目级方法论优先级高于全局方法论。

    返回：
        List[Tuple[str, str]]: 方法论列表，每个元素为(问题类型, 方法论内容)元组。
    """
    all_methodologies: List[Tuple[str, str]] = []

    # 优先加载项目级方法论
    project_methodology_dir = _get_project_methodology_directory()
    if project_methodology_dir:
        methodology_dirs = [project_methodology_dir]
    else:
        methodology_dirs = []

    # 添加全局方法论目录（优先级较低）
    methodology_dirs += [_get_methodology_directory()] + get_methodology_dirs()

    # 如果配置了中心方法论仓库，将其添加到加载路径
    central_repo = get_central_methodology_repo()
    if central_repo:
        # 支持本地目录路径或Git仓库URL
        expanded = os.path.expanduser(os.path.expandvars(central_repo))
        if os.path.isdir(expanded):
            # 直接使用本地目录（支持Git仓库的子目录）
            methodology_dirs.append(expanded)
        else:
            # 中心方法论仓库存储在数据目录下的特定位置
            central_repo_path = os.path.join(get_data_dir(), "central_methodology_repo")
            methodology_dirs.append(central_repo_path)

            # 确保中心方法论仓库被克隆/更新
            if not os.path.exists(central_repo_path):
                try:
                    import subprocess

                    PrettyOutput.auto_print(f"ℹ️ 正在克隆中心方法论仓库: {central_repo}")
                    subprocess.run(
                        ["git", "clone", central_repo, central_repo_path], check=True
                    )
                except Exception as e:
                    PrettyOutput.auto_print(f"❌ 克隆中心方法论仓库失败: {str(e)}")

    # --- 全局每日更新检查（后台线程执行，避免阻塞）---
    def check_methodology_updates() -> None:
        try:
            daily_check_git_updates(methodology_dirs, "methodologies")
        except Exception:
            # 静默失败，不影响正常使用
            pass

    threading.Thread(target=check_methodology_updates, daemon=True).start()

    import glob

    # 收集循环中的提示，统一打印，避免逐条加框
    warn_dirs: List[str] = []
    error_lines: List[str] = []

    for directory in set(methodology_dirs):  # Use set to avoid duplicates
        if not os.path.isdir(directory):
            warn_dirs.append(f"警告: 方法论目录不存在或不是一个目录: {directory}")
            continue

        for filepath in sorted(
            glob.glob(os.path.join(directory, "*.json")),
            key=os.path.getmtime,
            reverse=True,
        ):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    methodology = json.load(f)
                    problem_type = methodology.get("problem_type", "")
                    content = methodology.get("content", "")
                    if problem_type and content:
                        all_methodologies.append((problem_type, content))
            except Exception as e:
                filename = os.path.basename(filepath)
                error_lines.append(f"加载方法论文件 {filename} 失败: {str(e)}")

    # 统一打印目录警告与文件加载失败信息
    if warn_dirs:
        PrettyOutput.auto_print("⚠️ " + "\n⚠️ ".join(warn_dirs))
    if error_lines:
        PrettyOutput.auto_print("⚠️ " + "\n⚠️ ".join(error_lines))
    return all_methodologies


def load_methodology(
    user_input: str,
    tool_registery: Optional[Any] = None,
) -> str:
    """
    加载方法论并上传到大模型。

    参数：
        user_input: 用户输入文本，用于提示大模型
        tool_registery: 工具注册表，用于获取工具列表

    返回：
        str: 相关的方法论提示，如果未找到方法论则返回空字符串
    """

    prompt = tool_registery.prompt() if tool_registery else ""

    try:
        # 加载所有方法论
        PrettyOutput.auto_print("📁 加载方法论文件...")
        methodologies = _load_all_methodologies()
        if not methodologies:
            PrettyOutput.auto_print("⚠️ 没有找到方法论文件")
            return ""
        PrettyOutput.auto_print(f"✅ 加载方法论文件完成 (共 {len(methodologies)} 个)")

        # 方法论推荐使用normal模型以确保质量
        platform = PlatformRegistry().get_normal_platform()

        if not platform:
            PrettyOutput.auto_print("❌ 无法创建平台实例")
            return ""

        platform.set_suppress_output(True)

        # 步骤1：获取所有方法论的标题
        methodology_titles = [title for title, _ in methodologies]

        # 步骤2：让大模型选择相关性高的方法论
        methodology_titles_text = "\n".join(
            [f"{i}. {title}" for i, title in enumerate(methodology_titles, 1)]
        )

        selection_prompt = f"""以下是所有可用的方法论标题：

<methodology_titles>
{methodology_titles_text}
</methodology_titles>

<available_tools>
{prompt}
</available_tools>

<user_requirement>
{user_input}
</user_requirement>

请分析用户需求，从上述方法论中选择出与需求相关性较高的方法论（可以选择多个）。

请严格按照以下格式返回序号：
<NUM>序号1,序号2,序号3</NUM>

例如：<NUM>1,3,5</NUM>

如果没有相关的方法论，请返回：<NUM>none</NUM>

注意：只返回<NUM>标签内的内容，不要有其他任何输出。
"""

        # 获取大模型选择的方法论序号（限制输出最大50字）
        with console.status(
            "[bold blue]🔍 正在分析需求并推荐方法论...", spinner="dots"
        ):
            response = platform.chat_until_success(
                selection_prompt, max_output=50
            ).strip()

        # 重置平台，恢复输出
        platform.reset()
        platform.set_suppress_output(False)

        # 从响应中提取<NUM>标签内的内容
        import re

        num_match = re.search(r"<NUM>(.*?)</NUM>", response, re.DOTALL)

        if not num_match:
            # 如果没有找到<NUM>标签，尝试直接解析响应
            selected_indices_str = response
        else:
            selected_indices_str = num_match.group(1).strip()

        if selected_indices_str.lower() == "none":
            return "没有历史方法论可参考"

        # 解析选择的序号
        selected_methodologies = []
        try:
            if selected_indices_str:
                indices = [
                    int(idx.strip())
                    for idx in selected_indices_str.split(",")
                    if idx.strip().isdigit()
                ]
                for idx in indices:
                    if 1 <= idx <= len(methodologies):
                        selected_methodologies.append(methodologies[idx - 1])
        except Exception:
            # 如果解析失败，返回空结果
            return "没有历史方法论可参考"

        if not selected_methodologies:
            return "没有历史方法论可参考"

        # 获取模型上下文窗口大小，用于限制方法论内容
        methodology_token_limit = None
        try:
            # 直接获取模型的最大输入token数（上下文窗口）
            max_input_tokens = platform._get_platform_max_input_token_count()
            # 使用上下文窗口的0.75作为方法论限制，保留0.25作为安全余量
            methodology_token_limit = int(max_input_tokens * 0.75)
            if methodology_token_limit <= 0:
                methodology_token_limit = None
        except Exception:
            pass

        # 回退方案：使用cheap模型的输入窗口限制
        if methodology_token_limit is None:
            max_input_tokens = get_cheap_max_input_token_count()
            methodology_token_limit = int(max_input_tokens * 0.75)

        # 步骤3：将选择出来的方法论内容提供给大模型生成步骤
        # 首先构建基础提示词部分
        base_prompt = """以下是与用户需求相关的方法论内容：

"""
        suffix_prompt = f"""以下是所有可用的工具内容：

{prompt}

用户需求：{user_input}

请根据以上方法论和可调用的工具内容，规划/总结出执行步骤。

请按以下格式回复：
### 与该任务/需求相关的方法论
1. [方法论名字]
2. [方法论名字]
### 根据以上方法论，规划/总结出执行步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

除以上要求外，不要输出任何内容
"""

        # 计算基础部分的token数
        base_tokens = get_context_token_count(base_prompt + suffix_prompt)
        available_tokens = methodology_token_limit - base_tokens

        # 基于token限制筛选方法论内容
        final_prompt = base_prompt
        selected_count = 0
        total_methodology_tokens = 0

        for problem_type, content in selected_methodologies:
            methodology_text = f"## {problem_type}\n\n{content}\n\n---\n\n"
            methodology_tokens = get_context_token_count(methodology_text)

            # 检查是否已达到数量限制（最多3条）
            if selected_count >= 3:
                PrettyOutput.auto_print(
                    f"ℹ️ 已达到方法论数量限制 ({selected_count}/3)，停止加载更多方法论"
                )
                break

            # 检查是否会超过token限制
            if total_methodology_tokens + methodology_tokens > available_tokens:
                PrettyOutput.auto_print(
                    f"ℹ️ 达到方法论token限制 ({total_methodology_tokens}/{available_tokens})，停止加载更多方法论"
                )
                break

            final_prompt += methodology_text
            total_methodology_tokens += methodology_tokens
            selected_count += 1

        # 如果一个方法论都没有加载成功
        if selected_count == 0:
            PrettyOutput.auto_print("⚠️ 警告：由于token限制，无法加载任何方法论内容")
            return "没有历史方法论可参考"

        final_prompt += suffix_prompt

        PrettyOutput.auto_print(
            f"ℹ️ 成功加载 {selected_count} 个方法论，总token数: {total_methodology_tokens}"
        )

        # 如果内容不大，直接使用chat_until_success
        return platform.chat_until_success(final_prompt)

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 加载方法论失败: {str(e)}")
        return ""
