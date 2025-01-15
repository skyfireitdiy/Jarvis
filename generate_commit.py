import subprocess

def get_staged_diff():
    result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
    return result.stdout

def analyze_diff(diff):
    # 更详细的分类逻辑
    if "fix" in diff.lower() or "bug" in diff.lower():
        return "[修复]"
    elif "optimize" in diff.lower() or "improve" in diff.lower():
        return "[优化]"
    elif "feat" in diff.lower() or "feature" in diff.lower():
        return "[新增功能]"
    elif "refactor" in diff.lower():
        return "[重构]"
    else:
        return "[其他]"

def extract_key_info(diff):
    # 提取变更文件信息
    lines = diff.splitlines()
    file_changes = set()
    for line in lines:
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            file_path = line.split()[-1]  # 提取文件名
            file_changes.add(file_path)
    if not file_changes:
        return "无文件变更"
    changes_summary = f"涉及文件: {len(file_changes)}个 ({', '.join(file_changes)})"
    return changes_summary

def generate_commit_message(diff):
    tag = analyze_diff(diff)
    key_info = extract_key_info(diff)
    return f"{tag} {key_info}"

def main():
    diff = get_staged_diff()
    if not diff:
        print("暂存区无变更内容")
        return
    commit_message = generate_commit_message(diff)
    print(commit_message)

if __name__ == "__main__":
    main()