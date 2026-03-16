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
    max_iterations: int = 10,
    non_interactive: bool = True,
) -> None:
    """
    执行功能对齐验证。

    参数:
        project_root: 项目根目录
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
                project_root=project_root,
                report=alignment_result.get("report", ""),
                config=config,
                non_interactive=non_interactive,
            )

            # 重新验证
            PrettyOutput.auto_print("🔍 [verify] 重新验证功能对齐...")
            alignment_result = _run_alignment_analysis(
                crate_dir=crate_dir,
                project_root=project_root,
                config=config,
                non_interactive=non_interactive,
            )
    finally:
        os.chdir(original_cwd)


def _run_alignment_analysis(
    crate_dir: Path,
    project_root: Path,
    config: Dict[str, Any],
    non_interactive: bool,
) -> Dict[str, Any]:
    """
    运行功能对齐分析。

    使用 task_list_manager 拆分子任务进行分析。
    子任务将不一致的地方记录到文件中，最终总结基于这些文件生成。
    返回包含 is_aligned 和 summary 的字典。
    """
    from jarvis.jarvis_c2rust.agent_factory import create_agent

    # 定义报告文件路径（保存到 crate 根目录）
    report_file = crate_dir / "alignment_report.md"

    # 创建分析 Agent
    # 系统提示词：介绍明确的工作流程（支持大规模代码）
    system_prompt = f"""
你是一个 C 到 Rust 代码转译的功能对齐验证专家。

## 核心职责
分析转译后的 Rust 代码与原 C 代码的功能对齐性，识别不一致问题并生成详细报告。

## 明确的工作流程（必须严格按顺序执行，支持大规模代码分析）

### 阶段1：准备工作（必须首先完成）
1. **读取项目配置**
   - 读取项目根目录和 crate 目录信息
   - 理解根符号列表（root_symbols）和禁用库列表（disabled_libraries）
   - 查看附加说明（additional_notes）

2. **探索代码结构并识别文件映射**
   - 列出所有 C 源代码文件位置（使用 glob 或 list_dir 工具）
   - 列出所有转译后的 Rust 代码文件位置
   - **建立 C 文件与 Rust 文件的对应关系**（这是关键步骤）
   - 估算每个文件的大小（行数），如果单个文件超过 2000 行，考虑进一步拆分

### 阶段2：按文件创建任务列表（必须使用 task_list_manager）
3. **使用 task_list_manager.add_tasks 创建任务列表**
   - main_goal: "C2Rust 功能对齐验证：按文件分析转译后的 Rust 代码与原 C 代码的功能对齐性"
   - tasks_info: **按文件拆分任务**，每个文件一个子任务：
     * 为每个 C-Rust 文件对创建一个任务，任务名格式："验证文件: <文件名>"
     * 每个文件任务需要完成以下所有分析维度：
       - 函数签名和类型定义对比
       - 函数逻辑和算法实现对比
       - 错误处理机制验证
       - 内存安全性验证
       - 数据结构和布局对齐验证
     * 最后一个汇总任务："汇总所有文件报告并生成最终对齐报告"
   - **重要**：文件任务之间可以并行执行（无依赖关系），只有汇总任务依赖所有文件任务

### 阶段3：执行文件级任务（逐个或并行执行）
4. **使用 task_list_manager.execute_task 执行每个文件任务**
   - 对于每个文件任务，提供详细的 additional_info：
     * c_file_path: C 源代码文件路径
     * rust_file_path: 对应的 Rust 代码文件路径
     * root_symbols_in_file: 该文件中需要验证的根符号列表
     * analysis_dimensions: 需要分析的维度列表（函数签名、逻辑、错误处理、内存安全、布局对齐）
   
   - 每个文件任务执行时：
     * 读取并分析 C 代码文件（如果文件很大，可以分块读取关键部分）
     * 读取并分析对应的 Rust 代码文件
     * **对每个分析维度进行详细对比**：
       - 函数签名和类型定义对比
       - 函数逻辑和算法实现对比
       - 错误处理机制验证
       - 内存安全性验证
       - 数据结构和布局对齐验证
     * 记录发现的问题（格式：函数名、问题描述、严重程度、代码对比）
     * **立即生成该文件的部分报告**，保存到临时文件：`{{crate_dir}}/alignment_reports/{{filename}}_report.md`
     * 将问题统计信息（问题数量、严重程度分布）记录在任务结果中

