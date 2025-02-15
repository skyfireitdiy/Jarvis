from enum import auto
import os
import re
from typing import List

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_code_agent.patch import apply_patch
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_code_agent.relevant_files import find_relevant_files
from jarvis.models.registry import PlatformRegistry
from jarvis.tools.git_commiter import GitCommitTool
from jarvis.tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, get_file_line_count, get_multiline_input, get_single_line_input, has_uncommitted_changes, init_env, find_git_root, is_disable_codebase, make_choice_input, user_confirm





class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code", "execute_shell", "search", "ask_user"])
        code_system_prompt = """
You are a code agent, you are responsible for modifying the code.

You should read the code and analyze the code, and then provide a plan for the code modification.
"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           tool_registry=tool_registry, 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           output_filter=[apply_patch])

    

    def _init_env(self):
        curr_dir = os.getcwd()
        git_dir = find_git_root(curr_dir)
        self.root_dir = git_dir
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute({})

    def _handle_commit_workflow(self)->bool:
        """Handle the git commit workflow and return the commit details.
        
        Returns:
            tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
        """
        if not user_confirm("Do you want to commit the code?", default=True):
            os.system("git reset HEAD")
            os.system("git checkout -- .")
            return False

        git_commiter = GitCommitTool()
        commit_result = git_commiter.execute({})
        return commit_result["success"]

    
    def make_edit_plan(self, user_input: str, files_prompt: str) -> List[str]:
        """Build structured prompts to guide the code modification planning process.
        
        Args:
            user_input: The user's requirement/request
            files_prompt: The formatted list of relevant files
            
        Returns:
            str: A structured prompt for code modification planning
        """

        analysis_prompt = f"""# Code Analysis Phase

## My Requirement
{user_input}

## Available Files
{files_prompt}

## Analysis Steps
Please analyze the requirement and codebase thoroughly before suggesting any changes:

1. Requirement Understanding
- What is the core problem to solve?
- What are the expected outcomes?
- Are there any implicit requirements?
- What constraints need to be considered?

2. Codebase Analysis
- Which parts of the code are relevant?
- How do these components interact?
- What is the current implementation approach?
- What are the key dependencies?

3. Impact Assessment
- What would be affected by changes?
- Are there potential side effects?
- How might this affect other system parts?
- What are the technical constraints?

## Please Provide Your Analysis

### 1. Requirement Analysis
[Analyze the requirement in detail]
- Core objectives
- Success criteria
- Constraints
- Edge cases

### 2. Technical Context
[Describe the relevant technical details]
- Current implementation
- System architecture
- Key components
- Dependencies

### 3. Potential Approaches
[List possible solutions]
- Approach 1: [Description]
  - Pros:
  - Cons:
- Approach 2: [Description]
  - Pros:
  - Cons:

### 4. Recommended Approach
[Explain your recommended solution]
- Why this approach?
- Key benefits
- Risk mitigation

### 5. Implementation Considerations
[List important factors to consider]
- Technical considerations
- Performance impact
- Maintenance aspects
- Testing requirements

DO NOT PROCEED WITH CODE CHANGES YET.
"""

        summary_prompt = f"""# Modification Plan Summary

Based on your previous analysis, please provide a structured summary of the modification plans.
Focus only on the concrete changes needed, using this format:

<PLAN>
file: [primary file to be modified]
relative_files:
  - [related file 1 that might be affected]
  - [related file 2 that might be affected]
modify_plan: [
  Detailed description of the modifications needed:
  - What specific changes are required
  - Which functions/sections need to be modified
  - How the changes affect the overall functionality
  - Any dependencies that need to be considered
  - Implementation sequence if order matters
]
</PLAN>

Guidelines for the plan:
1. Create one <PLAN> block for each main file that needs changes
2. List all related files that might be affected
3. Be specific about what needs to change in each file
4. Include implementation sequence if order matters
5. Focus on concrete changes, not analysis

Example:
<PLAN>
file: src/core/processor.py
relative_files:
  - src/core/utils.py
  - src/core/config.py
