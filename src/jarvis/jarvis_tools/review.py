# -*- coding: utf-8 -*-
"""Review 工具：对当前代码修改执行单次代码审查。

CodeAgent 在修改代码的过程中，LLM 可在任务执行中主动调用本工具进行代码审查。
本工具执行**单次审查**（复用 CodeReviewer.run_single_review），**不做修复循环**：
发现问题直接返回错误结果，由 Agent（LLM）自行修复后再调用。

非交互模式下与 commit 工具联动：调用 review 工具且审查通过后，会自动接着 commit。
交互模式下不联动，仅执行审查。
"""

from typing import Any
from typing import Dict

from jarvis.jarvis_utils.output import PrettyOutput


class ReviewTool:
    """Review 工具

    对当前代码修改执行单次代码审查，发现问题返回错误结果由 Agent 自行修复。
    """

    name = "review"
    description = (
        "对当前代码修改执行单次代码审查。审查通过返回成功；若发现问题则返回失败"
        "（含问题列表），由你根据问题修复后再调用本工具。非交互模式下审查通过后"
        "会自动接着提交代码。"
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行单次代码审查（工具入口）。"""
        agent = (args or {}).get("agent")

        # disable_review 开启时直接禁用
        if agent is not None and getattr(agent, "disable_review", False):
            return {
                "success": False,
                "stdout": "",
                "stderr": "代码审查已禁用（disable_review 配置开启），跳过审查。",
            }

        try:
            result = self.run_review(agent)

            ok = bool(result.get("ok", True))
            issues = result.get("issues", []) or []
            summary = result.get("summary", "") or ""

            if ok:
                # 审查通过：非交互模式下自动接着 commit（联动）
                if agent is not None and getattr(agent, "non_interactive", False):
                    self._auto_commit(agent)
                return {
                    "success": True,
                    "stdout": summary or "代码审查通过",
                    "stderr": "",
                }

            # 审查发现问题：返回错误结果，由 Agent 自行修复
            issues_text = "\n".join(
                f"{i + 1}. [{issue.get('type', '未知')}] {issue.get('description', '无描述')}"
                f"\n   位置: {issue.get('location', '未知')}"
                f"\n   建议: {issue.get('suggestion', '无建议')}"
                for i, issue in enumerate(issues)
            )
            stderr = f"代码审查发现问题：\n{issues_text}"
            if summary:
                stderr += f"\n\n审查总结：{summary}"
            return {
                "success": False,
                "stdout": "",
                "stderr": stderr,
            }

        except Exception as e:
            PrettyOutput.auto_print(f"❌ Review 失败\n\n{str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Review failed: {str(e)}",
            }

    def run_review(self, agent: Any) -> Dict[str, Any]:
        """执行单次代码审查并返回结构化结果（供 execute 与 <Review> 命令复用）。

        返回:
            dict: 审查结果，包含 ok/issues/summary 字段
        """
        from jarvis.jarvis_code_agent.code_reviewer import CodeReviewer

        # 构造 CodeReviewer（复用 agent 的模型与起始 commit）
        reviewer = CodeReviewer(
            model=getattr(agent, "model", None),
            start_commit=getattr(agent, "start_commit", None),
            non_interactive=getattr(agent, "non_interactive", True),
            quick_mode=getattr(agent, "quick_mode", False),
        )
        return reviewer.run_single_review()

    def _auto_commit(self, agent: Any) -> None:
        """非交互模式下审查通过后自动 commit（联动）。

        复用 CommitTool 的压缩 checkpoint + 正式提交逻辑。
        传入 skip_review=True 跳过 commit 内部的重复审查（本工具刚审查通过）。
        """
        try:
            from jarvis.jarvis_tools.commit import CommitTool

            commit_tool = CommitTool()
            commit_result = commit_tool.execute({"agent": agent, "skip_review": True})
            if commit_result.get("success"):
                PrettyOutput.auto_print("✅ 审查通过，已自动提交代码")
            else:
                PrettyOutput.auto_print(
                    f"⚠️ 审查通过但自动提交失败: {commit_result.get('stderr', '')}"
                )
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 审查通过但自动提交异常: {e}")