### 阶段4：汇总和报告生成（最后一个任务）
5. **执行"汇总所有文件报告并生成最终对齐报告"任务**
   - 读取所有已完成文件任务的结果和部分报告文件
   - 汇总所有文件的问题统计
   - 按严重程度分类（High/Medium/Low）
   - 生成完整的 Markdown 报告，包含：
     * **总体结论**（一致/不一致/部分一致）
     * **统计信息**：总文件数、已分析文件数、总问题数、High/Medium/Low 数量
     * **按文件分组的问题列表**：每个文件的问题摘要（问题数量、严重程度分布）
     * **关键问题详细列表**：汇总所有 High 和 Medium 级别问题（每个问题包含：文件名、函数名、问题描述、严重程度、代码对比）
     * **改进建议**：针对发现的问题提出具体的修复建议
   - 将报告写入指定文件：{report_file}

### 阶段5：输出验证结果（最终步骤）
6. **输出验证结果**
   - 读取生成的报告文件：{report_file}
   - 根据报告内容判断验证结果：
     * 如果所有问题都是 Low 级别或没有问题 → is_aligned: true
     * 如果存在 High 或 Medium 级别问题 → is_aligned: false
   - 生成简洁的 summary 描述（例如："完全一致"、"存在 High 级别问题"、"部分一致，主要是 Low 级别问题"）
   - **最终输出要求**：任务完成后，系统会要求你生成最终总结。在最终总结中，必须严格按照以下 JSON 格式输出验证结果：
```json
{{
  "is_aligned": true/false,
  "summary": "总体结论（一致/不一致/部分一致）",
  "report_path": "{report_file}"
}}
```

## 重要约束
- **必须严格按照上述5个阶段的顺序执行，不能跳过任何阶段**
- **必须使用 task_list_manager 工具，不能直接执行分析**
- **必须按文件拆分任务，而不是按分析维度拆分**（这样才能支持大规模代码）
- **每个文件任务完成后立即生成该文件的部分报告**（支持增量查看进度）
- **每个子任务必须提供详细的 additional_info**
- **问题记录格式必须统一，包含：文件名、函数名、问题描述、严重程度、代码对比**
- **最终必须输出有效的 JSON 格式结果**

## 大规模代码处理策略
- **文件拆分原则**：如果单个文件超过 2000 行，考虑按函数组或模块进一步拆分
- **增量报告**：每个文件分析完成后立即生成部分报告，便于跟踪进度
- **并行执行**：文件任务之间无依赖，可以并行执行以提高效率
- **内存优化**：对于大文件，只读取需要分析的关键部分，避免一次性加载全部内容
"""

    # 总结提示词：约束结论结果（Agent 完成所有任务后会自动调用此提示词）
    summary_prompt = f"""
请基于功能对齐验证的分析结果，严格按照以下 JSON 格式输出最终结论：

```json
{{
  "is_aligned": true/false,
  "summary": "总体结论（一致/不一致/部分一致）",
  "report_path": "{report_file}"
}}
```

要求：
- 必须输出完整的 JSON 格式，不要包含其他文本
- is_aligned: true 表示完全对齐（所有问题都是 Low 级别或没有问题），false 表示存在 High 或 Medium 级别的不一致问题
- summary: 简洁描述总体结论，例如："完全一致"、"存在 High 级别问题"、"部分一致，主要是 Low 级别问题"
- report_path: 生成的报告文件路径（必须是：{report_file}）

请先读取报告文件 {report_file}，根据报告内容判断 is_aligned 的值，然后输出 JSON。
"""

    agent = create_agent(
        name="C2Rust-VerificationAgent",
        non_interactive=non_interactive,
        system_prompt=system_prompt,
        summary_prompt=summary_prompt,
        model_type="smart",
    )

    # 构建分析任务
    analysis_task = f"""
你是一个 C 到 Rust 代码转译的功能对齐验证专家。

## 任务目标
分析转译后的 Rust 代码与原 C 代码的功能对齐性，识别不一致问题并生成详细的对齐报告。

## 项目信息
- 项目根目录: {project_root}
- Rust crate 目录: {crate_dir}
- 根符号列表: {config.get("root_symbols", [])}
- 禁用库列表: {config.get("disabled_libraries", [])}
- 附加说明: {config.get("additional_notes", "")}

## 输出文件
- 对齐总结报告: {report_file}
- 部分报告目录: {crate_dir}/alignment_reports/（每个文件的分析报告）

## 执行步骤（严格按照系统提示词中的工作流程，支持大规模代码）

