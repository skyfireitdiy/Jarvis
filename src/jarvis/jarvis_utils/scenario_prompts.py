# -*- coding: utf-8 -*-
"""场景提示词公共模块

提供场景分类、难度评估和系统提示词加载功能。
支持从 builtin 目录和数据目录（~/.jarvis/prompts/）双路径加载，
用户扩展文件可覆盖 builtin 同名文件。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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
) -> Tuple[str, str, float]:
    """使用 normal_llm 对用户需求进行分类

    参数:
        user_input: 用户输入的需求描述
        scenario_subdir: 场景子目录名
        default_scenario_name: 默认场景名称（用于显示）
        classification_context: 分类上下文描述（如"场景类型"或"开发场景类型"）
        difficulty_descriptions: 难度等级描述字典

    返回:
        Tuple[str, str, float]: (场景类型, 难度等级, 推荐采样温度)
    """
    # 任务性质 → 温度档位（只让分类模型选档，数值在代码内映射并做范围保护）。
    # 档位依据"需要确定性还是创意"而非难度：改码/修 bug 偏 low，创意/开放偏 high。
    temperature_descriptions = {
        "low": "需精确、守规、结果可预期：精确修改、bug 修复、重构、严格遵循规范/规则的改动",
        "medium": "常规多步任务、一般开发与问答（默认）",
        "high": "需创意与发散：创意写作、文案润色、头脑风暴、开放式方案探索",
    }
    # 档位 → 采样温度（刻意避开过低值，避免陷入大段重复）
    temperature_map = {"low": 0.5, "medium": 0.7, "high": 1.0}

    if difficulty_descriptions is None:
        difficulty_descriptions = {
            "easy": "简易问答、单步操作、明晰小务（涉代码修改者，难度至少为medium，不得评easy）",
            "medium": "需多步操作、须理解上下文、具一定复杂度",
            "hard": "需深度分析、多维综合、赖专门知识与深思",
        }

    # 如果 user_input 是多模态内容，提取其中的文本
    if isinstance(user_input, list):
        text_parts = []
        for block in user_input:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        user_input = "\n".join(text_parts) if text_parts else "[多模态内容]"

    # 优先用结构化评估模型（eval_llm，如 Jev）做分类：它只接受 JSON 协议、
    # 返回结构化答案，无法消费自然语言提示词，故走专用协议转换；
    # 未配置评估模型或调用失败时，回退到 cheap/normal 文本模型流程。
    eval_result = _classify_with_eval_model(
        user_input,
        scenario_subdir,
        classification_context,
        difficulty_descriptions,
        temperature_descriptions,
        temperature_map,
    )
    if eval_result is not None:
        scenario, difficulty, temperature = eval_result
        _print_classification_result(
            scenario_subdir, scenario, difficulty, temperature, default_scenario_name
        )
        return scenario, difficulty, temperature

    try:
        # 未配置 eval 时：优先使用 cheap 档以节省成本；未配置 cheap 时回退 normal
        registry = PlatformRegistry()
        try:
            platform = registry.get_cheap_platform()
        except Exception:
            platform = registry.get_normal_platform()
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

        temperature_text = "\n".join(
            f"- {k}（{'偏精确' if k == 'low' else '均衡' if k == 'medium' else '偏创意'}）：{v}"
            for k, v in temperature_descriptions.items()
        )

        classification_prompt = f"""析用户所请，判其属何{classification_context}，量任之难易，并择所需温度档。

用户所请：
{user_input}

可选场景：
{scenarios_text}

难度等级：
{difficulty_text}

所需温度档（依任务性质而非难度选择）：
{temperature_text}

请按以下格式回答（仅此三行，不要夹杂其他内容）：
scenario: <场景>
difficulty: <难度>
temperature: <档位>

