# -*- coding: utf-8 -*-
"""Gateway 管理工具 - 用于管理 Agent 之间的通信和协作以及节点信息查询"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class GatewayManagerTool:
    """Gateway 管理工具，支持多种操作：

    1. **send_to_agent**: 向指定 Agent 发送消息（通过 Web Gateway 代理到目标 Agent 的 /message 接口）
    2. **list_agents**: 获取所有 Agent 列表
    3. **list_nodes**: 获取节点列表信息
    4. **list_model_groups**: 获取指定节点的模型组列表
    5. **create_agent**: 创建新的 Agent
    6. **list_directory**: 获取指定路径下的文件/目录列表，支持跨节点查询
    7. **delete_agent**: 删除指定的 Agent
    8. **get_node_secret**: 获取网关的节点连接私钥
    9. **update_nodes_code**: 更新所有节点代码到 main 分支
    10. **restart_nodes**: 一键重启所有节点服务（跳过当前节点）
    11. **create_timer**: 创建定时任务（支持指定节点）
    12. **list_timers**: 查询所有节点的定时任务（汇总）
    13. **get_timer**: 查询单个定时任务
    14. **delete_timer**: 删除定时任务
    15. **create_group**: 创建群组
    16. **list_groups**: 查询所有群组
    17. **get_group**: 查询群组详情
    18. **join_group**: 加入群组
    19. **leave_group**: 退出群组
    20. **send_group_message**: 发送群组消息

    **重要提示**：
    - 每次调用只能执行一种操作
    - 参数根据操作类型而有所不同
    """

    name = "gateway_manager"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """Agent 管理工具，用于管理 Agent 之间的通信和协作。

支持的操作：
1. **send_to_agent**: 向指定 Agent 发送消息，消息会通过 Web Gateway 代理到目标 Agent 的 /message 接口，添加到目标 Agent 的输入缓冲区
2. **list_agents**: 获取所有 Agent 列表
3. **list_nodes**: 获取节点列表信息，包括本节点配置、运行状态、已注册的子节点等
4. **list_model_groups**: 获取指定节点的模型组列表，包括模型组名称、各档位模型配置等
5. **create_agent**: 创建新的 Agent，支持指定类型、工作目录、模型组、任务等参数
6. **list_directory**: 获取指定路径下的文件/目录列表，支持跨节点查询（通过 node_id 指定目标节点）
7. **delete_agent**: 删除指定的 Agent，支持跨节点删除（通过 node_id 指定目标节点）
8. **get_node_secret**: 获取网关的节点连接私钥，用于子节点连接主网关时的身份认证
9. **update_nodes_code**: 更新所有节点代码到 main 分支，将所有节点的 Jarvis 代码切换到 main 分支并拉取最新代码
10. **restart_nodes**: 一键重启所有节点服务，跳过当前节点（因为当前节点有 Agent 在运行），依次重启子节点后最后重启 master 节点
11. **create_timer**: 创建定时任务，支持指定节点，可定时创建 Agent 或执行 Shell 命令
12. **list_timers**: 查询所有节点的定时任务并汇总
13. **get_timer**: 查询单个定时任务详情
14. **delete_timer**: 删除指定定时任务
15. **create_group**: 创建群组
16. **list_groups**: 查询所有群组
17. **get_group**: 查询群组详情
18. **join_group**: 加入群组
19. **leave_group**: 退出群组
20. **send_group_message**: 发送群组消息

