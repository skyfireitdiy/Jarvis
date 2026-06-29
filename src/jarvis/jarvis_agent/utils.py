# -*- coding: utf-8 -*-
"""
工具函数（jarvis_agent.utils）

- join_prompts: 统一的提示拼接策略（支持纯文本和多模态内容）
- is_auto_complete: 统一的自动完成标记检测
- fix_tool_call_with_llm: 使用大模型修复工具调用格式
"""

from enum import Enum
from typing import Any, List
from typing import Iterable
from typing import Optional, Union
from typing import cast


from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ot


def join_prompts(
    parts: Iterable[Union[str, List[ContentBlock]]],
) -> Union[str, List[ContentBlock]]:
    """
    将多个提示片段按统一规则拼接：
    - 支持纯文本和多模态内容
    - 如果所有部分都是字符串，返回拼接后的字符串
    - 如果任何部分是多模态内容，返回合并后的内容块列表
    """
    try:
        all_parts = list(parts)
    except Exception:
        # 防御性处理：若 parts 不可迭代或出现异常，直接返回空字符串
        return ""

    # 检查是否有多模态内容
    has_multimodal = any(isinstance(p, list) for p in all_parts)

    if not has_multimodal:
        # 所有部分都是字符串，使用原有逻辑
        non_empty: list[str] = [p for p in all_parts if isinstance(p, str) and p]
        return "\n\n".join(non_empty)

    # 有多模态内容，需要合并
    result_blocks: List[ContentBlock] = []

    for part in all_parts:
        if isinstance(part, str):
            if part.strip():
                # 将非空字符串转换为文本内容块
                result_blocks.append({"type": "text", "text": part})
        elif isinstance(part, list):
            # 直接添加内容块列表
            result_blocks.extend(part)

    return result_blocks


def is_auto_complete(response: str) -> bool:
    """
    检测是否包含自动完成标记。
    当前实现：包含 ot('!!!COMPLETE!!!') 即视为自动完成。
    """
    try:
        return ot("!!!COMPLETE!!!") in response
    except Exception:
        # 防御性处理：即使 ot 出现异常，也不阻塞主流程
        return "!!!COMPLETE!!!" in response


def normalize_next_action(next_action: Any) -> str:
    """
    规范化下一步动作为字符串:
    - 如果是 Enum, 返回其 value（若为字符串）
    - 如果是 str, 原样返回
    - 其他情况返回空字符串
    """
    try:
        if isinstance(next_action, Enum):
            value = getattr(next_action, "value", None)
            return value if isinstance(value, str) else ""
        if isinstance(next_action, str):
            return next_action
        return ""
    except Exception:
        return ""


def build_fix_prompt(content: str, error_msg: str, tool_usage: str) -> str:
    """构建修复工具调用的提示词

    参数:
        content: 包含错误工具调用的内容
        error_msg: 错误消息
        tool_usage: 工具使用说明

    返回:
        str: 构建好的提示字符串
    """
    return f"""你之前的工具调用格式有误，请根据工具使用说明修复以下内容。

**错误信息：**
{error_msg}

**工具使用说明：**
{tool_usage}

**错误的工具调用内容：**
{content}

请修复上述工具调用内容，确保：
1. 输出纯 JSON 对象，包含 name 和 arguments 字段
2. JSON格式正确，包含 name、arguments、want 三个字段
3. 如果使用多行字符串，直接换行即可

请直接返回修复后的完整工具调用内容，不要添加其他说明文字。"""


