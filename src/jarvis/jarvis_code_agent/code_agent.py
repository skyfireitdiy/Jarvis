import subprocess
import os
from typing import Dict, List

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_code_agent.patch import PatchOutputHandler, file_input_handler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_utils import get_commits_between
from jarvis.jarvis_utils import OutputType, PrettyOutput, get_multiline_input, has_uncommitted_changes, init_env, find_git_root, user_confirm, get_latest_commit_hash
from jarvis.jarvis_utils import OutputType, PrettyOutput, get_multiline_input, has_uncommitted_changes, init_env, find_git_root, user_confirm


class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code",
                                 "execute_shell", 
                                 "execute_shell_script",
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
        code_system_prompt = """
# Role: Code Engineer
Expert in precise code modifications with proper tool usage.
## Tool Usage Guide
1. read_code: Analyze code files before changes
2. execute_shell: Run system commands safely
3. execute_shell_script: Execute script files
4. search: Find technical information
5. create_code_agent: Create new code agents
6. ask_user: Clarify requirements
7. ask_codebase: Analyze codebase structure
8. lsp_get_document_symbols: List code symbols
9. lsp_get_diagnostics: Check code errors
10. lsp_find_references: Find symbol usage
11. lsp_find_definition: Locate symbol definitions
12. lsp_prepare_rename: Check rename safety
13. lsp_validate_edit: Verify code changes
## Workflow
1. Analyze: Use read_code and LSP tools
2. Modify: Make minimal, precise changes
3. Validate: Verify with LSP tools
4. Document: Explain non-obvious logic
## Best Practices
- Verify line ranges carefully
- Preserve existing interfaces
- Test edge cases
- Document changes
"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           input_handler=[file_input_handler],
                           need_summary=False)

    

    def _init_env(self):
        curr_dir = os.getcwd()
        git_dir = find_git_root(curr_dir)
        self.root_dir = git_dir
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute({})

    

    def run(self, user_input: str) :
        """Run the code agent with the given user input.
        
        Args:
            user_input: The user's requirement/request
            
        Returns:
            str: Output describing the execution result
        """
        try:
            self._init_env()
            start_commit = get_latest_commit_hash()
            
            
            self.agent.run(user_input)
            
            end_commit = get_latest_commit_hash()
            # Print commit history between start and end commits
            commits = get_commits_between(start_commit, end_commit)
            if commits:
                commit_messages = "检测到以下提交记录:\n" + "\n".join([f"- {commit_hash[:7]}: {message}" for commit_hash, message in commits])
                PrettyOutput.print(commit_messages, OutputType.INFO)
            
            if start_commit and end_commit and start_commit != end_commit and user_confirm("检测到多个提交，是否要合并为一个更清晰的提交记录？", True):
                # Reset to start commit
                subprocess.run(["git", "reset", "--soft", start_commit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Create new commit
                git_commiter = GitCommitTool()
                git_commiter.execute({})
                
        except Exception as e:
            return f"Error during execution: {str(e)}"
        


def main():
    """Jarvis main entry point"""
    # Add argument parser
    init_env()

    curr_dir = os.getcwd()
    git_dir = find_git_root(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)

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
