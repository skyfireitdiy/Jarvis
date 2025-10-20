# -*- coding: utf-8 -*-
"""
TaskPlanner: 任务规划与子任务调度器

职责：
- 判断是否需要拆分任务
- 解析 <SUB_TASK> 列表
- 为每个子任务创建子Agent并执行
- 汇总所有子任务执行结果并写回父Agent上下文
"""

from typing import Any, List
import re

import yaml  # type: ignore

from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class TaskPlanner:
    """将 Agent 的任务规划逻辑封装为独立类，便于维护与复用。"""

    def __init__(self, agent: Any) -> None:
        """
        参数:
            agent: 父Agent实例（须提供以下能力）
              - _create_temp_model(system_prompt: str) -> BasePlatform
              - _build_child_agent_params(name: str, description: str) -> dict
              - name, session, plan, plan_depth, plan_max_depth 等属性
        """
        self.agent = agent

    def maybe_plan_and_dispatch(self, task_text: str) -> None:
        """
        当启用 agent.plan 时，调用临时模型评估是否需要拆分任务并执行子任务。
        - 若模型返回 <DONT_NEED/>，则直接返回不做任何修改；
        - 若返回 <SUB_TASK> 块，则解析每行以“- ”开头的子任务，逐个创建子Agent执行；
        - 将子任务与结果以结构化块写回到 agent.session.prompt，随后由主循环继续处理。
        """
        if not getattr(self.agent, "plan", False):
            return

        try:
            PrettyOutput.print("任务规划启动，评估是否需要拆分...", OutputType.INFO)
            planning_sys = (
                "你是一个任务规划助手。请判断是否需要拆分任务。\n"
                "当需要拆分时，仅按以下结构输出：\n"
                "<PLAN>\n- 子任务1\n- 子任务2\n</PLAN>\n"
                "要求：<PLAN> 内必须是有效 YAML 列表，仅包含字符串项；禁止输出任何额外解释。\n"
                "当不需要拆分时，仅输出：\n<DONT_NEED/>\n"
                "禁止输出任何额外解释。"
            )
            temp_model = self.agent._create_temp_model(planning_sys)
            plan_prompt = f"任务：\n{task_text}\n\n请严格按要求只输出结构化标签块。"
            plan_resp = temp_model.chat_until_success(plan_prompt)  # type: ignore
            if not plan_resp:
                PrettyOutput.print("任务规划模型未返回有效响应。", OutputType.WARNING)
                return
        except Exception as e:
            # 规划失败不影响主流程
            PrettyOutput.print(f"任务规划失败: {e}", OutputType.ERROR)
            return

        text = str(plan_resp).strip()
        # 不需要拆分
        if re.search(r"<\s*DONT_NEED\s*/\s*>", text, re.IGNORECASE):
            PrettyOutput.print("任务规划完成：无需拆分。", OutputType.SUCCESS)
            return

        # 解析 <SUB_TASK> 块
        m = re.search(
            r"<\s*PLAN\s*>\s*(.*?)\s*<\s*/\s*PLAN\s*>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        subtasks: List[str] = []
        if m:
            block = m.group(1)
            try:
                data = yaml.safe_load(block)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            s = item.strip()
                            if s:
                                subtasks.append(s)
                else:
                    PrettyOutput.print("任务规划警告：<PLAN> 内内容不是 YAML 列表，已忽略。", OutputType.WARNING)
            except Exception as e:
                PrettyOutput.print(f"任务规划警告：解析 <PLAN> YAML 失败：{e}", OutputType.WARNING)
        else:
            PrettyOutput.print("任务规划提示：未检测到 <PLAN> 块，视为无需拆分。", OutputType.INFO)

        if not subtasks:
            # 无有效子任务，直接返回
            PrettyOutput.print("任务规划警告：模型响应中未找到有效子任务。", OutputType.WARNING)
            return

        PrettyOutput.print(f"任务已拆分为 {len(subtasks)} 个子任务:", OutputType.SUCCESS)
        for i, st in enumerate(subtasks, 1):
            PrettyOutput.print(f"  {i}. {st}", OutputType.INFO)

        # 执行子任务
        executed_subtask_block_lines: List[str] = ["<PLAN>"]
        executed_subtask_block_lines += [f"- {t}" for t in subtasks]
        executed_subtask_block_lines.append("</PLAN>")

        results_lines: List[str] = []
        for i, st in enumerate(subtasks, 1):
            try:
                PrettyOutput.print(f"开始执行子任务 {i}/{len(subtasks)}: {st}", OutputType.INFO)
                child_kwargs = self.agent._build_child_agent_params(
                    name=f"{self.agent.name}-child-{i}",
                    description=f"子任务执行器: {st}",
                )
                # 使用父Agent的类创建子Agent，避免循环依赖
                child = self.agent.__class__(**child_kwargs)
                # 构造子任务执行提示，包含父任务与前置子任务结果，避免背景缺失
                subtask_block_text = "\n".join(executed_subtask_block_lines)
                if results_lines:
                    prev_results_block = "<PREVIOUS_SUB_TASK_RESULTS>\n" + "\n".join(results_lines) + "\n</PREVIOUS_SUB_TASK_RESULTS>"
                else:
                    prev_results_block = "<PREVIOUS_SUB_TASK_RESULTS />"
                child_prompt = join_prompts([
                    f"原始任务：\n{task_text}",
                    f"子任务规划：\n{subtask_block_text}",
                    f"前置子任务执行结果：\n{prev_results_block}",
                    f"当前子任务：{st}",
                    "请基于原始任务背景与前置结果执行当前子任务，避免重复工作；如需依赖前置产物请直接复用；如需为后续子任务提供数据，请妥善保存（可使用工具保存文件或记忆）。"
                ])
                child_result = child.run(child_prompt)
                result_text = "" if child_result is None else str(child_result)
                # 防止极端长输出导致污染，这里不做截断，交由上层摘要策略控制
                results_lines.append(f"- 子任务{i}: {st}\n  结果: {result_text}")
                PrettyOutput.print(f"子任务 {i}/{len(subtasks)} 执行完成。", OutputType.SUCCESS)
            except Exception as e:
                results_lines.append(f"- 子任务{i}: {st}\n  结果: 执行失败，原因: {e}")
                PrettyOutput.print(f"子任务 {i}/{len(subtasks)} 执行失败: {e}", OutputType.ERROR)

        subtask_block = "\n".join(executed_subtask_block_lines)
        results_block = "<SUB_TASK_RESULTS>\n" + "\n".join(results_lines) + "\n</SUB_TASK_RESULTS>"

        PrettyOutput.print("所有子任务执行完毕，正在整合结果...", OutputType.INFO)
        # 先对所有子任务结果进行简要自动汇总，便于父Agent继续整合
        summary_block = "<RESULT_SUMMARY>\n无摘要（将直接使用结果详情继续）\n</RESULT_SUMMARY>"
        try:
            summarizing_sys = (
                "你是一个任务结果整合助手。请根据提供的原始任务、子任务清单与子任务执行结果，"
                "生成简明扼要的汇总与关键结论，突出已完成项、遗留风险与下一步建议。"
                "严格仅输出以下结构：\n"
                "<RESULT_SUMMARY>\n"
                "…你的简要汇总…\n"
                "</RESULT_SUMMARY>\n"
                "不要输出其他任何解释。"
            )
            temp_model2 = self.agent._create_temp_model(summarizing_sys)
            sum_prompt = (
                f"原始任务：\n{task_text}\n\n"
                f"子任务规划：\n{subtask_block}\n\n"
                f"子任务执行结果：\n{results_block}\n\n"
                "请按要求仅输出汇总块。"
            )
            sum_resp = temp_model2.chat_until_success(sum_prompt)  # type: ignore
            if isinstance(sum_resp, str) and sum_resp.strip():
                s = sum_resp.strip()
                if not re.search(r"<\s*RESULT_SUMMARY\s*>", s, re.IGNORECASE):
                    s = f"<RESULT_SUMMARY>\n{s}\n</RESULT_SUMMARY>"
                summary_block = s
        except Exception:
            # 汇总失败不影响主流程，继续使用默认占位
            pass

        # 合并回父Agent的 prompt，父Agent将基于汇总与详情继续执行
        try:
            self.agent.session.prompt = join_prompts(
                [
                    f"原始任务：\n{task_text}",
                    f"子任务规划：\n{subtask_block}",
                    f"子任务结果汇总：\n{summary_block}",
                    f"子任务执行结果：\n{results_block}",
                    "请基于上述子任务结果整合并完成最终输出。",
                ]
            )
        except Exception:
            # 回退拼接
            self.agent.session.prompt = (
                f"{task_text}\n\n{subtask_block}\n\n{summary_block}\n\n{results_block}\n\n"
                "请基于上述子任务结果整合并完成最终输出。"
            )