"""
合并一个 Pull Request。

用途:
- 合并指定的 PR（写操作，需要已登录 token）。
- 未登录时给出登录提示。

参数:
- number (int): PR 编号（必填）
- repo (str, 可选): 仓库 "owner/repo"，未指定时从当前工作目录解析
- merge_method (str, 可选): merge / squash / rebase，默认 merge

返回:
- success (bool)
- stdout (str)
- stderr (str)
"""

from typing import Any
from typing import Dict

from _gh_api import load_api, resolve_repo_arg


class GhMergePrTool:
    name = "gh_merge_pr"
    description = "合并一个 GitHub Pull Request（写操作，需已登录 token）。"
    parameters = {
        "type": "object",
        "properties": {
            "number": {
                "type": "integer",
                "description": "PR 编号",
            },
            "repo": {
                "type": "string",
                "description": "仓库 'owner/repo'，未指定时从当前工作目录解析",
            },
            "merge_method": {
                "type": "string",
                "enum": ["merge", "squash", "rebase"],
                "description": "合并方式，默认 merge",
            },
        },
        "required": ["number"],
    }

    @staticmethod
    def check() -> bool:
        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        api = load_api()
        repo, repo_err = resolve_repo_arg(args)
        if repo_err:
            return {"success": False, "stdout": "", "stderr": repo_err}
        result = api.merge_pr(
            repo=repo,
            number=args.get("number"),
            merge_method=args.get("merge_method"),
        )
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error", "未知错误"),
            }
        return {"success": True, "stdout": result.get("message", ""), "stderr": ""}
