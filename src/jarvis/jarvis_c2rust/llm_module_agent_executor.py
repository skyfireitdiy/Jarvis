"""LLM 模块规划 Agent 的执行器。"""

import os
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from pathlib import Path
from typing import List
from typing import Optional
from typing import Union

from jarvis.jarvis_c2rust.llm_module_agent_apply import (
    apply_project_structure_from_json,
)
from jarvis.jarvis_c2rust.llm_module_agent_utils import parse_project_json_entries
from jarvis.jarvis_c2rust.llm_module_agent_utils import resolve_created_dir


def execute_llm_plan(
    out: Optional[Union[Path, str]] = None,
    apply: bool = False,
    crate_name: Optional[Union[Path, str]] = None,
    llm_group: Optional[str] = None,
    non_interactive: bool = True,
) -> List:
    """
    返回 LLM 生成的目录结构原始 JSON 文本（来自 <PROJECT> 块）。
    不进行解析，便于后续按原样应用并在需要时使用更健壮的解析器处理。
    """
    # execute_llm_plan 是顶层入口，需要执行清理（skip_cleanup=False）
    # 延迟导入以避免循环依赖
    from jarvis.jarvis_c2rust.llm_module_agent import plan_crate_json_text

    json_text = plan_crate_json_text(llm_group=llm_group, skip_cleanup=False)
    entries, parse_error = parse_project_json_entries(json_text)
    if parse_error:
        raise ValueError(f"JSON解析失败: {parse_error}")
    if not entries:
        raise ValueError("[c2rust-llm-planner] 从LLM输出解析目录结构失败。正在中止。")

    # 2) 如需应用到磁盘
    if apply:
        target_root = crate_name if crate_name else "."
        try:
            apply_project_structure_from_json(json_text, project_root=target_root)
            PrettyOutput.auto_print("[c2rust-llm-planner] 项目结构已应用。")
        except Exception as e:
            PrettyOutput.auto_print(f"[c2rust-llm-planner] 应用项目结构失败: {e}")
            raise

        # Post-apply: 检查生成的目录结构，使用 CodeAgent 更新 Cargo.toml
        from jarvis.jarvis_code_agent.code_agent import (
            CodeAgent,
        )  # 延迟导入以避免全局耦合

        # 解析 crate 目录路径（与 apply 逻辑保持一致）
        try:
            created_dir = resolve_created_dir(target_root)
        except Exception:
            # 兜底：无法解析时直接使用传入的 target_root
            created_dir = Path(target_root)

        # 在 crate 目录内执行 git 初始化与初始提交（按新策略）
        try:
            # 初始化 git 仓库（若已存在则该命令为幂等）
            subprocess.run(["git", "init"], check=False, cwd=str(created_dir))
            # 添加所有文件并尝试提交
            subprocess.run(["git", "add", "-A"], check=False, cwd=str(created_dir))
            subprocess.run(
                ["git", "commit", "-m", "[c2rust-llm-planner] init crate"],
                check=False,
                cwd=str(created_dir),
            )
        except Exception:
            # 保持稳健，不因 git 失败影响主流程
            pass

        # 构建用于 CodeAgent 的目录上下文（简化版树形）
        def _format_tree(root: Path) -> str:
            lines: List[str] = []
            exclude = {".git", "target", ".jarvis"}
            if not root.exists():
                return ""
            for p in sorted(root.rglob("*")):
                if any(part in exclude for part in p.parts):
                    continue
                rel = p.relative_to(root)
                depth = len(rel.parts) - 1
                indent = "  " * depth
                name = rel.name + ("/" if p.is_dir() else "")
                lines.append(f"{indent}- {name}")
            return "\n".join(lines)

        dir_ctx = _format_tree(created_dir)
        crate_pkg_name = created_dir.name

        requirement_lines = [
            "目标：在该 crate 目录下确保 `cargo build` 能成功完成；如失败则根据错误最小化修改并重试，直到构建通过为止。",
            f"- crate_dir: {created_dir}",
            f"- crate_name: {crate_pkg_name}",
            "目录结构（部分）：",
            dir_ctx,
            "",
            "执行与修复流程（务必按序执行，可多轮迭代）：",
            "1) 先补齐 Rust 模块声明（仅最小化追加/升级，不覆盖业务实现）：",
            "   - 扫描 src 目录：",
            "     * 在每个子目录下（除 src 根）创建或更新 mod.rs，仅追加缺失的 `pub mod <child>;` 声明；",
            "     * 在 src/lib.rs 中为顶级子模块追加 `pub mod <name>;`；不要创建 src/mod.rs；忽略 lib.rs 与 main.rs 的自引用；",
            "   - 若存在 `mod <name>;` 但非 pub，则就地升级为 `pub mod <name>;`，保留原缩进与其他内容；",
            "   - 严禁删除现有声明或修改非声明代码；",
            '2) 在 Cargo.toml 的 [package] 中设置 edition："2024"；若本地工具链不支持 2024，请降级为 "2021" 并在说明中记录原因；保留其他已有字段与依赖不变。',
            "3) 根据当前源代码实际情况配置入口：",
            "   - 仅库：仅配置 [lib]（path=src/lib.rs），不要生成 main.rs；",
            "   - 单一可执行：存在 src/main.rs 时配置 [[bin]] 或默认二进制；可选保留 [lib] 以沉淀共享逻辑；",
            "   - 多可执行：为每个 src/bin/<name>.rs 配置 [[bin]]；共享代码放在 src/lib.rs；",
            "   - 不要创建与目录结构不一致的占位入口。",
            "4) 对被作为入口的源文件：若不存在 fn main() 则仅添加最小可用实现（不要改动已存在的实现）：",
            '   fn main() { println!("ok"); }',
            "5) 执行一次构建验证：`cargo build -q`（或 `cargo check -q`）。",
            "6) 若构建失败，读取错误并进行最小化修复，然后再次构建；重复直至成功。仅允许的修复类型：",
            "   - 依赖缺失：在 [dependencies] 中添加必要且稳定版本的依赖（优先无特性），避免新增未使用依赖；",
            "   - 入口/crate-type 配置错误：修正 [lib] 或 [[bin]] 的 name/path/crate-type 使之与目录与入口文件一致；",
            "   - 语言/工具链不兼容：将 edition 从 2024 调整为 2021；必要时可添加 rust-version 要求；",
            "   - 语法级/最小实现缺失：仅在入口文件中补充必要的 use/空实现/feature gate 以通过编译，避免改动非入口业务文件；",
            "   - 不要删除或移动现有文件与目录。",
            "7) 每轮修改后必须运行 `cargo build -q` 验证，直到构建成功为止。",
            "",
            "修改约束：",
            "- 允许修改的文件范围：Cargo.toml、src/lib.rs、src/main.rs、src/bin/*.rs、src/**/mod.rs（仅最小必要变更）；除非为修复构建与模块声明补齐，不要修改其他文件。",
            "- 尽量保持现有内容与结构不变，不要引入与构建无关的改动或格式化。",
            "",
            "交付要求：",
            "- 以补丁方式提交实际修改的文件；",
            "- 在最终回复中简要说明所做变更与最终 `cargo build` 的结果（成功/失败及原因）。",
        ]
        requirement_text = "\n".join(requirement_lines)

        prev_cwd = os.getcwd()
        try:
            # 切换到 crate 目录运行 CodeAgent 与构建
            os.chdir(str(created_dir))
            PrettyOutput.auto_print(
                f"[c2rust-llm-planner] 已切换到 crate 目录: {os.getcwd()}，执行 CodeAgent 初始化"
            )
            if llm_group:
                PrettyOutput.auto_print(f"[c2rust-llm-planner] 使用模型组: {llm_group}")
            try:
                # 验证模型配置在切换目录后是否仍然有效
                # CodeAgent 使用 smart 模型，所以这里也使用 smart 配置来显示正确的模型信息
                from jarvis.jarvis_utils.config import get_smart_model_name
                from jarvis.jarvis_utils.config import get_smart_platform_name

                if llm_group:
                    resolved_model = get_smart_model_name(llm_group)
                    resolved_platform = get_smart_platform_name(llm_group)
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner] 解析的模型配置: 平台={resolved_platform}, 模型={resolved_model}"
                    )
            except Exception as e:
                PrettyOutput.auto_print(
                    f"[c2rust-llm-planner] 警告: 无法验证模型配置: {e}"
                )

            try:
                agent = CodeAgent(
                    need_summary=False,
                    non_interactive=non_interactive,
                    model_group=llm_group,
                    enable_task_list_manager=False,
                    disable_review=True,
                )
                # 验证 agent 内部的模型配置
                if hasattr(agent, "model") and agent.model:
                    actual_model = getattr(agent.model, "model_name", "unknown")
                    actual_platform = type(agent.model).__name__
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner] CodeAgent 内部模型: {actual_platform}.{actual_model}"
                    )
                agent.run(requirement_text, prefix="[c2rust-llm-planner]", suffix="")
                PrettyOutput.auto_print(
                    "[c2rust-llm-planner] 初始 CodeAgent 运行完成。"
                )
            except Exception as e:
                error_msg = str(e)
                if "does not exist" in error_msg or "404" in error_msg:
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner] 模型配置错误: {error_msg}"
                    )
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner] 提示: 请检查模型组 '{llm_group}' 的配置是否正确"
                    )
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner] 当前工作目录: {os.getcwd()}"
                    )
                    # 尝试显示当前解析的模型配置（CodeAgent 使用 smart 模型）
                    try:
                        from jarvis.jarvis_utils.config import get_smart_model_name
                        from jarvis.jarvis_utils.config import get_smart_platform_name

                        if llm_group:
                            PrettyOutput.auto_print(
                                f"[c2rust-llm-planner] 当前解析的模型: {get_smart_platform_name(llm_group)}/{get_smart_model_name(llm_group)}"
                            )
                    except Exception:
                        pass
                raise

            # 进入构建与修复循环：构建失败则生成新的 CodeAgent，携带错误上下文进行最小修复
            iter_count = 0
            while True:
                iter_count += 1
                PrettyOutput.auto_print(
                    f"[c2rust-llm-planner] 在 {os.getcwd()} 执行: cargo build -q"
                )
                build_res = subprocess.run(
                    ["cargo", "build", "-q"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                stdout = build_res.stdout or ""
                stderr = build_res.stderr or ""
                output = (stdout + "\n" + stderr).strip()

                if build_res.returncode == 0:
                    PrettyOutput.auto_print("[c2rust-llm-planner] Cargo 构建成功。")
                    break

                PrettyOutput.auto_print(
                    f"[c2rust-llm-planner] Cargo 构建失败 (iter={iter_count})。"
                )
                # 打印编译错误输出，便于可视化与调试
                PrettyOutput.auto_print("[c2rust-llm-planner] 构建错误输出:")
                PrettyOutput.auto_print(output)
                # 将错误信息作为上下文，附加修复原则，生成新的 CodeAgent 进行最小修复
                repair_prompt = "\n".join(
                    [
                        requirement_text,
                        "",
                        "请根据以下构建错误进行最小化修复，然后再次执行 `cargo build` 验证：",
                        "<BUILD_ERROR>",
                        output,
                        "</BUILD_ERROR>",
                    ]
                )

                if llm_group:
                    PrettyOutput.auto_print(
                        f"[c2rust-llm-planner][iter={iter_count}] 使用模型组: {llm_group}"
                    )
                try:
                    repair_agent = CodeAgent(
                        need_summary=False,
                        non_interactive=non_interactive,
                        model_group=llm_group,
                        enable_task_list_manager=False,
                        disable_review=True,
                    )
                    repair_agent.run(
                        repair_prompt,
                        prefix=f"[c2rust-llm-planner][iter={iter_count}]",
                        suffix="",
                    )
                except Exception as e:
                    error_msg = str(e)
                    if "does not exist" in error_msg or "404" in error_msg:
                        PrettyOutput.auto_print(
                            f"[c2rust-llm-planner][iter={iter_count}] 模型配置错误: {error_msg}"
                        )
                        PrettyOutput.auto_print(
                            f"[c2rust-llm-planner][iter={iter_count}] 提示: 请检查模型组 '{llm_group}' 的配置"
                        )
                    raise
                # 不切换目录，保持在原始工作目录
        finally:
            # 恢复之前的工作目录
            os.chdir(prev_cwd)

    # 3) 输出 JSON 到文件（如指定），并返回解析后的 entries
    if out is not None:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # 使用原始文本写出，便于可读
        out_path.write_text(json_text, encoding="utf-8")
        PrettyOutput.auto_print(f"[c2rust-llm-planner] JSON 已写入: {out_path}")

    return entries
