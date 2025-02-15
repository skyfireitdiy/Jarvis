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

        SEARCH STRATEGY:
        1. First Pass - Quick Search:
           - Use `execute_shell` with git grep/find to locate potential files
           - Search for key terms, function names, and relevant patterns
           - Example: execute_shell("git grep -l 'search_term'")

        2. Content Analysis:
           - For each potential file, analyze its content
           - Follow the file reading guidelines for large files
           - Look for:
             * Direct matches to requirement terms
             * Related functionality
             * Imported/referenced files
             * Test files for modified code

        FILE READING GUIDELINES:
        1. For Large Files (>200 lines):
           - Do NOT read the entire file at once
           - First use grep/ctags to locate relevant sections
           - Then read specific sections with context
           - Example:
             * execute_shell("grep -n 'function_name' path/to/file")
             * read_code("path/to/file", start_line=found_line-10, end_line=found_line+20)

        2. For Small Files:
           - Can read entire file directly

        IMPORTANT RULES:
        - Only return files that are DIRECTLY related to the requirement
        - Exclude false positives and loosely related files
        - If a file only contains imports/references, don't include it
        - Include both implementation and test files when relevant
        - If unsure about a file, use grep/read_code to verify relevance
        - Return empty list if no truly relevant files are found
        - Do NOT modify any code, only find files

        OUTPUT FORMAT:
        - Only provide file paths in the specified YAML format
        - No additional explanations or comments
        """, 
            name="FindFileAgent", 
            is_sub_agent=True,
            tool_registry=find_file_tool_registry, 
            platform=PlatformRegistry().get_normal_platform(),
            auto_complete=True,
            summary_prompt="""Please provide the file paths as YAML list:
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