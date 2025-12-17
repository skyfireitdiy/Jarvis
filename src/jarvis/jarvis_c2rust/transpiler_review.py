# -*- coding: utf-8 -*-
"""
代码审查模块
"""

import json
import re
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.utils import dir_tree
from jarvis.jarvis_c2rust.utils import extract_json_from_summary
from jarvis.jarvis_c2rust.utils import truncate_git_diff_with_context_limit


class ReviewManager:
    """代码审查管理器"""

    def __init__(
        self,
        crate_dir: Path,
        data_dir: Path,
        llm_group: Optional[str],
        non_interactive: bool,
        review_max_iterations: int,
        disabled_libraries: List[str],
        progress: Dict[str, Any],
        save_progress_func: Callable[[], None],
        read_source_span_func: Callable[[FnRecord], str],
        collect_callees_context_func: Callable[[FnRecord], List[Dict[str, Any]]],
        extract_compile_flags_func: Callable[[str], Optional[str]],
        is_root_symbol_func: Callable[[FnRecord], bool],
        get_crate_commit_hash_func: Callable[[], Optional[str]],
        current_function_start_commit_getter: Callable[[], Optional[str]],
        compose_prompt_with_context_func: Callable[[str, bool], str],
        get_fix_agent_func: Callable[[Optional[str]], Any],
        check_and_handle_test_deletion_func: Callable[[Optional[str], Any], bool],
        append_additional_notes_func: Callable[[str], str],
        cargo_build_loop_func: Callable[[], Optional[bool]],
        get_build_loop_has_fixes_func: Callable[[], bool],
        on_before_tool_call_func: Callable[[Any, Any], None],
        on_after_tool_call_func: Callable[[Any, Any, Any, Any], None],
        agent_before_commits: Dict[str, Optional[str]],
        get_git_diff: Optional[Callable[[str], str]] = None,
        get_git_diff_func: Optional[Callable[[Optional[str]], str]] = None,
    ) -> None:
        self.crate_dir = crate_dir
        self.data_dir = data_dir
        self.llm_group = llm_group
        self.non_interactive = non_interactive
        self.review_max_iterations = review_max_iterations
        self.disabled_libraries = disabled_libraries
        self.progress = progress
        self.save_progress = save_progress_func
        self.read_source_span = read_source_span_func
        self.collect_callees_context = collect_callees_context_func
        self.extract_compile_flags = extract_compile_flags_func
        self.is_root_symbol = is_root_symbol_func
        self.get_crate_commit_hash = get_crate_commit_hash_func
        self.current_function_start_commit_getter = current_function_start_commit_getter
        self.compose_prompt_with_context: Callable[[str, bool], str] = (
            compose_prompt_with_context_func
        )
        self.get_fix_agent = get_fix_agent_func
        self.check_and_handle_test_deletion = check_and_handle_test_deletion_func
        self.append_additional_notes = append_additional_notes_func
        self.cargo_build_loop = cargo_build_loop_func
        self.get_build_loop_has_fixes = get_build_loop_has_fixes_func
        self.on_before_tool_call = on_before_tool_call_func
        self.on_after_tool_call = on_after_tool_call_func
        self.agent_before_commits = agent_before_commits
        self.get_git_diff = get_git_diff_func

    def review_and_optimize(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """
        审查生成的实现；若 summary 报告问题，则调用 CodeAgent 进行优化，直到无问题或次数用尽。
        合并了功能一致性审查和类型/边界严重问题审查，避免重复审查。
        审查只关注本次函数与相关最小上下文，避免全局重构。
        """

        def build_review_prompts() -> Tuple[str, str, str]:
            sys_p = (
                "你是Rust代码审查专家。验收标准：Rust 实现应与原始 C 实现在功能上一致，且不应包含可能导致功能错误的严重问题。\n"
                "**审查优先级**：测试破坏性检查 > 测试用例完备性 > 严重问题 > 破坏性变更 > 功能一致性 > 文件结构。优先检查测试是否被破坏（#[test] 标记丢失/重复、代码插入位置错误等），然后检查测试用例是否完备，再处理可能导致程序崩溃或编译失败的问题。\n"
                "**审查范围**：主要审查当前函数的实现，相关依赖函数作为辅助参考。\n"
                "审查标准（合并了功能一致性和严重问题检查）：\n"
                "1. 功能一致性检查：\n"
                "   - **核心功能定义**：核心输入输出、主要功能逻辑是否与 C 实现一致。核心功能指函数的主要目的和预期行为（如'计算哈希值'、'解析字符串'、'压缩数据'等），不包括实现细节；\n"
                "   - **安全改进允许行为不一致**：允许 Rust 实现修复 C 代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用、整数溢出、格式化字符串漏洞等），这些安全改进可能导致行为与 C 实现不一致，但这是允许的，不应被视为功能不一致；\n"
                "   - **忽略语言差异导致的行为不一致**：由于 Rust 和 C 语言的本质差异，以下行为差异是不可避免的，应被忽略：\n"
                "     * 整数溢出处理：Rust 在 debug 模式下会 panic，release 模式下会 wrapping，而 C 是未定义行为；\n"
                "     * 未定义行为：Rust 会避免或明确处理，而 C 可能产生未定义行为；\n"
                "     * 空指针/空引用：Rust 使用 Option<T> 或 Result<T, E> 处理，而 C 可能直接解引用导致崩溃；\n"
                "     * 内存安全：Rust 的借用检查器会阻止某些 C 中允许的不安全操作；\n"
                "     * 错误处理：Rust 使用 Result<T, E> 或 Option<T>，而 C 可能使用错误码或全局 errno；\n"
                "   - 允许 Rust 实现使用不同的类型设计、错误处理方式、资源管理方式等，只要功能一致即可；\n"
                "2. 严重问题检查（可能导致功能错误或程序崩溃）：\n"
                "   - 明显的空指针解引用或会导致 panic 的严重错误；\n"
                "   - 明显的越界访问或会导致程序崩溃的问题；\n"
                "   - 会导致程序无法正常运行的逻辑错误；\n"
                "3. 破坏性变更检测（对现有代码的影响）：\n"
                "   - **允许签名不一致**：允许函数签名、参数数量、参数类型、返回类型等与C实现不一致，只要功能实现了即可。这是Rust转译的正常现象，因为Rust的类型系统和设计理念与C不同；\n"
                "   - **仅检查实际破坏性影响**：只有当函数签名变更确实导致调用方代码无法编译或运行时，才报告为破坏性变更。如果调用方代码已经适配了新签名，或可以通过简单的适配解决，则不应视为破坏性变更；\n"
                "   - **⚠️⚠️ 重点：测试破坏性检查**：必须重点检查代码变更是否对当前测试造成破坏，这是最高优先级的检查项。具体包括：\n"
                "     * **检查 #[test] 标记丢失**：必须检查代码变更中是否错误删除了测试用例标记（#[test] 或 #[cfg(test)]）。如果发现删除了测试用例标记，必须报告为破坏性变更，除非：\n"
                "       - 测试用例被移动到其他位置（在diff中可以看到对应的添加）；\n"
                "       - 测试用例是重复的或过时的，确实需要删除；\n"
                "       - 测试用例被重构为其他形式的测试（如集成测试、文档测试等）；\n"
                "     * **检查 #[test] 标记重复**：必须检查代码变更中是否错误添加了重复的 #[test] 标记，导致测试函数被重复定义。如果发现重复的测试标记，必须报告为破坏性变更；\n"
                "     * **检查代码插入位置错误**：必须检查代码插入位置是否导致 #[test] 标记丢失或测试函数结构被破坏。例如：\n"
                "       - 在 #[test] 标记和测试函数之间插入了代码，导致测试标记失效；\n"
                "       - 在测试函数内部错误位置插入代码，导致测试函数结构被破坏；\n"
                "       - 在 #[cfg(test)] mod tests { ... } 块外部插入测试相关代码，导致测试无法运行；\n"
                "     * **检查测试函数结构破坏**：必须检查测试函数的完整性，确保测试函数没有被意外截断、合并或结构被破坏；\n"
                "     * **验证测试仍然可运行**：如果可能，检查测试代码的语法和结构是否正确，确保测试仍然可以被 cargo test 识别和运行；\n"
                "   - 检查模块导出变更是否会影响其他模块的导入（如 pub 关键字缺失、模块路径变更）；\n"
                "   - 检查类型定义变更是否会导致依赖该类型的代码失效（如结构体字段变更、枚举变体变更）；\n"
                "   - 检查常量或静态变量变更是否会影响引用该常量的代码；\n"
                "   - **优先使用diff信息**：如果diff中已包含调用方代码信息，优先基于diff判断；只有在diff信息不足时，才使用 read_code 工具读取调用方代码进行验证；\n"
                "4. 文件结构合理性检查：\n"
                "   - 检查模块文件位置是否符合 Rust 项目约定（如 src/ 目录结构、模块层次）；\n"
                "   - 检查文件命名是否符合 Rust 命名规范（如 snake_case、模块文件命名）；\n"
                "   - 检查模块组织是否合理（如相关功能是否放在同一模块、模块拆分是否过度或不足）；\n"
                "   - 检查模块导出是否合理（如 lib.rs 中的 pub mod 声明是否正确、是否遗漏必要的导出）；\n"
                "   - 检查是否存在循环依赖或过度耦合；\n"
                "5. 测试用例完备性检查：\n"
                "   - **检查是否有测试用例**：必须检查目标函数是否有对应的测试用例。如果完全没有测试用例，必须报告为功能一致性问题，因为无法验证 Rust 实现是否与 C 实现一致；\n"
                "   - **检查测试用例覆盖主要功能**：测试用例应该覆盖函数的主要功能路径和预期行为。如果测试用例只覆盖了部分功能，或缺少关键功能的测试，应报告为功能一致性问题；\n"
                "   - **检查测试用例覆盖边界情况**：测试用例应该覆盖边界情况，如：\n"
                "     * 空输入（空字符串、空数组、空指针等）；\n"
                "     * 极值输入（最大值、最小值、零值等）；\n"
                "     * 边界值（数组边界、字符串长度边界等）；\n"
                "     * 特殊值（负数、NaN、无穷大等，如果适用）；\n"
                "   - **检查测试用例覆盖错误情况**：如果 C 实现有错误处理（如返回错误码、设置 errno 等），测试用例应该覆盖这些错误情况。如果 Rust 实现使用 Result<T, E> 或 Option<T> 处理错误，测试用例应该验证错误情况；\n"
                "   - **检查测试用例与 C 实现行为一致**：测试用例的预期结果应该与 C 实现的行为一致。如果测试用例的预期结果与 C 实现不一致，应报告为功能一致性问题；\n"
                "   - **检查测试用例质量**：测试用例应该：\n"
                "     * 有清晰的测试名称，能够说明测试的目的；\n"
                "     * 有适当的断言，验证函数的输出和行为；\n"
                "     * 测试逻辑正确，能够真正验证函数的功能；\n"
                "   - **注意**：如果函数是资源释放类函数（如 fclose、free 等），在 Rust 中通过 RAII 自动管理，测试用例可以非常简单（如仅验证函数可以调用而不崩溃），这是可以接受的；\n"
                "不检查类型匹配、指针可变性、边界检查细节、资源释放细节、内存语义等技术细节（除非会导致功能错误）。\n"
                "**重要要求：在总结阶段，对于发现的每个问题，必须提供：**\n"
                "1. 详细的问题描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题\n"
                "2. 具体的修复建议：提供详细的修复方案，包括需要修改的代码位置、修改方式、预期效果等\n"
                "3. **修复代码示例（如果适用）**：对于可以明确修复的问题，提供具体的修复代码示例，包括修改前后的代码对比，帮助修复阶段快速定位和修复问题\n"
                "4. 问题分类：使用 [function] 标记功能一致性问题（包括测试用例完备性问题），使用 [critical] 标记严重问题，使用 [breaking] 标记破坏性变更，使用 [structure] 标记文件结构问题\n"
                "请在总结阶段详细指出问题、修改建议和修复代码示例，但不要尝试修复或修改任何代码，不要输出补丁。"
            )
            # 附加原始C函数源码片段，供审查作为只读参考
            c_code = self.read_source_span(rec) or ""
            # 附加被引用符号上下文与库替代上下文，以及crate目录结构，提供更完整审查背景
            callees_ctx = self.collect_callees_context(rec)
            librep_ctx = (
                rec.lib_replacement if isinstance(rec.lib_replacement, dict) else None
            )
            crate_tree = dir_tree(self.crate_dir)
            # 提取编译参数
            compile_flags = self.extract_compile_flags(rec.file)

            # 获取从初始commit到当前工作区的变更作为上下文（每次review都必须获取）
            # 使用统一的 get_git_diff 方法，可以获取到当前工作区的变更（包括未提交的修改）
            commit_diff = ""
            diff_status = ""  # 用于记录diff获取状态
            if self.get_git_diff:
                base_commit = self.current_function_start_commit_getter()
                try:
                    commit_diff = self.get_git_diff(base_commit)
                    if commit_diff and commit_diff.strip():
                        # 成功获取diff，限制长度避免上下文过大
                        # 使用50%的比例，因为review阶段需要更多的上下文信息
                        commit_diff = truncate_git_diff_with_context_limit(
                            commit_diff,
                            llm_group=self.llm_group,
                            token_ratio=0.5,
                            base_commit=base_commit,
                            crate_dir=self.crate_dir,
                        )
                        diff_status = "success"
                    else:
                        # 没有变更或获取失败
                        if base_commit:
                            current_commit = self.get_crate_commit_hash()
                            if current_commit == base_commit:
                                commit_diff = "(无变更：当前commit与函数开始时的commit相同，且工作区无修改)"
                                diff_status = "no_change"
                            else:
                                commit_diff = "(无法获取git差异)"
                                diff_status = "error"
                        else:
                            commit_diff = "(未记录函数开始时的commit id)"
                            diff_status = "no_start_commit"
                except Exception as e:
                    commit_diff = f"获取git差异时发生异常: {str(e)}"
                    diff_status = "error"
                    PrettyOutput.auto_print(
                        f"⚠️ [c2rust-transpiler][review] 获取git差异失败: {e}",
                    )
            else:
                # 没有提供 get_git_diff 函数
                commit_diff = "(未提供git差异获取函数)"
                diff_status = "no_git_diff_func"

            # 获取构建修复阶段的总结信息
            build_fixes_summary = ""
            try:
                cur = self.progress.get("current") or {}
                build_fixes = cur.get("build_fixes", [])
                if build_fixes:
                    build_fixes_summary = "\n\n【构建修复阶段总结】\n"
                    build_fixes_summary += (
                        "以下是在构建修复阶段进行的修复流程和结果总结，供审查参考：\n\n"
                    )
                    for i, fix_info in enumerate(build_fixes, 1):
                        fix_iter = fix_info.get("iteration", "?")
                        fix_stage = fix_info.get("stage", "unknown")
                        fix_tags = fix_info.get("tags", [])
                        fix_summary = fix_info.get("summary", "")
                        is_retry = fix_info.get("retry", False)
                        retry_marker = "（重试）" if is_retry else ""
                        build_fixes_summary += f"修复 #{i}（第 {fix_iter} 次迭代，阶段：{fix_stage}）{retry_marker}：\n"
                        if fix_tags:
                            build_fixes_summary += (
                                f"  错误分类：{', '.join(fix_tags)}\n"
                            )
                        if fix_summary:
                            build_fixes_summary += f"  修复总结：\n{fix_summary}\n"
                        build_fixes_summary += "\n"
                    build_fixes_summary += "提示：请参考上述修复总结，了解在构建修复阶段遇到的问题和修复过程，这有助于更准确地审查代码。"
            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][review] 获取构建修复总结失败: {e}",
                )

            usr_p_lines = [
                f"待审查函数：{rec.qname or rec.name}",
                f"建议签名：{rust_sig}",
                f"目标模块：{module}",
                f"**Crate 根目录（重要）**：{self.crate_dir.resolve()}",
                "  - 所有 Rust 源码文件都位于此目录下",
                "  - 使用 `read_code` 工具读取文件时，请使用相对于此目录的路径（如 `src/xxx.rs`）或绝对路径",
                "  - 使用 `edit_file_*` 工具编辑文件时，文件路径也应相对于此目录或使用绝对路径",
                f"源文件位置：{rec.file}:{rec.start_line}-{rec.end_line}",
                "",
                "原始C函数源码片段（只读参考，不要修改C代码）：",
                "<C_SOURCE>",
                c_code,
                "</C_SOURCE>",
                "",
            ]
            # 如果有构建修复总结，添加到 prompt 中
            if build_fixes_summary:
                usr_p_lines.append(build_fixes_summary)
                usr_p_lines.append("")

            usr_p_lines.extend(
                [
                    "审查说明（合并审查）：",
                    "**审查优先级**：测试破坏性检查 > 严重问题 > 破坏性变更 > 功能一致性 > 文件结构。优先检查测试是否被破坏（#[test] 标记丢失/重复、代码插入位置错误等），然后处理可能导致程序崩溃或编译失败的问题。",
                    "",
                    "1. 功能一致性：",
                    "   - **核心功能定义**：核心输入输出、主要功能逻辑是否与 C 实现一致。核心功能指函数的主要目的和预期行为（如'计算哈希值'、'解析字符串'、'压缩数据'等），不包括实现细节；",
                    "   - **安全改进允许行为不一致**：允许Rust实现修复C代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用、整数溢出、格式化字符串漏洞等），这些安全改进可能导致行为与 C 实现不一致，但这是允许的，不应被视为功能不一致；",
                    "   - **忽略语言差异导致的行为不一致**：由于 Rust 和 C 语言的本质差异，以下行为差异是不可避免的，应被忽略：",
                    "     * 整数溢出处理：Rust 在 debug 模式下会 panic，release 模式下会 wrapping，而 C 是未定义行为；",
                    "     * 未定义行为：Rust 会避免或明确处理，而 C 可能产生未定义行为；",
                    "     * 空指针/空引用：Rust 使用 Option<T> 或 Result<T, E> 处理，而 C 可能直接解引用导致崩溃；",
                    "     * 内存安全：Rust 的借用检查器会阻止某些 C 中允许的不安全操作；",
                    "     * 错误处理：Rust 使用 Result<T, E> 或 Option<T>，而 C 可能使用错误码或全局 errno；",
                    "   - 允许Rust实现使用不同的类型设计、错误处理方式、资源管理方式等，只要功能一致即可；",
                    "2. 严重问题（可能导致功能错误）：",
                    "   - 明显的空指针解引用或会导致 panic 的严重错误；",
                    "   - 明显的越界访问或会导致程序崩溃的问题；",
                    "3. 破坏性变更检测（对现有代码的影响）：",
                    "   - **允许签名不一致**：允许函数签名、参数数量、参数类型、返回类型等与C实现不一致，只要功能实现了即可。这是Rust转译的正常现象，因为Rust的类型系统和设计理念与C不同；",
                    "   - **仅检查实际破坏性影响**：只有当函数签名变更确实导致调用方代码无法编译或运行时，才报告为破坏性变更。如果调用方代码已经适配了新签名，或可以通过简单的适配解决，则不应视为破坏性变更；",
                    "   - **⚠️⚠️ 重点：测试破坏性检查**：必须重点检查代码变更是否对当前测试造成破坏，这是最高优先级的检查项。具体包括：",
                    "     * **检查 #[test] 标记丢失**：必须检查代码变更中是否错误删除了测试用例标记（#[test] 或 #[cfg(test)]）。如果发现删除了测试用例标记，必须报告为破坏性变更，除非：",
                    "       - 测试用例被移动到其他位置（在diff中可以看到对应的添加）；",
                    "       - 测试用例是重复的或过时的，确实需要删除；",
                    "       - 测试用例被重构为其他形式的测试（如集成测试、文档测试等）；",
                    "     * **检查 #[test] 标记重复**：必须检查代码变更中是否错误添加了重复的 #[test] 标记，导致测试函数被重复定义。如果发现重复的测试标记，必须报告为破坏性变更；",
                    "     * **检查代码插入位置错误**：必须检查代码插入位置是否导致 #[test] 标记丢失或测试函数结构被破坏。例如：",
                    "       - 在 #[test] 标记和测试函数之间插入了代码，导致测试标记失效；",
                    "       - 在测试函数内部错误位置插入代码，导致测试函数结构被破坏；",
                    "       - 在 #[cfg(test)] mod tests { ... } 块外部插入测试相关代码，导致测试无法运行；",
                    "     * **检查测试函数结构破坏**：必须检查测试函数的完整性，确保测试函数没有被意外截断、合并或结构被破坏；",
                    "     * **验证测试仍然可运行**：如果可能，检查测试代码的语法和结构是否正确，确保测试仍然可以被 cargo test 识别和运行；",
                    "   - 检查模块导出变更是否会影响其他模块的导入（如 pub 关键字缺失、模块路径变更）；",
                    "   - 检查类型定义变更是否会导致依赖该类型的代码失效（如结构体字段变更、枚举变体变更）；",
                    "   - 检查常量或静态变量变更是否会影响引用该常量的代码；",
                    "   - **优先使用diff信息**：如果diff中已包含调用方代码信息，优先基于diff判断；只有在diff信息不足时，才使用 read_code 工具读取调用方代码进行验证；",
                    "   - 如果该函数是根符号或被其他已转译函数调用，检查调用方代码是否仍能正常编译和使用；如果调用方已经适配了新签名，则不应视为破坏性变更；",
                    "4. 文件结构合理性检查：",
                    "   - 检查模块文件位置是否符合 Rust 项目约定（如 src/ 目录结构、模块层次）；",
                    "   - 检查文件命名是否符合 Rust 命名规范（如 snake_case、模块文件命名）；",
                    "   - 检查模块组织是否合理（如相关功能是否放在同一模块、模块拆分是否过度或不足）；",
                    "   - 检查模块导出是否合理（如 lib.rs 中的 pub mod 声明是否正确、是否遗漏必要的导出）；",
                    "   - 检查是否存在循环依赖或过度耦合；",
                    "   - 检查文件大小是否合理（如单个文件是否过大需要拆分，或是否过度拆分导致文件过多）；",
                    "5. 测试用例完备性检查：",
                    "   - **检查是否有测试用例**：必须检查目标函数是否有对应的测试用例。如果完全没有测试用例，必须报告为功能一致性问题，因为无法验证 Rust 实现是否与 C 实现一致；",
                    "   - **检查测试用例覆盖主要功能**：测试用例应该覆盖函数的主要功能路径和预期行为。如果测试用例只覆盖了部分功能，或缺少关键功能的测试，应报告为功能一致性问题；",
                    "   - **检查测试用例覆盖边界情况**：测试用例应该覆盖边界情况，如空输入（空字符串、空数组、空指针等）、极值输入（最大值、最小值、零值等）、边界值（数组边界、字符串长度边界等）、特殊值（负数、NaN、无穷大等，如果适用）；",
                    "   - **检查测试用例覆盖错误情况**：如果 C 实现有错误处理（如返回错误码、设置 errno 等），测试用例应该覆盖这些错误情况。如果 Rust 实现使用 Result<T, E> 或 Option<T> 处理错误，测试用例应该验证错误情况；",
                    "   - **检查测试用例与 C 实现行为一致**：测试用例的预期结果应该与 C 实现的行为一致。如果测试用例的预期结果与 C 实现不一致，应报告为功能一致性问题；",
                    "   - **检查测试用例质量**：测试用例应该有清晰的测试名称、适当的断言、正确的测试逻辑，能够真正验证函数的功能；",
                    "   - **注意**：如果函数是资源释放类函数（如 fclose、free 等），在 Rust 中通过 RAII 自动管理，测试用例可以非常简单（如仅验证函数可以调用而不崩溃），这是可以接受的；",
                    "不检查类型匹配、指针可变性、边界检查细节等技术细节（除非会导致功能错误）。",
                    "",
                    "**重要：问题报告要求**",
                    "对于发现的每个问题，必须在总结中提供：",
                    "1. 详细的问题描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题",
                    "2. 具体的修复建议：提供详细的修复方案，包括需要修改的代码位置、修改方式、预期效果等",
                    "3. **修复代码示例（如果适用）**：对于可以明确修复的问题，必须提供具体的修复代码示例，包括修改前后的代码对比。格式要求：",
                    "   - 修改前：显示有问题的代码片段（包含足够的上下文，如函数签名、前后几行代码）",
                    "   - 修改后：显示修复后的代码片段",
                    "   - 使用代码块格式（```rust ... ```）展示代码",
                    "   - 如果问题涉及多个位置，提供所有相关位置的修复代码示例",
                    "4. 问题分类：使用 [function] 标记功能一致性问题，使用 [critical] 标记严重问题，使用 [breaking] 标记破坏性变更，使用 [structure] 标记文件结构问题",
                    "示例（必须包含修复代码示例）：",
                    '  "[function] 返回值处理缺失：在函数 foo 的第 42 行，当输入参数为负数时，函数没有返回错误码，但 C 实现中会返回 -1。修复建议：在函数开始处添加参数验证，当参数为负数时返回 Result::Err(Error::InvalidInput)。修复代码示例：\n'
                    "    修改前：\n"
                    "    ```rust\n"
                    "    pub fn foo(x: i32) -> i32 {\n"
                    "        // 缺少参数验证\n"
                    "        x * 2\n"
                    "    }\n"
                    "    ```\n"
                    "    修改后：\n"
                    "    ```rust\n"
                    "    pub fn foo(x: i32) -> Result<i32, Error> {\n"
                    "        if x < 0 {\n"
                    "            return Err(Error::InvalidInput);\n"
                    "        }\n"
                    "        Ok(x * 2)\n"
                    "    }\n"
                    '    ```"',
                    '  "[critical] 空指针解引用风险：在函数 bar 的第 58 行，直接解引用指针 ptr 而没有检查其是否为 null，可能导致 panic。修复建议：使用 if let Some(value) = ptr.as_ref() 进行空指针检查，或使用 Option<&T> 类型。修复代码示例：\n'
                    "    修改前：\n"
                    "    ```rust\n"
                    "    pub fn bar(ptr: *const i32) -> i32 {\n"
                    "        unsafe { *ptr }\n"
                    "    }\n"
                    "    ```\n"
                    "    修改后：\n"
                    "    ```rust\n"
                    "    pub fn bar(ptr: Option<&i32>) -> Option<i32> {\n"
                    "        ptr.map(|p| *p)\n"
                    "    }\n"
                    '    ```"',
                    '  "[breaking] 测试函数重复定义：在 src/common/buffer.rs 第 111-112 行处，新增的测试函数 test_write_buf_1_byte 被同时标记了两次 #[test]，导致重复定义。修复建议：删除其中一个 #[test] 标记，确保每个测试函数只有一个 #[test] 属性。修复代码示例：\n'
                    "    修改前：\n"
                    "    ```rust\n"
                    "    #[test]\n"
                    "    #[test]  // 重复的标记\n"
                    "    fn test_write_buf_1_byte() {\n"
                    "        // ...\n"
                    "    }\n"
                    "    ```\n"
                    "    修改后：\n"
                    "    ```rust\n"
                    "    #[test]\n"
                    "    fn test_write_buf_1_byte() {\n"
                    "        // ...\n"
                    "    }\n"
                    '    ```"',
                    '  "[function] 测试用例缺失：函数 foo 没有对应的测试用例，无法验证 Rust 实现是否与 C 实现一致。修复建议：在目标模块的 #[cfg(test)] mod tests { ... } 块中添加测试用例，覆盖函数的主要功能、边界情况和错误情况。修复代码示例：\n'
                    "    修改前（src/foo.rs）：\n"
                    "    ```rust\n"
                    "    pub fn foo(x: i32) -> i32 {\n"
                    "        x * 2\n"
                    "    }\n"
                    "    // 缺少测试用例\n"
                    "    ```\n"
                    "    修改后（src/foo.rs）：\n"
                    "    ```rust\n"
                    "    pub fn foo(x: i32) -> i32 {\n"
                    "        x * 2\n"
                    "    }\n"
                    "    \n"
                    "    #[cfg(test)]\n"
                    "    mod tests {\n"
                    "        use super::*;\n"
                    "        \n"
                    "        #[test]\n"
                    "        fn test_foo_normal() {\n"
                    "            assert_eq!(foo(5), 10);\n"
                    "        }\n"
                    "        \n"
                    "        #[test]\n"
                    "        fn test_foo_zero() {\n"
                    "            assert_eq!(foo(0), 0);\n"
                    "        }\n"
                    "    }\n"
                    '    ```"',
                    '  "[structure] 模块导出缺失：函数 qux 所在的模块 utils 未在 src/lib.rs 中导出，导致无法从 crate 外部访问。修复建议：在 src/lib.rs 中添加 `pub mod utils;` 声明。修复代码示例：\n'
                    "    修改前（src/lib.rs）：\n"
                    "    ```rust\n"
                    "    // 缺少 pub mod utils;\n"
                    "    ```\n"
                    "    修改后（src/lib.rs）：\n"
                    "    ```rust\n"
                    "    pub mod utils;\n"
                    '    ```"',
                    "",
                    "被引用符号上下文（如已转译则包含Rust模块信息）：",
                    json.dumps(callees_ctx, ensure_ascii=False, indent=2),
                    "",
                    "库替代上下文（若存在）：",
                    json.dumps(librep_ctx, ensure_ascii=False, indent=2),
                    "",
                ]
            )
            # 添加禁用库列表（如果存在）
            if self.disabled_libraries:
                usr_p_lines.append(
                    f"禁用库列表（禁止在实现中使用这些库）：{', '.join(self.disabled_libraries)}"
                )
            # 添加根符号要求（如果是根符号）
            if self.is_root_symbol(rec):
                usr_p_lines.append(
                    f"根符号要求：此函数是根符号（{rec.qname or rec.name}），必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。"
                )
            # 添加编译参数（如果存在）
            if compile_flags:
                usr_p_lines.extend(
                    [
                        "",
                        "C文件编译参数（来自 compile_commands.json）：",
                        compile_flags,
                    ]
                )
            usr_p_lines.extend(
                [
                    "",
                    "当前crate目录结构（部分）：",
                    "<CRATE_TREE>",
                    crate_tree,
                    "</CRATE_TREE>",
                ]
            )

            # 添加git变更上下文（每次review都必须包含）
            usr_p_lines.extend(
                [
                    "",
                    "从函数开始到当前的git变更（用于了解代码变更历史和上下文，包括未提交的修改）：",
                    "<GIT_DIFF>",
                    commit_diff,
                    "</GIT_DIFF>",
                    "",
                ]
            )

            # 根据diff状态添加不同的说明
            if diff_status == "success":
                usr_p_lines.extend(
                    [
                        "**重要：git变更上下文说明**",
                        "- 上述diff显示了从函数开始处理时的commit到当前工作区的所有变更（包括已提交和未提交的修改）",
                        "- 这些变更可能包括：当前函数的实现、依赖函数的实现、模块结构的调整等",
                        "- **优先使用diff信息进行审查判断**：如果diff中已经包含了足够的信息（如函数实现、签名变更、模块结构等），可以直接基于diff进行审查，无需读取原始文件",
                        "- 只有在diff信息不足或需要查看完整上下文时，才使用 read_code 工具读取原始文件",
                        "- 在审查破坏性变更时，请特别关注这些变更对现有代码的影响",
                        "- 如果发现变更中存在问题（如破坏性变更、文件结构不合理等），请在审查报告中指出",
                    ]
                )
            elif diff_status == "no_change":
                usr_p_lines.extend(
                    [
                        "**注意**：当前commit与函数开始时的commit相同，且工作区无修改，说明没有代码变更。请使用 read_code 工具读取目标模块文件的最新内容进行审查。",
                    ]
                )
            else:
                # diff_status 为 "error"、"no_current_commit"、"no_start_commit" 或 "no_git_diff_func"
                usr_p_lines.extend(
                    [
                        "**注意**：由于无法获取git差异信息，请使用 read_code 工具读取目标模块文件的最新内容进行审查。",
                    ]
                )

            usr_p_lines.extend(
                [
                    "",
                    "如需定位或交叉验证 C 符号位置，请使用符号表检索工具：",
                    "- 工具: read_symbols",
                    "- 参数示例(JSON):",
                    f'  {{"symbols_file": "{(self.data_dir / "symbols.jsonl").resolve()}", "symbols": ["{rec.qname or rec.name}"]}}',
                    "",
                    "**代码读取工具使用说明**：",
                    "- 工具: read_code",
                    "- 用途: 读取 C 源码实现或 Rust 模块文件",
                    "- **重要**：读取 Rust 源码文件时，必须使用绝对路径或相对于 crate 根目录的路径",
                    f"- **Crate 根目录**：{self.crate_dir.resolve()}",
                    "  - 示例：",
                    f"    * 读取 Rust 文件：`read_code` 工具，文件路径使用 `{self.crate_dir.resolve()}/src/xxx.rs` 或 `src/xxx.rs`（相对于 crate 根目录）",
                    "    * 读取 C 文件：`read_code` 工具，文件路径使用 C 源文件的完整路径",
                    "",
                    "**重要：审查要求**",
                    "- **优先使用diff信息**：如果提供了git差异（GIT_DIFF），优先基于diff信息进行审查判断，只有在diff信息不足时才使用 read_code 工具读取原始文件",
                    "- 必须基于最新的代码进行审查，如果使用 read_code 工具，请读取目标模块文件的最新内容",
                    f"- **使用 read_code 工具时，文件路径应相对于 crate 根目录（{self.crate_dir.resolve()}）或使用绝对路径**",
                    "- 禁止依赖任何历史记忆、之前的审查结论或对话历史进行判断",
                    "- 每次审查都必须基于最新的代码状态（通过diff或read_code获取），确保审查结果反映当前代码的真实状态",
                    "- 结合git变更上下文（如果提供），全面评估代码变更的影响和合理性",
                    "",
                    "请基于提供的diff信息（如果可用）或读取crate中该函数的当前实现进行审查，并准备总结。",
                ]
            )
            usr_p = "\n".join(usr_p_lines)
            sum_p = (
                "请仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段：\n"
                '"ok": bool  // 若满足功能一致且无严重问题、无破坏性变更、文件结构合理，则为 true\n'
                '"function_issues": [string, ...]  // 功能一致性问题，每项以 [function] 开头，必须包含详细的问题描述和修复建议\n'
                '"critical_issues": [string, ...]  // 严重问题（可能导致功能错误），每项以 [critical] 开头，必须包含详细的问题描述和修复建议\n'
                '"breaking_issues": [string, ...]  // 破坏性变更问题（对现有代码的影响），每项以 [breaking] 开头，必须包含详细的问题描述和修复建议\n'
                '"structure_issues": [string, ...]  // 文件结构问题，每项以 [structure] 开头，必须包含详细的问题描述和修复建议\n'
                "注意：\n"
                "- 前置条件：必须在crate中找到该函数的实现（匹配函数名或签名）。若未找到，ok 必须为 false，function_issues 应包含 [function] function not found: 详细描述问题位置和如何查找函数实现\n"
                "- **安全改进允许行为不一致**：若Rust实现修复了C代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用等），即使导致行为与 C 实现不一致，这也是允许的，不应被视为功能不一致；\n"
                "- **忽略语言差异导致的行为不一致**：由于 Rust 和 C 语言的本质差异（如内存安全、类型系统、错误处理、未定义行为处理等），某些行为差异是不可避免的，这些差异应被忽略，不应被视为功能不一致；\n"
                "- **允许签名不一致**：允许函数签名、参数数量、参数类型、返回类型等与C实现不一致，只要功能实现了即可。这是Rust转译的正常现象，不应被视为破坏性变更；\n"
                "- **破坏性变更判断标准**：只有当函数签名变更确实导致调用方代码无法编译或运行时，才报告为破坏性变更。如果调用方代码已经适配了新签名，或可以通过简单的适配解决，则不应视为破坏性变更；\n"
                "- **⚠️⚠️ 重点：测试破坏性检查**：必须重点检查代码变更是否对当前测试造成破坏，这是最高优先级的检查项。具体包括：\n"
                "  1. **检查 #[test] 标记丢失**：必须检查代码变更中是否错误删除了测试用例标记（#[test] 或 #[cfg(test)]）。如果发现删除了测试用例标记且没有合理的理由（如移动到其他位置、重复测试等），必须报告为破坏性变更；\n"
                "  2. **检查 #[test] 标记重复**：必须检查代码变更中是否错误添加了重复的 #[test] 标记，导致测试函数被重复定义。如果发现重复的测试标记，必须报告为破坏性变更；\n"
                "  3. **检查代码插入位置错误**：必须检查代码插入位置是否导致 #[test] 标记丢失或测试函数结构被破坏。例如：在 #[test] 标记和测试函数之间插入了代码、在测试函数内部错误位置插入代码、在 #[cfg(test)] mod tests { ... } 块外部插入测试相关代码等；\n"
                "  4. **检查测试函数结构破坏**：必须检查测试函数的完整性，确保测试函数没有被意外截断、合并或结构被破坏；\n"
                "  5. **验证测试仍然可运行**：如果可能，检查测试代码的语法和结构是否正确，确保测试仍然可以被 cargo test 识别和运行；\n"
                "- **⚠️⚠️ 重点：测试用例完备性检查**：必须检查测试用例是否完备，这是第二优先级的检查项。具体包括：\n"
                "  1. **检查是否有测试用例**：必须检查目标函数是否有对应的测试用例。如果完全没有测试用例，必须报告为功能一致性问题（[function]），因为无法验证 Rust 实现是否与 C 实现一致；\n"
                "  2. **检查测试用例覆盖主要功能**：测试用例应该覆盖函数的主要功能路径和预期行为。如果测试用例只覆盖了部分功能，或缺少关键功能的测试，应报告为功能一致性问题；\n"
                "  3. **检查测试用例覆盖边界情况**：测试用例应该覆盖边界情况，如空输入（空字符串、空数组、空指针等）、极值输入（最大值、最小值、零值等）、边界值（数组边界、字符串长度边界等）、特殊值（负数、NaN、无穷大等，如果适用）；\n"
                "  4. **检查测试用例覆盖错误情况**：如果 C 实现有错误处理（如返回错误码、设置 errno 等），测试用例应该覆盖这些错误情况。如果 Rust 实现使用 Result<T, E> 或 Option<T> 处理错误，测试用例应该验证错误情况；\n"
                "  5. **检查测试用例与 C 实现行为一致**：测试用例的预期结果应该与 C 实现的行为一致。如果测试用例的预期结果与 C 实现不一致，应报告为功能一致性问题；\n"
                "  6. **检查测试用例质量**：测试用例应该有清晰的测试名称、适当的断言、正确的测试逻辑，能够真正验证函数的功能；\n"
                "  7. **注意**：如果函数是资源释放类函数（如 fclose、free 等），在 Rust 中通过 RAII 自动管理，测试用例可以非常简单（如仅验证函数可以调用而不崩溃），这是可以接受的；\n"
                "- 若Rust实现使用了不同的实现方式但保持了功能一致，且无严重问题、无破坏性变更、文件结构合理，ok 应为 true\n"
                "- 仅报告功能不一致、严重问题、破坏性变更和文件结构问题，不报告类型匹配、指针可变性、边界检查细节等技术细节（除非会导致功能错误）\n"
                "- **重要：每个问题描述必须包含以下内容：**\n"
                "  1. 问题的详细描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题\n"
                "  2. 修复建议：提供具体的修复方案，包括需要修改的代码位置、修改方式、预期效果等\n"
                "  3. **修复代码示例（如果适用）**：对于可以明确修复的问题，提供具体的修复代码示例，包括修改前后的代码对比。格式：\n"
                "     - 修改前：显示有问题的代码片段（包含足够的上下文，如函数签名、前后几行代码）\n"
                "     - 修改后：显示修复后的代码片段\n"
                "     - 如果问题涉及多个位置，提供所有相关位置的修复代码示例\n"
                "  4. 问题格式：[function]、[critical]、[breaking] 或 [structure] 开头，后跟详细的问题描述、修复建议和修复代码示例\n"
                "  示例格式：\n"
                '    "[function] 返回值处理缺失：在函数 foo 的第 42 行，当输入参数为负数时，函数没有返回错误码，但 C 实现中会返回 -1。修复建议：在函数开始处添加参数验证，当参数为负数时返回 Result::Err(Error::InvalidInput)。修复代码示例：\n'
                "    修改前：\n"
                "    ```rust\n"
                "    pub fn foo(x: i32) -> i32 {\n"
                "        // 缺少参数验证\n"
                "        x * 2\n"
                "    }\n"
                "    ```\n"
                "    修改后：\n"
                "    ```rust\n"
                "    pub fn foo(x: i32) -> Result<i32, Error> {\n"
                "        if x < 0 {\n"
                "            return Err(Error::InvalidInput);\n"
                "        }\n"
                "        Ok(x * 2)\n"
                "    }\n"
                '    ```"\n'
                '    "[critical] 空指针解引用风险：在函数 bar 的第 58 行，直接解引用指针 ptr 而没有检查其是否为 null，可能导致 panic。修复建议：使用 if let Some(value) = ptr.as_ref() 进行空指针检查，或使用 Option<&T> 类型。修复代码示例：\n'
                "    修改前：\n"
                "    ```rust\n"
                "    pub fn bar(ptr: *const i32) -> i32 {\n"
                "        unsafe { *ptr }\n"
                "    }\n"
                "    ```\n"
                "    修改后：\n"
                "    ```rust\n"
                "    pub fn bar(ptr: Option<&i32>) -> Option<i32> {\n"
                "        ptr.map(|p| *p)\n"
                "    }\n"
                '    ```"\n'
                '    "[breaking] 测试函数重复定义：在 src/common/buffer.rs 第 111-112 行处，新增的测试函数 test_write_buf_1_byte 被同时标记了两次 #[test]，导致重复定义。修复建议：删除其中一个 #[test] 标记，确保每个测试函数只有一个 #[test] 属性。修复代码示例：\n'
                "    修改前：\n"
                "    ```rust\n"
                "    #[test]\n"
                "    #[test]  // 重复的标记\n"
                "    fn test_write_buf_1_byte() {\n"
                "        // ...\n"
                "    }\n"
                "    ```\n"
                "    修改后：\n"
                "    ```rust\n"
                "    #[test]\n"
                "    fn test_write_buf_1_byte() {\n"
                "        // ...\n"
                "    }\n"
                '    ```"\n'
                '    "[structure] 模块导出缺失：函数 qux 所在的模块 utils 未在 src/lib.rs 中导出，导致无法从 crate 外部访问。修复建议：在 src/lib.rs 中添加 `pub mod utils;` 声明。修复代码示例：\n'
                "    修改前（src/lib.rs）：\n"
                "    ```rust\n"
                "    // 缺少 pub mod utils;\n"
                "    ```\n"
                "    修改后（src/lib.rs）：\n"
                "    ```rust\n"
                "    pub mod utils;\n"
                '    ```"\n'
                "请严格按以下格式输出（JSON格式，支持jsonnet语法如尾随逗号、注释、|||分隔符多行字符串等）：\n"
                "**示例1：审查通过（无问题）**\n"
                '<SUMMARY>\n{\n  "ok": true,\n  "function_issues": [],\n  "critical_issues": [],\n  "breaking_issues": [],\n  "structure_issues": []\n}\n</SUMMARY>\n'
                "**示例2：发现问题（必须报告问题）**\n"
                '<SUMMARY>\n{\n  "ok": false,\n  "function_issues": [],\n  "critical_issues": [],\n  "breaking_issues": [\n    "[breaking] 测试函数重复定义：在 src/common/buffer.rs 第 111-112 行处，新增的测试函数 test_write_buf_1_byte 被同时标记了两次 #[test]，导致重复定义。修复建议：删除其中一个 #[test] 标记，确保每个测试函数只有一个 #[test] 属性。"\n  ],\n  "structure_issues": []\n}\n</SUMMARY>\n'
                "**重要**：如果发现问题，ok 必须为 false，并在相应的问题数组中报告问题。不要因为只有小问题就设置 ok 为 true。"
            )
            # 在 usr_p 和 sum_p 中追加附加说明（sys_p 通常不需要）
            usr_p = self.append_additional_notes(usr_p)
            sum_p = self.append_additional_notes(sum_p)
            return sys_p, usr_p, sum_p

        i = 0
        max_iterations = self.review_max_iterations
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换

        # 获取函数信息用于 Agent name
        fn_name = rec.qname or rec.name or f"fn_{rec.id}"
        agent_name = f"C2Rust-Review-Agent({fn_name})"

        # 0表示无限重试，否则限制迭代次数
        use_direct_model_review = False  # 标记是否使用直接模型调用
        parse_failed = False  # 标记上一次解析是否失败
        parse_error_msg: Optional[str] = None  # 保存上一次的YAML解析错误信息
        previous_issues: Dict[
            str, List[str]
        ] = {}  # 保存上一次审查发现的问题，用于验证是否已修复
        while max_iterations == 0 or i < max_iterations:
            # 每次迭代都创建新的 Agent，避免历史记忆干扰
            # 但会在提示词中包含 previous_issues
            sys_p_init, _, sum_p_init = build_review_prompts()
            review_agent = Agent(
                system_prompt=sys_p_init,
                name=agent_name,
                model_group=self.llm_group,
                summary_prompt=sum_p_init,
                need_summary=True,
                auto_complete=True,
                use_tools=["execute_script", "read_code", "read_symbols"],
                non_interactive=self.non_interactive,
                use_methodology=False,
                use_analysis=False,
            )
            # 订阅 BEFORE_TOOL_CALL 和 AFTER_TOOL_CALL 事件，用于细粒度检测测试代码删除
            review_agent.event_bus.subscribe(BEFORE_TOOL_CALL, self.on_before_tool_call)
            review_agent.event_bus.subscribe(AFTER_TOOL_CALL, self.on_after_tool_call)
            # 记录 Agent 创建时的 commit id（作为初始值）
            agent_id = id(review_agent)
            agent_key = f"agent_{agent_id}"
            initial_commit = self.get_crate_commit_hash()
            if initial_commit:
                self.agent_before_commits[agent_key] = initial_commit

            agent = review_agent
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换

            # 每次迭代都重新获取最新的 diff（从保存的 commit 到当前的 HEAD）
            # 重新构建 user prompt，包含最新的 diff
            _, usr_p_current, _ = build_review_prompts()  # 重新构建，获取最新的 diff

            if i > 0:
                # 修复后的审查，添加代码已更新的提示和之前问题的验证要求
                previous_issues_text = ""
                if previous_issues:
                    previous_issues_lines = []
                    if previous_issues.get("function_issues"):
                        previous_issues_lines.append("功能一致性问题：")
                        previous_issues_lines.extend(
                            [
                                f"  - {issue}"
                                for issue in previous_issues["function_issues"]
                            ]
                        )
                    if previous_issues.get("critical_issues"):
                        previous_issues_lines.append("严重问题：")
                        previous_issues_lines.extend(
                            [
                                f"  - {issue}"
                                for issue in previous_issues["critical_issues"]
                            ]
                        )
                    if previous_issues.get("breaking_issues"):
                        previous_issues_lines.append("破坏性变更问题：")
                        previous_issues_lines.extend(
                            [
                                f"  - {issue}"
                                for issue in previous_issues["breaking_issues"]
                            ]
                        )
                    if previous_issues.get("structure_issues"):
                        previous_issues_lines.append("文件结构问题：")
                        previous_issues_lines.extend(
                            [
                                f"  - {issue}"
                                for issue in previous_issues["structure_issues"]
                            ]
                        )
                    if previous_issues_lines:
                        previous_issues_text = "\n".join(
                            [
                                "",
                                "【重要：需要验证之前发现的问题是否已修复】",
                                f"在第 {i} 次审查中，发现了以下问题：",
                                "<PREVIOUS_ISSUES>",
                                "\n".join(previous_issues_lines),
                                "</PREVIOUS_ISSUES>",
                                "",
                                "**必须验证：**",
                                "- 请仔细检查上述每个问题是否已经在代码修复中得到解决",
                                "- 如果问题仍然存在，必须再次报告为相应类型的问题",
                                "- 如果问题已经修复，则不应再报告",
                                "- **必须使用 read_code 工具或 git diff 来验证问题是否已修复，不能仅凭假设**",
                                "",
                            ]
                        )

                code_changed_notice = "\n".join(
                    [
                        "",
                        "【重要：代码已更新】",
                        f"在本次审查之前（第 {i} 次迭代），已根据审查意见对代码进行了修复和优化。",
                        "目标函数的实现已经发生变化，包括但不限于：",
                        "- 函数实现逻辑的修改",
                        "- 类型和签名的调整",
                        "- 依赖关系的更新",
                        "- 错误处理的改进",
                        "",
                        "**审查要求：**",
                        "- **优先使用diff信息**：如果提供了最新的git差异（GIT_DIFF），优先基于diff信息进行审查判断，只有在diff信息不足时才使用 read_code 工具读取原始文件",
                        "- 如果必须使用 read_code 工具，请读取目标模块文件的最新内容",
                        "- **禁止基于之前的审查结果、对话历史或任何缓存信息进行判断**",
                        "- 必须基于最新的代码状态（通过diff或read_code获取）进行审查评估",
                        "",
                        "如果diff信息充足，可以直接基于diff进行审查；如果diff信息不足，请使用 read_code 工具读取最新代码。",
                        "",
                    ]
                )
                usr_p_with_notice = (
                    usr_p_current + previous_issues_text + code_changed_notice
                )
                composed_prompt = self.compose_prompt_with_context(
                    usr_p_with_notice, False
                )
                # 修复后必须使用 Agent.run()，不能使用直接模型调用（因为需要工具调用）
                use_direct_model_review = False
            else:
                composed_prompt = self.compose_prompt_with_context(usr_p_current, False)

            if use_direct_model_review:
                # 格式解析失败后，直接调用模型接口
                # 构造包含摘要提示词和具体错误信息的完整提示
                error_guidance = ""
                # 检查上一次的解析结果
                if parse_error_msg:
                    # 如果有JSON解析错误，优先反馈
                    error_guidance = (
                        f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n"
                        f"- JSON解析失败: {parse_error_msg}\n\n"
                        f"请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。JSON 对象必须包含字段：ok（布尔值）、function_issues（字符串数组）、critical_issues（字符串数组）、breaking_issues（字符串数组）、structure_issues（字符串数组）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                    )
                elif parse_failed:
                    error_guidance = (
                        "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n"
                        "- 无法从摘要中解析出有效的 JSON 对象\n\n"
                        "请确保输出格式正确：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段：ok（布尔值）、function_issues（字符串数组）、critical_issues（字符串数组）、breaking_issues（字符串数组）、structure_issues（字符串数组）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                    )

                full_prompt = f"{composed_prompt}{error_guidance}\n\n{sum_p_init}"
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][review] 直接调用模型接口修复格式错误（第 {i + 1} 次重试）",
                )
                try:
                    response = agent.model.chat_until_success(full_prompt)
                    summary = str(response or "")
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ [c2rust-transpiler][review] 直接模型调用失败: {e}，回退到 run()",
                    )
                    summary = str(agent.run(composed_prompt) or "")
            else:
                # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                summary = str(agent.run(composed_prompt) or "")

            # 解析 JSON 格式的审查结果
            verdict, parse_error_review = extract_json_from_summary(summary)
            parse_failed = False
            parse_error_msg = None
            if parse_error_review:
                # JSON解析失败
                parse_failed = True
                parse_error_msg = parse_error_review
                PrettyOutput.auto_print(
                    f"[c2rust-transpiler][review] JSON解析失败: {parse_error_review}",
                )
                # 兼容旧格式：尝试解析纯文本 OK
                m = re.search(
                    r"<SUMMARY>([\s\S]*?)</SUMMARY>", summary, flags=re.IGNORECASE
                )
                content = (m.group(1).strip() if m else summary.strip()).upper()
                if content == "OK":
                    verdict = {
                        "ok": True,
                        "function_issues": [],
                        "critical_issues": [],
                        "breaking_issues": [],
                        "structure_issues": [],
                    }
                    parse_failed = False  # 兼容格式成功，不算解析失败
                    parse_error_msg = None
                else:
                    # 无法解析，立即重试：设置标志并继续循环
                    use_direct_model_review = True
                    parse_error_msg = f"无法从摘要中解析出有效的 JSON 对象，得到的内容类型为: {type(verdict).__name__}"
                    # 继续循环，立即重试
                    continue

            ok = bool(verdict.get("ok") is True)
            raw_function_issues = verdict.get("function_issues")
            function_issues: list[str] = (
                [str(item) for item in raw_function_issues]
                if isinstance(raw_function_issues, list)
                else []
            )
            raw_critical_issues = verdict.get("critical_issues")
            critical_issues: list[str] = (
                [str(item) for item in raw_critical_issues]
                if isinstance(raw_critical_issues, list)
                else []
            )
            raw_breaking_issues = verdict.get("breaking_issues")
            breaking_issues: list[str] = (
                [str(item) for item in raw_breaking_issues]
                if isinstance(raw_breaking_issues, list)
                else []
            )
            raw_structure_issues = verdict.get("structure_issues")
            structure_issues: list[str] = (
                [str(item) for item in raw_structure_issues]
                if isinstance(raw_structure_issues, list)
                else []
            )

            PrettyOutput.auto_print(
                f"📊 [c2rust-transpiler][review][iter={i + 1}] verdict ok={ok}, function_issues={len(function_issues)}, critical_issues={len(critical_issues)}, breaking_issues={len(breaking_issues)}, structure_issues={len(structure_issues)}",
            )

            # 保存本次审查发现的问题，供下次审查时验证（仅在发现问题时保存）
            if (
                not ok
                or function_issues
                or critical_issues
                or breaking_issues
                or structure_issues
            ):
                previous_issues = {
                    "function_issues": list(function_issues),
                    "critical_issues": list(critical_issues),
                    "breaking_issues": list(breaking_issues),
                    "structure_issues": list(structure_issues),
                }

            # 如果 ok 为 true，表示审查通过（功能一致且无严重问题、无破坏性变更、文件结构合理），直接返回，不触发修复
            if ok:
                limit_info = (
                    f" (上限: {max_iterations if max_iterations > 0 else '无限'})"
                )
                PrettyOutput.auto_print(
                    f"✅ [c2rust-transpiler][review] 代码审查通过{limit_info} (共 {i + 1} 次迭代)。",
                )
                # 清理当前 agent 的事件订阅和记录
                try:
                    review_agent.event_bus.unsubscribe(
                        BEFORE_TOOL_CALL, self.on_before_tool_call
                    )
                    review_agent.event_bus.unsubscribe(
                        AFTER_TOOL_CALL, self.on_after_tool_call
                    )
                    # 清理 agent_before_commits 中的记录
                    if agent_key in self.agent_before_commits:
                        del self.agent_before_commits[agent_key]
                except Exception:
                    pass
                # 记录审查结果到进度
                try:
                    cur = self.progress.get("current") or {}
                    cur["review"] = {
                        "ok": True,
                        "function_issues": list(function_issues),
                        "critical_issues": list(critical_issues),
                        "breaking_issues": list(breaking_issues),
                        "structure_issues": list(structure_issues),
                        "iterations": i + 1,
                    }
                    metrics = cur.get("metrics") or {}
                    metrics["review_iterations"] = i + 1
                    metrics["function_issues"] = len(function_issues)
                    metrics["type_issues"] = len(critical_issues)
                    metrics["breaking_issues"] = len(breaking_issues)
                    metrics["structure_issues"] = len(structure_issues)
                    cur["metrics"] = metrics
                    self.progress["current"] = cur
                    self.save_progress()
                except Exception:
                    pass
                return

            # 需要优化：提供详细上下文背景，并明确审查意见仅针对 Rust crate，不修改 C 源码
            crate_tree = dir_tree(self.crate_dir)
            issues_text = "\n".join(
                [
                    "功能一致性问题：" if function_issues else "",
                    *[f"  - {issue}" for issue in function_issues],
                    "严重问题（可能导致功能错误）：" if critical_issues else "",
                    *[f"  - {issue}" for issue in critical_issues],
                    "破坏性变更问题（对现有代码的影响）：" if breaking_issues else "",
                    *[f"  - {issue}" for issue in breaking_issues],
                    "文件结构问题：" if structure_issues else "",
                    *[f"  - {issue}" for issue in structure_issues],
                ]
            )
            # 获取 C 源文件位置信息
            c_file_location = ""
            if hasattr(rec, "file") and rec.file:
                if (
                    hasattr(rec, "start_line")
                    and hasattr(rec, "end_line")
                    and rec.start_line
                    and rec.end_line
                ):
                    c_file_location = f"{rec.file}:{rec.start_line}-{rec.end_line}"
                else:
                    c_file_location = str(rec.file)

            fix_prompt = "\n".join(
                [
                    "请根据以下审查结论对目标函数进行最小优化（保留结构与意图，不进行大范围重构）：",
                    "<REVIEW>",
                    issues_text
                    if issues_text.strip()
                    else "审查发现问题，但未提供具体问题描述",
                    "</REVIEW>",
                    "",
                    "上下文背景信息：",
                    f"- **Crate 根目录（重要）**: {self.crate_dir.resolve()}",
                    "  * 所有 Rust 源码文件都位于此目录下",
                    "  * 使用 `read_code` 工具读取 Rust 文件时，文件路径应相对于此目录（如 `src/xxx.rs`）或使用绝对路径",
                    "  * 使用 `edit_file_*` 工具编辑文件时，文件路径也应相对于此目录或使用绝对路径",
                    "  * 当前工作目录应切换到此目录，或使用绝对路径访问文件",
                    f"- 目标模块文件: {module}",
                    f"- 建议/当前 Rust 签名: {rust_sig}",
                    *(
                        [f"- C 源文件位置：{c_file_location}"]
                        if c_file_location
                        else []
                    ),
                    "crate 目录结构（部分）：",
                    crate_tree,
                    "",
                    "约束与范围：",
                    "- 本次审查意见仅针对 Rust crate 的代码与配置；不要修改任何 C/C++ 源文件（*.c、*.h 等）。",
                    "- 仅允许在 crate_dir 下进行最小必要修改（Cargo.toml、src/**/*.rs）；不要改动其他目录。",
                    "- 保持最小改动，避免与问题无关的重构或格式化。",
                    "- 优先修复严重问题（可能导致功能错误），然后修复功能一致性问题；",
                    "- ⚠️ **重要：修复范围要求** - 不仅要修复当前审查发现的问题，如果修复过程中导致其他测试用例失败，也必须一并修复：",
                    "  * 修复后必须运行 `cargo test -- --nocapture` 验证所有测试用例都能通过",
                    "  * 如果发现修复后某些原本通过的测试用例现在失败了，说明修复引入了回归问题，必须一并修复",
                    "  * 必须确保修复后所有测试用例（包括目标函数的测试和其他函数的测试）都能通过",
                    "  * 如果修复影响了其他函数或模块，需要检查并修复所有受影响的部分",
                    "- 如审查问题涉及缺失/未实现的被调函数或依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时在合理模块新增函数或引入精确 use；",
                    "- 禁止使用 todo!/unimplemented! 作为占位；",
                    "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号（禁止通配）；",
                    "- **使用工具时的路径说明**：",
                    f"  * `read_code` 工具：读取 Rust 文件时，使用相对于 crate 根目录（{self.crate_dir.resolve()}）的路径（如 `src/xxx.rs`）或绝对路径",
                    "  * `edit_file_*` 工具：编辑文件时，文件路径也应相对于 crate 根目录或使用绝对路径",
                    "- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
                    *(
                        [
                            f"- **禁用库约束**：禁止在优化中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果优化需要使用这些库的功能，请使用标准库或其他允许的库替代。"
                        ]
                        if self.disabled_libraries
                        else []
                    ),
                    *(
                        [
                            f"- **根符号要求**：此函数是根符号（{rec.qname or rec.name}），必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。"
                        ]
                        if self.is_root_symbol(rec)
                        else []
                    ),
                    "",
                    "【重要：依赖检查与实现要求】",
                    "在优化函数之前，请务必检查以下内容：",
                    "1. 检查当前函数是否已完整实现：",
                    f"   - 在目标模块 {module} 中查找函数 {rec.qname or rec.name} 的实现",
                    "   - 如果已存在实现，检查其是否完整且正确",
                    "2. 检查所有依赖函数是否已实现：",
                    "   - 遍历当前函数调用的所有被调函数（包括直接调用和间接调用）",
                    "   - 对于每个被调函数，检查其在 Rust crate 中是否已有完整实现",
                    "   - 可以使用 read_code 工具读取相关模块文件进行检查",
                    "3. 对于未实现的依赖函数：",
                    "   - 使用 read_symbols 工具获取其 C 源码和符号信息",
                    "   - 使用 read_code 工具读取其 C 源码实现",
                    "   - 在本次优化中一并补齐这些依赖函数的 Rust 实现",
                    "   - 根据依赖关系选择合适的模块位置（可在同一模块或合理的新模块中）",
                    "   - 确保所有依赖函数都有完整实现，禁止使用 todo!/unimplemented! 占位",
                    "4. 实现顺序：",
                    "   - 优先实现最底层的依赖函数（不依赖其他未实现函数的函数）",
                    "   - 然后实现依赖这些底层函数的函数",
                    "   - 最后优化当前目标函数",
                    "5. 验证：",
                    "   - 确保当前函数及其所有依赖函数都已完整实现",
                    "   - 确保没有遗留的 todo!/unimplemented! 占位",
                    "   - 确保所有函数调用都能正确解析",
                    "",
                ]
            )

            # 获取 C 代码用于修复 Agent
            c_code = self.read_source_span(rec)

            # 先创建修复 Agent（后续会复用）
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 记录运行前的 commit
            before_commit = self.get_crate_commit_hash()
            # 使用修复 Agent，每次重新创建，并传入 C 代码
            ca = self.get_fix_agent(c_code)

            # 添加 git 变更信息作为上下文
            if self.get_git_diff:
                try:
                    base_commit = self.current_function_start_commit_getter()
                    git_diff = self.get_git_diff(base_commit)
                    if git_diff and git_diff.strip():
                        # 限制 git diff 长度，避免上下文过大
                        # 使用较小的比例（30%）因为修复提示词本身已经很长
                        # 使用已创建的修复 Agent 获取更准确的剩余 token
                        git_diff = truncate_git_diff_with_context_limit(
                            git_diff,
                            agent=ca,
                            llm_group=self.llm_group,
                            token_ratio=0.3,
                            base_commit=base_commit,
                            crate_dir=self.crate_dir,
                        )

                        fix_prompt += "\n\n"
                        fix_prompt += "【Git 变更信息】\n"
                        fix_prompt += "以下是从函数开始处理到当前的 git 变更，可以帮助你了解已经做了哪些修改：\n"
                        fix_prompt += "<GIT_DIFF>\n"
                        fix_prompt += git_diff
                        fix_prompt += "\n</GIT_DIFF>\n"
                        fix_prompt += "\n"
                        fix_prompt += "提示：\n"
                        fix_prompt += "- 请仔细查看上述 git diff，了解当前代码的状态和已做的修改\n"
                        fix_prompt += (
                            "- 如果看到之前的修改引入了问题，可以在修复时一并处理\n"
                        )
                        fix_prompt += (
                            "- 如果看到某些文件被意外修改，需要确认这些修改是否必要\n"
                        )
                        fix_prompt += "- 结合审查问题，有针对性地修复代码\n"
                except Exception:
                    # 如果获取 git diff 失败，不影响主流程
                    pass

            fix_prompt += "\n请仅以补丁形式输出修改，避免冗余解释。"
            limit_info = f"/{max_iterations}" if max_iterations > 0 else "/∞"
            fix_prompt_with_notes = self.append_additional_notes(fix_prompt)
            ca.run(
                self.compose_prompt_with_context(fix_prompt_with_notes, True),
                prefix=f"⚠️ [c2rust-transpiler][review-fix iter={i + 1}{limit_info}]",
                suffix="",
            )

            # 检测并处理测试代码删除
            if self.check_and_handle_test_deletion(before_commit, ca):
                # 如果回退了，需要重新运行 agent
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][review-fix] 检测到测试代码删除问题，已回退，重新运行 agent (iter={i + 1})",
                )
                before_commit = self.get_crate_commit_hash()
                # 重新创建修复 Agent
                ca = self.get_fix_agent(c_code)
                ca.run(
                    self.compose_prompt_with_context(fix_prompt_with_notes, True),
                    prefix=f"⚠️ [c2rust-transpiler][review-fix iter={i + 1}{limit_info}][retry]",
                    suffix="",
                )
                # 再次检测
                if self.check_and_handle_test_deletion(before_commit, ca):
                    PrettyOutput.auto_print(
                        f"❌ [c2rust-transpiler][review-fix] 再次检测到测试代码删除问题，已回退 (iter={i + 1})",
                    )

            # 优化后进行一次构建验证；若未通过则进入构建修复循环，直到通过为止
            self.cargo_build_loop()

            # 检查构建修复过程中是否进行了修复
            build_has_fixes = (
                self.get_build_loop_has_fixes()
                if hasattr(self, "get_build_loop_has_fixes")
                else False
            )
            if build_has_fixes:
                PrettyOutput.auto_print(
                    "[c2rust-transpiler][review-fix] 构建修复过程中进行了修复，将在下一轮审查中重新检查",
                )

            # 记录本次审查结果
            try:
                cur = self.progress.get("current") or {}
                cur["review"] = {
                    "ok": False,
                    "function_issues": list(function_issues),
                    "critical_issues": list(critical_issues),
                    "breaking_issues": list(breaking_issues),
                    "structure_issues": list(structure_issues),
                    "iterations": i + 1,
                }
                metrics = cur.get("metrics") or {}
                metrics["function_issues"] = len(function_issues)
                metrics["type_issues"] = len(critical_issues)
                metrics["breaking_issues"] = len(breaking_issues)
                metrics["structure_issues"] = len(structure_issues)
                cur["metrics"] = metrics
                self.progress["current"] = cur
                self.save_progress()
            except Exception:
                pass

            # 清理当前迭代的 agent 事件订阅和记录（为下一次迭代做准备）
            # 取消事件订阅，避免事件总线持有对 agent 的引用，导致 agent 无法被垃圾回收
            try:
                review_agent.event_bus.unsubscribe(
                    BEFORE_TOOL_CALL, self.on_before_tool_call
                )
                review_agent.event_bus.unsubscribe(
                    AFTER_TOOL_CALL, self.on_after_tool_call
                )
                # 清理 agent_before_commits 中的记录
                if agent_key in self.agent_before_commits:
                    del self.agent_before_commits[agent_key]
            except Exception:
                pass

            i += 1

            # 达到迭代上限（仅当设置了上限时）
            # 注意：最后一次迭代的 agent 已经在循环内部清理过了，这里不需要额外清理
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][review] 已达到最大迭代次数上限({max_iterations})，停止审查优化。",
            )
            try:
                cur = self.progress.get("current") or {}
                cur["review_max_iterations_reached"] = True
                cur["review_iterations"] = i
                self.progress["current"] = cur
                self.save_progress()
            except Exception:
                pass
