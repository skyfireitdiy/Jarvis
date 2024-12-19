import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from colorama import Fore, Style

from .base import BaseAgent, AgentState
from .analysis import TaskAnalyzer
from .execution import TaskExecutor
from .reflection import TaskReflector
from .validation import validate_step_format
from utils import extract_json_from_response
from utils.logger import Logger
from llm import BaseLLM

class LlamaAgent(BaseAgent):
    """Main agent class that combines all components"""
    
    def __init__(self, llm: BaseLLM, verbose: bool = False):
        super().__init__(llm=llm, verbose=verbose)
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
        if not isinstance(step, dict):
            return {
                "success": False,
                "error": "Invalid step format",
                "result": None
            }
        
        # 从工具名称中提取工具ID
        tool_name = step.get("tool", "")
        tool_id = tool_name.split("(")[-1].strip(")") if "(" in tool_name else tool_name.lower()  # 添加lower()
        
        # 获取工具实例
        tool = self.tool_registry.get_tool(tool_id)
        
        if not tool:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
                "result": None
            }
        
        # 执行工具
        try:
            parameters = step.get("parameters", {})
            result = tool.execute(**parameters)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": None
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
        
        # Get task plan and previous analyses from context
        current_task_plan = self.task_context.get('task_plan', {})
        previous_analyses = self.task_context.get('analyses', [])
        
        if not current_task_plan:
            # If no task plan exists, create a basic one
            current_task_plan = {
                "overall_goal": task,
                "completed_steps": [],
                "remaining_steps": [],
                "current_focus": "Understanding the task requirements"
            }
        
        # Collect important information from previous analyses
        accumulated_info = {
            "key_findings": [],
            "verified_facts": [],
            "attempted_approaches": [],
            "successful_strategies": [],
            "failed_attempts": []
        }
        
        for prev_analysis in previous_analyses:
            # Collect key information
            if prev_analysis.get('key_info'):
                accumulated_info["key_findings"].extend(prev_analysis['key_info'])
            
            # Track successful steps
            if prev_analysis.get('task_plan', {}).get('completed_steps'):
                for step in prev_analysis['task_plan']['completed_steps']:
                    if isinstance(step, dict) and step.get('result'):
                        accumulated_info["successful_strategies"].append({
                            "step": step.get('step', ''),
                            "result": step.get('result', '')
                        })
            
            # Track failed attempts
            if not prev_analysis.get('success', True):
                accumulated_info["failed_attempts"].append({
                    "step": prev_analysis.get('step', ''),
                    "error": prev_analysis.get('error', '')
                })
        
        # Build prompt parts
        prompt_parts = [
            f"Task: {task}",
            "",
            "Previous Information:",
            "-------------------",
            "Key Findings:",
            *[f"• {finding}" for finding in accumulated_info["key_findings"]],
            "",
            "Verified Facts:",
            *[f"• {fact}" for fact in accumulated_info["verified_facts"]],
            "",
            "Successful Strategies:",
            *[f"• {strategy['step']}: {strategy['result']}" for strategy in accumulated_info["successful_strategies"]],
            "",
            "Failed Attempts:",
            *[f"• {attempt['step']}: {attempt['error']}" for attempt in accumulated_info["failed_attempts"]],
            "",
            "Current Task Plan:",
            json.dumps(current_task_plan, indent=2),
            "",
            "Current Step executed:",
            f"Tool: {step.get('tool', 'unknown')}",
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
            stdout if stdout else "(empty)",
            "",
            "stderr:",
            stderr if stderr else "(empty)",
            "",
            f"returncode: {returncode}",
            "------------",
            "",
            "Please analyze the above information and provide a structured response in JSON format with the following fields:",
            "{",
            '    "conclusion": "Brief summary of what was found or determined",',
            '    "key_info": [',
            '        "List of important information extracted from the result",',
            '        "Each item should be a specific fact or finding"',
            '    ],',
            '    "verified_facts": [',
            '        "List of facts that have been verified through multiple sources or direct evidence"',
            '    ],',
            '    "missing_info": [',
            '        "List of information that is still needed",',
            '        "Each item should be specific and actionable"',
            '    ],',
            '    "task_plan": {',
            '        "overall_goal": "The main objective we are trying to achieve",',
            '        "completed_steps": [',
            '            {',
            '                "step": "Description of completed step",',
            '                "result": "What was achieved"',
            '            }',
            '        ],',
            '        "remaining_steps": [',
            '            {',
            '                "step": "Description of remaining step",',
            '                "expected_result": "What we expect to achieve"',
            '            }',
            '        ],',
            '        "current_focus": "What we are currently working on"',
            '    },',
            '    "next_steps": [',
            '        {',
            '            "tool": "Tool to use",',
            '            "parameters": {"param1": "value1"},',
            '            "description": "What this step will do",',
            '            "success_criteria": ["How we know it worked"]',
            '        }',
            '    ],',
            '    "task_complete": false,',
            '    "user_confirmation_required": false,',
            '    "user_feedback_required": false',
            "}",
            "",
            "CRITICAL RULES:",
            "1. NEVER make up or assume information not present in the actual output",
            "2. If information is missing, list it in missing_info",
            "3. Be specific and precise in your analysis",
            "4. Include actual values and quotes from the output when available",
            "5. task_plan should reflect both what has been done and what is left to do",
            "6. Ensure next_steps align with remaining_steps in the task plan",
            "7. Move the current step to completed_steps if it was successful",
            "8. Update current_focus based on the next immediate step needed",
            "9. Add any new verified facts to the verified_facts list",
            "10. Consider all previous findings when analyzing new information"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        # Update task plan and accumulated info in context
        if analysis.get('task_plan'):
            self.task_context['task_plan'] = analysis['task_plan']
        
        if analysis.get('verified_facts'):
            if 'verified_facts' not in self.task_context:
                self.task_context['verified_facts'] = []
            self.task_context['verified_facts'].extend(analysis['verified_facts'])
        
        # Print analysis results with better formatting
        self.logger.log('Analysis', f"{Fore.CYAN}╭──────────── 🔍 Result Analysis 📊 ────────────╮{Style.RESET_ALL}", prefix=False)
        
        # Print goal/conclusion
        if analysis.get('conclusion'):
            self.logger.log('Analysis', f"{Fore.CYAN}│ Goal:{Style.RESET_ALL} {analysis.get('conclusion')}")
        
        # Print current information
        if analysis.get('key_info'):
            self.logger.log('Analysis', f"{Fore.CYAN}│ Current Info:{Style.RESET_ALL}")
            for info in analysis.get('key_info', []):
                self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{info}")
        
        # Print verified facts
        if analysis.get('verified_facts'):
            self.logger.log('Analysis', f"{Fore.CYAN}│ Verified Facts:{Style.RESET_ALL}")
            for fact in analysis.get('verified_facts', []):
                self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{fact}")
        
        # Print task plan
        if analysis.get('task_plan'):
            self.logger.log('Analysis', f"{Fore.CYAN}│ Task Plan:{Style.RESET_ALL}")
            task_plan = analysis['task_plan']
            self.logger.log('Analysis', f"{Fore.CYAN}│ • Goal:{Style.RESET_ALL} {task_plan['overall_goal']}")
            if task_plan.get('completed_steps'):
                self.logger.log('Analysis', f"{Fore.CYAN}│ • Completed Steps:{Style.RESET_ALL}")
                for step in task_plan['completed_steps']:
                    if isinstance(step, dict):
                        self.logger.log('Analysis', f"{Fore.CYAN}│   - {Style.RESET_ALL}{step['step']}: {step['result']}")
                    else:
                        self.logger.log('Analysis', f"{Fore.CYAN}│   - {Style.RESET_ALL}{step}")
            if task_plan.get('remaining_steps'):
                self.logger.log('Analysis', f"{Fore.CYAN}│ • Remaining Steps:{Style.RESET_ALL}")
                for step in task_plan['remaining_steps']:
                    if isinstance(step, dict):
                        self.logger.log('Analysis', f"{Fore.CYAN}│   - {Style.RESET_ALL}{step['step']}: {step['expected_result']}")
                    else:
                        self.logger.log('Analysis', f"{Fore.CYAN}│   - {Style.RESET_ALL}{step}")
            self.logger.log('Analysis', f"{Fore.CYAN}│ • Current Focus:{Style.RESET_ALL} {task_plan['current_focus']}")
        
        # Print missing information
        if analysis.get('missing_info'):
            self.logger.log('Analysis', f"{Fore.CYAN}│ Missing Info:{Style.RESET_ALL}")
            for info in analysis.get('missing_info', []):
                self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{info}")
        
        # Print next steps if any
        if analysis.get('next_steps'):
            self.logger.log('Analysis', f"{Fore.CYAN}│ Next Steps:{Style.RESET_ALL}")
            for step in analysis.get('next_steps', []):
                if isinstance(step, dict):
                    self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{step['description']}")
                else:
                    self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{step}")
        
        self.logger.log('Analysis', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}", prefix=False)
        
        # Store current analysis in task context
        if 'analyses' not in self.task_context:
            self.task_context['analyses'] = []
        self.task_context['analyses'].append(analysis)
        
        # Handle user confirmation only when task is complete
        if analysis.get("task_complete") and analysis.get("user_confirmation_required"):
            # 构建当前信息摘要
            current_info = []
            if analysis.get('key_info'):
                current_info.extend(analysis['key_info'])
            
            # 构建缺失信息摘要
            missing_info = []
            if analysis.get('missing_info'):
                missing_info.extend(analysis['missing_info'])
            
            # 格式化提示信息
            confirmation_msg = (
                f"\n📝 Here's what I found:\n"
                + "\n".join(f"✓ {info}" for info in current_info)
            )
            
            if missing_info:
                confirmation_msg += (
                    f"\n\n❓ Still missing:\n"
                    + "\n".join(f"• {info}" for info in missing_info)
                    + "\n\nWould you like me to continue searching for this information? (yes/no)"
                )
            else:
                confirmation_msg += "\n\nIs this information sufficient? (yes/no)"
            
            print(f"\n{Fore.YELLOW}{confirmation_msg}{Style.RESET_ALL}")
            response = input(f"{Fore.GREEN}> {Style.RESET_ALL}").strip().lower()
            
            # If user is not satisfied, get feedback and prepare next step
            if response not in ['y', 'yes', 'done', 'complete']:
                analysis['task_complete'] = False
                if analysis.get("user_feedback_required"):
                    if missing_info:
                        feedback_msg = "Which missing information should I focus on first?"
                    else:
                        feedback_msg = "What additional information would you like me to find?"
                    
                    print(f"\n{Fore.YELLOW}🤔 {feedback_msg}{Style.RESET_ALL}")
                    feedback = input(f"{Fore.GREEN}> {Style.RESET_ALL}").strip()
                    if feedback:
                        self.user_suggestions.append(feedback)
            else:
                # If user is satisfied, mark task as complete
                analysis['task_complete'] = True
                return analysis
            
            # If user wants to continue (responded with 'yes'), prepare next step
            if response in ['y', 'yes']:
                # Update task plan to reflect the need for more information
                if 'task_plan' not in analysis:
                    analysis['task_plan'] = current_task_plan
                
                # Add missing information to remaining steps
                if missing_info and analysis['task_plan'].get('remaining_steps') is not None:
                    for info in missing_info:
                        analysis['task_plan']['remaining_steps'].append({
                            "step": f"Search for {info}",
                            "expected_result": f"Obtain {info}"
                        })
                
                # Update current focus
                if missing_info:
                    analysis['task_plan']['current_focus'] = f"Searching for {missing_info[0]}"
                
                # Prepare next step
                analysis['next_steps'] = [{
                    "tool": "search",
                    "parameters": {
                        "query": f"{task} {missing_info[0] if missing_info else ''}"
                    },
                    "description": f"Search for {missing_info[0] if missing_info else 'additional information'}",
                    "success_criteria": ["Find relevant information about the missing details"]
                }]
        
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
        """Call LLM to get response"""
        if self.verbose:
            self.logger.log('LLM-REQUEST', f"Sending prompt to LLM ({self.llm.get_model_name()}):\n{prompt}")
        
        # Convert prompt to chat message format
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.get_chat_completion(messages)
        
        if self.verbose:
            self.logger.log('LLM-RESPONSE', f"Received response from LLM:\n{response}")
        
        return response
    
    def get_user_suggestion(self) -> str:
        """Get suggestion from user"""
        print(f"\n{Fore.YELLOW}🤔 I'm not sure what to do next. Could you help me by:{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}1. Providing more specific information about what you want{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}2. Suggesting a different approach{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}3. Clarifying any ambiguous parts{Style.RESET_ALL}")
        print("(Press Enter to stop)")
        suggestion = input(f"{Fore.GREEN}> {Style.RESET_ALL}").strip()
        if suggestion:
            print(f"{Fore.GREEN}👍 Thanks! I'll try with your suggestion.{Style.RESET_ALL}")
            self.user_suggestions.append(suggestion)
        return suggestion
    
    def analyze_result(self, result: Dict[str, Any], task: str) -> Dict[str, Any]:
        """Analyze tool execution result"""
        self.state = AgentState.ANALYZING
        
        # Prepare analysis prompt
        prompt = f"""
I need to accomplish this task: {task}

Tool execution result:
------------
Success: {result.get('success')}
Error: {result.get('error')}

Output:
stdout:
{result.get('result', {}).get('stdout', '')}

stderr:
{result.get('result', {}).get('stderr', '')}

returncode: {result.get('result', {}).get('returncode')}
------------

{self.get_analysis_prompt()}
"""
        
        # Get analysis from LLM
        analysis = self._get_llm_response(prompt)
        
        # Parse analysis
        try:
            analysis_data = json.loads(analysis)
            
            # Print analysis result with consistent formatting
            self.logger.log('Analysis', f"{Fore.CYAN}╭──────────── 🔍 Analysis Started ────────────╮{Style.RESET_ALL}", prefix=False)
            
            # Print goal/conclusion
            if analysis_data.get('conclusion'):
                self.logger.log('Analysis', f"{Fore.CYAN}│ Goal:{Style.RESET_ALL} {analysis_data.get('conclusion')}")
            
            # Print current information
            if analysis_data.get('key_info'):
                self.logger.log('Analysis', f"{Fore.CYAN}│ Current Info:{Style.RESET_ALL}")
                for info in analysis_data.get('key_info', []):
                    self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{info}")
            
            # Print missing information
            if analysis_data.get('missing_info'):
                self.logger.log('Analysis', f"{Fore.CYAN}│ Missing Info:{Style.RESET_ALL}")
                for info in analysis_data.get('missing_info', []):
                    self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{info}")
            
            # Print next steps if any
            if analysis_data.get('next_steps'):
                self.logger.log('Analysis', f"{Fore.CYAN}│ Next Steps:{Style.RESET_ALL}")
                for step in analysis_data.get('next_steps', []):
                    self.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{step}")
            
            self.logger.log('Analysis', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}", prefix=False)
            
            # Handle user confirmation only when task is complete
            if analysis_data.get("task_complete") and analysis_data.get("user_confirmation_required"):
                confirmation_msg = analysis_data.get("user_confirmation_message", 
                    "I have completed the task. Is this information sufficient or would you like additional details?")
                print(f"\n{Fore.YELLOW}👋 {confirmation_msg}{Style.RESET_ALL}")
                response = input("> ").strip().lower()
                
                # If user is not satisfied, get feedback
                if response not in ['y', 'yes', 'done', 'complete']:
                    analysis_data['task_complete'] = False
                    if analysis_data.get("user_feedback_required"):
                        feedback_msg = "What additional information would you like me to focus on?"
                        print(f"\n{Fore.YELLOW}🤔 {feedback_msg}{Style.RESET_ALL}")
                        feedback = input("> ").strip()
                        if feedback:
                            self.user_suggestions.append(feedback)
            
            return analysis_data
            
        except json.JSONDecodeError:
            self.logger.log('ERROR', "Failed to parse analysis response")
            return {
                "can_conclude": False,
                "conclusion": "Failed to parse analysis",
                "has_valid_data": False,
                "needs_retry": True,
                "validation_errors": ["Failed to parse analysis response"],
                "task_complete": False
            }