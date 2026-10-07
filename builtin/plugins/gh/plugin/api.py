"""
gh 插件私有功能层（运行在 gateway，供前端代理调用；不暴露给 Agent）。

提供 gh 插件的全部业务功能纯函数：
- list_issues / list_prs / get_issue / get_pr：读操作（匿名可用）
- merge_pr / comment / close_issue：写操作（需已登录 token，复用 gh CLI 登录态）
- resolve_repo：解析当前工作目录对应的仓库

每个函数返回 dict：{"success": bool, "data": .../ "message": .../ "error": ...}。
本模块不声明在 tool_load_dirs，因此不会被 ToolRegistry 加载，Agent 不可见；
gateway 通过插件功能代理端点动态加载本模块并调用。
"""

import os
import sys
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

# 确保能 import 同目录的 gh_common（gateway 动态加载本文件时 plugin/ 不在 sys.path）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import gh_common  # noqa: E402


def _require_repo(repo: Optional[str]) -> tuple:
    """校验并返回仓库名。返回 (repo, error)；repo 为空时 error 非空。"""
    repo = (repo or "").strip()
    if not repo:
        return "", "未指定仓库（当前目录不是 git 仓库或缺少 origin remote）"
    return repo, ""


# ---------------------------------------------------------------------------
# 读操作
# ---------------------------------------------------------------------------
def list_issues(repo: Optional[str] = None, state: str = "open") -> Dict[str, Any]:
    """列出仓库的 Issues（排除 PR）。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    state = (state or "open").strip()
    if state not in ("open", "closed", "all"):
        return {"success": False, "error": f"无效 state: {state}"}
    resp = gh_common.api_request(
        "GET",
        f"/repos/{repo}/issues?state={state}&per_page=100",
        token=gh_common.get_token(),
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    issues = resp["data"]
    if not isinstance(issues, list):
        return {"success": False, "error": "响应格式异常"}
    result = []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        result.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "user": (issue.get("user") or {}).get("login"),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
                "comments": issue.get("comments"),
                "html_url": issue.get("html_url"),
            }
        )
    return {"success": True, "data": result, "repo": repo, "state": state}


def list_prs(repo: Optional[str] = None, state: str = "open") -> Dict[str, Any]:
    """列出仓库的 Pull Requests。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    state = (state or "open").strip()
    if state not in ("open", "closed", "all"):
        return {"success": False, "error": f"无效 state: {state}"}
    resp = gh_common.api_request(
        "GET",
        f"/repos/{repo}/pulls?state={state}&per_page=100",
        token=gh_common.get_token(),
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    prs = resp["data"]
    if not isinstance(prs, list):
        return {"success": False, "error": "响应格式异常"}
    result = []
    for pr in prs:
        result.append(
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "user": (pr.get("user") or {}).get("login"),
                "created_at": pr.get("created_at"),
                "updated_at": pr.get("updated_at"),
                "html_url": pr.get("html_url"),
            }
        )
    return {"success": True, "data": result, "repo": repo, "state": state}


