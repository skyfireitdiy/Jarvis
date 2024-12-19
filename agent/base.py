from typing import Dict, Any, Set
from abc import ABC, abstractmethod
from enum import Enum
from colorama import Fore, Style
from datetime import datetime

from utils.logger import ColorLogger
from tools import Tool, ToolRegistry
from llm import LLM, OllamaLLM

class AgentState(Enum):
    """Agent state enum"""
    IDLE = "idle"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    CONCLUDING = "concluding"

class BaseAgent(ABC):
    """Base agent class defining interface"""
    
    def __init__(self, *args, **kwargs):
        self.state = AgentState.IDLE
        self.logger = ColorLogger()
        self.tool_registry = ToolRegistry()
        self.tried_combinations: Set[tuple] = set()
        
        # Initialize LLM if provided
        self.llm = kwargs.get('llm')
        self.verbose = kwargs.get('verbose', False)
        
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
        
        response = self.llm.chat(prompt)
        
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