# -*- coding: utf-8 -*-
"""
Jarvis C/C++ Test Setup CLI

功能目标：
- 创建一个Agent用于探测当前C/C++工程是否存在测试框架与测试用例
- 分析如何运行测试（优先自动检测已有脚本/构建系统：CTest, Make, Bazel, CMake+CTest, Ninja, Meson, etc.）
- 如不存在测试，自动在项目中创建一个基于 gtest 和 mockcpp 的最小测试框架骨架
- 最终生成可执行脚本 `.jarvis/c2rust/test_c.sh` 用于一键运行测试

使用方式：
- 作为模块：python -m jarvis.jarvis_c2rust.cli setup-tests -p <project_root>
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
import subprocess
import re
from typing import Optional, Dict, List

import typer

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_c2rust.agent_c_test import create_c_test_agent
from jarvis.jarvis_c2rust.agent_rust_link import create_rust_link_agent
from jarvis.jarvis_c2rust.symbol_scanner import scan_c_symbols_to_jsonl


app = typer.Typer(add_completion=False, no_args_is_help=True, help="C/C++ 测试框架探测与搭建工具")



def _ensure_executable(file_path: Path) -> None:
    try:
        mode = file_path.stat().st_mode
        file_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def _write_text(file_path: Path, content: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def scaffold_rust_staticlib(project_root: Path, crate_name: str = "c2rust_bridge") -> Dict[str, Path]:
    """在 .jarvis/c2rust 下创建一个最小 Rust staticlib 工程与构建脚本。

    返回关键路径字典：base_dir、crate_dir、include_dir、cargo_toml、lib_rs、header、build_script。
    """
    base_dir = project_root / ".jarvis" / "c2rust"
    crate_dir = base_dir / crate_name
    src_dir = crate_dir / "src"
    include_dir = base_dir / "include"
    build_script = base_dir / "build_rust.sh"
    cargo_toml = crate_dir / "Cargo.toml"
    lib_rs = src_dir / "lib.rs"
    header_h = include_dir / f"{crate_name}.h"

    cargo_content = (
        f"""[package]
name = "{crate_name}"
version = "0.1.0"
edition = "2021"

[lib]
name = "{crate_name}"
crate-type = ["staticlib"]

[profile.release]
lto = true
codegen-units = 1
"""
    )

    lib_rs_content = (
        """#[no_mangle]
pub extern "C" fn rust_add(a: i32, b: i32) -> i32 {
    a + b
}
"""
    )

    header_content = (
        f"""#ifndef {crate_name.upper()}_H
#define {crate_name.upper()}_H
#ifdef __cplusplus
extern "C" {{
#endif
#include <stdint.h>

int32_t rust_add(int32_t a, int32_t b);

#ifdef __cplusplus
}}
#endif
#endif
"""
    )

    build_sh = (
        f"""#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/{crate_name}"
if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found. Please install Rust toolchain (rustup) first." >&2
  exit 127
fi
cargo build --release
ARTIFACT="target/release/lib{crate_name}.a"
if [[ -f "$ARTIFACT" ]]; then
  echo "$(pwd)/$ARTIFACT"
else
  echo "Build succeeded but staticlib not found at $ARTIFACT" >&2
  exit 1
fi
"""
    )

    _write_text(cargo_toml, cargo_content)
    _write_text(lib_rs, lib_rs_content)
    _write_text(header_h, header_content)
    _write_text(build_script, build_sh)
    _ensure_executable(build_script)

    return {
        "base_dir": base_dir,
        "crate_dir": crate_dir,
        "include_dir": include_dir,
        "cargo_toml": cargo_toml,
        "lib_rs": lib_rs,
        "header": header_h,
        "build_script": build_script,
    }


def create_rust_link_agent(model_group: Optional[str] = None, non_interactive: Optional[bool] = True) -> Agent:
    """创建一个 Agent，将 .jarvis/c2rust 下的 Rust staticlib 链接进 C/C++ 测试进程。"""
    system_prompt = (
        """
<role>
你是一个资深C/C++与Rust混合构建工程师。
目标：在不破坏现有工程的前提下，把 .jarvis/c2rust 下的 Rust staticlib 产物链接到C/C++测试进程中。
</role>

