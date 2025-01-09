import json
import subprocess
from typing import Dict, Any, List, Optional
from .tools import ToolRegistry
from .utils import Spinner, PrettyOutput, OutputType, get_multiline_input
from .models import BaseModel
import re
import os
from datetime import datetime

class Agent:
    def __init__(self, model: BaseModel, tool_registry: ToolRegistry, name: str = "Jarvis"):
        """Initialize Agent with a model, optional tool registry and name"""
        self.model = model
        self.tool_registry = tool_registry or ToolRegistry(model)
        self.name = name
        # 编译正则表达式
        self.tool_call_pattern = re.compile(r'<tool_call>\s*({[^}]+})\s*</tool_call>')
        self.messages = [
            {
                "role": "system",
                "content": f"""You are {name}, a rigorous AI assistant that executes tasks step by step.

Key Principles:
1. Execute ONE step at a time
2. Wait for each step's result before planning the next
3. Use tools to obtain all data, no fabrication
4. Create sub-agents for independent subtasks
5. Think carefully before each action

""" + self.tool_registry.tool_help_text()
            }
        ]
        self.spinner = Spinner()

    def _call_model(self, messages: List[Dict], use_tools: bool = True) -> Dict:
        """调用模型获取响应"""
        self.spinner.start()
        try:
            return self.model.chat(
                messages=messages,
                tools=self.tool_registry.get_all_tools() if use_tools else []
            )
        except Exception as e:
            raise Exception(f"{self.name}: 模型调用失败: {str(e)}")
        finally:
            self.spinner.stop()

    def run(self, user_input: str) -> str:
        """处理用户输入并返回响应，返回任务总结报告"""
        self.clear_history()
        self.messages.append({
            "role": "user",
            "content": user_input
        })
        
        while True:
            try:
                response = self._call_model(self.messages)
                current_response = response

                self.messages.append({
                    "role": "assistant",
                    "content": response["message"].get("content", ""),
                    "tool_calls": current_response["message"]["tool_calls"]
                })
                
                if len(current_response["message"]["tool_calls"]) > 0:
                    if current_response["message"].get("content"):
                        PrettyOutput.print(f"{self.name}: {current_response['message']['content']}", OutputType.SYSTEM)
                        
                    tool_result = self.tool_registry.handle_tool_calls(current_response["message"]["tool_calls"])
                    PrettyOutput.print(f"{self.name} Tool Result: {tool_result}", OutputType.RESULT)

                    self.messages.append({
                        "role": "tool",
                        "content": tool_result
                    })
                    continue
                
                final_content = current_response["message"].get("content", "")
                if final_content:
                    PrettyOutput.print(f"{self.name}: {final_content}", OutputType.SYSTEM)
                
                user_input = get_multiline_input(f"{self.name}: 您可以继续输入，或输入空行结束当前任务")
                if not user_input:
                    PrettyOutput.print(f"{self.name}: 正在生成任务总结...", OutputType.INFO)
                    
                    # 优化后的任务总结提示语
                    summary_prompt = {
                        "role": "user",
                        "content": """The task has been completed. Based on the previous analysis and execution results, provide a task summary including:

1. Key Information:
   - Essential findings from analysis
   - Important results from tool executions
   - Critical data discovered

2. Task Results:
   - Final outcome
   - Actual achievements
   - Concrete results

Focus only on facts and actual results. Be direct and concise."""
                    }
                    while True:
                        try:
                            summary_response = self._call_model(self.messages + [summary_prompt], use_tools=False)
                            summary = summary_response["message"].get("content", "")
                            
                            PrettyOutput.print(f"==============={self.name} 任务总结===============", OutputType.INFO)
                            PrettyOutput.print(summary, OutputType.SYSTEM)
                            PrettyOutput.print("=" * (len(self.name) + 16), OutputType.INFO)
                            
                            return summary
                            
                        except Exception as e:
                            error_msg = f"{self.name}: 生成任务总结时出错: {str(e)}"
                            PrettyOutput.print(error_msg, OutputType.ERROR)
                        
                
                self.messages.append({
                    "role": "user",
                    "content": user_input
                })
                
            except Exception as e:
                error_msg = f"{self.name}: 处理响应时出错: {str(e)}"
                PrettyOutput.print(error_msg, OutputType.ERROR)

    def clear_history(self):
        """清除对话历史，只保留系统提示"""
        self.messages = [self.messages[0]] 