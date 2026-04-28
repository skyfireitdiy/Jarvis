# -*- coding: utf-8 -*-
from typing import Any
from typing import Dict


class GoalManagerTool:
    """当前 Agent 会话的目标管理工具"""

    name = "goal_manager"
    description = """管理当前 Agent 会话的任务目标，支持两种操作：

1. **set**: 设置或更新当前会话的最新目标文本。
2. **get**: 获取当前会话的最新目标文本。

**调用时机**：
- 当整体任务目标发生变更时，应调用 `set` 立即更新当前目标。
- 当需要确认当前整体目标，或在会话压缩、恢复后重新获取目标时，应调用 `get`。

**重要提示**：
- 该工具仅作用于当前 Agent 会话。
- 目标内容为纯文本。
- 目标会通过 SessionManager 在会话保存与恢复时自动持久化。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["set", "get"],
                "description": "操作类型：set（设置当前目标）、get（获取当前目标）",
            },
            "goal": {
                "type": "string",
                "description": "当前最新目标的纯文本内容（仅 action=set 时必填）",
            },
        },
        "required": ["action"],
    }

    _GOAL_KEY = "current_goal"

    def _get_session(self, args: Dict[str, Any]) -> Any:
        """获取当前 agent 的 session 对象"""
        agent = args.get("agent")
        if agent is None:
            raise ValueError("缺少 agent 上下文，无法访问当前会话")

        session = getattr(agent, "session", None)
        if session is None:
            raise ValueError("当前 agent 不包含 session，无法管理会话目标")

        return session

    def _execute_set(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """设置当前目标"""
        goal = args.get("goal", "")
        if not isinstance(goal, str) or not goal.strip():
            return {
                "success": False,
                "stdout": "",
                "stderr": "action=set 时必须提供非空的 goal 字符串",
            }

        session = self._get_session(args)
        normalized_goal = goal.strip()
        session.set_user_data(self._GOAL_KEY, normalized_goal)

        return {
            "success": True,
            "stdout": f"当前目标已更新：\n{normalized_goal}",
            "stderr": "",
        }

    def _execute_get(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取当前目标"""
        session = self._get_session(args)
        current_goal = session.get_user_data(self._GOAL_KEY)

        if isinstance(current_goal, str) and current_goal.strip():
            return {
                "success": True,
                "stdout": current_goal.strip(),
                "stderr": "",
            }

        return {
            "success": True,
            "stdout": "当前未设置目标",
            "stderr": "",
        }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行目标管理操作"""
        action = args.get("action")

        if action == "set":
            return self._execute_set(args)
        if action == "get":
            return self._execute_get(args)

        return {
            "success": False,
            "stdout": "",
            "stderr": "不支持的 action，必须为 set 或 get",
        }


class goal_manager(GoalManagerTool):
    """必须与文件名一致，供 ToolRegistry 自动注册"""

    pass
