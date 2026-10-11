"""
gh 插件私有功能层（运行在 gateway，供前端代理调用；不暴露给 Agent）。

提供 gh 插件的全部业务功能纯函数（GitHub/Gitee 双平台）：
- list_issues / list_prs / get_issue / get_pr：读操作（匿名可用）
- merge_pr / comment / close_issue：写操作（需已登录 token，复用 gh/gitee CLI 登录态）
- auth_status / auth_login：查询/写入 CLI 登录态（前端认证入口）
- resolve_repo：解析当前工作目录对应的仓库与平台
- fork_repo / clone_repo / prepare_issue_repo：Fork / Clone（GitHub 语义）

平台识别：默认按目标仓库 remote 主机名自动识别（github.com→github / gitee.com→gitee），
也可通过 platform 参数显式指定（auto/github/gitee）。

每个函数返回 dict：{"success": bool, "data": .../ "message": .../ "error": ...}。
本模块不声明在 tool_load_dirs，因此不会被 ToolRegistry 加载，Agent 不可见；
gateway 通过插件功能代理端点动态加载本模块并调用。
"""

import os
import subprocess
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


# 单页最大条数
_MAX_PER_PAGE = 100


def _normalize_paging(page: Any, per_page: Any) -> tuple:
    """规范化分页参数，返回 (page, per_page)。

    page 从 1 开始；per_page 限制在 [1, 100]。非法值回退默认。
    """
    try:
        page_num = int(page)
    except (TypeError, ValueError):
        page_num = 1
    if page_num < 1:
        page_num = 1
    try:
        per_page_num = int(per_page)
    except (TypeError, ValueError):
        per_page_num = _MAX_PER_PAGE
    if per_page_num < 1:
        per_page_num = _MAX_PER_PAGE
    if per_page_num > _MAX_PER_PAGE:
        per_page_num = _MAX_PER_PAGE
    return page_num, per_page_num


def _paging_meta(
    page: int, per_page: int, count: int, total: Optional[int] = None
) -> dict:
    """构造分页元数据。

    返回 {"total": int, "has_more": bool, "page": int, "per_page": int}。
    total 未提供时退化为「已加载条数」。
    """
    if total is None:
        total = (page - 1) * per_page + count
    has_more = count >= per_page
    return {"total": total, "has_more": has_more, "page": page, "per_page": per_page}


# ---------------------------------------------------------------------------
# 平台分发辅助
# ---------------------------------------------------------------------------
def _resolve_platform(platform: Optional[str], repo: Optional[str]) -> str:
    """解析平台：显式指定 → 按仓库名猜测 → github。

    仓库名含 gitee.com 前缀（如 gitee.com/owner/repo）时识别为 gitee；
    否则默认 github。
    """
    p = (platform or "").strip().lower()
    if p in ("gitee", "gitee.com"):
        return "gitee"
    if p == "github":
        return "github"
    # auto/None：按仓库名猜测
    repo_l = (repo or "").strip().lower()
    if "gitee.com" in repo_l or repo_l.startswith("gitee/"):
        return "gitee"
    return "github"


def _auth_error(platform: str, action: str) -> Dict[str, Any]:
    """构造未登录错误。"""
    host = "GitHub" if platform == "github" else "Gitee"
    cli = "gh auth login" if platform == "github" else "gitee auth login"
    return {
        "success": False,
        "error": f"{action}需要登录。请先在终端执行 {cli} 登录 {host}。",
    }


# ---------------------------------------------------------------------------
# 字段映射（统一为前端使用的字段）
# ---------------------------------------------------------------------------
def _map_issue_github(issue: dict) -> dict:
    """把 gh CLI 的 issue 对象映射为统一字段。"""
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": (issue.get("state") or "").lower(),
        "user": (issue.get("author") or {}).get("login"),
        "created_at": issue.get("createdAt"),
        "updated_at": issue.get("updatedAt"),
        "comments": len(issue.get("comments") or []),
        "html_url": issue.get("url"),
    }


