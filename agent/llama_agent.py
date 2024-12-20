import json
from typing import Dict, Any
from datetime import datetime
from colorama import Fore, Style

from .base import BaseAgent
from utils import extract_json_from_response
from utils.logger import Logger
from llm import BaseLLM

class LlamaAgent(BaseAgent):
    """Main agent class that implements the core task loop"""
    
    def __init__(self, llm: BaseLLM, tool_registry=None, verbose: bool = False):
        super().__init__(llm=llm, verbose=verbose)
        self.logger = Logger()
        self.tool_registry = tool_registry
        self.task_context = {}
        self.current_task = None
    
    def process_input(self, task: str):
        """Process user input using the task loop pattern"""
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
        
        while True:
            # 检查任务是否已完成
            self.logger.info(f"\n{Fore.BLUE}🔍 Checking task completion...{Style.RESET_ALL}")
            completion_status = self._check_task_completion()
            
            # 打印完成状态的关键信息
            if completion_status.get("evidence"):
                self.logger.info(f"{Fore.CYAN}📋 Evidence:{Style.RESET_ALL}")
                for evidence in completion_status.get("evidence", []):
                    self.logger.info(f"{Fore.CYAN}  • {evidence}{Style.RESET_ALL}")
            
            if completion_status.get("is_complete", False):
                conclusion = completion_status.get("conclusion", "")
                self.task_context["conclusion"] = conclusion
                self.logger.info(f"\n{Fore.GREEN}✨ Task Complete!{Style.RESET_ALL}")
                self.logger.info(f"{Fore.GREEN}📝 Conclusion: {conclusion}{Style.RESET_ALL}")
                break
            
            # 1. 任务分析：根据任务描述、计划、现有工具、现有信息、历史执行结果，给出下一步指导
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
    
    def _check_task_completion(self) -> Dict[str, Any]:
        """检查任务是否已完成，如果完成则给出总结"""
        prompt_parts = [
            "# Task Completion Check",
            "",
            "## Task",
            self.current_task,
            "",
            "## Current Information",
            "",
            "### Execution History",
            *[
                f"#### Step {i+1}: {execution['step'].get('description', 'Unknown step')}\n"
                f"Command: {execution['step'].get('parameters', {}).get('command', 'No command')}\n"
                f"Output:\n```\n{execution['result'].get('result', {}).get('result', {}).get('stdout', '')}\n```\n"
                f"Error:\n```\n{execution['result'].get('result', {}).get('result', {}).get('stderr', '')}\n```\n"
                f"Return Code: {execution['result'].get('result', {}).get('result', {}).get('returncode', '')}\n"
                f"Analysis: {execution.get('analysis', '(No analysis)')}\n"
                for i, execution in enumerate(self.task_context.get('execution_history', []))
            ],
            "",
            "## Analysis Requirements",
            "Based on ONLY the execution history above:",
            "",
            "1. Do we have enough ACTUAL RESULTS to answer the task question?",
            "2. If yes, what is the conclusion STRICTLY based on those results?",
            "",
            "CRITICAL RULES:",
            "1. NEVER make assumptions or guess results",
            "2. ONLY use information from actual execution results",
            "3. If no execution history exists, task CANNOT be complete",
            "4. If results are incomplete, task CANNOT be complete",
            "5. Conclusion MUST include actual evidence from results",
            "6. For ping results:",
            "   - Success: Must see actual response from IP",
            "   - Failure: Timeout or unreachable message IS a valid result",
            "   - Both success and failure are conclusive results",
            "",
            "## Response Format",
            "Respond with ONLY a JSON object in this format:",
            "{",
            '    "is_complete": true/false,',
            '    "reason": "Why task is/isn\'t complete",',
            '    "evidence": ["List of actual evidence from results"],',
            '    "conclusion": "Final answer with evidence if complete, otherwise empty"',
            "}"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = self._get_llm_response(prompt)
        completion_status = extract_json_from_response(response)
        
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
    
    def _get_step_guidance(self) -> Dict[str, Any]:
        """任务分析：根据上下文给出下一步指导"""
        prompt_parts = [
            "# Task Analysis",
            "",
            f"## Current Task",
            f"{self.current_task}",
            "",
            "## Information Extraction",
            "Extract from task description:",
            "",
            "* Required values and parameters",
            "* Implicit constraints",
            "* Related context",
            "",
            "## Tool Selection",
            "Based on extracted information:",
            "",
            "* Choose most suitable tool",
            "* MUST provide ALL required parameters for the tool",
            "* For shell tool, 'command' parameter is REQUIRED",
            "* Request user input only if absolutely necessary",
            "",
            "## Available Tools",
            self.tool_registry.get_tools_description(),
            "",
            "## Current Context",
            "",
            "### Status",
            f"`{self.task_context['current_state']}`",
            "",
            "### Task Plan",
            "```json",
            json.dumps(self.task_context.get('task_plan', {}), indent=2),
            "```",
            "",
            "### Previous Executions",
            *[
                f"#### Step: {execution['step'].get('description', 'Unknown step')}\n"
                f"Analysis: {execution.get('analysis', '(No analysis)')}\n"
                for execution in self.task_context.get('execution_history', [])
            ],
            "",
            # 添加用户输入历史到提示中
            *(
                [
                    "### User Inputs",
                    *sum([[
                        f"#### Input {i+1}:",
                        f"Reason: {input_entry['reason']}",
                        f"Response:\n{input_entry['input']}\n"
                    ] for i, input_entry in enumerate(self.task_context.get('user_inputs', []))], []),
                    ""
                ] if self.task_context.get('user_inputs') else []
            ),
            # 添加反思结果到提示中
            *(
                [
                    "### Recent Reflection",
                    "Based on previous failures, consider these insights:",
                    self.task_context.get('reflection', '(No reflection available)'),
                    ""
                ] if self.task_context.get('reflection') else []
            ),
            "",
            "## Response Format",
            "You MUST respond with ONLY a JSON object in the following format.",
            "DO NOT include any other text, explanation, or markdown formatting.",
            "",
            "CRITICAL RULES:",
            "1. ALL tool parameters MUST be explicitly provided",
            "2. For shell tool, MUST include 'command' parameter",
            "3. Parameters MUST match the tool's requirements",
            "4. NEVER leave parameters empty",
            "5. If reflection exists, MUST consider its suggestions",
            "6. MUST consider all user inputs when available",
            "",
            "{",
            '    "information_extracted": {',
            '        "available_info": ["List of information found in task"],',
            '        "implicit_info": ["Any implied information"],',
            '        "is_sufficient": true/false,',
            '        "missing_info": ["Any missing but required information"]',
            '    },',
            '    "need_user_input": false,',
            '    "user_input_reason": "Only present if need_user_input is true",',
            '    "next_steps": [',
            '        {',
            '            "tool": "tool_name",',
            '            "parameters": {"param1": "value1"},',
            '            "description": "What this step will do"',
            '        }',
            '    ],',
            '    "task_plan": {',
            '        "overall_goal": "Main objective",',
            '        "next_focus": "Current step focus"',
            '    }',
            "}"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = self._get_llm_response(prompt)
        guidance = extract_json_from_response(response)
        
        if guidance is None:
            # 如果无法解析JSON，返回一个基本的引请求用户重试
            return {
                "information_extracted": {
                    "available_info": [],
                    "implicit_info": [],
                    "is_sufficient": False,
                    "missing_info": ["Failed to parse response"]
                },
                "need_user_input": True,
                "user_input_reason": "Failed to analyze task. Please try rephrasing your request.",
                "next_steps": [],
                "task_plan": {
                    "overall_goal": "Retry task analysis",
                    "next_focus": "Understanding task requirements"
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
                "error": "Invalid step format: must be a dictionary",
                "result": None
            }
        
        tool_name = step.get("tool", "")
        if not tool_name:
            return {
                "success": False,
                "error": "Tool name is required",
                "result": None
            }
            
        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict):
            return {
                "success": False,
                "error": "Parameters must be a dictionary",
                "result": None
            }
        
        # 2. 获取工具
        tool_id = tool_name.split("(")[-1].strip(")") if "(" in tool_name else tool_name.lower()
        tool = self.tool_registry.get_tool(tool_id)
        if not tool:
            error = f"Tool not found: {tool_name}"
            if self.verbose:
                self.logger.error(error)
            return {
                "success": False,
                "error": error,
                "result": None
            }
        
        # 3. 工具特定参数校验
        if tool_id == "shell" and "command" not in parameters:
            error = "Shell tool requires 'command' parameter"
            if self.verbose:
                self.logger.error(error)
            return {
                "success": False,
                "error": error,
                "result": None
            }
        
        # 4. 执行工具
        try:
            result = tool.execute(**parameters)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            error_msg = str(e)
            if self.verbose:
                self.logger.error(f"Error executing {tool_name}: {error_msg}")
            else:
                self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "result": None
            }
    
    def analyze_tool_result(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
        """分析工具执行结果，提取对任务有用的信息"""
        # Get actual output content
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
            "# Result Analysis",
            "",
            "## Task",
            self.current_task,
            "",
            "## Current Context",
            "",
            "### Status",
            f"`{self.task_context['current_state']}`",
            "",
            "### Task Plan",
            "```json",
            json.dumps(self.task_context.get('task_plan', {}), indent=2),
            "```",
            "",
            "### Previous Executions",
            *[
                f"#### Step: {execution['step'].get('description', 'Unknown step')}\n"
                f"Analysis: {execution.get('analysis', '(No analysis)')}\n"
                for execution in self.task_context.get('execution_history', [])
            ],
            "",
            "## Current Step",
            f"* Tool: `{step.get('tool', 'unknown')}`",
            f"* Description: {step.get('description', 'No description')}",
            f"* Parameters: {json.dumps(step.get('parameters', {}), indent=2)}",
            "",
            "## Result Output",
            "",
            "### stdout",
            "```",
            stdout if stdout else "(empty)",
            "```",
            "",
            "### stderr",
            "```",
            stderr if stderr else "(empty)",
            "```",
            "",
            f"### Return Code: `{returncode}`",
            "",
            "## Analysis Requirements",
            "Based on ALL the above information, analyze whether this step helped accomplish the task.",
            "",
            "CRITICAL RULES:",
            "1. Focus on TASK COMPLETION, not command success",
            "2. Only include sections that have meaningful content",
            "3. Skip sections if there's nothing significant to report",
            "4. Be concise and specific",
            "",
            "Format your response using ONLY the relevant sections below:",
            "",
            "TASK PROGRESS: (REQUIRED)",
            "- What specific progress was made toward the goal",
            "- Which task requirements were satisfied",
            "",
            "USEFUL FINDINGS: (Only if actual data/facts were found)",
            "- Specific facts/data we can use",
            "- Concrete conclusions from the data",
            "",
            "ISSUES: (Only if problems were encountered)",
            "- Specific problems that blocked progress",
            "- Missing or invalid information",
            "",
            "NEXT STEPS: (Only if changes are needed)",
            "- Specific adjustments to try",
            "- Alternative approaches to consider",
            "",
            "Example response with all sections:",
            "TASK PROGRESS:",
            "Found package version and verified compatibility",
            "",
            "USEFUL FINDINGS:",
            "- numpy 1.21.3 is installed",
            "- Compatible with Python 3.8+",
            "",
            "ISSUES:",
            "- Missing dependency information",
            "",
            "NEXT STEPS:",
            "Check remaining dependencies",
            "",
            "Example response with minimal sections:",
            "TASK PROGRESS:",
            "No progress - command output not relevant to task",
            "",
            "NEXT STEPS:",
            "Try using search tool instead"
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
                f"### Attempt {i+1}:",
                f"Tool: {step['step'].get('tool')}",
                f"Parameters: {json.dumps(step['step'].get('parameters', {}), indent=2)}",
                f"Error: {step['result'].get('error', 'Unknown error')}",
                f"Output: {json.dumps(step['result'].get('result', {}), indent=2)}",
                f"Analysis: {step.get('analysis', '(No analysis)')}"
            ])
        
        prompt_parts = [
            "# Reflection on Failed Attempts",
            "",
            "## Task",
            self.current_task,
            "",
            "## Failed Attempts",
            *failed_attempts,
            "",
            "## Current Context",
            f"Task Plan: {json.dumps(self.task_context.get('task_plan', {}), indent=2)}",
            "",
            "## Reflection Requirements",
            "Based on the failed attempts above, provide a comprehensive analysis including:",
            "",
            "1. Common patterns in these failures",
            "2. Incorrect assumptions that were made",
            "3. Alternative approaches or tools that could work better",
            "4. Specific parameter adjustments that might help",
            "",
            "Format your response as a clear, structured analysis with specific recommendations.",
            "Focus on actionable insights that can guide the next attempt.",
            "",
            "Example format:",
            "FAILURE PATTERNS:",
            "- Pattern 1 description",
            "- Pattern 2 description",
            "",
            "INCORRECT ASSUMPTIONS:",
            "- Assumption 1 and why it's wrong",
            "- Assumption 2 and why it's wrong",
            "",
            "ALTERNATIVE APPROACHES:",
            "- Approach 1: description and why it might work",
            "- Approach 2: description and why it might work",
            "",
            "PARAMETER ADJUSTMENTS:",
            "- Parameter 1: suggested change and reasoning",
            "- Parameter 2: suggested change and reasoning",
            "",
            "RECOMMENDATIONS:",
            "Clear, actionable steps to try next"
        ]
        
        prompt = "\n".join(prompt_parts)
        reflection = self._get_llm_response(prompt)
        
        # 打印反思结果
        if reflection:
            self.logger.info(f"\n{Fore.YELLOW}🤔 Reflection after failures:{Style.RESET_ALL}")
            # 按行打印，保持格式
            for line in reflection.splitlines():
                if line.endswith(':'):  # 标题行
                    self.logger.info(f"\n{Fore.YELLOW}{line}{Style.RESET_ALL}")
                elif line.startswith('-'):  # 列表项
                    self.logger.info(f"{Fore.CYAN}  {line}{Style.RESET_ALL}")
                else:  # 普通文本
                    self.logger.info(f"{Fore.WHITE}{line}{Style.RESET_ALL}")
        
        return reflection