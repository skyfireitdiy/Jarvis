# -*- coding: utf-8 -*-
"""Playwright 浏览器驱动安装工具

提供便捷的命令行工具来安装 Playwright 浏览器驱动。
"""

import subprocess
import sys


def install_chromium() -> None:
    """安装 Playwright Chromium 浏览器驱动"""
    print("🔧 正在安装 Playwright Chromium 浏览器驱动...")
    print("这可能需要几分钟时间，请耐心等待...")
    print()

    try:
        # 使用 sys.executable 确保使用正确的 Python 解释器
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )

        print("✅ Playwright Chromium 浏览器驱动安装成功！")
        if result.stdout:
            print(result.stdout)

    except subprocess.CalledProcessError as e:
        print(f"❌ 安装失败，返回码: {e.returncode}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 安装过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    install_chromium()
