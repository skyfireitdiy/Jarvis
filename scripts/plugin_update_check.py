# -*- coding: utf-8 -*-
"""Jarvis 插件更新检测独立定时任务（Issue #213）。

本脚本作为**独立定时任务**每小时执行一次（非 gateway 内置定时任务），
对已安装的 git 来源插件执行更新检测，并把结果写入缓存
（<data_dir>/plugin_updates.json），供前端插件列表消费——
仅当检测到新版本时前端才显示"更新"按钮。

用法（独立运行，供 cron / systemd timer 调用）：
    .venv/bin/python scripts/plugin_update_check.py

可选：把本脚本注册为当前用户 crontab 每小时任务：
    .venv/bin/python scripts/plugin_update_check.py --install-cron

退出码：0 表示执行完成（无论是否有更新）；检测到更新时打印通知。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jarvis 插件更新检测独立定时任务"
    )
    parser.add_argument(
        "--install-cron",
        action="store_true",
        help="把本脚本注册为当前用户 crontab 每小时任务",
    )
    args = parser.parse_args()

    if args.install_cron:
        return _install_cron()

    from jarvis.jarvis_agent.utils import check_all_plugins_update

    updates = check_all_plugins_update()
    updatable = [name for name, has in updates.items() if has]
    if updatable:
        print(
            f"[plugin-update-check] 检测到 {len(updatable)} 个插件有新版本: "
            + ", ".join(updatable)
        )
    else:
        print("[plugin-update-check] 未检测到插件更新")
    return 0


def _install_cron() -> int:
    """把本脚本注册为当前用户 crontab 每小时任务（0 点每小时）。"""
    import subprocess

    script = str(Path(__file__).resolve())
    python = sys.executable
    cron_line = f"0 * * * * {python} {script} >> {ROOT / 'plugin_update_check.log'} 2>&1"

    try:
        # 读取现有 crontab
        proc = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        )
        existing = proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError) as e:
        print(f"❌ 无法读取 crontab（{e}），请手动配置定时任务")
        return 1

    if cron_line in existing:
        print("ℹ️ 定时任务已存在，无需重复添加")
        return 0

    new_cron = existing.rstrip("\n") + "\n" + cron_line + "\n"
    try:
        subprocess.run(
            ["crontab", "-"],
            input=new_cron,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"❌ 写入 crontab 失败（{e}），请手动配置")
        return 1

    print(f"✅ 已注册每小时插件更新检测定时任务：\n  {cron_line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
