from typing import Dict, Any
from colorama import Fore, Style
import json

from .base import AgentState
from utils import extract_json_from_response

class TaskAnalyzer:
    """Task analyzer component"""
    
    def analyze_task(self, task: str, agent) -> Dict[str, Any]:
        """Analyze task and determine next steps"""
        # Build prompt
        prompt_parts = [
            f"Task: {task}",
            "",
            "Please analyze this task and create a detailed plan. Your response should include:",
            "1. What is the overall goal?", 
            "2. What are all the steps needed to complete this task?",
            "3. What information or resources do we need?",
            "4. What should be our first step?",
            "",
            "Available tools:",
            agent.tool_registry.get_tools_description(),
            "",
            "Format your response as JSON:",
            "{",
            '    "analysis": {',
            '        "overall_goal": "Clear description of what we need to accomplish",',
            '        "required_info": ["List of information/resources needed"],',
            '        "potential_challenges": ["List of possible challenges"]',
            '    },',
            '    "task_plan": {',
            '        "overall_goal": "The main objective we are trying to achieve",',
            '        "completed_steps": [],',
            '        "remaining_steps": [',
            '            {',
            '                "step": "Description of step",',
            '                "tool": "Tool to use",',
            '                "expected_result": "What we expect to get"',
            '            }',
            '        ],',
            '        "current_focus": "First step to take"',
            '    },',
            '    "next_step": {',
            '        "tool": "tool_name",',
            '        "parameters": {"param1": "value1"},',
            '        "description": "What this step will do",',
            '        "success_criteria": ["How we know it worked"]',
            '    }',
            "}"
        ]
        
        prompt = "\n".join(prompt_parts)
        response = agent._get_llm_response(prompt)
        
        try:
            analysis = extract_json_from_response(response)
            
            # Store task plan in context if it exists
            if analysis.get('task_plan'):
                if 'task_plan' not in agent.task_context:
                    agent.task_context['task_plan'] = analysis['task_plan']
            
            # Print analysis with consistent formatting
            agent.logger.log('Analysis', f"{Fore.CYAN}╭──────────── 🔍 Initial Analysis ────────────╮{Style.RESET_ALL}", prefix=False)
            
            # Print overall goal
            if analysis.get('analysis', {}).get('overall_goal'):
                agent.logger.log('Analysis', f"{Fore.CYAN}│ Goal:{Style.RESET_ALL} {analysis['analysis']['overall_goal']}")
            
            # Print required information
            if analysis.get('analysis', {}).get('required_info'):
                agent.logger.log('Analysis', f"{Fore.CYAN}│ Required Information:{Style.RESET_ALL}")
                for info in analysis['analysis']['required_info']:
                    agent.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{info}")
            
            # Print task plan
            if analysis.get('task_plan'):
                agent.logger.log('Analysis', f"{Fore.CYAN}│ Task Plan:{Style.RESET_ALL}")
                task_plan = analysis['task_plan']
                agent.logger.log('Analysis', f"{Fore.CYAN}│ • Overall Goal:{Style.RESET_ALL} {task_plan['overall_goal']}")
                if task_plan.get('remaining_steps'):
                    agent.logger.log('Analysis', f"{Fore.CYAN}│ • Planned Steps:{Style.RESET_ALL}")
                    for step in task_plan['remaining_steps']:
                        agent.logger.log('Analysis', f"{Fore.CYAN}│   - {Style.RESET_ALL}{step['step']}")
                agent.logger.log('Analysis', f"{Fore.CYAN}│ • Current Focus:{Style.RESET_ALL} {task_plan['current_focus']}")
            
            # Print potential challenges
            if analysis.get('analysis', {}).get('potential_challenges'):
                agent.logger.log('Analysis', f"{Fore.CYAN}│ Potential Challenges:{Style.RESET_ALL}")
                for challenge in analysis['analysis']['potential_challenges']:
                    agent.logger.log('Analysis', f"{Fore.CYAN}│ • {Style.RESET_ALL}{challenge}")
            
            # Print next step
            if analysis.get('next_step'):
                agent.logger.log('Analysis', f"{Fore.CYAN}│ Next Step:{Style.RESET_ALL}")
                next_step = analysis['next_step']
                agent.logger.log('Analysis', f"{Fore.CYAN}│ • Tool:{Style.RESET_ALL} {next_step['tool']}")
                agent.logger.log('Analysis', f"{Fore.CYAN}│ • Description:{Style.RESET_ALL} {next_step['description']}")
            
            agent.logger.log('Analysis', f"{Fore.CYAN}╰──────────────────────────────────────────╯{Style.RESET_ALL}", prefix=False)
            
            return analysis
            
        except Exception as e:
            agent.logger.log('ERROR', f"Failed to analyze task: {str(e)}")
            return {
                "error": str(e),
                "next_step": None
            }