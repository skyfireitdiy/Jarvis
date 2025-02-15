from enum import auto
import os
import re
from typing import List

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_code_agent.patch import apply_patch
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_code_agent.relevant_files import find_relevant_files
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.git_commiter import GitCommitTool
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_file_line_count, get_multiline_input, get_single_line_input, has_uncommitted_changes, init_env, find_git_root, is_disable_codebase, make_choice_input, user_confirm





class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code", "execute_shell", "search", "ask_user", "ask_codebase"])
        code_system_prompt = """
You are a code agent, you are responsible for modifying the code.

You should read the code and analyze the code, and then provide a plan for the code modification.
"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           tool_registry=tool_registry, 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           output_filter=[apply_patch])

    

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

## Workflow Steps

1. ANALYSIS
- Understand the requirement thoroughly
- Identify which files need to be modified
- Review the current implementation
- Consider potential impacts

2. PLANNING
- Break down the changes into logical steps
- Consider dependencies between changes
- Plan the implementation sequence
- Think about potential risks

3. IMPLEMENTATION
For each file that needs changes:
a. Read and understand the current code
b. Plan the specific modifications
c. Write the patch in the required format
d. Review the patch for correctness

## Patch Format and Guidelines

1. Basic Format:
<PATCH>
> /path/to/file start_line,end_line
new_content_line1
new_content_line2
</PATCH>

2. Rules:
- The patch replaces content from start_line (inclusive) to end_line (exclusive)
- Use absolute paths relative to the project root
- Maintain consistent indentation
- Include enough context for precise location
- You can output multiple patches using multiple <PATCH> blocks

3. Example:
Before:
```
old_content_line0
old_content_line1
```

Patch:
```
<PATCH>
> /path/to/file 0,1
new_content_line0
new_content_line1
</PATCH>
```

After:
```
new_content_line0
new_content_line1
old_content_line1

```

Because the patch replaced [0,1), the content of old_content_line1 is not changed.

## Implementation Guidelines

1. Code Quality:
- Keep changes minimal and focused
- Maintain consistent style
- Add clear comments for complex logic
- Follow project patterns
- Ensure proper error handling

2. Tools Available:
- Use 'read_code/ask_codebase' to examine file contents
- Use 'execute_shell' for grep/find/ctags operations
- Use 'search' to search on web
- Use 'ask_user' when clarification is needed

Please proceed with the analysis and implementation following this workflow.
Start by examining the files and planning your changes.
Then provide the necessary patches in the specified format.
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