def get_issue(
    repo: Optional[str] = None, number: Optional[int] = None
) -> Dict[str, Any]:
    """查看单个 Issue 详情。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue 编号）"}
    resp = gh_common.api_request(
        "GET", f"/repos/{repo}/issues/{number}", token=gh_common.get_token()
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    issue = resp["data"]
    if not isinstance(issue, dict):
        return {"success": False, "error": "响应格式异常"}
    result = {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "user": (issue.get("user") or {}).get("login"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "comments": issue.get("comments"),
        "labels": [label.get("name") for label in (issue.get("labels") or [])],
        "body": issue.get("body"),
        "html_url": issue.get("html_url"),
    }
    return {"success": True, "data": result}


def get_pr(repo: Optional[str] = None, number: Optional[int] = None) -> Dict[str, Any]:
    """查看单个 Pull Request 详情。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（PR 编号）"}
    resp = gh_common.api_request(
        "GET", f"/repos/{repo}/pulls/{number}", token=gh_common.get_token()
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    pr = resp["data"]
    if not isinstance(pr, dict):
        return {"success": False, "error": "响应格式异常"}
    result = {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "user": (pr.get("user") or {}).get("login"),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
        "merged": pr.get("merged"),
        "mergeable": pr.get("mergeable"),
        "head": (pr.get("head") or {}).get("ref"),
        "base": (pr.get("base") or {}).get("ref"),
        "body": pr.get("body"),
        "html_url": pr.get("html_url"),
    }
    return {"success": True, "data": result}


def list_comments(
    repo: Optional[str] = None, number: Optional[int] = None
) -> Dict[str, Any]:
    """列出 Issue 或 PR 的评论。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue/PR 编号）"}
    resp = gh_common.api_request(
        "GET",
        f"/repos/{repo}/issues/{number}/comments?per_page=100",
        token=gh_common.get_token(),
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    comments = resp["data"]
    if not isinstance(comments, list):
        return {"success": False, "error": "响应格式异常"}
    result = []
    for c in comments:
        result.append(
            {
                "user": (c.get("user") or {}).get("login"),
                "body": c.get("body"),
                "created_at": c.get("created_at"),
                "html_url": c.get("html_url"),
            }
        )
    return {"success": True, "data": result}


# ---------------------------------------------------------------------------
# 写操作（需已登录 token）
# ---------------------------------------------------------------------------
def merge_pr(
    repo: Optional[str] = None,
    number: Optional[int] = None,
    merge_method: str = "merge",
) -> Dict[str, Any]:
    """合并一个 Pull Request。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（PR 编号）"}
    token = gh_common.get_token()
    if not token:
        return {
            "success": False,
            "error": "合并 PR 需要登录。请先在终端执行 gh auth login 登录 GitHub。",
        }
    merge_method = (merge_method or "merge").strip()
    resp = gh_common.api_request(
        "PUT",
        f"/repos/{repo}/pulls/{number}/merge",
        token=token,
        data={"merge_method": merge_method},
    )
    if not resp["success"]:
        hint = gh_common.auth_error_hint(resp["status"])
        return {"success": False, "error": resp["error"] + (" " + hint if hint else "")}
    return {"success": True, "message": f"PR #{number} 合并成功（{merge_method}）"}


def comment(
    repo: Optional[str] = None,
    number: Optional[int] = None,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    """在 Issue 或 PR 上发布评论。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue/PR 编号）"}
    body = (body or "").strip()
    if not body:
        return {"success": False, "error": "请提供 body（评论内容）"}
    token = gh_common.get_token()
    if not token:
        return {
            "success": False,
            "error": "发布评论需要登录。请先在终端执行 gh auth login 登录 GitHub。",
        }
    resp = gh_common.api_request(
        "POST",
        f"/repos/{repo}/issues/{number}/comments",
        token=token,
        data={"body": body},
    )
    if not resp["success"]:
        hint = gh_common.auth_error_hint(resp["status"])
        return {"success": False, "error": resp["error"] + (" " + hint if hint else "")}
    return {"success": True, "message": f"评论已发布到 #{number}"}


def close_issue(
    repo: Optional[str] = None, number: Optional[int] = None
) -> Dict[str, Any]:
    """关闭一个 Issue。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue 编号）"}
    token = gh_common.get_token()
    if not token:
        return {
            "success": False,
            "error": "关闭 issue 需要登录。请先在终端执行 gh auth login 登录 GitHub。",
        }
    resp = gh_common.api_request(
        "PATCH",
        f"/repos/{repo}/issues/{number}",
        token=token,
        data={"state": "closed"},
    )
    if not resp["success"]:
        hint = gh_common.auth_error_hint(resp["status"])
        return {"success": False, "error": resp["error"] + (" " + hint if hint else "")}
    return {"success": True, "message": f"issue #{number} 已关闭"}


# ---------------------------------------------------------------------------
# 仓库解析
# ---------------------------------------------------------------------------
def resolve_repo(working_dir: Optional[str] = None) -> Dict[str, Any]:
    """解析指定工作目录对应的 GitHub 仓库（owner/repo）。

    通过读取该目录的 git remote origin 得到仓库；非 git 仓库或无 origin
    时返回空 repo（不回退到默认仓库，避免插件发布后其他用户看到固定仓库）。
    供前端侧边栏跟随当前 agent 所在仓库使用。
    """
    repo = gh_common.resolve_repo_from_dir(working_dir or "")
    return {"success": True, "repo": repo, "working_dir": working_dir or ""}


# 可被 gateway 代理调用的函数白名单（防止任意函数被调用）
PUBLIC_FUNCTIONS: List[str] = [
    "list_issues",
    "list_prs",
    "get_issue",
    "get_pr",
    "list_comments",
    "merge_pr",
    "comment",
    "close_issue",
    "resolve_repo",
]
