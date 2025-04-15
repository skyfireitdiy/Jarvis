from typing import Any, Dict, List
import requests
import sseclient
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
        
        # 初始化SSE连接
        self.sse_client = None
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

            # 建立SSE连接
            sse_url = urljoin(self.base_url, 'events')
            response = self.session.get(sse_url, stream=True)
            self.sse_client = sseclient.SSEClient(response)

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
                urljoin(self.base_url, 'rpc'),
                json=request
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            PrettyOutput.print(f"发送请求失败: {str(e)}", OutputType.ERROR)
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
            if 'result' in response:
                tools = response['result']
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
                PrettyOutput.print(f"获取工具列表失败: {response.get('error', 'Unknown error')}", OutputType.ERROR)
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

    def __del__(self):
        """清理资源"""
        if self.sse_client and hasattr(self.sse_client, 'resp'):
            self.sse_client.resp.close()
        if self.session:
            self.session.close()
