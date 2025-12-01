# -*- coding: utf-8 -*-
"""
代码生成模块
"""

import json
import re
from pathlib import Path
from typing import List

import typer

from jarvis.jarvis_c2rust.models import FnRecord


class GenerationManager:
    """代码生成管理器"""

    def __init__(
        self,
        project_root: Path,
        crate_dir: Path,
        data_dir: Path,
        disabled_libraries: List[str],
        extract_compile_flags_func,
        append_additional_notes_func,
        is_root_symbol_func,
        get_code_agent_func,
        compose_prompt_with_context_func,
        check_and_handle_test_deletion_func,
        get_crate_commit_hash_func,
        ensure_top_level_pub_mod_func,
    ) -> None:
        self.project_root = project_root
        self.crate_dir = crate_dir
        self.data_dir = data_dir
        self.disabled_libraries = disabled_libraries
        self.extract_compile_flags = extract_compile_flags_func
        self.append_additional_notes = append_additional_notes_func
        self.is_root_symbol = is_root_symbol_func
        self.get_code_agent = get_code_agent_func
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
        is_root = self.is_root_symbol(rec)
        requirement_lines = [
            f"目标：在 {module} 中，使用 TDD 方法为 C 函数 {rec.qname or rec.name} 生成 Rust 实现。",
            f"函数签名：{rust_sig}",
            f"crate 目录：{self.crate_dir.resolve()}",
            f"C 工程目录：{self.project_root.resolve()}",
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
            "",
            "【核心要求】",
            "- 先写测试再写实现，测试必须可编译通过",
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
        compile_flags = self.extract_compile_flags(rec.file)
        if compile_flags:
            requirement_lines.extend(
                [
                    "",
                    "C文件编译参数（来自 compile_commands.json）：",
                    compile_flags,
                    "",
                ]
            )
        prompt = "\n".join(requirement_lines)
        return self.append_additional_notes(prompt)

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
                    typer.secho(
                        f"[c2rust-transpiler][gen] auto-created module file: {mp}",
                        fg=typer.colors.GREEN,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        # 记录运行前的 commit
        before_commit = self.get_crate_commit_hash()
        agent = self.get_code_agent()
        agent.run(
            self.compose_prompt_with_context(prompt),
            prefix="[c2rust-transpiler][gen]",
            suffix="",
        )

        # 检测并处理测试代码删除
        if self.check_and_handle_test_deletion(before_commit, agent):
            # 如果回退了，需要重新运行 agent
            typer.secho(
                "[c2rust-transpiler][gen] 检测到测试代码删除问题，已回退，重新运行 agent",
                fg=typer.colors.YELLOW,
            )
            before_commit = self.get_crate_commit_hash()
            agent.run(
                self.compose_prompt_with_context(prompt),
                prefix="[c2rust-transpiler][gen][retry]",
                suffix="",
            )
            # 再次检测
            if self.check_and_handle_test_deletion(before_commit, agent):
                typer.secho(
                    "[c2rust-transpiler][gen] 再次检测到测试代码删除问题，已回退",
                    fg=typer.colors.RED,
                )

        # 如果是根符号，确保其模块在 lib.rs 中被暴露
        if self.is_root_symbol(rec):
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
                            typer.secho(
                                f"[c2rust-transpiler][gen] 根符号 {rec.qname or rec.name} 的模块 {top_mod} 已在 lib.rs 中暴露",
                                fg=typer.colors.GREEN,
                            )
            except Exception:
                pass
