"""
列出 GitHub 仓库的 Pull Requests。

用途:
- 列出当前仓库（未指定时从当前工作目录解析）的 pull requests。
- 可按状态过滤：open（默认）/ closed / all。

参数:
- state (str, 可选): open / closed / all，默认 open
- repo (str, 可选): 仓库 "owner/repo"，未指定时从当前工作目录解析

返回:
- success (bool)
- stdout (str): JSON 文本，含 PR 列表（每个含 number/title/state/user/created_at）
- stderr (str)
"""

import json
from typing import Any
from typing import Dict

from _gh_api import load_api, resolve_repo_arg


class GhListPrsTool:
    name = "gh_list_prs"
    description = "列出 GitHub 仓库的 Pull Requests（默认 open 状态）。"
    parameters = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "PR 状态过滤，默认 open",
            },
            "repo": {
                "type": "string",
                "description": "仓库 'owner/repo'，未指定时从当前工作目录解析",
            },
        },
    }

    @staticmethod
    def check() -> bool:
        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        api = load_api()
        repo, repo_err = resolve_repo_arg(args)
        if repo_err:
            return {"success": False, "stdout": "", "stderr": repo_err}
        result = api.list_prs(repo=repo, state=args.get("state"))
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error", "未知错误"),
            }
        data = result.get("data") or []
        repo = result.get("repo", "")
        state = result.get("state", "")
        summary = f"仓库 {repo} 共 {len(data)} 个 PR（state={state}）"
        return {
            "success": True,
            "stdout": summary + "\n" + json.dumps(data, ensure_ascii=False, indent=2),
            "stderr": "",
        }
