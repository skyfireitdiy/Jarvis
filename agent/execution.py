from typing import Dict, Any, List, Optional
import json
from utils import extract_json_from_response
from .base import AgentState  # 导入AgentState
from colorama import Fore, Style

class TaskExecutor:
    """Task execution functionality"""
    
    def execute_task(self, task: str, agent) -> Dict[str, Any]:
        """Execute task using available tools"""
        agent.state = AgentState.EXECUTING
        
        # Initialize execution context
        context = {
            'variables': {},
            'files': {},
            'summaries': [],
            'conclusions': []
        }
        
        # Main execution loop
        max_steps = 10
        step_count = 0
        
        while step_count < max_steps:
            step_count += 1
            
            # Get next step
            analysis = agent.analyze_task(task)
            if not analysis or 'next_step' not in analysis:
                agent.logger.log('ERROR', "Failed to get next step from analysis")
                break
            
            # Get next step
            current_step = analysis.get('next_step')
            if not current_step:
                agent.logger.log('Execute', "No next step available. Asking for user suggestion...")
                suggestion = agent.get_user_suggestion()
                if not suggestion:
                    break
                    
                # Try to plan next step with user suggestion
                current_step = agent.plan_next_step_with_suggestion(task, current_step or {}, suggestion, context)
                if not current_step:
                    break
            
            # Log execution phase
            agent.logger.log('Execute', f"╭──────────── 🔄 Execution Phase {step_count} ────────────╮", prefix=False)
            agent.logger.log('Execute', f"│ Tool: {current_step.get('tool')}")
            agent.logger.log('Execute', f"│ Description: {current_step.get('description', 'No description')}")
            
            # Log parameters
            agent.logger.log('Execute', "│ Parameters:")
            for key, value in current_step.get('parameters', {}).items():
                agent.logger.log('Execute', f"│   • {key}: {value}")
            
            # Log success criteria
            agent.logger.log('Execute', "│ Success Criteria:")
            for criteria in current_step.get('success_criteria', []):
                agent.logger.log('Execute', f"│   ✓ {criteria}")
            
            agent.logger.log('Execute', "│ Executing...")
            agent.logger.log('Execute', "╰──────────────────────────────────────────╯", prefix=False)
            
            # Execute step
            result = agent.execute_step(current_step)
            
            # Analyze result
            result_analysis = agent.analyze_tool_result(task, current_step, result)
            
            # Update context with result
            context['last_output'] = result.get('result', {})
            if result.get('success'):
                if 'variables' in result.get('result', {}):
                    context['variables'].update(result['result']['variables'])
                if 'files' in result.get('result', {}):
                    context['files'].update(result['result']['files'])
                if 'summary' in result.get('result', {}):
                    context['summaries'].append(result['result']['summary'])
                if 'conclusion' in result.get('result', {}):
                    context['conclusions'].append(result['result']['conclusion'])
            
            # Check if task is complete
            if result_analysis.get('task_complete', False):
                break
            
            # Handle retry if needed
            if result_analysis.get('needs_retry', False):
                reflection = agent.reflect_on_failure(task, current_step, result, result_analysis)
                current_step = agent.adjust_failed_step(current_step, result.get('error', ''), context, reflection)
                continue
        
        # Return final context
        return context

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

    def execute_step(self, step: Dict[str, Any], agent) -> Dict[str, Any]:
        """Execute a single step"""
        if not isinstance(step, dict):
            return {
                "success": False,
                "error": "Invalid step format",
                "result": None
            }
        
        # 从工具名称中提取工具ID
        tool_name = step.get("tool", "")
        tool_id = tool_name.split("(")[-1].strip(")") if "(" in tool_name else tool_name
        
        # 获取工��实例
        tool = agent.tool_registry.get_tool(tool_id)
        
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