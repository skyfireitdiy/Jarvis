"""
关闭一个 Issue。

用途:
- 关闭指定的 issue（写操作，需要已登录 token）。
- 未登录时给出登录提示。

参数:
- number (int): issue 编号（必填）
- repo (str, 可选): 仓库 "owner/repo"，未指定时从当前工作目录解析

返回:
- success (bool)
- stdout (str)
- stderr (str)
"""

from typing import Any
from typing import Dict

from _gh_api import load_api, resolve_repo_arg


class GhCloseIssueTool:
    name = "gh_close_issue"
    description = "关闭一个 GitHub Issue（写操作，需已登录 token）。"
    parameters = {
        "type": "object",
        "properties": {
            "number": {
                "type": "integer",
                "description": "issue 编号",
            },
            "repo": {
                "type": "string",
                "description": "仓库 'owner/repo'，未指定时从当前工作目录解析",
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
        result = api.close_issue(repo=repo, number=args.get("number"))
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error", "未知错误"),
            }
        return {"success": True, "stdout": result.get("message", ""), "stderr": ""}
