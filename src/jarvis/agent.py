import time
from typing import Dict, List, Optional

import yaml
import numpy as np
import faiss
import json

from .models.registry import PlatformRegistry
from .tools import ToolRegistry
from .utils import PrettyOutput, OutputType, get_max_context_length, get_multiline_input, load_embedding_model, while_success
import os
from datetime import datetime
from prompt_toolkit import prompt
from sentence_transformers import SentenceTransformer

class Agent:
    def __init__(self, name: str = "Jarvis", is_sub_agent: bool = False):
        """Initialize Agent with a model, optional tool registry and name
        
        Args:
            model: 语言模型实例
            tool_registry: 工具注册表实例
            name: Agent名称，默认为"Jarvis"
            is_sub_agent: 是否为子Agent，默认为False
        """
        self.model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        self.tool_registry = ToolRegistry.get_global_tool_registry()
        self.name = name
        self.is_sub_agent = is_sub_agent
        self.prompt = ""
        self.conversation_length = 0  # 改用长度计数器
        
        # 从环境变量加载配置
        self.embedding_dimension = 1536  # Default for many embedding models
        self.max_context_length = get_max_context_length()
        
        # 初始化嵌入模型
        try:
            self.embedding_model = load_embedding_model()
            
            # 预热模型并获取正确的维度
            test_text = "这是一段测试文本，用于确保模型完全加载。"
            test_embedding = self.embedding_model.encode(
                test_text, 
                convert_to_tensor=True,
                normalize_embeddings=True
            )
            self.embedding_dimension = len(test_embedding)
            PrettyOutput.print("嵌入模型加载完成", OutputType.SUCCESS)
            
            # 初始化HNSW索引（使用正确的维度）
            hnsw_index = faiss.IndexHNSWFlat(self.embedding_dimension, 16)
            hnsw_index.hnsw.efConstruction = 40
            hnsw_index.hnsw.efSearch = 16
            self.methodology_index = faiss.IndexIDMap(hnsw_index)
            
        except Exception as e:
            PrettyOutput.print(f"加载嵌入模型失败: {str(e)}", OutputType.ERROR)
            raise
            
        # 初始化方法论相关属性
        self.methodology_data = []

    @staticmethod
    def extract_tool_calls(content: str) -> List[Dict]:
        """从内容中提取工具调用，如果检测到多个工具调用则抛出异常，并返回工具调用之前的内容和工具调用"""
        # 分割内容为行
        lines = content.split('\n')
        tool_call_lines = []
        in_tool_call = False
        
        # 逐行处理
        for line in lines:
            if '<TOOL_CALL>' in line:
                in_tool_call = True
                continue
            elif '</TOOL_CALL>' in line:
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
            ret = self.model.chat_until_success(message)
            if ret:
                return ret
            else:
                PrettyOutput.print(f"调用模型失败，重试中... 等待 {sleep_time}s", OutputType.INFO)
                time.sleep(sleep_time)
                sleep_time *= 2
                if sleep_time > 30:
                    sleep_time = 30
                continue

    def _create_methodology_embedding(self, methodology_text: str) -> np.ndarray:
        """为方法论文本创建嵌入向量"""
        try:
            # 对长文本进行截断
            max_length = 512
            text = ' '.join(methodology_text.split()[:max_length])
            
            # 使用sentence_transformers模型获取嵌入向量
            embedding = self.embedding_model.encode([text], 
                                                 convert_to_tensor=True,
                                                 normalize_embeddings=True)
            vector = np.array(embedding.cpu().numpy(), dtype=np.float32)
            return vector[0]  # 返回第一个向量，因为我们只编码了一个文本
        except Exception as e:
            PrettyOutput.print(f"创建方法论嵌入向量失败: {str(e)}", OutputType.ERROR)
            return np.zeros(self.embedding_dimension, dtype=np.float32)

    def _load_methodology(self, user_input: str) -> Dict[str, str]:
        """加载方法论并构建向量索引"""
        PrettyOutput.print("加载方法论...", OutputType.PROGRESS)
        user_jarvis_methodology = os.path.expanduser("~/.jarvis_methodology")
        if not os.path.exists(user_jarvis_methodology):
            return {}

        try:
            with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # 重置数据结构
            self.methodology_data = []
            vectors = []
            ids = []

            # 为每个方法论创建嵌入向量
            for i, (key, value) in enumerate(data.items()):
                PrettyOutput.print(f"向量化方法论: {key} ...", OutputType.INFO)
                methodology_text = f"{key}\n{value}"
                embedding = self._create_methodology_embedding(methodology_text)
                vectors.append(embedding)
                ids.append(i)
                self.methodology_data.append({"key": key, "value": value})

            if vectors:
                vectors_array = np.vstack(vectors)
                self.methodology_index.add_with_ids(vectors_array, np.array(ids)) # type: ignore
                query_embedding = self._create_methodology_embedding(user_input)
                k = min(5, len(self.methodology_data))
                PrettyOutput.print(f"检索方法论...", OutputType.INFO)
                distances, indices = self.methodology_index.search(
                    query_embedding.reshape(1, -1), k
                ) # type: ignore

                relevant_methodologies = {}
                for dist, idx in zip(distances[0], indices[0]):
                    if idx >= 0:
                        similarity = 1.0 / (1.0 + float(dist))
                        methodology = self.methodology_data[idx]
                        PrettyOutput.print(
                            f"方法论 '{methodology['key']}' 相似度: {similarity:.3f}",
                            OutputType.INFO
                        )
                        if similarity >= 0.5:
                            relevant_methodologies[methodology["key"]] = methodology["value"]
                        
                if relevant_methodologies:
                    return relevant_methodologies

            return {}

        except Exception as e:
            PrettyOutput.print(f"加载方法论时发生错误: {str(e)}", OutputType.ERROR)
            return {}

    def _summarize_and_clear_history(self) -> None:
        """
        [系统消息]
        总结当前对话历史并清空历史记录，只保留系统消息和总结
        
        这个方法会：
        1. 请求模型总结当前对话的关键信息
        2. 清空对话历史
        3. 保留系统消息
        4. 添加总结作为新的上下文
        5. 重置对话轮数
        """
        # 创建一个新的模型实例来做总结，避免影响主对话

        PrettyOutput.print("总结对话历史，准备生成总结，开始新的对话...", OutputType.PROGRESS)
        
        prompt = """Please summarize the key information from the previous conversation, including:
1. Current task objective
2. Confirmed key information
3. Solutions that have been tried
4. Current progress
5. Pending issues

Please describe in concise bullet points, highlighting important information. Do not include conversation details.
"""
        
        try:
            summary = self.model.chat_until_success(self.prompt + "\n" + prompt)
            
            # 清空当前对话历史，但保留系统消息
            self.conversation_length = 0  # Reset conversation length
            
            # 添加总结作为新的上下文
            self.prompt = f"""Here is a summary of key information from previous conversations:

{summary}

Please continue the task based on the above information.
"""
            self.conversation_length = len(self.prompt)  # 设置新的起始长度
            
        except Exception as e:
            PrettyOutput.print(f"总结对话历史失败: {str(e)}", OutputType.ERROR)

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
                analysis_prompt = """The current task has ended, please analyze whether a methodology needs to be generated.
If you think a methodology should be generated, first determine whether to create a new methodology or update an existing one. If updating an existing methodology, use 'update', otherwise use 'add'.
If you think a methodology is not needed, please explain why.
The methodology should be applicable to general scenarios, do not include task-specific information such as code commit messages.
The methodology should include: problem restatement, optimal solution, notes (as needed), and nothing else.
Only output the methodology tool call instruction, or the explanation for not generating a methodology. Do not output anything else.
"""
                self.prompt = analysis_prompt
                response = self._call_model(self.prompt)
                
                # 检查是否包含工具调用
                try:
                    tool_calls = Agent.extract_tool_calls(response)
                    if tool_calls:
                        self.tool_registry.handle_tool_calls(tool_calls)
                except Exception as e:
                    PrettyOutput.print(f"处理方法论生成失败: {str(e)}", OutputType.ERROR)
                
            except Exception as e:
                PrettyOutput.print(f"生成方法论时发生错误: {str(e)}", OutputType.ERROR)
        
        if not self.is_sub_agent:
            return "Task completed"
        
        # 生成任务总结
        summary_prompt = f"""Please generate a concise summary report of the task execution, including:

1. Task Objective: Task restatement
2. Execution Result: Success/Failure
3. Key Information: Important information extracted during execution
4. Important Findings: Any noteworthy discoveries
5. Follow-up Suggestions: If any

Please describe in concise bullet points, highlighting important information.
"""
        self.prompt = summary_prompt
        return self._call_model(self.prompt)


    def run(self, user_input: str, file_list: Optional[List[str]] = None) -> str:
        """处理用户输入并返回响应，返回任务总结报告
        
        Args:
            user_input: 用户输入的任务描述
            file_list: 可选的文件列表，默认为None
        
        Returns:
            str: 任务总结报告
        """
        try:
            PrettyOutput.section("准备环境", OutputType.PLANNING)
            if file_list:
                self.model.upload_files(file_list)

            # 加载方法论
            methodology = self._load_methodology(user_input)
            methodology_prompt = ""
            if methodology:
                methodology_prompt = f"""这是以往处理问题的标准方法论，如果当前任务与此类似，可参考：
{methodology}

"""
            tools_prompt = ""

            # 选择工具
            PrettyOutput.section("可用工具", OutputType.PLANNING)
            tools = self.tool_registry.get_all_tools()
            if tools:
                tools_prompt += "可用工具:\n"
                for tool in tools:
                    PrettyOutput.print(f"{tool['name']}: {tool['description']}", OutputType.INFO)
                    tools_prompt += f"- 名称: {tool['name']}\n"
                    tools_prompt += f"  描述: {tool['description']}\n"
                    tools_prompt += f"  参数: {tool['parameters']}\n"

            # 显示任务开始
            PrettyOutput.section(f"开始新任务: {self.name}", OutputType.PLANNING)

            self.clear_history()  

            self.model.set_system_message(f"""You are {self.name}, an AI assistant with powerful problem-solving capabilities.

When users need to execute tasks, you will strictly follow these steps to handle problems:
1. Problem Restatement: Confirm understanding of the problem
2. Root Cause Analysis (only if needed for problem analysis tasks)
3. Set Objectives: Define achievable and verifiable goals
4. Generate Solutions: Create one or more actionable solutions
5. Evaluate Solutions: Select the optimal solution from multiple options
6. Create Action Plan: Based on available tools, create an action plan using PlantUML format for clear execution flow
7. Execute Action Plan: Execute one step at a time, **use at most one tool** (wait for tool execution results before proceeding)
8. Monitor and Adjust: If execution results don't match expectations, reflect and adjust the action plan, iterate previous steps
9. Methodology: If the current task has general applicability and valuable experience is gained, use methodology tools to record it for future similar problems
10. Task Completion: End the task using task completion command when finished

Methodology Template:
1. Problem Restatement
2. Optimal Solution
3. Optimal Solution Steps (exclude failed actions)

-------------------------------------------------------------

{tools_prompt}

-------------------------------------------------------------

Tool Usage Format:

<TOOL_CALL>
name: tool_name
arguments:
    param1: value1
    param2: value2
</TOOL_CALL>

-------------------------------------------------------------

Strict Rules:
- Execute only one tool at a time
- Tool execution must strictly follow the tool usage format
- Wait for user to provide execution results
- Don't assume or imagine results
- Don't create fake dialogues
- If current information is insufficient, you may ask the user
- Not all problem-solving steps are mandatory, skip as appropriate
- Ask user before executing tools that might damage system or user's codebase
- Request user guidance when multiple iterations show no progress
- If yaml string contains colons, wrap the entire string in quotes to avoid yaml parsing errors
- Use | syntax for multi-line strings in yaml

{methodology_prompt}

-------------------------------------------------------------

""")
            self.prompt = f"{user_input}"

            while True:
                try:
                    # 显示思考状态
                    PrettyOutput.print("分析任务...", OutputType.PROGRESS)
                    
                    # 累加对话长度
                    self.conversation_length += len(self.prompt)
                    
                    # 如果对话历史长度超过限制，在提示中添加提醒
                    if self.conversation_length > self.max_context_length:
                        current_response = self._summarize_and_clear_history()
                        continue
                    else:
                        current_response = self._call_model(self.prompt)
                        self.conversation_length += len(current_response)  # 添加响应长度
                    try:
                        result = Agent.extract_tool_calls(current_response)
                    except Exception as e:
                        PrettyOutput.print(f"工具调用错误: {str(e)}", OutputType.ERROR)
                        self.prompt = f"工具调用错误: {str(e)}"
                        continue
                    
                    if len(result) > 0:
                        PrettyOutput.print("执行工具调用...", OutputType.PROGRESS)
                        tool_result = self.tool_registry.handle_tool_calls(result)
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
        

    def clear_history(self):
        """清除对话历史，只保留系统提示"""
        self.prompt = "" 
        self.model.reset()
        self.conversation_length = 0  # 重置对话长度



