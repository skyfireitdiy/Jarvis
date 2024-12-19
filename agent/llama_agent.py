import json
from typing import Dict, Any, Optional
from colorama import Fore, Style

from .base import BaseAgent, AgentState
from .analysis import TaskAnalyzer
from .execution import TaskExecutor
from .reflection import TaskReflector
from .validation import validate_step_format
from utils import extract_json_from_response
from utils.logger import Logger

class LlamaAgent(BaseAgent):
    """Main agent class that combines all components"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analyzer = TaskAnalyzer()
        self.executor = TaskExecutor()
        self.reflector = TaskReflector()
        self.logger = Logger()
    
    def validate_step_format(self, analysis: Dict[str, Any]) -> bool:
        """Validate step format using validation module"""
        return validate_step_format(analysis, self.logger)
    
    def analyze_task(self, task: str) -> Dict[str, Any]:
        """Analyze task using TaskAnalyzer"""
        return self.analyzer.analyze_task(task, self)
    
    def execute_task(self, task: str) -> Dict[str, Any]:
        """Execute task using TaskExecutor"""
        return self.executor.execute_task(task, self)
    
    def retry_task_analysis(self, task: str, previous_response: str, retry_count: int = 0) -> Dict[str, Any]:
        """Retry task analysis using TaskReflector"""
        return self.reflector.retry_task_analysis(task, previous_response, retry_count, self)
    
    def adjust_failed_step(self, step: Dict[str, Any], error: str, context: Dict[str, Any], reflection: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust failed step using TaskReflector"""
        return self.reflector.adjust_failed_step(step, error, context, reflection, self)
    
    def check_task_completion(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check task completion using TaskReflector"""
        return self.reflector.check_task_completion(task, context, self)
    
    def reflect_on_failure(self, task: str, current_step: Dict[str, Any], result: Dict[str, Any], result_analysis: Optional[Dict[str, Any]], agent=None) -> Dict[str, Any]:
        """Reflect on failure using TaskReflector"""
        return self.reflector.reflect_on_failure(task, current_step, result, result_analysis, self)
    
    def analyze_task_with_reflection(self, task: str, reflection: Dict[str, Any], agent=None) -> Dict[str, Any]:
        """Analyze task with reflection using TaskReflector"""
        return self.reflector.analyze_task_with_reflection(task, reflection, self)
    
    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step"""
        self.state = AgentState.EXECUTING
        
        # 验证step格式
        if not isinstance(step, dict) or "tool" not in step or "parameters" not in step:
            return {
                "success": False,
                "error": "Invalid step format",
                "result": {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Step must contain 'tool' and 'parameters'"
                }
            }
        
        tool_name = step.get("tool")
        tool = self.tool_registry.get_tool(tool_name)
        
        if not tool:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
                "result": {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": f"Tool {tool_name} not found"
                }
            }
        
        # 验证必要的参数
        parameters = step.get("parameters", {})
        if tool_name == "shell" and "command" not in parameters:
            return {
                "success": False,
                "error": "Shell tool requires 'command' parameter",
                "result": {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Missing required parameter: command"
                }
            }
        
        try:
            # 打印工具执行详情
            self.logger.log('EXECUTE', f"{Fore.CYAN}╭─ Tool Execution ───────────────────────{Style.RESET_ALL}")
            self.logger.log('EXECUTE', f"{Fore.CYAN}│ Tool:{Style.RESET_ALL} {tool_name}")
            self.logger.log('EXECUTE', f"{Fore.CYAN}│ Description:{Style.RESET_ALL} {step.get('description', 'No description')}")
            self.logger.log('EXECUTE', f"{Fore.CYAN}│ Input Parameters:{Style.RESET_ALL}")
            for param, value in parameters.items():
                self.logger.log('EXECUTE', f"{Fore.CYAN}│   • {param}:{Style.RESET_ALL} {value}")
            self.logger.log('EXECUTE', f"{Fore.CYAN}╰────────────────────────────────────────{Style.RESET_ALL}\n")
            
            # 执行工具
            result = tool.execute(**parameters)
            
            # 打印执行结果
            self.logger.log('RESULT', f"{Fore.GREEN}╭─ Execution Result ─────────────────────{Style.RESET_ALL}")
            if result.get("success", False):
                if "stdout" in result.get("result", {}):
                    stdout = result["result"]["stdout"].strip()
                    if stdout:
                        self.logger.log('RESULT', f"{Fore.GREEN}│ stdout:{Style.RESET_ALL}")
                        for line in stdout.split('\n'):
                            self.logger.log('RESULT', f"{Fore.GREEN}│   {Style.RESET_ALL}{line}")
                if "stderr" in result.get("result", {}):
                    stderr = result["result"]["stderr"].strip()
                    if stderr:
                        self.logger.log('RESULT', f"{Fore.RED}│ stderr:{Style.RESET_ALL}")
                        for line in stderr.split('\n'):
                            self.logger.log('RESULT', f"{Fore.RED}│   {Style.RESET_ALL}{line}")
                if "returncode" in result.get("result", {}):
                    returncode = result["result"]["returncode"]
                    color = Fore.GREEN if returncode == 0 else Fore.RED
                    self.logger.log('RESULT', f"{color}│ returncode:{Style.RESET_ALL} {returncode}")
            else:
                error = result.get("error", "Unknown error")
                self.logger.log('RESULT', f"{Fore.RED}│ error:{Style.RESET_ALL} {error}")
            self.logger.log('RESULT', f"{Fore.GREEN}╰────────────────────────────────────────{Style.RESET_ALL}\n")
            
            return {
                "success": True,
                "step": step,
                "result": result
            }
        except Exception as e:
            # 打印错误信息
            self.logger.log('ERROR', f"{Fore.RED}╭─ Execution Error ──────────────────────{Style.RESET_ALL}")
            self.logger.log('ERROR', f"{Fore.RED}│ {str(e)}{Style.RESET_ALL}")
            self.logger.log('ERROR', f"{Fore.RED}╰────────────────────────────────────────{Style.RESET_ALL}\n")
            
            return {
                "success": False,
                "error": str(e),
                "result": {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": str(e)
                }
            }
    
    def analyze_tool_result(self, task: str, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze tool execution result"""
        self.state = AgentState.OBSERVING
        
        # Get actual output content
        result_dict = result.get("result", {}).get("result", {})  # Get nested result dict
        if isinstance(result_dict, dict):
            stdout = result_dict.get("stdout", "").strip()
            stderr = result_dict.get("stderr", "").strip()
            returncode = result_dict.get("returncode", "")
        else:
            stdout = str(result_dict)
            stderr = ""
            returncode = ""
        
        success = result.get("success", False)
        error = result.get("error", "None")
        
        # Build prompt parts
        prompt_parts = [
            f"Task: {task}",
            "",
            "Step executed:",
            f"Tool: {step.get('tool')}",
            f"Description: {step.get('description', 'No description')}",
            f"Success criteria: {', '.join(step.get('success_criteria', []))}",
            "",
            "Result details:",
            "------------",
            f"Success: {success}",
            f"Error: {error}",
            "",
            "Output:",
            "stdout:",
        ]
        
        # Add actual stdout content
        if stdout:
            for line in stdout.split('\n'):
                prompt_parts.append(line)
        else:
            prompt_parts.append("(empty)")
        
        prompt_parts.extend([
            "",
            "stderr:",
        ])
        
        # Add actual stderr content
        if stderr:
            for line in stderr.split('\n'):
                prompt_parts.append(line)
        else:
            prompt_parts.append("(empty)")
        
        prompt_parts.extend([
            "",
            f"returncode: {returncode}",
            "------------",
            "",
            "CRITICAL RULES:",
            "1. NEVER make assumptions about results that aren't explicitly shown in the output",
            "2. If comparing values, you MUST use the actual values from the output",
            "3. If the command failed (success=False), you CANNOT conclude",
            "4. All conclusions MUST be based on explicit evidence in the output",
            "5. If output is unclear or ambiguous, you MUST request retry",
            "6. ALL RESPONSES MUST BE IN ENGLISH",
            "",
            "Please analyze this result and determine:",
            "1. Can we draw a definitive conclusion from this output?",
            "2. What specific information did we get from the output?",
            "3. Are there any errors or issues we need to address?",
            "4. Do we need to retry with a different approach?",
            "",
            "Format your response as JSON:",
            "{",
            '    "can_conclude": true/false,',
            '    "conclusion": "Clear statement about what we found, with exact values",',
            '    "key_info": [',
            '        "Each piece of information found, with exact values",',
            '        "Any errors or issues found"',
            '    ],',
            '    "has_valid_data": true/false,',
            '    "needs_retry": true/false,',
            '    "validation_errors": ["Any issues with the data"]',
            "}"
        ])
        
        prompt = "\n".join(prompt_parts)
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        # Print analysis results with better formatting
        self.logger.log('ANALYSIS', f"{Fore.CYAN}╭──────────── 📊 Result Analysis 📊 ────────────╮{Style.RESET_ALL}", prefix=False)
        
        if analysis.get("can_conclude"):
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ {Fore.GREEN}✓ Status:{Style.RESET_ALL} {Fore.GREEN}Can conclude{Style.RESET_ALL}", prefix=False)
            conclusion = analysis.get('conclusion', 'No conclusion provided')
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ 📝 Conclusion:{Style.RESET_ALL}", prefix=False)
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│   {Fore.YELLOW}➤ {conclusion}{Style.RESET_ALL}", prefix=False)
        else:
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ {Fore.YELLOW}⚠ Status:{Style.RESET_ALL} {Fore.YELLOW}Cannot conclude yet{Style.RESET_ALL}", prefix=False)
        
        if analysis.get("key_info"):
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ 🔍 Key Information:{Style.RESET_ALL}", prefix=False)
            for info in analysis["key_info"]:
                if any(keyword in info.lower() for keyword in ['=', 'found', 'result', 'count', 'total', 'number']):
                    self.logger.log('ANALYSIS', f"{Fore.CYAN}│   {Fore.YELLOW}➤ {info}{Style.RESET_ALL}", prefix=False)
                else:
                    self.logger.log('ANALYSIS', f"{Fore.CYAN}│   {Fore.WHITE}• {info}{Style.RESET_ALL}", prefix=False)
        
        if analysis.get("has_valid_data"):
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ {Fore.GREEN}✓ Data Validity:{Style.RESET_ALL} {Fore.GREEN}Valid{Style.RESET_ALL}", prefix=False)
        else:
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ {Fore.RED}✗ Data Validity:{Style.RESET_ALL} {Fore.RED}Invalid{Style.RESET_ALL}", prefix=False)
        
        if analysis.get("needs_retry"):
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ {Fore.YELLOW}⚠ Next Action:{Style.RESET_ALL} {Fore.YELLOW}Needs retry{Style.RESET_ALL}", prefix=False)
            if analysis.get("validation_errors"):
                self.logger.log('ANALYSIS', f"{Fore.CYAN}│ ❌ Validation Errors:{Style.RESET_ALL}", prefix=False)
                for error in analysis["validation_errors"]:
                    self.logger.log('ANALYSIS', f"{Fore.CYAN}│   {Fore.RED}✗ {error}{Style.RESET_ALL}", prefix=False)
        else:
            self.logger.log('ANALYSIS', f"{Fore.CYAN}│ {Fore.GREEN}✓ Next Action:{Style.RESET_ALL} {Fore.GREEN}Continue{Style.RESET_ALL}", prefix=False)
        
        self.logger.log('ANALYSIS', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}\n", prefix=False)
        
        return analysis
    
    def plan_next_step_with_suggestion(self, task: str, current_step: Dict[str, Any], suggestion: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Plan next step considering user suggestion"""
        prompt_parts = [
            f"Task: {task}",
            "",
            f"Current step: {json.dumps(current_step, ensure_ascii=False)}",
            f"User suggestion: {suggestion}",
            "",
            "Context:",
            f"- Variables: {json.dumps(context.get('variables', {}), ensure_ascii=False)}",
            f"- Files: {json.dumps(context.get('files', {}), ensure_ascii=False)}",
            "",
            "Previous attempts failed. Please plan a new step considering the user's suggestion.",
            "",
            "Available tools:",
            self.tool_registry.get_tools_description(),
            "",
            "Format your response as JSON:",
            "{"
            '    "next_step": {'
            '        "tool": "tool_name",'
            '        "parameters": {"param1": "value1"},'
            '        "description": "What this step will do",'
            '        "success_criteria": ["How we know it worked"]'
            '    }'
            "}"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        return analysis.get("next_step", current_step)
    
    def _has_tried_combination(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Check if we've already tried this tool-parameters combination"""
        return (tool_name, str(parameters)) in self.tried_combinations
    
    def _add_tried_combination(self, tool_name: str, parameters: Dict[str, Any]):
        """Add a tool-parameters combination to the tried set"""
        self.tried_combinations.add((tool_name, str(parameters)))
    
    def analyze_task_completion(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze if task is completed"""
        prompt_parts = [
            f"Task: {task}",
            "",
            "Current context:",
            f"Variables: {context.get('variables', {})}",
            f"Summaries: {context.get('summaries', [])}",
            f"Conclusions: {context.get('conclusions', [])}",
            "",
            "Last command output:",
            f"stdout: {context.get('last_output', {}).get('stdout', '')}",
            f"returncode: {context.get('last_output', {}).get('returncode', '')}",
            "",
            "Please analyze if this task is completed by considering:",
            "1. Has the original task goal been achieved?",
            "2. Do we have all necessary information in the actual command output?", 
            "3. Are the results clear, definitive and based on real output (not assumptions)?",
            "4. Is there any error in the command execution?",
            "",
            "CRITICAL RULES:",
            "1. NEVER make up or assume results that are not in the actual command output",
            "2. If there is no command output, the task CANNOT be complete",
            "3. If the last command failed or had errors, the task CANNOT be complete",
            "4. You MUST quote the exact command output when reporting results",
            "5. You MUST set is_completed=false if you cannot find a specific number in the output",
            "6. NEVER generate fake numbers or results",
            "",
            "Example of correct response when task is not complete:",
            '{',
            '    "is_completed": false,',
            '    "status": "failed",',
            '    "reason": "No valid output found from command execution",',
            '    "evidence": ["Last command returned error: <exact error>"]',
            '}',
            "",
            "Example of correct response when task is complete:",
            '{',
            '    "is_completed": true,',
            '    "status": "completed",',
            '    "reason": "Command successfully executed and returned line count",',
            '    "evidence": ["Command output shows exactly 82646 lines of code"]',
            '}',
            "",
            "Respond in this format:",
            "{",
            "    \"is_completed\": true/false,",
            "    \"status\": \"completed/failed/partial\",",
            "    \"reason\": \"Detailed explanation referencing specific output\",",
            "    \"evidence\": [",
            "        \"Exact quotes from command output showing completion\",",
            "        \"Any errors or issues found in output\"",
            "    ]",
            "}"
        ]

        prompt = "\n".join(prompt_parts)
        response = self._get_llm_response(prompt)
        return extract_json_from_response(response)
    
    def _display_completion_status(self, completion_status: Dict[str, Any]):
        """Display task completion status with evidence"""
        if completion_status.get("is_completed"):
            self.logger.log('STATUS', f"{Fore.GREEN}✓ Task completed{Style.RESET_ALL}")
            if "result" in completion_status and completion_status["result"].get("value"):
                self.logger.log('RESULT', f"{Fore.GREEN}Result:{Style.RESET_ALL} {completion_status['result']['value']}")
                self.logger.log('RESULT', f"{Fore.CYAN}Source:{Style.RESET_ALL} {completion_status['result']['source']}")
        else:
            self.logger.log('STATUS', f"{Fore.YELLOW}⚠ Task not completed{Style.RESET_ALL}")
        
        self.logger.log('STATUS', f"{Fore.CYAN}Status:{Style.RESET_ALL} {completion_status.get('status', 'unknown')}")
        self.logger.log('STATUS', f"{Fore.CYAN}Reason:{Style.RESET_ALL} {completion_status.get('reason', 'No reason provided')}")
        
        if completion_status.get("evidence"):
            self.logger.log('EVIDENCE', f"{Fore.CYAN}Evidence:{Style.RESET_ALL}")
            for evidence in completion_status["evidence"]:
                self.logger.log('EVIDENCE', f"  • {evidence}")
    
    def _get_llm_response(self, prompt: str) -> str:
        """Call LLM to get response with fancy formatting"""
        if self.verbose:
            # 使用斜体和青色显示发送的消息
            self.logger.log('LLM-REQUEST', f"{Fore.CYAN}[{self.llm.get_model_name()}] ╭──────────── 🤖 Prompt ────────────╮{Style.RESET_ALL}", prefix=False)
            for line in prompt.split('\n'):
                if line.strip():
                    self.logger.log('LLM-REQUEST', f"{Fore.CYAN}│ {Style.DIM}{line}{Style.RESET_ALL}", prefix=False)
                else:
                    self.logger.log('LLM-REQUEST', f"{Fore.CYAN}│{Style.RESET_ALL}", prefix=False)  # 空行也保持边框
            self.logger.log('LLM-REQUEST', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}\n", prefix=False)
        
        response = self.llm.chat(prompt)
        
        if self.verbose:
            # 使用斜体和紫色显示收到的回复
            self.logger.log('LLM-RESPONSE', f"{Fore.MAGENTA}[{self.llm.get_model_name()}] ╭──────────── 💭 Response ────────────╮{Style.RESET_ALL}", prefix=False)
            for line in response.split('\n'):
                if line.strip():
                    self.logger.log('LLM-RESPONSE', f"{Fore.MAGENTA}│ {Style.DIM}{line}{Style.RESET_ALL}", prefix=False)
                else:
                    self.logger.log('LLM-RESPONSE', f"{Fore.MAGENTA}│{Style.RESET_ALL}", prefix=False)  # 空行也保持边框
            self.logger.log('LLM-RESPONSE', f"{Fore.MAGENTA}╰──────────────────────────────────────────╯{Style.RESET_ALL}\n", prefix=False)
        
        return response