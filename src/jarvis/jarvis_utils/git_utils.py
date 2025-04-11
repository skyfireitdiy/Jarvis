"""
Git工具模块
该模块提供了与Git仓库交互的工具。
包含以下功能：
- 查找Git仓库的根目录
- 检查是否有未提交的更改
- 获取两个哈希值之间的提交历史
- 获取最新提交的哈希值
- 从Git差异中提取修改的行范围
"""
import os
import re
import subprocess
from typing import List, Tuple, Dict
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
def find_git_root(start_dir: str = ".") -> str:
    """
    切换到给定路径的Git根目录，如果不是Git仓库则初始化。

    参数:
        start_dir (str): 起始查找目录，默认为当前目录。

    返回:
        str: Git仓库根目录路径。如果目录不是Git仓库，则会初始化一个新的Git仓库。
    """
    os.chdir(start_dir)
    try:
        git_root = os.popen("git rev-parse --show-toplevel").read().strip()
        if not git_root:
            subprocess.run(["git", "init"], check=True)
            git_root = os.path.abspath(".")
    except subprocess.CalledProcessError:
        # 如果不是Git仓库，初始化一个新的
        subprocess.run(["git", "init"], check=True)
        git_root = os.path.abspath(".")
    os.chdir(git_root)
    return git_root
def has_uncommitted_changes() -> bool:
    """检查Git仓库中是否有未提交的更改
    
    返回:
        bool: 如果有未提交的更改返回True，否则返回False
    """
    # 静默添加所有更改
    subprocess.run(["git", "add", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 检查工作目录更改
    working_changes = subprocess.run(["git", "diff", "--exit-code"],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL).returncode != 0

    # 检查暂存区更改
    staged_changes = subprocess.run(["git", "diff", "--cached", "--exit-code"],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL).returncode != 0

    # 静默重置更改
    subprocess.run(["git", "reset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return working_changes or staged_changes
def get_commits_between(start_hash: str, end_hash: str) -> List[Tuple[str, str]]:
    """获取两个提交哈希值之间的提交列表

    参数：
        start_hash: 起始提交哈希值（不包含）
        end_hash: 结束提交哈希值（包含）

    返回：
        List[Tuple[str, str]]: (提交哈希值, 提交信息) 元组列表
    """
    try:
        # 使用git log和pretty格式获取哈希值和信息
        result = subprocess.run(
            ['git', 'log', f'{start_hash}..{end_hash}', '--pretty=format:%H|%s'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False  # 禁用自动文本解码
        )
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='replace')
            PrettyOutput.print(f"获取commit历史失败: {error_msg}", OutputType.ERROR)
            return []

        output = result.stdout.decode('utf-8', errors='replace')
        commits = []
        for line in output.splitlines():
            if '|' in line:
                commit_hash, message = line.split('|', 1)
                commits.append((commit_hash, message))
        return commits

    except Exception as e:
        PrettyOutput.print(f"获取commit历史异常: {str(e)}", OutputType.ERROR)
        return []
def get_latest_commit_hash() -> str:
    """获取当前Git仓库的最新提交哈希值

    返回：
        str: 提交哈希值，如果不在Git仓库、空仓库或发生错误则返回空字符串
    """
    try:
        # 首先检查是否存在HEAD引用
        head_check = subprocess.run(
            ['git', 'rev-parse', '--verify', 'HEAD'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        if head_check.returncode != 0:
            return ""  # 空仓库或无效HEAD

        # 获取HEAD的完整哈希值
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        return result.stdout.decode('utf-8', errors='replace').strip() if result.returncode == 0 else ""
    except Exception:
        return ""
def get_modified_line_ranges() -> Dict[str, Tuple[int, int]]:
    """从Git差异中获取所有更改文件的修改行范围

    返回：
        字典，将文件路径映射到包含修改部分的（起始行, 结束行）范围元组。
        行号从1开始。
    """
    # 获取所有文件的Git差异
    diff_output = os.popen("git show").read()

    # 解析差异以获取修改的文件及其行范围
    result = {}
    current_file = None

    for line in diff_output.splitlines():
        # 匹配类似"+++ b/path/to/file"的行
        file_match = re.match(r"^\+\+\+ b/(.*)", line)
        if file_match:
            current_file = file_match.group(1)
            continue

        # 匹配类似"@@ -100,5 +100,7 @@"的行，其中+部分显示新行
        range_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if range_match and current_file:
            start_line = int(range_match.group(1))  # 保持从1开始
            line_count = int(range_match.group(2)) if range_match.group(2) else 1
            end_line = start_line + line_count - 1
            result[current_file] = (start_line, end_line)

    return result
