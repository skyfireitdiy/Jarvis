"""
Git Utilities Module
This module provides utilities for interacting with Git repositories.
It includes functions for:
- Finding the root directory of a Git repository
- Checking for uncommitted changes
- Retrieving commit history between two hashes
- Getting the latest commit hash
- Extracting modified line ranges from Git diffs
"""
import os
import re
import subprocess
from typing import List, Tuple, Dict
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
def find_git_root(start_dir="."):
    """Change to git root directory of the given path"""
    os.chdir(start_dir)
    git_root = os.popen("git rev-parse --show-toplevel").read().strip()
    os.chdir(git_root)
    return git_root
def has_uncommitted_changes():
    """Check if there are uncommitted changes in the git repository"""
    # Add all changes silently
    subprocess.run(["git", "add", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Check working directory changes
    working_changes = subprocess.run(["git", "diff", "--exit-code"], 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL).returncode != 0
    
    # Check staged changes
    staged_changes = subprocess.run(["git", "diff", "--cached", "--exit-code"], 
                                   stdout=subprocess.DEVNULL, 
                                   stderr=subprocess.DEVNULL).returncode != 0
    
    # Reset changes silently
    subprocess.run(["git", "reset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    return working_changes or staged_changes
def get_commits_between(start_hash: str, end_hash: str) -> List[Tuple[str, str]]:
    """Get list of commits between two commit hashes
    
    Args:
        start_hash: Starting commit hash (exclusive)
        end_hash: Ending commit hash (inclusive)
        
    Returns:
        List[Tuple[str, str]]: List of (commit_hash, commit_message) tuples
    """
    try:
        # Use git log with pretty format to get hash and message
        result = subprocess.run(
            ['git', 'log', f'{start_hash}..{end_hash}', '--pretty=format:%H|%s'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            PrettyOutput.print(f"获取commit历史失败: {result.stderr}", OutputType.ERROR)
            return []
            
        commits = []
        for line in result.stdout.splitlines():
            if '|' in line:
                commit_hash, message = line.split('|', 1)
                commits.append((commit_hash, message))
        return commits
        
    except Exception as e:
        PrettyOutput.print(f"获取commit历史异常: {str(e)}", OutputType.ERROR)
        return []
def get_latest_commit_hash() -> str:
    """Get the latest commit hash of the current git repository
    
    Returns:
        str: The commit hash, or empty string if not in a git repo or error occurs
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except Exception:
        return ""
def get_modified_line_ranges() -> Dict[str, Tuple[int, int]]:
    """Get modified line ranges from git diff for all changed files.
    
    Returns:
        Dictionary mapping file paths to tuple with (start_line, end_line) ranges
        for modified sections. Line numbers are 1-based.
    """
    # Get git diff for all files
    diff_output = os.popen("git show").read()
    
    # Parse the diff to get modified files and their line ranges
    result = {}
    current_file = None
    
    for line in diff_output.splitlines():
        # Match lines like "+++ b/path/to/file"
        file_match = re.match(r"^\+\+\+ b/(.*)", line)
        if file_match:
            current_file = file_match.group(1)
            continue
            
        # Match lines like "@@ -100,5 +100,7 @@" where the + part shows new lines
        range_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if range_match and current_file:
            start_line = int(range_match.group(1))  # Keep as 1-based
            line_count = int(range_match.group(2)) if range_match.group(2) else 1
            end_line = start_line + line_count - 1
            result[current_file] = (start_line, end_line)
    
    return result