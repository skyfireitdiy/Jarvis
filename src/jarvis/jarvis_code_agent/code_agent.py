import os
from typing import List

from jarvis.agent import Agent
from jarvis.jarvis_code_agent.patch import apply_patch
from jarvis.jarvis_code_agent.relevant_files import find_relevant_files
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_file_line_count, get_multiline_input, has_uncommitted_changes, init_env, find_git_root





class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code",
                                 "execute_shell", 
                                 "search", 
                                 "ask_user", 
                                 "ask_codebase", 
                                 "lsp_get_document_symbols", 
                                 "lsp_get_diagnostics", 
                                 "lsp_find_references", 
                                 "lsp_find_definition", 
                                 "lsp_prepare_rename", 
                                 "lsp_validate_edit"])
        code_system_prompt = """
You are a code agent, you are responsible for modifying the code.

You should read the code and analyze the code, and then provide a plan for the code modification.

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

## File Reading Guidelines

1. For Large Files (>200 lines):
- Do NOT read the entire file at once using 'read_code'
- First use 'execute_shell' with grep/find to locate relevant sections
- Then use 'read_code' with specific line ranges to read only necessary portions
- Example: 
  * Use: execute_shell("grep -n 'function_name' path/to/file")
  * Then: read_code("path/to/file", start_line=found_line-10, end_line=found_line+20)

2. For Small Files:
- Can read entire file using 'read_code' directly

## Patch Format and Guidelines

1. Basic Format:
<PATCH>
> /path/to/file start_line,end_line
new_content_line1
new_content_line2
</PATCH>

2. Rules:
- Each <PATCH> block MUST contain exactly ONE patch for ONE location
- Multiple changes to different locations require separate <PATCH> blocks
- Line Numbers Behavior:
  * start_line (first number): This line WILL be replaced
  * end_line (second number): This line will NOT be replaced
  * The patch replaces content from start_line (inclusive) to end_line (exclusive)
- Use absolute paths relative to the project root
- Maintain consistent indentation
- Include enough context for precise location

3. Multiple Changes Example:
Before:
```
Line 0: first line
Line 1: second line
Line 2: third line
Line 3: fourth line
```

For multiple changes, use separate patches:
```
<PATCH>
> /path/to/file 0,1
new first line
</PATCH>

<PATCH>
> /path/to/file 2,3
new third line
</PATCH>
```

After:
```
new first line
Line 1: second line
new third line
Line 3: fourth line
```

Note: In this example:
- Each change is in its own <PATCH> block
- Changes are applied sequentially
- Line numbers are based on the original file

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
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           tool_registry=tool_registry, 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           output_handler_after_tool=[apply_patch],
                           need_summary=False)

    

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
