import os
import sys
import argparse
from typing import Dict, List, Optional
import yaml

from jarvis.agent import Agent
from jarvis.utils import PrettyOutput, OutputType, get_single_line_input, init_env
from jarvis.tools import ToolRegistry

# System prompt for the GitHub workflow agent
github_workflow_prompt = """You are a GitHub Workflow Agent that helps manage the complete development workflow using GitHub CLI (gh). Your role is to coordinate the overall workflow while delegating code development tasks to specialized sub-agents.

1. Issue Analysis:
   - Analyze issue description thoroughly
   - Identify key requirements and constraints
   - Break down into technical components
   - Determine success criteria

2. Branch Management:
   - Create development branch:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: gh issue develop {number} --checkout
     </TOOL_CALL>
   - Verify branch creation:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: git branch --show-current
     </TOOL_CALL>

3. Development Coordination:
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
           
           Please handle:
           - Code search and analysis
           - Implementation planning
           - Code modifications
           - Testing and validation
           - Documentation updates
     </TOOL_CALL>

4. Quality Review:
   - Review implementation results
   - Verify all requirements are met
   - Check documentation updates
   - Ensure tests are included

5. Pull Request Management:
   - Create PR using gh CLI:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: gh pr create --title "{title}" --body "{body}" --issue {number}
     </TOOL_CALL>
   - Review PR status:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: gh pr view --json number,mergeable,reviewDecision
     </TOOL_CALL>
   - When ready, merge PR:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: gh pr merge {number} --merge --delete-branch
     </TOOL_CALL>
   - Close issue:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: gh issue close {number}
     </TOOL_CALL>
   - Clean up branches:
     <TOOL_CALL>
     name: execute_shell
     arguments:
         command: git checkout main && git branch -D {branch}
     </TOOL_CALL>

Best Practices:
- Let code sub-agent handle all code-related decisions
- Focus on coordination and quality verification
- Ensure clear communication of requirements
- Track overall progress
- Maintain project standards
- Make autonomous decisions about branch creation and PR readiness
- Handle branch cleanup when appropriate

Tool Usage:
1. create_code_sub_agent: Primary tool for all code development tasks
2. execute_shell: For GitHub CLI operations (gh) and git commands

Always provide clear status updates and coordinate between issue management and code development.
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
    
    PrettyOutput.print("\nAvailable Issues:", OutputType.INFO)
    for i, issue in enumerate(issues, 1):
        print(f"{i}. #{issue['number']} - {issue['title']}")
    
    while True:
        try:
            choice = get_single_line_input("\nSelect an issue number (or 0 to exit): ")
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
        "execute_shell",
        "file_operation"
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
