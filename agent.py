import ollama
from enum import Enum
import json
from typing import Dict, Any, Optional, List

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
    def __init__(self):
        self.model = "llama3:latest"
        self.state = AgentState.ANALYZING
        self.tool_registry = ToolRegistry()
        self.task_history = []
        self.current_task = None
        self.thought_process = []
        self.logger = ColorLogger()
    
    def register_tool(self, tool: Tool):
        """Register a new tool"""
        self.tool_registry.register(tool)
    
    def _get_llm_response(self, prompt: str) -> str:
        """Call Llama model to get response"""
        response = ollama.chat(model=self.model, messages=[
            {'role': 'user', 'content': prompt}
        ])
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
        return suggestion

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
        
        prompt = f"""
        Task to complete: {task}
        
        Available Tools:
        {self.tool_registry.get_tools_description()}
        
        Current Progress:
        {chr(10).join(completed_summary) if completed_summary else "No steps completed yet"}
        
        First, analyze if the task is already completed based on the current progress.
        You must provide a clear conclusion about whether ALL required information has been obtained.
        
        The conclusion must be specific and evidence-based:
        - State exactly what information was found
        - State exactly what information is missing
        - Include actual values and measurements
        - Reference specific outputs or errors
        - Never make assumptions without evidence
        
        Then, if the task is not completed, provide the next step that would help get the missing information.
        
        Return your response in this EXACT JSON format:
        {{
            "analysis": {{
                "is_completed": false,
                "conclusion": "Required information X is missing",
                "reason": "Only found A and B, but C is still needed",
                "evidence": [
                    "Found: A = value1",
                    "Found: B = value2",
                    "Missing: C"
                ]
            }},
            "next_step": {{
                "tool": "tool_name",
                "parameters": {{"param_name": "param_value"}},
                "description": "Get the missing information C",
                "success_criteria": ["C value obtained"]
            }},
            "required_tasks": [],
            "is_final_step": false
        }}
        
        Note:
        1. The conclusion must list ALL found information with exact values
        2. Evidence must list both found AND missing information
        3. Don't repeat steps that have already provided good results
        4. Set is_completed to true ONLY if ALL required information is present AND valid
        5. If more information is needed, explain exactly what is missing
        6. ALWAYS include required_tasks (empty list if none) and is_final_step fields
        7. Set is_final_step to true only if ALL required information is obtained AND valid
        8. Next step should focus on getting missing or invalid information
        """
        
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        if "error" in analysis or not self.validate_step_format(analysis):
            return self.retry_task_analysis(task, response)
        
        return analysis

    def validate_step_format(self, analysis: Dict[str, Any]) -> bool:
        """Validate single step analysis format"""
        try:
            # Check analysis section
            if not isinstance(analysis.get("analysis"), dict):
                return False
            
            analysis_dict = analysis["analysis"]
            if not isinstance(analysis_dict.get("is_completed"), bool):
                return False
            if not isinstance(analysis_dict.get("conclusion"), str):
                return False
            if not isinstance(analysis_dict.get("reason"), str):
                return False
            if not isinstance(analysis_dict.get("evidence"), list):
                return False
            
            # Check next_step section if task is not completed
            if not analysis_dict["is_completed"]:
                next_step = analysis.get("next_step")
                if not isinstance(next_step, dict):
                    return False
                # Check all required fields are present
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
        # Ensure result has the expected structure
        if not isinstance(result, dict):
            result = {
                "success": False,
                "error": "Invalid result format",
                "result": {
                    "stdout": "",
                    "stderr": "Result was not in expected format",
                    "returncode": -1
                }
            }
        
        # Ensure result has a 'result' dict with required fields
        if "result" not in result:
            result["result"] = {}
        
        result_data = result["result"]
        if not isinstance(result_data, dict):
            result_data = {
                "stdout": str(result_data) if result_data else "",
                "stderr": "",
                "returncode": 0 if result.get("success", False) else 1
            }
            result["result"] = result_data
        
        # Ensure all required fields exist
        if "stdout" not in result_data:
            result_data["stdout"] = ""
        if "stderr" not in result_data:
            result_data["stderr"] = ""
        if "returncode" not in result_data:
            result_data["returncode"] = 0 if result.get("success", False) else 1
        
        prompt = f"""
        Task: {task}
        
        Step executed:
        - Tool: {step['tool']}
        - Description: {step['description']}
        - Success criteria: {', '.join(step['success_criteria'])}
        
        Result:
        {json.dumps(result, ensure_ascii=False, indent=2)}
        
        Please analyze this result carefully and thoroughly:
        1. For empty or error results, NEVER conclude the task is complete
        2. For any task, require ALL requested information to be present before concluding
        3. Check that the output contains EVERY piece of information mentioned in the task
        4. Verify the format and content of EACH required piece of information
        5. If ANY required information is missing or invalid, set has_valid_data=false
        
        Special validation rules:
        1. For command outputs:
           - Return code 0 doesn't always mean success
           - Must check actual output content
           - Must verify each piece of required data
           - Headers or empty results are not valid data
        2. For data validation:
           - Values must be in correct format
           - Numbers must be actual values, not labels
           - Names must be actual values, not placeholders
           - Empty or error responses are not valid data
        
        Return your analysis in this JSON format:
        {{
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
            "reason": "Detailed explanation of why we can/cannot conclude, listing ALL missing information if any",
            "has_valid_data": true/false,
            "needs_retry": true/false,
            "validation_errors": [
                "List any validation errors found (e.g. invalid format, missing data)"
            ]
        }}
        
        Rules:
        1. Set has_valid_data=false if:
           - Result is empty
           - Result contains only headers
           - Result contains errors
           - ANY required information is missing
           - Format of ANY information is incorrect
           - ANY check failed
        2. Set needs_retry=true if:
           - Current approach failed but a different approach might work
           - We got partial information but need more
           - Command needs modification to get missing information
           - ANY check needs retrying
        3. Set can_conclude=true ONLY if:
           - We have ALL required information
           - ALL information is in correct format
           - NO required information is missing
           - ALL checks passed
        4. key_info must list EVERY piece of information found, with its exact value
        5. missing_info must list EVERY piece of required information not found
        6. The conclusion must include ALL found information with exact values
        7. validation_errors must list any issues with data format or content
        """
        
        response = self._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        if "error" in analysis:
            return {
                "can_conclude": False,
                "conclusion": None,
                "key_info": [],
                "missing_info": ["Failed to analyze result"],
                "reason": "Failed to analyze result",
                "has_valid_data": False,
                "needs_retry": True,
                "validation_errors": ["Analysis failed"]
            }
        
        # Force can_conclude to False if any validation issues
        if analysis.get("missing_info", []) or analysis.get("validation_errors", []):
            analysis["can_conclude"] = False
            analysis["has_valid_data"] = False
            reasons = []
            if analysis.get("missing_info"):
                reasons.append(f"Missing information: {', '.join(analysis['missing_info'])}")
            if analysis.get("validation_errors"):
                reasons.append(f"Validation errors: {', '.join(analysis['validation_errors'])}")
            if not analysis.get("reason"):
                analysis["reason"] = " AND ".join(reasons)
        
        # Special check for header-only output
        stdout = result_data.get("stdout", "").strip()
        if stdout and all(word.isupper() or word.startswith('%') for word in stdout.split()):
            analysis["has_valid_data"] = False
            analysis["needs_retry"] = True
            analysis["validation_errors"] = analysis.get("validation_errors", []) + ["Output contains only headers"]
            analysis["reason"] = "Output contains only column headers without actual data"
        
        return analysis

    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step"""
        self.state = AgentState.EXECUTING
        tool_name = step.get("tool")
        
        # Log step details
        self.logger.log('STEP', f"Executing: {step['description']}")
        self.logger.log('STEP', f"Tool: {tool_name}")
        self.logger.log('STEP', f"Parameters: {json.dumps(step.get('parameters', {}), ensure_ascii=False)}")
        
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            error_msg = f"Tool not found: {tool_name}"
            self.logger.log('ERROR', error_msg, is_error=True)
            return {"error": error_msg}
            
        try:
            result = tool.execute(**step.get("parameters", {}))
            
            # Only consider it a failure if tool execution itself failed
            if isinstance(result, dict) and not result.get("success", False):
                return {
                    "error": result.get("error", "Execution failed"),
                    "details": result
                }
            
            # Log the result
            if isinstance(result, dict) and "result" in result:
                result_data = result["result"]
                if "stdout" in result_data:
                    self.logger.log('RESULT', f"Output: {result_data['stdout'].strip()}")
                if "stderr" in result_data and result_data["stderr"].strip():
                    self.logger.log('RESULT', f"Stderr: {result_data['stderr'].strip()}")
                if "returncode" in result_data and result_data["returncode"] != 0:
                    self.logger.log('RESULT', f"Return code: {result_data['returncode']}")
                if "command" in result_data:
                    self.logger.log('RESULT', f"Command: {result_data['command']}")
            else:
                self.logger.log('RESULT', f"Result: {result}")
            
            return {"success": True, "result": result}
            
        except Exception as e:
            error_msg = str(e)
            self.logger.log('ERROR', f"Failed: {error_msg}", is_error=True)
            return {"error": error_msg}
    
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

    def adjust_failed_step(self, failed_step: Dict[str, Any], error: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust failed step based on error"""
        prompt = f"""
        Failed step: {json.dumps(failed_step, ensure_ascii=False)}
        Error: {error}
        Context:
        - Variables: {json.dumps(context['variables'], ensure_ascii=False)}
        - Files: {json.dumps(context['files'], ensure_ascii=False)}
        
        Please analyze the error and suggest an alternative approach.
        Consider:
        1. Using a different command or tool that provides similar information
        2. Modifying parameters or options to handle potential issues
        3. Breaking down the step into smaller parts if needed
        4. Using more robust or reliable alternatives
        
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
        
        Available tools:
        {self.tool_registry.get_tools_description()}
        """
        
        response = self._get_llm_response(prompt)
        adjusted_step = extract_json_from_response(response)
        
        if "error" in adjusted_step:
            # If adjustment fails, ensure the original step has required fields
            if "description" not in failed_step:
                failed_step["description"] = "Retry previous step"
            if "success_criteria" not in failed_step:
                failed_step["success_criteria"] = ["successful execution"]
            return failed_step
        
        # Validate adjusted step has all required fields
        required_fields = ["tool", "parameters", "description", "success_criteria"]
        for field in required_fields:
            if field not in adjusted_step:
                adjusted_step[field] = failed_step.get(field, {
                    "tool": "shell",
                    "parameters": {"command": "ls", "timeout": 30},
                    "description": "Retry previous step",
                    "success_criteria": ["successful execution"]
                }[field])
        
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
            
            # Log analysis results
            self.logger.log('ANALYSIS', f"Status: {analysis['analysis']['conclusion']}")
            self.logger.log('ANALYSIS', f"Reason: {analysis['analysis']['reason']}")
            
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
                    
                    # Log analysis
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
                    
                    # Store key information for next steps
                    if result_analysis["key_info"]:
                        self.task_context["summaries"].extend(result_analysis["key_info"])
                    
                    if current_step["tool"] in ["write_file", "read_file"]:
                        filename = current_step["parameters"]["filename"]
                        self.task_context["files"][filename] = {
                            "last_operation": current_step["tool"],
                            "last_content": self.task_context["variables"].get(f"result_{len(results)}")
                        }
                    
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
                                    "conclusion": result_analysis["conclusion"],
                                    "reason": result_analysis["reason"],
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
                    current_step = self.adjust_failed_step(current_step, last_error, self.task_context)
                    retry_count += 1
                    total_failures += 1
                    consecutive_failures += 1
                    
                    # Ask for user suggestion after multiple consecutive failures
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
            
            if not success:
                self.logger.log('ERROR', f"Failed after {max_retries} attempts")
                return {
                    "task": task,
                    "success": False,
                    "error": "Maximum retry count reached",
                    "details": last_error
                }
            
            if not analysis["is_final_step"]:
                continue
        
        success = all("error" not in r for r in results) and bool(self.task_context["variables"])
        self.logger.log('DONE', f"Task {'completed' if success else 'failed'}")
        
        # Show final conclusion
        if final_analysis and final_analysis["analysis"]["is_completed"]:
            self.logger.log('CONCLUSION', f"Final conclusion: {final_analysis['analysis']['conclusion']}")
            self.logger.log('CONCLUSION', f"Reason: {final_analysis['analysis']['reason']}")
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
            "final_analysis": final_analysis
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