def fix_tool_call_with_llm(content: str, agent: Any, error_msg: str) -> Optional[str]:
    """使用大模型修复工具调用格式

    参数:
        content: 包含错误工具调用的内容
        agent: Agent实例，用于调用大模型
        error_msg: 错误消息

    返回:
        Optional[str]: 修复后的内容，如果修复失败则返回None
    """
    try:
        # 获取工具使用说明
        tool_usage = agent.get_tool_usage_prompt()

        # 构建修复提示
        fix_prompt = build_fix_prompt(content, error_msg, tool_usage)

        # 调用大模型修复
        PrettyOutput.auto_print("🤖 尝试使用大模型修复工具调用格式...")
        fixed_content: Any = agent.model.chat_until_success(fix_prompt)

        # 类型检查：确保返回的是字符串
        if fixed_content and isinstance(fixed_content, str):
            PrettyOutput.auto_print("✅ 大模型修复完成")
            # 类型断言：确保返回类型匹配函数签名
            return cast(Optional[str], fixed_content)
        else:
            PrettyOutput.auto_print("❌ 大模型修复失败：返回内容为空")
            return None

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 大模型修复失败：{str(e)}")
        return None


def install_plugin(source_path: str) -> bool:
    """安装插件到 Jarvis 数据目录

    参数:
        source_path: 插件源路径，可以是目录或压缩文件（tar/tar.gz/zip）

    返回:
        bool: 安装成功返回 True，失败返回 False

    功能:
        1. 校验插件是否包含 config.yaml
        2. 复制或解压到 ~/.jarvis/plugins/插件名/ 下
        3. 插件名从 config.yaml 的 name 字段获取，若无则使用目录名/文件名
    """
    import os
    import shutil
    import tarfile
    import zipfile
    import tempfile
    import yaml
    from pathlib import Path

    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.output import PrettyOutput

    try:
        source = Path(source_path).resolve()

        if not source.exists():
            PrettyOutput.auto_print(f"❌ 插件源路径不存在: {source_path}")
            return False

        # 获取 Jarvis 数据目录下的 plugins 目录
        data_dir = Path(get_data_dir())
        plugins_dir = data_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # 临时目录用于处理压缩文件
        temp_dir = None
        plugin_source_dir = None

        # 判断源类型：目录还是文件
        if source.is_dir():
            # 直接是目录
            plugin_source_dir = source
        elif source.is_file():
            # 是压缩文件，需要解压
            # 使用 suffixes 获取完整后缀列表，正确识别 .tar.gz 等复合后缀
            suffixes = [s.lower() for s in source.suffixes]
            is_zip = ".zip" in suffixes
            is_tar = ".tar" in suffixes or ".tgz" in suffixes

            if not is_zip and not is_tar:
                PrettyOutput.auto_print(
                    "❌ 不支持的文件格式，仅支持 .tar/.tar.gz/.tgz/.zip"
                )
                return False

            # 创建临时目录解压
            temp_dir = tempfile.mkdtemp(prefix="jarvis_plugin_")

            if is_zip:
                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(temp_dir)
            else:  # tar formats (including .tar.gz, .tgz)
                with tarfile.open(source, "r:*") as tf:
                    # 使用 filter='data' 防止路径遍历攻击 (CVE-2007-4559)
                    tf.extractall(temp_dir, filter="data")

            # 解压后，查找包含 config.yaml 的目录
            extracted_items = list(Path(temp_dir).iterdir())
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                # 只有一个目录，直接使用
                plugin_source_dir = extracted_items[0]
            else:
                # 多个文件/目录，使用临时目录本身
                plugin_source_dir = Path(temp_dir)
        else:
            PrettyOutput.auto_print("❌ 无效的源路径类型")
            return False

        # 校验是否包含 config.yaml
        config_file = plugin_source_dir / "config.yaml"
        if not config_file.exists():
            PrettyOutput.auto_print("❌ 插件缺少 config.yaml 文件")
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return False

        # 读取 config.yaml 获取插件名
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_content = yaml.safe_load(f)
                plugin_name = (
                    config_content.get("name", None)
                    if isinstance(config_content, dict)
                    else None
                )
        except Exception:
            plugin_name = None

        # 如果没有 name 字段，使用源目录名/文件名
        if not plugin_name:
            if source.is_dir():
                plugin_name = source.name
            else:
                # 使用文件名（去掉扩展名）
                plugin_name = source.stem
                # 如果是 .tar.gz，需要去掉两个扩展名
                if plugin_name.endswith(".tar"):
                    plugin_name = plugin_name[:-4]

        # 安全处理：只保留文件名部分，防止路径遍历攻击
        plugin_name = Path(plugin_name).name

        # 目标安装目录
        target_dir = plugins_dir / plugin_name

        # 如果目标目录已存在，先删除
        if target_dir.exists():
            PrettyOutput.auto_print(f"⚠️  插件目录已存在，将覆盖: {target_dir}")
            shutil.rmtree(target_dir)

        # 复制插件到目标目录
        shutil.copytree(plugin_source_dir, target_dir)

        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        PrettyOutput.auto_print(f"✅ 插件安装成功: {plugin_name} -> {target_dir}")
        return True

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 插件安装失败: {str(e)}")
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        return False


