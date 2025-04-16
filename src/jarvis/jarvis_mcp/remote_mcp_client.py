from typing import Any, Dict, List
import requests
from urllib.parse import urljoin
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from . import McpClient


class RemoteMcpClient(McpClient):
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
        self.sse_stream = None
        self._initialize()

    def _initialize(self) -> None:
        """初始化MCP连接"""
        try:
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

            result = response['result']
            
            # 发送initialized通知
            self._send_notification('notifications/initialized', {})

            # 建立SSE连接
            sse_url = urljoin(self.base_url, 'sse')
            self.sse_stream = self.session.get(sse_url, stream=True)
            self.sse_stream.raise_for_status()

        except Exception as e:
            PrettyOutput.print(f"MCP初始化失败: {str(e)}", OutputType.ERROR)
            raise

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到MCP服务器
        
        参数:
            method: 请求方法
            params: 请求参数
            
        返回:
            Dict[str, Any]: 响应结果
        """
        try:
            # 构建请求
            request = {
                'jsonrpc': '2.0',
                'method': method,
                'params': params,
                'id': 1
            }

            # 发送请求
            response = self.session.post(
                urljoin(self.base_url, 'sse'),
                json=request
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
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

            # 发送通知
            response = self.session.post(
                urljoin(self.base_url, 'sse'),
                json=notification
            )
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
        if self.sse_stream:
            self.sse_stream.close()
        if self.session:
            self.session.close()
