"""gh 插件工具类的 plugin/api.py 加载辅助。

工具类运行在 agent 进程（由 register_tool_by_file 加载，tools/ 在 sys.path）。
plugin/api.py 是插件私有功能层（运行在 gateway，供前端代理调用），不在 sys.path。
本模块用 importlib 按文件路径加载 plugin/api.py，供工具类薄封装调用。

本模块无工具类，register_tool_by_file 会将其跳过（不注册），仅作共享辅助。
"""

import importlib.util
import sys
from pathlib import Path

_GH_PLUGIN_DIR = Path(__file__).resolve().parent.parent  # builtin/plugins/gh
_API_PATH = _GH_PLUGIN_DIR / "plugin" / "api.py"

_api_module = None


def load_api():
    """加载并返回 plugin/api.py 模块（缓存，避免重复加载）。"""
    global _api_module
    if _api_module is not None:
        return _api_module
    spec = importlib.util.spec_from_file_location("gh_plugin_api", _API_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {_API_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["gh_plugin_api"] = module
    spec.loader.exec_module(module)
    _api_module = module
    return module


def resolve_repo_arg(args: dict) -> tuple:
    """解析工具调用的 repo 参数。

    显式指定 repo 则用之；否则从当前工作目录（os.getcwd()）解析 git remote
    origin 得到仓库。解析失败返回 (repo="", error)，由工具类提示显式传 repo。
    返回 (repo, error)。
    """
    import os

    repo = str((args or {}).get("repo") or "").strip()
    if repo:
        return repo, ""
    api = load_api()
    try:
        resolved = api.resolve_repo(os.getcwd())
    except Exception:
        resolved = {}
    repo = str((resolved or {}).get("repo") or "").strip()
    if not repo:
        return (
            "",
            "未指定仓库（当前目录不是 git 仓库或缺少 origin remote），请显式传入 repo 参数",
        )
    return repo, ""
