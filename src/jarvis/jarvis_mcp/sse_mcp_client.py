from typing import Any, Dict, List, Callable
import requests
import json
import threading
import time
from urllib.parse import urljoin, urlencode, parse_qs
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_mcp import McpClient


class SSEMcpClient(McpClient):
    """远程MCP客户端实现
    
    参数:
        config: 配置字典，包含以下字段：
            - base_url: str - MCP服务器的基础URL
            - auth_token: str - 认证令牌（可选）
            - headers: Dict[str, str] - 额外的HTTP头（可选）
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get('base_url', '')
        if not self.base_url:
            raise ValueError('No base_url specified in config')
        
        # 设置HTTP客户端
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
        
        # 添加认证令牌（如果提供）
        auth_token = config.get('auth_token')
        if auth_token:
            self.session.headers['Authorization'] = f'Bearer {auth_token}'
        
        # 添加额外的HTTP头
        extra_headers = config.get('headers', {})
        self.session.headers.update(extra_headers)
        
        # SSE相关属性
        self.sse_response = None
        self.sse_thread = None
        self.messages_endpoint = None
        self.session_id = None      # 从SSE连接获取的会话ID
        self.pending_requests = {}  # 存储等待响应的请求 {id: Event}
        self.request_results = {}   # 存储请求结果 {id: result}
        self.notification_handlers = {}
        self.event_lock = threading.Lock()
        self.request_id_counter = 0
        
        # 初始化连接
        self._initialize()

    def _initialize(self) -> None:
        """初始化MCP连接"""
        try:
            # 启动SSE连接
            self._start_sse_connection()
            
            # 等待获取消息端点和会话ID
            start_time = time.time()
            while (not self.messages_endpoint or not self.session_id) and time.time() - start_time < 5:
                time.sleep(0.1)
                
            if not self.messages_endpoint:
                self.messages_endpoint = "/messages"  # 默认端点
                PrettyOutput.print(f"未获取到消息端点，使用默认值: {self.messages_endpoint}", OutputType.WARNING)
                
            if not self.session_id:
                PrettyOutput.print("未获取到会话ID", OutputType.WARNING)
            
            # 发送初始化请求
            response = self._send_request('initialize', {
                'processId': None,  # 远程客户端不需要进程ID
                'clientInfo': {
                    'name': 'jarvis',
                    'version': '1.0.0'
                },
                'capabilities': {},
                'protocolVersion': "2025-03-26"
            })

            # 验证服务器响应
            if 'result' not in response:
                raise RuntimeError(f"初始化失败: {response.get('error', 'Unknown error')}")

            # 发送initialized通知
            self._send_notification('notifications/initialized', {})

        except Exception as e:
            PrettyOutput.print(f"MCP初始化失败: {str(e)}", OutputType.ERROR)
            raise

    def _start_sse_connection(self) -> None:
        """建立SSE连接并启动处理线程"""
        try:
            # 设置SSE请求头
            sse_headers = dict(self.session.headers)
            sse_headers.update({
                'Accept': 'text/event-stream',
                'Cache-Control': 'no-cache',
            })
            
            # 建立SSE连接
            sse_url = urljoin(self.base_url, 'sse')
            self.sse_response = self.session.get(
                sse_url, 
                stream=True, 
                headers=sse_headers,
                timeout=30
            )
            self.sse_response.raise_for_status()
            
            # 启动事件处理线程
            self.sse_thread = threading.Thread(target=self._process_sse_events, daemon=True)
            self.sse_thread.start()
            
        except Exception as e:
            PrettyOutput.print(f"SSE连接失败: {str(e)}", OutputType.ERROR)
            raise
    
    def _process_sse_events(self) -> None:
        """处理SSE事件流"""
        if not self.sse_response:
            return
            
        buffer = ""
        for line in self.sse_response.iter_lines(decode_unicode=True):
            if line:
                if line.startswith("data:"):
                    data = line[5:].strip()
                    # 检查是否包含消息端点信息
                    if data.startswith('/'):
                        # 这是消息端点信息，例如 "/messages/?session_id=xyz"
                        try:
                            # 提取消息端点路径和会话ID
                            url_parts = data.split('?')
                            self.messages_endpoint = url_parts[0]
                            
                            # 如果有查询参数，尝试提取session_id
                            if len(url_parts) > 1:
                                query_string = url_parts[1]
                                query_params = parse_qs(query_string)
                                if 'session_id' in query_params:
                                    self.session_id = query_params['session_id'][0]
                        except Exception as e:
                            PrettyOutput.print(f"解析消息端点或会话ID失败: {e}", OutputType.WARNING)
                    else:
                        buffer += data
                elif line.startswith(":"):  # 忽略注释行
                    continue
                elif line.startswith("event:"):  # 事件类型
                    continue  # 我们不使用事件类型
                elif line.startswith("id:"):  # 事件ID
                    continue  # 我们不使用事件ID
                elif line.startswith("retry:"):  # 重连时间
                    continue  # 我们自己管理重连
            else:  # 空行表示事件结束
                if buffer:
                    try:
                        self._handle_sse_event(buffer)
                    except Exception as e:
                        PrettyOutput.print(f"处理SSE事件出错: {e}", OutputType.ERROR)
                    buffer = ""
        
        PrettyOutput.print("SSE连接已关闭", OutputType.WARNING)

    def _handle_sse_event(self, data: str) -> None:
        """处理单个SSE事件数据"""
        try:
            event_data = json.loads(data)
            
            # 检查是请求响应还是通知
            if 'id' in event_data:
                # 这是一个请求的响应
                req_id = event_data['id']
                with self.event_lock:
                    self.request_results[req_id] = event_data
                    if req_id in self.pending_requests:
                        # 通知等待线程响应已到达
                        self.pending_requests[req_id].set()
            elif 'method' in event_data:
                # 这是一个通知
                method = event_data.get('method', '')
                params = event_data.get('params', {})
                
                # 调用已注册的处理器
                if method in self.notification_handlers:
                    for handler in self.notification_handlers[method]:
                        try:
                            handler(params)
                        except Exception as e:
                            PrettyOutput.print(
                                f"处理通知时出错 ({method}): {e}", 
                                OutputType.ERROR
                            )
        except json.JSONDecodeError:
            PrettyOutput.print(f"无法解析SSE事件: {data}", OutputType.WARNING)
        except Exception as e:
            PrettyOutput.print(f"处理SSE事件时出错: {e}", OutputType.ERROR)

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
                'jsonrpc': '2.0',
                'method': method,
                'params': params,
                'id': req_id
            }

            # 尝试不同的请求发送方式
            if self.session_id:
                # 方法1: 使用查询参数中的session_id
                query_params = {'session_id': self.session_id}
                messages_url = urljoin(self.base_url, self.messages_endpoint)
                
                # 尝试直接使用原始URL（不追加查询参数）
                try:
                    post_response = self.session.post(
                        messages_url,
                        json=request
                    )
                    post_response.raise_for_status()
                except requests.HTTPError:
                    # 如果失败，尝试添加会话ID到查询参数
                    messages_url_with_session = f"{messages_url}?{urlencode(query_params)}"
                    post_response = self.session.post(
                        messages_url_with_session,
                        json=request
                    )
                    post_response.raise_for_status()
            else:
                # 方法2: 不使用session_id
                if not self.messages_endpoint:
                    self.messages_endpoint = "/messages"
                
                messages_url = urljoin(self.base_url, self.messages_endpoint)
                
                # 尝试直接使用messages端点而不带任何查询参数
                try:
                    # 尝试1: 标准JSON-RPC格式
                    post_response = self.session.post(
                        messages_url,
                        json=request
                    )
                    post_response.raise_for_status()
                except requests.HTTPError:
                    # 尝试2: JSON字符串作为请求参数
                    post_response = self.session.post(
                        messages_url,
                        params={'request': json.dumps(request)}
                    )
                    post_response.raise_for_status()
            
            # 等待SSE通道返回响应（最多30秒）
            if not event.wait(timeout=30):
                raise TimeoutError(f"等待响应超时: {method}")
            
            # 获取响应结果
            with self.event_lock:
                result = self.request_results.pop(req_id, None)
                self.pending_requests.pop(req_id, None)
            
            if result is None:
                raise RuntimeError(f"未收到响应: {method}")
                
            return result

        except Exception as e:
            # 清理请求状态
            with self.event_lock:
                self.pending_requests.pop(req_id, None)
                self.request_results.pop(req_id, None)
                
            PrettyOutput.print(f"发送请求失败: {str(e)}", OutputType.ERROR)
            raise

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """发送通知到MCP服务器（不需要响应）
        
        参数:
            method: 通知方法
            params: 通知参数
        """
        try:
            # 构建通知
            notification = {
                'jsonrpc': '2.0',
                'method': method,
                'params': params
            }

            # 尝试不同的请求发送方式，与_send_request保持一致
            if self.session_id:
                # 方法1: 使用查询参数中的session_id
                query_params = {'session_id': self.session_id}
                messages_url = urljoin(self.base_url, self.messages_endpoint or '/messages')
                
                # 尝试直接使用原始URL（不追加查询参数）
                try:
                    post_response = self.session.post(
                        messages_url,
                        json=notification
                    )
                    post_response.raise_for_status()
                except requests.HTTPError:
                    # 如果失败，尝试添加会话ID到查询参数
                    messages_url_with_session = f"{messages_url}?{urlencode(query_params)}"
                    post_response = self.session.post(
                        messages_url_with_session,
                        json=notification
                    )
                    post_response.raise_for_status()
            else:
                # 方法2: 不使用session_id
                if not self.messages_endpoint:
                    self.messages_endpoint = "/messages"
                
                messages_url = urljoin(self.base_url, self.messages_endpoint)
                
                # 尝试直接使用messages端点而不带任何查询参数
                try:
                    # 尝试1: 标准JSON-RPC格式
                    post_response = self.session.post(
                        messages_url,
                        json=notification
                    )
                    post_response.raise_for_status()
                except requests.HTTPError:
                    # 尝试2: JSON字符串作为请求参数
                    post_response = self.session.post(
                        messages_url,
                        params={'request': json.dumps(notification)}
                    )
                    post_response.raise_for_status()

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
            response = self._send_request('tools/list', {})
            if 'result' in response and 'tools' in response['result']:
                # 注意这里: 响应结构是 response['result']['tools']
                tools = response['result']['tools']
                # 将MCP协议字段转换为内部格式
                formatted_tools = []
                for tool in tools:
                    # 从inputSchema中提取参数定义
                    input_schema = tool.get('inputSchema', {})
                    parameters = {}
                    if 'properties' in input_schema:
                        parameters = input_schema['properties']
                    
                    formatted_tools.append({
                        'name': tool.get('name', ''),
                        'description': tool.get('description', ''),
                        'parameters': parameters
                    })
                return formatted_tools
            else:
                error_msg = "获取工具列表失败"
                if 'error' in response:
                    error_msg += f": {response['error']}"
                elif 'result' in response:
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
            response = self._send_request('tools/call', {
                'name': tool_name,
                'arguments': arguments
            })
            if 'result' in response:
                result = response['result']
                # 从content中提取输出信息
                stdout = ''
                stderr = ''
                for content in result.get('content', []):
                    if content.get('type') == 'text':
                        stdout += content.get('text', '')
                    elif content.get('type') == 'error':
                        stderr += content.get('text', '')
                
                return {
                    'success': True,
                    'stdout': stdout,
                    'stderr': stderr
                }
            else:
                return {
                    'success': False,
                    'stdout': '',
                    'stderr': response.get('error', 'Unknown error')
                }
        except Exception as e:
            PrettyOutput.print(f"执行工具失败: {str(e)}", OutputType.ERROR)
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e)
            }

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
            response = self._send_request('resources/list', {})
            if 'result' in response and 'resources' in response['result']:
                return response['result']['resources']
            else:
                error_msg = "获取资源列表失败"
                if 'error' in response:
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
            response = self._send_request('resources/read', {
                'uri': uri
            })
            if 'result' in response and 'contents' in response['result']:
                contents = response['result']['contents']
                if contents:
                    content = contents[0]  # 获取第一个资源内容
                    # 根据资源类型返回内容
                    if 'text' in content:
                        return {
                            'success': True,
                            'stdout': content['text'],
                            'stderr': ''
                        }
                    elif 'blob' in content:
                        return {
                            'success': True,
                            'stdout': content['blob'],
                            'stderr': ''
                        }
                return {
                    'success': False,
                    'stdout': '',
                    'stderr': '资源内容为空'
                }
            else:
                error_msg = "获取资源内容失败"
                if 'error' in response:
                    error_msg += f": {response['error']}"
                else:
                    error_msg += ": 未知错误"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return {
                    'success': False,
                    'stdout': '',
                    'stderr': error_msg
                }
        except Exception as e:
            error_msg = f"获取资源内容失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.ERROR)
            return {
                'success': False,
                'stdout': '',
                'stderr': error_msg
            }

    def __del__(self):
        """清理资源"""
        # 清理请求状态
        with self.event_lock:
            for event in self.pending_requests.values():
                event.set()  # 释放所有等待的请求
            self.pending_requests.clear()
            self.request_results.clear()
            
        # 关闭SSE响应
        if self.sse_response:
            try:
                self.sse_response.close()
            except:
                pass
                
        # 关闭HTTP会话
        if self.session:
            self.session.close()
