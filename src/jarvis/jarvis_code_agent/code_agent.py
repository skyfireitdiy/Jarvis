from enum import auto
import os
import re
from typing import List

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.git_commiter import GitCommitTool
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_multiline_input, get_single_line_input, has_uncommitted_changes, init_env, find_git_root
from jarvis.jarvis_codebase.main import CodeBase

code_system_prompt = """
You are a code agent, you are responsible for modifying the code.

You should read the code and analyze the code, and then provide a plan for the code modification.
"""


class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code", "execute_shell", "search", "code_review", "ask_user", "apply_patch"])
        self.agent = Agent(system_prompt=code_system_prompt, name="CodeAgent", auto_complete=False, is_sub_agent=False, tool_registry=tool_registry, platform=PlatformRegistry().get_codegen_platform(), record_methodology=False)

    def _find_relevant_files(self, user_input) -> List[str]:
        try:
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
        ret = get_single_line_input(f"{tip}" + "[Y/n]" if default else "[y/N]")
        if ret == "":
            return default
        else:
            return ret == "y"
        
    def run(self, user_input):
        self._init_env()
        files = self._find_relevant_files(user_input)
        prompt = f"User requirement: {user_input}\n\nFiles related to the requirement: {files}\n\nPlease analyze the requirement and the files, and then provide a plan for the code modification."
        while True:
            self.agent.run(prompt)
            user_input = self._user_comfirm("Do you want to modify the code?", default=True)
            if user_input:
                self.agent.run("Please make above modification use `apply_patch` tool. only make ONE patch every time.")
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
                if not user_input or user_input == "__interrupt__":
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