def _map_issue_gitee(issue: dict) -> dict:
    """把 gitee CLI 的 issue 对象映射为统一字段。

    Gitee issue 的 number 是字符串（如 IHWYFN），保持原样。
    """
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": (issue.get("state") or "").lower(),
        "user": (issue.get("user") or {}).get("login"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "comments": None,
        "html_url": issue.get("html_url"),
    }


def _map_pr_github(pr: dict) -> dict:
    """把 gh CLI 的 pr 对象映射为统一字段。"""
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": (pr.get("state") or "").lower(),
        "user": (pr.get("author") or {}).get("login"),
        "created_at": pr.get("createdAt"),
        "updated_at": pr.get("updatedAt"),
        "merged": bool(pr.get("mergedAt")),
        "mergeable": pr.get("mergeable"),
        "html_url": pr.get("url"),
    }


def _map_pr_gitee(pr: dict) -> dict:
    """把 gitee CLI 的 pr 对象映射为统一字段。

    Gitee PR 无 merged 布尔字段，用 merged_at 推断。
    """
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": (pr.get("state") or "").lower(),
        "user": (pr.get("user") or {}).get("login"),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
        "merged": bool(pr.get("merged_at")),
        "mergeable": pr.get("mergeable"),
        "html_url": pr.get("html_url"),
    }


