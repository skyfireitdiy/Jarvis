# -*- coding: utf-8 -*-
"""场景提示词公共模块

提供场景分类、难度评估和系统提示词加载功能。
支持从 builtin 目录和数据目录（~/.jarvis/prompts/）双路径加载，
用户扩展文件可覆盖 builtin 同名文件。
"""

from pathlib import Path
from typing import Dict, List, Tuple, Union

import yaml  # type: ignore[import-untyped]

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.config import get_data_dir


# builtin 提示词根目录（从 jarvis_utils 向上4级到达项目根目录）
_BUILTIN_PROMPTS_ROOT = (
    Path(__file__).parent.parent.parent.parent / "builtin" / "prompts"
)


def _get_prompt_dirs(scenario_subdir: str) -> List[Path]:
    """获取提示词文件目录列表（按优先级从高到低）

    数据目录优先级高于 builtin 目录，用户扩展文件可覆盖内置文件。

    参数:
        scenario_subdir: 场景子目录名，如 "agent_system" 或 "code_agent_system"

    返回:
        List[Path]: 目录路径列表，优先级从高到低
    """
    dirs = []
    # 数据目录（用户扩展，优先级高）
    data_dir = Path(get_data_dir()) / "prompts" / scenario_subdir
    if data_dir.is_dir():
        dirs.append(data_dir)
    # builtin 目录（内置，优先级低）
    builtin_dir = _BUILTIN_PROMPTS_ROOT / scenario_subdir
    if builtin_dir.is_dir():
        dirs.append(builtin_dir)
    return dirs


