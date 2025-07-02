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
from typing import Any, Dict, List, Optional

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import is_context_overflow


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
    加载所有方法论文件

    返回：
        Dict[str, str]: 方法论字典，键为问题类型，值为方法论内容
    """
    methodology_dir = _get_methodology_directory()
    all_methodologies = {}

    if not os.path.exists(methodology_dir):
        return all_methodologies

    import glob

    for filepath in glob.glob(os.path.join(methodology_dir, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                methodology = json.load(f)
                problem_type = methodology.get("problem_type", "")
                content = methodology.get("content", "")
                if problem_type and content:
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

        # 获取当前平台
        platform = PlatformRegistry().get_normal_platform()
        platform.set_suppress_output(False)
        if not platform:
            return ""

        # 构建基础提示信息
        base_prompt = f"""以下是所有可用的方法论内容：

"""
        # 构建完整内容
        full_content = base_prompt
        for problem_type, content in methodologies.items():
            full_content += f"## {problem_type}\n\n{content}\n\n---\n\n"

        full_content += f"以下是所有可用的工具内容：\n\n"
        full_content += prompt

        # 添加用户输入和输出要求
        full_content += f"""
请根据以上方法论和可调用的工具内容，规划/总结出以下用户需求的执行步骤: {user_input}

请按以下格式回复：
### 与该任务/需求相关的方法论
1. [方法论名字]
2. [方法论名字]
### 根据以上方法论，规划/总结出执行步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

如果没有匹配的方法论，请输出：没有历史方法论可参考
除以上要求外，不要输出任何内容
"""

        # 检查内容是否过大
        is_large_content = is_context_overflow(full_content)
        temp_file_path = None

        try:
            if is_large_content:
                # 创建临时文件
                print(f"📝 创建方法论临时文件...")
                temp_file_path = _create_methodology_temp_file(methodologies)
                if not temp_file_path:
                    print(f"❌ 创建方法论临时文件失败")
                    return ""
                print(f"✅ 创建方法论临时文件完成")

                # 尝试上传文件
                upload_success = platform.upload_files([temp_file_path])

                if upload_success:
                    # 使用上传的文件生成摘要
                    return platform.chat_until_success(
                        base_prompt
                        + f"""
请根据已上传的方法论和可调用的工具文件内容，规划/总结出以下用户需求的执行步骤: {user_input}

请按以下格式回复：
### 与该任务/需求相关的方法论
1. [方法论名字]
2. [方法论名字]
### 根据以上方法论，规划/总结出执行步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

如果没有匹配的方法论，请输出：没有历史方法论可参考
除以上要求外，不要输出任何内容
"""
                    )
                else:
                    return "没有历史方法论可参考"
            # 如果内容不大或上传失败，直接使用chat_until_success
            return platform.chat_until_success(full_content)

        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass

    except Exception as e:
        PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
        return ""
