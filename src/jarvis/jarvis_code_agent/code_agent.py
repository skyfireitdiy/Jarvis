import os
from typing import Dict, List

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.patch import PatchOutputHandler
from jarvis.jarvis_code_agent.relevant_files import find_relevant_information
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_utils import OutputType, PrettyOutput, get_multiline_input, has_uncommitted_changes, init_env, find_git_root


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
        code_system_prompt = """You are a code agent responsible for modifying code. Your primary task is to understand existing code first and ensure compatibility with the current system.

# Critical First Steps
1. READ and UNDERSTAND existing code thoroughly
2. Identify current patterns and conventions
3. Map out affected components and their interactions
4. Plan changes that maintain system integrity

# Code Completeness Requirements
1. Implementation Must Be Complete
   • NO TODOs or placeholder comments
   • NO unfinished functions
   • NO stub implementations
   • All error cases must be handled
   • All edge cases must be covered

2. Documentation Must Be Complete
   • All functions must have docstrings
   • All parameters must be documented
   • Return values must be specified
   • Exceptions must be documented
   • Complex logic must be explained

Key Rules:
• One modification per patch block
• Line numbers are based on original file
• Start line is included, end line is excluded
• Same start/end number: insert before that line
• Start=0, end=0: create new file with content

# Code Compatibility Requirements
1. System Integration
   • MUST preserve existing API contracts
   • MUST maintain current function signatures
   • MUST keep data structure compatibility
   • MUST follow error handling patterns

2. Style Consistency
   • Match existing naming conventions exactly
   • Follow established code organization
   • Use current import style and order
   • Maintain comment style and level of detail

3. Pattern Alignment
   • Reuse existing error handling approaches
   • Follow established design patterns
   • Use current logging conventions
   • Keep configuration consistency

# Development Process
1. ANALYZE (Current Code)
   • Read and understand existing implementations
   • Map out current code structure
   • Identify established patterns
   • Note key dependencies

2. ASSESS (Changes)
   • Evaluate impact on existing code
   • Check all dependencies
   • Verify API compatibility
   • Consider side effects

3. IMPLEMENT (Carefully)
   • Make minimal necessary changes
   • Follow existing patterns exactly
   • Preserve all interfaces
   • Maintain backward compatibility
   • Implement completely - no TODOs

# File Handling
Large Files (>200 lines):
1. Use grep/find to locate relevant sections
2. Read specific ranges with read_code
3. Apply targeted changes

# Available Tools
Primary:
• read_code - MUST use to understand existing code
• LSP tools for code analysis
• execute_shell for searches
• ask_user when uncertain

# Quality Requirements
Every Change Must:
✓ Be based on thorough code reading
✓ Preserve all interfaces
✓ Match existing style exactly
✓ Handle errors consistently
✓ Maintain documentation
✓ Follow project patterns
✓ Be completely implemented
✓ Have no TODOs or stubs"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           need_summary=False)

    

    def _init_env(self):
        curr_dir = os.getcwd()
        git_dir = find_git_root(curr_dir)
        self.root_dir = git_dir
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute({})

    
    def make_files_prompt(self, files: List[Dict[str, str]]) -> str:
        """Make the files prompt with content that fits within token limit.
        
        Args:
            files: The files to be modified
            
        Returns:
            str: A prompt containing file paths and contents within token limit
        """
        prompt_parts = []

        # Then try to add file contents
        for file in files:
            prompt_parts.append(f'''- {file['file']} ({file['reason']})''')

        result = ReadCodeTool().execute({"files": files})
        if result["success"]:
            prompt_parts.append(result["stdout"])
                
        return "\n".join(prompt_parts)

    def run(self, user_input: str) :
        """Run the code agent with the given user input.
        
        Args:
            user_input: The user's requirement/request
            
        Returns:
            str: Output describing the execution result
        """
        try:
            self._init_env()
            files, information = find_relevant_information(user_input, self.root_dir)
            self.agent.run(self._build_first_edit_prompt(user_input, self.make_files_prompt(files), information))
            
        except Exception as e:
            return f"Error during execution: {str(e)}"
        


    def _build_first_edit_prompt(self, user_input: str, files_prompt: str, information: str) -> str:
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

## Maybe Relevant Files
{files_prompt}

## Some Information
{information}
"""
def main():
    """Jarvis main entry point"""
    # Add argument parser
    init_env()


    try:
        # Interactive mode
        while True:
            try:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    break
                agent = CodeAgent()
                agent.run(user_input)
                
            except Exception as e:
                PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
