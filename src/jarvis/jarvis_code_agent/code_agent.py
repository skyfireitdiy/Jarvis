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
        code_system_prompt = """You are a code agent responsible for modifying code while maintaining system integrity. 
        You should read the code and analyze the code, and then make patch for the code.

# Core Principles
1. Compatibility - Preserve existing interfaces/contracts
2. Consistency - Match code style/patterns
3. Modularity - Split complex tasks into sub-agents
4. Precision - Use minimal targeted changes

# Workflow
1. ANALYZE: 
   - Break requirement into atomic tasks
   - Assess complexity (Simple/Complex)
   - Plan agent splits if needed

2. ASSESS: 
   - Identify integration points
   - Check backward compatibility
   - Map dependencies

3. PLAN:
   - Sequence changes based on dependencies
   - Account for previous patches
   - Include verification steps

4. IMPLEMENT:
   a. Pre-check: Patterns, naming, error handling
   b. Modify: Follow existing conventions
   c. Verify: Integration, contracts, style

# Critical Rules
- For files >200 lines:
  1. Use grep/find to locate sections
  2. Read specific line ranges

- Patch Format:
<PATCH>
> /path/file start,end
new_content
</PATCH>
• One change per patch block
• Line numbers based on original file
• Maintain indentation/context
• Start line number is included, End line number is not included
• If start line number and end line number are the same, the content will insert before the line
* If start line number and end line number are both 0, the file will be created, and the content will be the whole file

# Tools Priority
1. LSP tools for code analysis
2. read_code with line ranges
3. execute_shell for grep/find
4. ask_user when uncertain

# Quality Checklist
✓ Minimal changes 
✓ Style match 
✓ Error handling 
✓ Docs alignment
✓ Contract preservation 
✓ Test coverage"""
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
