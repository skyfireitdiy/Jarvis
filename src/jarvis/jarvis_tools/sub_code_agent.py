# -*- coding: utf-8 -*-
"""
sub_code_agent 工具
将子任务交给 CodeAgent 执行，并返回执行结果。

约定：
- 必填参数：task
- 可选参数：background
- 不依赖父 Agent，所有配置使用系统默认与全局变量
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""

from typing import Any, Dict, List

from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_utils.globals import get_global_model_group


class SubCodeAgentTool:
    """
    使用 CodeAgent 托管执行子任务，执行完立即清理 CodeAgent 实例。
    - 不注册至全局
    - 使用系统默认/全局配置
    - 启用自动完成与总结
    """

    # 必须与文件名一致，供 ToolRegistry 自动注册
    name = "sub_code_agent"
    description = "将子任务交给 CodeAgent 执行并返回结果（自动完成并生成总结）。"
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要执行的子任务内容（必填）",
            },
            "background": {
                "type": "string",
                "description": "任务背景与已知信息（可选，将与任务一并提供给子Agent）",
            },
            "name": {
                "type": "string",
                "description": "子Agent的名称（可选，用于标识和区分不同的子Agent）",
            },
        },
        "required": ["task"],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行代码子任务并返回结果（由 CodeAgent 托管执行）。
        返回:
          - success: 是否成功
          - stdout: CodeAgent 执行结果（字符串；若为 None 则返回“任务执行完成”）
          - stderr: 错误信息（如有）
        """
        try:
            task: str = str(args.get("task", "")).strip()
            if not task:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "task 不能为空",
                }

            # 读取背景信息并组合任务
            background: str = str(args.get("background", "")).strip()
            enhanced_task = (
                f"背景信息:\n{background}\n\n任务:\n{task}" if background else task
            )

            # 读取子Agent名称（可选）
            agent_name: str = str(args.get("name", "")).strip()

            # 继承父Agent的模型组与工具使用集（用于覆盖默认值）
            parent_agent = args.get("agent")
            # 如未注入父Agent，尝试从全局获取当前或任一已注册Agent
            if parent_agent is None:
                try:
                    from jarvis.jarvis_utils import globals as G  # 延迟导入避免循环

                    curr = G.get_current_agent_name()
                    if curr:
                        parent_agent = getattr(G, "global_agents", {}).get(curr)
                    if parent_agent is None and getattr(G, "global_agents", {}):
                        try:
                            parent_agent = next(iter(G.global_agents.values()))
                        except Exception:
                            parent_agent = None
                except Exception:
                    parent_agent = None
            (
                getattr(parent_agent, "non_interactive", None)
                if parent_agent is not None
                else None
            )
            # 使用全局模型组（不再从 parent_agent 继承）
            model_group = get_global_model_group()
            use_tools: List[str] = []
            try:
                if parent_agent is not None:
                    parent_registry = parent_agent.get_tool_registry()
                    if parent_registry:
                        for t in parent_registry.get_all_tools():
                            if isinstance(t, dict) and t.get("name"):
                                use_tools.append(str(t["name"]))
            except Exception:
                pass

            # 创建 CodeAgent：参数优先使用父Agent的配置（若可获取），否则使用默认
            # 推断/继承 tool_group
            tool_group = None
            try:
                if parent_agent is not None:
                    tool_group = getattr(parent_agent, "tool_group", tool_group)
            except Exception:
                pass

            # 依据父Agent已启用工具集，推导 append_tools（作为在 CodeAgent 基础工具上的增量）
            # 禁用 sub_agent 和 sub_code_agent，避免无限递归
            forbidden_tools = {"sub_agent", "sub_code_agent"}
            append_tools = None
            try:
                base_tools = [
                    "execute_script",
                    "read_code",
                    "edit_file",
                ]
                if use_tools:
                    # 过滤掉基础工具和禁止的工具
                    extras = [
                        t
                        for t in use_tools
                        if t not in base_tools and t not in forbidden_tools
                    ]
                    append_tools = ",".join(extras) if extras else None
            except Exception:
                append_tools = None

            # 获取父代理的规则名称列表用于继承
            rule_names = None
            try:
                if parent_agent is not None and hasattr(
                    parent_agent, "loaded_rule_names"
                ):
                    parent_rules = getattr(parent_agent, "loaded_rule_names", [])
                    if parent_rules:
                        rule_names = ",".join(parent_rules)
            except Exception:
                rule_names = None

            # 从父代理继承disable_review配置
            disable_review = False
            try:
                if parent_agent is not None and hasattr(parent_agent, "disable_review"):
                    disable_review = getattr(parent_agent, "disable_review", False)
            except Exception:
                disable_review = False

            # 创建 CodeAgent，捕获 SystemExit 异常（如 git 配置不完整）
            try:
                code_agent = CodeAgent(
                    name=agent_name,
                    model_group=model_group,
                    need_summary=True,
                    append_tools=append_tools,
                    tool_group=tool_group,
                    non_interactive=True,
                    rule_names=rule_names,
                    disable_review=disable_review,
                    auto_complete=True,
                )
            except SystemExit as se:
                # 将底层 sys.exit 转换为工具错误，避免终止进程
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"初始化 CodeAgent 失败（可能未配置 git 或当前非 git 仓库）: {se}",
                }

            # 子Agent需要自动完成
            try:
                # 同步父Agent工具使用集（如可用），但禁用 sub_agent 和 sub_code_agent 避免无限递归
                if use_tools:
                    forbidden_tools = {"sub_agent", "sub_code_agent"}
                    filtered_tools = [t for t in use_tools if t not in forbidden_tools]
                    if filtered_tools:
                        code_agent.set_use_tools(filtered_tools)
                # 不再从父Agent获取模型名，使用系统默认配置（符合"不依赖父 Agent"的约定）
            except Exception:
                pass

            # 执行子任务（无提交信息前后缀）
            ret = code_agent.run(enhanced_task, prefix="", suffix="")

            return {
                "success": True,
                "stdout": ret,
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行子任务失败: {str(e)}",
            }
