from __future__ import annotations

import json
from pathlib import Path
from typing import List
from typing import cast

import typer

from jarvis.jarvis_c2rust.models import FnRecord


def build_generate_impl_prompt(
    self,
    rec: FnRecord,
    c_code: str,
    module: str,
    rust_sig: str,
    unresolved: List[str],
) -> str:
    """
    从 Transpiler._build_generate_impl_prompt 提取出的实现，保持签名与逻辑完全一致。
    """
    symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
    is_root = self._is_root_symbol(rec)
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
    compile_flags = self._extract_compile_flags(rec.file)
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
    return cast(str, self._append_additional_notes(prompt))


def codeagent_generate_impl(
    self,
    rec: FnRecord,
    c_code: str,
    module: str,
    rust_sig: str,
    unresolved: List[str],
) -> None:
    """
    从 Transpiler._codeagent_generate_impl 提取出的实现，保持逻辑一致。
    """
    # 构建提示词
    prompt = build_generate_impl_prompt(self, rec, c_code, module, rust_sig, unresolved)

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
    before_commit = self._get_crate_commit_hash()
    agent = self._get_code_agent()
    agent.run(
        self._compose_prompt_with_context(prompt),
        prefix="[c2rust-transpiler][gen]",
        suffix="",
    )

    # 检测并处理测试代码删除
    if self._check_and_handle_test_deletion(before_commit, agent):
        # 如果回退了，需要重新运行 agent
        typer.secho(
            "[c2rust-transpiler][gen] 检测到测试代码删除问题，已回退，重新运行 agent",
            fg=typer.colors.YELLOW,
        )
        before_commit = self._get_crate_commit_hash()
        agent.run(
            self._compose_prompt_with_context(prompt),
            prefix="[c2rust-transpiler][gen][retry]",
            suffix="",
        )
        # 再次检测
        if self._check_and_handle_test_deletion(before_commit, agent):
            typer.secho(
                "[c2rust-transpiler][gen] 再次检测到测试代码删除问题，已回退",
                fg=typer.colors.RED,
            )

    # 如果是根符号，确保其模块在 lib.rs 中被暴露
    if self._is_root_symbol(rec):
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
                        self._ensure_top_level_pub_mod(top_mod)
                        typer.secho(
                            f"[c2rust-transpiler][gen] 根符号 {rec.qname or rec.name} 的模块 {top_mod} 已在 lib.rs 中暴露",
                            fg=typer.colors.GREEN,
                        )
        except Exception:
            pass
