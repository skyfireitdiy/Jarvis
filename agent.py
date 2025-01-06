import json
import subprocess
from typing import Dict, Any, List, Optional
from tools import ToolRegistry
from utils import Spinner, PrettyOutput, OutputType, get_multiline_input
from models import BaseModel, OllamaModel
import re

class Agent:
    def __init__(self, model: BaseModel, tool_registry: ToolRegistry):
        self.model = model
        self.tool_registry = tool_registry
        # 编译正则表达式
        self.tool_call_pattern = re.compile(r'<tool_call>\s*({[^}]+})\s*</tool_call>')
        self.messages = [
            {
                "role": "system",
                "content": """你是一个严谨的AI助手，所有数据必须通过工具获取，不允许捏造或猜测数据。""" + "\n" + self.tool_registry.tool_help_text()
            }
        ]
        self.spinner = Spinner()

    def _call_model(self, messages: List[Dict], use_tools: bool = True) -> Dict:
        """调用模型获取响应"""
        self.spinner.start()
        try:
            return self.model.chat(
                messages=messages,
                tools=self.tool_registry.get_all_tools() if use_tools else None
            )
        except Exception as e:
            raise Exception(f"模型调用失败: {str(e)}")
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


    def run(self, user_input: str) :
        """处理用户输入并返回响应"""
        # 检查是否是结束命令
        self.clear_history()
        self.messages.append({
            "role": "user",
            "content": user_input
        })
        while True:
            try:
                # 获取初始响应
                response = self._call_model(self.messages)
                current_response = response

                # 将工具执行结果添加到对话
                self.messages.append({
                    "role": "assistant",
                    "content": response["message"].get("content", ""),
                    "tool_calls": current_response["message"]["tool_calls"]
                })
                
                # 处理可能的多轮工具调用
                if len(current_response["message"]["tool_calls"]) > 0:
                    # 添加当前助手响应到输出（如果有内容）
                    if current_response["message"].get("content"):
                        PrettyOutput.print(current_response["message"]["content"], OutputType.SYSTEM)
                        
                    # 处理工具调用
                    tool_result = self.handle_tool_calls(current_response["message"]["tool_calls"])
                    PrettyOutput.print(tool_result, OutputType.RESULT)

                    self.messages.append({
                        "role": "tool",
                        "content": tool_result
                    })
                    continue
                
                # 添加最终响应到对话历史和输出
                final_content = current_response["message"].get("content", "")
                
                if final_content:
                    PrettyOutput.print(final_content, OutputType.SYSTEM)
                    
                
                # 如果没有工具调用且响应很短，可能需要继续对话
                PrettyOutput.print("\n您可以继续输入，或输入空行或'finish'结束当前任务", OutputType.INFO)
                user_input = get_multiline_input()
                if user_input == "finish" or not user_input:
                    break
                
                self.messages.append({
                    "role": "user",
                    "content": user_input
                })
                
            except Exception as e:
                error_msg = f"处理响应时出错: {str(e)}"
                PrettyOutput.print(error_msg, OutputType.ERROR)

    def clear_history(self):
        """清除对话历史，只保留系统提示"""
        self.messages = [self.messages[0]] 