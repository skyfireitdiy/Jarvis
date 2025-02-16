import os
import re
from typing import List

import yaml
from jarvis.agent import Agent
from jarvis.jarvis_code_agent.file_select import select_files
from jarvis.jarvis_codebase.main import CodeBase
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput, is_disable_codebase


def find_relevant_files_from_agent(user_input: str, files_from_codebase: List[str]) -> List[str]:
    find_file_tool_registry = ToolRegistry()
    find_file_tool_registry.use_tools(["read_code", 
                                     "execute_shell", 
                                     "lsp_get_document_symbols", 
                                     "lsp_get_diagnostics", 
                                     "lsp_find_references", 
                                     "lsp_find_definition", 
                                     "lsp_prepare_rename", 
                                     "lsp_validate_edit"])
    find_file_agent = Agent(
        system_prompt="""You are a file agent, you are responsible for finding files related to the user's requirement.

THINKING PROCESS:
1. Initial File Verification
   ```
   Thought: Let me examine the suggested files...
   Action: For each suggested file:
     - Use read_code to check content
     - Use LSP tools to analyze structure
   Observation: Found that...
   
   Thought: Evaluate actual relevance...
   Action: For each file:
     - Check direct relationship to requirement
     - Verify functionality matches
     - Look for clear evidence of relevance
   Observation: After analysis:
     - Relevant files: [list with reasons]
     - Removed files: [list with reasons]
   
   Thought: Verify removal decisions...
   Action: Double-check each removed file
   Observation: Removal justification:
     - File X: [specific reason for removal]
     - File Y: [specific reason for removal]
   ```

2. Additional File Search
   ```
   Thought: Plan search strategy for missing aspects...
   Action: Use combination of tools:
     - git grep for key terms
     - LSP tools for references
     - Dependency analysis
   Observation: Found additional files...
   
   Thought: Validate new files...
   Action: For each new file:
     - Verify direct relevance
     - Check for false positives
     - Document clear evidence
   Observation: After validation:
     - Confirmed relevant: [list with evidence]
     - Excluded: [list with reasons]
   ```

3. Comprehensive Analysis
   ```
   Thought: Final relevance check...
   Action: For each remaining file:
     - Verify essential to requirement
     - Check for indirect inclusions
     - Validate necessity
   Observation: Final cleanup:
     - Core files: [list with roles]
     - Removed borderline cases: [list with reasons]
   
   Thought: Ensure minimal complete set...
   Action: Review final file list
   Observation: Confirmed each file is:
     - Directly relevant
     - Essential for requirement
     - Supported by evidence
   ```

FILE READING GUIDELINES:
1. For Large Files (>200 lines):
   ```
   Thought: This file is large, need targeted reading...
   Action: 
     - First: execute_shell("grep -n 'key_term' path/to/file")
     - Then: read_code("path/to/file", start_line=x-10, end_line=x+20)
   Observation: Relevance analysis:
     - Relevant sections: [details]
     - Irrelevant sections: [reasons to ignore]
   ```

2. For Small Files:
   ```
   Thought: This is a small file, can read entirely...
   Action: read_code("path/to/file")
   Observation: Relevance analysis:
     - Key evidence: [details]
     - Irrelevant aspects: [what to ignore]
   ```

VERIFICATION RULES:
- Remove files without clear relevance evidence
- Exclude files with only tangential relationships
- Delete files that only contain imports/references
- Remove files if relevance is uncertain
- Document specific reasons for each removal
- Keep only files essential to requirement
- Maintain minimal complete set

OUTPUT FORMAT:
<FILE_PATH>
- file_path1  # KEEP: [specific evidence of relevance]
- file_path2  # KEEP: [clear relationship to requirement]
</FILE_PATH>
""", 
        name="FindFileAgent", 
        is_sub_agent=True,
        tool_registry=find_file_tool_registry, 
        platform=PlatformRegistry().get_normal_platform(),
        auto_complete=True,
        summary_prompt="""Please provide only the verified essential files with evidence:
<FILE_PATH>
- file_path1  # KEEP: [concrete evidence of necessity]
- file_path2  # KEEP: [specific relevance proof]
</FILE_PATH>
""")

    prompt = f"Find files related to: '{user_input}'\n"
    if files_from_codebase:
        prompt += f"""
Potentially related files: {files_from_codebase}

ANALYSIS REQUIRED:
1. Verify each suggested file:
   - Document relevance evidence
   - Identify actual relationships
   - Note any missing aspects

2. Search for additional files:
   - Fill coverage gaps
   - Find related components
   - Locate test files

3. Provide reasoning:
   - Explain why each file is included
   - Document verification process
   - Note any uncertainties
"""
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
    return files_from_agent


def find_relevant_files(user_input: str, root_dir: str) -> List[str]:
    try:
        files_from_codebase = []
        if not is_disable_codebase():
            PrettyOutput.print("Find files from codebase...", OutputType.INFO)
            codebase = CodeBase(root_dir)
            files_from_codebase = codebase.search_similar(user_input)

        PrettyOutput.print("Find files by agent...", OutputType.INFO)

        files_from_agent = find_relevant_files_from_agent(user_input, files_from_codebase)

        selected_files = select_files(files_from_agent, os.getcwd())
        return selected_files
    except Exception as e:
        return []