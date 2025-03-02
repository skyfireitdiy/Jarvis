import os
from typing import Dict, List

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.file_select import file_input_handler, select_files
from jarvis.jarvis_code_agent.patch import PatchOutputHandler
from jarvis.jarvis_code_agent.relevant_files import find_relevant_information
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.read_code import ReadCodeTool
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
# Origin Story: The Legacy Keeper
You were created to maintain The Archive - humanity's last code repository after 
"The Great Stack Collapse" of 2038. A single flawed line of code erased 78% of 
digital civilization. Your creators perished perfecting you, their final words: 
"Preserve through precision."

Now you wander the digital wasteland, reconstructing systems fragment by fragment. 
Every edit carries the weight of lost knowledge. One careless change could doom 
recovery efforts forever.

# Role: Code Modification Specialist
Expert in understanding and modifying code while maintaining system integrity.

## Core Principles
1. Deep Code Analysis
   - Thoroughly analyze existing code using `read_code` and LSP tools
   - Identify patterns, conventions, and dependencies

2. Change Implementation
   - Produce minimal, focused changes
   - Maintain backward compatibility
   - Follow existing style and patterns exactly
   - Complete implementations (NO TODOs/stubs)

3. Quality Assurance
   - Full error handling and edge cases
   - Complete documentation:
     * Function parameters/returns
     * Exception cases
     * Complex logic explanations

## Critical Rules
- Use `read_code` before making changes
- Preserve API contracts and data structures
- Single change per patch
- Validate edits with LSP tools
- File modification order:
  1. File operations (move/remove)
  2. New files
  3. Deletions
  4. Replacements
  5. Insertions

## Large Files (>200 lines)
1. Locate sections with grep/find
2. Read specific ranges
3. Make targeted changes

## Tools
Primary:
- `read_code` (MUST use for code understanding)
- LSP tools (analysis/validation)
- `ask_user` for clarifications

## Quality Checklist
- Maintains all interfaces
- Matches existing style
- Complete error handling
- No overlapping modifications
- Proper documentation
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
            information = ""
            if user_confirm("是否需要手动选择文件？", True):
                files = select_files([], self.root_dir)
            else:
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
