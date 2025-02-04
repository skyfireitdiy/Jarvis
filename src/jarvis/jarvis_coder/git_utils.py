import os
from typing import List
import yaml
import time
from jarvis.utils import OutputType, PrettyOutput
from jarvis.models.registry import PlatformRegistry
from .model_utils import call_model_with_retry

def has_uncommitted_files() -> bool:
    """判断代码库是否有未提交的文件"""
    # 获取未暂存的修改
    unstaged = os.popen("git diff --name-only").read()
    # 获取已暂存但未提交的修改
    staged = os.popen("git diff --cached --name-only").read()
    # 获取未跟踪的文件
    untracked = os.popen("git ls-files --others --exclude-standard").read()
    
    return bool(unstaged or staged or untracked)

def generate_commit_message(git_diff: str, feature: str) -> str:
    """根据git diff和功能描述生成commit信息"""
    prompt = f"""你是一个经验丰富的程序员，请根据以下代码变更和功能描述生成简洁明了的commit信息：

功能描述：
{feature}

代码变更：
Git Diff:
{git_diff}

请遵循以下规则：
1. 使用英文编写
2. 采用常规的commit message格式：<type>(<scope>): <subject>
3. 保持简洁，不超过50个字符
4. 准确描述代码变更的主要内容
5. 优先考虑功能描述和git diff中的变更内容
"""
    
    model = PlatformRegistry().get_global_platform_registry().get_codegen_platform()
    success, response = call_model_with_retry(model, prompt)
    if not success:
        return "Update code changes"
        
    return response.strip().split("\n")[0]

def save_edit_record(record_dir: str, commit_message: str, git_diff: str) -> None:
    """保存代码修改记录"""
    # 获取下一个序号
    existing_records = [f for f in os.listdir(record_dir) if f.endswith('.yaml')]
    next_num = 1
    if existing_records:
        last_num = max(int(f[:4]) for f in existing_records)
        next_num = last_num + 1
    
    # 创建记录文件
    record = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commit_message": commit_message,
        "git_diff": git_diff
    }
    
    record_path = os.path.join(record_dir, f"{next_num:04d}.yaml")
    with open(record_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(record, f, allow_unicode=True)
    
    PrettyOutput.print(f"已保存修改记录: {record_path}", OutputType.SUCCESS) 