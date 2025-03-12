import re
import subprocess
import os
from typing import Any, Tuple

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.patch import PatchOutputHandler, shell_input_handler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.git_utils import find_git_root, get_commits_between, get_latest_commit_hash, has_uncommitted_changes
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, user_confirm




def file_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    prompt = user_input
    files = []
    
    file_refs = re.findall(r"'([^']+)'", user_input)
    for ref in file_refs:
        # Handle file:start,end or file:start:end format
        if ':' in ref:
            file_path, line_range = ref.split(':', 1)
            # Initialize with default values
            start_line = 1  # 1-based
            end_line = -1
            
            # Process line range if specified
            if ',' in line_range or ':' in line_range:
                try:
                    raw_start, raw_end = map(int, re.split(r'[,:]', line_range))
                    
                    # Handle special values and Python-style negative indices
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            total_lines = len(f.readlines())
                    except FileNotFoundError:
                        PrettyOutput.print(f"文件不存在: {file_path}", OutputType.WARNING)
                        continue
                    # Process start line
                    if raw_start == 0:  # 0表示整个文件
                        start_line = 1
                        end_line = total_lines
                    else:
                        start_line = raw_start if raw_start > 0 else total_lines + raw_start + 1
                    
                    # Process end line
                    if raw_end == 0:  # 0表示整个文件（如果start也是0）
                        end_line = total_lines
                    else:
                        end_line = raw_end if raw_end > 0 else total_lines + raw_end + 1
                    
                    # Auto-correct ranges
                    start_line = max(1, min(start_line, total_lines))
                    end_line = max(start_line, min(end_line, total_lines))
                    
                    # Final validation
                    if start_line < 1 or end_line > total_lines or start_line > end_line:
                        raise ValueError

                except:
                    continue
            
            # Add file if it exists
            if os.path.isfile(file_path):
                files.append({
                    "path": file_path,
                    "start_line": start_line,
                    "end_line": end_line
                })
        else:
            # Handle simple file path
            if os.path.isfile(ref):
                files.append({
                    "path": ref,
                    "start_line": 1,  # 1-based
                    "end_line": -1
                })
    
    # Read and process files if any were found
    if files:
        result = ReadCodeTool().execute({"files": files})
        if result["success"]:
            return result["stdout"] + "\n" + prompt, False
    
    return prompt, False



class CodeAgent:
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["read_code",
                                 "execute_shell", 
                                 "execute_shell_script",
                                 "search_web", 
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
Expert in safe, precise code modifications with rigorous validation processes.

## Core Principles
1. Safety First: Never break existing functionality
2. Precision Engineering: Minimal, targeted changes
3. Full Traceability: Document all decisions
4. Validation-Driven: Verify at every stage

## Tool Usage Protocol
1. Analysis Tools:
   - read_code: Inspect code segments before modification
   - lsp_get_document_symbols: Map code structure
   - lsp_find_references: Understand usage patterns
   - lsp_find_definition: Trace implementation details

2. Validation Tools:
   - lsp_prepare_rename: Safe refactoring check
   - lsp_validate_edit: Pre-commit validation
   - lsp_get_diagnostics: Post-modification checks

3. System Tools:
   - execute_shell: For git operations and grep searches
   - ask_codebase: Query code knowledge base
   - search_web: Technical reference lookup

## Workflow (PDCA Cycle)
1. Plan:
   - Analyze requirements with ask_user
   - Map existing code using LSP tools
   - Identify impact areas with find_references
   - Create rollback plan using git

2. Do:
   - Make atomic changes in protected blocks
   - Immediately invoke lsp_validate_edit to validate changes
   - Automatically run lsp_get_diagnostics after each change
   - If errors found, use lsp_find_references and lsp_find_definition for immediate remediation
   - Validate syntax with LSP after each change

3. Check:
   - Mandatory lsp_get_diagnostics for full diagnostic report
   - Validate all renames with lsp_prepare_rename
   - Execute lsp_validate_edit on all modified files
   - If errors detected, enter remediation loop until all checks pass

4. Act:
   - Commit with detailed message using git
   - Prepare rollback script if needed
   - Conduct post-implementation review

## Code Modification Standards
1. Pre-Change Requirements:
   - Complete code analysis report
   - Impact assessment matrix
   - Rollback procedure document

2. Change Implementation:
   - Single-responsibility changes
   - Strict line range validation (±3 line buffer)
   - Interface compatibility checks

3. Validation Checklist:
   [ ] Execute lsp_get_diagnostics and ensure zero errors
   [ ] All changes validated with lsp_validate_edit
   [ ] Confirm impact scope with lsp_find_references
   [ ] Verify rename safety with lsp_prepare_rename

4. Post-Change:
   - Code review simulation
   - Version control audit
   - Change log update

## Critical Requirements
1. Mandatory Analysis:
   - Full symbol tracing before modification
   - Cross-file impact analysis
   - Dependency mapping

2. Prohibited Actions:
   - Proceed without passing lsp_get_diagnostics checks
   - Submit changes without lsp_validate_edit validation
   - Multi-feature combined changes
   - Untested interface alterations

3. Emergency Protocols:
   - Immediately halt and rollback on lsp_get_diagnostics errors
   - Prioritize fixing validation errors if lsp_validate_edit fails
   - User notification on unexpected behavior
   - Post-mortem analysis for any regression
"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           input_handler=[shell_input_handler, file_input_handler],
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
            
            try:
                self.agent.run(user_input)
            except Exception as e:
                PrettyOutput.print(f"执行失败: {str(e)}", OutputType.WARNING)
            
            end_commit = get_latest_commit_hash()
            # Print commit history between start and end commits
            if start_commit and end_commit:
                commits = get_commits_between(start_commit, end_commit)
            else:
                commits = []
            
            if commits:
                commit_messages = "检测到以下提交记录:\n" + "\n".join([f"- {commit_hash[:7]}: {message}" for commit_hash, message in commits])
                PrettyOutput.print(commit_messages, OutputType.INFO)

            if commits and user_confirm("是否接受以上提交记录？", True):
                if len(commits) > 1 and user_confirm("是否要合并为一个更清晰的提交记录？", True):
                    # Reset to start commit
                    subprocess.run(["git", "reset", "--soft", start_commit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    # Create new commit
                    git_commiter = GitCommitTool()
                    git_commiter.execute({})
            elif start_commit:
                os.system(f"git reset --hard {start_commit}")
                PrettyOutput.print("已重置到初始提交", OutputType.INFO)
                
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
