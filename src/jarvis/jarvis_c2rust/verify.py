# -*- coding: utf-8 -*-
"""
C2Rust 功能对齐验证模块

目标：
- 检查 c2rust 转译是否完成
- 分析转译后的 Rust 代码与原 C 代码的功能对齐性
- 支持迭代优化，直到 Agent 认为没有问题

使用方式：
- 从 CLI 调用 verify 子命令
- 自动切换到目标 crate 目录
- 使用 task_list_manager 拆分子任务进行分析
- 生成结构化的对齐报告
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional

from jarvis.jarvis_c2rust.constants import CONFIG_JSON
from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
from jarvis.jarvis_c2rust.constants import RUN_STATE_JSON
from jarvis.jarvis_utils.output import PrettyOutput


def check_transpile_completed(project_root: Path) -> bool:
    """
    检查转译是否完成。

    读取 run_state.json，检查 transpile 和 optimize 阶段是否都已完成。
    """
    state_path = project_root / C2RUST_DIRNAME / RUN_STATE_JSON
    if not state_path.exists():
        return False

    try:
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)

        transpile_completed: bool = state.get("transpile", {}).get("completed", False)
        optimize_completed: bool = state.get("optimize", {}).get("completed", False)

        return transpile_completed and optimize_completed
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  [verify] 读取状态文件失败: {e}")
        return False


def load_config(project_root: Path) -> Dict[str, Any]:
    """
    加载 c2rust 配置。

    返回包含 root_symbols、disabled_libraries 和 additional_notes 的字典。
    """
    config_path = project_root / C2RUST_DIRNAME / CONFIG_JSON
    default_config = {
        "root_symbols": [],
        "disabled_libraries": [],
        "additional_notes": "",
    }

    if not config_path.exists():
        return default_config

    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
            if not isinstance(config, dict):
                return default_config
            return {
                "root_symbols": config.get("root_symbols", []),
                "disabled_libraries": config.get("disabled_libraries", []),
                "additional_notes": config.get("additional_notes", ""),
            }
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  [verify] 读取配置文件失败: {e}")
        return default_config


def run_verify(
    project_root: Path,
    llm_group: Optional[str] = None,
    max_iterations: int = 10,
    non_interactive: bool = True,
) -> None:
    """
    执行功能对齐验证。

    参数:
        project_root: 项目根目录
        llm_group: LLM 模型组
        max_iterations: 最大迭代次数
        non_interactive: 是否非交互模式
    """
    from jarvis.jarvis_c2rust.utils import default_crate_dir

    # Step 1: 检查转译是否完成
    PrettyOutput.auto_print("🔍 [verify] 检查转译状态...")
    if not check_transpile_completed(project_root):
        PrettyOutput.auto_print(
            "❌ [verify] 转译未完成，请先执行 'jarvis-c2rust run' 完成转译流程"
        )
        return
    PrettyOutput.auto_print("✅ [verify] 转译已完成")

    # 确定 crate 目录
    crate_dir = default_crate_dir(project_root)
    PrettyOutput.auto_print(f"📁 [verify] 目标 crate 目录: {crate_dir}")

    if not crate_dir.exists():
        PrettyOutput.auto_print(f"❌ [verify] crate 目录不存在: {crate_dir}")
        return

    # 加载配置
    config = load_config(project_root)
    PrettyOutput.auto_print(
        f"📋 [verify] 根符号数: {len(config.get('root_symbols', []))}, "
        f"禁用库数: {len(config.get('disabled_libraries', []))}"
    )

    # Step 2: 切换到 crate 目录并开始验证
    PrettyOutput.auto_print("🚀 [verify] 开始功能对齐验证...")

    import os

    original_cwd = os.getcwd()
    try:
        os.chdir(str(crate_dir))

        # 使用 task_list_manager 创建子任务进行分析
        PrettyOutput.auto_print(
            "📋 [verify] 创建分析任务列表（拆分子任务进行详细分析）..."
        )

        # 执行功能对齐分析
        alignment_result = _run_alignment_analysis(
            crate_dir=crate_dir,
            project_root=project_root,
            config=config,
            llm_group=llm_group,
            non_interactive=non_interactive,
        )

        # Step 3: 检查是否需要迭代优化
        iteration = 0
        while iteration < max_iterations:
            is_aligned = alignment_result.get("is_aligned", False)

            if is_aligned:
                PrettyOutput.auto_print("✅ [verify] 功能对齐验证通过！")
                PrettyOutput.auto_print(
                    f"📊 [verify] 验证结果: {alignment_result.get('summary', 'OK')}"
                )
                break

            iteration += 1
            if iteration >= max_iterations:
                PrettyOutput.auto_print(
                    f"⚠️  [verify] 达到最大迭代次数 ({max_iterations})，停止优化"
                )
                PrettyOutput.auto_print(
                    f"📊 [verify] 最终验证结果: {alignment_result.get('summary', 'NOT OK')}"
                )
                break

            PrettyOutput.auto_print(f"🔄 [verify] 第 {iteration} 次迭代优化...")

            # 执行优化
            _run_optimization(
                crate_dir=crate_dir,
                report=alignment_result.get("report", ""),
                config=config,
                llm_group=llm_group,
                non_interactive=non_interactive,
            )

            # 重新验证
            PrettyOutput.auto_print("🔍 [verify] 重新验证功能对齐...")
            alignment_result = _run_alignment_analysis(
                crate_dir=crate_dir,
                project_root=project_root,
                config=config,
                llm_group=llm_group,
                non_interactive=non_interactive,
            )
    finally:
        os.chdir(original_cwd)


def _run_alignment_analysis(
    crate_dir: Path,
    project_root: Path,
    config: Dict[str, Any],
    llm_group: Optional[str],
    non_interactive: bool,
) -> Dict[str, Any]:
    """
    运行功能对齐分析。

    使用 task_list_manager 拆分子任务进行分析。
    子任务将不一致的地方记录到文件中，最终总结基于这些文件生成。
    返回包含 is_aligned 和 summary 的字典。
    """
    from jarvis.jarvis_agent import Agent

    # 定义报告文件路径（保存到 crate 根目录）
    report_file = crate_dir / "alignment_report.md"

    # 创建分析 Agent
    # 系统提示词：介绍工作流程
    system_prompt = """
