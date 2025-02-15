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
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, get_single_line_input, has_uncommitted_changes, init_env, find_git_root, is_disable_codebase, user_confirm





class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code", "execute_shell", "search", "code_review", "ask_user"])
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

    def _handle_commit_workflow(self) -> tuple[bool, str, str]:
        """Handle the git commit workflow and return the commit details.
        
        Returns:
            tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
        """
        if not user_confirm("Do you want to commit the code?", default=True):
            os.system("git reset HEAD")
            os.system("git checkout -- .")
            advice = get_multiline_input("Please provide advice for the code modification. (empty line to exit)")
            return False, "", advice

        git_commiter = GitCommitTool()
        commit_result = git_commiter.execute({})
        commit_id = ""
        commit_message = ""
        
        if commit_result["success"]:
            structured_data = yaml.safe_load(commit_result["stdout"])
            commit_id = structured_data["commit_id"]
            commit_message = structured_data["commit_message"]

        if not user_confirm("Do you want to continue?", default=False):
            return False, commit_id, commit_message

        new_requirement = get_multiline_input("Please input new requirement. (empty line to exit)")
        if not new_requirement:
            return False, commit_id, commit_message

        return True, commit_id, commit_message

    def run(self, user_input: str) -> str:
        """Run the code agent with the given user input.
        
        Args:
            user_input: The user's requirement/request
            
        Returns:
            str: Output describing the execution result
        """
        try:
            self._init_env()
            files = find_relevant_files(user_input, self.root_dir)
            
            files_prompt = "\n".join(
                f"- {file} ({self._get_file_line_count(file)} lines)"
                for file in files
            )

            prompt = self._build_initial_prompt(user_input, files_prompt)
            output = ""

            while True:
                self.agent.run(prompt)

                if not has_uncommitted_changes():
                    prompt = get_multiline_input(
                        "Please input your advice for the code modification. (empty line to exit)"
                    )
                    if not prompt:
                        return output + "User cancelled the task, code has been reset"
                    continue

                continue_execution, commit_id, result = self._handle_commit_workflow()
                
                if not continue_execution:
                    if commit_id:  # Committed but don't want to continue
                        return output + "Task completed"
                    if result:  # Not committed, but have advice
                        prompt = f"User reject this patch, code has been reset. user advice: {result}\n"
                        prompt += "Please re-analyze the requirement and the files, and then provide a plan for the code modification."
                        continue
                    return output + "Task cancelled by user"

                # Continue with new requirement
                prompt = (
                    f"User has applied patches, commit id: '{commit_id}' "
                    f"commit message: '{result}'\n\n"
                    "Please analyze the new requirement, and then provide a plan "
                    "for the code modification."
                )
                output += prompt

        except Exception as e:
            return f"Error during execution: {str(e)}"

    def _build_initial_prompt(self, user_input: str, files_prompt: str) -> str:
        """Build the initial prompt for the agent.
        
        Args:
            user_input: The user's requirement
            files_prompt: The formatted list of relevant files
            
        Returns:
            str: The formatted prompt
        """
        return f"""User requirement: {user_input}

Files related to the requirement: 
{files_prompt}

## Analysis Phase
Please analyze the requirement and the files, then provide a plan for the code modification.

### File Analysis Tips
- For large files (>200 lines):
  - Use shell commands (ctags/grep) to locate key sections
  - Then use `read_code` to examine specific parts
- For small files (<100 lines):
  - Use `read_code` to analyze the entire file
- If key locations are unclear:
  - Use `ask_user` to get guidance

## Implementation Guidelines

### Clean Code Principles
1. Keep functions small and focused
2. Use meaningful and descriptive names
3. Maintain consistent code style
4. Add clear comments for complex logic
5. Follow DRY (Don't Repeat Yourself)
6. Keep code modular and maintainable
7. Handle errors appropriately
8. Write self-documenting code
9. Keep code simple and readable
10. Follow project patterns and conventions

### Pre-Patch Checklist
- Changes are minimal and focused
- Code style matches existing codebase
- Indentation is consistent
- Changes follow clean code principles
- Modifications are well-documented
- Filenames are correct

## Patch Format
Patches should follow this format:
<PATCH>
> /path/to/file start_line,end_line
content_line1
content_line2
...
</PATCH> 

Notes:
- The patch replaces content from start_line (will replace this line) to end_line (will not replace this line)
    Example:
    
    Before:
    ```
    content_line1
    content_line2
    ```

    Patch:
    ```
    > /path/to/file 1,2
    content_line1
    content_line2
    ```
    
    After:
    ```
    content_line1
    content_line2
    content_line2
    ```
    </PATCH> 
- You can output multiple patches, use multiple <PATCH> blocks

"""



    def _get_file_line_count(self, filename: str) -> int:
        try:
            return len(open(filename, "r", encoding="utf-8").readlines())
        except Exception as e:
            return 0


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
