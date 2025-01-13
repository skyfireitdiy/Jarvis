import json
import subprocess
import time
from typing import Dict, Any, List, Optional, Tuple

import yaml
from .tools import ToolRegistry
from .utils import PrettyOutput, OutputType, get_multiline_input, while_success, while_true
from .models import BaseModel
import re
import os
from datetime import datetime
from prompt_toolkit import prompt

class Agent:
    def __init__(self, model: BaseModel, tool_registry: ToolRegistry, name: str = "Jarvis", is_sub_agent: bool = False, verbose: bool = False):
        """Initialize Agent with a model, optional tool registry and name
        
        Args:
            model: 语言模型实例
            tool_registry: 工具注册表实例
            name: Agent名称，默认为"Jarvis"
            is_sub_agent: 是否为子Agent，默认为False
        """
        self.model = model
        self.tool_registry = tool_registry or ToolRegistry(model, verbose=verbose)
        self.name = name
        self.is_sub_agent = is_sub_agent
        self.prompt = ""


    @staticmethod
    def extract_tool_calls(content: str) -> List[Dict]:
        """从内容中提取工具调用，如果检测到多个工具调用则抛出异常，并返回工具调用之前的内容和工具调用"""
        # 分割内容为行
        lines = content.split('\n')
        tool_call_lines = []
        in_tool_call = False
        
        # 逐行处理
        for line in lines:
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
                            return [{
                                "name": tool_call_data["name"],
                                "arguments": tool_call_data["arguments"]
                            }]
                        else:
                            PrettyOutput.print("工具调用缺少必要字段", OutputType.ERROR)
                            raise Exception("工具调用缺少必要字段")
                    except yaml.YAMLError as e:
                        PrettyOutput.print(f"YAML解析错误: {str(e)}", OutputType.ERROR)
                        raise Exception(f"YAML解析错误: {str(e)}")
                    except Exception as e:
                        PrettyOutput.print(f"处理工具调用时发生错误: {str(e)}", OutputType.ERROR)
                        raise Exception(f"处理工具调用时发生错误: {str(e)}")
                in_tool_call = False
                continue
            
            if in_tool_call:
                tool_call_lines.append(line)
        
        return []

    def _call_model(self, message: str) -> str:
        """调用模型获取响应"""
        sleep_time = 5
        while True:
            ret = while_success(lambda: self.model.chat(message), sleep_time=5)
            if ret:
                return ret
            else:
                PrettyOutput.print(f"调用模型失败，重试中... 等待 {sleep_time}s", OutputType.INFO)
                time.sleep(sleep_time)
                sleep_time *= 2
                if sleep_time > 30:
                    sleep_time = 30
                continue


    def _load_methodology(self) -> str:
        """加载方法论"""
        user_jarvis_methodology = os.path.expanduser("~/.jarvis_methodology")
        if os.path.exists(user_jarvis_methodology):
            with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def run(self, user_input: str, file_list: Optional[List[str]] = None, keep_history: bool = False) -> str:
        """处理用户输入并返回响应，返回任务总结报告
        
        Args:
            user_input: 用户输入的任务描述
            file_list: 可选的文件列表，默认为None
            keep_history: 是否保留对话历史，默认为False
        
        Returns:
            str: 任务总结报告
        """
        try:
            self.clear_history()
            
            if file_list:
                self.model.upload_files(file_list)

            # 加载方法论
            methodology = self._load_methodology()

            methodology_prompt = ""
            if methodology:
                methodology_prompt = f"""这是以往处理问题的标准方法论，如果当前任务与此类似，可参考：
{methodology}

"""
            
            # 显示任务开始
            PrettyOutput.section(f"开始新任务: {self.name}", OutputType.PLANNING)

            tools_prompt = "可用工具:\n"
            for tool in self.tool_registry.get_all_tools():
                tools_prompt += f"- 名称: {tool['name']}\n"
                tools_prompt += f"  描述: {tool['description']}\n"
                tools_prompt += f"  参数: {tool['parameters']}\n"

            self.model.set_system_message(f"""你是 {self.name}，一个严格遵循 ReAct 框架的 AI 助手。

{tools_prompt}

核心能力：
1. 使用现有工具完成任务
2. 访问和理解网页内容（无需使用工具）
3. 分析和处理文件内容
4. 创建子代理处理复杂任务
5. 遵循 ReAct (思考-行动-观察) 框架

工作流程：
1. 思考
   - 分析需求和可用工具
   - 评估是否能用现有工具完成
   - 考虑是否需要访问网页
   - 判断是否需要创建子代理
   - 规划解决方案

2. 行动 (如果需要)
   - 优先使用现有工具
   - 访问网页获取信息
   - 创建新工具（成本高，谨慎使用）
   - 创建子代理处理以下场景:
     * 需要深入分析多个文件
     * 需要长期交互的复杂任务
     * 需要独立的上下文环境
   - 询问更多信息
   
3. 观察
   - 等待执行结果
   - 分析反馈
   - 规划下一步

子代理使用场景：
1. 文件分析任务
   - 代码审查和重构
   - 文档内容分析
   - 多文件关联分析
2. 复杂交互任务
   - 多轮对话
   - 需要保持上下文
3. 独立任务流程
   - 特定领域处理
   - 需要独立决策

工具使用格式：
<START_TOOL_CALL>
name: tool_name
arguments:
    param1: value1
    param2: value2
<END_TOOL_CALL>

严格规则：
1. 每次只能执行一个工具
2. 等待用户提供执行结果
3. 不要假设或想象结果
4. 不要创建虚假对话
5. 每个动作后停止等待

{methodology_prompt}

""")
            self.prompt = f"任务: {user_input}"

            while True:
                try:
                    # 显示思考状态
                    PrettyOutput.print("分析任务...", OutputType.PROGRESS)
                    
                    current_response = self._call_model(self.prompt)
                    
                    try:
                        result = Agent.extract_tool_calls(current_response)
                    except Exception as e:
                        PrettyOutput.print(f"工具调用错误: {str(e)}", OutputType.ERROR)
                        self.prompt = f"工具调用错误: {str(e)}"
                        continue
                    
                    if len(result) > 0:

                        PrettyOutput.print("执行工具调用...", OutputType.PROGRESS)
                        tool_result = self.tool_registry.handle_tool_calls(result)
                        PrettyOutput.print(tool_result, OutputType.RESULT)

                        self.prompt = tool_result
                        continue
                    
                    # 获取用户输入
                    user_input = get_multiline_input(f"{self.name}: 您可以继续输入，或输入空行结束当前任务")
                    if user_input == "__interrupt__":
                        PrettyOutput.print("任务已取消", OutputType.WARNING)
                        return "Task cancelled by user"

                    if user_input:
                        self.prompt = user_input
                        continue
                    
                    if not user_input:
                        PrettyOutput.section("任务完成", OutputType.SUCCESS)
                        while True:
                            choice = prompt("是否需要为此任务生成方法论以提升Jarvis对类似任务的处理能力？(y/n), 回车跳过: ")
                            if choice == "y":
                                self._make_methodology()
                                break
                            elif choice == "n" or choice == "":
                                break
                            else:
                                PrettyOutput.print("请输入y或n", OutputType.ERROR)
                                continue

                        if self.is_sub_agent:
                            # 生成任务总结
                            summary_prompt = f"""请对以上任务执行情况生成一个简洁的总结报告，包括：

1. 任务目标: xxxx
2. 执行结果: 成功/失败
3. 关键信息: 提取执行过程中的重要信息
4. 重要发现: 任何值得注意的发现
5. 后续建议: 如果有的话

请用简洁的要点形式描述，突出重要信息。
"""
                            self.prompt = summary_prompt
                            summary = self._call_model(self.prompt)
                            return summary
                        else:
                            return "Task completed"

                except Exception as e:
                    PrettyOutput.print(str(e), OutputType.ERROR)
                    return f"Task failed: {str(e)}"

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return f"Task failed: {str(e)}"
        
        finally:
            # 只在不保留历史时删除会话
            if not keep_history:
                try:
                    self.model.delete_chat()
                except Exception as e:
                    PrettyOutput.print(f"清理会话时发生错误: {str(e)}", OutputType.ERROR)

    def clear_history(self):
        """清除对话历史，只保留系统提示"""
        self.prompt = "" 
        self.model.reset()

    def _make_methodology(self):
        # 生成经验总结和方法论
        summary_prompt = f"""请根据之前的对话内容，总结处理此类问题的标准方法论。请总结出一个可以复用的标准流程，重点说明通用性和可操作性。

注意：
1. 方法论应该具有独特性，避免与已有方法论重复
2. 突出此类问题的特殊处理方式
3. 强调与其他类型问题的区别
4. 每个步骤都需要说明具体使用的工具或命令
5. 总结失败的经验教训和规避方法

输出格式严格遵顼以下模板(不要输出任何其他内容):
<START_METHOD>
1. 问题分类抽象
   - 这是什么类型的问题
   - 有哪些典型特征
   - 与其他类型问题的主要区别

2. 最佳实践
   - 推荐的处理步骤
     * 步骤1: xxx
       工具/命令: <具体工具名或命令>
       参数说明: xxx
     * 步骤2: xxx
       工具/命令: <具体工具名或命令>
       参数说明: xxx
<END_METHOD>
"""         
        PrettyOutput.print("正在总结方法论...", OutputType.PROGRESS)

        methodology = while_success(lambda: self._call_model(summary_prompt))

        PrettyOutput.section("方法论总结", OutputType.SUCCESS)

        # 方法论追加保存至 ~/.jarvis_methodology
        user_jarvis_methodology = os.path.expanduser("~/.jarvis_methodology")
        with open(user_jarvis_methodology, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(methodology)
            f.write("\n\n" + '-' * 50 + "\n\n")
        PrettyOutput.print("方法论已保存至 ~/.jarvis_methodology", OutputType.SUCCESS)
