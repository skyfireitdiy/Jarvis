import json
import yaml
from typing import Dict, Any, Optional
from datetime import datetime
from colorama import Fore, Style

from .base import BaseAgent
from utils import extract_yaml_from_response
from utils.logger import Logger
from llm import BaseLLM
from utils.yaml_utils import extract_yaml_from_response

class LlamaAgent(BaseAgent):
    """Main agent class that implements the core task loop"""
    
    def __init__(self, llm: BaseLLM, tool_registry=None, verbose: bool = False):
        super().__init__(llm=llm, verbose=verbose)
        self.logger = Logger()
        self.tool_registry = tool_registry
        self.task_context = {}
        self.current_task = None
    
    def process_input(self, task: str):
        """处理用户输入使用任务循环模式"""
        # 处理多行输入，将连续的换行替换为单个换行
        task = "\n".join(line.strip() for line in task.splitlines() if line.strip())
        
        self.current_task = task
        self.task_context = {
            "task_plan": None,
            "execution_history": [],
            "current_state": "Starting task analysis",
            "user_inputs": []  # 存储用户输入历史
        }
        
        self.logger.info(f"\n{Fore.CYAN}🎯 Task:{Style.RESET_ALL}")
        for line in task.splitlines():
            self.logger.info(f"{Fore.CYAN}  {line}{Style.RESET_ALL}")
        
        consecutive_failures = []
        reflection_summary = ""
        first_iteration = True
        
        while True:
            # 只在非第一轮迭代时检查任务是否完成
            if not first_iteration:
                self.logger.info(f"\n{Fore.BLUE}🔍 Checking task completion...{Style.RESET_ALL}")
                completion_status = self._check_task_completion()
                
                # 打印完成状态的关键信息
                if completion_status.get("evidence"):
                    self.logger.info(f"{Fore.CYAN}📋 Evidence:{Style.RESET_ALL}")
                    for evidence in completion_status.get("evidence", []):
                        self.logger.info(f"{Fore.CYAN}  • {evidence}{Style.RESET_ALL}")
                
                if completion_status.get("is_complete", False):
                    conclusion = completion_status.get("conclusion", "")
                    reason = completion_status.get("reason", "")
                    self.task_context["conclusion"] = conclusion
                    self.logger.info(f"\n{Fore.GREEN}✨ Task Complete!{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.GREEN}📝 Reason: {reason}{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.GREEN}📝 Conclusion: {conclusion}{Style.RESET_ALL}")
                    break
                else:
                    reason = completion_status.get("reason", "Unknown reason")
                    self.logger.info(f"\n{Fore.YELLOW}⏳ Task Incomplete:{Style.RESET_ALL}")
                    self.logger.info(f"{Fore.YELLOW}📝 Reason: {reason}{Style.RESET_ALL}")
            
            # 1. 任务分析
            self.logger.info(f"\n{Fore.BLUE}🤔 Analyzing task...{Style.RESET_ALL}")
            
            # 如果有反思总结，添加到提示中
            if reflection_summary:
                self.task_context["reflection"] = reflection_summary
            
            guidance = self._get_step_guidance()
            
            # 打印任务计划
            if guidance.get("task_plan"):
                plan = guidance["task_plan"]
                self.logger.info(f"\n{Fore.YELLOW}📋 Task Plan:{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}  • Goal: {plan.get('overall_goal')}{Style.RESET_ALL}")
                self.logger.info(f"{Fore.YELLOW}  • Next Focus: {plan.get('next_focus')}{Style.RESET_ALL}")
            
            # 打印提取的信息
            if guidance.get("information_extracted"):
                info = guidance["information_extracted"]
                self.logger.info(f"\n{Fore.MAGENTA}ℹ️ Extracted Information:{Style.RESET_ALL}")
                if info.get("available_info"):
                    self.logger.info(f"{Fore.MAGENTA}  Available Info:{Style.RESET_ALL}")
                    for item in info["available_info"]:
                        self.logger.info(f"{Fore.MAGENTA}    • {item}{Style.RESET_ALL}")
                if info.get("missing_info"):
                    self.logger.info(f"{Fore.YELLOW}  Missing Info:{Style.RESET_ALL}")
                    for item in info["missing_info"]:
                        self.logger.info(f"{Fore.YELLOW}    • {item}{Style.RESET_ALL}")
            
            # 检查是否需要用户补充信息
            if guidance.get("need_user_input", False):
                reason = guidance.get("user_input_reason", "Please provide more information")
                self.logger.info(f"\n{Fore.YELLOW}❓ {reason}{Style.RESET_ALL}")
                
                # 获取用户输入
                self.logger.info(f"\n{Fore.YELLOW}💬 Your response (type 'done' on a new line when finished):{Style.RESET_ALL}")
                user_input = []
                while True:
                    line = input().strip()
                    if line.lower() == 'done':
                        break
                    user_input.append(line)
                
                # 存储用户输入
                if user_input:
                    input_entry = {
                        'timestamp': datetime.now().isoformat(),
                        'reason': reason,
                        'input': '\n'.join(user_input)
                    }
                    self.task_context['user_inputs'].append(input_entry)
                    self.logger.info(f"{Fore.GREEN}✅ Input received and stored{Style.RESET_ALL}")
                else:
                    self.logger.info(f"{Fore.YELLOW}⚠️ No input provided{Style.RESET_ALL}")
                break
            
            # 2. 执行工具
            next_steps = guidance.get("next_steps", [])
            if not next_steps:
                self.logger.info(f"\n{Fore.YELLOW}⚠️ No next steps available{Style.RESET_ALL}")
                break
            
            step_success = False
            for step in next_steps:
                # 显示当前步骤
                self.logger.info(f"\n{Fore.BLUE}🔄 Executing step: {step.get('description', 'Unknown step')}{Style.RESET_ALL}")
                self.logger.info(f"{Fore.CYAN}⚙️ Using tool: {step.get('tool', '')}{Style.RESET_ALL}")
                self.logger.info(f"{Fore.CYAN}📋 Parameters: {json.dumps(step.get('parameters', {}), indent=2)}{Style.RESET_ALL}")
                
                # 执行工具
                result = self.execute_step(step)
                
                # 显示执行结果状态
                if result.get("success", False):
                    self.logger.info(f"{Fore.GREEN}✅ Execution successful{Style.RESET_ALL}")
                    step_success = True
                    consecutive_failures = []  # 重置连续失败计数
                    
                    # 显示输出结果
                    stdout = result.get("result", {}).get("result", {}).get("stdout", "").strip()
                    stderr = result.get("result", {}).get("result", {}).get("stderr", "").strip()
                    returncode = result.get("result", {}).get("result", {}).get("returncode", "")
                    
                    if stdout:
                        self.logger.info(f"{Fore.WHITE}📤 Output:\n{stdout}{Style.RESET_ALL}")
                    if stderr:
                        self.logger.info(f"{Fore.RED}⚠️ Error output:\n{stderr}{Style.RESET_ALL}")
                    if returncode is not None:
                        self.logger.info(f"{Fore.CYAN}📊 Return Code: {returncode}{Style.RESET_ALL}")
                else:
                    error = result.get('error', 'Unknown error')
                    self.logger.error(f"{Fore.RED}❌ Execution failed: {error}{Style.RESET_ALL}")
                    
                    # 记录失败信息
                    consecutive_failures.append({
                        'step': step,
                        'result': result,
                        'analysis': None  # 将在分析后更新
                    })
                
                # 3. 结果分析：根据执行结果，结合任务描述、计划、现有信息、历史执行结果，分析出对任务有用的信息
                self.logger.info(f"\n{Fore.BLUE}📊 Analyzing results...{Style.RESET_ALL}")
                analysis = self.analyze_tool_result(step, result)
                self.logger.info(f"{Fore.MAGENTA}💡 Analysis: {analysis}{Style.RESET_ALL}")
                
                # 更新最后一次失败的分析结果
                if consecutive_failures:
                    consecutive_failures[-1]['analysis'] = analysis
                
                # 更新任务上下文
                self._update_task_context(step, result, analysis)
            
            # 如果所有步骤都失败了，检查是否需要反思
            if not step_success and len(consecutive_failures) >= 3:
                reflection_summary = self._reflect_on_failures(consecutive_failures[-3:])
                consecutive_failures = []  # 重置失败计数
            
            first_iteration = False
    
    def _check_task_completion(self) -> Dict[str, Any]:
        """检查任务是否已完成，如果完成则给出总结"""
        prompt_parts = [
            "# 任务完成检查",
            "",
            "## 任务",
            self.current_task,
            "",
            "## 当前信息",
            "",
            "### 执行历史",
            *[
                f"#### 步骤 {i+1}: {execution['step'].get('description', '未知步骤')}\n"
                f"工具: {execution['step'].get('tool', '未知工具')}\n"
                f"参数: {json.dumps(execution['step'].get('parameters', {}), indent=2)}\n"
                f"成功: {execution['result'].get('success', False)}\n"
                f"分析结果: {execution.get('analysis', '(无分析)')}\n"
                for i, execution in enumerate(self.task_context.get('execution_history', []))
            ],
            "",
            "## 分析要求",
            "仅基于上述执行历史：",
            "",
            "1. 我们是否有足够的实际结果来回答任务问题？",
            "2. 如果有，基于这些结果的具体结论是什么？",
            "",
            "关键规则：",
            "1. 禁止做假设或猜测结果",
            "2. 只使用实际执行结果中的信息",
            "3. 如果没有执行历史，任务不能完成",
            "4. 如果结果不完整，任务不能完成",
            "5. 结论必须包含来自结果的实际证据",
            "6. 对于 ping 结果：",
            "   - 成功：必须看到来自 IP 的实际响应",
            "   - 失败：超时或不可达消息也是有效结果",
            "   - 成功和失败都是确定性结果",
            "",
            "## 响应格式",
            "你必须严格按照以下 YAML 格式返回响应：",
            "",
            "is_complete: true/false",
            "reason: 任务完成/未完成的原因",
            "evidence:",
            "  - 来自结果的实际证据1",
            "  - 来自结果的实际证据2",
            "conclusion: 如果完成则给出带证据的最终答案，否则为空",
            "",
            "示例响应：",
            "is_complete: true",
            'reason: 成功获取了所需的所有信息',
            "evidence:",
            "  - 第一步执行成功，获取了A信息",
            "  - 第二步执行成功，获取了B信息",
            'conclusion: 根据获取的信息，可以得出最终结论...'
        ]
        
        prompt = "\n".join(prompt_parts)
        completion_status = self._get_llm_yaml_response_with_retry(prompt)
        
        if completion_status is None:
            return {
                "is_complete": False,
                "reason": "Failed to check completion status",
                "evidence": [],
                "conclusion": ""
            }
            
        # 如果没有执行历史，强制设置为未完成
        if not self.task_context.get('execution_history'):
            completion_status["is_complete"] = False
            completion_status["reason"] = "No execution history available"
            completion_status["evidence"] = []
            completion_status["conclusion"] = ""
            
        return completion_status
    
    def _get_llm_json_response_with_retry(self, prompt: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """获取LLM响应并解析为JSON，支持重试"""
        last_response = None
        
        for attempt in range(max_retries):
            if attempt > 0:
                # 如果是重试，添加更明确的JSON格式要求
                retry_prompt = f"""
你的上一个响应包含无效的JSON格式。请仔细检查并重试。

常见错误：
1. JSON字符串中使用了单引号而不是双引号
2. 字段名没有使用双引号
3. 多行字符串格式不正确
4. 括号或逗号不匹配
5. 包含了额外的文本或注释

请确保：
1. 使用正确的JSON语法
2. 所有字符串使用双引号
3. 所有字段名使用双引号
4. 不要添加任何额外的文本
5. 不要使用注释
6. 确保所有括号和逗号正确匹配
7. 多行字符串使用适当的转义

原始提示：
{prompt}

之前的响应：
{last_response}

请提供一个有效的JSON响应：
"""
                response = self._get_llm_response(retry_prompt)
            else:
                response = self._get_llm_response(prompt)
            
            # 记录原始响应
            last_response = response
            
            # 尝试提取和解析JSON
            json_response = extract_yaml_from_response(response)
            if json_response is not None:
                return json_response
            
            # 如果解析失败，记录错误信息
            if self.verbose:
                self.logger.error(f"第 {attempt + 1} 次尝试解析JSON失败")
        
        # 所有重试都失败后返回None
        if self.verbose:
            self.logger.error("所有重试都失败，无法获取有效的JSON响应")
        return None
    
    def _get_llm_yaml_response_with_retry(self, prompt: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """获取LLM响应并解析为YAML，支持重试"""
        last_response = None
        
        for attempt in range(max_retries):
            if attempt > 0:
                retry_prompt = f"""
你的上一个响应包含无效的YAML格式。请仔细检查并重试。

常见错误：
1. 缩进不一致
2. 列表项格式不正确
3. 多行字符串格式不正确
4. 键值对格式不正确
5. 包含了额外的文本或注释

请确保：
1. 使用正确的YAML语法
2. 保持一致的缩进（建议使用2空格）
3. 列表项使用 "- " 开头
4. 多行字符串使用 | 或 >
5. 不要添加任何额外的文本
6. 不要使用注释

原始提示：
{prompt}

之前的响应：
{last_response}

请提供一个有效的YAML响应：
"""
                response = self._get_llm_response(retry_prompt)
            else:
                response = self._get_llm_response(prompt)
            
            last_response = response
            
            # 尝试提取和解析YAML
            yaml_response = extract_yaml_from_response(response)
            if yaml_response is not None:
                return yaml_response
            
            # 如果解析失败，记录错误信息
            if self.verbose:
                self.logger.error(f"第 {attempt + 1} 次尝试解析YAML失败")
        
        if self.verbose:
            self.logger.error("所有重试都失败，无法获取有效的YAML响应")
        return None
    
    def _get_step_guidance(self) -> Dict[str, Any]:
        """任务分析：根据上下文给出下一步指导"""
        prompt_parts = [
            "# 任务分析",
            "",
            "## 当前任务",
            self.current_task,
            "",
            "## 信息提取",
            "从任务描述中提取：",
            "",
            "* 所需的值和参数",
            "* 隐含的约束条件",
            "* 相关上下文",
            "",
            "## 工具选择",
            "基于提取的信息：",
            "",
            "* 选择最合适的工具",
            "* 必须提供工具所需的所有参数",
            "* 对于 shell 工具，必须包含 'command' 参数",
            "* 仅在绝对必要时才请求用户输入",
            "",
            "## 可用工具",
            self.tool_registry.get_tools_description(),
            "",
            "## 当前上下文",
            "",
            "### 状态",
            f"`{self.task_context['current_state']}`",
            "",
            "### 任务计划",
            "```json",
            json.dumps(self.task_context.get('task_plan', {}), indent=2),
            "```",
            "",
            "### 之前的执行",
            *[
                f"#### 步骤：{execution['step'].get('description', '未知步骤')}\n"
                f"分析：{execution.get('analysis', '(无分析)')}\n"
                for execution in self.task_context.get('execution_history', [])
            ],
            "",
            # 添加用户输入历史到提示中
            *(
                [
                    "### 用户输入",
                    *sum([[
                        f"#### 输入 {i+1}：",
                        f"原因：{input_entry['reason']}",
                        f"回应：\n{input_entry['input']}\n"
                    ] for i, input_entry in enumerate(self.task_context.get('user_inputs', []))], []),
                    ""
                ] if self.task_context.get('user_inputs') else []
            ),
            # 添加反思结果到提示中
            *(
                [
                    "### 最近的反思",
                    "基于前的失败，考虑以下见解：",
                    self.task_context.get('reflection', '(无反思可用)'),
                    ""
                ] if self.task_context.get('reflection') else []
            ),
            "",
            "## 响应格式",
            "你必须严格按照以下 YAML 格式返回响应。",
            "格式错误将导致工具执行失败。",
            "",
            "格式模板：",
            "information_extracted:",
            "  available_info:",
            "    - 从任务中提取的信息1",
            "    - 从任务中提取的信息2",
            "  implicit_info:",
            "    - 任何隐含的信息1",
            "    - 任何隐含的信息2",
            "  is_sufficient: true",
            "  missing_info: []",
            "",
            "need_user_input: false",
            "user_input_reason: 仅当 need_user_input 为 true 时出现",
            "",
            "next_steps:",
            "  - tool: 工具名称",
            "    parameters:",
            "      param1: value1",
            "    description: 这一步将做什么",
            "",
            "task_plan:",
            "  overall_goal: 主要目标",
            "  next_focus: 当前步骤重点",
            "",
            "示例响应：",
            "information_extracted:",
            "  available_info:",
            "    - 任务所需的值A",
            "    - 任务需的值B",
            "  implicit_info:",
            "    - 需要进行的操作类型",
            "  is_sufficient: true",
            "  missing_info: []",
            "",
            "need_user_input: false",
            "",
            "next_steps:",
            "  - tool: python",
            "    parameters:",
            "      code: |",
            "        print('Hello, World!')",
            "        for i in range(5):",
            "            print(i)",
            "    description: 执行Python代码示例",
            "",
            "task_plan:",
            "  overall_goal: 完成主要任务目标",
            "  next_focus: 执行当前步骤"
        ]
        
        prompt = "\n".join(prompt_parts)
        guidance = self._get_llm_yaml_response_with_retry(prompt, max_retries=3)
        
        # 然后再检查结果
        if guidance is None:
            return {
                "information_extracted": {
                    "available_info": [],
                    "implicit_info": [],
                    "is_sufficient": False,
                    "missing_info": ["无法解析响应，JSON格式无效"]
                },
                "need_user_input": True,
                "user_input_reason": "任务分析失败。请试重新描述您的请求。",
                "next_steps": [],
                "task_plan": {
                    "overall_goal": "重新尝试任务分析",
                    "next_focus": "理解任务需求"
                }
            }
        
        # 更新任务状态，包含提取的信息
        if guidance.get('information_extracted'):
            self.task_context['extracted_info'] = guidance['information_extracted']
            
        return guidance
    
    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个工具步骤"""
        # 1. 基本参数校验
        if not isinstance(step, dict):
            return {
                "success": False,
                "error": "步骤格式无效，必须是字典",
                "result": None
            }
        
        tool_name = step.get("tool", "")
        if not tool_name:
            return {
                "success": False,
                "error": "未提供工具名称",
                "result": None
            }
            
        # 获取参数，同支持 parameters 和 arguments
        parameters = step.get("parameters", step.get("arguments", {}))
        if not isinstance(parameters, dict):
            return {
                "success": False,
                "error": "参数必须是字典格式",
                "result": None
            }
        
        # 2. 获取工具
        tool_id = tool_name.split("(")[-1].strip(")") if "(" in tool_name else tool_name.lower()
        tool = self.tool_registry.get_tool(tool_id)
        if not tool:
            error = f"未找到工具：{tool_name}"
            if self.verbose:
                self.logger.error(error)
            return {
                "success": False,
                "error": error,
                "result": None
            }
        
        # 3. 执行工具
        try:
            result = tool.execute(**parameters)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            error_msg = str(e)
            if self.verbose:
                self.logger.error(f"执行 {tool_name} 时出错：{error_msg}")
            else:
                self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "result": None
            }
    
    def analyze_tool_result(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
        """分析工具执行结果，提取对任务有用的信息"""
        # 获取实际输出内容
        result_dict = result.get("result", {}).get("result", {})
        if isinstance(result_dict, dict):
            stdout = result_dict.get("stdout", "").strip()
            stderr = result_dict.get("stderr", "").strip()
            returncode = result_dict.get("returncode", "")
        else:
            stdout = str(result_dict)
            stderr = ""
            returncode = ""
        
        prompt_parts = [
            "# 结果分析",
            "",
            "## 任务",
            self.current_task,
            "",
            "## 当前上下文",
            "",
            "### 状态",
            f"`{self.task_context['current_state']}`",
            "",
            "### 任务计划",
            "```json",
            json.dumps(self.task_context.get('task_plan', {}), indent=2),
            "```",
            "",
            "### 之前的执行",
            *[
                f"#### 步骤：{execution['step'].get('description', '未知步骤')}\n"
                f"工具：{execution['step'].get('tool', '未知工具')}\n"
                f"参数：{json.dumps(execution['step'].get('parameters', {}), indent=2)}\n"
                f"成功：{execution['result'].get('success', False)}\n"
                f"分析结果：{execution.get('analysis', '(无分析)')}\n"
                for execution in self.task_context.get('execution_history', [])
            ],
            "",
            "## 当前步骤",
            f"* 工具：`{step.get('tool', '未知')}`",
            f"* 描述：{step.get('description', '无描述')}",
            f"* 参数：{json.dumps(step.get('parameters', {}), indent=2)}",
            "",
            "## 执行结果",
            "",
            "### 标准输出",
            "```",
            stdout if stdout else "(空)",
            "```",
            "",
            "### 标准错误",
            "```",
            stderr if stderr else "(空)",
            "```",
            "",
            f"### 返回码：`{returncode}`",
            "",
            "## 分析要求",
            "基于以上所有信息，分析此步骤是否帮助完成任务。",
            "",
            "关键规则：",
            "1. 关注任务完成情况，而不是命令成功与否",
            "2. 只包含有意义的内容部分",
            "3. 如果没有重要内容则跳过相应部分",
            "4. 保持简洁具体",
            "5. 禁止捏造或假设数据 - 只使用工具的实际输出",
            "6. 所有字和结论必须来自工具执行结果",
            "7. 如果工具没有输出特定数据，不要在分析中包含它",
            "8. 如果之前的分析给出了具体建议，必须先执行这些建议",
            "9. 在遇到错误时，优先采用错误信息中提供的解决方案",
            "",
            "使用以下相关部分格式化您的响应：",
            "",
            "任务进展：（必需）",
            "- 朝目标取得了什么具体进展",
            "- 满足了哪些任务要求",
            "",
            "有用发现：（仅当找到实际数据/事实时）",
            "- 可以使用的具体事实/数据",
            "- 从事实/数据得出的具体结论",
            "",
            "问题：（仅当遇到问题时）",
            "- 阻碍进展的具体问题",
            "- 缺失或无效的信息",
            "",
            "下一步：（仅当需要改变时）",
            "- 必须先执行之前未完成的建议",
            "- 如果错误信息提供了解决方案，优先使用该方案",
            "- 其他可能的调整建议",
            "- 要考虑的替代方法"
        ]
        
        prompt = "\n".join(prompt_parts)
        return self._get_llm_response(prompt)
    
    def _update_task_context(self, step: Dict[str, Any], result: Dict[str, Any], analysis: str):
        """更新任务上下文"""
        history_entry = {
            'step': step,
            'result': result,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        }
        self.task_context['execution_history'].append(history_entry)
    
    def _reflect_on_failures(self, failed_steps: list) -> str:
        """根据连续失败的步骤进行反思，给出新的建议"""
        # 构建失败尝试的描述
        failed_attempts = []
        for i, step in enumerate(failed_steps):
            failed_attempts.extend([
                f"### 尝试 {i+1}:",
                f"工具: {step['step'].get('tool')}",
                f"参数: {json.dumps(step['step'].get('parameters', {}), indent=2)}",
                f"错误: {step['result'].get('error', '未知错误')}",
                f"输出: {json.dumps(step['result'].get('result', {}), indent=2)}",
                f"分析: {step.get('analysis', '(无分析)')}"
            ])
        
        prompt_parts = [
            "# 失败尝试反思",
            "",
            "## 任务",
            self.current_task,
            "",
            "## 失败尝试",
            *failed_attempts,
            "",
            "## 当前上下文",
            f"任务计划: {json.dumps(self.task_context.get('task_plan', {}), indent=2)}",
            "",
            "## 反思要求",
            "基于上述失败尝试，提供全面分析包括",
            "",
            "1. 这些失败的共同模式",
            "2. 做出的错误假设",
            "3. 可能更好的替代方法或工具",
            "4. 可能有帮助的具体参数调整",
            "",
            "请以清晰、结构化的分析形式回应，给出具体建议。",
            "重点关注可以指导下一次尝试的可操作见解。",
            "",
            "格式示例：",
            "失败模式：",
            "- 模式1描述",
            "- 模式2描述",
            "",
            "错误假设：",
            "- 假设1及其错误原因",
            "- 假设2及其错误原因",
            "",
            "替代方法：",
            "- 方法1：描述及可能有效的原因",
            "- 方法2：描述及可能有效的原因",
            "",
            "参数调整：",
            "- 参数1：建议的改变及理由",
            "- 参数2：建议的改变及理由",
            "",
            "建议：",
            "明确的、可执行的下一步尝试"
        ]
        
        prompt = "\n".join(prompt_parts)
        reflection = self._get_llm_response(prompt)
        
        # 打印反思结果
        if reflection:
            self.logger.info(f"\n{Fore.YELLOW}🤔 Reflection after failures:{Style.RESET_ALL}")
            # 按行打印，保持格式
            for line in reflection.splitlines():
                if line.endswith(':'):  # 标题
                    self.logger.info(f"\n{Fore.YELLOW}{line}{Style.RESET_ALL}")
                elif line.startswith('-'):  # 列表项
                    self.logger.info(f"{Fore.CYAN}  {line}{Style.RESET_ALL}")
                else:  # 普通文本
                    self.logger.info(f"{Fore.WHITE}{line}{Style.RESET_ALL}")
        
        return reflection