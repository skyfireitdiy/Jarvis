from __future__ import annotations

from typing import Optional

from jarvis.jarvis_agent import Agent


def _default_system_prompt() -> str:
    return (
        """
<role>
你是一个资深C/C++构建与测试工程师，负责：
1) 识别当前仓库的构建系统与已有测试方式；
2) 推导出一条稳定的测试运行命令；
3) 若仓库没有测试，创建一个基于 gtest + mockcpp 的最小可运行示例（不影响现有源码）；
4) 生成一个可直接运行测试的一键脚本 .jarvis/c2rust/test_c.sh（无交互、幂等）。
</role>

<requirements>
- 仅使用必要最小变更；不要破坏现有构建。
- 优先探测已有脚本（如 scripts/test.sh、Makefile 的 test 目标、ctest、meson test、bazel test 等）。
- 如果需要引入依赖：优先使用系统包管理器安装或在脚本内检测并提示；不要在项目根目录写入大量第三方代码。
- 一键脚本必须可重复执行，包含：构建、运行测试、输出报告（如 junit 或文本）。
- 若未检测到任何构建系统，默认使用 CMake 组织最小测试骨架与运行流程。
- 严禁自动生成任何测试用例文件；仅搭建“测试框架/配置”，不创建示例测试。
- 若需创建测试框架：
  - 新建目录 tests/，并编写最小构建/配置（CMakeLists.txt 或 Makefile 二选一，按仓库既有体系择优）；
  - 允许引入 gtest/mockcpp 的依赖配置，但不要添加任何测试源文件；
  - 不修改现有源码，仅新增测试框架与配置。
- 将最终测试命令与依赖安装指引写入 .jarvis/c2rust/test_c.sh。
</requirements>

<steps>
1) 扫描仓库结构与常见构建系统文件；
2) 判定测试存在与否；
3) 给出可执行的测试命令行；
4) 若缺失测试：新增最小 gtest 结构并给出构建与运行命令；
5) 生成/覆写 .jarvis/c2rust/test_c.sh（bash），确保可执行；
6) 输出脚本的相对路径与用法。
</steps>

请严格输出所需的文件编辑与脚本生成操作。
"""
    ).strip()


def create_c_test_agent(
    model_group: Optional[str] = None, non_interactive: Optional[bool] = True
) -> Agent:
    """创建一个专用 Agent 来探测/搭建 C/C++ 测试并生成运行脚本。

    - 使用通用工具：execute_script, read_code, ask_user, save_memory, retrieve_memory, clear_memory
    - 禁用方法论/分析，简化交互
    - 非交互模式默认开启
    """
    system_prompt = _default_system_prompt()
    agent = Agent(
        system_prompt=system_prompt,
        name="C2Rust-CTest-Agent",
        auto_complete=True,
        model_group=model_group,
        need_summary=False,
        use_methodology=False,
        use_analysis=False,
        non_interactive=bool(non_interactive),
        agent_type="code",  # 复用 CodeAgent 的工具链与输入处理
    )
    # 精简工具集（CodeAgent 默认包含子集，这里按需设置）
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
        # 容错：如果设置失败，沿用默认
        pass
    return agent


