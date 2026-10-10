# -*- coding: utf-8 -*-
"""Commit 工具：把 CodeAgent 产生的 CheckPoint 临时提交压缩为一个正式提交。

CodeAgent 在修改代码的过程中，每次变更都会自动生成一个以 "CheckPoint #N"
开头的临时提交（见 jarvis_utils.git_utils.handle_commit_workflow）。这些临时
提交仅用于过程回退，不应直接进入历史。当需求真正完成时，调用本工具即可：

1. 找到最近的非 CheckPoint 提交作为压缩起点；
2. 若起点之后存在 CheckPoint 临时提交，用 `git reset --soft <起点>` 将它们
   全部压缩到暂存区；
3. 复用 GitCommitTool 基于暂存区差异用 LLM 生成正式的提交信息并提交。

可选参数 prefix / suffix 用于给提交信息添加前缀/后缀。
"""

import subprocess
from typing import Any
from typing import Dict

from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_utils.git_utils import find_recent_non_checkout_commit
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import decode_output


class CommitTool:
    """Commit 工具

    将 CodeAgent 产生的 CheckPoint 临时提交压缩为一个正式提交。
    """

    name = "commit"
    description = (
        "生成真正的 Git 提交。CodeAgent 修改代码时每次变更都会生成一个 "
        "CheckPoint 临时提交（仅用于过程回退）；当需求真正完成时调用本工具，"
        "会自动把这些 CheckPoint 临时提交压缩为一个正式提交（用 LLM 生成提交信息）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prefix": {
                "type": "string",
                "description": "提交信息前缀（可选）。该前缀会被追加到正式提交信息（LLM 生成的主题行）之前；无特殊要求请留空，避免影响提交信息的规范性与可读性。",
            },
            "suffix": {
                "type": "string",
                "description": "提交信息后缀（可选，加在生成信息之后）",
            },
        },
        "required": [],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行压缩 checkpoint 并生成正式提交。"""
        prefix = str((args or {}).get("prefix") or "").strip()
        suffix = str((args or {}).get("suffix") or "").strip()
        agent = (args or {}).get("agent")
        skip_review = bool((args or {}).get("skip_review", False))

        try:
            # 非交互模式下与 review 联动：未禁用 review 且未显式跳过时，先审查再提交。
            # 审查通过才真正 commit；审查发现问题则返回错误，不 commit。
            if (
                not skip_review
                and agent is not None
                and getattr(agent, "non_interactive", False)
                and not getattr(agent, "disable_review", False)
            ):
                review_result = self._run_review(agent)
                if not review_result.get("ok", True):
                    issues = review_result.get("issues", []) or []
                    issues_text = "\n".join(
                        f"{i + 1}. [{issue.get('type', '未知')}] {issue.get('description', '无描述')}"
                        f"\n   位置: {issue.get('location', '未知')}"
                        f"\n   建议: {issue.get('suggestion', '无建议')}"
                        for i, issue in enumerate(issues)
                    )
                    stderr = f"代码审查未通过，已取消提交：\n{issues_text}"
                    if review_result.get("summary"):
                        stderr += f"\n\n审查总结：{review_result['summary']}"
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": stderr,
                    }

            # 1. 找到压缩起点：最近的非 CheckPoint 提交
            start = find_recent_non_checkout_commit()
            current_head = get_latest_commit_hash()

            if not start:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "无法确定压缩起点（未找到任何非 CheckPoint 提交）",
                }

            # 2. 若起点之后存在 CheckPoint 临时提交，压缩它们到暂存区
            if start != current_head:
                PrettyOutput.auto_print(
                    f"ℹ️ 检测到 CheckPoint 临时提交，正在压缩到 {start[:7]} ..."
                )
                result = subprocess.run(
                    ["git", "reset", "--soft", start],
                    capture_output=True,
                    text=False,
                    check=False,
                )
                if result.returncode != 0:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"压缩 checkpoint 失败: {decode_output(result.stderr)}",
                    }

            # 3. 复用 GitCommitTool 生成正式提交（基于暂存区/工作区差异）
            git_commiter = GitCommitTool()
            commit_args: Dict[str, Any] = {}
            if prefix:
                commit_args["prefix"] = prefix
            if suffix:
                commit_args["suffix"] = suffix
            commit_result = git_commiter.execute(commit_args)

            # 4. 提交成功后自动保存当前会话（session），便于后续恢复
            if commit_result.get("success"):
                self._save_session_after_commit(args)

            return commit_result

        except Exception as e:
            PrettyOutput.auto_print(f"❌ Commit 失败\n\n{str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Commit failed: {str(e)}",
            }

    def _run_review(self, agent: Any) -> Dict[str, Any]:
        """非交互联动：执行单次代码审查（复用 CodeReviewer.run_single_review）。

        返回:
            dict: 审查结果，包含 ok/issues/summary 字段
        """
        try:
            from jarvis.jarvis_code_agent.code_reviewer import CodeReviewer

            reviewer = CodeReviewer(
                model=getattr(agent, "model", None),
                start_commit=getattr(agent, "start_commit", None),
                non_interactive=getattr(agent, "non_interactive", True),
                quick_mode=getattr(agent, "quick_mode", False),
            )
            return reviewer.run_single_review()
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 联动审查失败\n\n{str(e)}")
            return {"ok": False, "issues": [], "summary": f"联动审查失败: {str(e)}"}

    def _save_session_after_commit(self, args: Dict[str, Any]) -> None:
        """提交成功后自动保存当前会话，失败不影响提交结果。"""
        try:
            agent = (args or {}).get("agent")
            if agent is None or not hasattr(agent, "save_session"):
                return
            if agent.save_session():
                PrettyOutput.auto_print("💾 已自动保存会话（session）")
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 自动保存会话失败: {e}")
