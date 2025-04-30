from typing import Any, Dict, List
import subprocess
import os
import json
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_mcp import McpClient


class StdioMcpClient(McpClient):
    """本地MCP客户端实现
    
    参数:
        config: 配置字典（command、args、env）
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.process = None
        self.protocol_version = "2025-03-26"  # MCP协议版本
        self._start_process()
        self._initialize()

    def _start_process(self) -> None:
        """启动MCP进程"""
        try:
            # 构建命令和参数
            command = self.config.get('command', '')
            if not command:
                raise ValueError('No command specified in config')

            # 获取参数列表
            args = self.config.get('args', [])
            if not isinstance(args, list):
                args = [str(args)]

            # 获取环境变量
            env = os.environ.copy()
            env.update(self.config.get('env', {}))

            # 启动进程
            self.process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True
            )

        except Exception as e:
            PrettyOutput.print(f"启动MCP进程失败: {str(e)}", OutputType.ERROR)
            raise

    def _initialize(self) -> None:
        """初始化MCP连接"""
        try:
            # 发送初始化请求
            response = self._send_request('initialize', {
                'processId': os.getpid(),
                'clientInfo': {
                    'name': 'jarvis',
                    'version': '1.0.0'
                },
                'capabilities': {},
                'protocolVersion': self.protocol_version
            })

            # 验证服务器响应
            if 'result' not in response:
                raise RuntimeError(f"初始化失败: {response.get('error', 'Unknown error')}")

            result = response['result']
            
            # 发送initialized通知 - 使用正确的方法名格式
            self._send_notification('notifications/initialized', {})

        except Exception as e:
            PrettyOutput.print(f"MCP初始化失败: {str(e)}", OutputType.ERROR)
            raise

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到MCP进程
        
        参数:
            method: 请求方法
            params: 请求参数
            
        返回:
            Dict[str, Any]: 响应结果
        """
        if not self.process:
            raise RuntimeError('MCP process not started')

        try:
            # 构建请求
            request = {
                'jsonrpc': '2.0',
                'method': method,
                'params': params,
                'id': 1
            }

            # 发送请求
            self.process.stdin.write(json.dumps(request) + '\n')  # type: ignore
            self.process.stdin.flush()  # type: ignore

            # 读取响应
            response = self.process.stdout.readline()  # type: ignore
            return json.loads(response)

        except Exception as e:
            PrettyOutput.print(f"发送请求失败: {str(e)}", OutputType.ERROR)
            raise

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """发送通知到MCP进程（不需要响应）
        
        参数:
            method: 通知方法
            params: 通知参数
        """
        if not self.process:
            raise RuntimeError('MCP process not started')

        try:
            # 构建通知
            notification = {
                'jsonrpc': '2.0',
                'method': method,
                'params': params
            }
            # 发送通知
            self.process.stdin.write(json.dumps(notification) + '\n')  # type: ignore
            self.process.stdin.flush()  # type: ignore

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
        if self.process:
            try:
                # 发送退出通知 - 使用通知而非请求
                self._send_notification('notifications/exit', {})
                # 等待进程结束
                self.process.wait(timeout=1)
            except:
                # 如果进程没有正常退出，强制终止
                self.process.kill()