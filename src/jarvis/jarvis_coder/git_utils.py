import os
from typing import List
import yaml
import time
from jarvis.utils import OutputType, PrettyOutput, while_success
from jarvis.models.registry import PlatformRegistry

def has_uncommitted_files() -> bool:
    """Check if there are uncommitted files in the repository"""
    # Get unstaged modifications
    unstaged = os.popen("git diff --name-only").read()
    # Get staged but uncommitted modifications
    staged = os.popen("git diff --cached --name-only").read()
    # Get untracked files
    untracked = os.popen("git ls-files --others --exclude-standard").read()
    
    return bool(unstaged or staged or untracked)

def generate_commit_message(git_diff: str) -> str:
    """Generate commit message based on git diff and feature description"""
    prompt = f"""You are an experienced programmer, please generate a concise and clear commit message based on the following code changes and feature description:

Code changes:
Git Diff:
{git_diff}

Please follow these rules:
1. Write in English
2. Use conventional commit message format: <type>(<scope>): <subject>
3. Keep it concise, no more than 50 characters
4. Accurately describe the main content of code changes
5. Prioritize feature description and changes in git diff
6. Only generate the commit message text, do not output anything else
"""
    
    model = PlatformRegistry().get_global_platform_registry().get_normal_platform()
    response = model.chat_until_success(prompt)
        
    return ';'.join(response.strip().split("\n"))

def save_edit_record(record_dir: str, commit_message: str, git_diff: str) -> None:
    """Save code modification record"""
    # Get next sequence number
    existing_records = [f for f in os.listdir(record_dir) if f.endswith('.yaml')]
    next_num = 1
    if existing_records:
        last_num = max(int(f[:4]) for f in existing_records)
        next_num = last_num + 1
    
    # Create record file
    record = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commit_message": commit_message,
        "git_diff": git_diff
    }
    
    record_path = os.path.join(record_dir, f"{next_num:04d}.yaml")
    with open(record_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(record, f, allow_unicode=True)
    
    PrettyOutput.print(f"Modification record saved: {record_path}", OutputType.SUCCESS) 