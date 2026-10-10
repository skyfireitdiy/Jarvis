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


# 单页最大条数（GitHub REST API 上限为 100）
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


def _paging_meta(headers: dict, page: int, per_page: int, count: int) -> dict:
    """根据响应头与当前页信息，构造分页元数据。

    返回 {"total": int, "has_more": bool, "page": int, "per_page": int}。
    total 由 Link 头 rel="last" 的 page 推断（GitHub 列表接口不直接返回总数），
    无法推断时退化为「已加载条数」。
    """
    last_page = gh_common.parse_link_last_page(headers)
    has_more = bool(gh_common.parse_link_next(headers))
    if last_page > 0:
        # 最后一页可能不满 per_page，用 (last_page-1)*per_page + 当前页条数估算
        if has_more:
            total = last_page * per_page
        else:
            total = (last_page - 1) * per_page + count
    else:
        total = (page - 1) * per_page + count
    return {"total": total, "has_more": has_more, "page": page, "per_page": per_page}


# ---------------------------------------------------------------------------
# 读操作
# ---------------------------------------------------------------------------
def list_issues(
    repo: Optional[str] = None,
    state: str = "open",
    page: Any = 1,
    per_page: Any = _MAX_PER_PAGE,
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
    resp = gh_common.api_request(
        "GET",
        f"/repos/{repo}/issues?state={state}&per_page={per_page}&page={page}",
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
    meta = _paging_meta(resp.get("headers", {}), page, per_page, len(result))
    return {
        "success": True,
        "data": result,
        "repo": repo,
        "state": state,
        **meta,
    }


def list_prs(
    repo: Optional[str] = None,
    state: str = "open",
    page: Any = 1,
    per_page: Any = _MAX_PER_PAGE,
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
    resp = gh_common.api_request(
        "GET",
        f"/repos/{repo}/pulls?state={state}&per_page={per_page}&page={page}",
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
    meta = _paging_meta(resp.get("headers", {}), page, per_page, len(result))
    return {
        "success": True,
        "data": result,
        "repo": repo,
        "state": state,
        **meta,
    }


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
# Fork / Clone（需已登录 token）
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


def _current_login() -> str:
    """获取当前 gh 登录用户名；未登录返回空字符串。"""
    res = _run_command(["gh", "api", "user", "--jq", ".login"], timeout=15)
    if not res["success"]:
        return ""
    return res["stdout"].strip()


def fork_repo(repo: Optional[str] = None) -> Dict[str, Any]:
    """Fork 指定仓库到当前登录账号下。

    已存在同名 fork 时直接复用（不重复 fork）。返回：
    {"success": True, "fork_repo": "owner/repo", "message": str}。
    未登录 gh 或 fork 失败时返回 {"success": False, "error": str}。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}

    login = _current_login()
    if not login:
        return {
            "success": False,
            "error": "Fork 仓库需要登录。请先在终端执行 gh auth login 登录 GitHub。",
        }

    # 目标 fork 名 = 当前登录用户 / 原仓库名
    repo_name = repo.split("/", 1)[1]
    fork_repo = f"{login}/{repo_name}"

    # 已存在同名 fork 则复用
    existing = gh_common.api_request(
        "GET", f"/repos/{fork_repo}", token=gh_common.get_token()
    )
    if existing["success"]:
        return {
            "success": True,
            "fork_repo": fork_repo,
            "message": f"已存在同名 fork，直接复用：{fork_repo}",
        }

    res = _run_command(["gh", "repo", "fork", repo, "--clone=false"])
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"Fork 失败: {detail}"}
    return {
        "success": True,
        "fork_repo": fork_repo,
        "message": f"已 Fork 到 {fork_repo}",
    }


def clone_repo(
    repo: Optional[str] = None, target_dir: Optional[str] = None
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

    res = _run_command(["git", "clone", f"https://github.com/{repo}.git", local_dir])
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "error": f"Clone 失败: {detail}"}
    return {
        "success": True,
        "local_dir": local_dir,
        "message": f"已 Clone 到 {local_dir}",
    }


def prepare_issue_repo(
    repo: Optional[str] = None, target_dir: Optional[str] = None
) -> Dict[str, Any]:
    """组合操作：先 fork 原仓库，再把 fork 后的仓库 clone 到 target_dir，
    并配置 upstream remote 指向原仓库。

    供自定义仓库 Issue 的「Fork 并创建 CodeAgent 处理」流程使用。
    返回 {"success": True, "fork_repo": str, "local_dir": str, "message": str}。
    """
    repo, _repo_err = _require_repo(repo)
    if _repo_err:
        return {"success": False, "error": _repo_err}

    fork_result = fork_repo(repo)
    if not fork_result.get("success"):
        return {"success": False, "error": fork_result.get("error", "Fork 失败")}
    fork_repo_name = fork_result["fork_repo"]

    clone_result = clone_repo(fork_repo_name, target_dir)
    if not clone_result.get("success"):
        return {
            "success": False,
            "error": clone_result.get("error", "Clone 失败"),
            "fork_repo": fork_repo_name,
        }
    local_dir = clone_result["local_dir"]

    # 设置 upstream 指向原仓库，使后续 git fetch upstream / gh pr create 可用
    upstream_url = f"https://github.com/{repo}.git"
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
    "fork_repo",
    "clone_repo",
    "prepare_issue_repo",
]
