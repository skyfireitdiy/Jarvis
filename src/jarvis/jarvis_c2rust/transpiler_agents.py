# -*- coding: utf-8 -*-
"""
Agent 管理模块
"""

import json
import time
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.utils import dir_tree
from jarvis.jarvis_code_agent.code_agent import CodeAgent


class AgentManager:
    """Agent 管理器"""

    def __init__(
        self,
        crate_dir: Path,
        project_root: Path,
        llm_group: Optional[str],
        non_interactive: bool,
        fn_index_by_id: Dict[int, FnRecord],
        get_crate_commit_hash_func: Callable[[], str],
        agent_before_commits: Dict[str, Optional[str]],
    ) -> None:
        self.crate_dir = crate_dir
        self.project_root = project_root
        self.llm_group = llm_group
        self.non_interactive = non_interactive
        self.fn_index_by_id = fn_index_by_id
        self.get_crate_commit_hash = get_crate_commit_hash_func
        self.agent_before_commits = agent_before_commits
        self._current_function_id: Optional[int] = None
        self._current_context_full_header: str = ""
        self._current_context_compact_header: str = ""
        self._current_context_full_sent: bool = False
        # 存储当前函数的 C 代码，供修复 Agent 使用
        self._current_c_code: str = ""

    def get_generation_agent(self) -> CodeAgent:
        """
        获取代码生成Agent（CodeAgent）。每次调用都重新创建，不复用。
        用于代码生成。
        注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表。
        提示：代码生成遵循 TDD（测试驱动开发）方法，通过提示词指导 Agent 先写测试再写实现。
        """
        fid = self._current_function_id
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        # 统一启用方法论和分析功能，提供更好的代码生成能力
        # 获取函数信息用于 Agent name
        fn_name = ""
        if fid is not None:
            rec = self.fn_index_by_id.get(fid)
            if rec:
                fn_name = rec.qname or rec.name or f"fn_{fid}"
        agent_name = "C2Rust-GenerationAgent" + (f"({fn_name})" if fn_name else "")
        agent = CodeAgent(
            name=agent_name,
            need_summary=False,
            non_interactive=self.non_interactive,
            model_group=self.llm_group,
            append_tools="read_symbols,methodology",
            use_methodology=True,
            use_analysis=True,
            force_save_memory=False,
            enable_task_list_manager=False,
            disable_review=True,
        )
        # 订阅 BEFORE_TOOL_CALL 和 AFTER_TOOL_CALL 事件，用于细粒度检测测试代码删除
        agent.event_bus.subscribe(BEFORE_TOOL_CALL, self.on_before_tool_call)
        agent.event_bus.subscribe(AFTER_TOOL_CALL, self.on_after_tool_call)
        # 记录 Agent 创建时的 commit id（作为初始值）
        agent_id = id(agent)
        agent_key = f"agent_{agent_id}"
        initial_commit = self.get_crate_commit_hash()
        if initial_commit:
            self.agent_before_commits[agent_key] = initial_commit
        return agent

    def get_fix_agent(
        self, c_code: Optional[str] = None, need_summary: bool = False
    ) -> CodeAgent:
        """
        获取修复Agent（CodeAgent）。每次调用都重新创建，不复用。
        用于修复构建错误和测试失败，启用方法论和分析功能以提供更好的修复能力。
        注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表。

        参数:
            c_code: 原 C 实现的代码，将添加到 Agent 的上下文中
            need_summary: 是否需要生成总结，默认为 False（构建修复阶段不需要总结）
        """
        # 每次重新创建，不复用
        # 获取函数信息用于 Agent name
        fn_name = ""
        if self._current_function_id is not None:
            rec = self.fn_index_by_id.get(self._current_function_id)
            if rec:
                fn_name = rec.qname or rec.name or f"fn_{self._current_function_id}"

        # 使用当前 C 代码（如果提供了参数则使用参数，否则使用缓存的）
        current_c_code = c_code if c_code is not None else self._current_c_code

        agent_name = "C2Rust-FixAgent" + (f"({fn_name})" if fn_name else "")

        # 只有在需要总结时才设置 summary_prompt
        summary_prompt = None
        if need_summary:
            summary_prompt = """请总结本次修复的流程和结果。总结应包含以下内容：
1. **修复流程**：
   - 遇到的问题类型（编译错误、测试失败、警告等）
   - 问题定位过程（如何找到问题根源）
   - 修复步骤（具体做了哪些修改）
   - 使用的工具和方法
2. **修复结果**：
   - 修复是否成功
   - 修复了哪些问题
   - 修改了哪些文件
   - 是否引入了新的问题
   - 验证结果（编译、测试是否通过）
3. **注意事项**：
   - 如果修复过程中遇到困难，说明原因
   - 如果修复不完整，说明遗留问题
   - 如果修复可能影响其他代码，说明影响范围

请使用清晰的结构和简洁的语言，确保总结信息完整且易于理解。"""

        agent = CodeAgent(
            name=agent_name,
            need_summary=need_summary,
            summary_prompt=summary_prompt,
            non_interactive=self.non_interactive,
            model_group=self.llm_group,
            append_tools="read_symbols,methodology",
            use_methodology=True,
            use_analysis=True,
            force_save_memory=False,
            disable_review=True,
        )
        # 订阅 BEFORE_TOOL_CALL 和 AFTER_TOOL_CALL 事件，用于细粒度检测测试代码删除
        agent.event_bus.subscribe(BEFORE_TOOL_CALL, self.on_before_tool_call)
        agent.event_bus.subscribe(AFTER_TOOL_CALL, self.on_after_tool_call)
        # 记录 Agent 创建时的 commit id（作为初始值）
        agent_id = id(agent)
        agent_key = f"agent_{agent_id}"
        initial_commit = self.get_crate_commit_hash()
        if initial_commit:
            self.agent_before_commits[agent_key] = initial_commit

        # 为修复 Agent 添加包含原 C 代码的上下文
        if current_c_code:
            # 在 Agent 的 session 中添加 C 代码上下文
            if hasattr(agent, "session") and hasattr(agent.session, "prompt"):
                c_code_context = (
                    "\n\n【原始 C 实现代码（修复参考）】\n"
                    "以下是当前函数对应的原始 C 实现代码，修复时请参考：\n"
                    "<C_SOURCE>\n"
                    f"{current_c_code}\n"
                    "</C_SOURCE>\n"
                )
                agent.session.prompt = c_code_context + agent.session.prompt

        return agent

    def get_code_agent(self) -> CodeAgent:
        """
        获取代码生成/修复Agent（CodeAgent）。每次调用都重新创建，不复用。
        统一用于代码生成和修复，启用方法论和分析功能以提供更好的代码质量。
        注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表。
        提示：代码生成遵循 TDD（测试驱动开发）方法，通过提示词指导 Agent 先写测试再写实现。
        """
        fid = self._current_function_id
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        # 统一启用方法论和分析功能，提供更好的代码生成和修复能力
        # 获取函数信息用于 Agent name
        fn_name = ""
        if fid is not None:
            rec = self.fn_index_by_id.get(fid)
            if rec:
                fn_name = rec.qname or rec.name or f"fn_{fid}"
        agent_name = "C2Rust-CodeAgent" + (f"({fn_name})" if fn_name else "")
        agent = CodeAgent(
            name=agent_name,
            need_summary=False,
            non_interactive=self.non_interactive,
            model_group=self.llm_group,
            append_tools="read_symbols,methodology",
            use_methodology=True,
            use_analysis=True,
            force_save_memory=False,
            enable_task_list_manager=False,
            disable_review=True,
        )
        # 订阅 BEFORE_TOOL_CALL 和 AFTER_TOOL_CALL 事件，用于细粒度检测测试代码删除
        agent.event_bus.subscribe(BEFORE_TOOL_CALL, self.on_before_tool_call)
        agent.event_bus.subscribe(AFTER_TOOL_CALL, self.on_after_tool_call)
        # 记录 Agent 创建时的 commit id（作为初始值）
        agent_id = id(agent)
        agent_key = f"agent_{agent_id}"
        initial_commit = self.get_crate_commit_hash()
        if initial_commit:
            self.agent_before_commits[agent_key] = initial_commit
        return agent

    def compose_prompt_with_context(self, prompt: str, for_fix: bool = False) -> str:
        """
        在复用Agent时，将此前构建的函数上下文头部拼接到当前提示词前，确保连续性。
        策略：
        - 每个函数生命周期内，首次调用拼接"全量头部"；
        - 后续调用仅拼接"精简头部"；
        - 如头部缺失则直接返回原提示。

        参数:
            for_fix: 如果为 True，表示这是用于修复 Agent 的提示词，会在上下文中添加原 C 代码
        """
        # 如果是修复 Agent，添加原 C 代码上下文
        if for_fix and self._current_c_code:
            c_code_header = (
                "\n【原始 C 实现代码（修复参考）】\n"
                "以下是当前函数对应的原始 C 实现代码，修复时请参考：\n"
                "<C_SOURCE>\n"
                f"{self._current_c_code}\n"
                "</C_SOURCE>\n"
            )
            # 首次发送全量上下文
            if (
                not self._current_context_full_sent
            ) and self._current_context_full_header:
                self._current_context_full_sent = True
                return (
                    self._current_context_full_header + c_code_header + "\n\n" + prompt
                )
            # 后续拼接精简上下文
            if self._current_context_compact_header:
                return (
                    self._current_context_compact_header
                    + c_code_header
                    + "\n\n"
                    + prompt
                )
            return c_code_header + "\n\n" + prompt

        # 首次发送全量上下文
        if (not self._current_context_full_sent) and self._current_context_full_header:
            self._current_context_full_sent = True
            return self._current_context_full_header + "\n\n" + prompt
        # 后续拼接精简上下文
        if self._current_context_compact_header:
            return self._current_context_compact_header + "\n\n" + prompt
        return prompt

    def reset_function_context(
        self,
        rec: FnRecord,
        module: str,
        rust_sig: str,
        c_code: str,
        collect_callees_context_func: Callable[[Any], str],
        extract_compile_flags_func: Callable[[str], Dict[str, Any]],
    ) -> None:
        """
        初始化当前函数的上下文。
        在单个函数实现开始时调用一次。
        注意：所有 Agent 每次调用都重新创建，不复用。
        """
        self._current_function_id = rec.id
        # 保存当前函数的 C 代码，供修复 Agent 使用
        self._current_c_code = c_code or ""

        # 汇总上下文头部，供后续复用时拼接
        callees_ctx = collect_callees_context_func(rec)
        crate_tree = dir_tree(self.crate_dir)
        librep_ctx = (
            rec.lib_replacement if isinstance(rec.lib_replacement, dict) else None
        )
        # 提取编译参数
        compile_flags = extract_compile_flags_func(rec.file)

        header_lines = [
            "【当前函数上下文（复用Agent专用）】",
            f"- 函数: {rec.qname or rec.name} (id={rec.id})",
            f"- 源位置: {rec.file}:{rec.start_line}-{rec.end_line}",
            f"- 原 C 工程目录: {self.project_root.resolve()}",
            f"- 目标模块: {module}",
            f"- 建议/当前签名: {rust_sig}",
            f"- crate 根目录: {self.crate_dir.resolve()}",
            "",
            "原始C函数源码片段（只读参考）：",
            "<C_SOURCE>",
            c_code or "",
            "</C_SOURCE>",
            "",
            "被引用符号上下文：",
            json.dumps(callees_ctx, ensure_ascii=False, indent=2),
            "",
            "库替代上下文（若有）：",
            json.dumps(librep_ctx, ensure_ascii=False, indent=2),
        ]
        # 添加编译参数（如果存在）
        if compile_flags:
            header_lines.extend(
                [
                    "",
                    "C文件编译参数（来自 compile_commands.json）：",
                    str(compile_flags),
                ]
            )
        header_lines.extend(
            [
                "",
                "crate 目录结构（部分）：",
                "<CRATE_TREE>",
                crate_tree,
                "</CRATE_TREE>",
            ]
        )
        # 精简头部（后续复用）
        compact_lines = [
            "【函数上下文简要（复用）】",
            f"- 函数: {rec.qname or rec.name} (id={rec.id})",
            f"- 原 C 工程目录: {self.project_root.resolve()}",
            f"- 模块: {module}",
            f"- 签名: {rust_sig}",
            f"- crate: {self.crate_dir.resolve()}",
        ]
        self._current_context_full_header = "\n".join(header_lines)
        self._current_context_compact_header = "\n".join(compact_lines)
        self._current_context_full_sent = False

    def refresh_compact_context(
        self, rec: FnRecord, module: str, rust_sig: str
    ) -> None:
        """
        刷新精简上下文头部（在 sig-fix/ensure-impl 后调用，保证后续提示一致）。
        仅更新精简头部，不影响已发送的全量头部。
        """
        try:
            compact_lines = [
                "【函数上下文简要（复用）】",
                f"- 函数: {rec.qname or rec.name} (id={rec.id})",
                f"- 模块: {module}",
                f"- 签名: {rust_sig}",
                f"- crate: {self.crate_dir.resolve()}",
            ]
            self._current_context_compact_header = "\n".join(compact_lines)
        except Exception:
            pass

    def on_before_tool_call(
        self, agent: Any, current_response: Optional[Any] = None, **kwargs: Any
    ) -> None:
        """
        工具调用前的事件处理器，用于记录工具调用前的 commit id。

        在每次工具调用前记录当前的 commit，以便在工具调用后检测到问题时能够回退。
        """
        try:
            # 只关注可能修改代码的工具
            # 注意：在 BEFORE_TOOL_CALL 时，工具还未执行，无法获取工具名称
            # 但我们可以在 AFTER_TOOL_CALL 时检查工具名称，这里先记录 commit
            agent_id = id(agent)
            agent_key = f"agent_{agent_id}"
            current_commit = self.get_crate_commit_hash()
            if current_commit:
                # 记录工具调用前的 commit（如果之前没有记录，或者 commit 已变化）
                if (
                    agent_key not in self.agent_before_commits
                    or self.agent_before_commits[agent_key] != current_commit
                ):
                    self.agent_before_commits[agent_key] = current_commit
        except Exception as e:
            # 事件处理器异常不应影响主流程
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][test-detection] BEFORE_TOOL_CALL 事件处理器异常: {e}"
            )

    def on_after_tool_call(
        self,
        agent: Any,
        current_response: Optional[Any] = None,
        need_return: Optional[bool] = None,
        tool_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        工具调用后的事件处理器，用于细粒度检测测试代码删除。

        在每次工具调用后立即检测，如果检测到测试代码被错误删除，立即回退。
        """
        try:
            # 只检测编辑文件的工具调用
            last_tool = (
                agent.get_user_data("__last_executed_tool__")
                if hasattr(agent, "get_user_data")
                else None
            )
            if not last_tool:
                return

            # 只关注可能修改代码的工具
            edit_tools = {
                "edit_file",
                "apply_patch",
            }
            if last_tool not in edit_tools:
                return

            # 获取该 Agent 对应的工具调用前的 commit id
            agent_id = id(agent)
            agent_key = f"agent_{agent_id}"
            before_commit = self.agent_before_commits.get(agent_key)

            # 如果没有 commit 信息，无法检测
            if not before_commit:
                return

            # 检测测试代码删除
            from jarvis.jarvis_c2rust.utils import ask_llm_about_test_deletion
            from jarvis.jarvis_c2rust.utils import detect_test_deletion

            detection_result = detect_test_deletion("[c2rust-transpiler]")
            if not detection_result:
                # 没有检测到删除，更新 commit 记录
                current_commit = self.get_crate_commit_hash()
                if current_commit and current_commit != before_commit:
                    self.agent_before_commits[agent_key] = current_commit
                return

            PrettyOutput.auto_print(
                "⚠️ [c2rust-transpiler][test-detection] 检测到可能错误删除了测试代码标记（工具调用后检测）"
            )

            # 询问 LLM 是否合理
            need_reset = ask_llm_about_test_deletion(
                detection_result, agent, "[c2rust-transpiler]"
            )

            if need_reset:
                PrettyOutput.auto_print(
                    f"❌ [c2rust-transpiler][test-detection] LLM 确认删除不合理，正在回退到 commit: {before_commit}"
                )
                # 需要调用 reset_to_commit 函数，但这里需要通过回调传递
                # 暂时先记录，由调用方处理
                if hasattr(self, "_reset_to_commit_func"):
                    if self._reset_to_commit_func(before_commit):
                        PrettyOutput.auto_print(
                            "✅ [c2rust-transpiler][test-detection] 已回退到之前的 commit（工具调用后检测）"
                        )
                        # 回退后，保持之前的 commit 记录
                        self.agent_before_commits[agent_key] = before_commit
                        # 在 agent 的 session 中添加提示，告知修改被撤销
                        if hasattr(agent, "session") and hasattr(
                            agent.session, "prompt"
                        ):
                            agent.session.prompt += "\n\n⚠️ 修改被撤销：检测到测试代码被错误删除，已回退到之前的版本。\n"
                    else:
                        PrettyOutput.auto_print(
                            "❌ [c2rust-transpiler][test-detection] 回退失败"
                        )
            else:
                # LLM 认为删除合理，更新 commit 记录
                current_commit = self.get_crate_commit_hash()
                if current_commit and current_commit != before_commit:
                    self.agent_before_commits[agent_key] = current_commit
        except Exception as e:
            # 事件处理器异常不应影响主流程
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][test-detection] AFTER_TOOL_CALL 事件处理器异常: {e}"
            )

    def set_reset_to_commit_func(self, reset_func: Callable[[str], bool]) -> None:
        """设置回退 commit 的函数"""
        self._reset_to_commit_func = reset_func

    def update_progress_current(
        self,
        rec: FnRecord,
        module: str,
        rust_sig: str,
        progress: Dict[str, Any],
        save_progress_func: Callable[[], None],
    ) -> None:
        """更新当前进度"""
        progress["current"] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "id": rec.id,
            "name": rec.name,
            "qualified_name": rec.qname,
            "file": rec.file,
            "start_line": rec.start_line,
            "end_line": rec.end_line,
            "module": module,
            "rust_signature": rust_sig,
        }
        save_progress_func()
