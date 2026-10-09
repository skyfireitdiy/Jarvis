"""
gh 插件共享辅助模块（不含工具类，供各工具 import 复用）。

提供：
- GitHub token 的读取（复用 GitHub 官方 gh CLI 的登录态，`gh auth token`）
- GitHub REST API 请求封装（urllib，不依赖 requests）
- 默认仓库常量
"""

import json
import subprocess
import urllib.error
import urllib.request
from typing import Optional

# GitHub REST API 基址
API_BASE = "https://api.github.com"
# 默认仓库（当前 Jarvis 的 GitHub 仓库）
DEFAULT_REPO = "skyfireitdiy/Jarvis"


def get_token() -> str:
    """读取 GitHub token（复用 GitHub 官方 gh CLI 登录态）。

    通过 `gh auth token` 获取当前登录账号的 token；gh CLI 未安装或未登录
    时返回空字符串。gh 插件自身不提供登录认证，认证由 gh CLI 负责。
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _build_headers(token: str) -> dict:
    """构造请求头。带 token 时加 Authorization。"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Jarvis-gh-plugin",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_request(
    method: str,
    path: str,
    token: str = "",
    data: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """调用 GitHub REST API。

    参数:
        method: HTTP 方法（GET/POST/PUT/PATCH/DELETE）
        path: API 路径，如 "/repos/skyfireitdiy/Jarvis/pulls"
        token: GitHub token（写操作必需）
        data: 请求体 dict（可选）
        timeout: 超时秒数

    返回:
        dict: {"success": bool, "status": int, "data": dict|list|None,
               "headers": dict, "error": str}
        headers 为响应头（键统一小写），供上层解析分页 Link 头使用。
    """
    url = API_BASE + path
    body = None
    headers = _build_headers(token)
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = raw
            return {
                "success": True,
                "status": status,
                "data": parsed,
                "headers": resp_headers,
                "error": "",
            }
    except urllib.error.HTTPError as e:
        status = e.code
        resp_headers = {k.lower(): v for k, v in (e.headers or {}).items()}
        raw = e.read().decode("utf-8", errors="replace")
        message = ""
        try:
            err_data = json.loads(raw)
            message = err_data.get("message", "")
        except Exception:
            message = raw
        return {
            "success": False,
            "status": status,
            "data": None,
            "headers": resp_headers,
            "error": f"GitHub API {status}: {message}",
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "status": 0,
            "data": None,
            "headers": {},
            "error": f"网络错误: {e.reason}",
        }
    except Exception as e:
        return {"success": False, "status": 0, "data": None, "headers": {}, "error": str(e)}


def parse_link_next(headers: dict) -> str:
    """从响应头 Link 中解析 rel="next" 的 URL；无则返回空字符串。

    GitHub 分页通过 Link 头返回相邻页 URL，形如：
      <https://api.github.com/...&page=2>; rel="next", <...&page=5>; rel="last"
    """
    link = (headers or {}).get("link", "")
    if not link:
        return ""
    for part in link.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url = segments[0].strip().strip("<>")
        for seg in segments[1:]:
            if seg.strip() == 'rel="next"':
                return url
    return ""


def parse_link_last_page(headers: dict) -> int:
    """从响应头 Link 中解析 rel="last" 的 page 参数；无则返回 0。"""
    link = (headers or {}).get("link", "")
    if not link:
        return 0
    for part in link.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url = segments[0].strip().strip("<>")
        is_last = any(seg.strip() == 'rel="last"' for seg in segments[1:])
        if not is_last:
            continue
        # 从 URL 查询串中取 page 参数
        if "?" not in url:
            return 0
        query = url.split("?", 1)[1]
        for kv in query.split("&"):
            if kv.startswith("page="):
                try:
                    return int(kv.split("=", 1)[1])
                except ValueError:
                    return 0
    return 0


def parse_remote_repo(remote_url: str) -> str:
    """从 git remote URL 解析出 'owner/repo'（不含 .git 后缀）。

    支持常见格式：
      https://github.com/owner/repo.git
      https://github.com/owner/repo
      git@github.com:owner/repo.git
      ssh://git@github.com/owner/repo.git
    解析失败返回空字符串。
    """
    url = (remote_url or "").strip()
    if not url:
        return ""
    # 去掉 .git 后缀
    if url.endswith(".git"):
        url = url[: -len(".git")]
    # 去掉末尾斜杠
    url = url.rstrip("/")
    # ssh 风格：git@github.com:owner/repo
    if "://" not in url and ":" in url:
        url = url.split(":", 1)[1]
    else:
        # https/ssh:// 风格：取路径部分
        url = url.split("://", 1)[-1]
        # 去掉主机部分（第一个 / 之前）
        if "/" in url:
            url = url.split("/", 1)[1]
    # 去掉可能的用户名/端口等前缀，取 owner/repo
    parts = [p for p in url.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return ""


def resolve_repo_from_dir(working_dir: str) -> str:
    """在指定目录执行 git remote get-url origin，解析出 'owner/repo'。

    非 git 仓库或无 origin remote 时返回空字符串。
    """
    import subprocess

    working_dir = (working_dir or "").strip()
    if not working_dir:
        return ""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return parse_remote_repo(result.stdout.strip())


def auth_error_hint(status: int) -> str:
    """根据 HTTP 状态码给出认证提示。"""
    if status in (401, 403):
        return (
            "认证失败（token 缺失或无效）。请先在终端执行 gh auth login 登录 GitHub，"
            "或用 gh auth status 查看登录状态。"
        )
    return ""
