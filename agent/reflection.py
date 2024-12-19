from typing import Dict, Any, Optional
import json
from colorama import Fore, Style
from utils import extract_json_from_response
from .base import AgentState  # 导入AgentState

class TaskReflector:
    """Task reflection and retry functionality"""
    
    def retry_task_analysis(self, task: str, previous_response: str, retry_count: int = 0, agent=None) -> Dict[str, Any]:
        """Retry task analysis with reflection and improvements"""
        agent.logger.log('RETRY', f"Retry {retry_count + 1} for task analysis")
        
        if retry_count >= 3:
            # After multiple retries, try to understand why we're failing
            reflection_parts = [
                f"Task: {task}",
                "Previous attempts failed. Let's reflect on why and try a different approach.",
                "",
                "Previous response:",
                previous_response,
                "",
                "Issues to consider:",
                "1. Is the task clear and specific enough?",
                "2. Are we asking the right question?",
                "3. Do we need to break this down differently?",
                "4. Are we missing any context?",
                "",
                "Please help me:",
                "1. Identify why previous attempts failed",
                "2. Suggest a better way to approach this task",
                "3. Provide a properly formatted response",
                "",
                "Format your response as JSON:",
                "{"
                '    "analysis": {'
                '        "failure_reason": "Why previous attempts failed",'
                '        "suggested_approach": "How to better approach this",'
                '        "task_goal": "Clearer statement of what needs to be done",'
                '        "current_info": "What we know",'
                '        "missing_info": "What we need",'
                '        "evidence": ["Available facts"]'
                "    },"
                '    "next_step": {'
                '        "tool": "tool_name",'
                '        "parameters": {"param1": "value1"},'
                '        "description": "What this step will do",'
                '        "success_criteria": ["How we know it worked"]'
                "    },"
                '    "required_tasks": []'
                "}"
            ]
            
            reflection_prompt = "\n".join(reflection_parts)
            response = agent._get_llm_response(reflection_prompt)
            analysis = extract_json_from_response(response)
            
            if "error" not in analysis and agent.validate_step_format(analysis):
                # If reflection helped us get a valid response, use it
                if agent.verbose and "analysis" in analysis:
                    agent.logger.log('REFLECTION', f"Failure reason: {analysis['analysis'].get('failure_reason', 'Unknown')}")
                    agent.logger.log('REFLECTION', f"New approach: {analysis['analysis'].get('suggested_approach', 'Not specified')}")
                return analysis
                
            # If still failing after reflection, ask user for help
            suggestion = agent.get_user_suggestion()
            if suggestion:
                # Build prompt with user's suggestion
                suggestion_parts = [
                    f"Task: {task}",
                    "",
                    f"User suggestion: {suggestion}",
                    "",
                    "Previous attempts failed, but the user provided new information.",
                    "Please use this suggestion to formulate a new approach.",
                    "",
                    "Format your response as JSON:",
                    "{"
                    '    "analysis": {'
                    '        "task_goal": "What needs to be done",'
                    '        "current_info": "What we know",'
                    '        "missing_info": "What we need",'
                    '        "evidence": ["Available facts"]'
                    "    },"
                    '    "next_step": {'
                    '        "tool": "tool_name",'
                    '        "parameters": {"param1": "value1"},'
                    '        "description": "What this step will do",'
                    '        "success_criteria": ["How we know it worked"]'
                    "    },"
                    '    "required_tasks": []'
                    "}"
                ]
                
                suggestion_prompt = "\n".join(suggestion_parts)
                response = agent._get_llm_response(suggestion_prompt)
                analysis = extract_json_from_response(response)
                
                if "error" not in analysis and agent.validate_step_format(analysis):
                    return analysis
        
        # For earlier retries, try simpler approach
        simple_parts = [
            f"Task: {task}",
            "",
            "Previous response was invalid. Please provide a properly formatted response.",
            "",
            "Available tools:",
            agent.tool_registry.get_tools_description(),
            "",
            "Example of task analysis format:",
            '''{
    "analysis": {
        "task_goal": "Get the IP address of the machine",
        "current_info": "No IP information available yet",
        "missing_info": "Machine's IP address",
        "evidence": []
    },
    "next_step": {
        "tool": "shell",
        "parameters": {"command": "hostname -I"},
        "description": "Get the machine's IP address",
        "success_criteria": ["Command returns an IP address"]
    },
    "required_tasks": []
}''',
            "",
            "Note: next_step can be null if no further steps are needed",
            "",
            "Please provide your response in this exact format:",
            "{"
            '    "analysis": {'
            '        "task_goal": "What needs to be done",'
            '        "current_info": "What we know",'
            '        "missing_info": "What we need",'
            '        "evidence": ["Available facts"]'
            "    },"
            '    "next_step": {'
            '        "tool": "tool_name",'
            '        "parameters": {"param1": "value1"},'
            '        "description": "What this step will do",'
            '        "success_criteria": ["How we know it worked"]'
            "    },"
            '    "required_tasks": []'
            "}"
        ]
        
        simple_prompt = "\n".join(simple_parts)
        response = agent._get_llm_response(simple_prompt)
        analysis = extract_json_from_response(response)
        
        if "error" in analysis or not agent.validate_step_format(analysis):
            return self.retry_task_analysis(task, response, retry_count + 1, agent)
        
        return analysis
    
    def adjust_failed_step(self, step: Dict[str, Any], error: str, context: Dict[str, Any], reflection: Dict[str, Any], agent=None) -> Dict[str, Any]:
        """Adjust a failed step based on reflection"""
        # 获取历史执行记录
        history = []
        for attempt in context.get('attempts', []):
            history.append({
                'step': attempt.get('step', {}),
                'result': attempt.get('result', {}),
                'error': attempt.get('error', ''),
                'timestamp': attempt.get('timestamp', '')
            })
        
        # 构建提示
        prompt_parts = [
            "Previous step failed. Please adjust it based on the following information:",
            "",
            f"Step: {json.dumps(step, ensure_ascii=False)}",
            f"Error: {error}",
            "",
            "Context:",
            f"- Variables: {json.dumps(context.get('variables', {}), ensure_ascii=False)}",
            f"- Files: {json.dumps(context.get('files', {}), ensure_ascii=False)}",
            "",
            "Reflection:",
            f"- Root cause: {reflection.get('root_cause', 'Unknown')}",
            f"- Suggested fix: {reflection.get('suggested_fix', 'None')}",
            "",
            "Previous attempts and their results:",
        ]
        
        # 添加历史执行记录
        for i, attempt in enumerate(history, 1):
            prompt_parts.extend([
                f"\nAttempt {i}:",
                f"Tool: {attempt['step'].get('tool')}",
                f"Parameters: {json.dumps(attempt['step'].get('parameters', {}), ensure_ascii=False)}",
                f"Result: {'Success' if attempt['result'].get('success') else 'Failed'}",
                f"Error: {attempt['error']}",
                "Output:",
                f"stdout: {attempt['result'].get('result', {}).get('stdout', '')}",
                f"stderr: {attempt['result'].get('result', {}).get('stderr', '')}"
            ])
        
        prompt_parts.extend([
            "",
            "CRITICAL RULES:",
            "1. DO NOT repeat exactly the same command that failed before",
            "2. Learn from previous errors and avoid similar mistakes",
            "3. If a command syntax failed, try a different approach",
            "4. Consider using different tools if previous attempts consistently fail",
            "",
            "Please provide an adjusted step that addresses these issues.",
            "",
            "Format your response as JSON:",
            "{",
            '    "adjusted_step": {',
            '        "tool": "tool_name",',
            '        "parameters": {"param1": "value1"},',
            '        "description": "What this step will do",',
            '        "success_criteria": ["How we know it worked"]',
            '    }',
            "}"
        ])
        
        prompt = "\n".join(prompt_parts)
        response = agent._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        return analysis.get("adjusted_step", step)
    
    def check_task_completion(self, task: str, context: Dict[str, Any], agent=None) -> Dict[str, Any]:
        """Check if task is completed based on current context"""
        # 获取历史��记录
        history = []
        for attempt in context.get('attempts', []):
            history.append({
                'step': attempt.get('step', {}),
                'result': attempt.get('result', {}),
                'error': attempt.get('error', ''),
                'timestamp': attempt.get('timestamp', '')
            })
        
        completion_parts = [
            f"Task: {task}",
            "",
            "Current context:",
            f"Variables: {json.dumps(context.get('variables', {}), ensure_ascii=False)}",
            f"Summaries: {json.dumps(context.get('summaries', []), ensure_ascii=False)}",
            f"Conclusions: {json.dumps(context.get('conclusions', []), ensure_ascii=False)}",
            "",
            "Execution History:",
        ]
        
        # 添加历史执行记录
        for i, attempt in enumerate(history, 1):
            completion_parts.extend([
                f"\nAttempt {i}:",
                f"Tool: {attempt['step'].get('tool')}",
                f"Command: {attempt['step'].get('parameters', {}).get('command', 'N/A')}",
                f"Result: {'Success' if attempt['result'].get('success') else 'Failed'}",
                "Output:",
                f"stdout: {attempt['result'].get('result', {}).get('stdout', '')}",
                f"stderr: {attempt['result'].get('result', {}).get('stderr', '')}",
                f"returncode: {attempt['result'].get('result', {}).get('returncode', '')}"
            ])
        
        completion_parts.extend([
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
            "5. Have we tried appropriate alternatives when previous attempts failed?",
            "",
            "CRITICAL RULES:",
            "1. NEVER make up or assume results that are not in the actual command output",
            "2. If there is no command output, the task CANNOT be complete",
            "3. If the last command failed or had errors, the task CANNOT be complete",
            "4. You MUST quote the exact command output when reporting results",
            "5. You MUST set is_completed=false if you cannot find a specific number in the output",
            "6. NEVER generate fake numbers or results",
            "7. Learn from previous failed attempts",
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
        ])
        
        completion_prompt = "\n".join(completion_parts)
        response = agent._get_llm_response(completion_prompt)
        completion_status = extract_json_from_response(response)
        
        # 验证完成状态
        if completion_status.get("is_completed", False):
            # 检查是否有实际的命令输出
            if not context.get("last_output", {}).get("stdout"):
                # 如果没有实际输出但声��完成了，强制修正状态
                completion_status.update({
                    "is_completed": False,
                    "status": "failed",
                    "reason": "No actual command output available",
                    "evidence": ["Task cannot be complete without actual command output"]
                })
        
        return completion_status
    
    def reflect_on_failure(self, task: str, current_step: Dict[str, Any], result: Dict[str, Any], result_analysis: Optional[Dict[str, Any]], agent=None) -> Dict[str, Any]:
        """Reflect on failure and suggest improvements"""
        # 确保所有参数都有有效默认值
        if current_step is None:
            current_step = {}
        
        if result is None:
            result = {
                "success": False,
                "error": "No result available",
                "result": {
                    "returncode": "N/A",
                    "stdout": "",
                    "stderr": "No output available"
                }
            }
        
        # 确保result是字典类型
        if not isinstance(result, dict):
            result = {
                "success": False,
                "error": str(result),
                "result": {
                    "returncode": "N/A",
                    "stdout": "",
                    "stderr": str(result)
                }
            }
        
        # 获取错误信息和返回码
        error_msg = result.get("error", "Unknown error")
        result_dict = result.get("result", {})
        if not isinstance(result_dict, dict):
            result_dict = {
                "returncode": "N/A",
                "stdout": "",
                "stderr": str(result_dict)
            }
        
        return_code = result_dict.get("returncode", "N/A")
        stderr = result_dict.get("stderr", "")
        
        # 构建提示
        prompt_parts = [
            f"Task: {task}",
            "",
            "Current step that failed:",
            f"Tool: {current_step.get('tool', 'unknown')}",
            f"Parameters: {json.dumps(current_step.get('parameters', {}), ensure_ascii=False)}",
            f"Description: {current_step.get('description', 'No description')}",
            "",
            "Error details:",
            "------------",
            f"Return code: {return_code}",
            "",
            "Error message:",
            error_msg,
            "------------",
            "",
            "Please analyze this failure and suggest improvements.",
            "Consider:",
            "1. What specific part of the command failed?",
            "2. What assumptions were incorrect?",
            "3. What alternative approaches might work better?",
            "4. Are there any syntax or parameter issues?",
            "5. Would a different tool be more appropriate?",
            "",
            "IMPORTANT: Make sure to include the 'command' parameter in shell tool steps.",
            "",
            "Format your response as JSON:",
            "{",
            "    \"failure_analysis\": {",
            "        \"error_type\": \"Specific type of error\",",
            "        \"failure_reason\": \"Clear explanation of what went wrong\",",
            "        \"problematic_components\": [\"Specific parts that failed\"]",
            "    },",
            "    \"suggested_fixes\": {",
            "        \"command_corrections\": [\"How to fix command syntax\"],",
            "        \"parameter_adjustments\": [\"How to adjust parameters\"],",
            "        \"alternative_approaches\": [\"Other ways to achieve the goal\"]",
            "    },",
            "    \"improved_step\": {",
            "        \"tool\": \"shell\",",
            "        \"parameters\": {\"command\": \"actual command here\"},",
            "        \"description\": \"What this improved step will do\",",
            "        \"success_criteria\": [\"How we know it worked\"]",
            "    }",
            "}"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = agent._get_llm_response(prompt)
        reflection = extract_json_from_response(response)
        
        # 确保返回的反思结果包含改进的步骤
        if "improved_step" in reflection:
            return reflection["improved_step"]  # ��接返回改进的步骤
        
        # 如果没有改进的步骤返回基本的反思结果
        return {
            "failure_analysis": reflection.get("failure_analysis", {}),
            "suggested_fixes": reflection.get("suggested_fixes", {}),
            "improved_step": current_step  # 使用当前步骤作为后备
        }
    
    def analyze_task_with_reflection(self, task: str, reflection: Dict[str, Any], agent) -> Dict[str, Any]:
        """Analyze task incorporating reflection insights"""
        prompt_parts = [
            f"Task: {task}",
            "",
            "Previous attempt failed:",
            "Failure analysis:",
            f"Error type: {reflection.get('failure_analysis', {}).get('error_type', 'Unknown')}",
            f"Failure reason: {reflection.get('failure_analysis', {}).get('failure_reason', 'Unknown')}",
            "",
            "Previous attempt details:",
        ]
        
        # 添加之前尝试的详细信息
        if "previous_attempt" in reflection:
            prev = reflection["previous_attempt"]
            prompt_parts.extend([
                f"Tool used: {prev.get('tool')}",
                f"Command: {prev.get('command')}",
                f"Result: {json.dumps(prev.get('result', {}), ensure_ascii=False)}",
                f"Error: {prev.get('error')}",
                "",
                # 添加详细的错误信息
                "Error details:",
                f"Return code: {prev.get('result', {}).get('returncode', 'N/A')}",
                f"stdout: {prev.get('result', {}).get('stdout', '')}",
                f"stderr: {prev.get('result', {}).get('stderr', '')}",
                "",
                "CRITICAL WARNINGS:",
                "1. This exact command or approach failed previously",
                "2. You MUST provide a different solution",
                "3. If syntax error occurred, consider different parameters",
                "4. If tool failed, consider alternative tools",
                "",
                "IMPORTANT: You MUST suggest a different approach or command.",
            ])
        
        prompt_parts.extend([
            "Command issues:",
            *[f"- {issue}" for issue in reflection.get('failure_analysis', {}).get('command_issues', [])],
            "",
            "Suggested fixes:",
            *[f"- {fix}" for fix in reflection.get('suggested_fixes', {}).get('command_corrections', [])],
            *[f"- {adj}" for adj in reflection.get('suggested_fixes', {}).get('parameter_adjustments', [])],
            *[f"- {alt}" for alt in reflection.get('suggested_fixes', {}).get('alternative_approaches', [])],
            "",
            "Available tools:",
            agent.tool_registry.get_tools_description(),
            "",
            "Please analyze the task again and provide a NEW approach that hasn't been tried before.",
            "CRITICAL: DO NOT suggest the same command that was previously attempted.",
            "",
            "Format your response as JSON:",
            "{",
            '    "analysis": {',
            '        "task_goal": "What needs to be done",',
            '        "current_info": "What we know",',
            '        "missing_info": "What we need",',
            '        "evidence": ["Available facts"]',
            "    },",
            '    "next_step": {',
            '        "tool": "tool_name",',
            '        "parameters": {"command": "command_string"},',
            '        "description": "What this step will do",',
            '        "success_criteria": ["How we know it worked"]',
            "    },",
            '    "required_tasks": []',
            "}"
        ])
        
        prompt = "\n".join(prompt_parts)
        response = agent._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        # 验证和修复返回的JSON格式
        if "next_step" in analysis and "arguments" in analysis["next_step"]:
            # 如果LLM仍然使用了arguments，自动修复为parameters
            analysis["next_step"]["parameters"] = analysis["next_step"].pop("arguments")
        
        return analysis 