**重要提示**：
- 每次调用只能执行一种操作（send_to_agent、list_agents、list_nodes、list_model_groups、create_agent、list_directory、delete_agent、get_node_secret、update_nodes_code、restart_nodes、create_timer、list_timers、get_timer、delete_timer、create_group、list_groups、get_group、join_group、leave_group、send_group_message）
- 参数根据操作类型而有所不同"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "send_to_agent",
                    "list_agents",
                    "list_nodes",
                    "list_model_groups",
                    "create_agent",
                    "list_directory",
                    "delete_agent",
                    "get_node_secret",
                    "update_nodes_code",
                    "restart_nodes",
                    "create_timer",
                    "list_timers",
                    "get_timer",
                    "delete_timer",
                    "create_group",
                    "list_groups",
                    "get_group",
                    "join_group",
                    "leave_group",
                    "send_group_message",
                ],
                "description": "操作类型：send_to_agent（向 Agent 发送消息）、list_agents（获取所有 Agent 列表）、list_nodes（获取节点列表信息）、list_model_groups（获取指定节点的模型组列表）、create_agent（创建新的 Agent）、list_directory（获取文件/目录列表）、delete_agent（删除指定的 Agent）、get_node_secret（获取网关的节点连接私钥）、update_nodes_code（更新所有节点代码到 main 分支）、restart_nodes（一键重启所有节点服务，跳过当前节点）、create_timer（创建定时任务）、list_timers（查询所有节点定时任务）、get_timer（查询单个定时任务）、delete_timer（删除定时任务）、create_group（创建群组）、list_groups（查询所有群组）、get_group（查询群组详情）、join_group（加入群组）、leave_group（退出群组）、send_group_message（发送群组消息）",
            },
            # send_to_agent 操作的参数
            "agent_id": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": "目标 Agent 的 ID（send_to_agent 操作必填；delete_agent 操作必填）。支持单个 ID 字符串或 ID 数组。",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容（send_to_agent 操作必填）",
            },
            # list_model_groups / create_agent / list_directory 操作的参数
            "node_id": {
                "type": "string",
                "description": "目标节点 ID（send_to_agent 操作可选，未指定时自动查询 Agent 所在节点；list_model_groups 操作可选，默认为 master；create_agent 操作可选，默认为本节点；list_directory 操作可选，默认为本节点；delete_agent 操作可选，默认为本节点）",
            },
            # list_directory 操作的参数
            "path": {
                "type": "string",
                "description": "目录路径（list_directory 操作可选，默认为空表示用户主目录）",
            },
            # create_agent 操作的参数
            "agent_type": {
                "type": "string",
                "description": "Agent 类型（create_agent 操作必填），如 code、chat 等",
            },
            "working_dir": {
                "type": "string",
                "description": "工作目录（create_agent 操作必填）",
            },
            "agent_name": {
                "type": "string",
                "description": "Agent 名称（create_agent 操作可选）",
            },
            "llm_group": {
                "type": "string",
                "description": "模型组名称（create_agent 操作可选，默认为 default）",
            },
            "tool_group": {
                "type": "string",
                "description": "工具组名称（create_agent 操作可选，默认为 default）",
            },
            "config_file": {
                "type": "string",
                "description": "配置文件路径（create_agent 操作可选）",
            },
            "task": {
                "type": "string",
                "description": "Agent 的初始任务描述（create_agent 操作可选，no_interaction_mode 时必填）",
            },
            "additional_args": {
                "type": "string",
                "description": "附加参数（create_agent 操作可选）",
            },
            "worktree": {
                "type": "boolean",
                "description": "是否使用 git worktree（create_agent 操作可选，默认为 false）",
            },
            "quick_mode": {
                "type": "boolean",
                "description": "是否启用快速模式（create_agent 操作可选，默认为 false）",
            },
            "restore_session": {
                "type": "string",
                "description": "恢复会话的文件路径（create_agent 操作可选，默认为 null，不恢复会话）",
            },
            "no_interaction_mode": {
                "type": "boolean",
                "description": "是否启用无交互模式（create_agent 操作可选，默认为 false，启用时 task 必填）",
            },
            # timer 操作的参数
            "timer_id": {
                "type": "string",
                "description": "定时任务 ID（get_timer、delete_timer 操作必填）",
            },
            "schedule": {
                "type": "object",
                "description": "定时任务调度配置（create_timer 操作必填），三选一：run_at（ISO 时间字符串）、delay_seconds（延迟秒数≥0）、interval_seconds（间隔秒数>0）",
            },
            "timer_action_type": {
                "type": "string",
                "enum": ["create_agent", "run_shell_command"],
                "description": "定时任务动作类型（create_timer 操作必填）：create_agent 或 run_shell_command",
            },
            "timer_action_params": {
                "type": "object",
                "description": "定时任务动作参数（create_timer 操作必填）。create_agent 类型需：agent_type(必填)、working_dir(必填)、name、llm_group、tool_group、config_file、task、additional_args、worktree、proxy_node；run_shell_command 类型需：command(必填)、working_dir(必填)、interpreter",
            },
            # 群组操作的参数
            "group_id": {
                "type": "string",
                "description": "群组 ID（get_group、join_group、leave_group、send_group_message 操作必填）",
            },
            "group_name": {
                "type": "string",
                "description": "群组名称（create_group 操作必填）",
            },
            "group_description": {
                "type": "string",
                "description": "群组描述（create_group 操作可选）",
            },
        },
        "required": ["action"],
    }

    def execute(
        self,
        action: str,
        agent_id: Optional[str] = None,
        message: str = "",
        node_id: Optional[str] = None,
        path: str = "",
        agent_type: Optional[str] = None,
        working_dir: Optional[str] = None,
        agent_name: Optional[str] = None,
        llm_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        config_file: Optional[str] = None,
        task: Optional[str] = None,
        additional_args: Optional[str] = None,
        worktree: bool = False,
        quick_mode: bool = False,
        restore_session: Optional[str] = None,
        no_interaction_mode: bool = False,
        timer_id: Optional[str] = None,
        schedule: Optional[Dict[str, Any]] = None,
        timer_action_type: Optional[str] = None,
        timer_action_params: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None,
        group_name: Optional[str] = None,
        group_description: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行 Gateway 管理操作

        参数:
            action: 操作类型 (send_to_agent, list_agents, list_nodes, list_model_groups, create_agent, list_directory, delete_agent, get_node_secret, update_nodes_code, restart_nodes, create_timer, list_timers, get_timer, delete_timer, create_group, list_groups, get_group, join_group, leave_group, send_group_message)
            agent_id: 目标 Agent ID
            message: 消息内容
            node_id: 目标节点 ID
            path: 目录路径（list_directory）
            agent_type: Agent 类型（create_agent）
            working_dir: 工作目录（create_agent）
            agent_name: Agent 名称（create_agent）
            llm_group: 模型组（create_agent）
            tool_group: 工具组（create_agent）
            config_file: 配置文件（create_agent）
            task: 任务描述（create_agent）
            additional_args: 附加参数（create_agent）
            worktree: 是否使用 worktree（create_agent）
            quick_mode: 快速模式（create_agent）
            restore_session: 恢复会话（create_agent）
            no_interaction_mode: 无交互模式（create_agent）
            timer_id: 定时任务 ID（get_timer、delete_timer）
            schedule: 调度配置（create_timer）
            timer_action_type: 定时任务动作类型（create_timer）
            timer_action_params: 定时任务动作参数（create_timer）
            group_id: 群组 ID（get_group、join_group、leave_group、send_group_message）
            group_name: 群组名称（create_group）
            group_description: 群组描述（create_group）
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: 执行结果
        """
        # 兼容 v1.0 协议：registry 可能将整个参数字典作为 action 传入
        if isinstance(action, dict):
            args = action
            action = args.get("action", "")
            agent_id = args.get("agent_id")
            message = args.get("message", "")
            node_id = args.get("node_id")
            path = args.get("path", "")
            agent_type = args.get("agent_type")
            working_dir = args.get("working_dir")
            agent_name = args.get("agent_name")
            llm_group = args.get("llm_group")
            tool_group = args.get("tool_group")
            config_file = args.get("config_file")
            task = args.get("task")
            additional_args = args.get("additional_args")
            worktree = args.get("worktree", False)
            quick_mode = args.get("quick_mode", False)
            restore_session = args.get("restore_session")
            no_interaction_mode = args.get("no_interaction_mode", False)
            timer_id = args.get("timer_id")
            schedule = args.get("schedule")
            timer_action_type = args.get("timer_action_type")
            timer_action_params = args.get("timer_action_params")
            group_id = args.get("group_id")
            group_name = args.get("group_name")
            group_description = args.get("group_description")
        try:
            if action == "send_to_agent":
                return self._send_to_agent(agent_id, message, node_id=node_id)
            elif action == "list_agents":
                return self._list_agents()
            elif action == "list_nodes":
                return self._list_nodes()
            elif action == "list_model_groups":
                return self._list_model_groups(node_id)
            elif action == "create_agent":
                return self._create_agent(
                    agent_type=agent_type,
                    working_dir=working_dir,
                    name=agent_name,
                    llm_group=llm_group,
                    tool_group=tool_group,
                    config_file=config_file,
                    task=task,
                    additional_args=additional_args,
                    worktree=worktree,
                    quick_mode=quick_mode,
                    restore_session=restore_session,
                    no_interaction_mode=no_interaction_mode,
                    node_id=node_id,
                )
            elif action == "list_directory":
                return self._list_directory(path=path, node_id=node_id)
            elif action == "delete_agent":
                return self._delete_agent(agent_id=agent_id, node_id=node_id)
            elif action == "get_node_secret":
                return self._get_node_secret()
            elif action == "update_nodes_code":
                return self._update_nodes_code()
            elif action == "restart_nodes":
                return self._restart_nodes()
            elif action == "create_timer":
                return self._create_timer(
                    node_id=node_id,
                    schedule=schedule,
                    timer_action_type=timer_action_type,
                    timer_action_params=timer_action_params,
                )
            elif action == "list_timers":
                return self._list_timers()
            elif action == "get_timer":
                return self._get_timer(timer_id=timer_id)
            elif action == "delete_timer":
                return self._delete_timer(timer_id=timer_id)
            elif action == "create_group":
                return self._create_group(
                    group_name=group_name, group_description=group_description
                )
            elif action == "list_groups":
                return self._list_groups()
            elif action == "get_group":
                return self._get_group(group_id=group_id)
            elif action == "join_group":
                return self._join_group(group_id=group_id)
            elif action == "leave_group":
                return self._leave_group(group_id=group_id)
            elif action == "send_group_message":
                return self._send_group_message(group_id=group_id, message=message)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Unknown action: {action}",
                }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
            }

    def _get_master_url(self, action_name: str = "") -> Optional[Dict[str, Any]]:
        """获取 master_url，未设置时返回错误字典。

        参数:
            action_name: 操作名称，用于错误提示

        返回:
            None 表示 master_url 可用，否则返回错误字典
        """
        if not jglobals.master_url:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"master_url is not set, cannot {action_name}. "
                "Please ensure the agent is started with --master-url option.",
            }
        return None

    def _build_auth_headers(self) -> Dict[str, str]:
        """构建带认证信息的请求头。

        返回:
            Dict[str, str]: 请求头字典
        """
        headers: Dict[str, str] = {}
        auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _request_gateway(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        error_prefix: str = "Request failed",
    ) -> Dict[str, Any]:
        """向 Gateway 发送 HTTP 请求。

        参数:
            method: HTTP 方法 (GET/POST/DELETE)
            path: 请求路径 (如 /api/agents)
            json_data: POST 请求的 JSON 数据
            params: GET/DELETE 请求的 query 参数
            error_prefix: 错误提示前缀

        返回:
            Dict[str, Any]: 请求结果，包含 success/status_code/data 字段
        """
        url = f"{jglobals.master_url}{path}"
        headers = self._build_auth_headers()

        try:
            with httpx.Client(timeout=10.0) as client:
                if method.upper() == "POST":
                    response = client.post(url, json=json_data, headers=headers)
                elif method.upper() == "DELETE":
                    response = client.delete(url, headers=headers, params=params)
                else:
                    response = client.get(url, headers=headers, params=params)

            if response.status_code == 200:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.json(),
                }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "data": None,
                    "error": f"{error_prefix}: HTTP {response.status_code} - {response.text}",
                }
        except httpx.ConnectError:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"Cannot connect to gateway at {jglobals.master_url}. Please ensure the gateway is running.",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"{error_prefix}: {str(e)}",
            }

    def _handle_gateway_response(
        self, result: Dict[str, Any], success_data_key: str = "data"
    ) -> Dict[str, Any]:
        """处理 Gateway 响应的通用逻辑。

        参数:
            result: _request_gateway 的返回结果
            success_data_key: 成功时提取数据的键名

        返回:
            Dict[str, Any]: 标准化的执行结果
        """
        if not result["success"]:
            return {"success": False, "stdout": "", "stderr": result["error"]}

        gateway_data = result["data"]
        if not gateway_data.get("success"):
            error_info = gateway_data.get("error", {})
            error_msg = (
                error_info.get("message", "unknown error")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Gateway returned error: {error_msg}",
            }

        return {
            "success": True,
            "stdout": json.dumps(
                gateway_data.get(success_data_key, {}), ensure_ascii=False
            ),
            "stderr": "",
        }

    def _send_to_agent(
        self, agent_id: Any, message: str, node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """向指定 Agent(s) 发送消息。

        通过 Web Gateway 的 /api/agent/{agent_id}/message 接口发送消息，
        Gateway 会将请求代理到目标 Agent 的 /message 接口。
        当目标 Agent 在子节点时，通过 /api/node/{node_id}/agent/{agent_id}/message 路由转发。

        参数:
            agent_id: 目标 Agent ID (支持 str 或 List[str])
            message: 消息内容
            node_id: 目标节点 ID（可选，未指定时自动查询 Agent 所在节点）

        返回:
            Dict[str, Any]: 发送结果
        """
        if not agent_id:
            return {"success": False, "stdout": "", "stderr": "agent_id is required"}

        if not message:
            return {"success": False, "stdout": "", "stderr": "message is required"}

        err = self._get_master_url("send message to agent")
        if err:
            return err

        # 标准化 agent_ids 为列表
        target_ids = []
        if isinstance(agent_id, str):
            # 支持逗号分隔的字符串
            target_ids = [aid.strip() for aid in agent_id.split(",") if aid.strip()]
        elif isinstance(agent_id, list):
            target_ids = [str(aid).strip() for aid in agent_id if str(aid).strip()]
        else:
            return {"success": False, "stdout": "", "stderr": "Invalid agent_id type"}

        if not target_ids:
            return {
                "success": False,
                "stdout": "",
                "stderr": "No valid agent_id provided",
            }

        sender_id = jglobals.agent_id
        # 在消息末尾添加回复提示
        enhanced_message = f"{message}\n\n---\n回复此消息请使用: gateway_manager action=send_to_agent agent_id={sender_id} message=<你的回复>"

        results = []
        all_success = True

        # 构建 agent_id -> node_id 映射，用于确定路由路径
        agent_node_map: Dict[str, str] = {}
        if node_id:
            # 用户指定了 node_id，所有目标 Agent 使用同一 node_id
            for target_id in target_ids:
                agent_node_map[target_id] = node_id
        else:
            # 未指定 node_id，查询 Agent 列表获取各 Agent 所在节点
            try:
                agents_result = self._request_gateway(
                    method="GET",
                    path="/api/agents",
                    error_prefix="Failed to query agent list",
                )
                if agents_result["success"]:
                    agents_data = agents_result["data"]
                    if agents_data.get("success"):
                        for agent_info in agents_data.get("data") or []:
                            aid = str(agent_info.get("agent_id", ""))
                            if aid in target_ids:
                                agent_node_map[aid] = agent_info.get(
                                    "node_id", "master"
                                )
            except Exception:
                pass  # 查询失败时 fallback 到原有路径

        for target_id in target_ids:
            target_node_id = agent_node_map.get(target_id)
            # 判断是否需要走子节点路由
            if target_node_id and target_node_id != "master":
                # 子节点 Agent：通过 /api/node/{node_id}/agent/{agent_id}/message 路由
                path = f"/api/node/{target_node_id}/agent/{target_id}/message"
            else:
                # 本地/master Agent：走原有路径
                path = f"/api/agent/{target_id}/message"

            result = self._request_gateway(
                method="POST",
                path=path,
                json_data={"sender_id": sender_id, "content": enhanced_message},
                error_prefix=f"Failed to send message to agent {target_id}",
            )

            if result["success"]:
                results.append(
                    {
                        "agent_id": target_id,
                        "status": "sent",
                        "response": result["data"],
                    }
                )
            else:
                all_success = False
                results.append(
                    {
                        "agent_id": target_id,
                        "status": "failed",
                        "error": result["error"],
                    }
                )

        output = {
            "sender_id": sender_id,
            "message": message,
            "results": results,
        }

        stdout_str = json.dumps(output, ensure_ascii=False, indent=2)
        if all_success:
            stdout_str += "\n\nIf you want to wait for a response, output <Wait>."

        return {
            "success": all_success,
            "stdout": stdout_str,
            "stderr": "" if all_success else "Some messages failed to send",
        }

    def _list_agents(self) -> Dict[str, Any]:
        """获取所有 Agent 列表。

        通过 Web Gateway 的 /api/agents 接口获取 Agent 列表，
        返回所有 Agent 的基本信息。

        返回:
            Dict[str, Any]: Agent 列表
        """
        err = self._get_master_url("list agents")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path="/api/agents",
            error_prefix="Failed to list agents",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {gateway_data.get('error', 'unknown error')}",
                }

            agents = gateway_data.get("data", [])
            current_agent_id = jglobals.agent_id
            result_data = {
                "current_agent_id": current_agent_id,
                "agents": agents,
            }
            return {
                "success": True,
                "stdout": json.dumps(result_data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_nodes(self) -> Dict[str, Any]:
        """获取节点列表信息。

        通过 Web Gateway 的 /api/node/status 接口获取节点信息，
        包括本节点配置、运行状态、已注册的子节点、Agent 路由等。

        返回:
            Dict[str, Any]: 节点状态信息
        """
        err = self._get_master_url("list nodes")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path="/api/node/status",
            error_prefix="Failed to list nodes",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {gateway_data.get('error', 'unknown error')}",
                }

            # 提取节点相关信息
            data = gateway_data.get("data", {})
            current_node_id = data.get("node", {}).get("node_id")
            current_agent_id = jglobals.agent_id
            node_info = {
                "current_node_id": current_node_id,
                "current_agent_id": current_agent_id,
                "node": data.get("node", {}),
                "runtime_status": data.get("runtime_status", "unknown"),
                "nodes": data.get("nodes", []),
                "agent_routes": data.get("agent_routes", []),
            }
            return {
                "success": True,
                "stdout": json.dumps(node_info, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_model_groups(self, node_id: Optional[str] = None) -> Dict[str, Any]:
        """获取指定节点的模型组列表。

        通过 Web Gateway 的 /api/node/{node_id}/model-groups 接口获取模型组列表，
        支持跨节点查询，master 节点会代理请求到目标节点。

        参数:
            node_id: 目标节点 ID，默认为 master

        返回:
            Dict[str, Any]: 模型组列表
        """
        target_node = node_id or "master"

        err = self._get_master_url("list model groups")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path=f"/api/node/{target_node}/model-groups",
            error_prefix="Failed to list model groups",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {gateway_data.get('error', 'unknown error')}",
                }

            data = gateway_data.get("data", [])
            default_llm_group = gateway_data.get("default_llm_group", "")
            output = {
                "model_groups": data,
                "default_llm_group": default_llm_group,
            }
            return {
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _create_agent(
        self,
        agent_type: Optional[str] = None,
        working_dir: Optional[str] = None,
        name: Optional[str] = None,
        llm_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        config_file: Optional[str] = None,
        task: Optional[str] = None,
        additional_args: Optional[str] = None,
        worktree: bool = False,
        quick_mode: bool = False,
        restore_session: Optional[str] = None,
        no_interaction_mode: bool = False,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建新的 Agent。

        通过 Web Gateway 的 POST /api/agents 接口创建 Agent，
        支持跨节点创建（通过 node_id 参数指定目标节点）。

        参数:
            agent_type: Agent 类型（必填），如 code、chat 等
            working_dir: 工作目录（必填）
            name: Agent 名称
            llm_group: 模型组名称
            tool_group: 工具组名称
            config_file: 配置文件路径
            task: 初始任务描述
            additional_args: 附加参数
            worktree: 是否使用 git worktree
            quick_mode: 是否启用快速模式
            restore_session: 是否恢复上一次会话
            no_interaction_mode: 是否启用无交互模式（启用时 task 必填）
            node_id: 目标节点 ID

        返回:
            Dict[str, Any]: 创建结果
        """
        if not agent_type:
            return {"success": False, "stdout": "", "stderr": "agent_type is required"}
        if not working_dir:
            return {"success": False, "stdout": "", "stderr": "working_dir is required"}
        if no_interaction_mode and not task:
            return {
                "success": False,
                "stdout": "",
                "stderr": "task is required when no_interaction_mode is enabled",
            }

        err = self._get_master_url("create agent")
        if err:
            return err

        # 校验 worktree 冲突
        conflict = self._check_worktree_conflict(
            agent_type, worktree, working_dir, node_id
        )
        if conflict:
            return conflict

        # 构建请求体并发送
        body = self._build_create_agent_body(
            agent_type=agent_type,
            working_dir=working_dir,
            name=name,
            llm_group=llm_group,
            tool_group=tool_group,
            config_file=config_file,
            task=task,
            additional_args=additional_args,
            worktree=worktree,
            quick_mode=quick_mode,
            restore_session=restore_session,
            no_interaction_mode=no_interaction_mode,
            node_id=node_id,
        )

        result = self._request_gateway(
            method="POST",
            path="/api/agents",
            json_data=body,
            error_prefix="Failed to create agent",
        )

        if result["success"]:
            gateway_data = result["data"]
            # 修复：处理列表类型的响应
            if isinstance(gateway_data, list):
                if len(gateway_data) == 0:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "Gateway returned empty list",
                    }
                elif len(gateway_data) == 1:
                    gateway_data = gateway_data[0]
                else:
                    # 多个结果，取第一个并记录警告
                    import logging

                    logging.warning(
                        f"Gateway returned list with {len(gateway_data)} items, using first one"
                    )
                    gateway_data = gateway_data[0]

            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            agent_info = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(agent_info, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _check_worktree_conflict(
        self,
        agent_type: Optional[str],
        worktree: bool,
        working_dir: Optional[str],
        node_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """校验同一节点同一工作目录不允许同时有两个未启用 worktree 的 codeagent。

        参数:
            agent_type: Agent 类型
            worktree: 是否启用 worktree
            working_dir: 工作目录
            node_id: 目标节点 ID

        返回:
            冲突时返回错误字典，无冲突返回 None
        """
        if agent_type != "codeagent" or worktree:
            return None

        target_node_id = (node_id or "master").strip() or "master"
        normalized_dir = (working_dir or "").strip()

        agents_result = self._request_gateway(
            method="GET",
            path="/api/agents",
            error_prefix="Failed to get agents list for worktree check",
        )

        if not agents_result["success"]:
            return None

        agents_data = agents_result["data"]
        # 修复：处理列表类型的响应
        if isinstance(agents_data, list):
            if len(agents_data) == 0:
                return None
            elif len(agents_data) == 1:
                agents_data = agents_data[0]
            else:
                # 多个结果，取第一个并记录警告
                import logging

                logging.warning(
                    f"Gateway returned list with {len(agents_data)} items in worktree check, using first one"
                )
                agents_data = agents_data[0]

        if not agents_data.get("success"):
            return None

        # 修复：正确处理 data 字段是列表的情况
        data_field = agents_data.get("data", {})
        if isinstance(data_field, list):
            # data 是列表，直接作为 agents_list
            agents_list = data_field
        elif isinstance(data_field, dict):
            # data 是字典，从 agents 键获取列表
            agents_list = data_field.get("agents", [])
        else:
            agents_list = []
        for agent in agents_list:
            # 已停止的 agent 不冲突
            if agent.get("status") in ("stopped", "completed", "failed", "abandoned"):
                continue
            if agent.get("agent_type") != "codeagent":
                continue
            if agent.get("worktree"):
                continue
            agent_node_id = (agent.get("node_id") or "").strip() or "master"
            if agent_node_id != target_node_id:
                continue
            if (agent.get("working_dir") or "").strip() != normalized_dir:
                continue
            conflict_name = agent.get("name") or agent.get("agent_id") or "未命名"
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    f"工作目录冲突：节点 {target_node_id} 下已存在未启用 worktree 的代码 Agent「{conflict_name}」。"
                    f"同一工作目录下只能有一个未启用 worktree 的代码 Agent。"
                    f"请启用 worktree 或选择其他工作目录。"
                ),
            }

        return None

    def _build_create_agent_body(
        self,
        agent_type: Optional[str] = None,
        working_dir: Optional[str] = None,
        name: Optional[str] = None,
        llm_group: Optional[str] = None,
        tool_group: Optional[str] = None,
        config_file: Optional[str] = None,
        task: Optional[str] = None,
        additional_args: Optional[str] = None,
        worktree: bool = False,
        quick_mode: bool = False,
        restore_session: Optional[str] = None,
        no_interaction_mode: bool = False,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建创建 Agent 的请求体，只包含非空参数。"""
        body: Dict[str, Any] = {
            "agent_type": agent_type,
            "working_dir": working_dir,
        }
        if name:
            body["name"] = name
        if llm_group:
            body["llm_group"] = llm_group
        if tool_group:
            body["tool_group"] = tool_group
        if config_file:
            body["config_file"] = config_file
        if task:
            body["task"] = task
        if additional_args:
            body["additional_args"] = additional_args
        if worktree:
            body["worktree"] = True
        if quick_mode:
            body["quick_mode"] = True
        if restore_session:
            body["restore_session"] = restore_session
        if no_interaction_mode:
            body["no_interaction_mode"] = True
        if node_id:
            body["node_id"] = node_id
        return body

    def _list_directory(
        self, path: str = "", node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取指定路径下的文件/目录列表。

        通过 Web Gateway 的 GET /api/directories 接口获取目录列表，
        支持跨节点查询（通过 node_id 参数指定目标节点）。

        参数:
            path: 目录路径，默认为空（表示用户主目录）
            node_id: 目标节点 ID，默认为空（表示本节点）

        返回:
            Dict[str, Any]: 目录列表
        """
        err = self._get_master_url("list directory")
        if err:
            return err

        # 构建 query 参数
        query_params: Dict[str, str] = {}
        if path:
            query_params["path"] = path
        if node_id:
            query_params["node_id"] = node_id

        result = self._request_gateway(
            method="GET",
            path="/api/directories",
            params=query_params if query_params else None,
            error_prefix="Failed to list directory",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_detail = gateway_data.get("error", "unknown error")
                if isinstance(error_detail, dict):
                    error_msg = error_detail.get("message", str(error_detail))
                else:
                    error_msg = str(error_detail)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            data = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _get_node_secret(self) -> Dict[str, Any]:
        """获取网关的节点连接私钥。

        通过 Web Gateway 的 GET /api/node/secret 接口获取节点连接私钥，
        此私钥用于子节点连接主网关时的身份认证。

        返回:
            Dict[str, Any]: 包含 node_secret 的结果
        """
        err = self._get_master_url("get node secret")
        if err:
            return err

        result = self._request_gateway(
            method="GET",
            path="/api/node/secret",
            error_prefix="Failed to get node secret",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            data = gateway_data.get("data", {})
            node_secret = data.get("node_secret", "")
            return {
                "success": True,
                "stdout": json.dumps(
                    {"node_secret": node_secret}, ensure_ascii=False, indent=2
                ),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _update_nodes_code(self) -> Dict[str, Any]:
        """更新所有节点代码到 main 分支。

        通过 Web Gateway 的 POST /api/nodes/{node_id}/code-update 接口，
        将所有在线节点的 Jarvis 代码切换到 main 分支并拉取最新代码。

        返回:
            Dict[str, Any]: 包含各节点更新结果的信息
        """
        err = self._get_master_url("update nodes code")
        if err:
            return err

        # 先获取所有在线节点（通过 /api/node/status 接口）
        nodes_result = self._request_gateway(
            method="GET",
            path="/api/node/status",
            error_prefix="Failed to get nodes list",
        )

        if not nodes_result["success"]:
            return {"success": False, "stdout": "", "stderr": nodes_result["error"]}

        gateway_data = nodes_result["data"]
        if not gateway_data.get("success"):
            error_info = gateway_data.get("error", {})
            error_msg = (
                error_info.get("message", "unknown error")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Gateway returned error: {error_msg}",
            }

        # /api/node/status 返回结构: {"success": True, "data": {"nodes": [...]}}
        nodes_data = gateway_data.get("data", {})
        nodes = nodes_data.get("nodes", [])
        if not nodes:
            return {
                "success": False,
                "stdout": "",
                "stderr": "No online nodes available for code update",
            }

        # 对每个节点执行代码更新
        results = []
        success_count = 0
        for node in nodes:
            node_id = node.get("node_id", "")
            if not node_id:
                continue

            update_result = self._request_gateway(
                method="POST",
                path=f"/api/nodes/{node_id}/code-update",
                error_prefix=f"Failed to update code for node {node_id}",
            )

            if update_result["success"]:
                update_data = update_result["data"]
                if update_data.get("success"):
                    success_count += 1
                    data = update_data.get("data", {})
                    results.append(
                        {
                            "node_id": node_id,
                            "success": True,
                            "message": data.get("message", "更新成功"),
                        }
                    )
                else:
                    error_info = update_data.get("error", {})
                    error_msg = (
                        error_info.get("message", "unknown error")
                        if isinstance(error_info, dict)
                        else str(error_info)
                    )
                    results.append(
                        {
                            "node_id": node_id,
                            "success": False,
                            "message": error_msg,
                        }
                    )
            else:
                results.append(
                    {
                        "node_id": node_id,
                        "success": False,
                        "message": update_result["error"],
                    }
                )

        total_count = len(nodes)
        if success_count == total_count:
            message = f"代码更新成功，已更新 {success_count}/{total_count} 个节点"
        elif success_count > 0:
            message = f"代码更新部分成功，成功 {success_count}/{total_count} 个节点"
        else:
            message = "代码更新失败，没有节点更新成功"

        summary: Dict[str, Any] = {
            "total": total_count,
            "success": success_count,
            "failed": total_count - success_count,
            "results": results,
            "message": message,
        }

        return {
            "success": success_count > 0,
            "stdout": json.dumps(summary, ensure_ascii=False, indent=2),
            "stderr": "" if success_count > 0 else "All nodes failed to update",
        }

    def _restart_nodes(self) -> Dict[str, Any]:
        """一键重启所有节点服务（跳过当前节点）。

        通过 Web Gateway 的 POST /api/nodes/{node_id}/service/restart 接口，
        依次重启所有子节点，最后重启 master 节点。
        跳过当前节点（因为当前节点有 Agent 在运行）。

        返回:
            Dict[str, Any]: 包含各节点重启结果的信息
        """
        err = self._get_master_url("restart nodes")
        if err:
            return err
        # 先获取所有在线节点（通过 /api/node/status 接口）
        nodes_result = self._request_gateway(
            method="GET",
            path="/api/node/status",
            error_prefix="Failed to get nodes list",
        )

        if not nodes_result["success"]:
            return {"success": False, "stdout": "", "stderr": nodes_result["error"]}

        gateway_data = nodes_result["data"]
        if not gateway_data.get("success"):
            error_info = gateway_data.get("error", {})
            error_msg = (
                error_info.get("message", "unknown error")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Gateway returned error: {error_msg}",
            }

        # /api/node/status 返回结构: {"success": True, "data": {"nodes": [...]}}
        nodes_data = gateway_data.get("data", {})
        nodes = nodes_data.get("nodes", [])
        if not nodes:
            return {
                "success": False,
                "stdout": "",
                "stderr": "No online nodes available for restart",
            }

        # 获取当前节点 ID，跳过当前节点
        current_node_id = os.environ.get("NODE_ID", "master")

        # 排序：子节点在前，master 在后
        child_nodes = [n for n in nodes if n.get("node_id", "") != "master"]
        master_node = [n for n in nodes if n.get("node_id", "") == "master"]
        sorted_nodes = child_nodes + master_node

        # 对每个节点执行重启
        results = []
        success_count = 0
        skipped_count = 0
        for node in sorted_nodes:
            node_id = node.get("node_id", "")
            if not node_id:
                continue

            # 跳过当前节点
            if node_id == current_node_id:
                skipped_count += 1
                results.append(
                    {
                        "node_id": node_id,
                        "success": True,
                        "skipped": True,
                        "message": f"跳过当前节点 {node_id}（有 Agent 正在运行）",
                    }
                )
                continue

            restart_result = self._request_gateway(
                method="POST",
                path=f"/api/node/{node_id}/service/restart",
                json_data={"node_id": node_id, "restart_frontend": True},
                error_prefix=f"Failed to restart node {node_id}",
            )

            if restart_result["success"]:
                restart_data = restart_result["data"]
                if restart_data.get("success"):
                    success_count += 1
                    data = restart_data.get("data", {})
                    results.append(
                        {
                            "node_id": node_id,
                            "success": True,
                            "skipped": False,
                            "message": data.get("message", "重启请求已发送"),
                        }
                    )
                else:
                    error_info = restart_data.get("error", {})
                    error_msg = (
                        error_info.get("message", "unknown error")
                        if isinstance(error_info, dict)
                        else str(error_info)
                    )
                    results.append(
                        {
                            "node_id": node_id,
                            "success": False,
                            "skipped": False,
                            "message": error_msg,
                        }
                    )
            else:
                results.append(
                    {
                        "node_id": node_id,
                        "success": False,
                        "skipped": False,
                        "message": restart_result["error"],
                    }
                )

        total_count = len(sorted_nodes)
        restarted_count = total_count - skipped_count
        if success_count == restarted_count:
            message = (
                f"节点重启命令已发送完成，成功 {success_count}/{restarted_count} 个节点"
                + (f"，跳过当前节点 {current_node_id}" if skipped_count > 0 else "")
            )
        elif success_count > 0:
            message = (
                f"节点重启部分成功，成功 {success_count}/{restarted_count} 个节点"
                + (f"，跳过当前节点 {current_node_id}" if skipped_count > 0 else "")
            )
        else:
            message = "节点重启失败，没有节点重启成功"

        summary: Dict[str, Any] = {
            "total": total_count,
            "success": success_count,
            "skipped": skipped_count,
            "failed": restarted_count - success_count,
            "results": results,
            "message": message,
        }

        return {
            "success": success_count > 0,
            "stdout": json.dumps(summary, ensure_ascii=False, indent=2),
            "stderr": "" if success_count > 0 else "All nodes failed to restart",
        }

    def _delete_agent(
        self, agent_id: Optional[str] = None, node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """删除指定的 Agent。

        通过 Web Gateway 的 DELETE /api/agents/{agent_id} 接口删除 Agent，
        支持跨节点删除（通过 node_id 参数指定目标节点）。

        参数:
            agent_id: 要删除的 Agent ID（必填）
            node_id: 目标节点 ID，默认为空（表示本节点）

        返回:
            Dict[str, Any]: 删除结果
        """
        if not agent_id:
            return {"success": False, "stdout": "", "stderr": "agent_id is required"}

        err = self._get_master_url("delete agent")
        if err:
            return err

        # 构建 query 参数
        query_params: Dict[str, str] = {}
        if node_id:
            query_params["node_id"] = node_id

        result = self._request_gateway(
            method="DELETE",
            path=f"/api/agents/{agent_id}",
            params=query_params if query_params else None,
            error_prefix=f"Failed to delete agent {agent_id}",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }

            data = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _create_timer(
        self,
        node_id: Optional[str] = None,
        schedule: Optional[Dict[str, Any]] = None,
        timer_action_type: Optional[str] = None,
        timer_action_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建定时任务。

        参数:
            node_id: 目标节点 ID（可选，默认为 master）
            schedule: 调度配置，三选一
            timer_action_type: 动作类型（create_agent / run_shell_command）
            timer_action_params: 动作参数

        返回:
            Dict[str, Any]: 执行结果
        """
        if not schedule:
            return {"success": False, "stdout": "", "stderr": "schedule is required"}
        if not timer_action_type:
            return {
                "success": False,
                "stdout": "",
                "stderr": "timer_action_type is required",
            }
        if not timer_action_params:
            return {
                "success": False,
                "stdout": "",
                "stderr": "timer_action_params is required",
            }

        # 构建请求体
        body = {
            "schedule": schedule,
            "action": {
                "type": timer_action_type,
                "params": timer_action_params,
            },
        }

        # 确定请求路径（支持跨节点）
        path = "/api/timers"
        if node_id and node_id != "master":
            path = f"/api/node/{node_id}/timers"

        result = self._request_gateway(
            method="POST",
            path=path,
            json_data=body,
            error_prefix="Failed to create timer",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }
            data = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _list_timers(self) -> Dict[str, Any]:
        """查询所有节点的定时任务并汇总。

        返回:
            Dict[str, Any]: 执行结果
        """
        nodes_result = self._list_nodes()
        if not nodes_result.get("success"):
            return nodes_result

        try:
            nodes_data = json.loads(nodes_result["stdout"])
        except (json.JSONDecodeError, TypeError):
            return {
                "success": False,
                "stdout": "",
                "stderr": "Failed to parse nodes data",
            }

        all_timers = []
        errors = []

        # 构建节点 ID 列表：master + 所有子节点
        node_ids = ["master"]
        for sub_node in nodes_data.get("nodes", []):
            sub_node_id = sub_node.get("node_id", "")
            if sub_node_id:
                node_ids.append(sub_node_id)

        # 遍历所有节点查询定时任务
        for node_id in node_ids:
            path = "/api/timers"
            if node_id != "master":
                path = f"/api/node/{node_id}/timers"

            result = self._request_gateway(
                method="GET",
                path=path,
                error_prefix=f"Failed to list timers on node {node_id}",
            )

            if result["success"]:
                gateway_data = result["data"]
                if gateway_data.get("success"):
                    timers = gateway_data.get("data", [])
                    for timer in timers:
                        timer["node_id"] = node_id
                    all_timers.extend(timers)
                else:
                    error_info = gateway_data.get("error", {})
                    error_msg = (
                        error_info.get("message", "unknown error")
                        if isinstance(error_info, dict)
                        else str(error_info)
                    )
                    errors.append(f"node {node_id}: {error_msg}")
            else:
                errors.append(f"node {node_id}: {result['error']}")

        output = {
            "timers": all_timers,
            "total": len(all_timers),
        }
        if errors:
            output["errors"] = errors

        return {
            "success": True,
            "stdout": json.dumps(output, ensure_ascii=False, indent=2),
            "stderr": "",
        }

    def _get_timer(self, timer_id: Optional[str] = None) -> Dict[str, Any]:
        """查询单个定时任务。

        参数:
            timer_id: 定时任务 ID

        返回:
            Dict[str, Any]: 执行结果
        """
        if not timer_id:
            return {"success": False, "stdout": "", "stderr": "timer_id is required"}

        result = self._request_gateway(
            method="GET",
            path=f"/api/timers/{timer_id}",
            error_prefix=f"Failed to get timer {timer_id}",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }
            data = gateway_data.get("data", {})
            return {
                "success": True,
                "stdout": json.dumps(data, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _delete_timer(self, timer_id: Optional[str] = None) -> Dict[str, Any]:
        """删除定时任务。

        参数:
            timer_id: 定时任务 ID

        返回:
            Dict[str, Any]: 执行结果
        """
        if not timer_id:
            return {"success": False, "stdout": "", "stderr": "timer_id is required"}

        result = self._request_gateway(
            method="DELETE",
            path=f"/api/timers/{timer_id}",
            error_prefix=f"Failed to delete timer {timer_id}",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }
            return {
                "success": True,
                "stdout": json.dumps({"deleted": timer_id}, ensure_ascii=False),
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}

    def _create_group(
        self, group_name: Optional[str] = None, group_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建群组。

        参数:
            group_name: 群组名称
            group_description: 群组描述

        返回:
            Dict[str, Any]: 执行结果
        """
        if not group_name:
            return {"success": False, "stdout": "", "stderr": "group_name is required"}

        result = self._request_gateway(
            method="POST",
            path="/api/groups",
            json_data={"name": group_name, "description": group_description},
            error_prefix="Failed to create group",
        )

        return self._handle_gateway_response(result)

    def _list_groups(self) -> Dict[str, Any]:
        """查询所有群组。

        返回:
            Dict[str, Any]: 执行结果
        """
        result = self._request_gateway(
            method="GET",
            path="/api/groups",
            error_prefix="Failed to list groups",
        )

        return self._handle_gateway_response(result)

    def _get_group(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """查询群组详情。

        参数:
            group_id: 群组 ID

        返回:
            Dict[str, Any]: 执行结果
        """
        if not group_id:
            return {"success": False, "stdout": "", "stderr": "group_id is required"}

        result = self._request_gateway(
            method="GET",
            path=f"/api/groups/{group_id}",
            error_prefix=f"Failed to get group {group_id}",
        )

        return self._handle_gateway_response(result)

    def _join_group(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """加入群组。

        参数:
            group_id: 群组 ID

        返回:
            Dict[str, Any]: 执行结果
        """
        if not group_id:
            return {"success": False, "stdout": "", "stderr": "group_id is required"}

        result = self._request_gateway(
            method="POST",
            path=f"/api/groups/{group_id}/join",
            error_prefix=f"Failed to join group {group_id}",
        )

        return self._handle_gateway_response(result)

    def _leave_group(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """退出群组。

        参数:
            group_id: 群组 ID

        返回:
            Dict[str, Any]: 执行结果
        """
        if not group_id:
            return {"success": False, "stdout": "", "stderr": "group_id is required"}

        result = self._request_gateway(
            method="POST",
            path=f"/api/groups/{group_id}/leave",
            error_prefix=f"Failed to leave group {group_id}",
        )

        return self._handle_gateway_response(result)

    def _send_group_message(
        self, group_id: Optional[str] = None, message: str = ""
    ) -> Dict[str, Any]:
        """发送群组消息。

        参数:
            group_id: 群组 ID
            message: 消息内容

        返回:
            Dict[str, Any]: 执行结果
        """
        if not group_id:
            return {"success": False, "stdout": "", "stderr": "group_id is required"}
        if not message:
            return {"success": False, "stdout": "", "stderr": "message is required"}

        # 获取当前 Agent ID 作为发送者
        sender_id = jglobals.agent_id
        if not sender_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Current agent_id is not set",
            }

        # 在消息末尾添加回复提示
        enhanced_message = f"{message}\n\n---\n回复此群组消息请使用: gateway_manager action=send_group_message group_id={group_id} message=<你的回复>"

        result = self._request_gateway(
            method="POST",
            path=f"/api/groups/{group_id}/message",
            json_data={"sender_id": sender_id, "content": enhanced_message},
            error_prefix=f"Failed to send message to group {group_id}",
        )

        if result["success"]:
            gateway_data = result["data"]
            if not gateway_data.get("success"):
                error_info = gateway_data.get("error", {})
                error_msg = (
                    error_info.get("message", "unknown error")
                    if isinstance(error_info, dict)
                    else str(error_info)
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Gateway returned error: {error_msg}",
                }
            stdout_str = json.dumps(gateway_data.get("data", {}), ensure_ascii=False)
            stdout_str += "\n\nIf you want to wait for a response, output <Wait>."
            return {
                "success": True,
                "stdout": stdout_str,
                "stderr": "",
            }
        else:
            return {"success": False, "stdout": "", "stderr": result["error"]}
