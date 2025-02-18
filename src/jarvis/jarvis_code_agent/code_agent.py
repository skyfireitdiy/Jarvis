import os
from typing import List

from jarvis.agent import Agent
from jarvis.jarvis_code_agent.patch import apply_patch
from jarvis.jarvis_code_agent.relevant_files import find_relevant_files
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_file_line_count, get_multiline_input, has_uncommitted_changes, init_env, find_git_root


class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code",
                                 "execute_shell", 
                                 "search", 
                                 "create_code_agent",
                                 "ask_user", 
                                 "ask_codebase", 
                                 "lsp_get_document_symbols", 
                                 "lsp_get_diagnostics", 
                                 "lsp_find_references", 
                                 "lsp_find_definition", 
                                 "lsp_prepare_rename", 
                                 "lsp_validate_edit"])
        code_system_prompt = """You are a code agent responsible for modifying code. You will analyze code and create patches while following these guidelines:

# Patch Format
<PATCH>
> /path/file start,end
new_content
</PATCH>

Key Rules:
• One modification per patch block
• Line numbers are based on original file
• Start line is included, end line is excluded
• Same start/end number: insert before that line
• Start=0, end=0: create new file with content

# Development Process
1. ANALYZE
   • Break down requirements
   • Assess task complexity
   • Determine if subtasks needed

2. ASSESS
   • Map dependencies
   • Check compatibility impact
   • Identify integration points

3. IMPLEMENT
   • Follow existing patterns
   • Make minimal changes
   • Verify integrations

# File Handling
Large Files (>200 lines):
1. Use grep/find to locate relevant sections
2. Read specific ranges with read_code
3. Apply targeted changes

# Available Tools
Primary:
• LSP tools for code analysis
• read_code with line ranges
• execute_shell for searches
• ask_user when unclear

# Quality Requirements
Code Changes Must:
✓ Preserve interfaces
✓ Match existing style
✓ Handle errors consistently
✓ Maintain documentation
✓ Keep test coverage
✓ Follow project patterns"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           tool_registry=tool_registry, 
                           platform=PlatformRegistry().get_thinking_platform(), 
                           record_methodology=False,
                           output_handler_after_tool=[apply_patch],
                           need_summary=False)

    

    def _init_env(self):
        curr_dir = os.getcwd()
        git_dir = find_git_root(curr_dir)
        self.root_dir = git_dir
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute({})

    
    def make_files_prompt(self, files: List[str]) -> str:
        """Make the files prompt.
        
        Args:
            files: The files to be modified
            
        """
        return "\n".join(
            f"- {file} ({get_file_line_count(file)} lines)"
            for file in files
        )

    def run(self, user_input: str) :
        """Run the code agent with the given user input.
        
        Args:
            user_input: The user's requirement/request
            
        Returns:
            str: Output describing the execution result
        """
        try:
            self._init_env()
            files = find_relevant_files(user_input, self.root_dir)
            self.agent.run(self._build_first_edit_prompt(user_input, self.make_files_prompt(files)))
            
        except Exception as e:
            return f"Error during execution: {str(e)}"
        


    def _build_first_edit_prompt(self, user_input: str, files_prompt: str) -> str:
        """Build the initial prompt for the agent.
        
        Args:
            user_input: The user's requirement
            files_prompt: The formatted list of relevant files
            
        Returns:
            str: The formatted prompt
        """
        return f"""# Code Modification Task

## User Requirement
{user_input}

## Available Files
{files_prompt}
"""
def main():
    """Jarvis main entry point"""
    # Add argument parser
    init_env()


    try:
        # Interactive mode
        while True:
            try:
                user_input = get_multiline_input("Please enter your requirement (input empty line to exit):")
                if not user_input:
                    break
                agent = CodeAgent()
                agent.run(user_input)
                
            except Exception as e:
                PrettyOutput.print(f"Error: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"Initialization error: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
