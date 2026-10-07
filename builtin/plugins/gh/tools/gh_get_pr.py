"""
查看单个 Pull Request 详情。

用途:
- 查看指定 PR 的详细信息（标题、状态、作者、body、合并状态等）。

参数:
- number (int): PR 编号（必填）
- repo (str, 可选): 仓库 "owner/repo"，未指定时从当前工作目录解析

返回:
- success (bool)
- stdout (str): JSON 文本，含 PR 详情
- stderr (str)
"""

import json
from typing import Any
from typing import Dict

from _gh_api import load_api, resolve_repo_arg


class GhGetPrTool:
    name = "gh_get_pr"
    description = "查看单个 GitHub Pull Request 的详情。"
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
        result = api.get_pr(repo=repo, number=args.get("number"))
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error", "未知错误"),
            }
        return {
            "success": True,
            "stdout": json.dumps(result.get("data"), ensure_ascii=False, indent=2),
            "stderr": "",
        }
