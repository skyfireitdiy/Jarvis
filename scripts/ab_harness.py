# -*- coding: utf-8 -*-
"""同模型同任务的 Jarvis 提示/壳 A/B 基线。

用法：
    .venv/bin/python scripts/ab_harness.py            # 跑全部任务×全部 profile
    .venv/bin/python scripts/ab_harness.py --only mathx

行为：为每个任务在临时 git 仓库里跑两个 profile 的 CodeAgent（非交互），
记录最终返回、模型消息数/估算 token，写 JSON 报告到 .ab_harness_out/。

注意：使用当前配置的 llm_group；跑一次会真实调用 LLM（有成本）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# 每个任务：starter 文件（相对 task 仓库根）+ 任务描述（给出仓库内路径）
STARTER = {
    "mathx.py": "def add(a, b):\n    return a - b  # bug: 应相加\n",
}
TASKS = {
    "mathx": {
        "files": {"mathx.py": STARTER["mathx.py"]},
        "prompt": (
            "阅读仓库根目录下的 mathx.py。它应提供一个 add(a, b) 返回两数之和，"
            "但当前实现有 bug（返回差而非和）。请修复该函数，并写一个用 pytest 的测试"
            "验证 add(1,2)==3、add(0,0)==0、add(-1,1)==0，运行 pytest 全部通过。"
            "不要改动其他内容，完成后提交。"
        ),
    },
}

# profile = CodeAgent 构造/开关差异（快速 vs 当前默认）
PROFILES = {
    # current: 走默认壳（分类/规则自动加载/方法论等均按配置）
    "current": {"quick_mode": False, "disable_review": True},
    # lean: 跳过 Jarvis 壳的规则/分类/方法论等重流程，尽量接近"轻壳"
    "lean": {"quick_mode": True, "disable_review": True},
}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _make_repo(task_dir: Path, files: dict) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    _git(task_dir, "init", "-q")
    _git(task_dir, "config", "user.email", "jarvis@ab.local")
    _git(task_dir, "config", "user.name", "Jarvis AB")
    for name, content in files.items():
        p = task_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(task_dir, "add", ".")
    _git(task_dir, "commit", "-q", "-m", "init")


def _run_one(
    profile: str, task_key: str, info: dict, out_dir: Path, group: str
) -> dict:
    record = {"profile": profile, "task": task_key, "started": time.time()}
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="jarvis_ab_") as tmp:
        repo = Path(tmp) / "repo"
        _make_repo(repo, info["files"])
        os.chdir(repo)
        try:
            from jarvis.jarvis_code_agent.code_agent import CodeAgent
            from jarvis.jarvis_utils.config import set_llm_group

            set_llm_group(group)
            kw = dict(PROFILES[profile])
            ag = CodeAgent(
                non_interactive=True,
                need_summary=False,
                **kw,
            )
            # 关键：只有 set_non_interactive(True) 才会把 auto_complete 等一并打开，
            # 保证跑完不回到"等待用户输入"，否则会卡住等待 stdin。
            ag.set_non_interactive(True)
            result = ag.run(info["prompt"])
            record["return_type"] = type(result).__name__
            record["return_len"] = len(result) if isinstance(result, str) else -1
            record["result_head"] = (
                (result[:500] + "...") if isinstance(result, str) and len(result) > 500 else result
            )
            try:
                msgs = ag.model.get_messages()
                record["message_count"] = len(msgs)
                chars = sum(
                    len(str(m.get("content", ""))) if isinstance(m, dict) else 0
                    for m in msgs
                )
                record["history_chars"] = chars
            except Exception as e:
                record["history_err"] = str(e)
            try:
                out = subprocess.run(
                    ["git", "-C", str(repo), "log", "--oneline", "-n", "5"],
                    capture_output=True, text=True,
                )
                record["commits"] = out.stdout.strip()
            except Exception as e:
                record["git_err"] = str(e)
        except Exception as e:
            import traceback
            record["error"] = f"{type(e).__name__}: {e}"
            record["traceback"] = traceback.format_exc().splitlines()[-15:]
        finally:
            os.chdir(cwd)
    record["elapsed_s"] = round(time.time() - record.pop("started"), 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{task_key}__{profile}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只跑某个任务 key")
    ap.add_argument("--profile", default=None, help="只跑某个 profile（current/lean）")
    ap.add_argument("--group", default="ds_zn", help="llm_group（需可达），默认 ds_zn=scnet")
    args = ap.parse_args()
    out_dir = ROOT / ".ab_harness_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for task_key, info in TASKS.items():
        if args.only and task_key != args.only:
            continue
        for profile in PROFILES:
            if args.profile and profile != args.profile:
                continue
            r = _run_one(profile, task_key, info, out_dir, group=args.group)
            summary.append(r)
            print(
                f"[{profile}] {task_key}: "
                f"len={r.get('return_len')} msgs={r.get('message_count')} "
                f"err={'YES' if r.get('error') else 'NO'} ({r.get('elapsed_s')}s)"
            )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote .ab_harness_out/summary.json")


if __name__ == "__main__":
    main()
