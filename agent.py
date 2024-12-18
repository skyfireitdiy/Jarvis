import ollama
from enum import Enum
import json
from typing import Dict, Any, Optional, List
from colorama import Fore, Style

from logger import ColorLogger
from tools import Tool, ToolRegistry
from utils import extract_json_from_response

class AgentState(Enum):
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    REFLECTING = "reflecting"

class LlamaAgent:
    def __init__(self, verbose: bool = False):
        self.model = "llama3:latest"
        self.state = AgentState.ANALYZING
        self.tool_registry = ToolRegistry()
        self.task_history = []
        self.current_task = None
        self.thought_process = []
        self.logger = ColorLogger()
        self.verbose = verbose
        # Track tried tool-parameter combinations
        self.tried_combinations = set()
        # Store user suggestions
        self.user_suggestions = []
    
    def register_tool(self, tool: Tool):
        """Register a new tool"""
        self.tool_registry.register(tool)
    
    def _get_llm_response(self, prompt: str) -> str:
        """Call Llama model to get response"""
        if self.verbose:
            self.logger.log('LLM-REQUEST', f"Sending prompt to LLM:\n{prompt}")
        
        response = ollama.chat(model=self.model, messages=[
            {'role': 'user', 'content': prompt}
        ])
        
        if self.verbose:
            self.logger.log('LLM-RESPONSE', f"Received response from LLM:\n{response['message']['content']}")
        
        return response['message']['content']

    def validate_task_format(self, analysis: Dict[str, Any]) -> bool:
        """Validate task analysis format"""
        try:
            if not isinstance(analysis.get("subtasks"), list):
                return False
            
            for subtask in analysis["subtasks"]:
                if not isinstance(subtask, dict):
                    return False
                if "tool" not in subtask:
                    return False
                if not isinstance(subtask.get("parameters", {}), dict):
                    return False
                
            return True
        except Exception:
            return False

    def get_user_suggestion(self) -> str:
        """Get suggestion from user"""
        print(f"\n{Fore.YELLOW}🤔 The task seems difficult. Do you have any suggestions?{Style.RESET_ALL}")
        print("(Press Enter to skip)")
        suggestion = input("> ").strip()
        if suggestion:
            print(f"{Fore.GREEN}👍 Thanks! I'll try with your suggestion.{Style.RESET_ALL}")
            # Store the suggestion
            self.user_suggestions.append(suggestion)
        return suggestion

    def _get_suggestions_context(self) -> str:
        """Get user suggestions formatted for prompts"""
        if not self.user_suggestions:
            return ""
        
        suggestions = [f"- {suggestion}" for suggestion in self.user_suggestions]
        return "\nUser suggestions:\n" + "\n".join(suggestions)

    def retry_task_analysis(self, task: str, previous_response: str, retry_count: int = 0) -> Dict[str, Any]:
        """Retry task analysis with reflection and improvements"""
        if retry_count >= 3:
            # Get user suggestion after max retries
            suggestion = self.get_user_suggestion()
            if suggestion:
                # Add suggestion to prompt
                reflection_prompt = f"""
                Task to complete: {task}
                
                User suggestion: {suggestion}
                
                Available Tools:
                {self.tool_registry.get_tools_description()}
                
                Current Progress:
                {chr(10).join(self.task_context.get("summaries", [])) if self.task_context.get("summaries") else "No steps completed yet"}
                
                Previous attempt failed. Please consider the user's suggestion and try again.
                
                Return your response in this JSON format:
                {{
                    "analysis": {{
                        "is_completed": true/false,
                        "conclusion": "clear statement about task status/result",
                        "reason": "explanation of why the task is completed or not",
                        "evidence": ["specific evidence from results that supports the conclusion"]
                    }},
                    "next_step": {{
                        "tool": "tool_name",
                        "parameters": {{"param_name": "param_value"}},
                        "description": "what this step will do",
                        "success_criteria": ["criterion1", "criterion2"]
                    }} if not completed else null,
                    "required_tasks": [],
                    "is_final_step": true if completed else false
                }}
                """
                
                response = self._get_llm_response(reflection_prompt)
                analysis = extract_json_from_response(response)
                
                if "error" not in analysis and self.validate_step_format(analysis):
                    return analysis
            
            self.logger.log('ERROR', "Maximum retry count reached", is_error=True)
            return {
                "error": "Maximum retry count reached",
                "original_response": previous_response
            }
        
        self.logger.log('RETRY', f"Retry {retry_count + 1} for task analysis")
        
        # Create a detailed summary of completed steps and their results
        completed_summary = []
        for i, (var_name, result) in enumerate(sorted(self.task_context["variables"].items())):
            step_num = i + 1
            if isinstance(result, dict):
                # For structured results, try to create a meaningful description
                if "description" in result:
                    completed_summary.append(f"{step_num}. {result['description']}")
                elif "stdout" in result:
                    completed_summary.append(f"{step_num}. Output: {result['stdout']}")
                else:
                    completed_summary.append(f"{step_num}. Result: {json.dumps(result, ensure_ascii=False)}")
            else:
                completed_summary.append(f"{step_num}. Result: {result}")
        
        reflection_prompt = f"""
        Your previous response was not in the correct format.
        
        Task to complete: {task}
        
        Available Tools:
        {self.tool_registry.get_tools_description()}
        
        Current Progress:
        {chr(10).join(completed_summary) if completed_summary else "No steps completed yet"}
        
        Previous response:
        {previous_response}
        
        First, analyze if the task is already completed based on the current progress.
        You must provide a clear conclusion about whether the task goal has been achieved.
        
        For example, if the task is to check if a host is online:
        - If you see successful ping results, conclude "Host is online" with the ping response as evidence
        - If you see failed ping results, conclude "Host is offline" with the error messages as evidence
        - If you haven't checked the host yet, conclude "Status unknown" with "No checks performed yet" as evidence
        
        Then, if the task is not completed, provide the next step that would help complete it.
        
        Return your response in this JSON format:
        {{
            "analysis": {{
                "is_completed": true/false,
                "conclusion": "clear statement about task status/result",
                "reason": "explanation of why the task is completed or not",
                "evidence": ["specific evidence from results that supports the conclusion"]
            }},
            "next_step": {{
                "tool": "tool_name",
                "parameters": {{"param_name": "param_value"}},
                "description": "what this step will do",
                "success_criteria": ["criterion1", "criterion2"]
            }} if not completed else null,
            "required_tasks": [],
            "is_final_step": true if completed else false
        }}
        
        Note:
        1. The conclusion must be clear and specific about what was found/achieved
        2. Evidence must be actual output/results from completed steps
        3. Don't repeat steps that have already provided good results
        4. Set is_completed to true if you can make a definitive conclusion
        5. If more checks are needed, explain why in the reason
        """
        
        response = self._get_llm_response(reflection_prompt)
        analysis = extract_json_from_response(response)
        
        if "error" in analysis or not self.validate_step_format(analysis):
            return self.retry_task_analysis(task, response, retry_count + 1)
        
        return analysis

    def analyze_task(self, task: str) -> Dict[str, Any]:
        """Analyze task and return execution plan"""
        self.state = AgentState.ANALYZING
        self.logger.log('ANALYSIS', f"Analyzing task: {task}")
        
        # Create a detailed summary of completed steps and their results
        completed_summary = []
        for i, (var_name, result) in enumerate(sorted(self.task_context["variables"].items())):
            step_num = i + 1
            if isinstance(result, dict):
                if "description" in result:
                    completed_summary.append(f"{step_num}. {result['description']}")
                elif "stdout" in result:
                    completed_summary.append(f"{step_num}. Output: {result['stdout']}")
                else:
                    completed_summary.append(f"{step_num}. Result: {json.dumps(result, ensure_ascii=False)}")
            else:
                completed_summary.append(f"{step_num}. Result: {result}")
        
        # Include extracted information and conclusions in the summary
        if self.task_context.get("summaries"):
            completed_summary.extend([
                f"Found information:",
                *[f"- {info}" for info in self.task_context["summaries"]]
            ])
        
        if self.task_context.get("conclusions"):
            completed_summary.extend([
                f"Conclusions drawn:",
                *[f"- {conclusion}" for conclusion in self.task_context["conclusions"]]
            ])
        
        # Add user suggestions to the prompt
        suggestions_context = self._get_suggestions_context()
        
        # Zero-shot prompt template
        prompt = f"""
        I need to accomplish this task: {task}

        These are the tools I have available:
        {self.tool_registry.get_tools_description()}

        So far, this is what has been done:
        {chr(10).join(completed_summary) if completed_summary else "Nothing has been done yet"}
        {suggestions_context}

        Could you help me:
        1. Understand what exactly needs to be accomplished
        2. Identify what information we already have
        3. Determine what information we still need
        4. Plan the next step if we're not done
        5. Consider any user suggestions when planning the next step

        Please structure your response in this JSON format:
        {{
            "analysis": {{
                "is_completed": false,
                "task_goal": "What exactly needs to be accomplished",
                "current_info": "What information we already have",
                "missing_info": "What information we still need",
                "evidence": ["Specific fact we found 1", "Specific fact we found 2"]
            }},
            "next_step": {{
                "tool": "tool_name",
                "parameters": {{"param_name": "param_value"}},
                "description": "What we'll do next",
                "success_criteria": ["How we'll know it worked"]
            }},
            "required_tasks": [],
            "is_final_step": false
        }}

        Important:
        - Be specific about what information we have and what we need
        - Only mark as completed if we have everything we need
        - Make sure the next step directly helps get missing information
        - Include actual values and facts in the evidence
        """
        
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        if self.verbose:
            self.logger.log('ANALYSIS-RESULT', f"Parsed analysis:\n{json.dumps(analysis, indent=2, ensure_ascii=False)}")
        
        if "error" in analysis or not self.validate_step_format(analysis):
            if self.verbose:
                self.logger.log('ANALYSIS-ERROR', "Invalid analysis format, retrying...")
            return self.retry_task_analysis(task, response)
        
        # Log analysis results with highlights
        self.logger.log('ANALYSIS', f"{Fore.GREEN}Goal:{Style.RESET_ALL} {analysis['analysis']['task_goal']}")
        
        if analysis['analysis']['current_info']:
            self.logger.log('ANALYSIS', f"{Fore.CYAN}Current Info:{Style.RESET_ALL}")
            current_info = analysis['analysis']['current_info'].split('\n')
            for info in current_info:
                if info.strip():
                    self.logger.log('ANALYSIS', f"{Fore.CYAN}• {info.strip()}{Style.RESET_ALL}")
        
        if analysis['analysis']['missing_info']:
            self.logger.log('ANALYSIS', f"{Fore.YELLOW}Missing Info:{Style.RESET_ALL}")
            missing_info = analysis['analysis']['missing_info'].split('\n')
            for info in missing_info:
                if info.strip():
                    self.logger.log('ANALYSIS', f"{Fore.RED}• {info.strip()}{Style.RESET_ALL}")
        
        if analysis['analysis']['evidence']:
            self.logger.log('ANALYSIS', f"{Fore.GREEN}Evidence:{Style.RESET_ALL}")
            for evidence in analysis['analysis']['evidence']:
                self.logger.log('ANALYSIS', f"{Fore.MAGENTA}• {evidence}{Style.RESET_ALL}")
        
        return analysis

    def validate_step_format(self, analysis: Dict[str, Any]) -> bool:
        """Validate single step analysis format"""
        try:
            # Check analysis section
            if not isinstance(analysis.get("analysis"), dict):
                return False
            
            analysis_dict = analysis["analysis"]
            required_fields = [
                "is_completed", "task_goal", "current_info", 
                "missing_info", "evidence"
            ]
            
            # 验证所有必需字段存且格式正确
            for field in required_fields:
                if field not in analysis_dict:
                    return False
                
            if not isinstance(analysis_dict["is_completed"], bool):
                return False
            if not isinstance(analysis_dict["task_goal"], str):
                return False
            if not isinstance(analysis_dict["current_info"], str):
                return False
            if not isinstance(analysis_dict["missing_info"], str):
                return False
            if not isinstance(analysis_dict["evidence"], list):
                return False
            
            # Check next_step section if task is not completed
            if not analysis_dict["is_completed"]:
                next_step = analysis.get("next_step")
                if not isinstance(next_step, dict):
                    return False
                required_fields = ["tool", "parameters", "description", "success_criteria"]
                if not all(key in next_step for key in required_fields):
                    self.logger.log('ERROR', f"Missing required fields in next_step: {[f for f in required_fields if f not in next_step]}", is_error=True)
                    return False
                if not isinstance(next_step["parameters"], dict):
                    return False
                if not isinstance(next_step["success_criteria"], list):
                    return False
                if not isinstance(next_step["description"], str):
                    return False
                if not next_step["description"].strip():
                    return False
            else:
                # For completed tasks, next_step should be null
                if analysis.get("next_step") is not None:
                    return False
            
            # Check required fields
            if not isinstance(analysis.get("required_tasks"), list):
                return False
            
            if not isinstance(analysis.get("is_final_step"), bool):
                return False
            
            # Validate is_final_step matches is_completed
            if analysis["is_final_step"] != analysis_dict["is_completed"]:
                return False
            
            return True
        except Exception as e:
            self.logger.log(self.state.value, f"Validation error: {str(e)}", is_error=True)
            return False

    def _substitute_variables(self, content: str, context: Dict[str, Any]) -> str:
        """Replace {{variable}} placeholders with actual values from context"""
        if not isinstance(content, str):
            return content
            
        import re
        pattern = r'\{\{([^}]+)\}\}'
        
        def replace(match):
            var_name = match.group(1)
            return str(context['variables'].get(var_name, f"{{{{missing_var:{var_name}}}}}"))
            
        return re.sub(pattern, replace, content)

    def analyze_tool_result(self, task: str, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze tool execution result using AI"""
        # Get a summary of the result first
        summary = self._summarize_tool_result(task, step, result)
        
        # Add summary to result for better context
        result["summary"] = summary
        
        # Add user suggestions to the prompt
        suggestions_context = self._get_suggestions_context()
        
        # Define the validation format separately to reduce nesting
        validation_format = """
        "info_validation": {
            "required_info": ["List all pieces of information required by the task"],
            "found_info": {
                "<info_name>": {
                    "found": true/false,
                    "value": "actual value if found",
                    "valid": true/false,
                    "validation_error": "error message if invalid"
                }
            }
        }"""
        
        # Define the base response format
        response_format = """
        {
            "can_conclude": true/false,
            "conclusion": "Final conclusion if task can be concluded, otherwise null",
            "key_info": [
                "Each piece of information found, in format: <type>: <exact value>",
                "Example: Value A: 123",
                "Example: Status B: active",
                "Example: Result C: success"
            ],
            "missing_info": [
                "Each piece of required information that is missing"
            ],
            %s,
            "reason": "Detailed explanation of why we can/cannot conclude",
            "has_valid_data": true/false,
            "needs_retry": true/false,
            "validation_errors": [
                "List any validation errors found"
            ]
        }""" % validation_format
        
        prompt = f"""
        Task: {task}
        
        Step executed:
        - Tool: {step['tool']}
        - Description: {step['description']}
        - Success criteria: {', '.join(step['success_criteria'])}
        
        Result Summary:
        {json.dumps(summary, ensure_ascii=False, indent=2)}
        
        Full Result:
        {json.dumps(result, ensure_ascii=False, indent=2)}
        {suggestions_context}
        
        Please analyze this result carefully and thoroughly:
        1. For empty or error results, NEVER conclude the task is complete
        2. For any task, require ALL requested information to be present before concluding
        3. Check that the output contains EVERY piece of information mentioned in the task
        4. Verify the format and content of EACH required piece of information
        5. If ANY required information is missing or invalid, set has_valid_data=false
        6. ONLY draw conclusions based on actual tool output data
        7. Do NOT make assumptions or inferences without supporting data
        8. If data is ambiguous or unclear, mark it as invalid
        
        Data Validation Rules:
        1. Every conclusion must be directly supported by tool output
        2. Each piece of information must be explicitly present in the result
        3. Do not infer values that aren't in the data
        4. Mark data as invalid if it doesn't match expected format
        5. For missing or unclear data, request additional tool execution
        
        Required Information Checklist:
        1. List each piece of information required by the task
        2. For each piece, mark whether it was found in the result
        3. For each found piece, verify its format and validity
        4. Only set can_conclude=true if ALL required information is present and valid
        5. For each conclusion, cite the specific tool output that supports it
        
        Return your analysis in this JSON format:
        {response_format}
        
        Important:
        - NEVER conclude without ALL required information
        - Each piece of required information must be explicitly validated
        - Format validation errors must be specific and clear
        - Missing information must be clearly listed
        - Conclusion must include ALL found information in a clear format
        - If information is incomplete, explain exactly what is missing
        - Every conclusion must cite supporting tool output
        - Do not make assumptions beyond the actual data
        - If data is unclear, request clarification rather than guessing
        """
        
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        # Ensure all required fields are present
        default_analysis = {
            "can_conclude": False,
            "conclusion": None,
            "key_info": [],
            "missing_info": ["No information extracted"],
            "info_validation": {
                "required_info": [],
                "found_info": {}
            },
            "reason": "Failed to analyze result",
            "has_valid_data": False,
            "needs_retry": True,
            "validation_errors": ["Analysis failed to produce valid result"]
        }
        
        # Update default values with any valid values from the analysis
        for key in default_analysis:
            if key in analysis and analysis[key] is not None:
                default_analysis[key] = analysis[key]
        
        if self.verbose:
            self.logger.log('TOOL-ANALYSIS', f"Tool result analysis:")
            if analysis.get("key_info"):
                self.logger.log('TOOL-ANALYSIS', f"{Fore.GREEN}Found information:{Style.RESET_ALL}")
                for info in analysis["key_info"]:
                    self.logger.log('TOOL-ANALYSIS', f"{Fore.CYAN}• {info}{Style.RESET_ALL}")
            if analysis.get("missing_info"):
                self.logger.log('TOOL-ANALYSIS', f"{Fore.YELLOW}Missing information:{Style.RESET_ALL}")
                for info in analysis["missing_info"]:
                    self.logger.log('TOOL-ANALYSIS', f"{Fore.RED}• {info}{Style.RESET_ALL}")
        
        return default_analysis

    def _reflect_on_tool_usage(self, task: str, step: Dict[str, Any], result: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
        """Reflect on how to improve the tool usage"""
        # Add user suggestions to the prompt
        suggestions_context = self._get_suggestions_context()
        
        prompt = f"""
        Task: {task}
        
        Current tool usage:
        - Tool: {step['tool']}
        - Description: {step['description']}
        - Command/Action: {json.dumps(step['parameters'], ensure_ascii=False)}
        
        Result:
        {json.dumps(result, ensure_ascii=False, indent=2)}
        
        Summary:
        {json.dumps(summary, ensure_ascii=False, indent=2)}
        {suggestions_context}
        
        The current tool usage didn't provide helpful information.
        Please help me improve the tool usage by considering:
        1. Are we using the right parameters?
        2. Could we modify the command to get better output?
        3. Are there any options we should add?
        4. Is the tool being used correctly?
        
        Return your reflection in this JSON format:
        {{
            "reason": "Clear explanation of what's wrong with the current tool usage",
            "problems": [
                "Specific issues with how the tool is being used",
                "Example: Missing required flag",
                "Example: Incorrect parameter format"
            ],
            "improved_approach": {{
                "tool": "same_tool_name",
                "parameters": {{"improved_params": "better_values"}},
                "description": "How we'll use the tool better",
                "success_criteria": ["How we'll know it worked"]
            }},
            "explanation": "Why these improvements will help"
        }}
        
        Important:
        - Focus on improving how we use the current tool
        - Suggest specific parameter/option changes
        - Keep using the same tool, just better
        - Think about command flags, formats, options
        """
        
        response = self._get_llm_response(prompt)
        reflection = extract_json_from_response(response)
        
        if self.verbose:
            self.logger.log('TOOL-REFLECTION', f"Tool usage reflection:\n{json.dumps(reflection, indent=2, ensure_ascii=False)}")
        
        return reflection

    def _reflect_on_approach(self, task: str, step: Dict[str, Any], result: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
        """Reflect on the overall approach when tool improvements didn't help"""
        # Add user suggestions to the prompt
        suggestions_context = self._get_suggestions_context()
        
        prompt = f"""
        Task: {task}
        
        Current approach:
        - Tool: {step['tool']}
        - Description: {step['description']}
        - Command/Action: {json.dumps(step['parameters'], ensure_ascii=False)}
        
        Result after tool improvements:
        {json.dumps(result, ensure_ascii=False, indent=2)}
        
        Summary:
        {json.dumps(summary, ensure_ascii=False, indent=2)}
        {suggestions_context}
        
        Even with improved tool usage, we're not getting helpful information.
        Please help me rethink the approach by considering:
        1. Are we using the right tool for this task?
        2. Is there a better way to get this information?
        3. Should we break this down differently?
        4. Are we asking the right questions?
        
        Return your reflection in this JSON format:
        {{
            "reason": "Clear explanation of why the current approach isn't working",
            "problems": [
                "Fundamental issues with the current approach",
                "Example: Wrong tool for this type of task",
                "Example: Need to gather different information first"
            ],
            "improved_approach": {{
                "tool": "different_tool_name",
                "parameters": {{"param_name": "param_value"}},
                "description": "What the new approach will do",
                "success_criteria": ["How we'll know it worked"]
            }},
            "explanation": "Why this new approach should work better"
        }}
        
        Important:
        - Consider completely different approaches
        - Think about using different tools
        - Consider breaking the task down differently
        - Focus on getting the right information
        """
        
        response = self._get_llm_response(prompt)
        reflection = extract_json_from_response(response)
        
        if self.verbose:
            self.logger.log('APPROACH-REFLECTION', f"Approach reflection:\n{json.dumps(reflection, indent=2, ensure_ascii=False)}")
        
        return reflection

    def _summarize_tool_result(self, task: str, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize tool execution result and extract useful information"""
        prompt = f"""
        Task: {task}
        
        Step executed:
        - Tool: {step['tool']}
        - Description: {step['description']}
        - Command/Action: {json.dumps(step['parameters'], ensure_ascii=False)}
        - Success criteria: {', '.join(step['success_criteria'])}
        
        Result:
        {json.dumps(result, ensure_ascii=False, indent=2)}
        
        Please help me:
        1. Extract any useful information from this result
        2. Identify what this tells us about the task
        3. Draw direct conclusions from the information
        4. Determine if we found anything that helps complete the task
        5. Evaluate if this approach was helpful
        
        Return your summary in this JSON format:
        {{
            "extracted_info": [
                "Each piece of useful information found, in format: <type>: <value>",
                "Example: Command: ping -c 1 192.168.1.1",
                "Example: Response Time: 20ms",
                "Example: Status: Host is reachable"
            ],
            "operation": {{
                "tool_used": "Name of the tool that was used",
                "action_taken": "Specific action or command that was executed",
                "target": "What the action was performed on",
                "outcome": "What happened as a result"
            }},
            "conclusions": [
                "Direct conclusions that can be drawn from the information",
                "Example: 192.168.1.1 is online",
                "Example: Server response time is within normal range"
            ],
            "relevance": "How this information helps with the task (or 'none' if unhelpful)",
            "completeness": "What aspects of the task this information satisfies",
            "missing_aspects": "What aspects of the task still need information",
            "approach_effectiveness": "Was this approach effective? Why or why not?"
        }}
        """
        
        response = self._get_llm_response(prompt)
        summary = extract_json_from_response(response)
        
        if self.verbose:
            self.logger.log('TOOL-SUMMARY', f"Tool result summary:\n{json.dumps(summary, indent=2, ensure_ascii=False)}")
        
        # Add operation information to extracted info if not already present
        if "operation" in summary:
            op_info = summary["operation"]
            operation_details = [
                f"Tool: {op_info['tool_used']}",
                f"Action: {op_info['action_taken']}",
                f"Target: {op_info['target']}",
                f"Outcome: {op_info['outcome']}"
            ]
            
            # Add operation details to the beginning of extracted_info
            if "extracted_info" not in summary:
                summary["extracted_info"] = []
            summary["extracted_info"] = operation_details + summary["extracted_info"]
        
        # Add conclusions to the task context
        if "conclusions" in summary and summary["conclusions"]:
            if "conclusions" not in self.task_context:
                self.task_context["conclusions"] = []
            self.task_context["conclusions"].extend(summary["conclusions"])
            
            # Add conclusions to summaries with a "Conclusion:" prefix
            self.task_context["summaries"].extend([
                f"Conclusion: {conclusion}" for conclusion in summary["conclusions"]
            ])
        
        return summary

    def _has_tried_combination(self, tool: str, parameters: Dict[str, Any]) -> bool:
        """Check if we've already tried this tool-parameter combination"""
        # Convert parameters to a string for hashing
        param_str = json.dumps(parameters, sort_keys=True)
        combination = (tool, param_str)
        return combination in self.tried_combinations

    def _add_tried_combination(self, tool: str, parameters: Dict[str, Any]):
        """Add a tool-parameter combination to the tried set"""
        param_str = json.dumps(parameters, sort_keys=True)
        self.tried_combinations.add((tool, param_str))

    def _reflect_on_timeout(self, task: str, step: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        """Reflect on why the command timed out and how to fix it"""
        prompt = f"""
        Task: {task}
        
        Step that timed out:
        - Tool: {step['tool']}
        - Command/Action: {json.dumps(step['parameters'], ensure_ascii=False)}
        - Timeout: {timeout} seconds
        
        Please analyze why this step might have timed out and suggest improvements:
        1. Is this a command that might hang or run indefinitely?
        2. Does the command need a way to limit its execution?
        3. Would a different command be more appropriate?
        4. Should we add specific timeout or limit options?
        
        Common timeout causes:
        1. Network scanning without limits (e.g., nmap without target limits)
        2. Continuous monitoring commands (e.g., top without -n)
        3. Waiting for user input
        4. Large data processing without limits
        5. Infinite loops or recursion
        
        Return your analysis in this JSON format:
        {
            "timeout_cause": "Likely reason for the timeout",
            "is_command_problematic": true/false,
            "problems": [
                "List specific issues with the command"
            ],
            "improved_approach": {
                "tool": "tool_name",
                "parameters": {"param_name": "param_value"},
                "description": "What this improved step will do",
                "success_criteria": ["How we'll know it worked"]
            }
        }
        
        Important:
        - Focus on making commands exit cleanly
        - Add appropriate limits and constraints
        - Consider using more specific commands
        - Avoid commands that wait for user input
        - Add timeout options where available
        """
        
        response = self._get_llm_response(prompt)
        reflection = extract_json_from_response(response)
        
        if self.verbose:
            self.logger.log('TIMEOUT-REFLECTION', f"Timeout analysis:\n{json.dumps(reflection, indent=2, ensure_ascii=False)}")
        
        return reflection

    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step"""
        self.state = AgentState.EXECUTING
        tool_name = step.get("tool")
        parameters = step.get("parameters", {})
        
        # Check if we've already tried this combination
        if self._has_tried_combination(tool_name, parameters):
            self.logger.log('SKIP', f"Already tried {tool_name} with these parameters", is_error=True)
            return {
                "error": "Combination already tried",
                "details": {
                    "tool": tool_name,
                    "parameters": parameters
                }
            }
        
        # Add this combination to tried set
        self._add_tried_combination(tool_name, parameters)
        
        # Log step details
        self.logger.log('STEP', f"Executing: {step['description']}")
        self.logger.log('STEP', f"Tool: {tool_name}")
        self.logger.log('STEP', f"Parameters: {json.dumps(parameters, ensure_ascii=False)}")
        
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return {
                "error": f"Tool not found: {tool_name}",
                "details": {
                    "available_tools": list(self.tool_registry.tools.keys())
                }
            }
        
        try:
            result = tool.execute(**parameters)
            return result
        except TimeoutError as e:
            # When timeout occurs, reflect on the command
            timeout_reflection = self._reflect_on_timeout(self.current_task, step, parameters.get("timeout", 30))
            
            if timeout_reflection.get("is_command_problematic", False):
                # Log the reflection
                self.logger.log('TIMEOUT', f"Command may be problematic:")
                for problem in timeout_reflection.get("problems", []):
                    self.logger.log('TIMEOUT', f"• {problem}")
                
                # If we have an improved approach, return it with the error
                if "improved_approach" in timeout_reflection:
                    return {
                        "error": f"Command timed out: {str(e)}",
                        "timeout_analysis": timeout_reflection,
                        "improved_approach": timeout_reflection["improved_approach"]
                    }
            
            # If no specific improvements found, return generic timeout error
            return {
                "error": f"Command timed out: {str(e)}",
                "details": {
                    "timeout": parameters.get("timeout", 30),
                    "command": parameters.get("command", "unknown")
                }
            }
        except Exception as e:
            return {
                "error": str(e),
                "details": {
                    "exception_type": type(e).__name__,
                    "parameters": parameters
                }
            }
    
    def reflect_on_result(self, step_result: Dict[str, Any]) -> Dict[str, Any]:
        """Reflect on execution result"""
        self.state = AgentState.REFLECTING
        self.logger.log(self.state.value, "Starting result reflection")
        
        prompt = f"""
        Execution Result: {json.dumps(step_result, ensure_ascii=False)}
        
        Please analyze this result and return a reflection in JSON format:
        {{
            "achieved_goal": true/false,
            "problems": ["problem1", "problem2"],
            "improvements": ["improvement1", "improvement2"],
            "next_steps": ["step1", "step2"]
        }}
        """
        
        response = self._get_llm_response(prompt)
        reflection = extract_json_from_response(response)
        
        if "error" in reflection:
            self.logger.log(self.state.value, f"Reflection failed: {reflection['error']}", is_error=True)
            return {
                "achieved_goal": False,
                "problems": ["Failed to parse reflection format"],
                "improvements": ["Provide clearer format requirements"],
                "next_steps": ["Retry reflection"]
            }
        
        self.logger.log(self.state.value, f"Reflection completed: {json.dumps(reflection, ensure_ascii=False, indent=2)}")
        return reflection
    
    def plan_next_step(self, task: str, current_step: Dict[str, Any], current_result: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Plan next step based on current result"""
        prompt = f"""
        Task: {task}
        Current step: {json.dumps(current_step, ensure_ascii=False)}
        Current result: {json.dumps(current_result, ensure_ascii=False)}
        Context:
        - Variables: {json.dumps(context['variables'], ensure_ascii=False)}
        - Files: {json.dumps(context['files'], ensure_ascii=False)}
        
        Based on the current result and context, please plan the next step.
        Return a single step in JSON format:
        {{
            "tool": "tool_name",
            "parameters": {{"param_name": "param_value"}},
            "description": "step description",
            "success_criteria": ["criterion1", "criterion2"]
        }}
        
        If the task is complete, return null.
        
        Available tools:
        {self.tool_registry.get_tools_description()}
        """
        
        response = self._get_llm_response(prompt)
        next_step = extract_json_from_response(response)
        
        if "error" in next_step or not next_step:
            return None
        
        return next_step

    def adjust_failed_step(self, step: Dict[str, Any], error: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust a failed step considering previous attempts"""
        prompt = f"""
        Failed step: {json.dumps(step, ensure_ascii=False)}
        Error: {error}
        Context:
        - Variables: {json.dumps(context.get('variables', {}), ensure_ascii=False)}
        - Files: {json.dumps(context.get('files', {}), ensure_ascii=False)}
        
        Previously tried combinations:
        {chr(10).join([f"- Tool: {t}, Parameters: {p}" for t, p in self.tried_combinations])}
        
        Please analyze the error and suggest an alternative approach.
        Consider:
        1. Using a different command or tool that provides similar information
        2. Modifying parameters or options to handle potential issues
        3. Breaking down the step into smaller parts if needed
        4. Using more robust or reliable alternatives
        
        IMPORTANT: Do not suggest combinations that have already been tried!
        
        For process information tasks:
        1. If output shows only headers, add more rows: | head -2 or | head -3
        2. For memory info: try ps -eo pid,pmem,comm --sort=-pmem
        3. For process name: try ps -eo pid,comm --sort=-pmem
        4. For detailed memory: try ps -eo pid,rss,comm --sort=-rss
        
        Return the adjusted step in this EXACT format:
        {{
            "tool": "shell",
            "parameters": {{"command": "command here", "timeout": 30}},
            "description": "Clear description of what this step will do",
            "success_criteria": ["criterion1", "criterion2"]
        }}
        
        IMPORTANT:
        1. ALWAYS include all required fields: tool, parameters, description, success_criteria
        2. Description must be a clear, non-empty string
        3. Success criteria must be a non-empty list
        4. Parameters must include all required values for the tool
        5. DO NOT suggest combinations that have already been tried
        
        Available tools:
        {self.tool_registry.get_tools_description()}
        """
        
        response = self._get_llm_response(prompt)
        adjusted_step = extract_json_from_response(response)
        
        # Verify we haven't tried this combination before
        if self._has_tried_combination(adjusted_step.get("tool"), adjusted_step.get("parameters", {})):
            self.logger.log('ERROR', "Suggested step has already been tried, requesting another option", is_error=True)
            return self.adjust_failed_step(step, error + " (Previous suggestion was already tried)", context)
        
        return adjusted_step

    def execute_task(self, task: str) -> Dict[str, Any]:
        """Execute complete task using depth-first strategy"""
        self.logger.log('TASK', f"Starting: {task}")
        self.current_task = task
        self.thought_process = []
        
        # Store intermediate results
        self.task_context = {
            "results": [],
            "variables": {},
            "files": {},
            "summaries": []  # Store result summaries
        }
        
        results = []
        task_stack = [task]
        completed_tasks = set()
        final_analysis = None
        total_failures = 0  # Track total failures across all steps
        consecutive_failures = 0  # Track consecutive failures for current approach
        
        while task_stack:
            current_task = task_stack[-1]
            
            if current_task in completed_tasks:
                task_stack.pop()
                continue
            
            analysis = self.analyze_task(current_task)
            self.thought_process.append({"phase": "analysis", "content": analysis})
            
            if "error" in analysis:
                error_msg = f"Analysis failed: {analysis['error']}"
                self.logger.log('ERROR', error_msg)
                return {
                    "task": task,
                    "success": False,
                    "error": error_msg,
                    "details": analysis["error"]
                }
            
            # Log analysis results using new format
            self.logger.log('ANALYSIS', f"Goal: {analysis['analysis']['task_goal']}")
            self.logger.log('ANALYSIS', f"Current Info: {analysis['analysis']['current_info']}")
            self.logger.log('ANALYSIS', f"Missing Info: {analysis['analysis']['missing_info']}")
            
            if analysis["analysis"]["is_completed"]:
                # Verify we actually have valid results before concluding
                if not any(self.task_context["variables"].values()):
                    self.logger.log('ERROR', "Task marked as complete but no valid results found")
                    return {
                        "task": task,
                        "success": False,
                        "error": "No valid results",
                        "details": "Task was marked complete but no useful data was collected"
                    }
                
                completed_tasks.add(current_task)
                task_stack.pop()
                if len(task_stack) == 0:  # Main task completed
                    final_analysis = analysis
                continue
            
            if analysis["required_tasks"]:
                new_tasks = [task for task in reversed(analysis["required_tasks"]) 
                           if task not in completed_tasks]
                task_stack.extend(new_tasks)
                continue
            
            current_step = analysis["next_step"]
            max_retries = 3
            retry_count = 0
            success = False
            last_error = None
            
            # Log planned step
            self.logger.log('PLAN', f"Next step: {current_step['description']}")
            if current_step.get('success_criteria'):
                self.logger.log('PLAN', f"Success criteria: {', '.join(current_step['success_criteria'])}")
            
            while retry_count < max_retries and not success:
                result = self.execute_step(current_step)
                
                if "success" in result and result["success"]:
                    # Analyze tool result
                    self.logger.log('ANALYSIS', "Analyzing step result...")
                    result_analysis = self.analyze_tool_result(current_task, current_step, result)
                    
                    # Reset consecutive failures on valid data
                    if result_analysis.get("has_valid_data", False):
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                    
                    # Log analysis using new format
                    if result_analysis["can_conclude"]:
                        self.logger.log('ANALYSIS', f"Conclusion: {result_analysis['conclusion']}")
                        self.logger.log('ANALYSIS', f"Reason: {result_analysis['reason']}")
                    else:
                        self.logger.log('ANALYSIS', "Key information found:")
                        for info in result_analysis["key_info"]:
                            self.logger.log('ANALYSIS', f"- {info}")
                    
                    # Store result and analysis
                    if "result" in result:
                        if isinstance(result["result"], dict):
                            if "stdout" in result["result"] and result["result"]["stdout"].strip():
                                self.task_context["variables"][f"result_{len(results)}"] = result["result"]["stdout"].strip()
                            if "content" in result["result"] and result["result"]["content"].strip():
                                self.task_context["variables"][f"result_{len(results)}"] = result["result"]["content"]
                        else:
                            self.task_context["variables"][f"result_{len(results)}"] = str(result["result"])
                    
                    results.append(result)
                    
                    # Only mark as success if we got valid data or don't need retry
                    success = result_analysis.get("has_valid_data", False) or not result_analysis.get("needs_retry", True)
                    
                    # If we can conclude from this result, mark task as completed
                    if result_analysis["can_conclude"]:
                        completed_tasks.add(current_task)
                        task_stack.pop()
                        if len(task_stack) == 0:  # Main task completed
                            final_analysis = {
                                "analysis": {
                                    "is_completed": True,
                                    "task_goal": analysis["analysis"]["task_goal"],
                                    "current_info": result_analysis["conclusion"],
                                    "missing_info": "",
                                    "evidence": result_analysis["key_info"]
                                },
                                "next_step": None,
                                "required_tasks": [],
                                "is_final_step": True
                            }
                        
                        if not task_stack:
                            break
                else:
                    last_error = result.get("error", "Unknown error")
                    self.logger.log('RETRY', f"Failed: {last_error}, attempt {retry_count + 1}")
                    
                    # First try LLM's suggestion for improvement
                    improved_step = self.adjust_failed_step(current_step, last_error, self.task_context)
                    
                    # If the improved step is different from current and hasn't been tried
                    if (improved_step.get("tool") != current_step.get("tool") or 
                        improved_step.get("parameters") != current_step.get("parameters")):
                        current_step = improved_step
                    else:
                        # Only ask for user suggestion if LLM's suggestion isn't helpful
                        if consecutive_failures >= 2:
                            suggestion = self.get_user_suggestion()
                            if suggestion:
                                # Add suggestion to context
                                self.task_context["user_suggestion"] = suggestion
                                # Update current step with user suggestion
                                current_step = self.plan_next_step_with_suggestion(
                                    task, current_step, suggestion, self.task_context
                                )
                                # Reset retry count to give the new suggestion a chance
                                retry_count = 0
                                consecutive_failures = 0
                                continue
                    
                    retry_count += 1
                    total_failures += 1
                    consecutive_failures += 1
            
            if not success:
                # Before giving up, ask user for help
                self.logger.log('NOTICE', "Task execution encountered difficulties.")
                
                # Print current progress with highlights
                if self.task_context.get('summaries'):
                    self.logger.log('NOTICE', f"{Fore.GREEN}Information found so far:{Style.RESET_ALL}")
                    for info in self.task_context['summaries']:
                        self.logger.log('NOTICE', f"{Fore.CYAN}• {info}{Style.RESET_ALL}")
                
                if self.task_context.get('conclusions'):
                    self.logger.log('NOTICE', f"{Fore.GREEN}Conclusions drawn:{Style.RESET_ALL}")
                    for conclusion in self.task_context['conclusions']:
                        self.logger.log('NOTICE', f"{Fore.YELLOW}• {conclusion}{Style.RESET_ALL}")
                
                if self.task_context.get('variables'):
                    self.logger.log('NOTICE', f"{Fore.GREEN}Raw results:{Style.RESET_ALL}")
                    for var_name, value in self.task_context['variables'].items():
                        self.logger.log('NOTICE', f"{Fore.MAGENTA}• {var_name}: {value}{Style.RESET_ALL}")
                
                suggestion = self.get_user_suggestion()
                if suggestion:
                    # Add suggestion to context
                    self.task_context["user_suggestion"] = suggestion
                    
                    # Create a new analysis incorporating user's suggestion
                    retry_prompt = f"""
                    Task to retry: {task}
                    
                    Current progress:
                    {chr(10).join(self.task_context.get('summaries', []))}
                    
                    Previous attempts failed because:
                    - Total failures: {total_failures}
                    - Last error: {last_error}
                    
                    User provided new information/suggestion:
                    {suggestion}
                    
                    Please analyze how to proceed with this new information.
                    Consider:
                    1. How the user's suggestion helps with the task
                    2. What new approach we can try
                    3. What information we might have missed before
                    4. How to adjust our strategy
                    
                    Return your analysis in this JSON format:
                    {{
                        "analysis": {{
                            "is_completed": false,
                            "task_goal": "Updated understanding of what needs to be done",
                            "current_info": "What we know so far",
                            "missing_info": "What we still need to find",
                            "evidence": ["Facts we have 1", "Facts we have 2"]
                        }},
                        "next_step": {{
                            "tool": "tool_name",
                            "parameters": {{"param_name": "param_value"}},
                            "description": "What we'll try next",
                            "success_criteria": ["How we'll know it worked"]
                        }},
                        "required_tasks": [],
                        "is_final_step": false
                    }}
                    """
                    
                    response = self._get_llm_response(retry_prompt)
                    new_analysis = extract_json_from_response(response)
                    
                    if "error" not in new_analysis and self.validate_step_format(new_analysis):
                        self.logger.log('RETRY', "Retrying task with user's suggestion...")
                        # Reset failure counters
                        total_failures = 0
                        consecutive_failures = 0
                        # Try the new approach
                        if new_analysis.get("next_step"):
                            current_step = new_analysis["next_step"]
                            # Clear tried combinations to allow retrying with new context
                            self.tried_combinations.clear()
                            # Recursive call to continue execution with new approach
                            return self.execute_task(task)
    
        # Only return failure if user provided no suggestion or retry also failed
        success = (
            # 有��果且没有错误
            bool(results) and all("error" not in r for r in results) and 
            # 有变量或结论
            (bool(self.task_context["variables"]) or bool(self.task_context.get("conclusions"))) and
            # 如果有最终分析，检查是否完成
            (not final_analysis or final_analysis["analysis"]["is_completed"])
        )
        
        # 让LLM判断任务是否完成
        completion_prompt = f"""
        Task: {task}
        
        Final Result:
        {final_analysis["analysis"]["current_info"] if final_analysis else "No final analysis"}
        
        Evidence:
        {chr(10).join(f"- {e}" for e in final_analysis["analysis"]["evidence"]) if final_analysis and final_analysis["analysis"]["evidence"] else "No evidence"}
        
        Context:
        - Variables: {json.dumps(self.task_context.get("variables", {}), ensure_ascii=False)}
        - Conclusions: {json.dumps(self.task_context.get("conclusions", []), ensure_ascii=False)}
        - Summaries: {json.dumps(self.task_context.get("summaries", []), ensure_ascii=False)}
        
        Please analyze if this task is truly completed by considering:
        1. Was the original task goal achieved?
        2. Do we have all necessary information?
        3. Are the results clear and definitive?
        4. Is any important information missing?
        5. Are there any unresolved aspects?
        
        Return your analysis in this JSON format:
        {
            "is_completed": true/false,
            "completion_type": "full" | "partial" | "negative" | "failed",
            "reason": "Detailed explanation of why the task is considered completed or not",
            "missing_aspects": ["Any aspects that remain unaddressed"]
        }
        
        Important:
        - "full" means task completed successfully with positive result
        - "partial" means some aspects completed but not all
        - "negative" means task completed but with negative result
        - "failed" means task could not be completed
        - Be strict about completion - only mark as completed if ALL aspects are addressed
        """
        
        completion_response = self._get_llm_response(completion_prompt)
        completion_analysis = extract_json_from_response(completion_response)
        
        # 根据LLM的分析确定状态
        if completion_analysis.get("is_completed", False):
            completion_type = completion_analysis.get("completion_type", "full")
            if completion_type == "full":
                status = "completed"
            elif completion_type == "partial":
                status = "completed (partial success)"
            elif completion_type == "negative":
                status = "completed (negative result)"
            else:
                status = "failed"
        else:
            status = "failed"
        
        success = completion_analysis.get("is_completed", False)
        
        self.logger.log('DONE', f"Task {status}")
        if completion_analysis.get("reason"):
            self.logger.log('DONE', f"Reason: {completion_analysis['reason']}")
        if completion_analysis.get("missing_aspects"):
            self.logger.log('DONE', "Missing aspects:")
            for aspect in completion_analysis["missing_aspects"]:
                self.logger.log('DONE', f"- {aspect}")
        
        # Show final conclusion
        if final_analysis and final_analysis["analysis"]["is_completed"]:
            self.logger.log('CONCLUSION', f"Goal: {final_analysis['analysis']['task_goal']}")
            self.logger.log('CONCLUSION', f"Result: {final_analysis['analysis']['current_info']}")
            if final_analysis['analysis']['evidence']:
                self.logger.log('CONCLUSION', "Evidence:")
                for evidence in final_analysis['analysis']['evidence']:
                    self.logger.log('CONCLUSION', f"- {evidence}")
        
        return {
            "task": task,
            "success": success,
            "results": results,
            "thought_process": self.thought_process,
            "context": self.task_context,
            "final_analysis": final_analysis,
            "completion_analysis": completion_analysis
        }

    def plan_next_step_with_suggestion(self, task: str, current_step: Dict[str, Any], suggestion: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Plan next step considering user suggestion"""
        prompt = f"""
        Task: {task}
        Current step: {json.dumps(current_step, ensure_ascii=False)}
        User suggestion: {suggestion}
        
        Context:
        - Variables: {json.dumps(context['variables'], ensure_ascii=False)}
        - Files: {json.dumps(context['files'], ensure_ascii=False)}
        - Previous attempts failed
        
        Please plan a new step considering the user's suggestion.
        Return the step in JSON format:
        {{
            "tool": "tool_name",
            "parameters": {{"param_name": "param_value"}},
            "description": "step description",
            "success_criteria": ["criterion1", "criterion2"]
        }}
        
        Available tools:
        {self.tool_registry.get_tools_description()}
        """
        
        response = self._get_llm_response(prompt)
        next_step = extract_json_from_response(response)
        
        if "error" in next_step:
            return current_step
            
        return next_step