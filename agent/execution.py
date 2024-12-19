from typing import Dict, Any, List, Optional
import json
from utils import extract_json_from_response
from .base import AgentState  # 导入AgentState
from colorama import Fore, Style

class TaskExecutor:
    """Task execution functionality"""
    
    def execute_task(self, task: str, agent) -> Dict[str, Any]:
        """Execute a task and return results"""
        # 打印任务开始信息
        agent.logger.log('TASK', f"{Fore.MAGENTA}╭──────────── 🎯 Task Started ────────────╮{Style.RESET_ALL}", prefix=False)
        agent.logger.log('TASK', f"{Fore.MAGENTA}│ Task: {task}{Style.RESET_ALL}", prefix=False)
        agent.logger.log('TASK', f"{Fore.MAGENTA}╰──────────────────────────────────────────╯{Style.RESET_ALL}\n", prefix=False)
        
        # Initialize task context if needed
        if not hasattr(agent, 'task_context'):
            agent.task_context = {
                "variables": {},
                "files": {},
                "summaries": [],
                "conclusions": [],
                "attempts": []  # 用于存储所有尝试
            }
        
        # Ensure all required fields exist in task_context
        default_context = {
            "variables": {},
            "files": {},
            "summaries": [],
            "conclusions": [],
            "attempts": []
        }
        
        for key, value in default_context.items():
            if key not in agent.task_context:
                agent.task_context[key] = value
        
        # Analyze task
        analysis = agent.analyze_task(task)
        if "error" in analysis:
            agent.logger.log('ERROR', f"Analysis failed: {analysis['error']}", is_error=True)
            return analysis
        
        # Execute steps
        results = []
        success = False
        total_failures = 0
        consecutive_failures = 0
        retry_count = 0
        final_analysis = None
        last_output = None
        
        while not success and total_failures < 5:
            # 打印当前执行阶段
            agent.logger.log('EXECUTE', f"{Fore.CYAN}╭──────────── 🔄 Execution Phase {len(results) + 1} ────────────╮{Style.RESET_ALL}", prefix=False)
            
            # Get current step
            current_step = analysis.get("next_step")
            if not current_step:
                agent.logger.log('ERROR', f"{Fore.RED}│ No next step available. Stopping execution.{Style.RESET_ALL}", prefix=False)
                break
            
            # 打印步骤详情
            agent.logger.log('EXECUTE', f"{Fore.CYAN}│ Tool:{Style.RESET_ALL} {current_step.get('tool')}", prefix=False)
            agent.logger.log('EXECUTE', f"{Fore.CYAN}│ Description:{Style.RESET_ALL} {current_step.get('description', 'No description')}", prefix=False)
            agent.logger.log('EXECUTE', f"{Fore.CYAN}│ Parameters:{Style.RESET_ALL}", prefix=False)
            for param, value in current_step.get("parameters", {}).items():
                agent.logger.log('EXECUTE', f"{Fore.CYAN}│   • {param}:{Style.RESET_ALL} {value}", prefix=False)
            
            # 打印成功标准
            agent.logger.log('EXECUTE', f"{Fore.CYAN}│ Success Criteria:{Style.RESET_ALL}", prefix=False)
            for criterion in current_step.get("success_criteria", []):
                agent.logger.log('EXECUTE', f"{Fore.CYAN}│   ✓ {criterion}{Style.RESET_ALL}", prefix=False)
            
            # 检查是否重复执行
            command = current_step.get("parameters", {}).get("command")
            if command:
                previous_attempts = [a for a in agent.task_context["attempts"] 
                                   if a["step"].get("parameters", {}).get("command") == command]
                if previous_attempts:
                    agent.logger.log('RETRY', f"{Fore.YELLOW}│ ⚠ This command was previously attempted{Style.RESET_ALL}", prefix=False)
                    agent.logger.log('RETRY', f"{Fore.YELLOW}│ Getting new analysis with previous attempt info...{Style.RESET_ALL}", prefix=False)
                    agent.logger.log('EXECUTE', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}\n", prefix=False)
                    
                    # 构建包含历史尝试信息的反思
                    previous_attempt = previous_attempts[0]  # 获取第一次尝试的信息
                    reflection = {
                        "failure_analysis": {
                            "error_type": "Duplicate Command",
                            "failure_reason": f"Command '{command}' was previously attempted",
                            "problematic_components": ["Repeated command execution"]
                        },
                        "suggested_fixes": {
                            "command_corrections": [],
                            "parameter_adjustments": ["Need to use different command or parameters"],
                            "alternative_approaches": ["Consider using different tool or approach"]
                        },
                        "previous_attempt": {
                            "timestamp": previous_attempt.get("timestamp", ""),
                            "result": previous_attempt.get("result", {}),
                            "error": previous_attempt.get("error", ""),
                            "tool": previous_attempt["step"].get("tool", ""),
                            "command": command
                        },
                        "improved_step": {
                            "tool": "shell",  # 这里会被LLM替换
                            "parameters": {"command": ""},  # 这里会被LLM替换
                            "description": "Need new approach to avoid duplicate command",
                            "success_criteria": ["Command executes successfully", "Produces expected output"]
                        }
                    }
                    
                    # 获取新的分析结果，包含历史信息
                    analysis = agent.analyze_task_with_reflection(task, reflection)
                    continue  # 跳过当前执行，使用新的分析结果
            
            # 记录这次尝试
            attempt = {
                'step': current_step,
                'result': None,
                'error': None,
                'timestamp': agent.get_timestamp()
            }
            
            # 执行步骤
            agent.logger.log('EXECUTE', f"{Fore.CYAN}│ Executing...{Style.RESET_ALL}", prefix=False)
            agent.logger.log('EXECUTE', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}\n", prefix=False)
            
            result = agent.execute_step(current_step)
            
            # 更新尝试记录
            attempt['result'] = result
            attempt['error'] = result.get('error')
            agent.task_context["attempts"].append(attempt)
            
            results.append(result)
            
            if not result.get("success", False):
                last_error = result.get("error", "Unknown error")
                agent.logger.log('RETRY', f"Failed: {last_error}, attempt {retry_count + 1}")
                
                # Reflect on failure
                reflection = agent.reflect_on_failure(task, current_step, result, None)
                agent.logger.log('REFLECTION', f"Failure reason: {reflection.get('failure_reason', 'Unknown')}")
                agent.logger.log('REFLECTION', f"Suggested approach: {reflection.get('suggested_approach', 'Not specified')}")
                
                # 获取新的分析结果
                analysis = agent.analyze_task_with_reflection(task, reflection)
                retry_count += 1
                total_failures += 1
                consecutive_failures += 1
                continue  # 直接进入下一次循环，使用新的分析结果
            
            # 保存最后的输出
            if result.get("success"):
                last_output = result.get("result", {})
                agent.task_context["last_output"] = last_output
            
            if result.get("success", False):
                # Analyze result
                result_analysis = agent.analyze_tool_result(task, current_step, result)
                
                if "error" not in result_analysis:
                    if result_analysis.get("has_valid_data", False):
                        consecutive_failures = 0
                        retry_count = 0
                        
                        # Store any extracted information
                        if result_analysis.get("key_info"):
                            agent.task_context["summaries"].extend(result_analysis["key_info"])
                        
                        # If we can conclude from this result, mark task as completed
                        if result_analysis.get("can_conclude"):
                            final_analysis = {
                                "analysis": {
                                    "task_goal": analysis["analysis"]["task_goal"],
                                    "current_info": result_analysis["conclusion"],
                                    "missing_info": "",
                                    "evidence": result_analysis["key_info"]
                                },
                                "next_step": None,
                                "required_tasks": []
                            }
                            success = True
                            break
                        
                        # If we need to retry, analyze failure and get new approach
                        if result_analysis.get("needs_retry"):
                            agent.logger.log('RETRY', "Result indicates need for retry, analyzing failure...")
                            reflection = agent.reflect_on_failure(task, current_step, result, result_analysis)
                            agent.logger.log('REFLECTION', f"Failure reason: {reflection.get('failure_reason', 'Unknown')}")
                            agent.logger.log('REFLECTION', f"Suggested approach: {reflection.get('suggested_approach', 'Not specified')}")
                            analysis = agent.analyze_task_with_reflection(task, reflection)
                            continue
                    else:
                        consecutive_failures += 1
                else:
                    consecutive_failures += 1
            else:
                last_error = result.get("error", "Unknown error")
                agent.logger.log('RETRY', f"Failed: {last_error}, attempt {retry_count + 1}")
                
                # Reflect on failure
                reflection = agent.reflect_on_failure(task, current_step, result, None)
                agent.logger.log('REFLECTION', f"Failure reason: {reflection.get('failure_reason', 'Unknown')}")
                agent.logger.log('REFLECTION', f"Suggested approach: {reflection.get('suggested_approach', 'Not specified')}")
                
                # Try to improve based on reflection
                improved_step = agent.adjust_failed_step(current_step, last_error, agent.task_context, reflection)
                
                if "improved_step" in reflection:
                    current_step = reflection["improved_step"]  # 使用反思返回的完整改进步骤
                elif improved_step != current_step:
                    current_step = improved_step
                
                agent.logger.log('RETRY', "Trying improved step based on reflection...")
                continue
                
                # Only ask for user suggestion if reflection didn't help
                if consecutive_failures >= 2:
                    suggestion = agent.get_user_suggestion()
                    if suggestion:
                        # Add suggestion to context
                        agent.task_context["user_suggestion"] = suggestion
                        # Update current step with user suggestion
                        current_step = agent.plan_next_step_with_suggestion(
                            task, current_step, suggestion, agent.task_context
                        )
                        # Reset retry count to give the new suggestion a chance
                        retry_count = 0
                        consecutive_failures = 0
                        continue
                
                    retry_count += 1
                    total_failures += 1
                    consecutive_failures += 1
                    
                    # Get new analysis after reflection
                    agent.logger.log('RETRY', "Getting new analysis incorporating reflection...")
                    analysis = agent.analyze_task_with_reflection(task, reflection)
        
        # 确保context中包含最后的输出
        agent.task_context["last_output"] = last_output
        
        # Check task completion
        completion_check = agent.check_task_completion(task, agent.task_context)
        
        # Show final conclusion
        if final_analysis:
            agent.logger.log('CONCLUSION', f"Goal: {final_analysis['analysis']['task_goal']}")
            agent.logger.log('CONCLUSION', f"Result: {final_analysis['analysis']['current_info']}")
            if final_analysis['analysis']['evidence']:
                agent.logger.log('CONCLUSION', "Evidence:")
                for evidence in final_analysis['analysis']['evidence']:
                    agent.logger.log('CONCLUSION', f"- {evidence}")
        
        return {
            "task": task,
            "success": success,
            "results": results,
            "thought_process": agent.thought_process,
            "context": agent.task_context,
            "final_analysis": final_analysis,
            "completion_check": completion_check
        } 

    def reflect_on_failure(self, task: str, current_step: Dict[str, Any], result: Dict[str, Any], result_analysis: Optional[Dict[str, Any]], agent=None) -> Dict[str, Any]:
        """Reflect on failure using TaskReflector"""
        # 确保result不为None
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
        
        # 其余代码保持不变
        return_code = result.get("result", {}).get("returncode", "N/A")
        # ...