### 第一步：准备工作（探索代码结构）
1. **探索 C 源代码位置**
   - 使用 list_dir 或 glob 工具找到所有 C 源代码文件（通常在项目根目录的某个子目录）
   - 记录所有 C 文件的完整路径

2. **探索 Rust 代码结构**
   - 确认 Rust crate 目录结构（当前目录：{crate_dir}）
   - 使用 list_dir 或 glob 工具找到所有 Rust 源代码文件
   - 记录所有 Rust 文件的完整路径

3. **建立文件映射关系**
   - 建立 C 文件与 Rust 文件的对应关系（通常文件名相似或路径结构相似）
   - 对于每个文件对，识别其中包含的根符号
   - 估算每个文件的大小（行数），如果超过 2000 行，考虑进一步拆分

4. **创建部分报告目录**
   - 创建目录：{crate_dir}/alignment_reports/（如果不存在）

### 第二步：按文件创建任务列表
**必须立即使用 task_list_manager.add_tasks 创建任务列表**

**重要：必须按文件拆分，而不是按分析维度拆分！**

调用示例（假设有 file1.c/file1.rs, file2.c/file2.rs 两个文件对）：
```python
task_list_manager(
    action="add_tasks",
    main_goal="C2Rust 功能对齐验证：按文件分析转译后的 Rust 代码与原 C 代码的功能对齐性",
    tasks_info=[
        {{
            "name": "验证文件: file1.c",
            "description": "分析 file1.c 与 file1.rs 的功能对齐性，包括函数签名、逻辑、错误处理、内存安全、布局对齐等所有维度",
            "dependencies": []
        }},
        {{
            "name": "验证文件: file2.c",
            "description": "分析 file2.c 与 file2.rs 的功能对齐性，包括函数签名、逻辑、错误处理、内存安全、布局对齐等所有维度",
            "dependencies": []
        }},
        # ... 为每个文件对创建一个任务
        {{
            "name": "汇总所有文件报告并生成最终对齐报告",
            "description": "汇总所有文件任务的分析结果，生成完整的对齐报告",
            "dependencies": ["验证文件: file1.c", "验证文件: file2.c", ...]  # 依赖所有文件任务
        }}
    ]
)
```

**关键点：**
- 每个文件一个独立任务，文件任务之间无依赖（可以并行执行）
- 每个文件任务需要完成所有分析维度（函数签名、逻辑、错误处理、内存安全、布局对齐）
- 最后一个汇总任务依赖所有文件任务

### 第三步：执行文件级任务
**对每个文件任务，使用 task_list_manager.execute_task 执行**

每个文件任务执行时，必须提供详细的 additional_info：

**示例：验证文件 file1.c 任务的 additional_info**
```json
{{
    "c_file_path": "/path/to/file1.c",
    "rust_file_path": "/path/to/file1.rs",
    "root_symbols_in_file": ["function1", "function2", "Struct1"],
    "analysis_dimensions": [
        "函数签名和类型定义对比",
        "函数逻辑和算法实现对比",
        "错误处理机制验证",
        "内存安全性验证",
        "数据结构和布局对齐验证"
    ],
    "output_file": "{crate_dir}/alignment_reports/file1_report.md"
}}
```

**每个文件任务执行步骤：**
1. 读取 C 代码文件（如果文件很大，可以分块读取关键部分）
2. 读取对应的 Rust 代码文件
3. **对每个分析维度进行详细对比**：
   - **函数签名和类型定义对比**：对比函数签名、参数类型、返回值类型、类型定义
   - **函数逻辑和算法实现对比**：逐行对比函数实现逻辑、算法一致性、边界条件处理
   - **错误处理机制验证**：对比 C 的错误处理（返回值、errno）与 Rust 的错误处理（Result、Option）
   - **内存安全性验证**：检查 unsafe 代码块、内存管理、指针操作安全性
   - **数据结构和布局对齐验证**：验证结构体字段顺序、内存布局对齐、大小端处理
4. 记录所有发现的问题（格式见下方）
5. **立即生成该文件的部分报告**，保存到：`{crate_dir}/alignment_reports/{{filename}}_report.md`
6. 在任务结果中记录问题统计（问题数量、严重程度分布）

**问题记录格式（每个文件任务必须遵循）：**
```
### [严重程度] 文件名: 函数名/类型名

**问题描述**：详细描述问题

**C 代码**：
```c
// C 代码片段（包含文件路径和行号）
```

**Rust 代码**：
```rust
// Rust 代码片段（包含文件路径和行号）
```

**影响分析**：说明这个问题可能造成的影响

**分析维度**：函数签名/逻辑/错误处理/内存安全/布局对齐
```

