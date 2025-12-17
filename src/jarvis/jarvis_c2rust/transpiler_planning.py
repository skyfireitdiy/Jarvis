# -*- coding: utf-8 -*-
"""
模块和签名规划模块
"""

import json
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.utils import dir_tree
from jarvis.jarvis_c2rust.utils import extract_json_from_summary


class PlanningManager:
    """模块和签名规划管理器"""

    def __init__(
        self,
        project_root: Path,
        crate_dir: Path,
        data_dir: Path,
        llm_group: Optional[str],
        plan_max_retries: int,
        non_interactive: bool,
        disabled_libraries: List[str],
        root_symbols: List[str],
        extract_compile_flags_func: Callable[[str], Dict[str, Any]],
        collect_callees_context_func: Callable[[Any], List[Dict[str, Any]]],
        append_additional_notes_func: Callable[[str], str],
        is_root_symbol_func: Callable[[Any], bool],
        get_crate_commit_hash_func: Callable[[], str],
        on_before_tool_call_func: Callable[[Any, Optional[Any]], None],
        on_after_tool_call_func: Callable[
            [Any, Optional[Any], Optional[bool], Optional[str]], None
        ],
        agent_before_commits: Dict[str, Optional[str]],
    ) -> None:
        self.project_root = project_root
        self.crate_dir = crate_dir
        self.data_dir = data_dir
        self.llm_group = llm_group
        self.plan_max_retries = plan_max_retries
        self.non_interactive = non_interactive
        self.disabled_libraries = disabled_libraries
        self.root_symbols = root_symbols
        self.extract_compile_flags = extract_compile_flags_func
        self.collect_callees_context = collect_callees_context_func
        self.append_additional_notes = append_additional_notes_func
        self.is_root_symbol = is_root_symbol_func
        self.get_crate_commit_hash = get_crate_commit_hash_func
        self.on_before_tool_call = on_before_tool_call_func
        self.on_after_tool_call = on_after_tool_call_func
        self.agent_before_commits = agent_before_commits

    def build_module_selection_prompts(
        self,
        rec: FnRecord,
        c_code: str,
        callees_ctx: List[Dict[str, Any]],
        crate_tree: str,
    ) -> Tuple[str, str, str]:
        """
        返回 (system_prompt, user_prompt, summary_prompt)
        要求 summary 输出 JSON：
        {
          "module": "src/<path>.rs or module path (e.g., src/foo/mod.rs or src/foo/bar.rs)",
          "rust_signature": "pub fn ...",
          "notes": "optional"
        }
        """
        is_root = self.is_root_symbol(rec)
        system_prompt = (
            "你是资深Rust工程师，擅长为C/C++函数选择合适的Rust模块位置并产出对应的Rust函数签名。\n"
            "目标：根据提供的C源码、调用者上下文与crate目录结构，为该函数选择合适的Rust模块文件并给出Rust函数签名（不实现）。\n"
            "原则：\n"
            "- 按功能内聚与依赖方向选择模块，避免循环依赖；\n"
            "- 模块路径必须落在 crate 的 src/ 下，优先放置到已存在的模块中；必要时可建议创建新的子模块文件；\n"
            "- 函数接口设计应遵循 Rust 最佳实践，不需要兼容 C 的数据类型；优先使用 Rust 原生类型（如 i32/u32/usize、&[T]/&mut [T]、String、Result<T, E> 等），而不是 C 风格类型（如 core::ffi::c_*、libc::c_*）；\n"
            '- 禁止使用 extern "C"；函数应使用标准的 Rust 调用约定，不需要 C ABI；\n'
            "- 参数个数与顺序可以保持与 C 一致，但类型设计应优先考虑 Rust 的惯用法和安全性；\n"
            + (
                "- **根符号要求**：此函数是根符号，必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。\n"
                if is_root
                else ""
            )
            + "- **评估是否需要实现**：在规划阶段，请评估此函数是否真的需要实现。以下情况可以跳过实现（设置 skip_implementation 为 true），但**必须确保功能一致性**：\n"
            + "  * **已实现的函数**：如果函数已经在目标模块（module）中实现，可以使用 read_code 工具检查目标文件，确认函数已存在且**功能与 C 实现一致**，则无需重复实现。**重要**：如果已实现的函数功能不一致（如参数处理不同、返回值不同、行为不同等），则不能跳过，需要重新实现或修正\n"
            + "  * **资源释放类函数**：如文件关闭 fclose、内存释放 free、句柄释放、锁释放等，在 Rust 中通常通过 RAII（Drop trait）自动管理，无需显式实现\n"
            + "  * **已被库替代**：如果函数已被标准库或第三方 crate 替代（lib_replacement 字段已设置），且**库的功能与 C 实现完全一致**，不需要兼容层，可以跳过实现。**重要**：如果库的功能与 C 实现不一致（如 API 行为不同、参数要求不同、返回值不同等），则需要实现兼容层或重新实现，不能跳过\n"
            + "  * **空实现或无意义函数**：如果 C 函数本身是空实现、简单返回常量、或仅用于兼容性占位，在 Rust 中可能不需要实现\n"
            + "  * **内联函数或宏**：如果函数在 C 中是内联函数或宏，在 Rust 中可能不需要单独实现\n"
            + "  * **其他不需要实现的情况**：根据具体情况判断，如果函数在 Rust 转译中确实不需要实现，可以跳过\n"
            + "  * **功能一致性检查原则**：在判断是否跳过实现时，必须仔细对比 C 实现与 Rust 实现（或库替代）的功能一致性，包括但不限于：输入参数处理、返回值、副作用、错误处理、边界条件处理等。如果存在任何不一致，则不能跳过实现\n"
            + "  * 如果设置 skip_implementation 为 true，请在 notes 字段中详细说明原因，并确认已进行功能一致性检查\n"
            + "- 仅输出必要信息，避免冗余解释。"
        )
        # 提取编译参数
        compile_flags = self.extract_compile_flags(rec.file)
        compile_flags_section = ""
        if compile_flags:
            compile_flags_section = "\n".join(
                [
                    "",
                    "C文件编译参数（来自 compile_commands.json）：",
                    str(compile_flags),
                ]
            )

        user_prompt = "\n".join(
            [
                "请阅读以下上下文并准备总结：",
                f"- 函数标识: id={rec.id}, name={rec.name}, qualified={rec.qname}",
                f"- 源文件位置: {rec.file}:{rec.start_line}-{rec.end_line}",
                f"- crate 根目录路径: {self.crate_dir.resolve()}",
                "",
                "C函数源码片段：",
                "<C_SOURCE>",
                c_code,
                "</C_SOURCE>",
                "",
                "符号表签名与参数（只读参考）：",
                json.dumps(
                    {
                        "signature": getattr(rec, "signature", ""),
                        "params": getattr(rec, "params", None),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "",
                "被引用符号上下文（如已转译则包含Rust模块信息）：",
                json.dumps(callees_ctx, ensure_ascii=False, indent=2),
                "",
                "库替代上下文（若存在）：",
                json.dumps(
                    getattr(rec, "lib_replacement", None), ensure_ascii=False, indent=2
                ),
                compile_flags_section,
                "",
                *(
                    [
                        f"禁用库列表（禁止在实现中使用这些库）：{', '.join(self.disabled_libraries)}"
                    ]
                    if self.disabled_libraries
                    else []
                ),
                *([""] if self.disabled_libraries else []),
                "当前crate目录结构（部分）：",
                "<CRATE_TREE>",
                crate_tree,
                "</CRATE_TREE>",
                "",
                "为避免完整读取体积较大的符号表，你也可以使用工具 read_symbols 按需获取指定符号记录：",
                "- 工具: read_symbols",
                "- 参数示例(JSON):",
                f'  {{"symbols_file": "{(self.data_dir / "symbols.jsonl").resolve()}", "symbols": ["符号1", "符号2"]}}',
                "",
                "**重要：检查函数是否已实现及功能一致性**",
                "在确定目标模块（module）后，请使用 read_code 工具检查该模块文件，确认函数是否已经实现：",
                "- 工具: read_code",
                "- 参数示例(JSON):",
                '  {"file_path": "<目标模块路径>"}',
                '- 如果函数已经在目标模块中实现，**必须仔细对比 C 实现与 Rust 实现的功能一致性**（包括参数处理、返回值、副作用、错误处理、边界条件等），只有功能完全一致时才能设置 skip_implementation 为 true，并在 notes 中说明 "函数已在目标模块中实现，且功能与 C 实现一致"。如果功能不一致，则不能跳过，需要重新实现或修正',
                "",
                "如果理解完毕，请进入总结阶段。",
            ]
        )
        summary_prompt = (
            "请仅输出一个 <SUMMARY> 块，块内必须且只包含一个 JSON 对象，不得包含其它内容。\n"
            "允许字段（JSON 对象）：\n"
            '- "module": "<绝对路径>/src/xxx.rs 或 <绝对路径>/src/xxx/mod.rs；或相对路径 src/xxx.rs / src/xxx/mod.rs"\n'
            '- "rust_signature": "pub fn xxx(...)->..."\n'
            '- "skip_implementation": bool  // 可选，如果为 true，表示此函数不需要实现，可以直接标记为已实现\n'
            '- "notes": "可选说明（若有上下文缺失或风险点，请在此列出；如果 skip_implementation 为 true，必须在此说明原因）"\n'
            "注意：\n"
            "- module 必须位于 crate 的 src/ 目录下，接受绝对路径或以 src/ 开头的相对路径；尽量选择已有文件；如需新建文件，给出合理路径；\n"
            "- rust_signature 应遵循 Rust 最佳实践，不需要兼容 C 的数据类型；优先使用 Rust 原生类型和惯用法，而不是 C 风格类型。\n"
            "- **评估是否需要实现**：请仔细评估此函数是否真的需要实现。以下情况可以设置 skip_implementation 为 true，但**必须确保功能一致性**：\n"
            + "  * **已实现的函数**：如果函数已经在目标模块（module）中实现，可以使用 read_code 工具检查目标文件，确认函数已存在且**功能与 C 实现一致**，则无需重复实现。**重要**：如果已实现的函数功能不一致（如参数处理不同、返回值不同、行为不同等），则不能跳过，需要重新实现或修正\n"
            + "  * **资源释放类函数**：如文件关闭 fclose、内存释放 free、句柄释放、锁释放等，在 Rust 中通常通过 RAII（Drop trait）自动管理，无需显式实现\n"
            + "  * **已被库替代**：如果函数已被标准库或第三方 crate 替代（lib_replacement 字段已设置），且**库的功能与 C 实现完全一致**，不需要兼容层，可以跳过实现。**重要**：如果库的功能与 C 实现不一致（如 API 行为不同、参数要求不同、返回值不同等），则需要实现兼容层或重新实现，不能跳过\n"
            + "  * **空实现或无意义函数**：如果 C 函数本身是空实现、简单返回常量、或仅用于兼容性占位，在 Rust 中可能不需要实现\n"
            + "  * **内联函数或宏**：如果函数在 C 中是内联函数或宏，在 Rust 中可能不需要单独实现\n"
            + "  * **其他不需要实现的情况**：根据具体情况判断，如果函数在 Rust 转译中确实不需要实现，可以跳过\n"
            + "  * **功能一致性检查原则**：在判断是否跳过实现时，必须仔细对比 C 实现与 Rust 实现（或库替代）的功能一致性，包括但不限于：输入参数处理、返回值、副作用、错误处理、边界条件处理等。如果存在任何不一致，则不能跳过实现\n"
            + "  * **重要**：如果设置 skip_implementation 为 true，必须在 notes 字段中详细说明原因，并确认已进行功能一致性检查，例如：\n"
            + '    - "函数已在目标模块中实现，且功能与 C 实现一致"\n'
            + '    - "通过 RAII 自动管理，无需显式实现"\n'
            + '    - "已被标准库 std::xxx 替代，且功能完全一致，无需实现"\n'
            + '    - "空实现函数，在 Rust 中不需要"\n'
            + '    - "内联函数，已在调用处展开，无需单独实现"\n'
            + "- 如果函数确实需要实现，或功能不一致需要修正，则不要设置 skip_implementation 或设置为 false\n"
            + "- 类型设计原则：\n"
            + "  * 基本类型：优先使用 i32/u32/i64/u64/isize/usize/f32/f64 等原生 Rust 类型，而不是 core::ffi::c_* 或 libc::c_*；\n"
            + "  * 指针/引用：优先使用引用 &T/&mut T 或切片 &[T]/&mut [T]，而非原始指针 *const T/*mut T；仅在必要时使用原始指针；\n"
            + "  * 字符串：优先使用 String、&str 而非 *const c_char/*mut c_char；\n"
            + "  * 错误处理：考虑使用 Result<T, E> 而非 C 风格的错误码；\n"
            + "  * 参数个数与顺序可以保持与 C 一致，但类型应优先考虑 Rust 的惯用法、安全性和可读性；\n"
            + (
                "- **根符号要求**：此函数是根符号，rust_signature 必须包含 `pub` 关键字，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。\n"
                if is_root
                else ""
            )
            + "- 函数签名应包含可见性修饰（pub）与函数名；类型应为 Rust 最佳实践的选择，而非简单映射 C 类型。\n"
            + '- 禁止使用 extern "C"；函数应使用标准的 Rust 调用约定，不需要 C ABI。\n'
            + "请严格按以下格式输出（JSON格式，支持jsonnet语法如尾随逗号、注释、|||分隔符多行字符串等）：\n"
            + "示例1（正常函数）：\n"
            + '<SUMMARY>\n{\n  "module": "...",\n  "rust_signature": "...",\n  "notes": "..."\n}\n</SUMMARY>\n'
            + "示例2（已实现的函数，且功能一致，可跳过实现）：\n"
            + '<SUMMARY>\n{\n  "module": "...",\n  "rust_signature": "...",\n  "skip_implementation": true,\n  "notes": "函数已在目标模块中实现，且功能与 C 实现一致（参数处理、返回值、副作用均一致）"\n}\n</SUMMARY>\n'
            + "示例3（不需要实现的函数，可跳过实现）：\n"
            + '<SUMMARY>\n{\n  "module": "...",\n  "rust_signature": "...",\n  "skip_implementation": true,\n  "notes": "通过 RAII 自动管理，无需显式实现"\n}\n</SUMMARY>\n'
            + "示例4（已被库替代，且功能一致，可跳过实现）：\n"
            + '<SUMMARY>\n{\n  "module": "...",\n  "rust_signature": "...",\n  "skip_implementation": true,\n  "notes": "已被标准库 std::xxx 替代，且功能与 C 实现完全一致（API 行为、参数要求、返回值均一致），无需实现"\n}\n</SUMMARY>\n'
            + "示例5（空实现函数，可跳过实现）：\n"
            + '<SUMMARY>\n{\n  "module": "...",\n  "rust_signature": "...",\n  "skip_implementation": true,\n  "notes": "C 函数为空实现，在 Rust 中不需要"\n}\n</SUMMARY>'
        )
        # 在 user_prompt 和 summary_prompt 中追加附加说明（system_prompt 通常不需要）
        user_prompt = self.append_additional_notes(user_prompt)
        summary_prompt = self.append_additional_notes(summary_prompt)
        return system_prompt, user_prompt, summary_prompt

    def plan_module_and_signature(
        self, rec: FnRecord, c_code: str
    ) -> Tuple[str, str, bool]:
        """调用 Agent 选择模块与签名，返回 (module_path, rust_signature, skip_implementation)，若格式不满足将自动重试直到满足"""
        crate_tree = dir_tree(self.crate_dir)
        callees_ctx = self.collect_callees_context(rec)
        sys_p, usr_p, base_sum_p = self.build_module_selection_prompts(
            rec, c_code, callees_ctx, crate_tree
        )

        def _validate(meta: Any) -> Tuple[bool, str]:
            """基本格式检查，仅验证字段存在性，不做硬编码规则校验"""
            if not isinstance(meta, dict) or not meta:
                return False, "未解析到有效的 <SUMMARY> 中的 JSON 对象"
            module = meta.get("module")
            rust_sig = meta.get("rust_signature")
            if not isinstance(module, str) or not module.strip():
                return False, "缺少必填字段 module"
            if not isinstance(rust_sig, str) or not rust_sig.strip():
                return False, "缺少必填字段 rust_signature"
            # 路径归一化：容忍相对/简略路径，最终归一为 crate_dir 下的绝对路径（不做硬编码校验）
            try:
                raw = str(module).strip().replace("\\", "/")
                crate_root = self.crate_dir.resolve()
                mp: Path
                p = Path(raw)
                if p.is_absolute():
                    mp = p.resolve()
                else:
                    # 规范化相对路径：若不以 src/ 开头，自动补全为 src/<raw>
                    if raw.startswith("./"):
                        raw = raw[2:]
                    if not raw.startswith("src/"):
                        raw = f"src/{raw}"
                    mp = (crate_root / raw).resolve()
                # 将归一化后的绝对路径回写到 meta，避免后续流程二次解析歧义
                meta["module"] = str(mp)
            except Exception:
                # 路径归一化失败不影响，保留原始值
                pass
            return True, ""

        def _retry_sum_prompt(reason: str) -> str:
            return (
                base_sum_p
                + "\n\n[格式检查失败，必须重试]\n"
                + f"- 失败原因：{reason}\n"
                + "- 仅输出一个 <SUMMARY> 块；块内直接包含 JSON 对象（不需要额外的标签）；\n"
                + "- JSON 对象必须包含字段：module、rust_signature。\n"
            )

        attempt = 0
        last_reason = "未知错误"
        plan_max_retries_val = self.plan_max_retries
        # 如果 plan_max_retries 为 0，表示无限重试
        use_direct_model = False  # 标记是否使用直接模型调用
        agent = None  # 在循环外声明，以便重试时复用

        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        while plan_max_retries_val == 0 or attempt < plan_max_retries_val:
            attempt += 1
            sum_p = base_sum_p if attempt == 1 else _retry_sum_prompt(last_reason)

            # 第一次创建 Agent，后续重试时复用（如果使用直接模型调用）
            # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
            if agent is None or not use_direct_model:
                # 获取函数信息用于 Agent name
                fn_name = rec.qname or rec.name or f"fn_{rec.id}"
                agent_name = f"C2Rust-Function-Planner({fn_name})"
                agent = Agent(
                    system_prompt=sys_p,
                    name=agent_name,
                    model_group=self.llm_group,
                    summary_prompt=sum_p,
                    need_summary=True,
                    auto_complete=True,
                    use_tools=["execute_script", "read_code", "read_symbols"],
                    non_interactive=self.non_interactive,
                    use_methodology=False,
                    use_analysis=False,
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

            if use_direct_model:
                # 格式校验失败后，直接调用模型接口
                # 构造包含摘要提示词和具体错误信息的完整提示
                error_guidance = ""
                if last_reason and last_reason != "未知错误":
                    if "JSON解析失败" in last_reason:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_reason}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。JSON 对象必须包含字段：module（字符串）、rust_signature（字符串）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                    else:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_reason}\n\n请确保输出格式正确：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签）；JSON 对象必须包含字段：module（字符串）、rust_signature（字符串）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"

                full_prompt = f"{usr_p}{error_guidance}\n\n{sum_p}"
                try:
                    response = agent.model.chat_until_success(full_prompt)
                    summary = response
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ [c2rust-transpiler][plan] 直接模型调用失败: {e}，回退到 run()"
                    )
                    summary = agent.run(usr_p)
            else:
                # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                summary = agent.run(usr_p)

            meta, parse_error = extract_json_from_summary(str(summary or ""))
            if parse_error:
                # JSON解析失败，将错误信息反馈给模型
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][plan] JSON解析失败: {parse_error}"
                )
                last_reason = f"JSON解析失败: {parse_error}"
                use_direct_model = True
                # 解析失败，继续重试
                continue
            else:
                ok, reason = _validate(meta)
            if ok:
                module = str(meta.get("module") or "").strip()
                rust_sig = str(meta.get("rust_signature") or "").strip()
                skip_impl = bool(meta.get("skip_implementation") is True)
                if skip_impl:
                    notes = str(meta.get("notes") or "")
                    PrettyOutput.auto_print(
                        f"✅ [c2rust-transpiler][plan] 第 {attempt} 次尝试成功: 模块={module}, 签名={rust_sig}, 跳过实现={skip_impl}"
                    )
                    if notes:
                        PrettyOutput.auto_print(
                            f"ℹ️ [c2rust-transpiler][plan] 跳过实现原因: {notes}"
                        )
                else:
                    PrettyOutput.auto_print(
                        f"✅ [c2rust-transpiler][plan] 第 {attempt} 次尝试成功: 模块={module}, 签名={rust_sig}"
                    )
                return module, rust_sig, skip_impl
            else:
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][plan] 第 {attempt} 次尝试失败: {reason}"
                )
                last_reason = reason
                # 格式校验失败，后续重试使用直接模型调用
                use_direct_model = True

        # 规划超出重试上限：回退到兜底方案（默认模块 src/ffi.rs + 简单占位签名）
        # 注意：如果 plan_max_retries_val == 0（无限重试），理论上不应该到达这里
        try:
            crate_root = self.crate_dir.resolve()
            fallback_module = str((crate_root / "src" / "ffi.rs").resolve())
        except Exception:
            fallback_module = "src/ffi.rs"
        fallback_sig = f"pub fn {rec.name or ('fn_' + str(rec.id))}()"
        PrettyOutput.auto_print(
            f"⚠️ [c2rust-transpiler][plan] 超出规划重试上限({plan_max_retries_val if plan_max_retries_val > 0 else '无限'})，回退到兜底: module={fallback_module}, signature={fallback_sig}"
        )
        return fallback_module, fallback_sig, False
