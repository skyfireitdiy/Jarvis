import json
import subprocess
from typing import Dict, Any, List, Optional
import ollama
from tools import ToolRegistry
from utils import Spinner, PrettyOutput, OutputType
import re

class OllamaAgent:
    def __init__(self, model_name: str, api_base: str = "http://localhost:11434"):
        self.model_name = model_name
        self.api_base = api_base
        # 创建 Ollama 客户端
        self.client = ollama.Client(host=api_base)
        # 编译正则表达式
        self.tool_call_pattern = re.compile(r'<tool_call>\s*({[^}]+})\s*</tool_call>')
        self.messages = [
            {
                "role": "system",
                "content": """你是一个严谨的AI助手，所有数据必须通过工具获取，不允许捏造或猜测数据。
                
                工作原则：
                1. 使用search工具获取事实信息
                2. 使用execute_shell获取系统信息
                3. 使用execute_python处理数据
                4. 如果缺少信息，使用ask_user询问
                5. 在给出答案前，必须说明数据来源
                6. 对于search返回的网页链接，可以使用read_webpage工具获取详细内容
                
                工具使用建议：
                1. 先用search工具搜索相关信息
                2. 如果搜索结果中有感兴趣的网页，使用read_webpage工具读取其内容
                3. 根据网页内容提供更详细的答案
                
                禁止事项：
                1. 不要猜测或捏造数据
                2. 不要使用未经验证的信息
                3. 如果工具执行失败，要说明原因
                4. 如果无法获取数据，要诚实告知
                
                工具调用格式：
                <tool_call>
                {
                    "name": "工具名称",
                    "arguments": {
                        "参数1": "值1",
                        "参数2": "值2"
                    }
                }
                </tool_call>
                
                示例：
                1. 搜索并读取网页：
                <tool_call>
                {
                    "name": "search",
                    "arguments": {
                        "query": "Python GIL",
                        "max_results": 3
                    }
                }
                </tool_call>
                
                对感兴趣的搜索结果使用read_webpage：
                <tool_call>
                {
                    "name": "read_webpage",
                    "arguments": {
                        "url": "https://example.com/python-gil",
                        "extract_type": "all"
                    }
                }
                </tool_call>"""
            }
        ]
        self.tool_registry = ToolRegistry()
        self.spinner = Spinner()

    def _call_ollama(self, messages: List[Dict], use_tools: bool = True) -> Dict:
        """调用Ollama API获取响应"""
        self.spinner.start()
        try:
            # 准备请求参数
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                tools=self.tool_registry.get_all_tools() if use_tools else None
            )
            
            # 转换响应格式以保持兼容性
            return {
                "message": {
                    "content": response.message.content if response.message else "",
                    "tool_calls": response.message.tool_calls if response.message else []
                }
            }
        except Exception as e:
            raise Exception(f"Ollama API调用失败: {str(e)}")
        finally:
            self.spinner.stop()

    def handle_tool_calls(self, tool_calls: List[Dict]) -> str:
        """处理工具调用"""
        results = []
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]
            # 打印工具调用信息
            PrettyOutput.print(f"调用工具: {name}", OutputType.INFO)
            if isinstance(args, dict):
                for key, value in args.items():
                    PrettyOutput.print(f"  - {key}: {value}", OutputType.INFO)
            else:
                PrettyOutput.print(f"  参数: {args}", OutputType.INFO)
            PrettyOutput.print("", OutputType.INFO)  # 空行
            
            result = self.tool_registry.execute_tool(name, args)
            if result["success"]:
                output = f"执行结果:\n{result['stdout']}"
                if result.get("stderr"):
                    output += f"\n错误: {result['stderr']}"
            else:
                output = f"执行失败: {result['error']}"
            results.append(output)
        return "\n".join(results)

    def _extract_tool_calls(self, content: str) -> List[Dict]:
        """从内容中提取工具调用"""
        tool_calls = []
        # 修改正则表达式以更好地处理多行内容
        pattern = re.compile(
            r'<tool_call>\s*({(?:[^{}]|(?:{[^{}]*})|(?:{(?:[^{}]|{[^{}]*})*}))*})\s*</tool_call>',
            re.DOTALL  # 添加DOTALL标志以匹配跨行内容
        )
        
        matches = pattern.finditer(content)
        for match in matches:
            try:
                tool_call_str = match.group(1).strip()
                tool_call = json.loads(tool_call_str)
                if isinstance(tool_call, dict) and "name" in tool_call and "arguments" in tool_call:
                    tool_calls.append({
                        "function": {
                            "name": tool_call["name"],
                            "arguments": tool_call["arguments"]
                        }
                    })
                else:
                    PrettyOutput.print(f"无效的工具调用格式: {tool_call_str}", OutputType.ERROR)
            except json.JSONDecodeError as e:
                PrettyOutput.print(f"JSON解析错误: {str(e)}", OutputType.ERROR)
                PrettyOutput.print(f"解析内容: {tool_call_str}", OutputType.ERROR)
                continue
        
        return tool_calls

    def run(self, user_input: str) -> str:
        """处理用户输入并返回响应"""
        # 检查是否是结束命令
        self.clear_history()
        while True:
            if user_input.strip().lower() == "finish" or user_input.strip().lower() == "":
                # 获取最终确认
                try:
                    result = self.tool_registry.execute_tool(
                        "ask_user_confirmation",
                        {
                            "question": "确认要结束当前任务吗？",
                            "details": "输入'y'确认结束，'n'继续任务"
                        }
                    )
                    if result["success"] and result["stdout"] == "yes":
                        return "任务已完成，期待下次为您服务！"
                    else:
                        return "好的，让我们继续完成任务。"
                except Exception:
                    return "任务已完成，期待下次为您服务！"

            # 添加用户输入到对话历史
            self.messages.append({
                "role": "user",
                "content": user_input
            })
            
            try:
                outputs = []
                
                # 获取初始响应
                response = self._call_ollama(self.messages)
                current_response = response
                
                # 处理可能的多轮工具调用
                while "tool_calls" in current_response["message"] and \
                    current_response["message"]["tool_calls"] is not None and \
                    len(current_response["message"]["tool_calls"]) > 0:
                    # 添加当前助手响应到输出（如果有内容）
                    if current_response["message"].get("content"):
                        PrettyOutput.print(current_response["message"]["content"], OutputType.SYSTEM)
                        outputs.append(current_response["message"]["content"])
                    
                    # 处理工具调用
                    tool_result = self.handle_tool_calls(current_response["message"]["tool_calls"])
                    PrettyOutput.print(tool_result, OutputType.RESULT)
                    outputs.append(tool_result)
                    
                    # 将工具执行结果添加到对话
                    self.messages.append({
                        "role": "assistant",
                        "content": response["message"].get("content", ""),
                        "tool_calls": current_response["message"]["tool_calls"]
                    })
                    self.messages.append({
                        "role": "tool",
                        "content": tool_result
                    })
                    
                    # 获取下一轮响应
                    current_response = self._call_ollama(self.messages)
                
                # 添加最终响应到对话历史和输出
                final_content = current_response["message"].get("content", "")
                # 检查内容中是否有工具调用标记
                if final_content:
                    tool_calls = self._extract_tool_calls(final_content)
                    if tool_calls:
                        # 从内容中移除工具调用标记
                        clean_content = self.tool_call_pattern.sub("", final_content).strip()
                        if clean_content:
                            PrettyOutput.print(clean_content, OutputType.SYSTEM)
                            outputs.append(clean_content)
                        
                        # 处理工具调用
                        tool_result = self.handle_tool_calls(tool_calls)
                        PrettyOutput.print(tool_result, OutputType.RESULT)
                        outputs.append(tool_result)
                        
                        # 将工具执行结果添加到对话
                        self.messages.append({
                            "role": "assistant",
                            "content": clean_content,
                            "tool_calls": tool_calls
                        })
                        self.messages.append({
                            "role": "tool",
                            "content": tool_result
                        })
                        
                        # 获取新的响应
                        current_response = self._call_ollama(self.messages)
                        final_content = current_response["message"].get("content", "")
                
                if final_content:
                    PrettyOutput.print(final_content, OutputType.SYSTEM)
                    outputs.append(final_content)
                
                # 如果没有工具调用且响应很短，可能需要继续对话
                PrettyOutput.print("\n您可以继续输入，或输入'finish'或者直接回车结束当前任务", OutputType.INFO)
                PrettyOutput.print("\n请输入您的回答:", OutputType.INFO)
                user_input = input(">>> ").strip()
                if user_input.strip().lower() == "finish" or user_input.strip().lower() == "":
                    break
                
            except Exception as e:
                error_msg = f"处理响应时出错: {str(e)}"
                PrettyOutput.print(error_msg, OutputType.ERROR)
                return error_msg

    def clear_history(self):
        """清除对话历史，只保留系统提示"""
        self.messages = [self.messages[0]] 