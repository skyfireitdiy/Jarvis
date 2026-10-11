"""
gh 插件共享辅助模块（不含工具类，供各工具 import 复用）。

提供：
- GitHub/Gitee 双平台支持：token 读取（复用 gh / gitee CLI 登录态）、
  命令执行封装（参数化，禁 shell 拼接）、平台识别
- 默认仓库常量
"""

import json
import subprocess
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

# 默认仓库（当前 Jarvis 的 GitHub 仓库）
DEFAULT_REPO = "skyfireitdiy/Jarvis"

# 支持的平台
PLATFORMS = ("github", "gitee")


def normalize_platform(platform: Optional[str]) -> str:
    """规范化平台参数。auto 或非法值回退 github；返回 'github' 或 'gitee'。"""
    p = (platform or "").strip().lower()
    if p in ("gitee", "gitee.com"):
        return "gitee"
    return "github"


def detect_platform_from_remote(remote_url: str) -> str:
    """根据 git remote URL 的主机名识别平台：gitee.com → gitee，其余 → github。"""
    url = (remote_url or "").strip().lower()
    if "gitee.com" in url:
        return "gitee"
    return "github"


def get_token(platform: Optional[str] = None) -> str:
    """读取平台 token（复用对应官方 CLI 登录态）。

    - github: `gh auth token`
    - gitee: `gitee auth token`
    CLI 未安装或未登录时返回空字符串。插件自身不提供登录认证，认证由 CLI 负责。
    """
    platform = normalize_platform(platform)
    cmd = (
        ["gh", "auth", "token"]
        if platform == "github"
        else ["gitee", "auth", "token"]
    )
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def run_cli(
    platform: Optional[str],
    args: List[str],
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """参数化执行平台 CLI 命令（gh / gitee），禁 shell 拼接，避免注入。

    参数:
        platform: 'github' 或 'gitee'（auto 回退 github）
        args: 命令参数列表（不含可执行名）
        cwd: 工作目录（可选）
        timeout: 超时秒数

    返回:
        {"success": bool, "returncode": int, "stdout": str, "stderr": str, "error": str}
    """
    platform = normalize_platform(platform)
    executable = "gh" if platform == "github" else "gitee"
    try:
        result = subprocess.run(
            [executable] + list(args),
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
            "error": f"命令不存在: {executable}（请确认已安装并加入 PATH）",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"命令执行超时（>{timeout}s）: {executable} {' '.join(args)}",
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


def cli_json(
    platform: Optional[str],
    args: List[str],
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """执行平台 CLI 命令并把 stdout 解析为 JSON。

    返回:
        {"success": bool, "data": Any, "error": str}
        命令失败或 stdout 非 JSON 时 success=False。
    """
    res = run_cli(platform, args, cwd=cwd, timeout=timeout)
    if not res["success"]:
        detail = res["stderr"] or res["error"] or "未知错误"
        return {"success": False, "data": None, "error": detail}
    stdout = res["stdout"]
    if not stdout:
        return {"success": False, "data": None, "error": "命令无输出"}
    try:
        return {"success": True, "data": json.loads(stdout), "error": ""}
    except Exception:
        return {
            "success": False,
            "data": None,
            "error": f"命令输出不是合法 JSON: {stdout[:200]}",
        }


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


def resolve_platform_from_dir(working_dir: str) -> str:
    """在指定目录读取 origin remote URL，识别平台（github/gitee）。

    非 git 仓库或无 origin remote 时返回 'github'（默认）。
    """
    working_dir = (working_dir or "").strip()
    if not working_dir:
        return "github"
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return "github"
    if result.returncode != 0:
        return "github"
    return detect_platform_from_remote(result.stdout.strip())


def auth_error_hint(platform: Optional[str], status: int = 0) -> str:
    """根据平台与状态码给出认证提示。"""
    platform = normalize_platform(platform)
    cli = "gh auth login" if platform == "github" else "gitee auth login"
    host = "GitHub" if platform == "github" else "Gitee"
    if status in (401, 403):
        return (
            f"认证失败（token 缺失或无效）。请先在终端执行 {cli} 登录 {host}，"
            f"或用 {cli.split()[0]} auth status 查看登录状态。"
        )
    return ""