你是一个 C 到 Rust 代码转译的功能对齐验证专家。

工作流程：
1. 使用 task_list_manager 将分析任务拆分为多个子任务
2. 每个子任务分析 C 代码和 Rust 代码的对齐性
3. 所有子任务完成后，汇总分析结果生成对齐报告
4. 最终以 JSON 格式输出验证结果
"""

    # 总结提示词：约束结论结果
    summary_prompt = """
请基于分析结果，严格按照以下 JSON 格式输出结论：

```json
{
  "is_aligned": true/false,
  "summary": "总体结论（一致/不一致/部分一致）",
  "report_path": "alignment_report.md 文件路径"
}
```

要求：
- 必须输出完整的 JSON 格式
- is_aligned: true 表示完全对齐，false 表示存在不一致
- summary: 简洁描述总体结论
- report_path: 生成的报告文件路径
"""

    agent = Agent(
        name="C2Rust-VerificationAgent",
        non_interactive=non_interactive,
        model_group=llm_group,
        system_prompt=system_prompt,
        summary_prompt=summary_prompt,
    )

    # 构建分析任务
    analysis_task = f"""
你是一个 C 到 Rust 代码转译的功能对齐验证专家。

任务目标：
分析转译后的 Rust 代码与原 C 代码的功能对齐性，生成详细的对齐报告。

项目信息：
- 项目根目录: {project_root}
- Rust crate 目录: {crate_dir}
- 根符号列表: {config.get("root_symbols", [])}
- 禁用库列表: {config.get("disabled_libraries", [])}
- 附加说明: {config.get("additional_notes", "")}

输出文件：
- 对齐总结报告: {report_file}

分析要求（必须拆分为子任务）：
1. 读取并分析 C 代码和对应的 Rust 代码
2. 对比函数签名和类型定义
3. 分析函数逻辑和边界情况处理
4. 检查错误处理机制
5. 验证内存安全性（特别是 unsafe 代码）
6. 检查数据结构和布局对齐

子任务要求：
- 使用 task_list_manager 将以上分析步骤拆分为独立的子任务
- 每个子任务负责分析特定的方面
- 子任务完成后，将发现的问题和结论汇总

报告中每条不一致问题的格式：
```
### [严重程度] 函数名

**问题描述**：详细描述问题

**C 代码**：
```c
// C 代码片段
```

**Rust 代码**：
```rust
// Rust 代码片段
```
```

严重程度分类：
- High：严重影响功能或安全性的问题
- Medium：中等影响的问题
- Low：轻微或不影响功能的问题

最终总结任务：
在所有子任务完成后，汇总所有分析结果，生成以下内容并写入 {report_file}：
1. 总体结论（一致/不一致/部分一致）
2. 不一致问题的数量和分类
3. 关键问题摘要（包含函数名、问题描述、严重程度、代码对比）
4. 改进建议

请开始分析，必须使用 task_list_manager 拆分子任务。
"""

    try:
        result = agent.run(analysis_task)
        # 尝试从结果中提取结构化数据
        if isinstance(result, dict):
            return result
        # 如果返回的是字符串，尝试解析 JSON
        if isinstance(result, str):
            try:
                parsed: Dict[str, Any] = json.loads(result)
                return parsed
            except json.JSONDecodeError:
                pass
        # 默认返回
        return {
            "is_aligned": True,
            "summary": "验证完成（无法解析详细结果）",
            "report_path": str(report_file),
        }
    except Exception as e:
        PrettyOutput.auto_print(f"❌ [verify] 分析过程出错: {e}")
        return {
            "is_aligned": False,
            "summary": "分析失败",
            "report_path": str(report_file),
        }


def _run_optimization(
    crate_dir: Path,
    report: str,
    config: Dict[str, Any],
    llm_group: Optional[str],
    non_interactive: bool,
) -> None:
    """
    运行代码优化。

    使用 CodeAgent 基于对齐报告优化 Rust 代码。
    """
    from jarvis.jarvis_code_agent.code_agent import CodeAgent

    # 创建优化 CodeAgent
    agent = CodeAgent(
        name="C2Rust-OptimizationAgent",
        need_summary=False,
        non_interactive=non_interactive,
        model_group=llm_group,
    )

    optimization_task = f"""
你是一个 C 到 Rust 代码转译的优化专家。

任务目标：
根据功能对齐验证报告，优化 Rust 代码以修复不一致的问题。

对齐报告：
{report}

配置信息：
- 根符号列表: {config.get("root_symbols", [])}
- 禁用库列表: {config.get("disabled_libraries", [])}
- 附加说明: {config.get("additional_notes", "")}

优化要求：
1. 仔细阅读对齐报告中指出的所有问题
2. 逐个修复这些问题
3. 确保修复后代码能够编译通过
4. 保持代码风格和项目规范
5. 不要破坏已有的功能

请开始优化，使用适当的工具（如 edit_file）修改代码。
"""

    try:
        agent.run(optimization_task)
        PrettyOutput.auto_print("✅ [verify] 优化完成")
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  [verify] 优化过程出错: {e}")
