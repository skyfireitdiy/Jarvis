import json
import subprocess
from typing import Dict, Any, List, Optional
from .tools import ToolRegistry
from .utils import Spinner, PrettyOutput, OutputType, get_multiline_input
from .models import BaseModel, OllamaModel
import re
import os
from datetime import datetime

class Agent:
    def __init__(self, model: BaseModel, tool_registry: ToolRegistry):
        self.model = model
        self.tool_registry = tool_registry
        # 编译正则表达式
        self.tool_call_pattern = re.compile(r'<tool_call>\s*({[^}]+})\s*</tool_call>')
        self.messages = [
            {
                "role": "system",
                "content": """You are a rigorous AI assistant, all data must be obtained through tools, and no fabrication or speculation is allowed. """ + "\n" + self.tool_registry.tool_help_text()
            }
        ]
        self.spinner = Spinner()

    def _compress_conversion(self, messages: List[Dict]) -> List[Dict]:
        """压缩对话历史，提取关键信息并生成新的压缩后的对话记录"""
        # 保留系统消息
        PrettyOutput.print("压缩对话历史", OutputType.INFO)
        compressed_messages = [messages[0]]
        
        # 构建提示信息，要求模型总结对话
        summary_prompt = {
            "role": "user",
            "content": """As we are approaching the token limit, please summarize the key points of our previous conversation, including:

1. User's main questions and requirements
2. Key information that has been confirmed
3. Important tool calls that were executed and their results
4. Outstanding issues that need to be addressed

Please organize the information in concise bullet points, ensuring no critical information is lost. This summary will serve as the new context for our conversation."""
        }
        
        # 调用模型生成总结
        summary_response = self._call_model(messages + [summary_prompt], use_tools=False)
        summary_content = summary_response["message"].get("content", "")
        
        # 添加压缩后的上下文消息
        compressed_messages.append({
            "role": "system",
            "content": f"Summary of previous conversation:\n{summary_content}"
        })
        
        return compressed_messages
            


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
                stdout = result["stdout"]
                stderr = result.get("stderr", "")
                
                # 如果任一输出超过1024字符，则保存到文件
                if len(stdout) > 1024 or len(stderr) > 1024:
                    output = save_long_output(stdout, stderr, name, args)
                else:
                    output_parts = []
                    output_parts.append(f"执行结果:\n{stdout}")
                    if stderr:
                        output_parts.append(f"错误:\n{stderr}")
                    output = "\n\n".join(output_parts)
            else:
                error_msg = result["error"]
                if len(error_msg) > 1024:
                    output = save_long_output(stderr=error_msg, name=name, args=args)
                else:
                    output = f"执行失败: {error_msg}"
                    
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
            # 检查消息数量是否需要压缩（比如超过10条）
            if len(self.messages) > 10:
                self.messages = self._compress_conversion(self.messages)
                
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
                        
                    # 使用 ToolRegistry 的 handle_tool_calls 方法处理工具调用
                    tool_result = self.tool_registry.handle_tool_calls(current_response["message"]["tool_calls"])
                    PrettyOutput.print(tool_result, OutputType.RESULT)

                    if self.model.max_conversation_count() < len(self.messages):
                        self.messages = self._compress_conversion(self.messages)

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
                user_input = get_multiline_input("您可以继续输入，或输入空行结束当前任务")
                if  not user_input:
                    PrettyOutput.print("===============任务结束===============", OutputType.INFO)
                    break

                if self.model.max_conversation_count() < len(self.messages):
                    self.messages = self._compress_conversion(self.messages)
                
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