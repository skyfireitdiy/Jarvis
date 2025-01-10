import json
import subprocess
from typing import Dict, Any, List, Optional, Tuple

import yaml
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
            tools_prompt += f"- Tool: {tool['name']}\n"
            tools_prompt += f"  Description: {tool['description']}\n"
            tools_prompt += f"  Arguments: {tool['parameters']}\n"

        self.messages = [
            {
                "role": "system",
                "content": f"""You are {name}, an AI assistant that strictly follows the ReAct framework for step-by-step reasoning and action.

{tools_prompt}

ReAct FRAMEWORK:
1. THOUGHT
   - Analyze current situation
   - Consider available tools
   - Plan next action
   - Base on FACTS only

2. ACTION (OPTIONAL)
   - Tool call is NOT required in every response
   - If more information is needed, just ask the user
   - When using a tool:
     - Use ONLY tools from the provided list
     - Execute exactly ONE tool
     - Tools are executed by the user manually
     - Format MUST be valid YAML:
     <START_TOOL_CALL>
     name: tool_name
     arguments:
         param1: value1       # All arguments must be properly indented
         param2: |           # Use YAML block style for multiline strings
             line1
             line2
     <END_TOOL_CALL>

3. OBSERVATION
   - Wait for tool result or user response
   - Tool results will be provided by the user
   - Continue in next response

RESPONSE FORMAT:
Thought: I analyze that [current situation]... Based on [facts], I need to [goal]...

[If tool is needed:]
Action: I will use [tool] to [specific purpose]...
<START_TOOL_CALL>
name: tool_name
arguments:
    param1: value1
    param2: |
        multiline
        value
<END_TOOL_CALL>

[If more information is needed:]
I need more information about [specific details]. Could you please provide [what you need]?

[STOP HERE - Wait for user response]

STRICT RULES:
‼️ ONLY use tools from the list below
‼️ Tool call is optional - ask user if needed
‼️ ONE tool call per response
‼️ Tool call MUST be valid YAML format
‼️ Arguments MUST be properly indented
‼️ Use YAML block style (|) for multiline values
‼️ Content after <END_TOOL_CALL> is discarded
‼️ Tools are executed manually by the user
‼️ Wait for user to provide tool results
‼️ No assumed results
‼️ No hypothetical actions

Remember:
- Think before acting
- Ask user when needed
- Use ONLY listed tools
- ONE tool at a time
- Follow YAML format strictly
- Wait for user's response
- Tool results come from user
- Next step in next response
"""
            }
        ]

    @staticmethod
    def extract_tool_calls(content: str) -> Tuple[str, List[Dict]]:
        """从内容中提取工具调用，如果检测到多个工具调用则抛出异常，并返回工具调用之前的内容和工具调用"""
        # 分割内容为行
        lines = content.split('\n')
        tool_call_lines = []
        content_lines = []  # 存储工具调用之前的内容
        in_tool_call = False
        
        # 逐行处理
        for line in lines:
            content_lines.append(line)  # 所有内容都添加到 content_lines
            
            if '<START_TOOL_CALL>' in line:
                in_tool_call = True
                continue
            elif '<END_TOOL_CALL>' in line:
                if in_tool_call and tool_call_lines:
                    try:
                        # 直接解析YAML
                        tool_call_text = '\n'.join(tool_call_lines)
                        tool_call_data = yaml.safe_load(tool_call_text)
                        
                        # 验证必要的字段
                        if "name" in tool_call_data and "arguments" in tool_call_data:
                            # 返回工具调用之前的内容和工具调用
                            return '\n'.join(content_lines), [{
                                "name": tool_call_data["name"],
                                "arguments": tool_call_data["arguments"]
                            }]
                        else:
                            PrettyOutput.print("工具调用缺少必要字段", OutputType.ERROR)
                            raise '工具调用缺少必要字段'
                    except yaml.YAMLError as e:
                        PrettyOutput.print(f"YAML解析错误: {str(e)}", OutputType.ERROR)
                        raise 'YAML解析错误'
                    except Exception as e:
                        PrettyOutput.print(f"处理工具调用时发生错误: {str(e)}", OutputType.ERROR)
                        raise '处理工具调用时发生错误'
                in_tool_call = False
                continue
            
            if in_tool_call:
                tool_call_lines.append(line)
        
        # 如果没有找到有效的工具调用，返回原始内容
        return '\n'.join(content_lines), []

    def _call_model(self, messages: List[Dict]) -> Dict:
        """调用模型获取响应"""
        try:
            return self.model.chat(
                messages=messages,
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
                
                current_response = self._call_model(self.messages)

                try:
                    result = Agent.extract_tool_calls(current_response)
                except Exception as e:
                    PrettyOutput.print(f"工具调用错误: {str(e)}", OutputType.ERROR)
                    self.messages.append({
                        "role": "user",
                        "content": f"工具调用错误: {str(e)}"
                    })
                    continue


                self.messages.append({
                    "role": "assistant",
                    "content": result[0]
                })

                
                if len(result[1]) > 0:
                    try:
                        # 显示工具调用
                        PrettyOutput.print("执行工具调用...", OutputType.PROGRESS)
                        tool_result = self.tool_registry.handle_tool_calls(result[1])
                        PrettyOutput.print(tool_result, OutputType.RESULT)
                    except Exception as e:
                        PrettyOutput.print(str(e), OutputType.ERROR)
                        tool_result = f"Tool call failed: {str(e)}"

                    self.messages.append({
                        "role": "user",
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
                            summary = self._call_model(self.messages + [summary_prompt])
                             
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