# -*- coding: utf-8 -*-
"""
代码生成模块
"""

import json
import re
from pathlib import Path
from typing import Any, Callable, List

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_c2rust.models import FnRecord


class GenerationManager:
    """代码生成管理器"""

    def __init__(
        self,
        project_root: Path,
        crate_dir: Path,
        data_dir: Path,
        disabled_libraries: List[str],
        extract_compile_flags_func: Callable[[str], List[str]],
        append_additional_notes_func: Callable[[str, str], str],
        is_root_symbol_func: Callable[[str], bool],
        get_generation_agent_func: Callable[[], Any],
        compose_prompt_with_context_func: Callable[[str, Any], str],
        check_and_handle_test_deletion_func: Callable[[str, str], bool],
        get_crate_commit_hash_func: Callable[[], str],
        ensure_top_level_pub_mod_func: Callable[[str], None],
    ) -> None:
        self.project_root = project_root
        self.crate_dir = crate_dir
        self.data_dir = data_dir
        self.disabled_libraries = disabled_libraries
        self.extract_compile_flags = extract_compile_flags_func
        self.append_additional_notes = append_additional_notes_func
        self.is_root_symbol = is_root_symbol_func
        self.get_generation_agent = get_generation_agent_func
        self.compose_prompt_with_context = compose_prompt_with_context_func
        self.check_and_handle_test_deletion = check_and_handle_test_deletion_func
        self.get_crate_commit_hash = get_crate_commit_hash_func
        self.ensure_top_level_pub_mod = ensure_top_level_pub_mod_func

    def build_generate_impl_prompt(
        self,
        rec: FnRecord,
        c_code: str,
        module: str,
        rust_sig: str,
        unresolved: List[str],
    ) -> str:
        """
        构建代码生成提示词。

        返回完整的提示词字符串。
        """
        symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
        is_root = self.is_root_symbol(rec.qname or rec.name)
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

        requirement_lines = [
            f"目标：在 {module} 中，使用 TDD 方法为 C 函数 {rec.qname or rec.name} 生成 Rust 实现。",
            f"函数签名：{rust_sig}",
            f"crate 目录：{self.crate_dir.resolve()}",
            f"C 工程目录：{self.project_root.resolve()}",
            *([f"C 源文件位置：{c_file_location}"] if c_file_location else []),
            *(
                ["根符号要求：必须使用 `pub` 关键字，模块必须在 src/lib.rs 中导出"]
                if is_root
                else []
            ),
            "",
            "【TDD 流程】",
            "1. Red：先写测试（#[cfg(test)] mod tests），基于 C 函数行为设计测试用例",
            "2. Green：编写实现使测试通过，确保与 C 语义等价",
            "3. Refactor：优化代码，保持测试通过",
            "   - 如果发现现有测试用例有错误，优先修复测试用例而不是删除",
            "",
            "【核心要求】",
            "- 先写测试再写实现，测试必须可编译通过",
            "- ⚠️ 重要：如果发现现有测试用例有错误（如测试逻辑错误、断言不正确、测试用例设计不当等），应该修复测试用例而不是删除它们。只有在测试用例完全重复、过时或确实不需要时才能删除。",
            "- ⚠️ 重要：不要将正式代码写到测试区域。所有正式的函数实现、类型定义、常量等都应该写在 `#[cfg(test)] mod tests { ... }` 块之外。测试代码（测试函数、测试辅助函数等）才应该写在 `#[cfg(test)] mod tests { ... }` 块内部。",
            "- ⚠️ 重要：测试用例必须尽可能完备，因为后续 review 阶段会检测测试用例完备性，避免返工。测试用例应该包括：",
            "  * 主要功能路径的测试：覆盖函数的核心功能和预期行为",
            "  * 边界情况测试：空输入（空字符串、空数组、空指针等）、极值输入（最大值、最小值、零值等）、边界值（数组边界、字符串长度边界等）、特殊值（负数、NaN、无穷大等，如果适用）",
            "  * 错误情况测试：如果 C 实现有错误处理（如返回错误码、设置 errno 等），测试用例应该覆盖这些错误情况。如果 Rust 实现使用 Result<T, E> 或 Option<T> 处理错误，测试用例应该验证错误情况",
            "  * 与 C 实现行为一致性：测试用例的预期结果应该与 C 实现的行为一致",
            "  * 测试用例质量：测试名称清晰、断言适当、测试逻辑正确，能够真正验证函数的功能",
            "  * 注意：如果函数是资源释放类函数（如 fclose、free 等），在 Rust 中通过 RAII 自动管理，测试用例可以非常简单（如仅验证函数可以调用而不崩溃），这是可以接受的",
            "- 禁止使用 todo!/unimplemented!，必须实现完整功能",
            "- 使用 Rust 原生类型（i32/u32、&str/String、&[T]/&mut [T]、Result<T,E>），避免 C 风格类型",
            '- 禁止使用 extern "C"，使用标准 Rust 调用约定',
            "- 保持最小变更，避免无关重构",
            "- 注释使用中文，禁止 use ...::* 通配导入",
            "- 资源释放类函数（fclose/free 等）可通过 RAII 自动管理，提供空实现并在文档中说明",
            *(
                [f"- 禁用库：{', '.join(self.disabled_libraries)}"]
                if self.disabled_libraries
                else []
            ),
            "",
            "【依赖处理】",
            "- 检查依赖函数是否已实现，未实现的需一并补齐（遵循 TDD：先测试后实现）",
            "- 使用 read_symbols/read_code 获取 C 源码",
            "- 优先处理底层依赖，确保所有测试通过",
            "",
            "【工具】",
            f'- read_symbols: {{"symbols_file": "{symbols_path}", "symbols": [...]}}',
            "- read_code: 读取 C 源码或 Rust 模块",
            "",
            *([f"未转换符号：{', '.join(unresolved)}"] if unresolved else []),
            "",
            "C 源码：",
            "<C_SOURCE>",
            c_code,
            "</C_SOURCE>",
            "",
            "签名参考：",
            json.dumps(
                {
                    "signature": getattr(rec, "signature", ""),
                    "params": getattr(rec, "params", None),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "仅输出补丁，不要解释。",
        ]
        # 若存在库替代上下文，则附加到实现提示中，便于生成器参考（多库组合、参考API、备注等）
        librep_ctx = None
        try:
            librep_ctx = getattr(rec, "lib_replacement", None)
        except Exception:
            librep_ctx = None
        if isinstance(librep_ctx, dict) and librep_ctx:
            requirement_lines.extend(
                [
                    "",
                    "库替代上下文（若存在）：",
                    json.dumps(librep_ctx, ensure_ascii=False, indent=2),
                    "",
                ]
            )
        # 添加编译参数（如果存在）
        compile_flags = None
        if hasattr(rec, "file") and rec.file:
            compile_flags = self.extract_compile_flags(rec.file)
        if compile_flags:
            requirement_lines.extend(
                [
                    "",
                    "C文件编译参数（来自 compile_commands.json）：",
                    "\n".join(compile_flags),
                    "",
                ]
            )
        prompt = "\n".join(requirement_lines)
        return self.append_additional_notes(prompt, "")

    def extract_rust_fn_name_from_sig(self, rust_sig: str) -> str:
        """
        从 rust 签名中提取函数名，支持生命周期参数和泛型参数。
        例如: 'pub fn foo(a: i32) -> i32 { ... }' -> 'foo'
        例如: 'pub fn foo<'a>(bzf: &'a mut BzFile) -> Result<&'a [u8], BzError>' -> 'foo'
        """
        # 支持生命周期参数和泛型参数：fn name<'a, T>(...)
        m = re.search(
            r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]+>)?\s*\(", rust_sig or ""
        )
        return m.group(1) if m else ""

    def codeagent_generate_impl(
        self,
        rec: FnRecord,
        c_code: str,
        module: str,
        rust_sig: str,
        unresolved: List[str],
    ) -> None:
        """
        使用 CodeAgent 生成/更新目标模块中的函数实现。
        约束：最小变更，生成可编译的占位实现，尽可能保留后续细化空间。
        """
        # 构建提示词
        prompt = self.build_generate_impl_prompt(
            rec, c_code, module, rust_sig, unresolved
        )

        # 确保目标模块文件存在（提高补丁应用与实现落盘的确定性）
        try:
            mp = Path(module)
            if not mp.is_absolute():
                mp = (self.crate_dir / module).resolve()
            mp.parent.mkdir(parents=True, exist_ok=True)
            if not mp.exists():
                try:
                    mp.write_text(
                        "// Auto-created by c2rust transpiler\n", encoding="utf-8"
                    )
                    PrettyOutput.auto_print(
                        f"✅ [c2rust-transpiler][gen] auto-created module file: {mp}"
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        # 记录运行前的 commit
        before_commit = self.get_crate_commit_hash()
        # 使用生成 Agent（可以复用）
        agent = self.get_generation_agent()
        agent.run(
            self.compose_prompt_with_context(prompt, agent),
            prefix="[c2rust-transpiler][gen]",
            suffix="",
        )

        # 检测并处理测试代码删除
        if self.check_and_handle_test_deletion(before_commit, agent):
            # 如果回退了，需要重新运行 agent
            PrettyOutput.auto_print(
                "⚠️ [c2rust-transpiler][gen] 检测到测试代码删除问题，已回退，重新运行 agent"
            )
            before_commit = self.get_crate_commit_hash()
            # 重试时使用相同的 prompt（已包含 C 源文件位置信息）
            agent.run(
                self.compose_prompt_with_context(prompt, agent),
                prefix="[c2rust-transpiler][gen][retry]",
                suffix="",
            )
            # 再次检测
            if self.check_and_handle_test_deletion(before_commit, agent):
                PrettyOutput.auto_print(
                    "❌ [c2rust-transpiler][gen] 再次检测到测试代码删除问题，已回退"
                )

        # 如果是根符号，确保其模块在 lib.rs 中被暴露
        if self.is_root_symbol(rec.qname or rec.name):
            try:
                mp = Path(module)
                crate_root = self.crate_dir.resolve()
                rel = (
                    mp.resolve().relative_to(crate_root)
                    if mp.is_absolute()
                    else Path(module)
                )
                rel_s = str(rel).replace("\\", "/")
                if rel_s.startswith("./"):
                    rel_s = rel_s[2:]
                if rel_s.startswith("src/"):
                    parts = rel_s[len("src/") :].strip("/").split("/")
                    if parts and parts[0]:
                        top_mod = parts[0]
                        # 过滤掉 "mod" 关键字和 .rs 文件
                        if top_mod != "mod" and not top_mod.endswith(".rs"):
                            self.ensure_top_level_pub_mod(top_mod)
                            PrettyOutput.auto_print(
                                f"📋 [c2rust-transpiler][gen] 根符号 {rec.qname or rec.name} 的模块 {top_mod} 已在 lib.rs 中暴露"
                            )
            except Exception:
                pass
