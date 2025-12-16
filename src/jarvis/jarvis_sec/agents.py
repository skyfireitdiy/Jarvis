# -*- coding: utf-8 -*-
"""Agent创建和订阅模块"""

from typing import Any, Dict, Optional

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_sec.prompts import build_summary_prompt
from jarvis.jarvis_sec.prompts import get_cluster_summary_prompt
from jarvis.jarvis_sec.prompts import get_cluster_system_prompt
from jarvis.jarvis_sec.prompts import get_review_summary_prompt
from jarvis.jarvis_sec.prompts import get_review_system_prompt
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.tag import ot


def subscribe_summary_event(agent: Agent) -> Dict[str, str]:
    """订阅Agent摘要事件"""
    summary_container: Dict[str, str] = {"text": ""}
    try:
        from jarvis.jarvis_agent.events import AFTER_SUMMARY as _AFTER_SUMMARY
    except Exception:
        _AFTER_SUMMARY = None  # type: ignore

    if _AFTER_SUMMARY:

        def _on_after_summary(**kwargs: Any) -> None:
            try:
                summary_container["text"] = str(kwargs.get("summary", "") or "")
            except Exception:
                summary_container["text"] = ""

        try:
            agent.event_bus.subscribe(_AFTER_SUMMARY, _on_after_summary)
        except Exception:
            pass
    return summary_container


def create_analysis_agent(
    task_id: str, llm_group: Optional[str], force_save_memory: bool = False
) -> Agent:
    """创建分析Agent"""
    system_prompt = f"""
# 单Agent安全分析约束
- 你的核心任务是评估代码的安全问题，目标：针对本候选问题进行证据核实、风险评估与修复建议补充，查找漏洞触发路径，确认在某些条件下会触发；以此来判断是否是漏洞。
- **必须进行调用路径推导**：
  - 对于每个候选问题，必须明确推导从可控输入到缺陷代码的完整调用路径。
  - 调用路径推导必须包括：
    1. 识别可控输入的来源（例如：用户输入、网络数据、文件读取、命令行参数等）
    2. 追踪数据流：从输入源开始，逐步追踪数据如何传递到缺陷代码位置
    3. 识别调用链：明确列出从入口函数到缺陷代码的所有函数调用序列（例如：main() -> parse_input() -> process_data() -> vulnerable_function()）
    4. 分析每个调用点的数据校验情况：检查每个函数是否对输入进行了校验、边界检查或安全检查
    5. 确认触发条件：明确说明在什么条件下，未校验或恶意输入能够到达缺陷代码位置
  - 如果无法推导出完整的调用路径，或者所有调用路径都有充分的保护措施，则应该判定为误报。
  - 调用路径推导必须在分析过程中明确展示，不能省略或假设。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- **调用路径追溯要求**：
  - 必须向上追溯所有可能的调用者，查看完整的调用路径，以确认风险是否真实存在。
  - 使用 read_code 和 execute_script 工具查找函数的调用者（例如：使用 grep 搜索函数名，查找所有调用该函数的位置）。
  - 对于每个调用者，必须检查其是否对输入进行了校验。
  - 如果发现任何调用路径未做校验，必须明确记录该路径。
  - 例如：一个函数存在空指针解引用风险，必须检查所有调用者。如果所有调用者均能确保传入的指针非空，则该风险在当前代码库中可能不会实际触发；但如果存在任何调用者未做校验，则风险真实存在。
- 若多条告警位于同一文件且行号相距不远，可一次性读取共享上下文，对这些相邻告警进行联合分析与判断；但仍需避免无关扩展与大范围遍历。
- 禁止修改任何文件或执行写操作命令（rm/mv/cp/echo >、sed -i、git、patch、chmod、chown 等）；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
- **记忆使用**：
  - 在分析过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是与当前分析函数相关的记忆。
  - 如果有必要，使用 save_memory 工具保存每个函数的分析要点，使用函数名作为 tag（例如：函数名、文件名等）。
  - 记忆内容示例：某个函数的指针已经判空、某个函数已有输入校验、某个函数的调用路径分析结果等。
  - 这样可以避免重复分析，提高效率，并保持分析的一致性。
- 完成对本批次候选问题的判断后，主输出仅打印结束符 {ot("!!!COMPLETE!!!")}，不要输出其他任何内容。任务总结将会在后面的交互中被询问。
""".strip()

    agent_kwargs: Dict[str, Any] = dict(
        system_prompt=system_prompt,
        name=task_id,
        auto_complete=True,
        need_summary=True,
        summary_prompt=build_summary_prompt(),
        non_interactive=True,
        in_multi_agent=False,
        use_methodology=False,
        use_analysis=False,
        output_handler=[ToolRegistry()],
        force_save_memory=force_save_memory,
        use_tools=["read_code", "execute_script", "save_memory", "retrieve_memory"],
    )
    if llm_group:
        agent_kwargs["model_group"] = llm_group
    return Agent(**agent_kwargs)


def create_review_agent(
    current_review_num: int,
    llm_group: Optional[str],
) -> Agent:
    """创建复核Agent"""
    review_system_prompt = get_review_system_prompt()
    review_summary_prompt = get_review_summary_prompt()

    review_task_id = f"JARVIS-SEC-Review-Batch-{current_review_num}"
    review_agent_kwargs: Dict[str, Any] = dict(
        system_prompt=review_system_prompt,
        name=review_task_id,
        auto_complete=True,
        need_summary=True,
        summary_prompt=review_summary_prompt,
        non_interactive=True,
        in_multi_agent=False,
        use_methodology=False,
        use_analysis=False,
        output_handler=[ToolRegistry()],
        use_tools=["read_code", "execute_script", "retrieve_memory", "save_memory"],
    )
    if llm_group:
        review_agent_kwargs["model_group"] = llm_group
    return Agent(**review_agent_kwargs)


def create_cluster_agent(
    file: str,
    chunk_idx: int,
    llm_group: Optional[str],
    force_save_memory: bool = False,
) -> Agent:
    """创建聚类Agent"""
    cluster_system_prompt = get_cluster_system_prompt()
    cluster_summary_prompt = get_cluster_summary_prompt()

    agent_kwargs_cluster: Dict[str, Any] = dict(
        system_prompt=cluster_system_prompt,
        name=f"JARVIS-SEC-Cluster::{file}::batch{chunk_idx}",
        auto_complete=True,
        need_summary=True,
        summary_prompt=cluster_summary_prompt,
        non_interactive=True,
        in_multi_agent=False,
        use_methodology=False,
        use_analysis=False,
        output_handler=[ToolRegistry()],
        force_save_memory=force_save_memory,
        use_tools=["read_code", "execute_script", "save_memory", "retrieve_memory"],
    )
    if llm_group:
        agent_kwargs_cluster["model_group"] = llm_group
    return Agent(**agent_kwargs_cluster)
