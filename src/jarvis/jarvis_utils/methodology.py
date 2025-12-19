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

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import tempfile
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_central_methodology_repo
from jarvis.jarvis_utils.config import get_cheap_max_input_token_count
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_methodology_dirs
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.utils import daily_check_git_updates


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


def _load_all_methodologies() -> Dict[str, str]:
    """
    从默认目录和配置的外部目录加载所有方法论文件。

    返回：
        Dict[str, str]: 方法论字典，键为问题类型，值为方法论内容。
    """
    all_methodologies = {}
    methodology_dirs = [_get_methodology_directory()] + get_methodology_dirs()

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

    # --- 全局每日更新检查 ---
    daily_check_git_updates(methodology_dirs, "methodologies")

    import glob

    # 收集循环中的提示，统一打印，避免逐条加框
    warn_dirs: List[str] = []
    error_lines: List[str] = []

    for directory in set(methodology_dirs):  # Use set to avoid duplicates
        if not os.path.isdir(directory):
            warn_dirs.append(f"警告: 方法论目录不存在或不是一个目录: {directory}")
            continue

        for filepath in glob.glob(os.path.join(directory, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    methodology = json.load(f)
                    problem_type = methodology.get("problem_type", "")
                    content = methodology.get("content", "")
                    if problem_type and content:
                        if problem_type in all_methodologies:
                            pass
                        all_methodologies[problem_type] = content
            except Exception as e:
                filename = os.path.basename(filepath)
                error_lines.append(f"加载方法论文件 {filename} 失败: {str(e)}")

    # 统一打印目录警告与文件加载失败信息
    if warn_dirs:
        PrettyOutput.auto_print("⚠️ " + "\n⚠️ ".join(warn_dirs))
    if error_lines:
        PrettyOutput.auto_print("⚠️ " + "\n⚠️ ".join(error_lines))
    return all_methodologies


def _create_methodology_temp_file(methodologies: Dict[str, str]) -> Optional[str]:
    """
    创建包含所有方法论的临时文件

    参数：
        methodologies: 方法论字典，键为问题类型，值为方法论内容

    返回：
        Optional[str]: 临时文件路径，如果创建失败则返回None
    """
    if not methodologies:
        return None

    try:
        # 创建临时文件
        fd, temp_path = tempfile.mkstemp(suffix=".md", prefix="methodologies_")
        os.close(fd)

        # 写入方法论内容
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write("# 方法论集合\n\n")
            for problem_type, content in methodologies.items():
                f.write(f"## {problem_type}\n\n")
                f.write(f"{content}\n\n")
                f.write("---\n\n")
            f.flush()

        return temp_path
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 创建方法论临时文件失败: {str(e)}")
        return None


def upload_methodology(platform: BasePlatform, other_files: List[str] = []) -> bool:
    """
    上传方法论文件到指定平台

    参数：
        platform: 平台实例，需实现upload_files方法

    返回：
        bool: 上传是否成功
    """
    methodology_dir = _get_methodology_directory()
    if not os.path.exists(methodology_dir):
        PrettyOutput.auto_print("⚠️ 方法论文档不存在")
        return False

    methodologies = _load_all_methodologies()
    if not methodologies:
        PrettyOutput.auto_print("⚠️ 没有可用的方法论文档")
        return False

    temp_file_path = _create_methodology_temp_file(methodologies)
    if not temp_file_path:
        return False

    try:
        return platform.upload_files([temp_file_path, *other_files])

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass


def load_methodology(
    user_input: str,
    tool_registery: Optional[Any] = None,
    platform_name: Optional[str] = None,
    model_name: Optional[str] = None,
    model_group: Optional[str] = None,
) -> str:
    """
    加载方法论并上传到大模型。

    参数：
        user_input: 用户输入文本，用于提示大模型
        tool_registery: 工具注册表，用于获取工具列表
        platform_name (str, optional): 指定的平台名称. Defaults to None.
        model_name (str, optional): 指定的模型名称. Defaults to None.

    返回：
        str: 相关的方法论提示，如果未找到方法论则返回空字符串
    """

    prompt = tool_registery.prompt() if tool_registery else ""

    # 获取方法论目录
    methodology_dir = _get_methodology_directory()
    if not os.path.exists(methodology_dir):
        return ""

    try:
        # 加载所有方法论
        PrettyOutput.auto_print("📁 加载方法论文件...")
        methodologies = _load_all_methodologies()
        if not methodologies:
            PrettyOutput.auto_print("⚠️ 没有找到方法论文件")
            return ""
        PrettyOutput.auto_print(f"✅ 加载方法论文件完成 (共 {len(methodologies)} 个)")

        if platform_name:
            # 如果指定了平台名称，使用 get_normal_platform 获取平台实例
            # 这样可以确保使用正确的 model_group 和配置
            try:
                platform = PlatformRegistry().get_normal_platform(model_group)
                if model_name:
                    platform.set_model_name(model_name)
            except Exception as e:
                # 如果获取失败，尝试直接创建（向后兼容）
                platform = PlatformRegistry().create_platform(platform_name)
                if platform and model_name:
                    platform.set_model_name(model_name)
                if not platform:
                    PrettyOutput.auto_print(f"❌ 无法创建平台实例: {str(e)}")
                    return ""
        else:
            # 方法论推荐使用cheap模型以降低成本
            platform = PlatformRegistry().get_cheap_platform(model_group)

        if not platform:
            PrettyOutput.auto_print("❌ 无法创建平台实例")
            return ""

        platform.set_suppress_output(True)

        # 步骤1：获取所有方法论的标题
        methodology_titles = list(methodologies.keys())

        # 步骤2：让大模型选择相关性高的方法论
        selection_prompt = """以下是所有可用的方法论标题：

"""
        for i, title in enumerate(methodology_titles, 1):
            selection_prompt += f"{i}. {title}\n"

        selection_prompt += f"""
以下是可用的工具列表：
{prompt}

用户需求：{user_input}

请分析用户需求，从上述方法论中选择出与需求相关性较高的方法论（可以选择多个）。

请严格按照以下格式返回序号：
<NUM>序号1,序号2,序号3</NUM>

例如：<NUM>1,3,5</NUM>

如果没有相关的方法论，请返回：<NUM>none</NUM>

注意：只返回<NUM>标签内的内容，不要有其他任何输出。
"""

        # 获取大模型选择的方法论序号
        response = platform.chat_until_success(selection_prompt).strip()

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
        selected_methodologies = {}
        try:
            if selected_indices_str:
                indices = [
                    int(idx.strip())
                    for idx in selected_indices_str.split(",")
                    if idx.strip().isdigit()
                ]
                for idx in indices:
                    if 1 <= idx <= len(methodology_titles):
                        title = methodology_titles[idx - 1]
                        selected_methodologies[title] = methodologies[title]
        except Exception:
            # 如果解析失败，返回空结果
            return "没有历史方法论可参考"

        if not selected_methodologies:
            return "没有历史方法论可参考"

        # 优先使用剩余token数量，回退到输入窗口限制
        methodology_token_limit = None
        try:
            remaining_tokens = platform.get_remaining_token_count()
            # 使用剩余token的2/3作为限制，保留1/3作为安全余量
            methodology_token_limit = int(remaining_tokens * 2 / 3)
            if methodology_token_limit <= 0:
                methodology_token_limit = None
        except Exception:
            pass

        # 回退方案：使用输入窗口的2/3（方法论使用cheap模型）
        if methodology_token_limit is None:
            max_input_tokens = get_cheap_max_input_token_count()
            methodology_token_limit = int(max_input_tokens * 2 / 3)

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

        for problem_type, content in selected_methodologies.items():
            methodology_text = f"## {problem_type}\n\n{content}\n\n---\n\n"
            methodology_tokens = get_context_token_count(methodology_text)

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
