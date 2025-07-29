# -*- coding: utf-8 -*-
import json
import threading
from typing import Any, Callable, Dict, List
from urllib.parse import urljoin

import requests

from jarvis.jarvis_mcp import McpClient
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class StreamableMcpClient(McpClient):
    """Streamable HTTP MCP客户端实现

    参数:
        config: 配置字典，包含以下字段：
            - base_url: str - MCP服务器的基础URL
            - auth_token: str - 认证令牌（可选）
            - headers: Dict[str, str] - 额外的HTTP头（可选）
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get("base_url", "")
        if not self.base_url:
            raise ValueError("No base_url specified in config")

        # 设置HTTP客户端
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

        # 添加认证令牌（如果提供）
        auth_token = config.get("auth_token")
        if auth_token:
            self.session.headers["Authorization"] = f"Bearer {auth_token}"

        # 添加额外的HTTP头
        extra_headers = config.get("headers", {})
        self.session.headers.update(extra_headers)

        # 请求相关属性
        self.pending_requests: Dict[str, threading.Event] = {}  # 存储等待响应的请求 {id: Event}
        self.request_results: Dict[str, Dict[str, Any]] = {}  # 存储请求结果 {id: result}
        self.notification_handlers: Dict[str, List[Callable]] = {}
        self.event_lock = threading.Lock()
        self.request_id_counter = 0

        # 初始化连接
        self._initialize()

    def _initialize(self) -> None:
        """初始化MCP连接"""
        try:
            # 发送初始化请求
            response = self._send_request(
                "initialize",
                {
                    "processId": None,  # 远程客户端不需要进程ID
                    "clientInfo": {"name": "jarvis", "version": "1.0.0"},
                    "capabilities": {},
                    "protocolVersion": "2025-03-26",
                },
            )

            # 验证服务器响应
            if "result" not in response:
                raise RuntimeError(f"初始化失败: {response.get('error', 'Unknown error')}")

            # 发送initialized通知
            self._send_notification("notifications/initialized", {})

        except Exception as e:
            PrettyOutput.print(f"MCP初始化失败: {str(e)}", OutputType.ERROR)
            raise

    def register_notification_handler(self, method: str, handler: Callable) -> None:
        """注册通知处理器

        参数:
            method: 通知方法名
            handler: 处理通知的回调函数，接收params参数
        """
        with self.event_lock:
            if method not in self.notification_handlers:
                self.notification_handlers[method] = []
            self.notification_handlers[method].append(handler)

    def unregister_notification_handler(self, method: str, handler: Callable) -> None:
        """注销通知处理器

        参数:
            method: 通知方法名
            handler: 要注销的处理器函数
        """
        with self.event_lock:
            if method in self.notification_handlers:
                if handler in self.notification_handlers[method]:
                    self.notification_handlers[method].remove(handler)
                if not self.notification_handlers[method]:
                    del self.notification_handlers[method]

    def _get_next_request_id(self) -> str:
        """获取下一个请求ID"""
        with self.event_lock:
            self.request_id_counter += 1
            return str(self.request_id_counter)

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到MCP服务器

        参数:
            method: 请求方法
            params: 请求参数

        返回:
            Dict[str, Any]: 响应结果
        """
        # 生成唯一请求ID
        req_id = self._get_next_request_id()

        # 创建事件标志，用于等待响应
        event = threading.Event()

        with self.event_lock:
            self.pending_requests[req_id] = event

        try:
            # 构建请求
            request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": req_id,
            }

            # 发送请求到Streamable HTTP端点
            mcp_url = urljoin(self.base_url, "mcp")
            response = self.session.post(mcp_url, json=request, stream=True)  # 启用流式传输
            response.raise_for_status()

            # 处理流式响应
            result = None
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    try:
                        data = json.loads(line)
                        if "id" in data and data["id"] == req_id:
                            # 这是我们的请求响应
                            result = data
                            break
                        elif "method" in data:
                            # 这是一个通知
                            method = data.get("method", "")
                            params = data.get("params", {})
                            if method in self.notification_handlers:
                                for handler in self.notification_handlers[method]:
                                    try:
                                        handler(params)
                                    except Exception as e:
                                        PrettyOutput.print(
                                            f"处理通知时出错 ({method}): {e}",
                                            OutputType.ERROR,
                                        )
                    except json.JSONDecodeError:
                        PrettyOutput.print(f"无法解析响应: {line}", OutputType.WARNING)
                        continue

            if result is None:
                raise RuntimeError(f"未收到响应: {method}")

            return result

        except Exception as e:
            PrettyOutput.print(f"发送请求失败: {str(e)}", OutputType.ERROR)
            raise
        finally:
            # 清理请求状态
            with self.event_lock:
                self.pending_requests.pop(req_id, None)
                self.request_results.pop(req_id, None)

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """发送通知到MCP服务器（不需要响应）

        参数:
            method: 通知方法
            params: 通知参数
        """
        try:
            # 构建通知
            notification = {"jsonrpc": "2.0", "method": method, "params": params}

            # 发送通知到Streamable HTTP端点
            mcp_url = urljoin(self.base_url, "mcp")
            response = self.session.post(mcp_url, json=notification)
            response.raise_for_status()

        except Exception as e:
            PrettyOutput.print(f"发送通知失败: {str(e)}", OutputType.ERROR)
            raise

    def get_tool_list(self) -> List[Dict[str, Any]]:
        """获取工具列表

        返回:
            List[Dict[str, Any]]: 工具列表，每个工具包含以下字段：
                - name: str - 工具名称
                - description: str - 工具描述
                - parameters: Dict - 工具参数
        """
        try:
            response = self._send_request("tools/list", {})
            if "result" in response and "tools" in response["result"]:
                # 注意这里: 响应结构是 response['result']['tools']
                tools = response["result"]["tools"]
                # 将MCP协议字段转换为内部格式
                formatted_tools = []
                for tool in tools:
                    # 从inputSchema中提取参数定义
                    input_schema = tool.get("inputSchema", {})
                    parameters = {}
                    if "properties" in input_schema:
                        parameters = input_schema["properties"]

                    formatted_tools.append(
                        {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": parameters,
                        }
                    )
                return formatted_tools
            else:
                error_msg = "获取工具列表失败"
                if "error" in response:
                    error_msg += f": {response['error']}"
                elif "result" in response:
                    error_msg += f": 响应格式不正确 - {response['result']}"
                else:
                    error_msg += ": 未知错误"

                PrettyOutput.print(error_msg, OutputType.ERROR)
                return []
        except Exception as e:
            PrettyOutput.print(f"获取工具列表失败: {str(e)}", OutputType.ERROR)
            return []

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具

        参数:
            tool_name: 工具名称
            arguments: 参数字典，包含工具执行所需的参数

        返回:
            Dict[str, Any]: 执行结果，包含以下字段：
                - success: bool - 是否执行成功
                - stdout: str - 标准输出
                - stderr: str - 标准错误
        """
        try:
            response = self._send_request(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )
            if "result" in response:
                result = response["result"]
                # 从content中提取输出信息
                stdout = ""
                stderr = ""
                for content in result.get("content", []):
                    if content.get("type") == "text":
                        stdout += content.get("text", "")
                    elif content.get("type") == "error":
                        stderr += content.get("text", "")

                return {"success": True, "stdout": stdout, "stderr": stderr}
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": response.get("error", "Unknown error"),
                }
        except Exception as e:
            PrettyOutput.print(f"执行工具失败: {str(e)}", OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": str(e)}

    def get_resource_list(self) -> List[Dict[str, Any]]:
        """获取资源列表

        返回:
            List[Dict[str, Any]]: 资源列表，每个资源包含以下字段：
                - uri: str - 资源的唯一标识符
                - name: str - 资源的名称
                - description: str - 资源的描述（可选）
                - mimeType: str - 资源的MIME类型（可选）
        """
        try:
            response = self._send_request("resources/list", {})
            if "result" in response and "resources" in response["result"]:
                return response["result"]["resources"]
            else:
                error_msg = "获取资源列表失败"
                if "error" in response:
                    error_msg += f": {response['error']}"
                else:
                    error_msg += ": 未知错误"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return []
        except Exception as e:
            PrettyOutput.print(f"获取资源列表失败: {str(e)}", OutputType.ERROR)
            return []

    def get_resource(self, uri: str) -> Dict[str, Any]:
        """获取指定资源的内容

        参数:
            uri: str - 资源的URI标识符

        返回:
            Dict[str, Any]: 执行结果，包含以下字段：
                - success: bool - 是否执行成功
                - stdout: str - 资源内容（文本或base64编码的二进制内容）
                - stderr: str - 错误信息
        """
        try:
            response = self._send_request("resources/read", {"uri": uri})
            if "result" in response and "contents" in response["result"]:
                contents = response["result"]["contents"]
                if contents:
                    content = contents[0]  # 获取第一个资源内容
                    # 根据资源类型返回内容
                    if "text" in content:
                        return {
                            "success": True,
                            "stdout": content["text"],
                            "stderr": "",
                        }
                    elif "blob" in content:
                        return {
                            "success": True,
                            "stdout": content["blob"],
                            "stderr": "",
                        }
                return {"success": False, "stdout": "", "stderr": "资源内容为空"}
            else:
                error_msg = "获取资源内容失败"
                if "error" in response:
                    error_msg += f": {response['error']}"
                else:
                    error_msg += ": 未知错误"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return {"success": False, "stdout": "", "stderr": error_msg}
        except Exception as e:
            error_msg = f"获取资源内容失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {"success": False, "stdout": "", "stderr": error_msg}

    def __del__(self):
        """清理资源"""
        # 清理请求状态
        with self.event_lock:
            for event in self.pending_requests.values():
                event.set()  # 释放所有等待的请求
            self.pending_requests.clear()
            self.request_results.clear()

        # 关闭HTTP会话
        if self.session:
            self.session.close()
