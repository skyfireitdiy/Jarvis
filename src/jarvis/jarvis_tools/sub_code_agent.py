# -*- coding: utf-8 -*-
"""
sub_code_agent 工具
将子任务交给 CodeAgent 执行，并返回执行结果。

约定：
- 仅接收一个参数：task
- 不依赖父 Agent，所有配置使用系统默认与全局变量
- 子Agent必须自动完成(auto_complete=True)且需要summary(need_summary=True)
"""
from typing import Any, Dict, Optional
import json

from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_utils.globals import delete_agent
from jarvis.jarvis_code_agent import code_agent as code_agent_module


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
            }
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

            # 在模块级别打补丁，仅自动确认交互（允许用户输入）
            def _auto_confirm(tip: str, default: bool = True) -> bool:
                return default



            code_agent_module.user_confirm = _auto_confirm

            # 读取背景信息并组合任务
            background: str = str(args.get("background", "")).strip()
            enhanced_task = f"背景信息:\n{background}\n\n任务:\n{task}" if background else task

            # 创建 CodeAgent（使用系统默认配置），子Agent需要 summary
            try:
                code_agent = CodeAgent(
                    need_summary=True,  # 强制子Agent需要总结
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
                code_agent.agent.auto_complete = True
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
