from typing import Dict, Any, Set
from abc import ABC, abstractmethod
from enum import Enum
from colorama import Fore, Style
from datetime import datetime
import time

from utils.logger import Logger
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
    
    def __init__(self, llm: BaseLLM, tool_registry=None, verbose: bool = False):
        self.state = AgentState.IDLE
        self.logger = Logger()
        from tools import registry
        self.tool_registry = tool_registry or registry
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
        """Get response from LLM with retry logic"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if self.verbose:
                    self.logger.info(f"Sending prompt to LLM ({self.llm.get_model_name()}):\n{prompt}")
                response = self.llm.get_completion(prompt)
                if self.verbose:
                    self.logger.info(f"Received response from LLM:\n{response}")
                return response
            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    raise e
                time.sleep(1)  # Wait before retry
    
    def get_user_suggestion(self) -> str:
        """Get suggestion from user with support for multiline input"""
        print(f"\n{Fore.YELLOW}🤔 The task seems difficult. Do you have any suggestions?{Style.RESET_ALL}")
        print(f"{Fore.CYAN}(Enter your input, use multiple lines if needed. Type 'done' on a new line to finish, or press Enter to skip){Style.RESET_ALL}")
        
        lines = []
        while True:
            line = input("> ").strip()
            if not line and not lines:  # Empty input without previous lines
                return ""
            if line.lower() == 'done' or (not line and lines):  # 'done' or empty line after input
                break
            lines.append(line)
        
        suggestion = "\n".join(lines)
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
    
    @abstractmethod
    def process_input(self, task: str):
        """Process user input"""
        raise NotImplementedError("Subclass must implement process_input method")