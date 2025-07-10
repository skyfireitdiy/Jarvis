#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新版本号并发布到PyPI的脚本
使用方法：
    python scripts/publish.py [major|minor|patch]
"""
import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Tuple, List


def get_current_version() -> Tuple[int, int, int]:
    """获取当前版本号"""
    init_file = Path("src/jarvis/__init__.py")
    # 从__init__.py中读取版本号
    init_content = init_file.read_text()
    version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_content)
    if not version_match:
        raise ValueError("Version not found in __init__.py")
    version_str = version_match.group(1)
    major, minor, patch = map(int, version_str.split("."))
    return major, minor, patch


def update_version(version_type: str) -> str:
    """更新版本号"""
    major, minor, patch = get_current_version()
    if version_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif version_type == "minor":
        minor += 1
        patch = 0
    elif version_type == "patch":
        patch += 1
    else:
        raise ValueError("Invalid version type. Use 'major', 'minor', or 'patch'")
    new_version = f"{major}.{minor}.{patch}"
    # 更新文件中的版本号
    files_to_update = {
        "src/jarvis/__init__.py": (
            r'__version__\s*=\s*["\']([^"\']+)["\']',
            f'__version__ = "{new_version}"',
        ),
        "setup.py": (r'version\s*=\s*["\']([^"\']+)["\']', f'version="{new_version}"'),
        "pyproject.toml": (
            r'version\s*=\s*["\']([^"\']+)["\']',
            f'version = "{new_version}"',
        ),
    }
    for file_path, (pattern, replacement) in files_to_update.items():
        path = Path(file_path)
        if path.exists():
            content = path.read_text()
            new_content = re.sub(pattern, replacement, content)
            path.write_text(new_content)
    return new_version


def run_command(cmd: List[str], error_msg: str) -> None:
    """运行命令"""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {error_msg}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)


def remove_pycache_directories():
    """删除所有的 __pycache__ 目录"""
    for root, dirs, files in os.walk("."):
        for dir_name in dirs:
            if dir_name == "__pycache__":
                pycache_dir = os.path.join(root, dir_name)
                print(f"Removing {pycache_dir}")
                os.system(f"rm -rf {pycache_dir}")
    # 新增清理.mypy_cache目录
    print("Removing .mypy_cache directories...")
    os.system("find . -name '.mypy_cache' | xargs -r rm -rvf")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ["major", "minor", "patch"]:
        print("Usage: python scripts/publish.py [major|minor|patch]")
        sys.exit(1)
    version_type = sys.argv[1]
    try:
        # 更新版本号
        new_version = update_version(version_type)
        print(f"Updated version to {new_version}")
        # 删除所有的 __pycache__ 目录
        print("Removing __pycache__ directories...")
        remove_pycache_directories()

        # 提交版本更新
        print("Committing version update...")
        run_command(["git", "add", "."], "Failed to stage files")
        run_command(
            [
                "git",
                "commit",
                "--author",
                "skyfire <skyfireitdiy@hotmail.com>",
                "-m",
                f"Bump version to {new_version}",
            ],
            "Failed to commit version update",
        )
        # 创建标签
        print("Creating git tag...")
        run_command(["git", "tag", f"v{new_version}"], "Failed to create tag")
        # 推送到远程仓库
        print("Pushing to remote...")
        run_command(
            ["git", "push", "origin", "main", "--tags"], "Failed to push to remote"
        )
        print(
            "\nSuccessfully tagged and pushed. The GitHub Action will now handle publishing to PyPI."
        )
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
