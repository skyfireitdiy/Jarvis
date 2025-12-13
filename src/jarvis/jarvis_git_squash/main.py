# -*- coding: utf-8 -*-
import subprocess
from typing import Dict

import typer

from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_utils.globals import get_agent
from jarvis.jarvis_utils.globals import get_current_agent_name
from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.utils import init_env

app = typer.Typer(help="Git压缩工具")


class GitSquashTool:
    name = "git_squash_agent"
    description = "Squash commits interactively using a base commit hash"
    labels = ["git", "version_control", "squash"]

    def _confirm_squash(self) -> bool:
        """Prompt user for confirmation to squash commits"""
        return user_confirm("是否确认压缩提交?", default=True)

    def _reset_to_commit(self, commit_hash: str) -> bool:
        """Perform soft reset to specified commit hash"""
        try:
            subprocess.Popen(
                ["git", "reset", "--mixed", commit_hash],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).wait()
            return True
        except Exception:
            return False

    def execute(self, args: Dict):
        """Execute the squash operation"""
        try:
            if not self._confirm_squash():
                PrettyOutput.auto_print("⚠️ 操作已取消")
                return

            if not self._reset_to_commit(args["commit_hash"]):
                PrettyOutput.auto_print("⚠️ 重置到指定提交失败")
                return

            # Use existing GitCommitTool for new commit
            commit_tool = GitCommitTool()
            agent = get_agent(get_current_agent_name())
            exec_args = {"lang": args.get("lang", "Chinese")}
            if agent:
                exec_args["agent"] = agent
            commit_tool.execute(exec_args)
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 压缩提交失败: {str(e)}")


@app.command()
def cli(
    commit_hash: str = typer.Argument(..., help="要压缩的基础提交哈希"),
    lang: str = typer.Option("Chinese", "--lang", help="提交信息的语言"),
):
    init_env()
    tool = GitSquashTool()
    tool.execute({"commit_hash": commit_hash, "lang": lang})


def main():
    """Application entry point"""
    app()


if __name__ == "__main__":
    main()
