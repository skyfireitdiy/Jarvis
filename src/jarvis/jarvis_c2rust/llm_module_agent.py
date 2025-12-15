# -*- coding: utf-8 -*-
"""
LLM 驱动的 Rust Crate 模块规划 Agent

目标:
- 复用 scanner 中的 find_root_function_ids 与调用图信息，构造"以根函数为起点"的上下文
- 通过 jarvis_agent.Agent 调用 LLM，基于上下文生成 Rust crate 的目录规划（JSON）

设计要点:
- 与现有 scanner/cli 解耦，最小侵入新增模块
- 使用 jarvis_agent.Agent 的平台与系统提示管理能力，但不走完整工具循环，直接进行一次性对话生成
- 对输出格式进行强约束：仅输出 JSON，无解释文本

用法:
  from jarvis.jarvis_c2rust.llm_module_agent import plan_crate_json_llm
  PrettyOutput.auto_print(plan_crate_json_llm(project_root="."))

CLI 集成建议:
  可在 jarvis_c2rust/cli.py 中新增 llm-plan 子命令调用本模块的 plan_crate_json_llm（已独立封装，便于后续补充）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Union

from jarvis.jarvis_agent import Agent  # 复用 LLM Agent 能力
from jarvis.jarvis_c2rust.llm_module_agent_apply import (
    apply_project_structure_from_json,
)
from jarvis.jarvis_c2rust.llm_module_agent_executor import (
    execute_llm_plan,
)
from jarvis.jarvis_c2rust.llm_module_agent_loader import GraphLoader
from jarvis.jarvis_c2rust.llm_module_agent_prompts import PromptBuilder
from jarvis.jarvis_c2rust.llm_module_agent_types import sanitize_mod_name
from jarvis.jarvis_c2rust.llm_module_agent_utils import (
    entries_to_json,
    parse_project_json_entries,
    perform_pre_cleanup_for_planner,
)
from jarvis.jarvis_c2rust.llm_module_agent_validator import ProjectValidator
from jarvis.jarvis_utils.output import PrettyOutput


class LLMRustCratePlannerAgent:
    """
    使用 jarvis_agent.Agent 调用 LLM 来生成 Rust crate 规划（JSON）。
    """

    def __init__(
        self,
        project_root: Union[Path, str] = ".",
        db_path: Optional[Union[Path, str]] = None,
        llm_group: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.db_path = (
            Path(db_path).resolve()
            if db_path is not None
            else (self.project_root / ".jarvis" / "c2rust" / "symbols.jsonl")
        )
        self.llm_group = llm_group
        self.loader = GraphLoader(self.db_path, self.project_root)
        # 读取附加说明
        self.additional_notes = self._load_additional_notes()

        # 初始化提示词构建器和验证器
        self.prompt_builder = PromptBuilder(
            self.project_root,
            self.loader,
            self._crate_name,
            self._has_original_main,
            self._append_additional_notes,
        )
        self.validator = ProjectValidator(
            self._crate_name,
            self._has_original_main,
        )

    def _load_additional_notes(self) -> str:
        """从配置文件加载附加说明"""
        try:
            from jarvis.jarvis_c2rust.constants import CONFIG_JSON

            config_path = self.project_root / ".jarvis" / "c2rust" / CONFIG_JSON
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    config = json.load(f)
                    if isinstance(config, dict):
                        return str(config.get("additional_notes", "") or "").strip()
        except Exception:
            pass
        return ""

    def _append_additional_notes(self, prompt: str) -> str:
        """
        在提示词末尾追加附加说明（如果存在）。

        Args:
            prompt: 原始提示词

        Returns:
            追加了附加说明的提示词
        """
        if self.additional_notes and self.additional_notes.strip():
            return (
                prompt
                + "\n\n"
                + "【附加说明（用户自定义）】\n"
                + self.additional_notes.strip()
            )
        return prompt

    def _crate_name(self) -> str:
        """
        计算crate名称：
        - 当 project_root 为当前目录时，返回 "<当前目录名>_rs"
        - 否则返回 project_root 的目录名
        - 输出用于命名/提示，保持下划线风格（不影响 Cargo 包名）
        """
        try:
            cwd = Path(".").resolve()
            if self.project_root.resolve() == cwd:
                base = f"{cwd.name}_rs"
            else:
                base = self.project_root.name or "c2rust_crate"
        except Exception:
            base = "c2rust_crate"
        return sanitize_mod_name(base)

    def _has_original_main(self) -> bool:
        """
        判断原始项目是否包含 main 函数：
        - 若 symbols 图谱中存在函数名为 'main' 或限定名以 '::main' 结尾，则认为存在
        """
        try:
            for m in self.loader.fn_by_id.values():
                n = (m.name or "").strip()
                q = (m.qname or "").strip()
                if n == "main" or q.endswith("::main"):
                    return True
        except Exception:
            # 如果在遍历过程中发生异常，视为不存在 main
            pass
        return False

    def _get_project_json_text(self, max_retries: int = 10) -> str:
        """
        执行主流程并返回原始 <PROJECT> JSON 文本，不进行解析。
        若格式校验失败，将自动重试，直到满足为止或达到最大重试次数。

        Args:
            max_retries: 最大重试次数，默认 10 次

        Raises:
            RuntimeError: 达到最大重试次数仍未生成有效输出
        """
        # 从 translation_order.jsonl 生成上下文，不再基于 symbols.jsonl 的调用图遍历
        roots_ctx = self.prompt_builder.build_roots_context_from_order()

        system_prompt = self.prompt_builder.build_system_prompt()
        user_prompt = self.prompt_builder.build_user_prompt(roots_ctx)
        base_summary_prompt = self.prompt_builder.build_summary_prompt(roots_ctx)

        last_error = "未知错误"
        attempt = 0
        use_direct_model = False  # 标记是否使用直接模型调用
        agent = None  # 在循环外声明，以便重试时复用

        while attempt < max_retries:
            attempt += 1
            # 首次使用基础 summary_prompt；失败后附加反馈
            summary_prompt = (
                base_summary_prompt
                if attempt == 1
                else self.prompt_builder.build_retry_summary_prompt(
                    base_summary_prompt, last_error
                )
            )

            # 第一次创建 Agent，后续重试时复用（如果使用直接模型调用）
            if agent is None or not use_direct_model:
                agent = Agent(
                    system_prompt=system_prompt,
                    name="C2Rust-LLM-Module-Planner",
                    model_group=self.llm_group,
                    summary_prompt=summary_prompt,
                    need_summary=True,
                    auto_complete=True,
                    use_tools=["execute_script", "read_code"],
                    non_interactive=True,  # 非交互
                    use_methodology=False,
                    use_analysis=False,
                )

            # 进入主循环：第一轮仅输出 {ot('!!!COMPLETE!!!')} 触发自动完成；随后 summary 输出 <PROJECT> 块（仅含 JSON）
            if use_direct_model:
                # 格式校验失败后，直接调用模型接口
                # 构造包含摘要提示词和具体错误信息的完整提示
                error_guidance = ""
                if last_error and last_error != "未知错误":
                    if "JSON解析失败" in last_error:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_error}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <PROJECT> 块，块内仅包含 JSON 格式的项目结构定义。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                    else:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_error}\n\n请确保输出格式正确：仅输出一个 <PROJECT> 块，块内仅包含 JSON 格式的项目结构定义。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"

                full_prompt = f"{user_prompt}{error_guidance}\n\n{summary_prompt}"
                try:
                    response = agent.model.chat_until_success(full_prompt)
                    summary_output = response
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner] 直接模型调用失败: {e}，回退到 run()"
                    )
                    summary_output = agent.run(user_prompt)
            else:
                # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                summary_output = agent.run(user_prompt)

            project_text = str(summary_output) if summary_output is not None else ""
            json_text = self.validator.extract_json_from_project(project_text)

            # 尝试解析并校验
            entries, parse_error_json = parse_project_json_entries(json_text)
            if parse_error_json:
                # JSON解析失败，记录错误并重试
                last_error = parse_error_json
                use_direct_model = True  # 格式校验失败，后续重试使用直接模型调用
                PrettyOutput.auto_print(
                    f"[c2rust-llm-planner] JSON解析失败: {parse_error_json}"
                )
                continue

            ok, reason = self.validator.validate_project_entries(entries)
            if ok:
                return json_text
            else:
                last_error = reason
                use_direct_model = True  # 格式校验失败，后续重试使用直接模型调用

        # 达到最大重试次数
        raise RuntimeError(
            f"达到最大重试次数 ({max_retries}) 仍未生成有效的项目结构。"
            f"最后一次错误: {last_error}"
        )

    def plan_crate_json_with_project(self) -> List[Any]:
        """
        执行主流程并返回解析后的 JSON 对象（列表）：
        - 列表项：
          * 字符串：文件，如 "lib.rs"
          * 字典：目录及其子项，如 {"src/": [ ... ]}
        """
        json_text = self._get_project_json_text()
        json_entries, parse_error = parse_project_json_entries(json_text)
        if parse_error:
            raise RuntimeError(f"JSON解析失败: {parse_error}")
        return json_entries

    def plan_crate_json_text(self) -> str:
        """
        执行主流程但返回原始 <PROJECT> JSON 文本，不进行解析。
        便于后续按原样应用目录结构，避免早期解析失败导致信息丢失。
        """
        return self._get_project_json_text()


def plan_crate_json_text(
    project_root: Union[Path, str] = ".",
    db_path: Optional[Union[Path, str]] = None,
    llm_group: Optional[str] = None,
    skip_cleanup: bool = False,
) -> str:
    """
    返回 LLM 生成的目录结构原始 JSON 文本（来自 <PROJECT> 块）。
    在规划前执行预清理并征询用户确认：删除将要生成的 crate 目录、当前目录的 Cargo.toml 工作区文件，以及 .jarvis/c2rust 下的 progress.json 与 symbol_map.jsonl。
    用户不同意则退出程序。
    当 skip_cleanup=True 时，跳过清理与确认（用于外层已处理的场景）。
    """
    # 若外层已处理清理确认，则跳过本函数的清理与确认（避免重复询问）
    if skip_cleanup:
        agent = LLMRustCratePlannerAgent(
            project_root=project_root, db_path=db_path, llm_group=llm_group
        )
        return agent.plan_crate_json_text()

    perform_pre_cleanup_for_planner(project_root)

    agent = LLMRustCratePlannerAgent(
        project_root=project_root, db_path=db_path, llm_group=llm_group
    )
    return agent.plan_crate_json_text()


def plan_crate_json_llm(
    project_root: Union[Path, str] = ".",
    db_path: Optional[Union[Path, str]] = None,
    skip_cleanup: bool = False,
) -> List[Any]:
    """
    便捷函数：使用 LLM 生成 Rust crate 模块规划（解析后的对象）。
    在规划前执行预清理并征询用户确认：删除将要生成的 crate 目录、当前目录的 Cargo.toml 工作区文件，以及 .jarvis/c2rust 下的 progress.json 与 symbol_map.jsonl。
    用户不同意则退出程序。
    当 skip_cleanup=True 时，跳过清理与确认（用于外层已处理的场景）。
    """
    # 若外层已处理清理确认，则跳过本函数的清理与确认（避免重复询问）
    if skip_cleanup:
        agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path)
        return agent.plan_crate_json_with_project()

    perform_pre_cleanup_for_planner(project_root)

    agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path)
    return agent.plan_crate_json_with_project()


__all__ = [
    "LLMRustCratePlannerAgent",
    "plan_crate_json_text",
    "plan_crate_json_llm",
    "execute_llm_plan",  # 向后兼容
    "entries_to_json",  # 向后兼容
    "apply_project_structure_from_json",  # 向后兼容
]
