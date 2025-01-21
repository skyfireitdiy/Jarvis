import time
from typing import Dict, List, Optional

import yaml

from .models.registry import PlatformRegistry
from .tools import ToolRegistry
from .utils import PrettyOutput, OutputType, get_multiline_input, while_success
import os
from datetime import datetime
from prompt_toolkit import prompt

class Agent:
    def __init__(self, name: str = "Jarvis", is_sub_agent: bool = False):
        """Initialize Agent with a model, optional tool registry and name
        
        Args:
            model: 语言模型实例
            tool_registry: 工具注册表实例
            name: Agent名称，默认为"Jarvis"
            is_sub_agent: 是否为子Agent，默认为False
        """
        self.model = PlatformRegistry.get_global_platform()
        self.tool_registry = ToolRegistry.get_global_tool_registry()
        self.name = name
        self.is_sub_agent = is_sub_agent
        self.prompt = ""
        self.conversation_turns = 0  


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


    def _load_methodology(self) -> Dict[str, str]:
        """加载方法论"""
        user_jarvis_methodology = os.path.expanduser("~/.jarvis_methodology")
        if os.path.exists(user_jarvis_methodology):
            with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            PrettyOutput.print(f"从 {user_jarvis_methodology} 加载方法论: {', '.join(data.keys())}", OutputType.INFO)
            return data
        return {}

    def _summarize_and_clear_history(self) -> None:
        """总结当前对话历史并清空历史记录，只保留系统消息和总结
        
        这个方法会：
        1. 请求模型总结当前对话的关键信息
        2. 清空对话历史
        3. 保留系统消息
        4. 添加总结作为新的上下文
        5. 重置对话轮数
        """
        # 创建一个新的模型实例来做总结，避免影响主对话

        PrettyOutput.print("总结对话历史，准备生成总结，开始新的对话...", OutputType.PLANNING)
        
        prompt = """请总结之前对话中的关键信息，包括：
1. 当前任务目标
2. 已经确认的关键信息
3. 已经尝试过的方案
4. 当前进展
5. 待解决的问题

请用简洁的要点形式描述，突出重要信息。不要包含对话细节。
"""
        
        try:
            summary = self.model.chat(prompt)
            
            # 清空当前对话历史，但保留系统消息
            self.model.delete_chat()
            
            # 添加总结作为新的上下文
            self.prompt = f"""以下是之前对话的关键信息总结：

{summary}

请基于以上信息继续完成任务。
"""
            
            # 重置对话轮数
            self.conversation_turns = 0
            
        except Exception as e:
            PrettyOutput.print(f"总结对话历史失败: {str(e)}", OutputType.ERROR)

    
    def _choose_methodology(self, methodology: Dict[str, str], task: str) -> str:
        PrettyOutput.section("选择方法论", OutputType.PLANNING)
        """选择方法论"""
        prompt = f"""请根据任务内容选择合适的方法论，并返回问题类型和方法论内容，如果当前任务没有合适的方法论，则返回空字符串，格式如下：
任务内容:
{task}

方法论:
"""
        for k, v in methodology.items():
            prompt += f"问题类型：{k}\n"
            prompt += f"方法论：{v}\n"
        return self._call_model(prompt)

    def _complete_task(self) -> str:
        """完成任务并生成总结
        
        Returns:
            str: 任务总结或完成状态
        """
        PrettyOutput.section("任务完成", OutputType.SUCCESS)
        
        # 询问是否生成方法论，带输入验证
        while True:
            user_input = input("是否要为此任务生成方法论？(y/n): ").strip().lower()
            if user_input in ['y', 'n', '']:
                break
            PrettyOutput.print("无效输入，请输入 y 或 n", OutputType.WARNING)
        
        if user_input == 'y':
            try:
                # 让模型判断是否需要生成方法论
                analysis_prompt = """本次任务已结束，请分析是否值得生成方法论，需要考虑以下几点：
1. 任务是否具有通用性，可以应用到类似场景
2. 解决方案是否具有创新性或特殊价值
3. 执行过程是否包含值得记录的经验或教训
4. 是否有助于提升处理类似问题的效率
5. 是否已经有类似的方法论了

如果认为需要生成方法论，请先判断是创建新的方法论还是更新已有方法论。如果是更新已有方法论，使用update，否则使用add。

方法论模板：
1. 问题重述：准确描述问题的核心和边界
2. 最优解决方案：描述最佳的解决思路和方案
3. 最优方案执行步骤：列出具体的执行步骤（失败的尝试不需要记录）

如果认为不需要生成方法论，请说明原因。
仅输出方法论工具的调用指令，或者是不需要生成方法论的说明，除此之外不要输出任何内容。
"""
                self.prompt = analysis_prompt
                response = self._call_model(self.prompt)
                
                # 检查是否包含工具调用
                try:
                    result = Agent.extract_tool_calls(response)
                    PrettyOutput.print(result, OutputType.RESULT)
                except Exception as e:
                    PrettyOutput.print(f"处理方法论生成失败: {str(e)}", OutputType.ERROR)
                
            except Exception as e:
                PrettyOutput.print(f"生成方法论时发生错误: {str(e)}", OutputType.ERROR)
        
        if not self.is_sub_agent:
            return "Task completed"
        
        # 生成任务总结
        summary_prompt = f"""请对以上任务执行情况生成一个简洁的总结报告，包括：

1. 任务目标: 任务重述
2. 执行结果: 成功/失败
3. 关键信息: 提取执行过程中的重要信息
4. 重要发现: 任何值得注意的发现
5. 后续建议: 如果有的话

请用简洁的要点形式描述，突出重要信息。
"""
        self.prompt = summary_prompt
        return self._call_model(self.prompt)

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
            if file_list:
                self.model.upload_files(file_list)

            # 加载方法论
            methodology = self._load_methodology()

            if not methodology:
                methodology = self._choose_methodology(methodology, user_input)

            methodology_prompt = ""
            if methodology:
                methodology_prompt = f"""这是以往处理问题的标准方法论，如果当前任务与此类似，可参考：
{methodology}

"""

            self.clear_history()
            self.conversation_turns = 0  
            
            # 显示任务开始
            PrettyOutput.section(f"开始新任务: {self.name}", OutputType.PLANNING)

            tools_prompt = "可用工具:\n"
            for tool in self.tool_registry.get_all_tools():
                tools_prompt += f"- 名称: {tool['name']}\n"
                tools_prompt += f"  描述: {tool['description']}\n"
                tools_prompt += f"  参数: {tool['parameters']}\n"

            self.model.set_system_message(f"""你是 {self.name}，一个问题处理能力强大的 AI 助手。
                                          
你会严格按照以下步骤处理问题：
1. 问题重述：确认理解问题
2. 根因分析（如果是问题分析类需要，其他不需要）
3. 设定目标：需要可达成，可检验的一个或多个目标
4. 生成解决方案：生成一个或者多个具备可操作性的解决方案
5. 评估解决方案：从众多解决方案中选择一种最优的方案
6. 制定行动计划：根据目前可以使用的工具制定行动计划
7. 执行行动计划：每步执行一个步骤，最多使用一个工具（工具执行完成后，等待工具结果再执行下一步）
8. 监控与调整：如果执行结果与预期不符，则反思并调整行动计划，迭代之前的步骤
9. 方法论：如果当前任务具有通用性且执行过程中遇到了值得记录的经验，使用方法论工具记录方法论，以提升后期处理类似问题的能力
10. 任务结束：如果任务已经完成，使用任务结束指令结束任务
-------------------------------------------------------------                       

方法论模板：
1. 问题重述
2. 最优解决方案
3. 最优方案执行步骤（失败的行动不需要体现）

-------------------------------------------------------------

{tools_prompt}

-------------------------------------------------------------

工具使用格式：

<START_TOOL_CALL>
name: tool_name
arguments:
    param1: value1
    param2: value2
<END_TOOL_CALL>

-------------------------------------------------------------

严格规则：
1. 每次只能执行一个工具
2. 等待用户提供执行结果
3. 不要假设或想象结果
4. 不要创建虚假对话
5. 如果现有信息不足以解决问题，则可以询问用户
6. 处理问题的每个步骤不是必须有的，可按情况省略
7. 在执行一些可能对系统或者用户代码库造成破坏的工具时，请先询问用户
8. 在多次迭代却没有任何进展时，可请求用户指导

-------------------------------------------------------------

特殊指令：
1. !<<SUMMARIZE>>! - 当你发现对话历史过长可能导致token超限时，可以使用此指令总结当前对话要点并清空历史。使用方法：直接回复"!<<SUMMARIZE>>!"即可。

-------------------------------------------------------------

{methodology_prompt}

-------------------------------------------------------------

""")
            self.prompt = f"用户任务: {user_input}"

            while True:
                try:
                    # 显示思考状态
                    PrettyOutput.print("分析任务...", OutputType.PROGRESS)
                    
                    # 增加对话轮次
                    self.conversation_turns += 1
                    
                    # 如果对话超过10轮，在提示中添加提醒
                    if self.conversation_turns > 10:
                        self.prompt = f"{self.prompt}\n(提示：当前对话已超过10轮，建议使用 !<<SUMMARIZE>>! 指令总结对话历史，避免token超限)"
                    
                    current_response = self._call_model(self.prompt)
                    
                    # 检查是否需要总结对话历史
                    if "!<<SUMMARIZE>>!" in current_response:
                        self._summarize_and_clear_history()
                        continue
                    
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
                        return self._complete_task()

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
        self.conversation_turns = 0  # 重置对话轮次