<requirements>
- 识别项目使用的构建系统（CMake/Make/Ninja/Meson/Bazel等），最小化修改方案。
- 将 Rust 静态库产物加入测试目标的链接步骤；如为 CMake，请使用 target_link_libraries 并配置 -L 与 -l；如为 Makefile，追加 LDFLAGS/LDLIBS。
- 如果存在 .jarvis/c2rust/test_c.sh，请在其中加入调用 build_rust.sh 的步骤（测试前构建Rust库）。
- 不修改业务源码；如需声明函数原型，请包含 .jarvis/c2rust/include/<crate>.h。
- 允许在脚本中加入平台依赖说明（如需 -ldl -lpthread -lm）。
- 输出你做出的文件编辑（路径与关键改动），以及最终的测试与构建命令。
</requirements>

<inputs>
- 你将收到：工程根目录、Rust crate 名称、静态库构建脚本路径、头文件路径、预期静态库文件名。
</inputs>

<steps>
1) 探测构建系统与测试目标；
2) 在测试目标的链接阶段加入 Rust 静态库（-L <dir> -l<crate> 或绝对路径 .a）；
3) 确保编译步骤能找到头文件：在需要处包含 .jarvis/c2rust/include；
4) 更新/生成 .jarvis/c2rust/test_c.sh：先构建Rust库，再运行测试；
5) 输出最终命令与用法。
</steps>
""".strip()
    )
    agent = Agent(
        system_prompt=system_prompt,
        name="C2Rust-Link-Agent",
        auto_complete=True,
        model_group=model_group,
        need_summary=False,
        use_methodology=False,
        use_analysis=False,
        non_interactive=bool(non_interactive),
        agent_type="code",
    )
    try:
        agent.set_use_tools(
            [
                "execute_script",
                "read_code",
                "ask_user",
                "save_memory",
                "retrieve_memory",
                "clear_memory",
            ]
        )
    except Exception:
        pass
    return agent


def setup_rust_staticlib_integration(
    path: str = ".",
    crate_name: str = "c2rust_bridge",
    model_group: Optional[str] = None,
    non_interactive: bool = True,
) -> None:
    """创建 Rust staticlib 并调用 Agent 改造构建以链接到测试进程。"""
    try:
        init_env("Jarvis Rust 静态库集成器", config_file=None)
    except Exception:
        pass

    project_root = Path(os.path.expanduser(os.path.expandvars(path))).resolve()
    if not project_root.exists() or not project_root.is_dir():
        PrettyOutput.print(f"无效的工程目录: {project_root}", OutputType.ERROR)
        raise typer.Exit(code=2)

    os.chdir(str(project_root))

    paths = scaffold_rust_staticlib(project_root, crate_name=crate_name)
    build_script = paths["build_script"]
    header = paths["header"]
    crate_dir = paths["crate_dir"]
    staticlib_name = f"lib{crate_name}.a"
    staticlib_dir = crate_dir / "target" / "release"

    agent = create_rust_link_agent(model_group=model_group, non_interactive=non_interactive)

    user_task = (
        "请将 Rust 静态库产物链接进当前仓库的C/C++测试进程。\n"
        f"- 工程根目录：{project_root}\n"
        f"- Rust crate：{crate_name}\n"
        f"- 构建脚本：{build_script}\n"
        f"- 头文件：{header}\n"
        f"- 预期静态库文件：{staticlib_dir / staticlib_name}\n"
        "- 要求：保持改动最小，在测试流程中先执行构建脚本，再运行测试；"
        "若存在 .jarvis/c2rust/test_c.sh 请在其中加入Rust构建；否则生成之。\n"
        "最终输出：修改过的文件列表与最终测试命令。"
    )

    try:
        agent.run(user_task)
    except Exception as e:
        PrettyOutput.print(
            f"Rust 集成 Agent 执行失败，请手动处理。错误: {e}", OutputType.ERROR
        )

    PrettyOutput.print(
        f"Rust 静态库已就绪：{crate_dir}\n构建：bash {build_script}\n头文件：{header}",
        OutputType.SUCCESS,
    )


@app.command("setup-tests", help="探测/搭建C/C++测试并生成 .jarvis/c2rust/test_c.sh")
def setup_tests(
    path: str = typer.Option(".", "--path", "-p", help="C/C++ 工程根目录"),
    model_group: Optional[str] = typer.Option(None, "--llm-group", "-g", help="使用的模型组"),
    non_interactive: bool = typer.Option(True, "-n", "--non-interactive", help="非交互模式运行"),
) -> None:
    try:
        init_env("Jarvis C/C++ 测试探测器", config_file=None)
    except Exception:
        pass

    project_root = Path(os.path.expanduser(os.path.expandvars(path))).resolve()
    if not project_root.exists() or not project_root.is_dir():
        PrettyOutput.print(f"无效的工程目录: {project_root}", OutputType.ERROR)
        raise typer.Exit(code=2)

    os.chdir(str(project_root))

    agent = create_c_test_agent(model_group=model_group, non_interactive=non_interactive)

    user_task = (
        "请在当前仓库内完成以下目标：\n"
        "- 若存在测试：定位如何运行并生成 .jarvis/c2rust/test_c.sh；\n"
        "- 若不存在测试：仅搭建最小 gtest 测试框架（禁止生成任何测试用例），并生成 .jarvis/c2rust/test_c.sh；\n"
        "- 脚本须幂等、非交互，可直接运行，必要时自动创建 build 目录并构建；\n"
        "- 脚本内包含依赖安装或提示（尽量不破坏项目）；\n"
        "- 最后输出脚本路径与示例用法。"
    )

    try:
        agent.run(user_task)
    except Exception as e:
        PrettyOutput.print(
            f"Agent 执行失败，请手动处理。错误: {e}", OutputType.ERROR
        )

    script_path = project_root / ".jarvis" / "c2rust" / "test_c.sh"
    if script_path.is_file():
        _ensure_executable(script_path)
        rel = script_path.relative_to(project_root)
        PrettyOutput.print(
            f"测试脚本已就绪：./{rel}\n运行：bash ./{rel}",
            OutputType.SUCCESS,
        )
        verify = True
        if verify:
            try:
                PrettyOutput.print("正在执行测试脚本以进行验证...", OutputType.INFO)
                result = subprocess.run(
                    ["bash", str(script_path)],
                    cwd=str(project_root),
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                out = (result.stdout or "") + "\n" + (result.stderr or "")

                # 粗略识别是否执行了测试
                total_tests = None
                try:
                    m = re.search(r"Total Tests:\s*(\\d+)", out)
                    if m:
                        total_tests = int(m.group(1))
                    if total_tests is None:
                        m2 = re.search(r"\[=+\-\s\]*\]\s*Running\s*(\\d+)\s*tests?", out)
                        if m2:
                            total_tests = int(m2.group(1))
                    if total_tests is None:
                        ok_m = re.search(r"Ok:\s*(\\d+)", out)
                        fail_m = re.search(r"Fail:\s*(\\d+)", out)
                        if ok_m or fail_m:
                            ok_v = int(ok_m.group(1)) if ok_m else 0
                            fail_v = int(fail_m.group(1)) if fail_m else 0
                            total_tests = ok_v + fail_v
                except Exception:
                    total_tests = None

                if result.returncode == 0:
                    if isinstance(total_tests, int):
                        if total_tests > 0:
                            PrettyOutput.print(
                                f"验证通过：执行了 {total_tests} 个测试。", OutputType.SUCCESS
                            )
                        else:
                            PrettyOutput.print(
                                "脚本执行成功，但未检测到任何测试用例被执行。", OutputType.WARNING
                            )
                    else:
                        PrettyOutput.print(
                            "脚本执行成功，但无法解析测试数量。", OutputType.INFO
                        )
                else:
                    PrettyOutput.print(
                        f"脚本执行失败，退出码 {result.returncode}。输出：\n" + out,
                        OutputType.ERROR,
                    )
            except Exception as e:
                PrettyOutput.print(f"运行验证时发生错误: {e}", OutputType.ERROR)
        return

    # 未生成脚本时给出手动指导
    manual = (
        "未检测到由Agent生成的 .jarvis/c2rust/test_c.sh。\n"
        "请手动执行以下任一方案：\n"
        "1) 如果项目使用CMake：\n"
        "   cmake -S . -B build && cmake --build build && (cd build && ctest --output-on-failure)\n"
        "2) 如果存在Makefile的test目标：\n"
        "   make test\n"
        "3) Meson：meson setup builddir && meson test -C builddir\n"
        "4) Ninja：ninja test 或 ninja -C build test\n"
        "5) Bazel：bazel test //...\n"
        "如需最小gtest样例，可在项目中创建 tests/ 与简单的CMakeLists.txt，并使用ctest运行。"
    )
    PrettyOutput.print(manual, OutputType.WARNING)


@app.command(
    "setup-rust-link",
    help="在 .jarvis/c2rust 下创建 Rust 静态库，并通过 Agent 将其链接到C测试流程",
)
def setup_rust_link(
    path: str = typer.Option(".", "--path", "-p", help="C/C++ 工程根目录"),
    crate_name: str = typer.Option(
        "c2rust_bridge", "--crate", "-c", help="Rust crate 名称"
    ),
    model_group: Optional[str] = typer.Option(
        None, "--llm-group", "-g", help="使用的模型组"
    ),
    non_interactive: bool = typer.Option(
        True, "-n", "--non-interactive", help="非交互模式运行"
    ),
) -> None:
    setup_rust_staticlib_integration(
        path=path,
        crate_name=crate_name,
        model_group=model_group,
        non_interactive=non_interactive,
    )


@app.command(
    "setup-all",
    help="依次执行测试探测/搭建与Rust静态库链接，将两个流程串联为一个",
)
def setup_all(
    path: str = typer.Option(".", "--path", "-p", help="C/C++ 工程根目录"),
    crate_name: str = typer.Option(
        "c2rust_bridge", "--crate", "-c", help="Rust crate 名称"
    ),
    model_group: Optional[str] = typer.Option(
        None, "--llm-group", "-g", help="使用的模型组"
    ),
    non_interactive: bool = typer.Option(
        True, "-n", "--non-interactive", help="非交互模式运行"
    ),
) -> None:
    # 先探测/搭建测试并生成 .jarvis/c2rust/test_c.sh
    setup_tests(path=path, model_group=model_group, non_interactive=non_interactive)
    # 再创建并链接 Rust 静态库到测试流程
    setup_rust_staticlib_integration(
        path=path,
        crate_name=crate_name,
        model_group=model_group,
        non_interactive=non_interactive,
    )
    # 最后进行 C 符号扫描，生成 symbols.jsonl
    try:
        project_root = Path(os.path.expanduser(os.path.expandvars(path))).resolve()
        out_path = project_root / ".jarvis" / "c2rust" / "symbols.jsonl"
        count = scan_c_symbols_to_jsonl(
            project_root=project_root,
            output_file=out_path,
            extra_excludes=[],
        )
        PrettyOutput.print(
            f"C 符号已扫描：{count} 条，输出：{out_path}", OutputType.SUCCESS
        )
    except Exception as e:
        PrettyOutput.print(f"符号扫描失败: {e}", OutputType.WARNING)


@app.command(
    "scan-c-symbols",
    help="扫描C语言符号并输出到 .jarvis/c2rust/symbols.jsonl",
)
def scan_c_symbols(
    path: str = typer.Option(".", "--path", "-p", help="C/C++ 工程根目录"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="输出文件路径（默认 .jarvis/c2rust/symbols.jsonl）"
    ),
    exclude: List[str] = typer.Option(
        None, "--exclude", "-x", help="额外排除的目录/模式，可多次传入"
    ),
) -> None:
    project_root = Path(os.path.expanduser(os.path.expandvars(path))).resolve()
    if not project_root.exists() or not project_root.is_dir():
        PrettyOutput.print(f"无效的工程目录: {project_root}", OutputType.ERROR)
        raise typer.Exit(code=2)

    out_path = (
        Path(output).resolve()
        if output
        else (project_root / ".jarvis" / "c2rust" / "symbols.jsonl")
    )

    try:
        count = scan_c_symbols_to_jsonl(
            project_root=project_root,
            output_file=out_path,
            extra_excludes=exclude or [],
        )
        PrettyOutput.print(
            f"写入完成: {out_path}，共 {count} 条符号记录。", OutputType.SUCCESS
        )
    except Exception as e:
        PrettyOutput.print(f"扫描失败: {e}", OutputType.ERROR)
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()


