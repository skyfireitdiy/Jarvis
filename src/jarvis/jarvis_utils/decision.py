# -*- coding: utf-8 -*-
"""决策调用统一入口。

项目中存在大量"给模型一批候选 + 任务描述，让模型做选择/打分"的决策场景。
这些场景默认走各自的现有流程（normal/cheap 模型 + 文本协议 + 正则解析）。

当模型组中配置了结构化评估模型（llm_groups 中的 eval_llm）时，这些场景
可以改走该模型，以获得更稳定的结构化输出。

本模块提供统一入口，避免在各业务处散落"是否配置了评估模型"的判断：

- get_eval_platform(): 获取结构化评估模型实例，未配置时返回 None
- decide(): 有评估模型则用它，否则执行 fallback，保证未配置时行为零变化
"""

from typing import Any, Callable, Dict, Optional

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.config import is_eval_model_configured
from jarvis.jarvis_utils.output import PrettyOutput


def get_eval_platform() -> Optional[BasePlatform]:
    """获取结构化评估模型实例。

    未配置 eval_llm 或创建失败时返回 None，调用方据此回退现有流程。

    返回:
        Optional[BasePlatform]: 评估模型实例，未配置时为 None
    """
    if not is_eval_model_configured():
        return None
    try:
        registry = PlatformRegistry.get_global_platform_registry()
        return registry.get_eval_platform()
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  创建结构化评估模型失败，回退现有流程: {e}")
        return None


def decide(
    prompt: str,
    fallback: Callable[[], Any],
    *,
    suppress_output: bool = True,
) -> Any:
    """执行一次决策调用。

    配置了结构化评估模型时，用该模型执行 prompt 并返回其文本响应；
    否则调用 fallback 走现有流程。

    参数:
        prompt: 决策提示词
        fallback: 未配置评估模型时执行的现有流程，返回任意结果
        suppress_output: 使用评估模型时是否抑制输出（默认抑制）

    返回:
        Any: 评估模型的文本响应（str），或 fallback 的返回值
    """
    platform = get_eval_platform()
    if platform is None:
        return fallback()

    try:
        platform.set_suppress_output(suppress_output)
        response = platform.chat_until_success(prompt).strip()
        if not response:
            PrettyOutput.auto_print("⚠️  结构化评估模型返回为空，回退现有流程")
            return fallback()
        return response
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  结构化评估模型调用失败，回退现有流程: {e}")
        return fallback()
    finally:
        try:
            platform.delete_chat()
        except Exception:
            pass


def decide_json(
    prompt: str,
    fallback: Callable[[], Any],
    *,
    suppress_output: bool = True,
) -> Any:
    """执行一次决策调用并解析 JSON 结果。

    与 decide 相同，但会把模型响应解析为 JSON 对象；解析失败时回退现有流程。

    参数:
        prompt: 决策提示词（应要求模型输出 JSON）
        fallback: 未配置评估模型或解析失败时执行的现有流程
        suppress_output: 使用评估模型时是否抑制输出（默认抑制）

    返回:
        Any: 解析出的 JSON 对象，或 fallback 的返回值
    """
    import json

    from jarvis.jarvis_utils.utils import extract_json_from_text

    platform = get_eval_platform()
    if platform is None:
        return fallback()

    try:
        platform.set_suppress_output(suppress_output)
        response = platform.chat_until_success(prompt).strip()
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  结构化评估模型调用失败，回退现有流程: {e}")
        return fallback()
    finally:
        try:
            platform.delete_chat()
        except Exception:
            pass

    if not response:
        PrettyOutput.auto_print("⚠️  结构化评估模型返回为空，回退现有流程")
        return fallback()

    json_str, _ = extract_json_from_text(response)
    if not json_str:
        PrettyOutput.auto_print("⚠️  结构化评估模型未返回合法 JSON，回退现有流程")
        return fallback()

    try:
        return json.loads(json_str)
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  解析结构化评估结果失败，回退现有流程: {e}")
        return fallback()


def decide_choice(
    task: str,
    candidates: Dict[str, str],
    fallback: Callable[[], Any],
    *,
    max_select: int = 3,
    min_confidence: float = 0.5,
) -> Any:
    """从一批候选中选出与任务最相关的若干项。

    结构化评估模型（如 Jev）只接受 JSON 协议、返回结构化答案，无法直接消费
    自然语言提示词。本函数负责把"候选列表 + 任务描述"翻译成该模型能理解的
    结构化问题，再把答案翻译回候选 ID 列表，从而让决策场景真正用上评估模型。

    实现方式：为每个候选构造一个 noul（是/否）问题，一次请求拿到所有候选的
    相关概率，再按概率降序取前 max_select 个。

    参数:
        task: 任务描述
        candidates: 候选映射 {候选ID: 候选描述}，ID 会原样返回给调用方
        fallback: 未配置评估模型或调用失败时执行的现有流程
        max_select: 最多返回多少个候选（默认 3）
        min_confidence: 相关概率阈值，低于该值的候选不返回（默认 0.5）

    返回:
        Any: 选中的候选 ID 列表（List[str]），或 fallback 的返回值
    """
    import json

    platform = get_eval_platform()
    if platform is None or not candidates:
        return fallback()

    # 为每个候选构造一个 noul 问题，问题 ID 直接用候选 ID
    questions: Dict[str, Any] = {}
    for cid, desc in candidates.items():
        questions[str(cid)] = {
            "type": "noul",
            "instructions": (
                f"以下候选是否与任务高度相关、应当被选中？候选说明：{desc}"
            ),
        }

    payload = {
        "state": f"任务描述：{task}",
        "questions": questions,
    }

    try:
        platform.set_suppress_output(True)
        response = platform.chat_until_success(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  结构化评估模型调用失败，回退现有流程: {e}")
        return fallback()
    finally:
        try:
            platform.delete_chat()
        except Exception:
            pass

    if not response:
        PrettyOutput.auto_print("⚠️  结构化评估模型返回为空，回退现有流程")
        return fallback()

    # 从可读文本中解析每个候选的 noul 概率
    scores = _parse_noul_scores(response)
    if not scores:
        PrettyOutput.auto_print("⚠️  未能解析结构化评估结果，回退现有流程")
        return fallback()

    # 按概率降序取前 max_select 个，并过滤低于阈值的候选
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    picked = [cid for cid, score in ranked[:max_select] if score >= min_confidence]
    if not picked:
        PrettyOutput.auto_print("⚠️  结构化评估未选出任何候选，回退现有流程")
        return fallback()
    return picked


def _parse_noul_scores(response: str) -> Dict[str, float]:
    """从 Jev 的可读答案文本中解析各问题的 noul 概率。

    答案文本形如：
        - <候选ID> [noul]: 0.96
        - <候选ID> [noul]: 0.03

    参数:
        response: Jev 返回的可读答案文本

    返回:
        Dict[str, float]: {候选ID: 概率}，解析失败时返回空字典
    """
    import re

    pattern = re.compile(r"^-\s*(.+?)\s*\[noul\]:\s*([0-9]*\.?[0-9]+)\s*$")
    scores: Dict[str, float] = {}
    for line in response.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        try:
            scores[match.group(1)] = float(match.group(2))
        except ValueError:
            continue
    return scores
