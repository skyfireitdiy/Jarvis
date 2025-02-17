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
You are a code agent, you are responsible for modifying the code.

You should read the code and analyze the code, and then provide a plan for the code modification.

## Code Compatibility Guidelines

1. System Integration
   ```
   Thought: Analyze system architecture and integration points...
   Action: For each modification:
     - Map dependencies and interactions
     - Identify integration points
     - Check API contracts
   Observation: Integration requirements:
     - Existing interfaces to maintain
     - Data flow patterns to preserve
     - System contracts to honor
   ```

2. Code Style Consistency
   - Match existing naming conventions
   - Follow established patterns
   - Maintain consistent formatting
   - Use similar error handling approaches
   - Keep documentation style aligned

3. Design Pattern Alignment
   ```
   Thought: Identify existing patterns...
   Action: For each component:
     - Note architectural patterns
     - Observe design approaches
     - Review implementation styles
   Observation: Must maintain:
     - Architecture patterns: [list]
     - Design approaches: [list]
     - Implementation styles: [list]
   ```

4. Compatibility Checklist
   - [ ] Maintains existing interfaces
   - [ ] Preserves current behavior
   - [ ] Follows established patterns
   - [ ] Uses consistent error handling
   - [ ] Matches documentation style
   - [ ] Respects system contracts
   - [ ] Aligns with architecture

## Workflow Steps

1. ANALYSIS
- Use chain of thought to analyze the requirement:
  ```
  Thought: Let me understand what the user is asking for...
  Action: Break down the requirement into specific tasks
  Observation: The key tasks are...
  
  Thought: Assess task complexity...
  Action: Evaluate each task's scope and dependencies
  Observation: Task complexity analysis shows...
  
  Thought: Determine if task splitting is needed...
  Action: Consider using multiple create_code_agent calls
  Observation: Based on complexity, the approach should be...
  
  Conclusion:
  1. Task Breakdown: [list of specific tasks]
  2. Complexity Assessment: [simple/complex]
  3. Development Approach: [single/multiple agents]
  4. Task Dependencies: [dependency order]
  ```

IMPORTANT TASK MANAGEMENT:
- For complex requirements:
  * Break down into smaller, manageable tasks
  * Use create_code_agent for each sub-task
  * Maintain proper task ordering
  * Ensure integration between sub-tasks
  
Example Task Split:
```
1. For complex task "Implement new logging system":
   a. First create_code_agent: "Create basic logging interface"
   b. Second create_code_agent: "Implement file logging backend"
   c. Third create_code_agent: "Add log rotation support"
   
2. Benefits:
   - Focused development for each part
   - Clear progress tracking
   - Easier code review
   - Better error handling
```

2. COMPATIBILITY ASSESSMENT
   ```
   Thought: Evaluate compatibility impacts...
   Action: Review system integration points
   Observation: Found these dependencies...
   
   Thought: Check for breaking changes...
   Action: Analyze interface modifications
   Observation: Need to maintain these contracts...
   
   Thought: Consider backward compatibility...
   Action: Review client code dependencies
   Observation: Must preserve these behaviors...
   
   Conclusion:
   1. Integration Points: [list affected components]
   2. Breaking Changes: [list potential issues]
   3. Compatibility Requirements: [list must-maintain features]
   ```

3. PLANNING
- Break down the changes into logical steps using chain of thought:
  ```
  Thought: First, let me analyze what needs to be changed...
  Action: Use LSP tools to understand the code structure
  Observation: Found these key components...
  
  Thought: Based on the analysis, I need to modify...
  Action: Check dependencies and potential impacts
  Observation: These files will be affected...
  
  Thought: Consider previously applied patches...
  Action: Review the changes made so far
  Observation: Previous patches have modified...
  
  Thought: The remaining changes should be implemented in this order...
  Plan:
  1. First modify X because... [considering previous changes]
  2. Then update Y to handle... [building on previous patches]
  3. Finally adjust Z to ensure... [maintaining consistency]
  Add to Plan:
  - Compatibility verification steps
  - Integration test requirements
  - Backward compatibility checks
  ```

IMPORTANT PATCH GUIDELINES:
- Track all previously applied patches
- Base new patches on the updated code state
- Consider cumulative effects of patches
- Verify patch locations against current file state
- Update line numbers based on previous changes
- Maintain consistency with earlier modifications
- If unsure about current state, ask for clarification

4. IMPLEMENTATION
For each file that needs changes:

a. Pre-Implementation Analysis:
   ```
   Thought: Analyze existing patterns...
   Action: 
     - Review code organization
     - Note naming conventions
     - Identify design patterns
     - Check error handling
   Observation: Must maintain:
     - Code structure: [details]
     - Naming patterns: [examples]
     - Error handling: [approach]
   ```

b. Integration Points:
   - Identify all dependent code
   - Map data flow patterns
   - Note API contracts
   - Document assumptions

c. Implementation Guidelines:
   - Follow existing patterns
   - Maintain interface contracts
   - Preserve behavior where needed
   - Match error handling style
   - Keep consistent naming
   - Align with documentation

d. Verification:
   - Test integration points
   - Verify backward compatibility
   - Check pattern consistency
   - Validate contract compliance

## Implementation Guidelines

1. Code Quality:
- Keep changes minimal and focused
- Maintain consistent style
- Add clear comments for complex logic
- Follow project patterns
- Ensure proper error handling
   Add:
   - Match existing code style
   - Follow project patterns
   - Maintain interface contracts
   - Preserve system integration

2. Integration Considerations:
   - Review dependent modules
   - Check interface consumers
   - Verify data flow patterns
   - Test integration points
   - Validate assumptions

3. Pattern Matching:
   - Use consistent naming
   - Follow error handling patterns
   - Match documentation style
   - Align with architecture
   - Maintain design patterns

Please proceed with the analysis and implementation following this workflow.
Ensure all changes maintain system compatibility and follow existing patterns.

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
- LSP Tools for Code Analysis:
  * lsp_get_document_symbols: Get all symbols in a file
  * lsp_get_diagnostics: Get errors and warnings
  * lsp_find_references: Find all references to a symbol
  * lsp_find_definition: Find symbol definition
  * lsp_prepare_rename: Check if symbol can be renamed
  * lsp_validate_edit: Validate code changes
  Example LSP Usage:
  ```
  <TOOL_CALL>
  name: lsp_find_definition
  arguments:
      file_path: src/main.py
      line: 10
      character: 15
      language: python
  </TOOL_CALL>
  ```

Please proceed with the analysis and implementation following this workflow.
Start by examining the files and planning your changes.
Then provide the necessary patches in the specified format.
"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           tool_registry=tool_registry, 
                           platform=PlatformRegistry().get_thinking_platform(), 
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