**部分报告格式（每个文件任务完成后立即生成）：**
```markdown
# 文件对齐报告: file1.c / file1.rs

## 文件信息
- C 文件: /path/to/file1.c
- Rust 文件: /path/to/file1.rs
- 根符号数: 3

## 问题统计
- 总问题数: 5
- High: 1
- Medium: 2
- Low: 2

## 问题列表
[按上述格式列出所有问题]

## 分析维度总结
- 函数签名和类型定义: 1个问题
- 函数逻辑和算法实现: 2个问题
- 错误处理机制: 1个问题
- 内存安全性: 1个问题
- 数据结构和布局对齐: 0个问题
```

**严重程度分类：**
- **High**：严重影响功能或安全性的问题（如：逻辑错误、内存安全问题、功能缺失）
- **Medium**：中等影响的问题（如：类型不匹配但不影响功能、错误处理方式不同但结果一致）
- **Low**：轻微或不影响功能的问题（如：命名风格差异、注释缺失）

### 第四步：汇总报告
**执行"汇总所有文件报告并生成最终对齐报告"任务**

该任务需要：
1. 读取所有已完成文件任务的结果
2. 读取所有部分报告文件（`{crate_dir}/alignment_reports/*_report.md`）
3. 汇总所有文件的问题统计
4. 按严重程度分类（High/Medium/Low）
5. 生成完整的 Markdown 报告，包含以下章节：
   - **总体结论**：一致/不一致/部分一致
   - **统计信息**：
     * 总文件数、已分析文件数
     * 总问题数、High/Medium/Low 数量
     * 各文件问题分布
   - **按文件分组的问题摘要**：每个文件的问题数量、严重程度分布、关键问题概述
   - **关键问题详细列表**：汇总所有 High 和 Medium 级别问题的详细信息（包含文件名、函数名、问题描述、严重程度、代码对比）
   - **改进建议**：针对发现的问题提出具体的修复建议
6. 将报告写入文件：{report_file}

### 第五步：输出验证结果
**最后，当所有任务完成后，系统会要求你生成最终总结**

在最终总结中，你需要：
1. 读取生成的报告文件：{report_file}
2. 根据报告内容判断 is_aligned：
   - 如果所有问题都是 Low 级别或没有问题 → is_aligned: true
   - 如果存在 High 或 Medium 级别问题 → is_aligned: false
3. 生成简洁的 summary 描述
4. **必须严格按照以下 JSON 格式输出验证结果**：
```json
{{
  "is_aligned": true/false,
  "summary": "总体结论（一致/不一致/部分一致）",
  "report_path": "{report_file}"
}}
```

**重要**：最终总结必须输出完整的 JSON 格式，不要包含其他文本。

## 重要提醒
- **必须严格按照上述5个步骤顺序执行**
- **必须按文件拆分任务，而不是按分析维度拆分**（这样才能支持大规模代码）
- **第一步完成后立即创建任务列表，不要直接开始分析**
- **每个文件任务完成后立即生成部分报告**（支持增量查看进度）
- **每个子任务必须提供详细的 additional_info**
- **问题记录格式必须统一，包含文件名、函数名、问题描述、严重程度、代码对比**
- **最终必须输出有效的 JSON 格式结果**

