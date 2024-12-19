from typing import Dict, Any, Set
from abc import ABC, abstractmethod
from enum import Enum
from colorama import Fore, Style
from datetime import datetime

from utils.logger import ColorLogger
from tools import Tool, ToolRegistry
from llm import BaseLLM

class AgentState(Enum):
    """Agent state enum"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    OBSERVING = "observing"
    DONE = "done"

class BaseAgent(ABC):
    """Base agent class defining interface"""
    
    def __init__(self, llm: BaseLLM, verbose: bool = False):
        self.state = AgentState.IDLE
        self.logger = ColorLogger()
        self.tool_registry = ToolRegistry()
        self.tried_combinations: Set[tuple] = set()
        
        # Initialize LLM if provided
        self.llm = llm
        self.verbose = verbose
        
        # Initialize task-related attributes
        self.task_history = []
        self.current_task = None
        self.thought_process = []
        self.user_suggestions = []
        
        # Initialize task context
        self.task_context = {
            "variables": {},
            "files": {},
            "summaries": [],
            "conclusions": [],
            "attempts": []
        }
    
    def register_tool(self, tool: Tool):
        """Register a new tool"""
        self.tool_registry.register(tool)
    
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
        print(f"\n{Fore.YELLOW}🤔 The task seems difficult. Do you have any suggestions?{Style.RESET_ALL}")
        print("(Press Enter to skip)")
        suggestion = input("> ").strip()
        if suggestion:
            print(f"{Fore.GREEN}👍 Thanks! I'll try with your suggestion.{Style.RESET_ALL}")
            self.user_suggestions.append(suggestion)
        return suggestion
    
    def _get_suggestions_context(self) -> str:
        """Get user suggestions formatted for prompts"""
        if not self.user_suggestions:
            return ""
        
        suggestions = [f"- {suggestion}" for suggestion in self.user_suggestions]
        return "\nUser suggestions:\n" + "\n".join(suggestions)
    
    def get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        return datetime.now().isoformat()
    
    def get_analysis_prompt(self) -> str:
        """Get prompt for analyzing tool execution result"""
        return """Please analyze the execution result and provide a structured response in JSON format with the following fields:

{
    "conclusion": "Brief summary of what was found or determined",
    "key_info": [
        "List of important information extracted from the result",
        "Each item should be a specific fact or finding"
    ],
    "missing_info": [
        "List of information that is still needed",
        "Each item should be specific and actionable"
    ],
    "task_plan": {
        "overall_goal": "The main objective we're trying to achieve",
        "completed_steps": [
            "List of steps that have been completed",
            "Include what was achieved in each step"
        ],
        "remaining_steps": [
            "List of steps still needed to complete the task",
            "Should be specific and actionable"
        ],
        "current_focus": "What we're currently working on"
    },
    "next_steps": [
        "List of specific actions to take next",
        "Each step should be clear and actionable"
    ],
    "task_complete": false,
    "user_confirmation_required": false,
    "user_feedback_required": false
}

CRITICAL RULES:
1. NEVER make up or assume information not present in the actual output
2. If information is missing, list it in missing_info
3. Be specific and precise in your analysis
4. Include actual values and quotes from the output when available
5. task_plan should reflect both what's been done and what's left to do
6. Ensure next_steps align with remaining_steps in the task plan"""