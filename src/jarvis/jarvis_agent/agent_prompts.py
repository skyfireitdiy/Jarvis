# -*- coding: utf-8 -*-
"""通用Agent系统提示词模块

提供场景分类、难度评估和系统提示词加载功能。
场景提示词文件位于 builtin/prompts/agent_system/ 目录。
"""

from pathlib import Path
from typing import Dict, List, Tuple, Union

import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.output import PrettyOutput


# 提示词文件目录
_PROMPTS_DIR = (
    Path(__file__).parent.parent.parent.parent / "builtin" / "prompts" / "agent_system"
)


def _load_scenario_types() -> Dict[str, Dict[str, str]]:
    """从 md 文件的 YAML front matter 加载场景类型定义

    返回:
        Dict[str, Dict[str, str]]: 场景类型字典，格式为 {scenario_id: {"name": "...", "description": "..."}}

    异常:
        FileNotFoundError: 如果提示词目录不存在
        IOError: 如果文件读取失败
        ValueError: 如果文件格式不正确
    """
    if not _PROMPTS_DIR.exists():
        raise FileNotFoundError(f"提示词目录不存在: {_PROMPTS_DIR}")

    scenarios = {}

    try:
        # 扫描所有 .md 文件（排除 README.md）
        for md_file in _PROMPTS_DIR.glob("*.md"):
            # 跳过 README.md
            if md_file.name.lower() == "readme.md":
                continue

            # 场景 ID 使用文件名（不含扩展名）
            scenario_id = md_file.stem

            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # 解析 YAML front matter
                # 格式：---\nname: xxx\ndescription: yyy\n---\nprompt 正文
                front_matter = None
                if content.startswith("---"):
                    # 找到第二个 '---'
                    end_marker = content.find("\n---", 4)
                    if end_marker != -1:
                        front_matter_text = content[4:end_marker]
                        front_matter = yaml.safe_load(front_matter_text)

                if front_matter is None:
                    raise ValueError(
                        f"文件 '{md_file.name}' 缺少 YAML front matter 或格式不正确"
                    )

                if not isinstance(front_matter, dict):
                    raise ValueError(
                        f"文件 '{md_file.name}' 的 front matter 不是有效的字典"
                    )

                if "name" not in front_matter or "description" not in front_matter:
                    raise ValueError(
                        f"文件 '{md_file.name}' 的 front matter 缺少必需的字段 'name' 或 'description'"
                    )

                scenarios[scenario_id] = {
                    "name": front_matter["name"],
                    "description": front_matter["description"],
                }

            except yaml.YAMLError as e:
                raise IOError(
                    f"解析文件 '{md_file.name}' 的 YAML front matter 失败: {e}"
                ) from e
            except ValueError:
                raise
            except Exception as e:
                raise IOError(f"加载文件 '{md_file.name}' 失败: {e}") from e

        if not scenarios:
            raise FileNotFoundError(f"在目录 {_PROMPTS_DIR} 中未找到有效的提示词文件")

        return scenarios

    except FileNotFoundError:
        raise
    except ValueError:
        raise
    except Exception as e:
        raise IOError(f"加载场景类型定义失败: {e}") from e


def _get_scenario_types() -> Dict[str, str]:
    """获取场景类型名称字典（向后兼容）

    返回:
        Dict[str, str]: {scenario_id: scenario_name}
    """
    scenarios = _load_scenario_types()
    return {
        scenario_id: scenario_info["name"]
        for scenario_id, scenario_info in scenarios.items()
    }


# 场景类型定义（向后兼容，实际从文件加载）
SCENARIO_TYPES = _get_scenario_types()


