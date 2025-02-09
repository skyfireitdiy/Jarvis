import os
from typing import List
import yaml
import time
from jarvis.utils import OutputType, PrettyOutput, find_git_root, while_success
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


def init_git_repo(root_dir: str) -> str:
    git_dir = find_git_root(root_dir)
    if not git_dir:
        git_dir = root_dir

    PrettyOutput.print(f"Git root directory: {git_dir}", OutputType.INFO)

    # 1. Check if the code repository path exists, if it does not exist, create it
    if not os.path.exists(git_dir):
        PrettyOutput.print(
            "Root directory does not exist, creating...", OutputType.INFO)
        os.makedirs(git_dir)

    os.chdir(git_dir)

    # 3. Process .gitignore file
    gitignore_path = os.path.join(git_dir, ".gitignore")
    gitignore_modified = False
    jarvis_ignore_pattern = ".jarvis-*"

    # 3.1 If .gitignore does not exist, create it
    if not os.path.exists(gitignore_path):
        PrettyOutput.print("Create .gitignore file", OutputType.INFO)
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(f"{jarvis_ignore_pattern}\n")
        gitignore_modified = True
    else:
        # 3.2 Check if it already contains the .jarvis-* pattern
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 3.2 Check if it already contains the .jarvis-* pattern
        if jarvis_ignore_pattern not in content.split("\n"):
            PrettyOutput.print("Add .jarvis-* to .gitignore", OutputType.INFO)
            with open(gitignore_path, "a", encoding="utf-8") as f:
                # Ensure the file ends with a newline
                if not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{jarvis_ignore_pattern}\n")
            gitignore_modified = True

    # 4. Check if the code repository is a git repository, if not, initialize the git repository
    if not os.path.exists(os.path.join(git_dir, ".git")):
        PrettyOutput.print("Initialize Git repository", OutputType.INFO)
        os.system("git init")
        os.system("git add .")
        os.system("git commit -m 'Initial commit'")
    # 5. If .gitignore is modified, commit the changes
    elif gitignore_modified:
        PrettyOutput.print("Commit .gitignore changes", OutputType.INFO)
        os.system("git add .gitignore")
        os.system("git commit -m 'chore: update .gitignore to exclude .jarvis-* files'")
    # 6. Check if there are uncommitted files in the code repository, if there are, commit once
    elif has_uncommitted_files():
        PrettyOutput.print("Commit uncommitted changes", OutputType.INFO)
        os.system("git add .")
        git_diff = os.popen("git diff --cached").read()
        commit_message = generate_commit_message(git_diff)
        os.system(f"git commit -m '{commit_message}'")
    return git_dir