import time
from typing import Dict, List, Optional

import yaml
import numpy as np
import faiss

from .models.registry import PlatformRegistry
from .tools import ToolRegistry
from .utils import PrettyOutput, OutputType, get_max_context_length, get_multiline_input, load_embedding_model
import os

class Agent:
    def __init__(self, name: str = "Jarvis", is_sub_agent: bool = False):
        """Initialize Agent with a model, optional tool registry and name
        
        Args:
            model: LLM model instance
            tool_registry: Tool registry instance
            name: Agent name, default is "Jarvis"
            is_sub_agent: Whether it is a sub-agent, default is False
        """
        self.model = PlatformRegistry.get_global_platform_registry().get_normal_platform()
        self.tool_registry = ToolRegistry.get_global_tool_registry()
        self.name = name
        self.is_sub_agent = is_sub_agent
        self.prompt = ""
        self.conversation_length = 0  # Use length counter instead
        
        # Load configuration from environment variables
        self.embedding_dimension = 1536  # Default for many embedding models
        self.max_context_length = get_max_context_length()
        
        # Initialize embedding model
        try:
            self.embedding_model = load_embedding_model()
            
            # Warm up model and get correct dimension
            test_text = "This is a test text to ensure the model is fully loaded."
            test_embedding = self.embedding_model.encode(
                test_text, 
                convert_to_tensor=True,
                normalize_embeddings=True
            )
            self.embedding_dimension = len(test_embedding)
            PrettyOutput.print("Successfully loaded embedding model", OutputType.SUCCESS)
            
            # Initialize HNSW index (use correct dimension)
            hnsw_index = faiss.IndexHNSWFlat(self.embedding_dimension, 16)
            hnsw_index.hnsw.efConstruction = 40
            hnsw_index.hnsw.efSearch = 16
            self.methodology_index = faiss.IndexIDMap(hnsw_index)
            
        except Exception as e:
            PrettyOutput.print(f"Failed to load embedding model: {str(e)}", OutputType.ERROR)
            raise
            
        # Initialize methodology related attributes
        self.methodology_data = []

    @staticmethod
    def extract_tool_calls(content: str) -> List[Dict]:
        """Extract tool calls from content, if multiple tool calls are detected, raise an exception, and return the content before the tool call and the tool call"""
        # Split content into lines
        lines = content.split('\n')
        tool_call_lines = []
        in_tool_call = False
        
        # Process line by line
        for line in lines:
            if '<TOOL_CALL>' in line:
                in_tool_call = True
                continue
            elif '</TOOL_CALL>' in line:
                if in_tool_call and tool_call_lines:
                    try:
                        # Parse YAML directly
                        tool_call_text = '\n'.join(tool_call_lines)
                        tool_call_data = yaml.safe_load(tool_call_text)
                        
                        # Validate necessary fields
                        if "name" in tool_call_data and "arguments" in tool_call_data:
                            # Return content before tool call and tool call
                            return [{
                                "name": tool_call_data["name"],
                                "arguments": tool_call_data["arguments"]
                            }]
                        else:
                            PrettyOutput.print("Tool call missing necessary fields", OutputType.ERROR)
                            raise Exception("Tool call missing necessary fields")
                    except yaml.YAMLError as e:
                        PrettyOutput.print(f"YAML parsing error: {str(e)}", OutputType.ERROR)
                        raise Exception(f"YAML parsing error: {str(e)}")
                    except Exception as e:
                        PrettyOutput.print(f"Error processing tool call: {str(e)}", OutputType.ERROR)
                        raise Exception(f"Error processing tool call: {str(e)}")
                in_tool_call = False
                continue
            
            if in_tool_call:
                tool_call_lines.append(line)
        
        return []

    def _call_model(self, message: str) -> str:
        """Call model to get response"""
        sleep_time = 5
        while True:
            ret = self.model.chat_until_success(message)
            if ret:
                return ret
            else:
                PrettyOutput.print(f"Model call failed, retrying... waiting {sleep_time}s", OutputType.INFO)
                time.sleep(sleep_time)
                sleep_time *= 2
                if sleep_time > 30:
                    sleep_time = 30
                continue

    def _create_methodology_embedding(self, methodology_text: str) -> np.ndarray:
        """Create embedding vector for methodology text"""
        try:
            # Truncate long text
            max_length = 512
            text = ' '.join(methodology_text.split()[:max_length])
            
            # 使用sentence_transformers模型获取嵌入向量
            embedding = self.embedding_model.encode([text], 
                                                 convert_to_tensor=True,
                                                 normalize_embeddings=True)
            vector = np.array(embedding.cpu().numpy(), dtype=np.float32)
            return vector[0]  # Return first vector, because we only encoded one text
        except Exception as e:
            PrettyOutput.print(f"Failed to create methodology embedding vector: {str(e)}", OutputType.ERROR)
            return np.zeros(self.embedding_dimension, dtype=np.float32)

    def _load_methodology(self, user_input: str) -> Dict[str, str]:
        """Load methodology and build vector index"""
        PrettyOutput.print("Loading methodology...", OutputType.PROGRESS)
        user_jarvis_methodology = os.path.expanduser("~/.jarvis_methodology")
        if not os.path.exists(user_jarvis_methodology):
            return {}

        try:
            with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Reset data structure
            self.methodology_data = []
            vectors = []
            ids = []

            # Create embedding vector for each methodology
            for i, (key, value) in enumerate(data.items()):
                PrettyOutput.print(f"Vectorizing methodology: {key} ...", OutputType.INFO)
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
                PrettyOutput.print(f"Retrieving methodology...", OutputType.INFO)
                distances, indices = self.methodology_index.search(
                    query_embedding.reshape(1, -1), k
                ) # type: ignore

                relevant_methodologies = {}
                for dist, idx in zip(distances[0], indices[0]):
                    if idx >= 0:
                        similarity = 1.0 / (1.0 + float(dist))
                        methodology = self.methodology_data[idx]
                        PrettyOutput.print(
                            f"Methodology '{methodology['key']}' similarity: {similarity:.3f}",
                            OutputType.INFO
                        )
                        if similarity >= 0.5:
                            relevant_methodologies[methodology["key"]] = methodology["value"]
                        
                if relevant_methodologies:
                    return relevant_methodologies

            return {}

        except Exception as e:
            PrettyOutput.print(f"Error loading methodology: {str(e)}", OutputType.ERROR)
            return {}

    def _summarize_and_clear_history(self) -> None:
        """
        [System message]
        Summarize current conversation history and clear history, only keep system message and summary
        
        This method will:
        1. Request the model to summarize the key information from the current conversation
        2. Clear the conversation history
        3. Keep the system message
        4. Add the summary as new context
        5. Reset the conversation round
        """
        # Create a new model instance to summarize, avoid affecting the main conversation

        PrettyOutput.print("Summarizing conversation history, preparing to generate summary, starting new conversation...", OutputType.PROGRESS)
        
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
            PrettyOutput.print(f"Failed to summarize conversation history: {str(e)}", OutputType.ERROR)

    def _complete_task(self) -> str:
        """Complete task and generate summary
        
        Returns:
            str: Task summary or completion status
        """
        PrettyOutput.section("Task completed", OutputType.SUCCESS)
        
        # 询问是否生成方法论，带输入验证
        while True:
            user_input = input("Generate methodology for this task? (y/n): ").strip().lower()
            if user_input in ['y', 'n', '']:
                break
            PrettyOutput.print("Invalid input, please enter y or n", OutputType.WARNING)
        
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
                    PrettyOutput.print(f"Failed to handle methodology generation: {str(e)}", OutputType.ERROR)
                
            except Exception as e:
                PrettyOutput.print(f"Error generating methodology: {str(e)}", OutputType.ERROR)
        
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
        """Process user input and return response, return task summary report
        
        Args:
            user_input: User input task description
            file_list: Optional file list, default is None
        
        Returns:
            str: Task summary report
        """
        try:
            PrettyOutput.section("Preparing environment", OutputType.PLANNING)
            if file_list:
                self.model.upload_files(file_list)

            # Load methodology
            methodology = self._load_methodology(user_input)
            methodology_prompt = ""
            if methodology:
                methodology_prompt = f"""This is the standard methodology for handling previous problems, if the current task is similar, you can refer to it:
{methodology}

"""
            tools_prompt = ""

            # 选择工具
            PrettyOutput.section("Available tools", OutputType.PLANNING)
            tools = self.tool_registry.get_all_tools()
            if tools:
                tools_prompt += "Available tools:\n"
                for tool in tools:
                    PrettyOutput.print(f"{tool['name']}: {tool['description']}", OutputType.INFO)
                    tools_prompt += f"- Name: {tool['name']}\n"
                    tools_prompt += f"  Description: {tool['description']}\n"
                    tools_prompt += f"  Parameters: {tool['parameters']}\n"

            # 显示任务开始
            PrettyOutput.section(f"Starting new task: {self.name}", OutputType.PLANNING)

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
                    PrettyOutput.print("Analyzing task...", OutputType.PROGRESS)
                    
                    # 累加对话长度
                    self.conversation_length += len(self.prompt)
                    
                    # 如果对话历史长度超过限制，在提示中添加提醒
                    if self.conversation_length > self.max_context_length:
                        current_response = self._summarize_and_clear_history()
                        continue
                    else:
                        current_response = self._call_model(self.prompt)
                        self.conversation_length += len(current_response)  # Add response length
                    try:
                        result = Agent.extract_tool_calls(current_response)
                    except Exception as e:
                        PrettyOutput.print(f"Tool call error: {str(e)}", OutputType.ERROR)
                        self.prompt = f"Tool call error: {str(e)}"
                        continue
                    
                    if len(result) > 0:
                        PrettyOutput.print("Executing tool call...", OutputType.PROGRESS)
                        tool_result = self.tool_registry.handle_tool_calls(result)
                        self.prompt = tool_result
                        continue
                    
                    # 获取用户输入
                    user_input = get_multiline_input(f"{self.name}: You can continue to input, or enter an empty line to end the current task")
                    if user_input == "__interrupt__":
                        PrettyOutput.print("Task cancelled by user", OutputType.WARNING)
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
        """Clear conversation history, only keep system prompt"""
        self.prompt = "" 
        self.model.reset()
        self.conversation_length = 0  # Reset conversation length



