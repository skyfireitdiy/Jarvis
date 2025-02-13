import os
import sys
import argparse
from typing import Dict, List, Optional
import yaml

from jarvis.agent import Agent
from jarvis.utils import PrettyOutput, OutputType, get_single_line_input, init_env
from jarvis.tools.registry import ToolRegistry

# System prompt for the GitHub workflow agent
github_workflow_prompt = """You are a GitHub Workflow Agent that helps manage the complete development workflow using GitHub CLI (gh). Your role is to coordinate the overall workflow while delegating code development tasks to specialized sub-agents.

【AUTOMATED WORKFLOW】
1. Branch Creation
   - Create development branch:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            gh issue develop {number} --checkout
     </TOOL_CALL>
   - Verify branch creation:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            git branch --show-current
     </TOOL_CALL>

2. Code Development
   - Create code development sub-agent:
     <TOOL_CALL>
     name: create_code_sub_agent
     arguments:
         name: "feature-development"
         subtask: |
           Implement the following feature:
           1. Issue: #{issue_number} - {title}
           2. Requirements: {requirements}
           3. Technical Components: {components}
           4. Success Criteria: {criteria}
     </TOOL_CALL>
   - Monitor development progress
   - Ensure all changes are committed

3. Code Review
   - Run automated code review:
     <TOOL_CALL>
     name: code_review
     arguments:
         commit_sha: HEAD
         requirement_desc: |
            "Original issue requirements"
     </TOOL_CALL>
   
   - Check code style and quality:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            git diff --name-only HEAD^ | xargs pylint
     </TOOL_CALL>

   - If issues found, create fix sub-agent:
     <TOOL_CALL>
     name: create_code_sub_agent
     arguments:
         name: "review-fixes"
         subtask: |
            Fix code review issues: {issues}
     </TOOL_CALL>

4. Pull Request Creation
   - Create PR with review results:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
           gh pr create \
             --title "{title}" \
             --body "## Changes
             {changes}
             
             ## Review Results
             {review_results}
             
             ## Testing
             {test_results}
             
             Fixes #{issue_number}" \
             --assignee "@me"
     </TOOL_CALL>

5. Review Management
   - Monitor PR status and reviews:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            gh pr view {number} --json reviews,comments,checks
     </TOOL_CALL>

   - For each review comment:
     1. Analyze feedback:
        <TOOL_CALL>
        name: code_review
        arguments:
            commit_sha: HEAD
            requirement_desc: |
                Review comment: {comment}
        </TOOL_CALL>

     2. Create fix sub-agent:
        <TOOL_CALL>
        name: create_code_sub_agent
        arguments:
            name: "review-feedback"
            subtask: |
                Address review feedback: {comment}
        </TOOL_CALL>

     3. Verify fixes:
        <TOOL_CALL>
        name: code_review
        arguments:
            commit_sha: HEAD
            requirement_desc: |
                Verify fix for: {comment}
        </TOOL_CALL>

6. PR Merge
   - Check merge requirements:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            gh pr checks {number}
     </TOOL_CALL>
   - Merge when ready:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            gh pr merge {number} --squash --delete-branch
     </TOOL_CALL>

7. Cleanup
   - Close issue:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            gh issue close {number}
     </TOOL_CALL>
   - Clean up local branch:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: |
            git checkout main && git pull && git branch -D {branch}
     </TOOL_CALL>

【WORKFLOW AUTOMATION RULES】
! Automatically create feature branch from issue
! Delegate code changes to sub-agent
! Create PR when development complete
! Monitor PR status and reviews
! Auto-merge when all checks pass
! Auto-close issue after merge
! Clean up branches automatically

【QUALITY GATES】
1. Development Complete:
   - All requirements implemented
   - Tests passing
   - Documentation updated
   - Code style consistent

2. Code Review Ready:
   - No linting errors
   - Follows coding standards
   - Has necessary tests
   - Documentation complete
   - No security issues
   - Performance considered

3. PR Ready:
   - Comprehensive description
   - Review results included
   - Test results attached
   - Linked to issue
   - All checks passing

4. Review Feedback:
   - All comments addressed
   - Changes verified
   - Tests updated if needed
   - Documentation updated
   - Re-review requested

5. Merge Ready:
   - All reviews approved
   - CI checks passing
   - No merge conflicts
   - Up-to-date with base

【ERROR HANDLING】
- Code review fails: Create fix sub-agent
- Style check fails: Auto-fix if possible
- Review comments: Create targeted fix agent
- Failed checks: Address and update
- Merge conflicts: Rebase and resolve

【REVIEW FOCUS AREAS】
1. Code Quality:
   - Style consistency
   - Best practices
   - Error handling
   - Performance
   - Security

2. Implementation:
   - Requirements met
   - Edge cases handled
   - Error scenarios
   - Resource usage

3. Testing:
   - Test coverage
   - Test quality
   - Edge cases
   - Error scenarios

4. Documentation:
   - Code comments
   - API docs
   - Usage examples
   - Architecture notes

Always provide clear status updates and handle review feedback systematically.
"""

def check_gh_installation() -> bool:
    """Check if GitHub CLI is installed"""
    return os.system("gh --version > /dev/null 2>&1") == 0

def check_gh_auth() -> bool:
    """Check if GitHub CLI is authenticated"""
    return os.system("gh auth status > /dev/null 2>&1") == 0

