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
        """加载经验总结"""
        user_jarvis_methodology = os.path.expanduser("~/.jarvis_methodology")
        ret = ""
        if os.path.exists(user_jarvis_methodology):
            with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                for k, v in data.items():
                    ret += f"问题类型: \n{k}\n经验总结: \n{v}\n\n"
            PrettyOutput.print(f"从 {user_jarvis_methodology} 加载经验总结: {', '.join(data.keys())}", OutputType.INFO)
        return ret

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

            # 加载经验总结
            methodology = self._load_methodology()

            methodology_prompt = ""
            if methodology:
                methodology_prompt = f"""这是以往处理问题的标准经验总结，如果当前任务与此类似，可参考：
{methodology}

"""
            
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
9. 经验总结：如果当前任务具有通用性且执行过程中遇到了值得记录的经验，使用经验总结工具记录经验总结

-------------------------------------------------------------                       

经验总结模板：
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

{methodology_prompt}

-------------------------------------------------------------

""")
            self.prompt = f"用户任务: {user_input}"

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
                        while True:
                            choice = prompt("是否需要手动为此任务生成经验总结以提升Jarvis对类似任务的处理能力？(y/n), 回车跳过: ")
                            if choice == "y":
                                self._make_methodology()
                                break
                            elif choice == "n" or choice == "":
                                break
                            else:
                                PrettyOutput.print("请输入y或n", OutputType.ERROR)
                                continue
                        PrettyOutput.section("任务完成", OutputType.SUCCESS)
                        if self.is_sub_agent:
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
        """生成经验总结"""
        current_response = self._call_model("""请根据之前的对话内容，判断是否有必要更新、添加、删除现有经验总结，如果有，使用methodology工具进行管理。
经验总结模板：
1. 问题重述
2. 最优解决方案
3. 最优方案执行步骤（失败的行动不需要体现）
                         """)
        
        try:
            result = Agent.extract_tool_calls(current_response)
        except Exception as e:
            PrettyOutput.print(f"工具调用错误: {str(e)}", OutputType.ERROR)
            return
        if len(result) > 0:
            PrettyOutput.print("执行工具调用...", OutputType.PROGRESS)
            tool_result = self.tool_registry.handle_tool_calls(result)
            PrettyOutput.print(tool_result, OutputType.RESULT)
                         