def list_plugins() -> None:
    """
    列出所有已安装的插件

    功能:
        扫描 ~/.jarvis/plugins/ 目录，读取每个插件的 config.yaml
        并格式化输出插件信息（名称、描述、版本等）
    """
    from pathlib import Path
    import yaml
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.output import PrettyOutput

    plugins_dir = Path(get_data_dir()) / "plugins"

    if not plugins_dir.exists():
        PrettyOutput.auto_print("📦 未安装任何插件")
        return

    # 获取所有插件目录
    plugin_dirs = [d for d in plugins_dir.iterdir() if d.is_dir()]

    if not plugin_dirs:
        PrettyOutput.auto_print("📦 未安装任何插件")
        return

    PrettyOutput.auto_print(f"📦 已安装的插件 ({len(plugin_dirs)}个):\n")

    for plugin_dir in sorted(plugin_dirs):
        config_file = plugin_dir / "config.yaml"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if isinstance(config, dict):
                        name = config.get("name", plugin_dir.name)
                        description = config.get("description", "无描述")
                        version = config.get("version", "未知版本")
                        PrettyOutput.auto_print(f"  • {name} (v{version})")
                        PrettyOutput.auto_print(f"    {description}")
                        PrettyOutput.auto_print("")
                    else:
                        PrettyOutput.auto_print(f"  • {plugin_dir.name}")
                        PrettyOutput.auto_print("    配置文件格式错误")
                        PrettyOutput.auto_print("")
            except Exception as e:
                PrettyOutput.auto_print(f"  • {plugin_dir.name}")
                PrettyOutput.auto_print(f"    读取配置失败: {str(e)}")
                PrettyOutput.auto_print("")
        else:
            PrettyOutput.auto_print(f"  • {plugin_dir.name}")
            PrettyOutput.auto_print("    ⚠️ 缺少 config.yaml")
            PrettyOutput.auto_print("")


def uninstall_plugin(plugin_name: str) -> bool:
    """
    卸载插件

    Args:
        plugin_name: 插件名称

    Returns:
        bool: 卸载成功返回 True，失败返回 False
    """
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.output import PrettyOutput

    # 安全处理：只保留文件名部分，防止路径遍历攻击
    plugin_name = Path(plugin_name).name

    plugins_dir = Path(get_data_dir()) / "plugins"
    plugin_dir = plugins_dir / plugin_name

    if not plugin_dir.exists():
        PrettyOutput.auto_print(f"⚠️ 插件不存在: {plugin_name}")
        return False

    if not plugin_dir.is_dir():
        PrettyOutput.auto_print(f"⚠️ 插件路径不是目录: {plugin_dir}")
        return False

    try:
        import shutil

        shutil.rmtree(plugin_dir)
        PrettyOutput.auto_print(f"✅ 插件已卸载: {plugin_name}")
        return True
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 卸载插件失败: {str(e)}")
        return False


__all__ = [
    "join_prompts",
    "is_auto_complete",
    "normalize_next_action",
    "fix_tool_call_with_llm",
    "install_plugin",
    "uninstall_plugin",
]
