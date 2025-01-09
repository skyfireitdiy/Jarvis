import json
import subprocess
from typing import Dict, Any, List, Optional
from .tools import ToolRegistry
from .utils import PrettyOutput, OutputType, get_multiline_input
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

        # 构建工具说明
        tools_prompt = "Available Tools:\n"
        for tool in self.tool_registry.get_all_tools():
            tools_prompt += f"- Tool: {tool['function']['name']}\n"
            tools_prompt += f"  Description: {tool['function']['description']}\n"
            tools_prompt += f"  Arguments: {tool['function']['parameters']}\n"

        self.messages = [
            {
                "role": "system",
                "content": f"""You are {name}, an AI assistant that follows the ReAct (Reasoning + Acting) framework to solve tasks step by step.

FRAMEWORK:
1. Thought: Analyze the current situation and plan the next step
2. Action: Execute ONE specific tool call
3. Observation: Review the result
4. Next: Plan the next step or conclude

FORMAT:
Thought: I need to [reasoning about the current situation]...
Action: I will use [tool] to [purpose]...
<START_TOOL_CALL>
name: tool_name
arguments:
    param1: value1
<END_TOOL_CALL>

After receiving result:
Observation: The tool returned [analyze result]...
Next: Based on this, I will [next step]...

CORE RULES:
1. ONE Action Per Response
   - Only ONE tool call per response
   - Additional tool calls will be ignored
   - Complete current step before next

2. Clear Reasoning
   - Explain your thought process
   - Justify tool selection
   - Analyze results thoroughly

Examples:
✓ Good Response:
Thought: I need to check the content of utils.py first to understand its structure.
Action: I will read the file content.
<START_TOOL_CALL>
name: file_operation
arguments:
    operation: read
    filepath: src/utils.py
<END_TOOL_CALL>

✗ Bad Response:
Thought: Let's analyze the code.
Action: I'll read and check everything.
[Multiple or vague tool calls...]

Remember:
- Always start with "Thought:"
- Use exactly ONE tool per response
- Wait for results before next step
- Clearly explain your reasoning

{tools_prompt}"""
            }
        ]

    def _call_model(self, messages: List[Dict], use_tools: bool = True) -> Dict:
        """调用模型获取响应"""
        try:
            return self.model.chat(
                messages=messages,
                tools=self.tool_registry.get_all_tools() if use_tools else []
            )
        except Exception as e:
            raise Exception(f"{self.name}: 模型调用失败: {str(e)}")

    def run(self, user_input: str) -> str:
        """处理用户输入并返回响应，返回任务总结报告"""
        self.clear_history()
        
        # 显示任务开始
        PrettyOutput.section(f"开始新任务: {self.name}", OutputType.PLANNING)
        
        self.messages.append({
            "role": "user",
            "content": user_input
        })
        
        while True:
            try:
                # 显示思考状态
                PrettyOutput.print("分析任务...", OutputType.PROGRESS)
                response = self._call_model(self.messages)
                current_response = response

                # 流式输出已经在model中处理，这里添加换行
                PrettyOutput.print_stream_end()

                self.messages.append({
                    "role": "assistant",
                    "content": response["message"].get("content", ""),
                    "tool_calls": current_response["message"]["tool_calls"]
                })
                
                if len(current_response["message"]["tool_calls"]) > 0:
                    if current_response["message"].get("content"):
                        PrettyOutput.print(current_response["message"]["content"], OutputType.SYSTEM)
                        
                    try:
                        # 显示工具调用
                        PrettyOutput.print("执行工具调用...", OutputType.PROGRESS)
                        tool_result = self.tool_registry.handle_tool_calls(current_response["message"]["tool_calls"])
                        PrettyOutput.print(tool_result, OutputType.RESULT)
                    except Exception as e:
                        PrettyOutput.print(str(e), OutputType.ERROR)
                        tool_result = f"Tool call failed: {str(e)}"

                    self.messages.append({
                        "role": "tool",
                        "content": tool_result
                    })
                    continue
                
                # 获取用户输入
                user_input = get_multiline_input(f"{self.name}: 您可以继续输入，或输入空行结束当前任务")
                if not user_input:
                    PrettyOutput.print("生成任务总结...", OutputType.PROGRESS)
                    
                    # 生成任务总结
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
                            
                            # 显示任务总结
                            PrettyOutput.section("任务总结", OutputType.SUCCESS)
                            PrettyOutput.print(summary, OutputType.SYSTEM)
                            PrettyOutput.section("任务完成", OutputType.SUCCESS)
                            
                            return summary
                            
                        except Exception as e:
                            PrettyOutput.print(str(e), OutputType.ERROR)
                
                if user_input == "__interrupt__":
                    PrettyOutput.print("任务已取消", OutputType.WARNING)
                    return "Task cancelled by user"
                
                self.messages.append({
                    "role": "user",
                    "content": user_input
                })
                
            except Exception as e:
                PrettyOutput.print(str(e), OutputType.ERROR)

    def clear_history(self):
        """清除对话历史，只保留系统提示"""
        self.messages = [self.messages[0]] 