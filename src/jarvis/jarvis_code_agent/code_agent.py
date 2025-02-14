from enum import auto
import os
import re
from typing import List

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_code_agent.apply_patch import apply_patch
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.git_commiter import GitCommitTool
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, get_single_line_input, has_uncommitted_changes, init_env, find_git_root, is_disable_codebase
from jarvis.jarvis_codebase.main import CodeBase

code_system_prompt = """
You are a code agent, you are responsible for modifying the code.

You should read the code and analyze the code, and then provide a plan for the code modification.
"""


class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code", "execute_shell", "search", "code_review", "ask_user"])
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           tool_registry=tool_registry, 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           output_filter=[apply_patch])

    def _find_relevant_files(self, user_input) -> List[str]:
        try:
            files1 = []
            if not is_disable_codebase():
                PrettyOutput.print("Find files from codebase...", OutputType.INFO)
                codebase = CodeBase(self.root_dir)
                files1 = codebase.search_similar(user_input)

            PrettyOutput.print("Find files by agent...", OutputType.INFO)
            find_file_tool_registry = ToolRegistry()
            find_file_tool_registry.use_tools(["read_code", "execute_shell"])
            find_file_agent = Agent(
                system_prompt="""You are a file agent, you are responsible for finding files related to the user's requirement.
            You can use `read_code` tool to read the code and analyze the code, and `execute_shell` tool to execute shell command(such as `grep/find/ls/git/ctags`) to find files.

            IMPORTANT:
            - Only provide the file path, do not provide any other information.
            - If you can't find the file, please provide empty list.
            - Don't modify the code, just find related files.
            """, 
                name="FindFileAgent", 
                is_sub_agent=True,
                tool_registry=find_file_tool_registry, 
                platform=PlatformRegistry().get_normal_platform(),
                auto_complete=True,
                summary_prompt="""Please provide the file path as this format(yaml list), if you can't find the file, please provide empty list:
                <FILE_PATH>
                - file_path1
                - file_path2
                </FILE_PATH>
                """)
            output = find_file_agent.run(f"Find files related about '{user_input}'")

            files = re.findall(r'<FILE_PATH>(.*?)</FILE_PATH>', output, re.DOTALL)
            files2 = []
            if files:
                try:
                    files2 = yaml.safe_load(files[0])
                except Exception as e:
                    files2 = []
            else:
                files2 = []
            

            final_files = set(files1) | set(files2)

            selected_files = select_files(list(final_files), os.getcwd())
            return selected_files
        except Exception as e:
            return []

    def _init_env(self):
        curr_dir = os.getcwd()
        git_dir = find_git_root(curr_dir)
        self.root_dir = git_dir
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute({})

    def _user_comfirm(self, tip:str, default=True):
        ret = get_single_line_input(f"{tip}" + "[Y/n]" if default else "[y/N]" + ": ")
        if ret == "":
            return default
        else:
            return ret == "y"
        
    def _get_file_line_count(self, filename: str) -> int:
        try:
            return len(open(filename, "r", encoding="utf-8").readlines())
        except Exception as e:
            return 0
        
    def run(self, user_input):
        self._init_env()
        files = self._find_relevant_files(user_input)
        files_prompt = ""
        for file in files:
            files_prompt += f"- {file} ({self._get_file_line_count(file)} lines)\n"   
        prompt = f"""User requirement: {user_input}

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
- The patch replaces content from start_line (included) to end_line (excluded)
- You can output multiple patches
- <PATCH> and <TOOL_CALL> can only appear once in the output, if both appear, the <PATCH> will be ignored.

"""
        while True:
            self.agent.run(prompt)
            if has_uncommitted_changes():
                if self._user_comfirm("Do you want to commit the code?", default=True):
                    git_commiter = GitCommitTool()
                    commit_result = git_commiter.execute({})
                    commit_id = ""
                    commit_message = ""
                    if commit_result["success"]:
                        structed_data = yaml.safe_load(commit_result["stdout"])
                        commit_id = structed_data["commit_id"]
                        commit_message = structed_data["commit_message"]
                    if self._user_comfirm("Do you want to continue?", default=False):
                        new_requirement = get_multiline_input("Please input new requirement. (empty line to exit)")
                        if new_requirement == "":
                            break
                        
                        prompt = f"User has apply patches, commit id: '{commit_id}' commit message: '{commit_message}'\n\nPlease analyze the new requirement, and then provide a plan for the code modification."
                        continue
                else:
                    os.system("git reset --hard")
                    advice = get_multiline_input("Please provide advice for the code modification. (empty line to exit)")
                    if advice:
                        self.agent.run(f"User reject this patch, code has been reset. user advice: {advice}\n Please re-analyze the requirement and the files, and then provide a plan for the code modification.")
            else:
                prompt = get_multiline_input("Please input your advice for the code modification. (empty line to exit)")
                if not prompt:
                    break


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
