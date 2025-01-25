import subprocess

def get_staged_diff():
    result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
    return result.stdout

def analyze_diff(diff):
    if "fix" in diff.lower() or "bug" in diff.lower():
        return "[修复]"
    elif "optimize" in diff.lower() or "improve" in diff.lower():
        return "[优化]"
    else:
        return "[其他]"

def generate_commit_message(diff):
    tag = analyze_diff(diff)
    return f"{tag} 自动生成的commit信息"

def commit_changes(commit_message):
    subprocess.run(["git", "commit", "-m", commit_message])

if __name__ == "__main__":
    diff = get_staged_diff()
    commit_message = generate_commit_message(diff)
    commit_changes(commit_message)
    print(f"提交成功: {commit_message}")