modify_plan: Add new processing function process_data() to handle JSON input. 
  - Add input validation in process_data()
  - Update utils.py to add JSON schema validation
  - Modify config.py to include new processing options
  - Ensure backward compatibility with existing processors
</PLAN>

Please provide only the <PLAN> blocks without any additional explanation or analysis.
"""
        self.agent.set_summary_prompt(summary_prompt)
        output = self.agent.run(analysis_prompt)
        while True:
            plan = self._extract_plan(output)
            if plan:
                if user_confirm("Do you want to apply the plan?", default=True):
                    return plan
                else:
                    analysis_prompt = get_multiline_input("Please provide your advice for the code modification. (empty line to exit)")
                    if not analysis_prompt:
                        return []
                    output = self.agent.run(analysis_prompt)
            else:
                analysis_prompt = get_multiline_input("Please provide your advice for the code modification. (empty line to exit)")
                if not analysis_prompt:
                    return []
                output = self.agent.run(analysis_prompt)
        return []
    
    def _extract_plan(self, output: str) -> List[str]:
        """Extract the <PLAN> blocks from the output.
        
        Args:
            output: The output from the agent
            
        Returns:
            List[str]: The <PLAN> blocks
        """
        return re.findall(r'<PLAN>(.*?)</PLAN>', output, re.DOTALL)
    
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

            files_prompt = self.make_files_prompt(files)

            edit_plan = self.make_edit_plan(user_input, files_prompt)
            if not edit_plan:
                return "No edit plan found"
            self._edit_code(edit_plan)
            
        except Exception as e:
            return f"Error during execution: {str(e)}"
        
    def _edit_code(self, edit_plan: List[str]):
        edit_prompt = self._build_first_edit_prompt()
        summary_prompt = """
Summary current code modification.
"""
        self.agent.set_summary_prompt(summary_prompt)
        for plan in edit_plan:
            while True:
                edit_prompt += f"Now you are going to modify the code based on the plan: \n{plan}\n"

                self.agent.run(edit_prompt)

                edit_prompt = ""

                if not has_uncommitted_changes():
                    user_feedback = make_choice_input(
                        "Please input your feedback for the code modification. (empty line to exit)",
                        ["retry", "skip", "abort"]
                    )
                    if user_feedback == "abort":
                        return "Task cancelled by user"
                    if user_feedback == "skip":
                        edit_prompt += "Skip this modification plan."
                        break
                    if user_feedback == "retry":
                        more_info = get_multiline_input("Please provide more information for the code modification. (empty line to exit)")
                        if not more_info:
                            return "Task cancelled by user"
                        edit_prompt = more_info
                        continue
                else:
                    if not self._handle_commit_workflow():
                        user_feedback = make_choice_input(
                            "Please input your feedback for the code modification. (empty line to exit)",
                            ["retry", "skip", "abort"]
                        )
                        if user_feedback == "abort":
                            return "Task cancelled by user"
                        if user_feedback == "retry":
                            more_info = get_multiline_input("Please provide more information for the code modification. (empty line to exit)")
                            if not more_info:
                                return "Task cancelled by user"
                            edit_prompt = more_info
                            continue
                        else:
                            edit_prompt += "Skip this modification plan."
                            break

    def _build_first_edit_prompt(self) -> str:
        """Build the initial prompt for the agent.
        
        Args:
            user_input: The user's requirement
            files_prompt: The formatted list of relevant files
            
        Returns:
            str: The formatted prompt
        """
        return f"""
        Now you are going to modify the code based on the plan. use the following format to output the patch:
        <PATCH>
        > /path/to/file 1,2
        content_line1
        content_line2
        </PATCH>

        Notes:
        - The patch replaces content from start_line (will replace this line) to end_line (will not replace this line)
        - Example:
    
        Before:
        ```
        content_line1
        content_line2
        ```

        Patch:
        ```
        <PATCH>
        > /path/to/file 1,2
        content_line1
        content_line2
        </PATCH>
        ```
        
        After:
        ```
        content_line1
        content_line2
        content_line2
        ```

        - You can output multiple patches, use multiple <PATCH> blocks
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
