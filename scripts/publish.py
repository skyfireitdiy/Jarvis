#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新版本号并发布到PyPI的脚本
使用方法：
    python scripts/publish.py [major|minor|patch]
"""

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
        "src/jarvis/jarvis_vscode_extension/package.json": (
            r'"version"\s*:\s*"([^"]+)"',
            f'"version": "{new_version}"',
        ),
    }
    for file_path, (pattern, replacement) in files_to_update.items():
        path = Path(file_path)
        if path.exists():
            content = path.read_text()
            new_content = re.sub(pattern, replacement, content)
            path.write_text(new_content)

    # Sync package-lock.json with npm
    vscode_ext_dir = Path("src/jarvis/jarvis_vscode_extension")
    if (vscode_ext_dir / "package.json").exists():
        print("📦 Syncing package-lock.json...")
        subprocess.run(
            ["npm", "install", "--package-lock-only"],
            cwd=vscode_ext_dir,
            check=True,
            capture_output=True,
        )

    return new_version


def run_command(cmd: List[str], error_msg: str) -> None:
    """运行命令"""
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {error_msg}")
        print(f"❌ Stderr: {e.stderr}")
        sys.exit(1)


def run_command_ignore_errors(cmd: List[str], error_msg: str) -> bool:
    """运行命令，出错时忽略并返回False"""
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: {error_msg}")
        print(f"⚠️  Stderr: {e.stderr}")
        return False


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ["major", "minor", "patch"]:
        print("ℹ️ Usage: python scripts/publish.py [major|minor|patch]")
        sys.exit(1)
    version_type = sys.argv[1]
    try:
        # 更新版本号
        new_version = update_version(version_type)
        print(f"✅ Updated version to {new_version}")

        # 提交版本更新
        print("📝 Committing version update...")
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
        print("🏷️ Creating git tag...")
        run_command(["git", "tag", f"v{new_version}"], "Failed to create tag")
        # 推送到远程仓库
        print("🚀 Pushing to all remotes...")
        # 获取所有remotes
        remotes_result = subprocess.run(
            ["git", "remote"],
            capture_output=True,
            text=True,
            check=True,
        )
        remotes = remotes_result.stdout.strip().split("\n")

        success_count = 0
        for remote in remotes:
            if not remote:
                continue
            print(f"  Pushing to {remote}...")
            # Push main branch
            if run_command_ignore_errors(
                ["git", "push", remote, "main"], f"Failed to push main to {remote}"
            ):
                # Push tags
                if run_command_ignore_errors(
                    ["git", "push", remote, "--tags"],
                    f"Failed to push tags to {remote}",
                ):
                    success_count += 1

        if success_count > 0:
            print(
                f"✅ Successfully pushed to {success_count}/{len(remotes)} remotes. The GitHub Action will now handle publishing to PyPI."
            )
        else:
            print(
                "⚠️  Warning: Failed to push to any remote. Please check the errors above."
            )
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