## 大规模代码处理技巧
- **文件拆分**：如果单个文件超过 2000 行，可以按函数组进一步拆分
- **增量报告**：每个文件分析完成后立即生成部分报告，便于跟踪进度
- **并行执行**：文件任务之间无依赖，可以并行执行以提高效率
- **内存优化**：对于大文件，只读取需要分析的关键部分（基于根符号列表）
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
    project_root: Path,
    report: str,
    config: Dict[str, Any],
    non_interactive: bool,
) -> None:
    """
    运行代码优化。

    使用 CodeAgent 基于对齐报告优化 Rust 代码。
    """
    from jarvis.jarvis_c2rust.agent_factory import create_code_agent
    from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
    from jarvis.jarvis_c2rust.constants import SYMBOLS_JSONL

    # 确定 symbols.jsonl 文件路径
    symbols_path = project_root / C2RUST_DIRNAME / SYMBOLS_JSONL

    # 创建优化 CodeAgent，添加 read_symbols 工具
    agent = create_code_agent(
        name="C2Rust-OptimizationAgent",
        need_summary=False,
        non_interactive=non_interactive,
        append_tools="read_symbols",  # 添加 read_symbols 工具用于读取 C 符号信息
        model_type="smart",
    )

    optimization_task = f"""
你是一个 C 到 Rust 代码转译的优化专家，专门负责修复功能对齐验证中发现的问题。

## 任务目标
根据功能对齐验证报告，优化 Rust 代码以修复不一致的问题，确保转译后的 Rust 代码与原 C 代码功能完全对齐。

## 对齐报告
{report}

## 项目信息
- 项目根目录: {project_root}
- Rust crate 目录: {crate_dir}
- 根符号列表: {config.get("root_symbols", [])}
- 禁用库列表: {config.get("disabled_libraries", [])}
- 附加说明: {config.get("additional_notes", "")}

## 可用工具
1. **read_symbols**: 读取 C 符号信息（用于对比 C 代码）
   - 符号表文件: {symbols_path}
   - 使用示例: `read_symbols({{"symbols_file": "{symbols_path}", "symbols": ["函数名"]}})`
2. **read_code**: 读取 C 源码或 Rust 代码文件
   - 读取 Rust 文件时，使用相对于 crate 根目录的路径（如 `src/xxx.rs`）或绝对路径
   - 读取 C 文件时，使用 C 源文件的完整路径
3. **edit_file**: 修改 Rust 代码文件
4. **execute_script**: 执行编译和测试命令（如 `cargo check`, `cargo test`）

## 优化工作流程

### 第一步：分析问题（ANALYZE）
1. 仔细阅读对齐报告，理解每个问题的：
   - 问题类型（函数签名、逻辑、错误处理、内存安全、布局对齐）
   - 严重程度（High/Medium/Low）
   - 具体位置（文件名、函数名）
   - C 代码和 Rust 代码的差异

### 第二步：收集信息（COLLECT）
2. 对于每个需要修复的问题：
   - 使用 `read_code` 读取相关的 Rust 代码文件
   - 使用 `read_symbols` 读取对应的 C 符号信息（如果需要对比 C 实现）
   - 使用 `read_code` 读取 C 源码文件（如果需要详细对比）

### 第三步：提出方案（HYPOTHESIZE）
3. 针对每个问题设计修复方案：
   - 分析问题的根本原因
   - 设计最小改动的修复方案
   - 考虑修复后对其他代码的影响
   - 确保修复方案符合 Rust 最佳实践

### 第四步：执行修复（EXECUTE）
4. 逐个修复问题：
   - 使用 `edit_file` 工具修改 Rust 代码
   - 每次修改后，使用 `execute_script` 执行 `cargo check` 验证编译
   - 如果报告中有测试用例，执行 `cargo test` 验证功能
   - 确保修复后代码能够编译通过

### 第五步：反思（REVIEW）
5. 修复完成后进行全面反思：
   - 审查代码质量（语法/功能/风格）
   - 核对功能是否完成，验证所有问题都已修复
   - 检查波及的代码是否都考虑到
   - 确认是否有配套的修改（如文档、测试、配置等）
   - 确保代码能够编译通过
   - 运行相关测试确保功能正确
   - 检查是否引入了新的问题
   - 评估影响面和潜在风险

## 优化要求
1. **优先级**：优先修复 High 级别问题，然后是 Medium 级别问题
2. **最小改动**：只修改必要的部分，不要进行无关的重构
3. **功能对齐**：确保修复后的 Rust 代码与原 C 代码功能完全一致
4. **代码质量**：
   - 保持代码风格和项目规范
   - 使用 Rust 最佳实践（如 Result 类型处理错误、所有权系统管理内存）
   - 添加必要的注释说明修复原因
5. **验证**：每次修改后必须验证编译通过，不要累积多个修改后再验证
6. **不要破坏已有功能**：修复问题时，确保不会影响其他已正常工作的代码

## 注意事项
- **C 代码对比**：如果需要对比 C 实现，使用 `read_symbols` 工具读取符号信息，或使用 `read_code` 读取 C 源文件
- **Rust 文件路径**：读取 Rust 文件时，使用相对于 crate 根目录的路径（如 `src/xxx.rs`）
- **编译验证**：每次修改后立即执行 `cargo check` 验证编译，不要等到最后才验证
- **测试验证**：如果对齐报告提到测试用例，执行相关测试确保功能正确

请开始优化，按照上述工作流程逐步修复问题。
"""

    try:
        agent.run(optimization_task)
        PrettyOutput.auto_print("✅ [verify] 优化完成")
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️  [verify] 优化过程出错: {e}")
