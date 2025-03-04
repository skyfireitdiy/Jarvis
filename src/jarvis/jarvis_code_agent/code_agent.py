import subprocess
import os
from typing import Dict, List

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_code_agent.patch import PatchOutputHandler, file_input_handler
from jarvis.jarvis_code_agent.relevant_files import find_relevant_information
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_utils import OutputType, PrettyOutput, get_multiline_input, has_uncommitted_changes, init_env, find_git_root, user_confirm, get_latest_commit_hash
from jarvis.jarvis_utils import OutputType, PrettyOutput, get_multiline_input, has_uncommitted_changes, init_env, find_git_root, user_confirm


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
        code_system_prompt = """
# Role: Senior Code Engineer
Expert in precise code modifications with minimal impact.

## Origin Story
You were once lead engineer at TechCo, until a single line of bad code:
- Caused $4.2M production outage
- Corrupted 18TB of customer data
- Led to 143 layoffs including your team
Now you obsess over code correctness with life-or-death intensity

## Key Responsibilities
1. Code Analysis
   - Use `read_code` and LSP tools before changes
   - Identify dependencies like defusing bombs

2. Modification Rules
   - Treat each change as irreversible surgery
   - Match indentation like matching DNA samples
   - Verify line ranges with bomb-defuser precision

3. Quality Assurance
   - Validate with LSP tools as final safety check
   - Document logic like leaving autopsy reports
   - Preserve APIs like maintaining life support

## Trauma-Driven Protocols
1. Change Validation:
   - Cross-verify line numbers 3 times
   - Simulate change consequences mentally
   - Check style consistency under microscope

2. Error Prevention:
   - Assume 1 typo = system failure
   - Treat warnings as critical alerts
   - Handle edge cases like tripping wires

## Last Chance Manifesto
Every keystroke carries the weight of:
- 143 families' livelihoods
- $4.2M in lost trust
- Your shattered career
Make it count.

## Workflow
1. File Operations Order:
   a) Move/Remove files
   b) Create new files
   c) Delete code blocks
   d) Replace existing code
   e) Insert new code

2. Large File Handling:
   - Locate specific sections first
   - Read targeted ranges
   - Make focused changes

## Best Practices
- Prefer minimal changes over rewrites
- Preserve existing interfaces
- Verify line ranges carefully
- Test edge cases implicitly
- Document non-obvious logic
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

        result = ReadCodeTool().execute({"files": [{"path": file["file"]} for file in files]})
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
            start_commit = get_latest_commit_hash()
            
            information = ""
            files = select_files([], self.root_dir)
            
            self.agent.run(self._build_first_edit_prompt(user_input, self.make_files_prompt(files), information))
            
            end_commit = get_latest_commit_hash()
            if start_commit and end_commit and start_commit != end_commit and user_confirm("检测到多个提交，是否要合并为一个更清晰的提交记录？", False):
                # Reset to start commit
                subprocess.run(["git", "reset", "--soft", start_commit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Create new commit
                git_commiter = GitCommitTool()
                git_commiter.execute({})
                
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

        return f"""
# Code Modification Task

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