def _load_scenario_types(scenario_subdir: str) -> Dict[str, Dict[str, str]]:
    """从 md 文件的 YAML front matter 加载场景类型定义

    优先从数据目录加载，同名文件覆盖 builtin。

    参数:
        scenario_subdir: 场景子目录名

    返回:
        Dict[str, Dict[str, str]]: 场景类型字典
    """
    prompt_dirs = _get_prompt_dirs(scenario_subdir)
    if not prompt_dirs:
        raise FileNotFoundError(
            f"提示词目录不存在: builtin 和数据目录中均未找到 {scenario_subdir}"
        )

    scenarios = {}

    # 按优先级从低到高加载（builtin 先，数据目录后），
    # 这样数据目录的同名文件会覆盖 builtin 的
    for prompt_dir in reversed(prompt_dirs):
        try:
            for md_file in prompt_dir.glob("*.md"):
                if md_file.name.lower() == "readme.md":
                    continue

                scenario_id = md_file.stem

                try:
                    with open(md_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    front_matter = None
                    if content.startswith("---"):
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
        except (FileNotFoundError, ValueError):
            raise
        except Exception as e:
            raise IOError(f"加载场景类型定义失败: {e}") from e

    if not scenarios:
        raise FileNotFoundError(f"在目录 {prompt_dirs} 中未找到有效的提示词文件")

    return scenarios


def _get_scenario_types(scenario_subdir: str) -> Dict[str, str]:
    """获取场景类型名称字典

    参数:
        scenario_subdir: 场景子目录名

    返回:
        Dict[str, str]: {scenario_id: scenario_name}
    """
    scenarios = _load_scenario_types(scenario_subdir)
    return {
        scenario_id: scenario_info["name"]
        for scenario_id, scenario_info in scenarios.items()
    }


def _load_prompt_from_file(scenario: str, scenario_subdir: str) -> str:
    """从文件加载提示词

    优先从数据目录加载，同名文件覆盖 builtin。

    参数:
        scenario: 场景类型
        scenario_subdir: 场景子目录名

    返回:
        str: 提示词内容（不包括 YAML front matter）
    """
    prompt_dirs = _get_prompt_dirs(scenario_subdir)

    # 按优先级从高到低查找（数据目录优先）
    for prompt_dir in prompt_dirs:
        prompt_file = prompt_dir / f"{scenario}.md"
        if prompt_file.exists():
            try:
                with open(prompt_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # 跳过 YAML front matter
                if content.startswith("---"):
                    end_marker = content.find("\n---", 4)
                    if end_marker != -1:
                        content = content[end_marker + 4 :]

                content = content.strip()
                if not content:
                    raise ValueError(f"提示词文件为空: {prompt_file}")
                return content
            except Exception as e:
                raise IOError(f"加载提示词文件失败 ({prompt_file}): {e}") from e

    raise FileNotFoundError(
        f"提示词文件不存在: {scenario}.md。请确保文件存在于 {prompt_dirs} 目录下。"
    )


def classify_user_request(
    user_input: Union[str, List[ContentBlock]],
    scenario_subdir: str,
    default_scenario_name: str = "通用任务",
    classification_context: str = "场景类型",
    difficulty_descriptions: Dict[str, str] | None = None,
) -> Tuple[str, str]:
    """使用 normal_llm 对用户需求进行分类

    参数:
        user_input: 用户输入的需求描述
        scenario_subdir: 场景子目录名
        default_scenario_name: 默认场景名称（用于显示）
        classification_context: 分类上下文描述（如"场景类型"或"开发场景类型"）
        difficulty_descriptions: 难度等级描述字典

    返回:
        Tuple[str, str]: (场景类型, 难度等级)
    """
    if difficulty_descriptions is None:
        difficulty_descriptions = {
            "easy": "简单问答、单步操作、明确的小任务（注意：如果涉及代码修改，任务难度至少为medium，不能评为easy）",
            "medium": "需要多步操作、需要理解上下文、涉及一定复杂度",
            "hard": "需要深度分析、多维度综合、需要专业知识和深入思考",
        }

    # 如果 user_input 是多模态内容，提取其中的文本
    if isinstance(user_input, list):
        text_parts = []
        for block in user_input:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        user_input = "\n".join(text_parts) if text_parts else "[多模态内容]"

    try:
        platform = PlatformRegistry().get_normal_platform()
        platform.set_suppress_output(False)

        scenarios = _load_scenario_types(scenario_subdir)

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

        difficulty_text = "\n".join(
            f"- {k}（{'简单' if k == 'easy' else '中等' if k == 'medium' else '困难'}）：{v}"
            for k, v in difficulty_descriptions.items()
        )

        classification_prompt = f"""请分析以下用户需求，判断其属于哪个{classification_context}，并评估任务难度。

用户需求：
{user_input}

可选场景类型：
{scenarios_text}

任务难度等级：
{difficulty_text}

请按以下格式返回（只返回这两行，不要包含其他内容）：
scenario: <场景类型>
difficulty: <难度等级>

如果无法明确判断场景类型，scenario 返回 default。
如果无法明确判断难度，difficulty 返回 medium。
"""

        response = platform.chat_until_success(classification_prompt)
        response = response.strip().lower()

        scenario = "default"
        difficulty = "medium"

        # 获取当前场景类型列表用于验证
        current_scenario_types = _get_scenario_types(scenario_subdir)

        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("scenario:"):
                scenario_value = line.split(":", 1)[1].strip()
                for scenario_type in current_scenario_types.keys():
                    if (
                        scenario_type in scenario_value
                        or scenario_value == scenario_type
                    ):
                        scenario = scenario_type
                        break
            elif line.startswith("difficulty:"):
                difficulty_value = line.split(":", 1)[1].strip()
                if difficulty_value in ["easy", "medium", "hard"]:
                    difficulty = difficulty_value

        difficulty_display = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(
            difficulty, difficulty
        )
        PrettyOutput.auto_print(
            f"📋 需求分类结果: {current_scenario_types.get(scenario, default_scenario_name)} ({scenario}) | 难度: {difficulty_display} ({difficulty})"
        )
        return scenario, difficulty

    except Exception:
        PrettyOutput.auto_print("⚠")
        return "default", "medium"


def get_system_prompt(
    scenario: str = "default", scenario_subdir: str = "agent_system"
) -> str:
    """根据场景类型获取对应的系统提示词

    参数:
        scenario: 场景类型
        scenario_subdir: 场景子目录名

    返回:
        str: 对应场景的完整系统提示词
    """
    return _load_prompt_from_file(scenario, scenario_subdir)
