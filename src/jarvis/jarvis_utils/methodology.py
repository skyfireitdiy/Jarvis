# -*- coding: utf-8 -*-
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
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_data_dir, get_methodology_dirs
from jarvis.jarvis_utils.globals import get_agent, current_agent_name
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import is_context_overflow, daily_check_git_updates

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
            PrettyOutput.print(f"创建方法论目录失败: {str(e)}", OutputType.ERROR)
    return methodology_dir


def _load_all_methodologies() -> Dict[str, str]:
    """
    从默认目录和配置的外部目录加载所有方法论文件。

    返回：
        Dict[str, str]: 方法论字典，键为问题类型，值为方法论内容。
    """
    all_methodologies = {}
    methodology_dirs = [_get_methodology_directory()] + get_methodology_dirs()

    # --- 全局每日更新检查 ---
    daily_check_git_updates(methodology_dirs, "methodologies")

    import glob

    for directory in set(methodology_dirs):  # Use set to avoid duplicates
        if not os.path.isdir(directory):
            PrettyOutput.print(f"警告: 方法论目录不存在或不是一个目录: {directory}", OutputType.WARNING)
            continue

        for filepath in glob.glob(os.path.join(directory, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    methodology = json.load(f)
                    problem_type = methodology.get("problem_type", "")
                    content = methodology.get("content", "")
                    if problem_type and content:
                        if problem_type in all_methodologies:
                            PrettyOutput.print(f"警告: 方法论 '{problem_type}' 被 '{filepath}' 覆盖。", OutputType.WARNING)
                        all_methodologies[problem_type] = content
            except Exception as e:
                filename = os.path.basename(filepath)
                PrettyOutput.print(
                    f"加载方法论文件 {filename} 失败: {str(e)}", OutputType.WARNING
                )

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
        PrettyOutput.print(f"创建方法论临时文件失败: {str(e)}", OutputType.ERROR)
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
        PrettyOutput.print("方法论文档不存在", OutputType.WARNING)
        return False

    methodologies = _load_all_methodologies()
    if not methodologies:
        PrettyOutput.print("没有可用的方法论文档", OutputType.WARNING)
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


def load_methodology(user_input: str, tool_registery: Optional[Any] = None) -> str:
    """
    加载方法论并上传到大模型。

    参数：
        user_input: 用户输入文本，用于提示大模型
        tool_registery: 工具注册表，用于获取工具列表

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
        print(f"📁 加载方法论文件...")
        methodologies = _load_all_methodologies()
        if not methodologies:
            print(f"❌ 没有找到方法论文件")
            return ""
        print(f"✅ 加载方法论文件完成 (共 {len(methodologies)} 个)")

        platform = PlatformRegistry().get_normal_platform()
        platform.set_suppress_output(True)

        # 步骤1：获取所有方法论的标题
        methodology_titles = list(methodologies.keys())

        # 步骤2：让大模型选择相关性高的方法论
        selection_prompt = f"""以下是所有可用的方法论标题：

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
        num_match = re.search(r'<NUM>(.*?)</NUM>', response, re.DOTALL)
        
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
                indices = [int(idx.strip()) for idx in selected_indices_str.split(",") if idx.strip().isdigit()]
                for idx in indices:
                    if 1 <= idx <= len(methodology_titles):
                        title = methodology_titles[idx - 1]
                        selected_methodologies[title] = methodologies[title]
        except Exception:
            # 如果解析失败，返回空结果
            return "没有历史方法论可参考"

        if not selected_methodologies:
            return "没有历史方法论可参考"

        # 步骤3：将选择出来的方法论内容提供给大模型生成步骤
        final_prompt = f"""以下是与用户需求相关的方法论内容：

"""
        for problem_type, content in selected_methodologies.items():
            final_prompt += f"## {problem_type}\n\n{content}\n\n---\n\n"

        final_prompt += f"""以下是所有可用的工具内容：

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

        # 如果内容不大，直接使用chat_until_success
        return platform.chat_until_success(final_prompt)

    except Exception as e:
        PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
        return ""