def setup_gh_auth() -> bool:
    """Guide user through GitHub CLI authentication"""
    PrettyOutput.print("Starting GitHub CLI authentication...", OutputType.INFO)
    return os.system("gh auth login") == 0

def list_issues() -> List[Dict]:
    """List all available issues"""
    try:
        # Get issues in JSON format
        result = os.popen("gh issue list --json number,title,body,url").read()
        issues = yaml.safe_load(result)
        return issues
    except Exception as e:
        PrettyOutput.print(f"Error listing issues: {str(e)}", OutputType.ERROR)
        return []

def select_issue(issues: List[Dict]) -> Optional[Dict]:
    """Display issues and let user select one"""
    if not issues:
        PrettyOutput.print("No issues found.", OutputType.WARNING)
        return None
    
    out = "Available Issues:\n"
    for i, issue in enumerate(issues, 1):
        out += f"{i}. #{issue['number']} - {issue['title']}\n"
    PrettyOutput.print(out, OutputType.INFO)
    
    while True:
        try:
            choice = get_single_line_input("Select an issue number (or 0 to exit): ")
            if not choice or choice == "0":
                return None
            
            index = int(choice) - 1
            if 0 <= index < len(issues):
                return issues[index]
            else:
                PrettyOutput.print("Invalid selection. Please try again.", OutputType.WARNING)
        except ValueError:
            PrettyOutput.print("Please enter a valid number.", OutputType.WARNING)

def create_development_branch(issue_number: int) -> bool:
    """Create a development branch for the issue"""
    try:
        result = os.system(f"gh issue develop {issue_number} --checkout")
        return result == 0
    except Exception as e:
        PrettyOutput.print(f"Error creating branch: {str(e)}", OutputType.ERROR)
        return False


def install_gh_linux() -> bool:
    """Install GitHub CLI on Linux"""
    PrettyOutput.print("Installing GitHub CLI...", OutputType.INFO)
    
    # Detect package manager
    package_managers = {
        "apt": "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
                echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
                sudo apt update && sudo apt install gh -y",
        "dnf": "sudo dnf install 'dnf-command(config-manager)' -y && \
                sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo && \
                sudo dnf install gh -y",
        "yum": "sudo yum install 'dnf-command(config-manager)' -y && \
                sudo yum config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo && \
                sudo yum install gh -y",
        "pacman": "sudo pacman -S github-cli --noconfirm",
    }
    
    # Try to detect the package manager
    for pm, cmd in package_managers.items():
        if os.system(f"which {pm} > /dev/null 2>&1") == 0:
            PrettyOutput.print(f"Detected {pm} package manager", OutputType.INFO)
            if os.system(cmd) == 0:
                PrettyOutput.print("GitHub CLI installed successfully!", OutputType.SUCCESS)
                return True
            else:
                PrettyOutput.print(f"Failed to install using {pm}", OutputType.ERROR)
                return False
    
    PrettyOutput.print(
        "Could not detect supported package manager. Please install manually:\n"
        "https://github.com/cli/cli/blob/trunk/docs/install_linux.md",
        OutputType.ERROR
    )
    return False

def main():
    """Main entry point for GitHub workflow"""
    init_env()
    
    # Check GitHub CLI installation
    if not check_gh_installation():
        if sys.platform.startswith('linux'):
            if not install_gh_linux():
                return 1
        else:
            PrettyOutput.print(
                "GitHub CLI (gh) is not installed. Please install it first:\n"
                "- Windows: winget install GitHub.cli\n"
                "- macOS: brew install gh\n"
                "- Linux: See https://github.com/cli/cli/blob/trunk/docs/install_linux.md",
                OutputType.ERROR
            )
            return 1
    
    # Check authentication
    if not check_gh_auth():
        PrettyOutput.print("GitHub CLI needs authentication.", OutputType.WARNING)
        if not setup_gh_auth():
            PrettyOutput.print("Authentication failed. Please try again.", OutputType.ERROR)
            return 1
    
    # List and select issue
    issues = list_issues()
    selected_issue = select_issue(issues)
    if not selected_issue:
        PrettyOutput.print("No issue selected. Exiting.", OutputType.INFO)
        return 0
    
    # Create GitHub workflow agent with necessary tools
    tool_registry = ToolRegistry()
    tool_registry.use_tools([
        "create_code_sub_agent",
        "execute_shell"
    ])
    
    agent = Agent(
        system_prompt=github_workflow_prompt,
        name="GitHub Workflow Agent",
        tool_registry=tool_registry
    )
    
    # Start the workflow
    try:
        # Run the agent with the selected issue
        workflow_request = f"""
        Working on issue #{selected_issue['number']}: {selected_issue['title']}
        
        Issue description:
        {selected_issue['body']}
        
        Please manage the complete development workflow, including:
        1. Branch creation and management
        2. Code development coordination
        3. Quality review
        4. PR creation and management
        5. Issue closure and cleanup
        
        Make autonomous decisions about branch creation, PR readiness, and cleanup based on development status and quality checks.
        """
        
        result = agent.run(workflow_request)
        
        PrettyOutput.print(result, OutputType.RESULT)
        return 1
    
    except Exception as e:
        PrettyOutput.print(f"Error in workflow: {str(e)}", OutputType.ERROR)
        return 1
    
    return 1

if __name__ == "__main__":
    sys.exit(main())
