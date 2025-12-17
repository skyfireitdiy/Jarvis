# -*- coding: utf-8 -*-
# mypy: disable-error-code=unreachable
"""
构建和修复模块
"""

import re
import subprocess
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple


from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_c2rust.constants import CONSECUTIVE_FIX_FAILURE_THRESHOLD
from jarvis.jarvis_c2rust.constants import ERROR_SUMMARY_MAX_LENGTH
from jarvis.jarvis_c2rust.utils import truncate_git_diff_with_context_limit


class BuildManager:
    """构建和修复管理器"""

    def __init__(
        self,
        crate_dir: Path,
        project_root: Path,
        data_dir: Path,
        test_max_retries: int,
        disabled_libraries: List[str],
        root_symbols: List[str],
        progress: Dict[str, Any],
        save_progress_func: Callable[[], None],
        extract_compile_flags_func: Callable[[str], List[str]],
        get_current_function_context_func: Callable[[], Dict[str, Any]],
        get_fix_agent_func: Callable[[], Any],
        compose_prompt_with_context_func: Callable[[str], str],
        check_and_handle_test_deletion_func: Callable[[str, Any], bool],
        get_crate_commit_hash_func: Callable[[], str],
        reset_to_commit_func: Callable[[str], None],
        append_additional_notes_func: Callable[[str], str],
        consecutive_fix_failures_getter: Callable[[], int],
        consecutive_fix_failures_setter: Callable[[int], None],
        current_function_start_commit_getter: Callable[[], Optional[str]],
        get_git_diff_func: Optional[Callable[[Optional[str]], str]] = None,
    ) -> None:
        self.crate_dir = crate_dir
        self.project_root = project_root
        self.data_dir = data_dir
        self.test_max_retries = test_max_retries
        self.disabled_libraries = disabled_libraries
        self.root_symbols = root_symbols
        self.progress = progress
        self.save_progress = save_progress_func
        self.extract_compile_flags = extract_compile_flags_func
        self.get_current_function_context = get_current_function_context_func
        self.get_fix_agent = get_fix_agent_func
        self.compose_prompt_with_context = compose_prompt_with_context_func
        self.check_and_handle_test_deletion = check_and_handle_test_deletion_func
        self.get_crate_commit_hash = get_crate_commit_hash_func
        self.reset_to_commit = reset_to_commit_func
        self.append_additional_notes = append_additional_notes_func
        self._consecutive_fix_failures_getter = consecutive_fix_failures_getter
        self._consecutive_fix_failures_setter = consecutive_fix_failures_setter
        self._current_function_start_commit_getter = (
            current_function_start_commit_getter
        )
        self.get_git_diff = get_git_diff_func
        self._build_loop_has_fixes = False  # 标记构建循环中是否进行了修复

    def classify_rust_error(self, text: str) -> List[str]:
        """
        朴素错误分类，用于提示 CodeAgent 聚焦修复：
        - missing_import: unresolved import / not found in this scope / cannot find ...
        - type_mismatch: mismatched types / expected ... found ...
        - visibility: private module/field/function
        - borrow_checker: does not live long enough / borrowed data escapes / cannot borrow as mutable
        - dependency_missing: failed to select a version / could not find crate
        - module_not_found: file not found for module / unresolved module
        """
        tags: List[str] = []
        t = (text or "").lower()

        def has(s: str) -> bool:
            return s in t

        if (
            ("unresolved import" in t)
            or ("not found in this scope" in t)
            or ("cannot find" in t)
            or ("use of undeclared crate or module" in t)
        ):
            tags.append("missing_import")
        if ("mismatched types" in t) or ("expected" in t and "found" in t):
            tags.append("type_mismatch")
        if (
            ("private" in t and "module" in t)
            or ("private" in t and "field" in t)
            or ("private" in t and "function" in t)
        ):
            tags.append("visibility")
        if (
            ("does not live long enough" in t)
            or ("borrowed data escapes" in t)
            or ("cannot borrow" in t)
        ):
            tags.append("borrow_checker")
        if (
            ("failed to select a version" in t)
            or ("could not find crate" in t)
            or ("no matching package named" in t)
        ):
            tags.append("dependency_missing")
        if ("file not found for module" in t) or ("unresolved module" in t):
            tags.append("module_not_found")
        # 去重
        try:
            tags = list(dict.fromkeys(tags))
        except Exception:
            tags = list(set(tags))
        return tags

    def detect_crate_kind(self) -> str:
        """
        检测 crate 类型：lib、bin 或 mixed。
        判定规则（尽量保守，避免误判）：
        - 若存在 src/lib.rs 或 Cargo.toml 中包含 [lib]，视为包含 lib
        - 若存在 src/main.rs 或 Cargo.toml 中包含 [[bin]]（或 [bin] 兼容），视为包含 bin
        - 同时存在则返回 mixed
        - 两者都不明确时，默认返回 lib（与默认模版一致）
        """
        try:
            cargo_path = (self.crate_dir / "Cargo.toml").resolve()
            txt = ""
            if cargo_path.exists():
                try:
                    txt = cargo_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    txt = ""
            txt_lower = txt.lower()
            has_lib = (self.crate_dir / "src" / "lib.rs").exists() or bool(
                re.search(r"(?m)^\s*\[lib\]\s*$", txt_lower)
            )
            # 兼容：[[bin]] 为数组表，极少数项目也会写成 [bin]
            has_bin = (self.crate_dir / "src" / "main.rs").exists() or bool(
                re.search(r"(?m)^\s*\[\[bin\]\]\s*$", txt_lower)
                or re.search(r"(?m)^\s*\[bin\]\s*$", txt_lower)
            )
            if has_lib and has_bin:
                return "mixed"
            if has_bin:
                return "bin"
            if has_lib:
                return "lib"
        except Exception:
            pass
        # 默认假设为 lib
        return "lib"

    def run_cargo_fmt(self, workspace_root: str) -> None:
        """执行 cargo fmt 格式化代码"""
        try:
            res = subprocess.run(
                ["cargo", "fmt"],
                capture_output=True,
                text=True,
                check=False,
                cwd=workspace_root,
            )
            if res.returncode == 0:
                PrettyOutput.auto_print("🔍 [c2rust-transpiler][fmt] 代码格式化完成")
            else:
                # fmt 失败不影响主流程，只记录警告
                PrettyOutput.auto_print(
                    f"⚠️ [c2rust-transpiler][fmt] 代码格式化失败（非致命）: {res.stderr or res.stdout}"
                )
        except Exception as e:
            # fmt 失败不影响主流程，只记录警告
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][fmt] 代码格式化异常（非致命）: {e}"
            )

    def build_repair_prompt_base(
        self,
        stage: str,
        tags: List[str],
        sym_name: str,
        src_loc: str,
        c_code: str,
        curr: Dict[str, Any],
        symbols_path: str,
        include_output_patch_hint: bool = False,
        agent: Optional[Any] = None,
    ) -> List[str]:
        """
        构建修复提示词的基础部分。

        返回基础行列表。
        """
        # 检查是否为根符号
        is_root = sym_name in (self.root_symbols or [])
        # 获取 C 源文件位置信息（如果 src_loc 包含文件路径和行号）
        c_file_location = ""
        if src_loc:
            # src_loc 格式可能是 "file:start-end" 或 "file"
            if ":" in src_loc and "-" in src_loc:
                c_file_location = src_loc
            elif src_loc:
                # 如果只有文件路径，尝试从 curr 获取行号信息
                if curr.get("file"):
                    file_path = curr.get("file", "")
                    start_line = curr.get("start_line")
                    end_line = curr.get("end_line")
                    if start_line and end_line:
                        c_file_location = f"{file_path}:{start_line}-{end_line}"
                    else:
                        c_file_location = file_path
                else:
                    c_file_location = src_loc

        base_lines = [
            f"目标：以最小的改动修复问题，使 `{stage}` 命令可以通过。",
            f"阶段：{stage}",
            f"错误分类标签: {tags}",
            *([f"C 源文件位置：{c_file_location}"] if c_file_location else []),
            f"**Crate 根目录（重要）**：{self.crate_dir.resolve()}",
            "  - 所有 Rust 源码文件都位于此目录下",
            "  - 使用 `read_code` 工具读取文件时，请使用相对于此目录的路径（如 `src/xxx.rs`）或绝对路径",
            "  - 使用 `edit_file_*` 工具编辑文件时，文件路径也应相对于此目录或使用绝对路径",
            "",
            "允许的修复：修正入口/模块声明/依赖；对入口文件与必要mod.rs进行轻微调整；在缺失/未实现的被调函数导致错误时，一并补齐这些依赖的Rust实现（可新增合理模块/函数）；避免大范围改动。",
            "- 保持最小改动，避免与错误无关的重构或格式化；",
            "- 如构建失败源于缺失或未实现的被调函数/依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时可在合理的模块中新建函数；",
            "- 禁止使用 todo!/unimplemented! 作为占位；",
            "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号，避免通配；",
            "- **编译警告消除**：修复时必须同时消除所有编译警告（compiler warnings）。修复后应运行 `cargo check --message-format=short` 验证没有警告；",
            "- **Clippy 警告消除**：修复时必须同时消除所有 clippy 警告。修复后应运行 `cargo clippy -- -D warnings` 验证没有警告；",
            "- **🔍 调试辅助：如果遇到难以定位的问题，可以使用以下方法辅助调试**：",
            "  * 添加临时调试输出：使用 `println!()` 或 `dbg!()` 宏输出关键变量的值、函数调用路径、中间状态等",
            "  * 检查函数调用链：使用 `read_code` 工具读取相关函数的实现，确认调用关系是否正确",
            "  * 验证数据流：在关键位置添加调试输出，检查数据在函数间的传递是否正确",
            "  * 对比 C 实现：使用 `read_symbols` 和 `read_code` 工具读取 C 源码，对比 Rust 实现与 C 实现的差异",
            "  * 检查类型转换：确认 Rust 类型与 C 类型的对应关系是否正确，特别是指针、数组、结构体等",
            "  * 验证边界条件：检查数组边界、空值处理、溢出处理等边界情况",
            "  * 运行单个测试：如果测试套件很大，可以使用 `cargo test -- --nocapture <test_name>` 运行特定测试，加快调试速度",
            "  * 查看完整错误信息：确保阅读完整的错误输出，包括堆栈跟踪、类型信息、位置信息等",
            "  * 注意：调试输出可以在修复后移除，但建议保留关键位置的调试信息直到问题完全解决",
            "- ⚠️ **重要：修复范围要求** - 不仅要修复当前问题，如果修复过程中导致其他测试用例失败，也必须一并修复：",
            "  * 修复后必须运行 `cargo test -- --nocapture` 验证所有测试用例都能通过",
            "  * 如果发现修复后某些原本通过的测试用例现在失败了，说明修复引入了回归问题，必须一并修复",
            "  * 必须确保修复后所有测试用例（包括目标函数的测试和其他函数的测试）都能通过",
            "  * 如果修复影响了其他函数或模块，需要检查并修复所有受影响的部分",
            "  * 不要只修复当前问题，而忽略其他测试的失败",
            "- **⚠️ 重要：修复后必须验证** - 修复完成后，必须使用 `execute_script` 工具执行验证命令：",
            "  * 执行 `cargo test -- --nocapture` 验证编译和测试是否通过",
            "  * 命令必须成功（返回码为 0），才说明修复成功",
            "  * **不要假设修复成功，必须实际执行命令验证**",
            "  * **cargo test 会自动编译，无需单独执行 cargo check**",
            "- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
            f"- 依赖管理：如修复中引入新的外部 crate 或需要启用 feature，请同步更新 Cargo.toml 的 [dependencies]/[dev-dependencies]/[features]{('，避免未声明依赖导致构建失败；版本号可使用兼容范围（如 ^x.y）或默认值' if stage == 'cargo test' else '')}；",
            *(
                [
                    f"- **禁用库约束**：禁止在修复中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果修复需要使用这些库的功能，请使用标准库或其他允许的库替代。"
                ]
                if self.disabled_libraries
                else []
            ),
            *(
                [
                    f"- **根符号要求**：此函数是根符号（{sym_name}），必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。"
                ]
                if is_root
                else []
            ),
            "",
            "【重要：依赖检查与实现要求】",
            "在修复问题之前，请务必检查以下内容：",
            "1. 检查当前函数是否已完整实现：",
            f"   - 在目标模块中查找函数 {sym_name} 的实现",
            "   - 如果已存在实现，检查其是否完整且正确",
            "2. 检查所有依赖函数是否已实现：",
            "   - 分析构建错误，识别所有缺失或未实现的被调函数",
            "   - 遍历当前函数调用的所有被调函数（包括直接调用和间接调用）",
            "   - 对于每个被调函数，检查其在 Rust crate 中是否已有完整实现",
            "   - 可以使用 read_code 工具读取相关模块文件进行检查",
            "3. 对于未实现的依赖函数：",
            "   - 使用 read_symbols 工具获取其 C 源码和符号信息",
            "   - 使用 read_code 工具读取其 C 源码实现",
            "   - 在本次修复中一并补齐这些依赖函数的 Rust 实现",
            "   - 根据依赖关系选择合适的模块位置（可在同一模块或合理的新模块中）",
            "   - 确保所有依赖函数都有完整实现，禁止使用 todo!/unimplemented! 占位",
            "4. 实现顺序：",
            "   - 优先实现最底层的依赖函数（不依赖其他未实现函数的函数）",
            "   - 然后实现依赖这些底层函数的函数",
            "   - 最后修复当前目标函数",
            "5. 验证：",
            "   - 确保当前函数及其所有依赖函数都已完整实现",
            "   - 确保没有遗留的 todo!/unimplemented! 占位",
            "   - 确保所有函数调用都能正确解析",
        ]
        if include_output_patch_hint:
            base_lines.append("- 请仅输出补丁，不要输出解释或多余文本。")
        base_lines.extend(
            [
                "",
                "最近处理的函数上下文（供参考，优先修复构建错误）：",
                f"- 函数：{sym_name}",
                f"- 源位置：{src_loc}",
                f"- 目标模块（progress）：{curr.get('module') or ''}",
                f"- 建议签名（progress）：{curr.get('rust_signature') or ''}",
                "",
                "原始C函数源码片段（只读参考）：",
                "<C_SOURCE>",
                c_code,
                "</C_SOURCE>",
            ]
        )
        # 添加编译参数（如果存在）
        c_file_path = curr.get("file") or ""
        if c_file_path:
            compile_flags = self.extract_compile_flags(c_file_path)
            if compile_flags:
                base_lines.extend(
                    [
                        "",
                        "C文件编译参数（来自 compile_commands.json）：",
                        "\n".join(compile_flags),
                    ]
                )
        base_lines.extend(
            [
                "",
                "【工具使用建议】",
                "1. 符号表检索：",
                "   - 工具: read_symbols",
                "   - 用途: 定位或交叉验证 C 符号位置",
                "   - 参数示例(JSON):",
                f'     {{"symbols_file": "{symbols_path}", "symbols": ["{sym_name}"]}}',
                "",
                "2. 代码读取：",
                "   - 工具: read_code",
                "   - 用途: 读取 C 源码实现或 Rust 模块文件",
                "   - 调试用途: 当遇到问题时，可以读取相关文件检查实现是否正确",
                "   - **重要**：读取 Rust 源码文件时，必须使用绝对路径或相对于 crate 根目录的路径",
                f"   - **Crate 根目录**：{self.crate_dir.resolve()}",
                "   - 示例：",
                f"     * 读取 Rust 文件：`read_code` 工具，文件路径使用 `{self.crate_dir.resolve()}/src/xxx.rs` 或 `src/xxx.rs`（相对于 crate 根目录）",
                "     * 读取 C 文件：`read_code` 工具，文件路径使用 C 源文件的完整路径",
                "",
                "3. 脚本执行（调试辅助）：",
                "   - 工具: execute_script",
                "   - 调试用途:",
                "     * 执行 `cargo test -- --nocapture <test_name>` 运行特定测试，加快调试速度",
                "     * 执行 `cargo test --message-format=short --no-run` 只检查编译，不运行测试",
                "     * 执行 `cargo check` 快速检查编译错误（如果测试太慢）",
                "     * 执行 `cargo test --lib` 只运行库测试，跳过集成测试",
                "     * 执行 `cargo test --test <test_file>` 运行特定的测试文件",
                "",
                "上下文：",
                f"- **Crate 根目录路径（重要）**: {self.crate_dir.resolve()}",
                "  * 所有 Rust 源码文件都位于此目录下",
                "  * 使用 `read_code` 工具读取 Rust 文件时，文件路径应相对于此目录（如 `src/xxx.rs`）或使用绝对路径",
                "  * 当前工作目录应切换到此目录，或使用绝对路径访问文件",
                f"- 包名称（用于 cargo -p）: {self.crate_dir.name}",
            ]
        )

        # 添加 git 变更信息作为上下文
        if self.get_git_diff:
            try:
                base_commit = self._current_function_start_commit_getter()
                git_diff = self.get_git_diff(base_commit)
                if git_diff and git_diff.strip():
                    # 限制 git diff 长度，避免上下文过大
                    # 使用较小的比例（30%）因为修复提示词本身已经很长
                    # 如果提供了 agent 则使用它获取更准确的剩余 token，否则使用回退方案
                    git_diff = truncate_git_diff_with_context_limit(
                        git_diff, agent=agent, token_ratio=0.3
                    )

                    base_lines.extend(
                        [
                            "",
                            "【Git 变更信息】",
                            "以下是从函数开始处理到当前的 git 变更，可以帮助你了解已经做了哪些修改：",
                            "<GIT_DIFF>",
                            git_diff,
                            "</GIT_DIFF>",
                            "",
                            "提示：",
                            "- 请仔细查看上述 git diff，了解当前代码的状态和已做的修改",
                            "- 如果看到之前的修改引入了问题，可以在修复时一并处理",
                            "- 如果看到某些文件被意外修改，需要确认这些修改是否必要",
                        ]
                    )
            except Exception:
                # 如果获取 git diff 失败，不影响主流程，只记录警告
                pass

        return base_lines

    def build_repair_prompt_stage_section(
        self, stage: str, output: str, command: Optional[str] = None
    ) -> List[str]:
        """
        构建修复提示词的阶段特定部分（测试或检查）。

        返回阶段特定的行列表。
        """
        section_lines: List[str] = []
        if stage == "cargo_test_warning":
            section_lines.extend(
                [
                    "",
                    "【⚠️ 重要：Cargo Test 编译警告 - 必须消除】",
                    "以下输出来自 `cargo test -- --nocapture` 命令，包含编译和测试过程中的警告详情：",
                    "- **Cargo Test 警告当前状态：有警告** - 必须消除所有警告才能继续",
                    "- 这些警告是在 `cargo test` 编译阶段产生的（如 `unused_mut`、`unused_variables`、`dead_code` 等）",
                    "- Cargo Test 警告通常表示代码存在潜在问题或可以改进的地方",
                    "- **请仔细阅读警告信息**，包括：",
                    "  * 警告类型（如 `unused_mut`、`unused_variables`、`dead_code`、`unused_import` 等）",
                    "  * 警告位置（文件路径和行号）",
                    "  * 警告说明和建议的修复方法",
                    "",
                    "**关键要求：**",
                    "- 必须分析每个警告的根本原因，并按照编译器的建议进行修复",
                    "- 必须实际修复导致警告的代码，而不是忽略警告",
                    "- 修复后必须确保 `cargo test -- --nocapture` 能够通过（返回码为 0 且无警告输出）",
                    "- 注意：`cargo test` 会自动编译代码，编译阶段的警告会显示在输出中",
                    "",
                ]
            )
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append(
                    "提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。"
                )
            section_lines.extend(
                [
                    "",
                    "【Cargo Test 警告详细信息 - 必须仔细阅读并修复】",
                    "以下是从 `cargo test -- --nocapture` 命令获取的完整输出，包含所有警告的具体信息：",
                    "<CARGO_TEST_WARNINGS>",
                    output,
                    "</CARGO_TEST_WARNINGS>",
                    "",
                    "**修复要求：**",
                    "1. 仔细分析上述警告信息，找出每个警告的根本原因",
                    "2. 定位到具体的代码位置（文件路径和行号）",
                    "3. 按照编译器的建议进行修复：",
                    "   - 如果警告建议移除 `mut`，请移除不必要的 `mut` 关键字",
                    "   - 如果警告建议使用下划线前缀，请将未使用的变量改为 `_变量名`",
                    "   - 如果警告是 `dead_code`（未使用的函数/变量），请移除未使用的代码或使用 `#[allow(dead_code)]` 注解（仅在必要时）",
                    "   - 如果警告建议移除未使用的导入，请移除或使用 `#[allow(unused_imports)]` 注解（仅在必要时）",
                    "   - 如果警告建议使用更安全的 API，请使用建议的 API",
                    "   - 如果警告建议改进代码结构，请按照建议优化代码",
                    "4. 修复所有警告，确保 `cargo test -- --nocapture` 能够通过（返回码为 0 且无警告输出）",
                    "5. 如果某些警告确实无法修复或需要特殊处理，可以使用 `#[allow(warning_name)]` 注解，但必须添加注释说明原因",
                    "",
                    "**⚠️ 重要：修复后必须验证**",
                    "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                    f"  - 命令：`{command or 'cargo test -- --nocapture'}`",
                    "- 验证要求：",
                    "  * 如果命令执行成功（返回码为 0）且无警告输出，说明修复成功",
                    "  * 如果命令执行失败（返回码非 0）或有警告输出，说明仍有警告，需要继续修复",
                    "  * **不要假设修复成功，必须实际执行命令验证**",
                    "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
                    "",
                    "修复后请再次执行 `cargo test -- --nocapture` 进行验证。",
                ]
            )
        elif stage == "compiler_warning":
            section_lines.extend(
                [
                    "",
                    "【⚠️ 重要：编译警告 - 必须消除】",
                    "以下输出来自 `cargo check --message-format=short` 命令，包含编译警告详情：",
                    "- **编译警告当前状态：有警告** - 必须消除所有警告才能继续",
                    "- 编译警告通常表示代码存在潜在问题或可以改进的地方",
                    "- **请仔细阅读警告信息**，包括：",
                    "  * 警告类型（如 `unused_variable`、`dead_code`、`unused_import` 等）",
                    "  * 警告位置（文件路径和行号）",
                    "  * 警告说明和建议的修复方法",
                    "",
                    "**关键要求：**",
                    "- 必须分析每个警告的根本原因，并按照编译器的建议进行修复",
                    "- 必须实际修复导致警告的代码，而不是忽略警告",
                    "- 修复后必须确保 `cargo check --message-format=short` 能够通过（返回码为 0 且无警告输出）",
                    "",
                ]
            )
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append(
                    "提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。"
                )
            section_lines.extend(
                [
                    "",
                    "【编译警告详细信息 - 必须仔细阅读并修复】",
                    "以下是从 `cargo check --message-format=short` 命令获取的完整输出，包含所有警告的具体信息：",
                    "<COMPILER_WARNINGS>",
                    output,
                    "</COMPILER_WARNINGS>",
                    "",
                    "**修复要求：**",
                    "1. **优先尝试自动修复**：先使用 `cargo fix` 命令自动修复可以自动修复的警告：",
                    "   - 执行 `cargo fix --allow-dirty --allow-staged` 尝试自动修复编译警告",
                    "   - 如果自动修复成功，验证修复效果：执行 `cargo check --message-format=short` 检查是否还有警告",
                    "   - 如果自动修复后仍有警告，继续手动修复剩余的警告",
                    "2. 仔细分析上述编译警告信息，找出每个警告的根本原因",
                    "3. 定位到具体的代码位置（文件路径和行号）",
                    "4. 按照编译器的建议进行修复：",
                    "   - 如果警告建议移除未使用的代码，请移除或使用 `#[allow(...)]` 注解（仅在必要时）",
                    "   - 如果警告建议使用更安全的 API，请使用建议的 API",
                    "   - 如果警告建议改进代码结构，请按照建议优化代码",
                    "5. 修复所有警告，确保 `cargo check --message-format=short` 能够通过（无警告输出）",
                    "6. 如果某些警告确实无法修复或需要特殊处理，可以使用 `#[allow(warning_name)]` 注解，但必须添加注释说明原因",
                    "",
                    "**⚠️ 重要：修复后必须验证**",
                    "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                    f"  - 命令：`{command or 'cargo check --message-format=short'}`",
                    "- 验证要求：",
                    "  * 如果命令执行成功（返回码为 0）且无警告输出，说明修复成功",
                    "  * 如果命令执行失败（返回码非 0）或有警告输出，说明仍有警告，需要继续修复",
                    "  * **不要假设修复成功，必须实际执行命令验证**",
                    "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
                    "",
                    "修复后请再次执行 `cargo check --message-format=short` 进行验证。",
                ]
            )
        elif stage == "clippy":
            section_lines.extend(
                [
                    "",
                    "【⚠️ 重要：Clippy 警告 - 必须消除】",
                    "以下输出来自 `cargo clippy -- -D warnings` 命令，包含 clippy 警告详情：",
                    "- **Clippy 当前状态：有警告** - 必须消除所有警告才能继续",
                    "- Clippy 是 Rust 的代码质量检查工具，警告通常表示代码可以改进",
                    "- **请仔细阅读警告信息**，包括：",
                    "  * 警告类型（如 `unused_variable`、`needless_borrow`、`clippy::unwrap_used` 等）",
                    "  * 警告位置（文件路径和行号）",
                    "  * 警告说明和建议的修复方法",
                    "",
                    "**关键要求：**",
                    "- 必须分析每个警告的根本原因，并按照 clippy 的建议进行修复",
                    "- 必须实际修复导致警告的代码，而不是忽略警告",
                    "- 修复后必须确保 `cargo clippy -- -D warnings` 能够通过（返回码为 0）",
                    "",
                ]
            )
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append(
                    "提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。"
                )
            section_lines.extend(
                [
                    "",
                    "【Clippy 警告详细信息 - 必须仔细阅读并修复】",
                    "以下是从 `cargo clippy -- -D warnings` 命令获取的完整输出，包含所有警告的具体信息：",
                    "<CLIPPY_WARNINGS>",
                    output,
                    "</CLIPPY_WARNINGS>",
                    "",
                    "**修复要求：**",
                    "1. **优先尝试自动修复**：先使用 `cargo clippy --fix` 命令自动修复可以自动修复的警告：",
                    "   - 执行 `cargo clippy --fix --allow-dirty --allow-staged -- -D warnings` 尝试自动修复 clippy 警告",
                    "   - 如果自动修复成功，验证修复效果：执行 `cargo clippy -- -D warnings` 检查是否还有警告",
                    "   - 如果自动修复后仍有警告，继续手动修复剩余的警告",
                    "2. 仔细分析上述 clippy 警告信息，找出每个警告的根本原因",
                    "3. 定位到具体的代码位置（文件路径和行号）",
                    "4. 按照 clippy 的建议进行修复：",
                    "   - 如果警告建议使用更简洁的写法，请采用建议的写法",
                    "   - 如果警告建议移除未使用的代码，请移除或使用 `#[allow(...)]` 注解（仅在必要时）",
                    "   - 如果警告建议使用更安全的 API，请使用建议的 API",
                    "   - 如果警告建议改进性能，请按照建议优化代码",
                    "5. 修复所有警告，确保 `cargo clippy -- -D warnings` 能够通过",
                    "6. 如果某些警告确实无法修复或需要特殊处理，可以使用 `#[allow(clippy::warning_name)]` 注解，但必须添加注释说明原因",
                    "",
                    "**⚠️ 重要：修复后必须验证**",
                    "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                    f"  - 命令：`{command or 'cargo clippy -- -D warnings'}`",
                    "- 验证要求：",
                    "  * 如果命令执行成功（返回码为 0），说明修复成功",
                    "  * 如果命令执行失败（返回码非 0），说明仍有警告，需要继续修复",
                    "  * **不要假设修复成功，必须实际执行命令验证**",
                    "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
                    "",
                    "修复后请再次执行 `cargo clippy -- -D warnings` 进行验证。",
                ]
            )
        elif stage == "cargo test":
            section_lines.extend(
                [
                    "",
                    "【⚠️ 重要：测试失败 - 必须修复】",
                    "以下输出来自 `cargo test` 命令，包含测试执行结果和失败详情：",
                    "- **测试当前状态：失败** - 必须修复才能继续",
                    "- 如果看到测试用例名称和断言失败，说明测试逻辑或实现有问题",
                    "- 如果看到编译错误，说明代码存在语法或类型错误",
                    "- **请仔细阅读失败信息**，包括：",
                    "  * 测试用例名称（如 `test_bz_read_get_unused`）",
                    "  * 失败位置（文件路径和行号，如 `src/ffi/decompress.rs:76:47`）",
                    "  * 错误类型（如 `SequenceError`、`Result::unwrap()` 失败等）",
                    "  * 期望值与实际值的差异",
                    "  * 完整的堆栈跟踪信息",
                    "",
                    "**关键要求：**",
                    "- 必须分析测试失败的根本原因，而不是假设问题已解决",
                    "- 必须实际修复导致测试失败的代码，而不是只修改测试用例",
                    "- 修复后必须确保测试能够通过，而不是只修复编译错误",
                    "",
                ]
            )
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append(
                    "提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。"
                )
            section_lines.extend(
                [
                    "",
                    "【测试失败详细信息 - 必须仔细阅读并修复】",
                    "以下是从 `cargo test` 命令获取的完整输出，包含测试失败的具体信息：",
                    "<TEST_FAILURE>",
                    output,
                    "</TEST_FAILURE>",
                    "",
                    "**修复要求：**",
                    "1. 仔细分析上述测试失败信息，找出失败的根本原因",
                    "2. 定位到具体的代码位置（文件路径和行号）",
                    "3. **如果问题难以定位，添加调试信息辅助定位**：",
                    "   - 在关键位置添加 `println!()` 或 `dbg!()` 输出变量值、函数调用路径、中间状态",
                    "   - 检查函数参数和返回值是否正确传递",
                    "   - 验证数据结构和类型转换是否正确",
                    "   - 对比 C 实现与 Rust 实现的差异，找出可能导致问题的点",
                    "   - 使用 `read_code` 工具读取相关函数的实现，确认逻辑是否正确",
                    "   - 如果测试输出信息不足，可以添加更详细的调试输出来定位问题",
                    "4. 修复导致测试失败的代码逻辑",
                    "5. ⚠️ **重要：修复范围要求** - 不仅要修复当前失败的测试用例，如果修复过程中导致其他测试用例失败，也必须一并修复：",
                    "   - 修复后必须运行 `cargo test -- --nocapture` 验证所有测试用例都能通过",
                    "   - 如果发现修复后某些原本通过的测试用例现在失败了，说明修复引入了回归问题，必须一并修复",
                    "   - 必须确保修复后所有测试用例（包括目标函数的测试和其他函数的测试）都能通过",
                    "   - 如果修复影响了其他函数或模块，需要检查并修复所有受影响的部分",
                    "   - 不要只修复当前失败的测试，而忽略其他测试的失败",
                    "6. 确保修复后所有测试能够通过（不要只修复编译错误）",
                    "7. 如果测试用例本身有问题，可以修改测试用例，但必须确保测试能够正确验证函数行为",
                    "",
                    "**⚠️ 重要：修复后必须验证**",
                    "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                    f"  - 命令：`{command or 'cargo test -- --nocapture'}`",
                    "- 验证要求：",
                    "  * 如果命令执行成功（返回码为 0），说明修复成功",
                    "  * 如果命令执行失败（返回码非 0），说明修复未成功，需要继续修复",
                    "  * **不要假设修复成功，必须实际执行命令验证**",
                    "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
                    "",
                    "**⚠️ 并发问题提示**：",
                    "- 如果测试运行失败，但在修复时没有修改任何代码，重新运行测试却成功了，这可能是并发问题导致的：",
                    "  * 可能是测试之间存在竞态条件（race condition）",
                    "  * 可能是共享资源（文件、网络、数据库等）的并发访问问题",
                    "  * 可能是测试执行顺序依赖问题",
                    "- 如果遇到这种情况，建议：",
                    "  * 多次运行测试确认问题是否稳定复现",
                    "  * 检查测试之间是否存在共享状态或资源",
                    "  * 检查测试是否依赖特定的执行顺序",
                    "  * 考虑添加同步机制或隔离测试环境",
                    "  * 如果问题不稳定，可能需要添加重试机制或调整测试策略",
                    "",
                    "修复后请再次执行 `cargo test -q` 进行验证。",
                ]
            )
        else:
            section_lines.extend(
                [
                    "",
                    "请阅读以下构建错误并进行必要修复：",
                ]
            )
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append(
                    "提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。"
                )
            section_lines.extend(
                [
                    "",
                    "<BUILD_ERROR>",
                    output,
                    "</BUILD_ERROR>",
                    "",
                    "**修复要求：**",
                    "1. 仔细分析上述构建错误信息，找出错误的根本原因",
                    "2. 定位到具体的代码位置（文件路径和行号）",
                    "3. **如果问题难以定位，添加调试信息辅助定位**：",
                    "   - 使用 `read_code` 工具读取相关文件，检查代码实现是否正确",
                    "   - 检查类型定义、函数签名、模块导入等是否正确",
                    "   - 验证依赖关系是否正确，所有被调用的函数/类型是否已定义",
                    "   - 如果错误信息不够清晰，可以尝试编译单个文件或模块来缩小问题范围",
                    "   - 对比 C 实现与 Rust 实现的差异，确认类型映射是否正确",
                    "4. 修复导致构建错误的代码",
                    "5. ⚠️ **重要：修复范围要求** - 不仅要修复当前构建错误，如果修复过程中导致其他测试用例失败，也必须一并修复：",
                    "   - 修复后必须运行 `cargo test -- --nocapture` 验证所有测试用例都能通过",
                    "   - 如果发现修复后某些原本通过的测试用例现在失败了，说明修复引入了回归问题，必须一并修复",
                    "   - 必须确保修复后所有测试用例（包括目标函数的测试和其他函数的测试）都能通过",
                    "   - 如果修复影响了其他函数或模块，需要检查并修复所有受影响的部分",
                    "   - 不要只修复当前构建错误，而忽略其他测试的失败",
                    "6. 确保修复后代码能够编译通过，且所有测试用例都能通过",
                    "",
                    "**⚠️ 重要：修复后必须验证**",
                    "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                    "  - 命令：`cargo test -- --nocapture`",
                    "- 验证要求：",
                    "  * 命令必须执行成功（返回码为 0），才说明修复成功",
                    "  * 如果命令执行失败（返回码非 0），说明修复未成功，需要继续修复",
                    "  * **不要假设修复成功，必须实际执行命令验证**",
                    "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
                    "",
                    "修复后请执行 `cargo test -- --nocapture` 进行验证。",
                ]
            )
        return section_lines

    def build_repair_prompt(
        self,
        stage: str,
        output: str,
        tags: List[str],
        sym_name: str,
        src_loc: str,
        c_code: str,
        curr: Dict[str, Any],
        symbols_path: str,
        include_output_patch_hint: bool = False,
        command: Optional[str] = None,
        agent: Optional[Any] = None,
    ) -> str:
        """
        构建修复提示词。

        Args:
            stage: 阶段名称（"cargo test"）
            output: 构建错误输出
            tags: 错误分类标签
            sym_name: 符号名称
            src_loc: 源文件位置
            c_code: C 源码片段
            curr: 当前进度信息
            symbols_path: 符号表文件路径
            include_output_patch_hint: 是否包含"仅输出补丁"提示（test阶段需要）
            command: 执行的命令（可选）
        """
        base_lines = self.build_repair_prompt_base(
            stage,
            tags,
            sym_name,
            src_loc,
            c_code,
            curr,
            symbols_path,
            include_output_patch_hint,
            agent=agent,
        )
        stage_lines = self.build_repair_prompt_stage_section(stage, output, command)
        prompt = "\n".join(base_lines + stage_lines)
        return self.append_additional_notes(prompt)

    def run_cargo_test_and_fix(
        self, workspace_root: str, test_iter: int
    ) -> Tuple[bool, Optional[bool]]:
        """
        运行 cargo test 并在失败时修复。

        Returns:
            (是否成功, 是否需要回退重新开始，None表示需要回退)
        """
        # 测试失败时需要详细输出，移除 -q 参数以获取完整的测试失败信息（包括堆栈跟踪、断言详情等）
        try:
            res_test = subprocess.run(
                ["cargo", "test", "--", "--nocapture"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                cwd=workspace_root,
            )
            returncode = res_test.returncode
            stdout = res_test.stdout or ""
            stderr = res_test.stderr or ""
        except subprocess.TimeoutExpired as e:
            # 超时视为测试失败，继续修复流程
            returncode = -1
            stdout = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            stderr = "命令执行超时（30秒）\n" + (
                e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            )
            PrettyOutput.auto_print(
                "⚠️ [c2rust-transpiler][build] Cargo 测试超时（30秒），视为失败并继续修复流程"
            )
        except Exception as e:
            # 其他异常也视为测试失败
            returncode = -1
            stdout = ""
            stderr = f"执行 cargo test 时发生异常: {str(e)}"
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][build] Cargo 测试执行异常: {e}，视为失败并继续修复流程"
            )

        # 检查 cargo test 输出中是否包含警告（即使测试通过也可能有警告）
        test_output_combined = stdout + "\n" + stderr
        test_has_warnings = "warning:" in test_output_combined.lower()

        warning_type: Optional[str] = None
        output: str = ""
        if returncode == 0:
            # 测试通过，先检查 cargo test 输出中的警告，再检查编译警告，最后检查 clippy 警告
            if test_has_warnings:
                # cargo test 输出中有警告，提取并修复
                PrettyOutput.auto_print(
                    "⚠️ [c2rust-transpiler][build] Cargo 测试通过，但输出中存在警告，需要修复。"
                )
                PrettyOutput.auto_print(test_output_combined)
                # 将 cargo test 输出中的警告作为修复目标
                warning_type = "cargo_test_warning"
                output = test_output_combined
            else:
                # cargo test 输出中无警告，检查编译警告
                compiler_has_warnings = False
                compiler_output = ""
                try:
                    res_compiler = subprocess.run(
                        ["cargo", "check", "--message-format=short"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                        cwd=workspace_root,
                    )
                    # 检查是否有警告输出（即使返回码为0，也可能有警告）
                    combined_output = (
                        (res_compiler.stdout or "") + "\n" + (res_compiler.stderr or "")
                    )
                    # 检查输出中是否包含警告（warning: 关键字）
                    if (
                        "warning:" in combined_output.lower()
                        or res_compiler.returncode != 0
                    ):
                        compiler_has_warnings = True
                        compiler_output = combined_output
                except subprocess.TimeoutExpired:
                    # 编译检查超时，视为有警告
                    compiler_has_warnings = True
                    compiler_output = "编译检查超时（30秒）"
                except Exception as e:
                    # 编译检查执行异常，视为有警告
                    compiler_has_warnings = True
                    compiler_output = f"执行编译检查时发生异常: {str(e)}"

                if compiler_has_warnings:
                    PrettyOutput.auto_print(
                        "⚠️ [c2rust-transpiler][build] Cargo 测试通过，无 cargo test 警告，但存在编译警告，需要修复。"
                    )
                    PrettyOutput.auto_print(compiler_output)
                    # 将编译警告作为修复目标，继续修复流程
                    warning_type = "compiler"
                    output = compiler_output
                else:
                    # 无编译警告，检查 clippy 警告
                    clippy_has_warnings = False
                    clippy_output = ""
                    try:
                        res_clippy = subprocess.run(
                            ["cargo", "clippy", "--", "-D", "warnings"],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            check=False,
                            cwd=workspace_root,
                        )
                        if res_clippy.returncode != 0:
                            clippy_has_warnings = True
                            clippy_output = (
                                (res_clippy.stdout or "")
                                + "\n"
                                + (res_clippy.stderr or "")
                            )
                    except subprocess.TimeoutExpired:
                        # clippy 超时，视为有警告
                        clippy_has_warnings = True
                        clippy_output = "Clippy 检查超时（30秒）"
                    except Exception as e:
                        # clippy 执行异常，视为有警告
                        clippy_has_warnings = True
                        clippy_output = f"执行 clippy 时发生异常: {str(e)}"

                    if clippy_has_warnings:
                        PrettyOutput.auto_print(
                            "⚠️ [c2rust-transpiler][build] Cargo 测试通过，无编译警告，但存在 clippy 警告，需要修复。"
                        )
                        PrettyOutput.auto_print(clippy_output)
                        # 将 clippy 警告作为修复目标，继续修复流程
                        warning_type = "clippy"
                        output = clippy_output
                    else:
                        PrettyOutput.auto_print(
                            "✅ [c2rust-transpiler][build] Cargo 测试通过，无 cargo test 警告，无编译警告，clippy 无警告。"
                        )
                        # 测试通过且无编译警告和 clippy 警告，重置连续失败计数
                        self._consecutive_fix_failures_setter(0)
                        try:
                            cur = self.progress.get("current") or {}
                            metrics = cur.get("metrics") or {}
                            metrics["test_attempts"] = int(test_iter)
                            cur["metrics"] = metrics
                            cur["impl_verified"] = True
                            cur["failed_stage"] = None
                            self.progress["current"] = cur
                            self.save_progress()
                        except Exception:
                            pass
                        return (True, False)
        else:
            # 测试失败
            # 检查测试失败输出中是否也包含警告（可能需要一并修复）
            if test_has_warnings:
                # 测试失败且输出中有警告，优先修复警告（因为警告可能导致测试失败）
                PrettyOutput.auto_print(
                    "⚠️ [c2rust-transpiler][build] Cargo 测试失败，且输出中存在警告，将优先修复警告。"
                )
                warning_type = "cargo_test_warning"
                output = test_output_combined
            else:
                # 测试失败但无警告，按测试失败处理
                warning_type = None
                output = test_output_combined
            limit_info = (
                f" (上限: {self.test_max_retries if self.test_max_retries > 0 else '无限'})"
                if test_iter % 10 == 0 or test_iter == 1
                else ""
            )
            PrettyOutput.auto_print(
                f"❌ [c2rust-transpiler][build] Cargo 测试失败 (第 {test_iter} 次尝试{limit_info})。"
            )
            PrettyOutput.auto_print(output)
            maxr = self.test_max_retries
            if maxr > 0 and test_iter >= maxr:
                PrettyOutput.auto_print(
                    f"❌ [c2rust-transpiler][build] 已达到最大重试次数上限({maxr})，停止构建修复循环。"
                )
                try:
                    cur = self.progress.get("current") or {}
                    metrics = cur.get("metrics") or {}
                    metrics["test_attempts"] = int(test_iter)
                    cur["metrics"] = metrics
                    cur["impl_verified"] = False
                    cur["failed_stage"] = "test"
                    err_summary = (output or "").strip()
                    if len(err_summary) > ERROR_SUMMARY_MAX_LENGTH:
                        err_summary = (
                            err_summary[:ERROR_SUMMARY_MAX_LENGTH] + "...(truncated)"
                        )
                    cur["last_build_error"] = err_summary
                    self.progress["current"] = cur
                    self.save_progress()
                except Exception:
                    pass
                return (False, False)

        # 构建失败（测试阶段）修复、编译警告修复、clippy 警告修复或 cargo test 警告修复
        if warning_type == "cargo_test_warning":
            # cargo test 输出中的警告修复
            tags = ["cargo_test_warning"]
            stage_name = "cargo_test_warning"
            command_str = "cargo test -- --nocapture"
        elif warning_type == "compiler":
            # 编译警告修复
            tags = ["compiler_warning"]
            stage_name = "compiler_warning"
            command_str = "cargo check --message-format=short"
        elif warning_type == "clippy":
            # clippy 警告修复
            tags = ["clippy_warning"]
            stage_name = "clippy"
            command_str = "cargo clippy -- -D warnings"
        else:
            # 测试失败修复
            tags = self.classify_rust_error(output)
            stage_name = "cargo test"
            command_str = "cargo test -- --nocapture"

        symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
        curr_info = self.get_current_function_context()
        sym_name = curr_info.get("sym_name", "")
        src_loc = curr_info.get("src_loc", "")
        c_code = curr_info.get("c_code", "")

        # 调试输出：确认错误信息是否正确传递
        if warning_type is None:
            PrettyOutput.auto_print(
                f"🔍 [c2rust-transpiler][debug] 测试失败信息长度: {len(output)} 字符"
            )
            if output:
                # 提取关键错误信息用于调试
                error_lines = output.split("\n")
                key_errors = [
                    line
                    for line in error_lines
                    if any(
                        keyword in line.lower()
                        for keyword in [
                            "failed",
                            "error",
                            "panic",
                            "unwrap",
                            "sequence",
                        ]
                    )
                ]
                if key_errors:
                    PrettyOutput.auto_print(
                        "🔍 [c2rust-transpiler][debug] 关键错误信息（前5行）:"
                    )
                    for i, line in enumerate(key_errors[:5], 1):
                        PrettyOutput.auto_print(f"🔍   {i}. {line[:100]}")

        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        # 记录运行前的 commit
        before_commit = self.get_crate_commit_hash()
        # 先创建修复 Agent（后续会复用）
        # 使用修复 Agent，每次重新创建，并传入 C 代码
        agent = self.get_fix_agent()

        repair_prompt = self.build_repair_prompt(
            stage=stage_name,
            output=output,
            tags=tags,
            sym_name=sym_name,
            src_loc=src_loc,
            c_code=c_code,
            curr=curr_info,
            symbols_path=symbols_path,
            include_output_patch_hint=True,
            command=command_str,
            agent=agent,
        )
        agent.run(
            self.compose_prompt_with_context(repair_prompt),
            prefix=f"[c2rust-transpiler][build-fix iter={test_iter}][test]",
            suffix="",
        )

        # 检测并处理测试代码删除
        if self.check_and_handle_test_deletion(before_commit, agent):
            # 如果回退了，需要重新运行 agent
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][build-fix] 检测到测试代码删除问题，已回退，重新运行 agent (iter={test_iter})"
            )
            before_commit = self.get_crate_commit_hash()
            # 重新创建修复 Agent
            agent = self.get_fix_agent()
            agent.run(
                self.compose_prompt_with_context(repair_prompt),
                prefix=f"[c2rust-transpiler][build-fix iter={test_iter}][test][retry]",
                suffix="",
            )
            # 再次检测
            if self.check_and_handle_test_deletion(before_commit, agent):
                PrettyOutput.auto_print(
                    f"❌ [c2rust-transpiler][build-fix] 再次检测到测试代码删除问题，已回退 (iter={test_iter})"
                )

        # 修复后验证：先检查编译，再实际运行测试
        # 第一步：检查编译是否通过
        res_compile = subprocess.run(
            ["cargo", "test", "--message-format=short", "-q", "--no-run"],
            capture_output=True,
            text=True,
            check=False,
            cwd=workspace_root,
        )
        if res_compile.returncode != 0:
            PrettyOutput.auto_print(
                "⚠️ [c2rust-transpiler][build] 修复后编译仍有错误，将在下一轮循环中处理"
            )
            # 编译失败，增加连续失败计数
            current_failures = self._consecutive_fix_failures_getter()
            self._consecutive_fix_failures_setter(current_failures + 1)
            # 检查是否需要回退
            current_start_commit = self._current_function_start_commit_getter()
            if (
                current_failures >= CONSECUTIVE_FIX_FAILURE_THRESHOLD
                and current_start_commit
            ):
                PrettyOutput.auto_print(
                    f"❌ [c2rust-transpiler][build] 连续修复失败 {current_failures} 次，回退到函数开始时的 commit: {current_start_commit}"
                )
                if self.reset_to_commit(current_start_commit):
                    # 返回特殊值，表示需要重新开始
                    return (False, None)
                # 回退失败，继续尝试修复
            return (False, False)  # 需要继续循环

        # 第二步：编译通过，实际运行测试验证
        try:
            res_test_verify = subprocess.run(
                ["cargo", "test", "--", "--nocapture"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                cwd=workspace_root,
            )
            verify_returncode = res_test_verify.returncode
            verify_stdout = res_test_verify.stdout or ""
            verify_stderr = res_test_verify.stderr or ""
            verify_output_combined = verify_stdout + "\n" + verify_stderr
            verify_has_warnings = "warning:" in verify_output_combined.lower()
        except subprocess.TimeoutExpired:
            # 超时视为测试失败
            verify_returncode = -1
            verify_has_warnings = False
            verify_output_combined = ""
            PrettyOutput.auto_print(
                "⚠️ [c2rust-transpiler][build] 修复后验证测试超时（30秒），视为失败"
            )
        except Exception as e:
            # 其他异常也视为测试失败
            verify_returncode = -1
            verify_has_warnings = False
            verify_output_combined = ""
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][build] 修复后验证测试执行异常: {e}，视为失败"
            )

        if verify_returncode == 0:
            # 测试通过，检查是否有警告
            if verify_has_warnings:
                PrettyOutput.auto_print(
                    "⚠️ [c2rust-transpiler][build] 修复后测试通过，但输出中存在警告，将在下一轮循环中处理"
                )
                PrettyOutput.auto_print(verify_output_combined)
                # 有警告，继续循环修复
                return (False, False)
            # 测试通过，先检查编译警告，再检查 clippy 警告
            compiler_has_warnings_after_fix = False
            compiler_output_after_fix = ""
            try:
                res_compiler_verify = subprocess.run(
                    ["cargo", "check", "--message-format=short"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    cwd=workspace_root,
                )
                # 检查是否有警告输出
                combined_output = (
                    (res_compiler_verify.stdout or "")
                    + "\n"
                    + (res_compiler_verify.stderr or "")
                )
                if (
                    "warning:" in combined_output.lower()
                    or res_compiler_verify.returncode != 0
                ):
                    compiler_has_warnings_after_fix = True
                    compiler_output_after_fix = combined_output
            except subprocess.TimeoutExpired:
                compiler_has_warnings_after_fix = True
                compiler_output_after_fix = "编译检查超时（30秒）"
            except Exception as e:
                compiler_has_warnings_after_fix = True
                compiler_output_after_fix = f"执行编译检查时发生异常: {str(e)}"

            if compiler_has_warnings_after_fix:
                PrettyOutput.auto_print(
                    "⚠️ [c2rust-transpiler][build] 修复后测试通过，但存在编译警告，将在下一轮循环中处理"
                )
                PrettyOutput.auto_print(compiler_output_after_fix)
                # 有编译警告，继续循环修复
                return (False, False)
            else:
                # 无编译警告，检查 clippy 警告
                clippy_has_warnings_after_fix = False
                clippy_output_after_fix = ""
                try:
                    res_clippy_verify = subprocess.run(
                        ["cargo", "clippy", "--", "-D", "warnings"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                        cwd=workspace_root,
                    )
                    if res_clippy_verify.returncode != 0:
                        clippy_has_warnings_after_fix = True
                        clippy_output_after_fix = (
                            (res_clippy_verify.stdout or "")
                            + "\n"
                            + (res_clippy_verify.stderr or "")
                        )
                except subprocess.TimeoutExpired:
                    clippy_has_warnings_after_fix = True
                    clippy_output_after_fix = "Clippy 检查超时（30秒）"
                except Exception as e:
                    clippy_has_warnings_after_fix = True
                    clippy_output_after_fix = f"执行 clippy 时发生异常: {str(e)}"

                if clippy_has_warnings_after_fix:
                    PrettyOutput.auto_print(
                        "⚠️ [c2rust-transpiler][build] 修复后测试通过，无编译警告，但存在 clippy 警告，将在下一轮循环中处理"
                    )
                    PrettyOutput.auto_print(clippy_output_after_fix)
                    # 有 clippy 警告，继续循环修复
                    return (False, False)
                else:
                    PrettyOutput.auto_print(
                        "✅ [c2rust-transpiler][build] 修复后测试通过，无 cargo test 警告，无编译警告，clippy 无警告，继续构建循环"
                    )
                    # 测试真正通过且无编译警告和 clippy 警告，重置连续失败计数
                    self._consecutive_fix_failures_setter(0)
                    return (False, False)  # 需要继续循环（但下次应该会通过）
        else:
            # 编译通过但测试仍然失败，说明修复没有解决测试逻辑问题
            PrettyOutput.auto_print(
                "⚠️ [c2rust-transpiler][build] 修复后编译通过，但测试仍然失败，将在下一轮循环中处理"
            )
            # 测试失败，增加连续失败计数（即使编译通过）
            current_failures = self._consecutive_fix_failures_getter()
            self._consecutive_fix_failures_setter(current_failures + 1)
            current_start_commit = self._current_function_start_commit_getter()
            # 检查是否需要回退
            if (
                current_failures >= CONSECUTIVE_FIX_FAILURE_THRESHOLD
                and current_start_commit
            ):
                PrettyOutput.auto_print(
                    f"❌ [c2rust-transpiler][build] 连续修复失败 {current_failures} 次（编译通过但测试失败），回退到函数开始时的 commit: {current_start_commit}"
                )
                if self.reset_to_commit(current_start_commit):
                    # 返回特殊值，表示需要重新开始
                    return (False, None)
                # 回退失败，继续尝试修复
            return (False, False)  # 需要继续循环

    def cargo_build_loop(self) -> Optional[bool]:
        """在 crate 目录执行构建与测试：直接运行 cargo test（运行所有测试，不区分项目结构）。失败则最小化修复直到通过或达到上限。

        Returns:
            Optional[bool]:
                - True: 测试通过（可能进行了修复）
                - False: 测试失败（达到重试上限）
                - None: 需要回退重新开始
        """
        workspace_root = str(self.crate_dir)
        test_limit = f"最大重试: {self.test_max_retries if self.test_max_retries > 0 else '无限'}"
        PrettyOutput.auto_print(
            f"🔍 [c2rust-transpiler][build] 工作区={workspace_root}，开始构建循环（test，{test_limit}）"
        )
        test_iter = 0
        has_fixes = False  # 标记是否进行了修复
        while True:
            # 运行所有测试（不区分项目结构）
            # cargo test 会自动编译并运行所有类型的测试：lib tests、bin tests、integration tests、doc tests 等
            test_iter += 1
            test_success, need_restart = self.run_cargo_test_and_fix(
                workspace_root, test_iter
            )
            if need_restart is None:
                self._build_loop_has_fixes = False  # 回退时重置标记
                return None  # 需要回退重新开始
            if test_success:
                # 如果进行了修复（test_iter > 1），标记需要重新 review
                if test_iter > 1:
                    has_fixes = True
                # 将修复标记保存到实例变量，供调用方检查
                self._build_loop_has_fixes = has_fixes
                return True  # 测试通过
            # 如果测试失败，说明进行了修复尝试
            if test_iter > 1:
                has_fixes = True