def classify_user_request(
    user_input: Union[str, List[ContentBlock]],
) -> Tuple[str, str]:
    """使用 normal_llm 对用户需求进行分类

    参数:
        user_input: 用户输入的需求描述（支持纯文本或多模态内容）

    返回:
        Tuple[str, str]: (场景类型, 难度等级)
            场景类型: research/document_writing/troubleshooting/data_analysis/planning/translation/default
            难度等级: easy/medium/hard
    """
    # 如果 user_input 是多模态内容，提取其中的文本
    if isinstance(user_input, list):
        text_parts = []
        for block in user_input:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        user_input = "\n".join(text_parts) if text_parts else "[多模态内容]"
    try:
        # 获取 normal_llm 平台
        platform = PlatformRegistry().get_normal_platform()
        platform.set_suppress_output(False)

        # 从文件加载场景类型定义
        scenarios = _load_scenario_types()

        # 构建分类提示词
        scenarios_list = []
        scenario_ids = []
        for idx, (scenario_id, scenario_info) in enumerate(scenarios.items(), 1):
            scenario_name = scenario_info["name"]
            scenario_desc = scenario_info["description"]
            scenarios_list.append(
                f"{idx}. {scenario_id}（{scenario_name}）：{scenario_desc}"
            )
            scenario_ids.append(scenario_id)

        scenarios_text = "\n".join(scenarios_list)

        classification_prompt = f"""请分析以下用户需求，判断其属于哪个场景类型，并评估任务难度。

用户需求：
{user_input}

可选场景类型：
{scenarios_text}

任务难度等级：
- easy（简单）：简单问答、单步操作、明确的小任务
- medium（中等）：需要多步操作、需要理解上下文、涉及一定复杂度
- hard（困难）：需要深度分析、多维度综合、需要专业知识和深入思考

请按以下格式返回（只返回这两行，不要包含其他内容）：
scenario: <场景类型>
difficulty: <难度等级>

如果无法明确判断场景类型，scenario 返回 default。
如果无法明确判断难度，difficulty 返回 medium。
"""

        # 使用 normal_llm 进行分类
        response = platform.chat_until_success(classification_prompt)

        # 解析响应，提取场景类型和难度
        response = response.strip().lower()

        # 初始化默认值
        scenario = "default"
        difficulty = "medium"

        # 解析响应格式：scenario: xxx\ndifficulty: yyy
        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("scenario:"):
                scenario_value = line.split(":", 1)[1].strip()
                # 验证场景类型是否有效
                for scenario_type in SCENARIO_TYPES.keys():
                    if (
                        scenario_type in scenario_value
                        or scenario_value == scenario_type
                    ):
                        scenario = scenario_type
                        break
            elif line.startswith("difficulty:"):
                difficulty_value = line.split(":", 1)[1].strip()
                # 验证难度等级是否有效
                if difficulty_value in ["easy", "medium", "hard"]:
                    difficulty = difficulty_value

        # 输出分类结果
        difficulty_display = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(
            difficulty, difficulty
        )
        PrettyOutput.auto_print(
            f"📋 需求分类结果: {SCENARIO_TYPES.get(scenario, '通用任务')} ({scenario}) | 难度: {difficulty_display} ({difficulty})"
        )
        return scenario, difficulty

    except Exception as e:
        # 分类失败时返回默认类型和中等难度
        PrettyOutput.auto_print(f"⚠️ 需求分类失败: {e}，使用默认分类")
        return "default", "medium"


def _load_prompt_from_file(scenario: str) -> str:
    """从文件加载提示词

    参数:
        scenario: 场景类型

    返回:
        str: 提示词内容（不包括 YAML front matter）

    异常:
        FileNotFoundError: 如果文件不存在
        IOError: 如果文件读取失败
    """
    prompt_file = _PROMPTS_DIR / f"{scenario}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(
            f"提示词文件不存在: {prompt_file}。请确保文件存在于 {_PROMPTS_DIR} 目录下。"
        )

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 跳过 YAML front matter（如果存在）
        # 格式：---\nname: xxx\ndescription: yyy\n---\nprompt 正文
        if content.startswith("---"):
            # 找到第二个 '---' 的位置
            end_marker = content.find("\n---", 4)
            if end_marker != -1:
                # 跳过 front matter，返回后面的内容
                content = content[end_marker + 4 :]  # +4 跳过 "\n---"

        content = content.strip()

        if not content:
            raise ValueError(f"提示词文件为空: {prompt_file}")
        return content
    except Exception as e:
        raise IOError(f"加载提示词文件失败 ({prompt_file}): {e}") from e


def get_system_prompt(scenario: str = "default") -> str:
    """根据场景类型获取对应的系统提示词

    从文件加载完整的提示词。每个场景的提示词文件都包含完整的提示词内容，
    包括基础的 ARCHER 流程和场景特定的指导，可以根据场景调整 ARCHER 流程的要求。

    参数:
        scenario: 场景类型（research/document_writing/troubleshooting/data_analysis/planning/translation/default）

    返回:
        str: 对应场景的完整系统提示词

    异常:
        FileNotFoundError: 如果提示词文件不存在
        IOError: 如果文件读取失败
    """
    # 直接从文件加载完整的提示词
    return _load_prompt_from_file(scenario)
