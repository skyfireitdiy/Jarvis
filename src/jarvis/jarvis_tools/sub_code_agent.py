# -*- coding: utf-8 -*-
"""
sub_code_agent 工具
将子任务交给 CodeAgent 执行，并返回执行结果。

约定：
- 仅接收一个参数：task
- 不依赖父 Agent，所有配置使用系统默认与全局变量
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""
from typing import Any, Dict
import json

from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_utils.globals import delete_agent
from jarvis.jarvis_utils.config import set_config, get_git_check_mode
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class SubCodeAgentTool:
    """
    使用 CodeAgent 托管执行子任务，执行完立即清理内部 Agent。
    - 不注册至全局
    - 使用系统默认/全局配置
    - 启用自动完成与总结
    """

    # 必须与文件名一致，供 ToolRegistry 自动注册
    name = "sub_code_agent"
    description = "将子任务交给 CodeAgent 执行，并返回执行结果（使用系统默认配置，自动完成并生成总结）。"
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

            # 继承父Agent的模型组与工具使用集（用于覆盖默认值）
            parent_agent = args.get("agent")
            # 如未注入父Agent，尝试从全局获取当前或任一已注册Agent
            if parent_agent is None:
                try:
                    from jarvis.jarvis_utils import globals as G  # 延迟导入避免循环

                    curr = getattr(G, "current_agent_name", "")
                    if curr:
                        parent_agent = getattr(G, "global_agents", {}).get(curr)
                    if parent_agent is None and getattr(G, "global_agents", {}):
                        try:
                            parent_agent = next(iter(G.global_agents.values()))
                        except Exception:
                            parent_agent = None
                except Exception:
                    parent_agent = None
            model_group = None
            use_tools: list[str] = []
            try:
                if parent_agent is not None:
                    if getattr(parent_agent, "model", None):
                        model_group = getattr(parent_agent.model, "model_group", None)
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
            append_tools = None
            try:
                base_tools = [
                    "execute_script",
                    "search_web",
                    "ask_user",
                    "read_code",
                    "rewrite_file",
                    "save_memory",
                    "retrieve_memory",
                    "clear_memory",
                    "sub_code_agent",
                ]
                if use_tools:
                    extras = [t for t in use_tools if t not in base_tools]
                    append_tools = ",".join(extras) if extras else None
            except Exception:
                append_tools = None

            # 在子Agent中放宽 Git 配置校验，避免因严格校验导致进程退出
            # 使用配置项将校验模式临时切换为 warn，构造完成后恢复原值
            old_mode = None
            try:
                old_mode = get_git_check_mode()
                set_config("JARVIS_GIT_CHECK_MODE", "warn")
                code_agent = CodeAgent(
                    model_group=model_group,
                    need_summary=True,
                    append_tools=append_tools,
                    tool_group=tool_group,
                )
            except SystemExit as se:
                # 将底层 sys.exit 转换为工具错误，避免终止进程
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"初始化 CodeAgent 失败（可能未配置 git 或当前非 git 仓库）: {se}",
                }
            finally:
                if old_mode is not None:
                    try:
                        set_config("JARVIS_GIT_CHECK_MODE", old_mode)
                    except Exception:
                        pass

            # 子Agent需要自动完成
            try:
                code_agent.agent.auto_complete = True
                # 同步父Agent工具使用集（如可用）
                if use_tools:
                    code_agent.agent.set_use_tools(use_tools)
                # 同步父Agent的模型名称（如可用），以尽量保持平台与模型一致
                if (
                    parent_agent is not None
                    and getattr(parent_agent, "model", None)
                    and getattr(code_agent.agent, "model", None)
                ):
                    try:
                        parent_model_name = parent_agent.model.name()  # type: ignore[attr-defined]
                        if parent_model_name:
                            from typing import Any
                            model_obj: Any = getattr(code_agent.agent, "model", None)
                            if model_obj is not None:
                                model_obj.set_model_name(parent_model_name)
                                # 模型有效性校验与回退，确保父Agent模型在子Agent平台上可用
                                try:
                                    available_models = model_obj.get_model_list()
                                    if available_models:
                                        available_names = [m for m, _ in available_models]
                                        current_model_name = model_obj.name()
                                        if current_model_name not in available_names:
                                            PrettyOutput.print(
                                                f"检测到子CodeAgent模型 {current_model_name} 不存在于平台 {model_obj.platform_name()} 的可用模型列表，将回退到 {available_names[0]}",
                                                OutputType.WARNING,
                                            )
                                            model_obj.set_model_name(available_names[0])
                                except Exception:
                                    # 获取模型列表或设置模型失败时，保持原设置并继续，交由底层报错处理
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass

            # 执行子任务（无提交信息前后缀）
            ret = code_agent.run(enhanced_task, prefix="", suffix="")
            stdout = ret if isinstance(ret, str) and ret else "任务执行完成"

            # 主动清理内部 Agent，避免污染父Agent的全局状态
            try:
                inner_agent = code_agent.agent
                delete_agent(inner_agent.name)
            except Exception:
                pass

            return {
                "success": True,
                "stdout": json.dumps({"result": stdout}, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行子任务失败: {str(e)}",
            }