如果难以确定场景，scenario 返回 default。
如果难以确定难度，difficulty 返回 medium。
如果难以确定温度，temperature 返回 medium。
"""

        response = platform.chat_until_success(classification_prompt)
        response = response.strip().lower()

        scenario = "default"
        difficulty = "medium"
        temperature = 0.7

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
            elif line.startswith("temperature:"):
                temperature_value = line.split(":", 1)[1].strip()
                if temperature_value in temperature_map:
                    temperature = temperature_map[temperature_value]

        _print_classification_result(
            scenario_subdir, scenario, difficulty, temperature, default_scenario_name
        )
        return scenario, difficulty, temperature

    except Exception:
        PrettyOutput.auto_print("⚠")
        return "default", "medium", 0.7


def _print_classification_result(
    scenario_subdir: str,
    scenario: str,
    difficulty: str,
    temperature: float,
    default_scenario_name: str,
) -> None:
    """打印需求分类结果（场景/难度/温度）。

    参数:
        scenario_subdir: 场景子目录名
        scenario: 场景类型 ID
        difficulty: 难度等级（easy/medium/hard）
        temperature: 采样温度数值
        default_scenario_name: 默认场景名称（用于显示）
    """
    try:
        current_scenario_types = _get_scenario_types(scenario_subdir)
    except Exception:
        current_scenario_types = {}
    difficulty_display = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(
        difficulty, difficulty
    )
    temperature_display = {0.5: "偏精确", 0.7: "均衡", 1.0: "偏创意"}.get(
        temperature, temperature
    )
    PrettyOutput.auto_print(
        f"📋 需求分类结果: {current_scenario_types.get(scenario, default_scenario_name)} ({scenario}) | 难度: {difficulty_display} ({difficulty}) | 温度: {temperature_display} ({temperature})"
    )


def _classify_with_eval_model(
    user_input: str,
    scenario_subdir: str,
    classification_context: str,
    difficulty_descriptions: Dict[str, str],
    temperature_descriptions: Dict[str, str],
    temperature_map: Dict[str, float],
) -> Optional[Tuple[str, str, float]]:
    """用结构化评估模型（eval_llm，如 Jev）对用户需求分类。

    结构化评估模型只接受 JSON 协议（state + questions），无法消费自然语言
    提示词，故这里把"场景/难度/温度"翻译成三个 choice 问题，再解析其返回的
    可读答案文本。未配置评估模型、调用失败或解析失败时返回 None，由调用方
    回退到文本模型流程。

    参数:
        user_input: 用户输入的需求描述（已转为纯文本）
        scenario_subdir: 场景子目录名
        classification_context: 分类上下文描述
        difficulty_descriptions: 难度等级描述字典
        temperature_descriptions: 温度档位描述字典
        temperature_map: 温度档位 → 数值映射

    返回:
        Optional[Tuple[str, str, float]]: (场景类型, 难度等级, 采样温度)，
        未配置评估模型或失败时返回 None
    """
    from jarvis.jarvis_utils.decision import get_eval_platform

    platform = get_eval_platform()
    if platform is None:
        return None

    try:
        scenarios = _load_scenario_types(scenario_subdir)
        current_scenario_types = {
            scenario_id: scenario_info["name"]
            for scenario_id, scenario_info in scenarios.items()
        }

        # 场景候选：以 scenario_id 为 criteria 键，名称+描述作为说明
        scenario_criteria: Dict[str, str] = {}
        for scenario_id, scenario_info in scenarios.items():
            scenario_criteria[scenario_id] = (
                f"{scenario_info['name']}：{scenario_info['description']}"
            )

        # 难度候选：easy/medium/hard
        difficulty_criteria = {
            k: f"{'简单' if k == 'easy' else '中等' if k == 'medium' else '困难'}：{v}"
            for k, v in difficulty_descriptions.items()
        }

        # 温度档位候选：low/medium/high
        temperature_criteria = {
            k: f"{'偏精确' if k == 'low' else '均衡' if k == 'medium' else '偏创意'}：{v}"
            for k, v in temperature_descriptions.items()
        }

        payload = {
            "state": f"用户所请：\n{user_input}",
            "questions": {
                "scenario": {
                    "type": "choice",
                    "instructions": (
                        f"判断用户所请属于哪种{classification_context}。"
                        "若难以确定，选择 default。"
                    ),
                    "criteria": scenario_criteria,
                },
                "difficulty": {
                    "type": "choice",
                    "instructions": "评估该任务的难度等级。若难以确定，选择 medium。",
                    "criteria": difficulty_criteria,
                },
                "temperature": {
                    "type": "choice",
                    "instructions": (
                        "依据任务性质（需精确还是需创意，而非难度）"
                        "选择所需采样温度档。若难以确定，选择 medium。"
                    ),
                    "criteria": temperature_criteria,
                },
            },
        }

        import json

        platform.set_suppress_output(True)
        try:
            response = platform.chat_until_success(
                json.dumps(payload, ensure_ascii=False)
            )
        finally:
            try:
                platform.delete_chat()
            except Exception:
                pass

        if not response:
            PrettyOutput.auto_print("⚠️ 结构化评估模型返回为空，回退文本模型分类")
            return None

        answers = _parse_choice_answers(response)
        if not answers:
            PrettyOutput.auto_print("⚠️ 未能解析结构化评估结果，回退文本模型分类")
            return None

        scenario = "default"
        scenario_value = answers.get("scenario", "")
        for scenario_type in current_scenario_types.keys():
            if scenario_type in scenario_value or scenario_value == scenario_type:
                scenario = scenario_type
                break

        difficulty = "medium"
        difficulty_value = answers.get("difficulty", "")
        if difficulty_value in ("easy", "medium", "hard"):
            difficulty = difficulty_value

        temperature = 0.7
        temperature_value = answers.get("temperature", "")
        if temperature_value in temperature_map:
            temperature = temperature_map[temperature_value]

        return scenario, difficulty, temperature
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 结构化评估模型分类失败，回退文本模型分类: {e}")
        return None


def _parse_choice_answers(response: str) -> Dict[str, str]:
    """从结构化评估模型的可读答案文本中解析各 choice 问题的取值。

    答案文本形如：
        - scenario [choice]: 通用开发
        - difficulty [choice]: medium
        - temperature [choice]: low

    参数:
        response: 结构化评估模型返回的可读答案文本

    返回:
        Dict[str, str]: {问题ID: 选项值}，解析失败时返回空字典
    """
    import re

    pattern = re.compile(r"^-\s*(.+?)\s*\[choice\]:\s*(.+?)\s*$")
    answers: Dict[str, str] = {}
    for line in response.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        answers[match.group(1)] = match.group(2)
    return answers


def _front_matter_dict(
    prompt_dirs: List[Path], scenario: str
) -> Optional[Dict[str, Any]]:
    """读取首个存在的场景文件并解析其 front matter

    用于检测场景文件是否声明继承 default 的共享核心（inherit_core: true）。

    参数:
        prompt_dirs: 提示词目录列表（优先级从高到低）
        scenario: 场景文件名（不含 .md 后缀）

    返回:
        Optional[Dict]: front matter 字典；文件不存在或解析失败返回 None
    """
    for prompt_dir in prompt_dirs:
        prompt_file = prompt_dir / f"{scenario}.md"
        if prompt_file.exists():
            try:
                content = prompt_file.read_text(encoding="utf-8")
                if content.startswith("---"):
                    end_marker = content.find("\n---", 4)
                    if end_marker != -1:
                        front_matter = yaml.safe_load(content[4:end_marker])
                        if isinstance(front_matter, dict):
                            return front_matter
            except Exception:
                pass
            return {}
    return None


def get_system_prompt(
    scenario: str = "default", scenario_subdir: str = "agent_system"
) -> str:
    """根据场景类型获取对应的系统提示词

    - 未声明继承的场景文件：原样返回（向后兼容，用户自定义文件不受影响）。
    - 声明了 ``inherit_core: true`` 的场景文件：返回"场景正文 + default 场景的共享核心"，
      使公共段落只维护在 default 一处，避免各场景复制漂移。

    参数:
        scenario: 场景类型
        scenario_subdir: 场景子目录名

    返回:
        str: 对应场景的完整系统提示词
    """
    content = _load_prompt_from_file(scenario, scenario_subdir)
    if scenario == "default":
        return content

    prompt_dirs = _get_prompt_dirs(scenario_subdir)
    front_matter = _front_matter_dict(prompt_dirs, scenario)
    if not (front_matter and front_matter.get("inherit_core", False)):
        return content

    # 共享核心从 default 正文的 core_marker 章节起（见 default 文件的 front matter）。
    # 无 core_marker 时退化为取 default 正文第一个 "## " 章节。
    base = _load_prompt_from_file("default", scenario_subdir)
    default_fm = _front_matter_dict(prompt_dirs, "default") or {}
    marker = default_fm.get("core_marker")
    if marker and marker in base:
        core = base[base.find(marker) :]
    else:
        idx = base.find("\n## ")
        core = base[idx + 1 :] if idx != -1 else base
    return content.rstrip() + "\n\n" + core
