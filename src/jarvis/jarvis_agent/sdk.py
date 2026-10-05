"""Jarvis Agent SDK 增强模块。

提供高层编排 API，让开发者能：
- 编排多 Agent：``run_agents_parallel``（并行）/ ``pipeline``（串行管道）
- 结构化输出：``run_structured``（按 JSON schema 返回）
- 生命周期回调：``on_event``（复用 event_bus 订阅 Agent 生命周期事件）

设计原则：纯增量、复用现有 ``Agent``/``CodeAgent`` 与 ``event_bus`` 机制，
不修改任何现有核心逻辑，导入本模块无副作用。

用法示例::

    from jarvis.jarvis_agent.sdk import run_agents_parallel, pipeline, run_structured
    from jarvis.jarvis_code_agent.code_agent import CodeAgent

    # 并行运行两个独立 Agent
    results = run_agents_parallel([
        (CodeAgent(non_interactive=True), "分析 src/ 目录结构"),
        (CodeAgent(non_interactive=True), "统计测试用例数量"),
    ])

    # 串行管道：前一个 Agent 的输出作为后一个的输入
    results = pipeline([
        (CodeAgent(non_interactive=True), lambda prev: f"基于以下内容写摘要: {prev}"),
        (CodeAgent(non_interactive=True), lambda prev: f"把摘要翻译成英文: {prev}"),
    ], initial_input="原始文本")
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union, cast

# 生命周期事件名（与 jarvis_agent.events 保持一致，避免强依赖）
EVENT_TASK_STARTED = "task_started"
EVENT_TASK_COMPLETED = "task_completed"
EVENT_BEFORE_SUMMARY = "before_summary"
EVENT_AFTER_SUMMARY = "after_summary"
EVENT_BEFORE_MODEL_CALL = "before_model_call"
EVENT_AFTER_MODEL_CALL = "after_model_call"

# 单个编排单元：Agent 实例 + 任务（字符串或"接收前序输出"的函数）
AgentTask = Tuple[Any, Union[str, Callable[[str], str]]]


def run_agents_parallel(
    agents: Sequence[AgentTask],
    max_workers: Optional[int] = None,
) -> List[Optional[str]]:
    """并行运行多个独立 Agent 任务。

    参数:
        agents: ``(agent, task)`` 元组列表。task 为字符串任务描述。
        max_workers: 线程池大小，默认等于任务数。

    返回:
        与 ``agents`` 顺序对应的结果列表（每个元素为对应 Agent 的 ``run()`` 返回值）。

    说明:
        每个 Agent 在独立线程中运行，互不干扰。若单个 Agent 抛异常，
        该位置的结果为 ``None``，其余 Agent 不受影响。
    """
    if not agents:
        return []

    def _run_one(item: AgentTask) -> Optional[str]:
        agent, task = item
        if not isinstance(task, str):
            raise TypeError("run_agents_parallel 的 task 必须是字符串")
        try:
            return agent.run(task)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers or len(agents)) as executor:
        return list(executor.map(_run_one, agents))


def pipeline(
    stages: Sequence[AgentTask],
    initial_input: str = "",
) -> List[Optional[str]]:
    """串行运行 Agent 管道：前一个 Agent 的输出作为后一个的输入。

    参数:
        stages: ``(agent, task)`` 元组列表。task 可为：
            - 字符串：固定任务描述
            - 可调用对象 ``lambda prev_output: str``：接收前一个 Agent 的输出
        initial_input: 首个 stage 的 task 为可调用对象时，传入的初始输入。

    返回:
        每个 stage 的输出列表（顺序与 ``stages`` 一致）。

    说明:
        管道是串行的，任一 stage 抛异常会中断后续 stage（该位置返回 ``None``）。
    """
    results: List[Optional[str]] = []
    prev_output: str = initial_input

    for agent, task in stages:
        if isinstance(task, str):
            task_str = task
        else:
            task_fn = cast(Callable[[str], str], task)
            task_str = task_fn(prev_output)
        try:
            output = agent.run(task_str)
            results.append(output)
            if output is not None:
                prev_output = output
        except Exception:
            results.append(None)
            break

    return results


def run_structured(
    agent: Any,
    task: str,
    schema: Optional[Dict[str, Any]] = None,
) -> Any:
    """让 Agent 输出结构化 JSON 并解析返回。

    参数:
        agent: Agent 实例（通常为 ``CodeAgent``）。
        task: 任务描述。会自动附加"仅输出 JSON"的指令。
        schema: 可选的 JSON schema 描述（dict），用于约束输出结构。

    返回:
        解析后的 Python 对象（dict / list / 标量）。

    说明:
        在任务中要求 Agent 只输出 JSON，再从返回文本中提取 JSON 块解析。
        若解析失败抛 ``ValueError``。schema 仅作为任务提示的一部分，
        不做严格校验（保持与现有非交互输出机制兼容）。
    """
    schema_hint = ""
    if schema:
        schema_hint = (
            "\n\n输出必须符合以下 JSON 结构（字段名与类型必须一致）：\n"
            + json.dumps(schema, ensure_ascii=False, indent=2)
        )

    structured_task = (
        f"{task}\n\n请严格只输出一个合法的 JSON 对象/数组作为最终结果，"
        f"不要输出任何其他文字、解释或 Markdown 代码块标记。{schema_hint}"
    )

    output = agent.run(structured_task)
    if output is None:
        raise ValueError("Agent 未返回任何输出，无法解析结构化结果")

    return _extract_json(output)


def _extract_json(text: str) -> Any:
    """从文本中提取并解析 JSON（容忍 Markdown 代码块包裹与前后杂文本）。"""
    stripped = text.strip()

    # 去掉可能的 Markdown 代码块围栏
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()

    # 先尝试直接解析
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 回退：提取第一个 JSON 对象或数组
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue

    raise ValueError(f"无法从 Agent 输出中解析 JSON: {text[:200]}")


def on_event(agent: Any, event: str, callback: Callable[..., None]) -> None:
    """订阅 Agent 生命周期事件（复用 event_bus）。

    参数:
        agent: Agent 实例（需有 ``event_bus`` 属性）。
        event: 事件名，如 ``task_completed`` / ``after_summary``。
        callback: 回调函数，接收事件负载（通常含 ``agent=`` 关键字）。

    用法示例::

        from jarvis.jarvis_agent.sdk import on_event, EVENT_TASK_COMPLETED

        def on_done(agent=None, **kw):
            print(f"Agent {agent.name} 完成任务")

        on_event(agent, EVENT_TASK_COMPLETED, on_done)
    """
    if not hasattr(agent, "event_bus"):
        raise AttributeError("Agent 没有 event_bus 属性，无法订阅事件")
    agent.event_bus.subscribe(event, callback)