# ---------------------------------------------------------------------------
# 读操作
# ---------------------------------------------------------------------------
def list_issues(
    repo: Optional[str] = None,
    state: str = "open",
    page: Any = 1,
    per_page: Any = _MAX_PER_PAGE,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """列出仓库的 Issues（排除 PR），支持分页。

    返回 data 为当前页 issue 列表，并附 total/has_more/page/per_page 分页元数据。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    state = (state or "open").strip()
    if state not in ("open", "closed", "all"):
        return {"success": False, "error": f"无效 state: {state}"}
    page, per_page = _normalize_paging(page, per_page)
    platform = _resolve_platform(platform, repo)

    if platform == "gitee":
        resp = gh_common.cli_json(
            "gitee",
            ["issue", "list", "-R", repo, "-s", state, "-p", str(page), "-l", str(per_page), "--json"],
        )
        if not resp["success"]:
            return {"success": False, "error": resp["error"]}
        issues = resp["data"]
        if not isinstance(issues, list):
            return {"success": False, "error": "响应格式异常"}
        result = [_map_issue_gitee(issue) for issue in issues]
        meta = _paging_meta(page, per_page, len(result))
        return {
            "success": True,
            "data": result,
            "repo": repo,
            "state": state,
            "platform": platform,
            **meta,
        }

    # github：gh issue list 无 --page，用 --limit 拉取后切片
    fetch_limit = page * per_page
    resp = gh_common.cli_json(
        "github",
        [
            "issue",
            "list",
            "--repo",
            repo,
            "-s",
            state,
            "--limit",
            str(fetch_limit),
            "--json",
            "number,title,state,author,createdAt,updatedAt,url,comments",
        ],
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    issues = resp["data"]
    if not isinstance(issues, list):
        return {"success": False, "error": "响应格式异常"}
    start = (page - 1) * per_page
    page_items = issues[start : start + per_page]
    result = [_map_issue_github(it) for it in page_items]
    meta = _paging_meta(page, per_page, len(result), total=len(issues))
    return {
        "success": True,
        "data": result,
        "repo": repo,
        "state": state,
        "platform": platform,
        **meta,
    }


def list_prs(
    repo: Optional[str] = None,
    state: str = "open",
    page: Any = 1,
    per_page: Any = _MAX_PER_PAGE,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """列出仓库的 Pull Requests，支持分页。

    返回 data 为当前页 PR 列表，并附 total/has_more/page/per_page 分页元数据。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    state = (state or "open").strip()
    if state not in ("open", "closed", "all"):
        return {"success": False, "error": f"无效 state: {state}"}
    page, per_page = _normalize_paging(page, per_page)
    platform = _resolve_platform(platform, repo)

    if platform == "gitee":
        resp = gh_common.cli_json(
            "gitee",
            ["pr", "list", "-R", repo, "-s", state, "-p", str(page), "-l", str(per_page), "--json"],
        )
        if not resp["success"]:
            return {"success": False, "error": resp["error"]}
        prs = resp["data"]
        if not isinstance(prs, list):
            return {"success": False, "error": "响应格式异常"}
        result = [_map_pr_gitee(pr) for pr in prs]
        meta = _paging_meta(page, per_page, len(result))
        return {
            "success": True,
            "data": result,
            "repo": repo,
            "state": state,
            "platform": platform,
            **meta,
        }

    # github：--limit 拉取后切片
    fetch_limit = page * per_page
    resp = gh_common.cli_json(
        "github",
        [
            "pr",
            "list",
            "--repo",
            repo,
            "-s",
            state,
            "--limit",
            str(fetch_limit),
            "--json",
            "number,title,state,author,createdAt,updatedAt,url,mergeable,isDraft,mergedAt",
        ],
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    prs = resp["data"]
    if not isinstance(prs, list):
        return {"success": False, "error": "响应格式异常"}
    start = (page - 1) * per_page
    page_items = prs[start : start + per_page]
    result = [_map_pr_github(it) for it in page_items]
    meta = _paging_meta(page, per_page, len(result), total=len(prs))
    return {
        "success": True,
        "data": result,
        "repo": repo,
        "state": state,
        "platform": platform,
        **meta,
    }


def get_issue(
    repo: Optional[str] = None,
    number: Optional[Any] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """查看单个 Issue 详情。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue 编号）"}
    platform = _resolve_platform(platform, repo)
    number = str(number).strip()

    if platform == "gitee":
        resp = gh_common.cli_json("gitee", ["issue", "view", number, "-R", repo, "--json"])
        if not resp["success"]:
            return {"success": False, "error": resp["error"]}
        issue = resp["data"]
        if not isinstance(issue, dict):
            return {"success": False, "error": "响应格式异常"}
        result = _map_issue_gitee(issue)
        result["labels"] = [label.get("name") for label in (issue.get("labels") or [])]
        result["body"] = issue.get("body")
        return {"success": True, "data": result, "platform": platform}

    resp = gh_common.cli_json(
        "github",
        [
            "issue",
            "view",
            number,
            "--repo",
            repo,
            "--json",
            "number,title,state,author,createdAt,updatedAt,url,comments,labels,body",
        ],
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    issue = resp["data"]
    if not isinstance(issue, dict):
        return {"success": False, "error": "响应格式异常"}
    result = _map_issue_github(issue)
    result["labels"] = [label.get("name") for label in (issue.get("labels") or [])]
    result["body"] = issue.get("body")
    return {"success": True, "data": result, "platform": platform}


def get_pr(
    repo: Optional[str] = None,
    number: Optional[Any] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """查看单个 Pull Request 详情。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（PR 编号）"}
    platform = _resolve_platform(platform, repo)
    number = str(number).strip()

    if platform == "gitee":
        resp = gh_common.cli_json("gitee", ["pr", "view", number, "-R", repo, "--json"])
        if not resp["success"]:
            return {"success": False, "error": resp["error"]}
        pr = resp["data"]
        if not isinstance(pr, dict):
            return {"success": False, "error": "响应格式异常"}
        result = _map_pr_gitee(pr)
        result["head"] = (pr.get("head") or {}).get("ref")
        result["base"] = (pr.get("base") or {}).get("ref")
        result["body"] = pr.get("body")
        return {"success": True, "data": result, "platform": platform}

    resp = gh_common.cli_json(
        "github",
        [
            "pr",
            "view",
            number,
            "--repo",
            repo,
            "--json",
            "number,title,state,author,createdAt,updatedAt,url,mergedAt,closed,mergeable,headRefName,baseRefName,body,isDraft",
        ],
    )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    pr = resp["data"]
    if not isinstance(pr, dict):
        return {"success": False, "error": "响应格式异常"}
    result = _map_pr_github(pr)
    result["head"] = pr.get("headRefName")
    result["base"] = pr.get("baseRefName")
    result["body"] = pr.get("body")
    return {"success": True, "data": result, "platform": platform}


def list_comments(
    repo: Optional[str] = None,
    number: Optional[Any] = None,
    kind: str = "issue",
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """列出 Issue 或 PR 的评论。kind: 'issue' 或 'pr'。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue/PR 编号）"}
    kind = (kind or "issue").strip().lower()
    if kind not in ("issue", "pr"):
        kind = "issue"
    platform = _resolve_platform(platform, repo)
    number = str(number).strip()

    if platform == "gitee":
        # gitee-cli 无独立列评论命令，用 api 端点
        endpoint = (
            f"/repos/{repo}/issues/{number}/comments"
            if kind == "issue"
            else f"/repos/{repo}/pulls/{number}/comments"
        )
        resp = gh_common.cli_json("gitee", ["api", endpoint])
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
        return {"success": True, "data": result, "platform": platform}

    # github：gh issue/pr view --json comments
    if kind == "issue":
        resp = gh_common.cli_json(
            "github", ["issue", "view", number, "--repo", repo, "--json", "comments"]
        )
    else:
        resp = gh_common.cli_json(
            "github", ["pr", "view", number, "--repo", repo, "--json", "comments"]
        )
    if not resp["success"]:
        return {"success": False, "error": resp["error"]}
    comments = (resp["data"] or {}).get("comments")
    if not isinstance(comments, list):
        return {"success": False, "error": "响应格式异常"}
    result = []
    for c in comments:
        result.append(
            {
                "user": (c.get("author") or {}).get("login"),
                "body": c.get("body"),
                "created_at": c.get("createdAt"),
                "html_url": c.get("url"),
            }
        )
    return {"success": True, "data": result, "platform": platform}


# ---------------------------------------------------------------------------
# 写操作（需已登录 token）
# ---------------------------------------------------------------------------
def merge_pr(
    repo: Optional[str] = None,
    number: Optional[Any] = None,
    merge_method: str = "merge",
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """合并一个 Pull Request。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（PR 编号）"}
    platform = _resolve_platform(platform, repo)
    number = str(number).strip()
    merge_method = (merge_method or "merge").strip()
    if merge_method not in ("merge", "squash", "rebase"):
        return {"success": False, "error": f"无效 merge_method: {merge_method}"}
    if not gh_common.get_token(platform):
        return _auth_error(platform, "合并 PR")

    if platform == "gitee":
        res = gh_common.run_cli(
            "gitee",
            ["pr", "merge", number, "-R", repo, "--method", merge_method],
            timeout=60,
        )
    else:
        method_flag = f"--{merge_method}"
        res = gh_common.run_cli(
            "github", ["pr", "merge", number, "--repo", repo, method_flag], timeout=60
        )
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"合并 PR 失败: {detail}"}
    return {
        "success": True,
        "message": f"PR #{number} 合并成功（{merge_method}）",
        "platform": platform,
    }


def comment(
    repo: Optional[str] = None,
    number: Optional[Any] = None,
    body: Optional[str] = None,
    kind: str = "issue",
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """在 Issue 或 PR 上发布评论。kind: 'issue' 或 'pr'。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue/PR 编号）"}
    body = (body or "").strip()
    if not body:
        return {"success": False, "error": "请提供 body（评论内容）"}
    kind = (kind or "issue").strip().lower()
    if kind not in ("issue", "pr"):
        kind = "issue"
    platform = _resolve_platform(platform, repo)
    number = str(number).strip()
    if not gh_common.get_token(platform):
        return _auth_error(platform, "发布评论")

    if platform == "gitee":
        res = gh_common.run_cli(
            "gitee", [kind, "comment", number, "-R", repo, "-b", body], timeout=60
        )
    else:
        res = gh_common.run_cli(
            "github", [kind, "comment", number, "--repo", repo, "--body", body], timeout=60
        )
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"发布评论失败: {detail}"}
    return {"success": True, "message": f"评论已发布到 #{number}", "platform": platform}


def close_issue(
    repo: Optional[str] = None,
    number: Optional[Any] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """关闭一个 Issue。"""
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    if number is None:
        return {"success": False, "error": "请提供 number（issue 编号）"}
    platform = _resolve_platform(platform, repo)
    number = str(number).strip()
    if not gh_common.get_token(platform):
        return _auth_error(platform, "关闭 issue")

    if platform == "gitee":
        res = gh_common.run_cli("gitee", ["issue", "close", number, "-R", repo], timeout=60)
    else:
        res = gh_common.run_cli("github", ["issue", "close", number, "--repo", repo], timeout=60)
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"关闭 issue 失败: {detail}"}
    return {"success": True, "message": f"issue #{number} 已关闭", "platform": platform}


# ---------------------------------------------------------------------------
# Fork / Clone
# ---------------------------------------------------------------------------
def _run_command(args: List[str], cwd: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
    """参数化执行外部命令（禁止 shell 拼接，避免注入）。

    返回 {"success": bool, "stdout": str, "stderr": str, "returncode": int}。
    命令不存在或超时时 success=False，error 说明原因。
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"命令不存在: {args[0]}（请确认已安装）",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"命令执行超时（>{timeout}s）: {' '.join(args)}",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": str(e),
        }
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "error": "",
    }


def _current_login(platform: Optional[str] = None) -> str:
    """获取当前登录用户名；未登录返回空字符串。"""
    platform = gh_common.normalize_platform(platform)
    if platform == "gitee":
        res = gh_common.cli_json("gitee", ["api", "/user"])
        if not res["success"]:
            return ""
        user = res["data"]
        return (user or {}).get("login", "") if isinstance(user, dict) else ""
    res = gh_common.run_cli("github", ["api", "user", "--jq", ".login"])
    if not res["success"]:
        return ""
    return (res["stdout"] or "").strip()


def _cli_installed(platform: str) -> bool:
    """判断平台 CLI 是否已安装（gh / gitee）。"""
    executable = "gh" if platform == "github" else "gitee"
    return _run_command([executable, "--version"], timeout=10)["success"]


def auth_status(platform: Optional[str] = None) -> Dict[str, Any]:
    """查询指定平台在当前节点是否已认证。

    返回 {"success": True, "authenticated": bool, "login": str, "installed": bool}。
    - installed: 对应 CLI（gh / gitee）是否已安装
    - authenticated: 是否已登录（CLI 未安装视为未认证）
    - login: 已登录用户名（未登录为空串）
    """
    platform = gh_common.normalize_platform(platform)
    if not _cli_installed(platform):
        return {
            "success": True,
            "authenticated": False,
            "login": "",
            "installed": False,
            "platform": platform,
        }
    login = _current_login(platform)
    return {
        "success": True,
        "authenticated": bool(login),
        "login": login,
        "installed": True,
        "platform": platform,
    }


def auth_login(
    platform: Optional[str] = None, token: Optional[str] = None
) -> Dict[str, Any]:
    """用 token 登录指定平台（仅在该平台未认证时写入凭据）。

    token 通过 stdin 传给对应 CLI 的 `auth login --with-token`，由 CLI 校验并写入
    凭据存储；已认证时拒绝（避免覆盖已有凭据）。token 不写日志、不回显。
    返回 {"success": True, "message": str, "login": str}；失败时 success=False。
    """
    platform = gh_common.normalize_platform(platform)
    token = (token or "").strip()
    if not token:
        return {"success": False, "error": "请提供 token"}
    if not _cli_installed(platform):
        host = "GitHub" if platform == "github" else "Gitee"
        cli = "gh" if platform == "github" else "gitee"
        return {
            "success": False,
            "error": f"当前节点未安装 {cli} CLI，无法登录 {host}",
        }
    if _current_login(platform):
        return {
            "success": False,
            "error": f"当前节点已登录 {platform}，无需重复认证",
        }

    executable = "gh" if platform == "github" else "gitee"
    args = ["auth", "login", "--with-token"]
    try:
        result = subprocess.run(
            [executable] + args,
            input=token + "\n",
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "认证超时，请重试"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": f"认证失败: {e}"}
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return {"success": False, "error": f"认证失败: {detail or 'token 无效'}"}

    login = _current_login(platform)
    host = "GitHub" if platform == "github" else "Gitee"
    return {
        "success": True,
        "message": f"已登录 {host}（{login or platform}）",
        "login": login,
    }


def fork_repo(
    repo: Optional[str] = None, platform: Optional[str] = None
) -> Dict[str, Any]:
    """Fork 指定仓库到当前登录账号下。

    已存在同名 fork 时直接复用（不重复 fork）。返回：
    {"success": True, "fork_repo": "owner/repo", "message": str}。
    未登录或 fork 失败时返回 {"success": False, "error": str}。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    platform = gh_common.normalize_platform(platform)

    login = _current_login(platform)
    if not login:
        return _auth_error(platform, "Fork 仓库")

    # 目标 fork 名 = 当前登录用户 / 原仓库名
    repo_name = repo.split("/", 1)[1]
    fork_repo = f"{login}/{repo_name}"

    if platform == "gitee":
        # 已存在同名 fork 则复用（gitee api 查仓库）
        existing = gh_common.cli_json("gitee", ["api", f"/repos/{fork_repo}"])
        if existing["success"]:
            return {
                "success": True,
                "fork_repo": fork_repo,
                "message": f"已存在同名 fork，直接复用：{fork_repo}",
            }
        res = gh_common.run_cli(
            "gitee", ["repo", "fork", repo, "--clone=false"], timeout=300
        )
    else:
        # 已存在同名 fork 则复用（gh repo view 判断）
        existing = gh_common.run_cli("github", ["repo", "view", fork_repo])
        if existing["success"]:
            return {
                "success": True,
                "fork_repo": fork_repo,
                "message": f"已存在同名 fork，直接复用：{fork_repo}",
            }
        res = gh_common.run_cli(
            "github", ["repo", "fork", repo, "--clone=false"], timeout=300
        )
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"Fork 失败: {detail}"}
    return {
        "success": True,
        "fork_repo": fork_repo,
        "message": f"已 Fork 到 {fork_repo}",
    }


def clone_repo(
    repo: Optional[str] = None,
    target_dir: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """将仓库 clone 到 target_dir 下（同名子目录）。

    - 目标目录下已存在同名子目录且为同一仓库（origin 匹配）时复用，不重复 clone。
    - 已存在同名子目录但 origin 不匹配（非该仓库）时报错，避免覆盖用户数据。
    返回 {"success": True, "local_dir": str}。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    target_dir = (target_dir or "").strip()
    if not target_dir:
        return {"success": False, "error": "请提供 target_dir（clone 目标目录）"}
    if not os.path.isdir(target_dir):
        return {"success": False, "error": f"目标目录不存在: {target_dir}"}
    platform = gh_common.normalize_platform(platform)

    repo_name = repo.split("/", 1)[1]
    local_dir = os.path.join(target_dir, repo_name)

    if os.path.exists(local_dir):
        if not os.path.isdir(local_dir):
            return {"success": False, "error": f"目标路径已存在且不是目录: {local_dir}"}
        # 已存在：校验是否同一仓库
        existing_repo = gh_common.resolve_repo_from_dir(local_dir)
        if existing_repo == repo:
            return {
                "success": True,
                "local_dir": local_dir,
                "message": f"目录已存在同一仓库，直接复用：{local_dir}",
            }
        if existing_repo:
            return {
                "success": False,
                "error": (
                    f"目标目录已存在且属于其他仓库（{existing_repo}）：{local_dir}，"
                    "请更换目标目录或先移除该目录。"
                ),
            }
        return {
            "success": False,
            "error": f"目标目录已存在且不是 git 仓库: {local_dir}，请更换目标目录。",
        }

    clone_url = (
        f"https://gitee.com/{repo}.git"
        if platform == "gitee"
        else f"https://github.com/{repo}.git"
    )
    res = _run_command(["git", "clone", clone_url, local_dir])
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"Clone 失败: {detail}"}
    return {
        "success": True,
        "local_dir": local_dir,
        "message": f"已 Clone 到 {local_dir}",
    }


def prepare_issue_repo(
    repo: Optional[str] = None,
    target_dir: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """组合操作：先 fork 原仓库，再把 fork 后的仓库 clone 到 target_dir，
    并配置 upstream remote 指向原仓库。

    供自定义仓库 Issue 的「Fork 并创建 CodeAgent 处理」流程使用。
    返回 {"success": True, "fork_repo": str, "local_dir": str, "message": str}。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}
    platform = gh_common.normalize_platform(platform)

    fork_result = fork_repo(repo, platform=platform)
    if not fork_result.get("success"):
        return {"success": False, "error": fork_result.get("error", "Fork 失败")}
    fork_repo_name = fork_result["fork_repo"]

    clone_result = clone_repo(fork_repo_name, target_dir, platform=platform)
    if not clone_result.get("success"):
        return {
            "success": False,
            "error": clone_result.get("error", "Clone 失败"),
            "fork_repo": fork_repo_name,
        }
    local_dir = clone_result["local_dir"]

    # 设置 upstream 指向原仓库，使后续 git fetch upstream / gh pr create 可用
    host = "gitee.com" if platform == "gitee" else "github.com"
    upstream_url = f"https://{host}/{repo}.git"
    upstream_msg = _ensure_upstream_remote(local_dir, upstream_url)
    return {
        "success": True,
        "fork_repo": fork_repo_name,
        "local_dir": local_dir,
        "message": f"已 Fork 并 Clone 到 {local_dir}；{upstream_msg}",
    }


def _ensure_upstream_remote(local_dir: str, upstream_url: str) -> str:
    """确保本地仓库配置了指向原仓库的 upstream remote（幂等）。

    已存在同名 upstream 且指向相同 URL 时跳过；指向不同 URL 时更新。
    返回描述信息（供 message 拼接）。
    """
    existing = _run_command(
        ["git", "remote", "get-url", "upstream"], cwd=local_dir, timeout=15
    )
    if existing["success"]:
        if existing["stdout"].strip() == upstream_url:
            return "upstream 已指向原仓库"
        _run_command(
            ["git", "remote", "set-url", "upstream", upstream_url],
            cwd=local_dir,
            timeout=15,
        )
        return f"upstream 已更新指向原仓库 {upstream_url}"
    res = _run_command(
        ["git", "remote", "add", "upstream", upstream_url],
        cwd=local_dir,
        timeout=15,
    )
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return f"设置 upstream 失败: {detail}"
    return f"upstream 已指向原仓库 {upstream_url}"


# ---------------------------------------------------------------------------
# 仓库解析
# ---------------------------------------------------------------------------
def resolve_repo(
    working_dir: Optional[str] = None, platform: Optional[str] = None
) -> Dict[str, Any]:
    """解析指定工作目录对应的仓库（owner/repo）与平台（github/gitee）。

    通过读取该目录的 git remote origin 得到仓库与平台；非 git 仓库或无 origin
    时返回空 repo（不回退到默认仓库，避免插件发布后其他用户看到固定仓库）。
    供前端侧边栏跟随当前 agent 所在仓库使用。
    """
    repo = gh_common.resolve_repo_from_dir(working_dir or "")
    detected = gh_common.resolve_platform_from_dir(working_dir or "")
    # 显式指定平台优先；auto/None 时按 remote 识别
    p_raw = (platform or "").strip().lower()
    if p_raw in ("gitee", "gitee.com"):
        p = "gitee"
    elif p_raw == "github":
        p = "github"
    else:
        p = detected
    return {
        "success": True,
        "repo": repo,
        "platform": p,
        "working_dir": working_dir or "",
    }


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
    "fork_repo",
    "clone_repo",
    "prepare_issue_repo",
    "auth_status",
    "auth_login",
]
