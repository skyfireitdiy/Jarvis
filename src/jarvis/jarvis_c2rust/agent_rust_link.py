from __future__ import annotations

from typing import Optional

from jarvis.jarvis_agent import Agent


def create_rust_link_agent(
    model_group: Optional[str] = None, non_interactive: Optional[bool] = True
) -> Agent:
    """创建一个 Agent，将 .jarvis/c2rust 下的 Rust staticlib 链接进 C/C++测试进程。"""
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


