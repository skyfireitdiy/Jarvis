# -*- coding: utf-8 -*-
"""
md-preview 插件私有功能层（运行于 gateway，供前端 function-call 代理调用）。

本模块演示 context_menu_items 扩展点的回调：目录树右键菜单点击「Markdown 预览」
后，前端经 POST /api/plugins/{node_id}/function-call 调用本模块的
preview_markdown 函数，读取指定 .md 文件的**原始 Markdown 文本**返回。

渲染统一在前端完成：前端复用会话消息的渲染管线（marked + highlight.js +
mermaid/dot/plantuml 浏览器端图表渲染），保证预览效果与聊天会话一致，
特别是 Mermaid 流程图、Graphviz 等图表支持。

安全边界：
  - 只允许读取 .md/.markdown 后缀的文件（避免任意文件读取）；
  - 只允许读取绝对路径（拒绝相对路径/空路径）；
  - 仅 PUBLIC_FUNCTIONS 白名单内的函数可被 gateway 前端代理调用。
"""
import os
from pathlib import Path

# 允许的后缀（小写）
_ALLOWED_SUFFIXES = (".md", ".markdown")


def _is_safe_md_path(path):
    """校验路径是否为可预览的 Markdown 文件绝对路径。

    规则：非空、绝对路径、后缀为 .md/.markdown、文件存在且为普通文件。
    """
    if not path or not isinstance(path, str):
        return False
    path = path.strip()
    if not path:
        return False
    # 只允许绝对路径
    if not os.path.isabs(path):
        return False
    # 只允许 .md/.markdown 后缀
    if not path.lower().endswith(_ALLOWED_SUFFIXES):
        return False
    p = Path(path)
    if not p.is_file():
        return False
    return True


def preview_markdown(path: str = "", **_kwargs):
    """读取 Markdown 文件，返回原始文本（渲染由前端会话管线完成）。

    参数（由前端 runPluginFileTreeContextAction 传入）：
        path: 目标 .md 文件绝对路径
    返回：{ success, data: { content, path, title } }
    """
    if not _is_safe_md_path(path):
        return {
            "success": False,
            "error": {
                "code": "INVALID_PATH",
                "message": "仅支持预览工作目录内的 .md/.markdown 文件",
            },
        }
    file_path = Path(str(path).strip())
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "success": False,
            "error": {
                "code": "READ_FAILED",
                "message": f"读取文件失败: {e}",
            },
        }
    return {
        "success": True,
        "data": {
            "content": content,
            "path": str(file_path),
            "title": file_path.name,
        },
    }


# 可被 gateway 前端代理调用的白名单（function-call 端点只允许这些函数）
PUBLIC_FUNCTIONS = [
    "preview_markdown",
]
