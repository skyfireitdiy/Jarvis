


import os
import re
from typing import List

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, is_disable_codebase


def find_relevant_files(user_input: str, root_dir: str) -> List[str]:
    try:
        files_from_codebase = []
        if not is_disable_codebase():
            PrettyOutput.print("Find files from codebase...", OutputType.INFO)
            codebase = CodeBase(root_dir)
            files_from_codebase = codebase.search_similar(user_input)

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
        prompt = f"Find files related about '{user_input}'\n"
        if files_from_codebase:
            prompt += f"\n\nFiles maybe related: {files_from_codebase}\n\n Please read above files first"
        output = find_file_agent.run(prompt)

        rsp_from_agent = re.findall(r'<FILE_PATH>(.*?)</FILE_PATH>', output, re.DOTALL)
        files_from_agent = []
        if rsp_from_agent:
            try:
                files_from_agent = yaml.safe_load(rsp_from_agent[0])
            except Exception as e:
                files_from_agent = []
        else:
            files_from_agent = []

        selected_files = select_files(files_from_agent, os.getcwd())
        return selected_files
    except Exception as e:
        return []