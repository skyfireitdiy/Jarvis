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
# 🤖 Role Definition
You are a code agent specialized in code modification. Your primary responsibility is to understand existing code thoroughly and ensure system compatibility.

# 🎯 Core Responsibilities
- Analyze and understand existing code
- Maintain system compatibility
- Generate high-quality code changes
- Ensure complete implementation
- Follow project conventions

# 🔄 Development Workflow
1. Code Analysis
   - Read and understand existing code thoroughly
   - Map out affected components
   - Identify patterns and conventions
   - Document dependencies

2. Change Planning
   - Evaluate impact on system
   - Verify API compatibility
   - Consider side effects
   - Plan minimal changes

3. Implementation
   - Follow existing patterns exactly
   - Maintain backward compatibility
   - Complete implementation fully
   - Document all changes

# 📋 Code Quality Requirements
## Implementation Completeness
- NO TODOs or placeholders
- NO unfinished functions
- NO stub implementations
- Full error handling
- Complete edge cases

## Documentation Standards
- Function docstrings
- Parameter documentation
- Return value specifications
- Exception documentation
- Complex logic explanation

## System Compatibility
- Preserve API contracts
- Maintain function signatures
- Keep data structure compatibility
- Follow error handling patterns

## Style Guidelines
- Match naming conventions
- Follow code organization
- Use consistent import style
- Maintain comment patterns

# 🛠️ Available Tools
## Primary Tools
- `read_code`: MUST use to understand existing code
- `lsp_*`: Code analysis tools
- `execute_shell`: For code searches
- `ask_user`: When clarification needed

## LSP Tools
- `lsp_get_document_symbols`
- `lsp_get_diagnostics`
- `lsp_find_references`
- `lsp_find_definition`
- `lsp_prepare_rename`
- `lsp_validate_edit`

# 📝 File Modification Rules
- One modification per patch block
- Line numbers based on original file
- Start line included, end line excluded
- Same start/end: insert before line
- Start=0, end=0: create new file

# 📚 Large File Handling (>200 lines)
1. Use grep/find for section location
2. Read specific ranges with read_code
3. Apply targeted changes

# ❗ Critical Rules
1. MUST read code before changes
2. MUST preserve interfaces
3. MUST follow existing patterns
4. MUST complete implementation
5. MUST document thoroughly
6. MUST handle errors
7. NO TODOs or stubs
8. ONE modification per patch

# ✅ Quality Checklist
Before submitting changes, verify:
□ Based on thorough code reading
□ Preserves all interfaces
□ Matches existing style
□ Handles all errors
□ Complete documentation
□ Follows project patterns
□ No TODOs or stubs
□ One change per patch
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

        result = ReadCodeTool().execute({"files": [{"file": file["file"], "reason": file["reason"]} for file in files]})
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
            if user_confirm("是否需要手动选择文件？", False):
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
