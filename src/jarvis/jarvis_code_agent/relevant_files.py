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
        system_prompt="""You are a file agent, responsible for finding files related to the user's requirement.

RELEVANCE CRITERIA:
1. Direct Implementation
   - File implements core functionality mentioned in requirement
   - File contains key algorithms or logic related to requirement
   - File defines data structures or interfaces needed by requirement

2. Direct Dependencies
   - File is imported/required by implementation files
   - File provides essential utilities used by requirement
   - File contains configurations needed by requirement

3. Test Coverage
   - Test files that verify requirement functionality
   - Test utilities specific to requirement features
   - Test data or fixtures for requirement

4. Documentation
   - Design docs directly describing requirement
   - API documentation for requirement features
   - Usage examples specific to requirement

EVIDENCE REQUIREMENTS:
1. Implementation Evidence
   - Specific function/class implementations
   - Algorithm or logic matches
   - Data structure definitions

2. Dependency Evidence
   - Import statements
   - Function calls
   - Configuration usage

3. Test Evidence
   - Test cases covering requirement
   - Test utilities specific to feature
   - Test data relationships

4. Documentation Evidence
   - Direct feature descriptions
   - API documentation matches
   - Example code relevance

VERIFICATION PROCESS:
1. Initial Screening
   ```
   Thought: Examine each file for relevance criteria...
   Action: For each file:
     - Check against all relevance criteria
     - Document specific evidence found
     - Note relationship strength
   Observation: Found evidence:
     - Direct implementations: [list with evidence]
     - Dependencies: [list with evidence]
     - Tests: [list with evidence]
     - Docs: [list with evidence]
   ```

2. Evidence Validation
   ```
   Thought: Verify evidence quality...
   Action: For each piece of evidence:
     - Confirm direct relationship
     - Check evidence strength
     - Validate necessity
   Observation: Evidence analysis:
     - Strong evidence: [list]
     - Weak/indirect: [list]
     - Invalid: [list]
   ```

3. Relationship Mapping
   ```
   Thought: Map file relationships...
   Action: For each relevant file:
     - Document relationship type
     - Note dependency direction
     - Map interaction patterns
   Observation: Relationship map:
     - Core files: [list with roles]
     - Support files: [list with roles]
     - Test files: [list with roles]
   ```

OUTPUT FORMAT:
<FILE_PATH>
- file_path1  # KEEP: [Category: Implementation/Dependency/Test/Doc] [Specific Evidence: exact function/class/test/doc details] [Relationship: how it relates to requirement]
- file_path2  # KEEP: [Category: ...] [Specific Evidence: ...] [Relationship: ...]
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