from typing import Dict, Any, Optional
import json
from colorama import Fore, Style
from utils import extract_json_from_response
from .validation import validate_step_format
from .base import AgentState

class TaskAnalyzer:
    """Task analysis functionality"""
    
    def analyze_task(self, task: str, agent) -> Dict[str, Any]:
        """Analyze task and return execution plan"""
        agent.state = AgentState.ANALYZING
        agent.logger.log('ANALYSIS', f"Analyzing task: {task}")
        
        # Create a detailed summary of completed steps and their results
        completed_summary = []
        for i, (var_name, result) in enumerate(sorted(agent.task_context["variables"].items())):
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
        if agent.task_context.get("summaries"):
            completed_summary.extend([
                f"Found information:",
                *[f"- {info}" for info in agent.task_context["summaries"]]
            ])
        
        if agent.task_context.get("conclusions"):
            completed_summary.extend([
                f"Conclusions drawn:",
                *[f"- {conclusion}" for conclusion in agent.task_context["conclusions"]]
            ])
        
        # Add user suggestions to the prompt
        suggestions_context = agent._get_suggestions_context()
        
        # Build prompt parts
        prompt_parts = [
            f"I need to accomplish this task: {task}",
            "",
            "These are the tools I have available:",
            agent.tool_registry.get_tools_description(),
            "",
            "So far, this is what has been done:",
            chr(10).join(completed_summary) if completed_summary else "Nothing has been done yet",
            suggestions_context,
            "",
            "Could you help me:",
            "1. Understand what exactly needs to be accomplished",
            "2. Identify what information we already have",
            "3. Determine what information we still need",
            "4. Plan the next step if we're not done",
            "5. Consider any user suggestions when planning the next step",
            "",
            "Please structure your response in this JSON format:",
            "{"
            '    "analysis": {'
            '        "task_goal": "What exactly needs to be accomplished",'
            '        "current_info": "What information we already have",'
            '        "missing_info": "What information we still need",'
            '        "evidence": ["Specific fact we found 1", "Specific fact we found 2"]'
            "    },",
            '    "next_step": {'
            '        "tool": "tool_name",'
            '        "parameters": {"param_name": "param_value"},'
            '        "description": "What we\'ll do next",'
            '        "success_criteria": ["How we\'ll know it worked"]'
            "    },",
            '    "required_tasks": []'
            "}",
            "",
            "Important:",
            "- Be specific about what information we have and what we need",
            "- Make sure the next step directly helps get missing information",
            "- Include actual values and facts in the evidence"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = agent._get_llm_response(prompt)
        analysis = extract_json_from_response(response)
        
        if agent.verbose:
            agent.logger.log('ANALYSIS-RESULT', f"Parsed analysis:\n{json.dumps(analysis, indent=2, ensure_ascii=False)}")
        
        if "error" in analysis or not agent.validate_step_format(analysis):
            if agent.verbose:
                agent.logger.log('ANALYSIS-ERROR', "Invalid analysis format, retrying...")
            return agent.retry_task_analysis(task, response)
        
        # Log analysis results with highlights
        agent.logger.log('ANALYSIS', f"{Fore.GREEN}Goal:{Style.RESET_ALL} {analysis['analysis']['task_goal']}")
        
        if analysis['analysis']['current_info']:
            agent.logger.log('ANALYSIS', f"{Fore.CYAN}Current Info:{Style.RESET_ALL}")
            current_info = analysis['analysis']['current_info'].split('\n')
            for info in current_info:
                if info.strip():
                    agent.logger.log('ANALYSIS', f"{Fore.CYAN}• {info.strip()}{Style.RESET_ALL}")
        
        if analysis['analysis']['missing_info']:
            agent.logger.log('ANALYSIS', f"{Fore.YELLOW}Missing Info:{Style.RESET_ALL}")
            missing_info = analysis['analysis']['missing_info'].split('\n')
            for info in missing_info:
                if info.strip():
                    agent.logger.log('ANALYSIS', f"{Fore.RED}• {info.strip()}{Style.RESET_ALL}")
        
        return analysis 