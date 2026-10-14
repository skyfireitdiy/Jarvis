# -*- coding: utf-8 -*-
"""
工具函数（jarvis_agent.utils）

- join_prompts: 统一的提示拼接策略（支持纯文本和多模态内容）
- is_auto_complete: 统一的自动完成标记检测
- fix_tool_call_with_llm: 使用大模型修复工具调用格式
"""

from enum import Enum
from typing import Any, List
from typing import Iterable
from typing import Optional, Union
from typing import cast
import pathlib


from jarvis.jarvis_platform.content_types import ContentBlock
from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_utils.tag import ot


def join_prompts(
    parts: Iterable[Union[str, List[ContentBlock]]],
) -> Union[str, List[ContentBlock]]:
    """
    将多个提示片段按统一规则拼接：
    - 支持纯文本和多模态内容
    - 如果所有部分都是字符串，返回拼接后的字符串
    - 如果任何部分是多模态内容，返回合并后的内容块列表
    """
    try:
        all_parts = list(parts)
    except Exception:
        # 防御性处理：若 parts 不可迭代或出现异常，直接返回空字符串
        return ""

    # 检查是否有多模态内容
    has_multimodal = any(isinstance(p, list) for p in all_parts)

    if not has_multimodal:
        # 所有部分都是字符串，使用原有逻辑
        non_empty: list[str] = [p for p in all_parts if isinstance(p, str) and p]
        return "\n\n".join(non_empty)

    # 有多模态内容，需要合并
    result_blocks: List[ContentBlock] = []

    for part in all_parts:
        if isinstance(part, str):
            if part.strip():
                # 将非空字符串转换为文本内容块
                result_blocks.append({"type": "text", "text": part})
        elif isinstance(part, list):
            # 直接添加内容块列表
            result_blocks.extend(part)

    return result_blocks


def is_auto_complete(response: str) -> bool:
    """
    检测是否包含自动完成标记。
    当前实现：包含 ot('!!!COMPLETE!!!') 即视为自动完成。
    """
    try:
        return ot("!!!COMPLETE!!!") in response
    except Exception:
        # 防御性处理：即使 ot 出现异常，也不阻塞主流程
        return "!!!COMPLETE!!!" in response


def normalize_next_action(next_action: Any) -> str:
    """
    规范化下一步动作为字符串:
    - 如果是 Enum, 返回其 value（若为字符串）
    - 如果是 str, 原样返回
    - 其他情况返回空字符串
    """
    try:
        if isinstance(next_action, Enum):
            value = getattr(next_action, "value", None)
            return value if isinstance(value, str) else ""
        if isinstance(next_action, str):
            return next_action
        return ""
    except Exception:
        return ""


def build_fix_prompt(content: str, error_msg: str, tool_usage: str) -> str:
    """构建修复工具调用的提示词

    参数:
        content: 包含错误工具调用的内容
        error_msg: 错误消息
        tool_usage: 工具使用说明

    返回:
        str: 构建好的提示字符串
    """
    return f"""你上次的工具调用格式有误，请根据工具使用说明修正以下内容。

**错误信息：**
{error_msg}

**工具使用说明：**
{tool_usage}

**错误的工具调用内容：**
{content}

请修正上述工具调用内容，确保：
一、输出纯 JSON 对象，包含 name 与 arguments 字段
二、JSON 格式正确，包含 name、arguments、want 三个字段
三、若使用多行字符串，直接换行即可

直接返回修正后的完整工具调用内容，不要添加其他文字。"""


def fix_tool_call_with_llm(content: str, agent: Any, error_msg: str) -> Optional[str]:
    """使用大模型修复工具调用格式

    参数:
        content: 包含错误工具调用的内容
        agent: Agent实例，用于调用大模型
        error_msg: 错误消息

    返回:
        Optional[str]: 修复后的内容，如果修复失败则返回None
    """
    try:
        # 获取工具使用说明
        tool_usage = agent.get_tool_usage_prompt()

        # 构建修复提示
        fix_prompt = build_fix_prompt(content, error_msg, tool_usage)

        # 调用大模型修复
        PrettyOutput.auto_print("🤖 尝试使用大模型修复工具调用格式...")
        fixed_content: Any = agent.model.chat_until_success(fix_prompt)

        # 类型检查：确保返回的是字符串
        if fixed_content and isinstance(fixed_content, str):
            PrettyOutput.auto_print("✅ 大模型修复完成")
            # 类型断言：确保返回类型匹配函数签名
            return cast(Optional[str], fixed_content)
        else:
            PrettyOutput.auto_print("❌ 大模型修复失败：返回内容为空")
            return None

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 大模型修复失败：{str(e)}")
        return None


def _compare_versions(v1: str, v2: str) -> Optional[int]:
    """比较两个语义化版本号。

    参数:
        v1: 第一个版本号（如 "1.2.0"）
        v2: 第二个版本号（如 "1.3.0"）

    返回:
        int: 1 表示 v1 > v2，0 表示相等，-1 表示 v1 < v2
        None: 任一版本号无法解析时返回 None
    """
    try:
        from packaging.version import Version

        ver1 = Version(v1)
        ver2 = Version(v2)
        if ver1 > ver2:
            return 1
        if ver1 < ver2:
            return -1
        return 0
    except Exception:
        return None


def _check_version_constraint(version: str, constraint: str) -> bool:
    """检查版本是否满足版本约束。

    支持的约束格式（可逗号组合多个条件）：
        "1.2.0"          精确版本
        ">=1.2.0"        大于等于
        ">1.2.0"         大于
        "<=1.2.0"        小于等于
        "<1.2.0"         小于
        "==1.2.0"        精确等于
        "*"              任意版本
        ">=1.0.0,<2.0.0" 区间（逗号分隔多个条件，需全部满足）

    参数:
        version: 待检查的版本号
        constraint: 版本约束表达式

    返回:
        bool: 满足约束返回 True，否则返回 False
    """
    if not version or not constraint:
        return True
    constraint = constraint.strip()
    if not constraint or constraint == "*":
        return True

    # 拆分逗号分隔的多个条件，需全部满足
    parts = [p.strip() for p in constraint.split(",") if p.strip()]
    if not parts:
        return True

    from packaging.version import Version

    try:
        ver = Version(version)
    except Exception:
        return False

    for part in parts:
        # 解析操作符
        if part.startswith(">="):
            op, target = ">=", part[2:].strip()
        elif part.startswith("<="):
            op, target = "<=", part[2:].strip()
        elif part.startswith("=="):
            op, target = "==", part[2:].strip()
        elif part.startswith(">"):
            op, target = ">", part[1:].strip()
        elif part.startswith("<"):
            op, target = "<", part[1:].strip()
        else:
            op, target = "==", part

        try:
            target_ver = Version(target)
        except Exception:
            # 约束目标无法解析，视为不满足
            return False

        cmp = (ver > target_ver) - (ver < target_ver)
        if op == ">=" and cmp < 0:
            return False
        if op == "<=" and cmp > 0:
            return False
        if op == "==" and cmp != 0:
            return False
        if op == ">" and cmp <= 0:
            return False
        if op == "<" and cmp >= 0:
            return False

    return True


def _resolve_plugin_dep_url(url: str, tag: Optional[str], branch: Optional[str]) -> str:
    """解析插件依赖的 git 来源地址。

    Jarvis 插件安装仅支持 git 来源（Issue #213）。本函数把依赖配置的
    url/tag/branch 解析为可供 `git clone` 的仓库地址：

    - 若 url 是 git 仓库地址（https://github.com/owner/repo 或 git@host:owner/repo.git），
      返回该仓库地址（去掉尾部斜杠，保留 .git 后缀以便 git 识别）。
    - 若提供了 branch/tag，返回 `url#branch` 形式，供安装逻辑提取分支后
      `git clone --branch <branch>` 使用。
    - 非 git 仓库地址（如 http 下载链接）原样返回（由 install_plugin 拒绝）。

    参数:
        url: 依赖插件配置的 url
        tag: 依赖插件配置的 tag（可选）
        branch: 依赖插件配置的 branch（可选）

    返回:
        str: 解析后的 git 克隆地址
    """
    if not url:
        return url
    url = url.rstrip("/")
    # 仅当 url 是 git 仓库地址时才构造分支后缀；否则原样返回（由安装逻辑拒绝）
    if not _is_git_repo_url(url):
        return url
    ref = branch or tag
    if ref:
        return f"{url}#{ref}"
    return url


def _is_git_repo_url(url: str) -> bool:
    """判断 url 是否为 git 仓库地址（https/git/ssh 形式）。

    形如：
        https://github.com/owner/repo
        https://github.com/owner/repo.git
        git@github.com:owner/repo.git
        ssh://git@host/owner/repo.git
    """
    if not url:
        return False
    url = url.strip()
    if url.startswith(("git@", "ssh://", "git://", "file://")):
        return True
    if url.startswith(("http://", "https://")):
        # 去掉可能的 #branch 后缀后判断是否为仓库路径（含 owner/repo 结构）
        base = url.split("#", 1)[0].rstrip("/")
        return ".git" in base or _looks_like_repo_path(base)
    # 本地路径：目录内含 .git 视为 git 仓库（供本地开发/测试使用）
    try:
        import os

        return os.path.isdir(os.path.join(url.split("#", 1)[0], ".git"))
    except Exception:
        return False


def _looks_like_repo_path(url: str) -> bool:
    """粗略判断 http(s) URL 是否形如 <host>/<owner>/<repo> 的仓库路径。"""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if not parsed.hostname or not parsed.path:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    return len(parts) >= 2


def _check_plugin_dependencies(dependencies: Any, plugins_dir: Any) -> list:
    """检查插件的插件依赖是否已安装且版本兼容。

    参数:
        dependencies: 插件依赖声明，可为 dict（{插件名: 版本约束}）
            或 list（[{"name":..., "version":...}]）
        plugins_dir: 已安装插件的目录

    返回:
        list: 不满足的依赖列表，每项为 dict（含 type/name/version_constraint/installed/reason，
            可选 url/tag/branch 用于依赖自动安装）
    """
    if not dependencies:
        return []

    import yaml

    # 归一化为 dict {name: {"version":..., "url":..., "tag":..., "branch":...}}
    # 简写形式 {name: "version"} 或 [{name, version}] 仍支持
    dep_map: dict = {}
    if isinstance(dependencies, dict):
        for k, v in dependencies.items():
            name = str(k)
            if isinstance(v, dict):
                # 完整形式：{name: {version, url, tag, branch}}
                dep_map[name] = {
                    "version": str(v.get("version")) if v.get("version") else "*",
                    "url": v.get("url"),
                    "tag": v.get("tag"),
                    "branch": v.get("branch"),
                }
            else:
                # 简写形式：{name: "version"}
                dep_map[name] = {
                    "version": str(v) if v else "*",
                    "url": None,
                    "tag": None,
                    "branch": None,
                }
    elif isinstance(dependencies, list):
        for item in dependencies:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    dep_map[str(name)] = {
                        "version": str(item.get("version") or "*"),
                        "url": item.get("url"),
                        "tag": item.get("tag"),
                        "branch": item.get("branch"),
                    }
    else:
        return []

    missing = []
    for dep_name, dep_info in dep_map.items():
        constraint = dep_info["version"]
        dep_url = dep_info.get("url")
        dep_tag = dep_info.get("tag")
        dep_branch = dep_info.get("branch")
        dep_dir = plugins_dir / dep_name
        installed_version = None
        if dep_dir.exists():
            config_file = dep_dir / "config.yaml"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f)
                        if isinstance(cfg, dict):
                            installed_version = cfg.get("version")
                except Exception:
                    installed_version = None

        if not dep_dir.exists():
            missing.append(
                {
                    "type": "plugins",
                    "name": dep_name,
                    "version_constraint": constraint,
                    "installed": None,
                    "reason": "未安装",
                    "url": dep_url,
                    "tag": dep_tag,
                    "branch": dep_branch,
                }
            )
        elif installed_version is None:
            # 已安装但无版本号，无法校验，视为满足（保守）
            continue
        elif not _check_version_constraint(str(installed_version), constraint):
            missing.append(
                {
                    "type": "plugins",
                    "name": dep_name,
                    "version_constraint": constraint,
                    "installed": str(installed_version),
                    "reason": f"版本不兼容（已装 {installed_version}，需 {constraint}）",
                    "url": dep_url,
                    "tag": dep_tag,
                    "branch": dep_branch,
                }
            )

    return missing


def _check_python_dependencies(dependencies: Any) -> list:
    """检查插件的 Python 包依赖是否已安装且版本兼容。

    参数:
        dependencies: Python 包依赖声明，可为 dict（{包名: 版本约束}）
            或 list（[{"name":..., "version":...}]）

    返回:
        list: 不满足的依赖列表，每项为 dict（含 type/name/version_constraint/installed/reason）
    """
    if not dependencies:
        return []

    import importlib.metadata
    import importlib.util

    # 归一化为 dict {name: constraint}
    dep_map: dict = {}
    if isinstance(dependencies, dict):
        dep_map = {str(k): (str(v) if v else "*") for k, v in dependencies.items()}
    elif isinstance(dependencies, list):
        for item in dependencies:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    dep_map[str(name)] = str(item.get("version") or "*")
    else:
        return []

    missing = []
    for pkg_name, constraint in dep_map.items():
        # 检查包是否可导入（兼容包名与模块名不同，如 Pillow -> PIL）
        try:
            spec = importlib.util.find_spec(pkg_name)
            installed = spec is not None
        except Exception:
            installed = False

        installed_version = None
        if installed:
            try:
                installed_version = importlib.metadata.version(pkg_name)
            except Exception:
                installed_version = None

        if not installed:
            missing.append(
                {
                    "type": "python",
                    "name": pkg_name,
                    "version_constraint": constraint,
                    "installed": None,
                    "reason": "未安装",
                }
            )
        elif installed_version is None:
            # 已安装但无法读取版本号，无法校验，视为满足（保守）
            continue
        elif not _check_version_constraint(str(installed_version), constraint):
            missing.append(
                {
                    "type": "python",
                    "name": pkg_name,
                    "version_constraint": constraint,
                    "installed": str(installed_version),
                    "reason": f"版本不兼容（已装 {installed_version}，需 {constraint}）",
                }
            )

    return missing


def _check_command_dependencies(dependencies: Any) -> list:
    """检查插件的系统命令依赖是否存在于 PATH 中。

    参数:
        dependencies: 命令依赖声明，可为 list（["git", "jq"]）
            或 dict（{"git": 任意值}）或 list（[{"name": "git"}]）

    返回:
        list: 不满足的依赖列表，每项为 dict（含 type/name/version_constraint/installed/reason）
    """
    if not dependencies:
        return []

    import shutil

    # 归一化为命令名列表
    cmd_names = []
    if isinstance(dependencies, list):
        for item in dependencies:
            if isinstance(item, str):
                cmd_names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                cmd_names.append(str(item["name"]))
    elif isinstance(dependencies, dict):
        cmd_names = [str(k) for k in dependencies.keys()]

    missing = []
    for cmd in cmd_names:
        if shutil.which(cmd) is None:
            missing.append(
                {
                    "type": "commands",
                    "name": cmd,
                    "version_constraint": "*",
                    "installed": None,
                    "reason": "命令不存在",
                }
            )

    return missing


def _check_dependencies(dependencies: Any, plugins_dir: Any) -> list:
    """检查插件的依赖是否已满足。

    支持三类依赖：
        1. plugins: 插件依赖（其他已安装的 Jarvis 插件）
        2. python:  Python 包依赖（可用 importlib 导入）
        3. commands: 系统命令依赖（PATH 中可找到）

    参数:
        dependencies: config.yaml 中的 dependencies 字段。
            新格式为 dict，含 plugins/python/commands 子键；
            旧格式为扁平 dict（{插件名: 版本约束}）或 list，视为插件依赖。
        plugins_dir: 已安装插件的目录

    返回:
        list: 不满足的依赖列表，每项为 dict（含 type/name/version_constraint/installed/reason）
    """
    if not dependencies:
        return []

    # 归一化分类：新格式用 plugins/python/commands 子键，旧格式视为插件依赖
    if isinstance(dependencies, dict) and any(
        k in dependencies for k in ("plugins", "python", "commands")
    ):
        plugin_deps = dependencies.get("plugins")
        python_deps = dependencies.get("python")
        command_deps = dependencies.get("commands")
    else:
        plugin_deps = dependencies
        python_deps = None
        command_deps = None

    missing = []
    missing.extend(_check_plugin_dependencies(plugin_deps, plugins_dir))
    missing.extend(_check_python_dependencies(python_deps))
    missing.extend(_check_command_dependencies(command_deps))

    return missing


def _scaffold_slug(name: str) -> str:
    """把插件名规范化为安全的目录/文件名 slug（小写、连字符分隔）。"""
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").lower()
    return slug or "my-plugin"


def _scaffold_class_name(name: str) -> str:
    """把插件名转成工具类名（CamelCase + Tool 后缀）。"""
    parts = _scaffold_slug(name).split("-")
    return "".join(p.capitalize() for p in parts) + "Tool"


def _scaffold_tool_module_name(name: str) -> str:
    """把插件名转成工具模块文件名（文件名 stem 必须等于工具 name）。"""
    return _scaffold_slug(name) + "_tool"


def scaffold_plugin(
    name: str, output_dir: Optional[str] = None, init_git: bool = True
) -> Optional[str]:
    """生成一个符合 Jarvis 加载约定的插件脚手架目录。

    参数:
        name: 插件名称（用于生成目录名、config.yaml 的 name、工具/规则/Agent 命名）
        output_dir: 输出目录（默认当前工作目录）
        init_git: 是否初始化 git 仓库（默认 True，生成 .gitignore/LICENSE 并 git init + 初始提交；
            git 不可用或提交失败时优雅降级，不抛异常）

    返回:
        str: 生成的插件目录绝对路径；失败返回 None

    生成的骨架包含:
        config.yaml      插件配置（含全部扩展点示例）
        README.md        开发者文档
        .gitignore       标准 Python 忽略项
        LICENSE          MIT 开源协议（与 config.yaml 的 license 一致）
        rules/           规则目录（YAML front matter 模板）
        tools/           工具目录（class XxxTool 模板，name==文件名 stem）
        agents/          Agent 定义目录模板
        orchestration/   编排流水线模板
        frontend/        前端扩展（admin_tab.js / sidebar_view.js，用 window.Vue）
        plugin/          插件私有功能（api.py 模板，含 PUBLIC_FUNCTIONS 白名单）
    """
    import os
    from pathlib import Path

    slug = _scaffold_slug(name)
    base_dir = Path(output_dir or os.getcwd()).resolve()
    plugin_dir = base_dir / slug

    # 目标目录已存在且非空则拒绝，避免误覆盖
    if plugin_dir.exists() and any(plugin_dir.iterdir()):
        PrettyOutput.auto_print(f"❌ 目标目录已存在且非空: {plugin_dir}")
        return None

    tool_class = _scaffold_class_name(name)
    tool_module = _scaffold_tool_module_name(name)
    # 插件私有功能函数名基（Python 标识符，连字符替换为下划线）
    func_base = slug.replace("-", "_")

    # 目录结构
    for sub in ("rules", "tools", "agents", "orchestration", "frontend", "plugin"):
        (plugin_dir / sub).mkdir(parents=True, exist_ok=True)

    # ---------- .gitignore ----------
    gitignore = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# 虚拟环境
.venv/
venv/
env/
ENV/

# 测试与覆盖率
.pytest_cache/
.coverage
.coverage.*
htmlcov/
.tox/
.nox/
.mypy_cache/
.ruff_cache/
.hypothesis/

# 编辑器与 IDE
.idea/
.vscode/
*.swp
*.swo
.DS_Store

# Jarvis 本地运行产物
.jarviscache/
"""
    (plugin_dir / ".gitignore").write_text(gitignore, encoding="utf-8")

    # ---------- LICENSE ----------
    license_text = """MIT License

Copyright (c) 2026 {name}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""".replace("{name}", name)
    (plugin_dir / "LICENSE").write_text(license_text, encoding="utf-8")

    # ---------- config.yaml ----------
    config = f"""---
name: {slug}
description: {name}——请补充插件描述。
version: 0.1.0
license: MIT
builtin: true
# 扩展点说明（按需启用，路径用 {{{{plugin_dir}}}} 占位，运行时自动渲染）：
# - rules_load_dirs: 规则目录，规则文件带 YAML front matter（name/description）
# - tool_load_dirs: 工具目录，工具类 name 必须等于文件名 stem
# - agent_definition_dirs: Agent 定义目录（YAML 格式）
# - orchestration: 编排流水线（配合 OrganizeAgents + --task-file 消费）
# - frontend: 前端扩展点（admin_tabs/sidebar_views/tool_panels，JS 用 window.Vue）
# - plugin/: 插件私有功能（运行在 gateway，供前端代理调用，不暴露给 Agent）
#   api.py 末尾需定义 PUBLIC_FUNCTIONS 白名单，gateway 只允许调用白名单内函数。
# 私有配置隔离：除上述扩展点字段外，其余字段（name/version/dependencies/自定义业务字段）
# 会被隔离到全局配置 plugin_configs.<插件名>，不污染全局配置顶层、多插件同名私有字段互不覆盖；
# 插件可通过 get_plugin_config("<插件名>") 读取自己的私有配置。
rules_load_dirs:
  - "{{{{plugin_dir}}}}/rules"
tool_load_dirs:
  - "{{{{plugin_dir}}}}/tools"
# agent_definition_dirs:
#   - "{{{{plugin_dir}}}}/agents"
# 编排流水线模板声明（配合 @OrganizeAgents 自动发现，用户可直接选编号）
orchestration:
  - name: "{slug}-pipeline"
    description: "{name} 编排流水线"
    file: "{{{{plugin_dir}}}}/orchestration/{slug}_pipeline.yaml"
# frontend:
#   admin_tabs:
#     - id: {slug}-admin
#       title: "{name} 管理"
#       entry: admin_tab.js
#   sidebar_views:
#     - id: {slug}-view
#       title: "{name}"
#       entry: sidebar_view.js
# 依赖声明（可选，三类：plugins/python/commands）
# dependencies:
#   commands:
#     - git
"""
    (plugin_dir / "config.yaml").write_text(config, encoding="utf-8")

    # ---------- README.md ----------
    readme = f"""# {name}

> 由 `jarvis --new-plugin {name}` 生成的插件脚手架。

## 插件结构

```
{slug}/
├── config.yaml          # 插件配置（name/version + 扩展点声明）
├── README.md
├── rules/               # 规则（YAML front matter: name/description）
├── tools/               # 工具（class XxxTool, name==文件名 stem）
├── agents/              # Agent 定义（可选）
├── orchestration/       # 编排流水线（可选）
├── frontend/            # 前端扩展（可选，用 window.Vue）
└── plugin/              # 插件私有功能（可选，运行在 gateway，不暴露给 Agent）
```

## 开发指南

### 1. 工具（tools/）

工具文件是 Python 模块，类名 `{tool_class}`，**`name` 必须等于文件名 stem（`{tool_module}`）**，
否则注册表不会加载。实现 `check()`（静态方法，返回 bool 表示是否可用）与
`execute(args) -> {{"success", "stdout", "stderr"}}`。

### 2. 规则（rules/）

Markdown 文件，开头带 YAML front matter：

```yaml
---
name: <规则名>
description: <何时触发该规则>
---
```

### 3. 前端扩展（frontend/，可选）

前端 JS 是纯浏览器 ES module：**用 `window.Vue` 渲染，导出 default 组件，不要 `import 'vue'`**。
在 config.yaml 的 `frontend` 字段声明 `admin_tabs` / `sidebar_views` / `tool_panels`。

### 4. 编排（orchestration/，可选）

YAML 编排流水线，配合 `OrganizeAgents` 与 `jca -n --task-file` 消费。

### 5. 插件私有功能（plugin/，可选）

插件自己使用的功能实现（如 API 封装、业务纯函数）放在 `plugin/api.py`。
**不声明在 `tool_load_dirs`**，因此不会被 ToolRegistry 加载，Agent 看不到、调不到；
运行在 gateway，供前端代理调用。约定：

- 每个功能是纯函数，返回 dict：`{{"success": bool, "data": .../ "message": .../ "error": ...}}`。
- 模块末尾定义 `PUBLIC_FUNCTIONS: list[str]` 白名单，gateway 只允许调用白名单内函数。
- 前端通过 `POST /api/plugins/{{node_id}}/function-call` 调用（请求体 `{{plugin, function, arguments}}`）。

## 安装

```bash
jarvis --install-plugin {slug}
```

## 卸载

```bash
jarvis --uninstall-plugin {slug}
```
"""
    (plugin_dir / "README.md").write_text(readme, encoding="utf-8")

    # ---------- rules/<slug>.md ----------
    rule = f"""---
name: {slug}_rule
description: {name} 的规则模板。当需要遵循 {name} 插件的约定时触发。
---
# {name} 规则

在此编写规则正文。规则用于指导 Agent 在相关场景下的行为。
"""
    (plugin_dir / "rules" / f"{slug}.md").write_text(rule, encoding="utf-8")

    # ---------- tools/<tool_module>.py ----------
    tool = f'''"""
{name} 工具模板。

用途:
- 在此描述工具的用途与行为。

参数:
- 在此描述参数。

返回:
- success (bool)
- stdout (str)
- stderr (str)
"""
import json
from typing import Any
from typing import Dict


class {tool_class}:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "{tool_module}"
    description = "{name} 工具：请补充工具描述。"

    parameters = {{
        "type": "object",
        "properties": {{
            "input": {{
                "type": "string",
                "description": "输入内容",
            }},
        }},
        "required": ["input"],
    }}

    @staticmethod
    def check() -> bool:
        """工具是否可用（无外部依赖时始终返回 True）。"""
        return True

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            data = args.get("input")
            if not data or not isinstance(data, str):
                return {{
                    "success": False,
                    "stdout": "",
                    "stderr": "参数错误：input 必须是非空字符串",
                }}
            output = {{
                "echo": data,
                "note": "请在此实现实际逻辑",
            }}
            return {{
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }}
        except Exception as e:
            return {{
                "success": False,
                "stdout": "",
                "stderr": f"{tool_module} 执行异常: {{e}}",
            }}
'''
    (plugin_dir / "tools" / f"{tool_module}.py").write_text(tool, encoding="utf-8")

    # ---------- agents/<slug>.yaml ----------
    agent = f"""# {name} Agent 定义模板（可选，需在 config.yaml 启用 agent_definition_dirs）
name: {slug}_agent
description: {name} 的 Agent 角色定义。
system_prompt: |
  你是 {name} 插件的专用 Agent。
"""
    (plugin_dir / "agents" / f"{slug}.yaml").write_text(agent, encoding="utf-8")

    # ---------- orchestration/<slug>_pipeline.yaml ----------
    pipeline = f"""# {name} 编排流水线模板（可选，配合 OrganizeAgents + --task-file 消费）
# 参考 builtin/agent_orchestration/ 下的示例编排文件格式。
agents:
  - name: {slug}_worker
    role: 执行者
    task: 在此描述任务
"""
    (plugin_dir / "orchestration" / f"{slug}_pipeline.yaml").write_text(
        pipeline, encoding="utf-8"
    )

    # ---------- frontend/admin_tab.js ----------
    admin_tab_js = """// 管理页 Tab 组件模板（可选，需在 config.yaml 的 frontend.admin_tabs 声明）
// 约定：纯浏览器 ES module，用 window.Vue 渲染，导出 default 组件，不要 import 'vue'。
export default {
  name: "PluginAdminTab",
  template: `
    <div style="padding: 16px;">
      <h3>插件管理页</h3>
      <p>在此实现管理功能。</p>
    </div>
  `,
};
"""
    (plugin_dir / "frontend" / "admin_tab.js").write_text(
        admin_tab_js, encoding="utf-8"
    )

    # ---------- frontend/sidebar_view.js ----------
    sidebar_view_js = """// 侧边栏视图组件模板（可选，需在 config.yaml 的 frontend.sidebar_views 声明）
// 约定：纯浏览器 ES module，用 window.Vue 渲染，导出 default 组件，不要 import 'vue'。
export default {
  name: "PluginSidebarView",
  template: `
    <div style="padding: 16px;">
      <h3>插件视图</h3>
      <p>在此实现侧边栏视图内容。</p>
    </div>
  `,
};
"""
    (plugin_dir / "frontend" / "sidebar_view.js").write_text(
        sidebar_view_js, encoding="utf-8"
    )

    # ---------- plugin/api.py ----------
    api_py = f'''"""
{name} 插件私有功能层（运行在 gateway，供前端代理调用；不暴露给 Agent）。

本模块不声明在 tool_load_dirs，因此不会被 ToolRegistry 加载，Agent 看不到、调不到；
gateway 通过插件功能代理端点（POST /api/plugins/{{node_id}}/function-call）动态加载并调用。

约定：
- 每个功能是纯函数，返回 dict：{{"success": bool, "data": .../ "message": .../ "error": ...}}。
- 模块末尾定义 PUBLIC_FUNCTIONS 白名单，gateway 只允许调用白名单内函数。
"""
from typing import Any
from typing import Dict


def {func_base}_echo(text: str = "") -> Dict[str, Any]:
    """示例功能：回显输入文本。请在此实现实际业务逻辑。"""
    if not text:
        return {{"success": False, "error": "参数错误：text 不能为空"}}
    return {{"success": True, "data": {{"echo": text}}}}


# gateway 只允许调用白名单内的功能（防任意函数被调用）
PUBLIC_FUNCTIONS: list[str] = ["{func_base}_echo"]
'''
    (plugin_dir / "plugin" / "api.py").write_text(api_py, encoding="utf-8")

    # ---------- git 初始化 ----------
    if init_git:
        _init_plugin_git(plugin_dir, slug)

    PrettyOutput.auto_print(
        f"✅ 插件脚手架已生成: {plugin_dir}\n   安装: jarvis --install-plugin {slug}"
    )
    return str(plugin_dir)


def _init_plugin_git(plugin_dir: pathlib.Path, slug: str) -> None:
    """为插件脚手架初始化 git 仓库并创建初始提交。

    生成 .gitignore/LICENSE 后执行 git init、git add、git commit、分支改名为 main。
    git 不可用、未配置身份或提交失败时优雅降级（打印提示，不抛异常），
    保证脚手架生成本身永远成功。
    """
    import subprocess

    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )

    try:
        if _git("init", "-q").returncode != 0:
            PrettyOutput.auto_print("⚠️ git init 失败，跳过 git 初始化")
            return
        if _git("checkout", "-q", "-b", "main").returncode != 0:
            # 旧版 git 或已存在分支时忽略，继续后续步骤
            pass
        if _git("add", "-A").returncode != 0:
            PrettyOutput.auto_print("⚠️ git add 失败，跳过 git 初始化")
            return
        commit = _git(
            "commit", "-q", "-m", f"Initial commit for {slug} plugin scaffold"
        )
        if commit.returncode != 0:
            # 未配置 user.name/user.email 等场景：提示用户自行提交
            PrettyOutput.auto_print(
                "⚠️ git 初始提交失败（可能未配置 user.name/user.email），"
                "请在插件目录执行 git commit 完成首次提交"
            )
            return
        PrettyOutput.auto_print(
            f"✅ 已初始化 git 仓库并创建初始提交（分支 main）: {plugin_dir}"
        )
    except (OSError, subprocess.SubprocessError) as e:
        # git 未安装或执行异常：优雅降级，不阻断脚手架生成
        PrettyOutput.auto_print(f"⚠️ git 初始化失败（{e}），跳过 git 初始化")


def _remove_plugin_dir(path) -> None:
    """
    安全删除插件目录：软链接（含悬空软链接）用 os.unlink 只删链接本身，
    真实目录用 shutil.rmtree 递归删除。

    软链接安装的插件卸载/覆盖时，只应删除链接，绝不能误删其指向的本地源码。
    """
    import os
    import shutil

    if os.path.islink(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def _git_run(cwd, *args: str, check: bool = False, timeout: int = 120) -> "Any":
    """执行 git 命令，返回 CompletedProcess。

    cwd 为 None 时不指定工作目录。check=True 时失败抛 CalledProcessError。
    """
    import subprocess

    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        if check:
            raise RuntimeError(f"git 执行失败: {e}") from e
        # 构造一个失败结果
        return subprocess.CompletedProcess(cmd, 1, "", str(e))
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} 失败: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc


def _parse_git_source(source: str) -> "tuple[str, str]":
    """解析 git 安装来源，返回 (仓库 URL, 分支名)。

    支持 `url#branch` 形式指定分支（与依赖声明 url+branch/tag 一致）；
    未指定分支时默认 "main"。
    """
    source = (source or "").strip()
    if not source:
        return "", ""
    if "#" in source:
        url, _, branch = source.partition("#")
        return url.strip().rstrip("/"), (branch or "main").strip()
    return source.rstrip("/"), "main"


def _git_clone_plugin(url: str, branch: str, dest: "pathlib.Path") -> None:
    """把 git 仓库克隆到 dest 目录（保留 .git 元数据）。

    失败时抛 RuntimeError。
    """
    import os

    args = ["clone", "--quiet"]
    if branch:
        args += ["--branch", branch]
    # 浅克隆（--depth 1）不支持本地仓库（file:// 或本地路径），仅对远程 URL 使用
    is_local = url.startswith("file://") or os.path.isdir(url.split("#", 1)[0])
    if not is_local:
        args += ["--depth", "1"]
    args += [url, str(dest)]
    proc = _git_run(None, *args)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git clone 失败: {proc.stderr.strip() or proc.stdout.strip()}"
        )


def _read_plugin_source(plugin_dir) -> "Optional[str]":
    """读取插件目录记录的来源 URL（.source 文件）。不存在返回 None。"""
    from pathlib import Path

    source_file = Path(plugin_dir) / ".source"
    try:
        if source_file.exists():
            return source_file.read_text(encoding="utf-8").strip() or None
    except Exception:
        pass
    return None


def _read_plugin_branch(plugin_dir) -> str:
    """读取插件目录记录的安装分支（.git-branch 文件），默认 "main"。"""
    from pathlib import Path

    branch_file = Path(plugin_dir) / ".git-branch"
    try:
        if branch_file.exists():
            branch = branch_file.read_text(encoding="utf-8").strip()
            if branch:
                return branch
    except Exception:
        pass
    return "main"


# 插件生命周期钩子时机（config.yaml 的 hooks 字段键名）。
# 每个时机对应一个命令列表，在插件安装/升级/卸载的对应阶段执行。
PLUGIN_HOOK_STAGES = frozenset(
    {
        "pre-install",
        "post-install",
        "pre-update",
        "post-update",
        "pre-uninstall",
        "post-uninstall",
    }
)


def _read_plugin_hooks(plugin_dir) -> dict:
    """读取插件 config.yaml 的 hooks 私有配置字段。

    返回:
        dict: {时机: [命令, ...]}；无 hooks 字段或解析失败时返回空 dict。
    """
    from pathlib import Path

    config_file = Path(plugin_dir) / "config.yaml"
    if not config_file.exists():
        return {}
    try:
        import yaml

        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict):
            return {}
        hooks = config.get("hooks")
        if not isinstance(hooks, dict):
            return {}
        result: dict = {}
        for stage, commands in hooks.items():
            if stage not in PLUGIN_HOOK_STAGES:
                continue
            if isinstance(commands, str):
                commands = [commands]
            if isinstance(commands, list):
                cleaned = [c for c in commands if isinstance(c, str) and c.strip()]
                if cleaned:
                    result[stage] = cleaned
        return result
    except Exception:
        return {}


def _run_plugin_hooks(plugin_dir, stage: str, phase: str = "pre") -> bool:
    """执行插件生命周期钩子命令。

    在插件安装/升级/卸载的对应时机执行 config.yaml 的 hooks 字段声明的命令。
    命令以插件目录为工作目录、经 shell 执行（等同信任插件代码本身）。

    参数:
        plugin_dir: 插件目录（Path 或 str）
        stage: 钩子时机，如 "pre-install" / "post-update"
        phase: 阶段，决定失败处理：
            - "pre"：前置钩子失败返回 False（调用方应中止操作，避免半成品状态）
            - "post"：后置钩子失败仅警告并返回 True（主体操作已完成）

    返回:
        bool: 钩子全部执行成功返回 True；pre 阶段失败返回 False；
            无钩子声明或执行出错时按对应阶段规则返回。
    """
    from pathlib import Path

    hooks = _read_plugin_hooks(plugin_dir)
    commands = hooks.get(stage)
    if not commands:
        return True
    return _run_plugin_hook_commands(commands, Path(plugin_dir), stage, phase=phase)


def _run_plugin_hook_commands(
    commands, plugin_dir, stage: str, phase: str = "pre"
) -> bool:
    """执行一组插件生命周期钩子命令（命令已从 config.yaml 预读）。

    供 post-uninstall 等场景使用：插件目录已删除，无法再读取 config.yaml，
    需在删除前预读命令后传入执行。

    参数:
        commands: 命令字符串列表
        plugin_dir: 工作目录（Path 或 str）
        stage: 钩子时机，用于日志展示
        phase: 阶段，决定失败处理（同 _run_plugin_hooks）

    返回:
        bool: 全部成功返回 True；pre 阶段失败返回 False
    """
    import subprocess

    from pathlib import Path

    if not commands:
        return True

    plugin_dir = Path(plugin_dir)
    stage_label = stage.replace("-", " ")
    for cmd in commands:
        PrettyOutput.auto_print(
            f"⚙️  执行插件{stage_label}钩子: {cmd}（目录: {plugin_dir}）"
        )
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(plugin_dir),
                shell=True,  # nosec B602 - 钩子由插件作者声明，等同信任插件代码
                capture_output=True,
                text=True,
                timeout=300,
            )
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 插件{stage_label}钩子执行异常: {e}")
            if phase == "pre":
                return False
            continue
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            PrettyOutput.auto_print(
                f"❌ 插件{stage_label}钩子执行失败（退出码 {proc.returncode}）: "
                f"{detail or '无输出'}"
            )
            if phase == "pre":
                return False
        elif proc.stdout.strip():
            PrettyOutput.auto_print(f"📋 钩子输出: {proc.stdout.strip()}")
    return True


def _write_plugin_source(plugin_dir, url: str, branch: str) -> None:
    """记录 git 来源元数据（.source + .git-branch）。"""
    from pathlib import Path

    try:
        (Path(plugin_dir) / ".source").write_text(url, encoding="utf-8")
        (Path(plugin_dir) / ".git-branch").write_text(branch, encoding="utf-8")
    except Exception as e:
        from jarvis.jarvis_utils.exception_utils import save_exception

        save_exception(e, module="jarvis_agent.utils", function="_write_plugin_source")


def install_plugin(
    source_path: str,
    force: bool = False,
    source_url: Optional[str] = None,
    _installing_deps: Optional[set] = None,
) -> bool:
    """安装插件到 Jarvis 数据目录。

    参数:
        source_path: 插件来源，支持三种类型：
            - git 仓库地址（https://github.com/owner/repo、git@host:owner/repo.git、
              file://...、本地目录含 .git），可用 `url#branch` 指定分支（默认 main）。
              安装后保留 .git 元数据，支持自动检测更新 / 升级。
            - 本地目录（不含 .git）：建立软链接，本地代码更新后立即生效，不支持更新检测。
            - 压缩文件（.zip/.tar/.tar.gz/.tgz）：解压安装，不支持更新检测。
            链接（http(s) URL）仅支持 git 仓库地址；非 git 的 http(s) 下载链接会被拒绝。
        force: 是否强制覆盖已安装的插件（忽略版本比较），默认 False
        source_url: 来源 URL（可选），git 安装成功后记录到插件目录，供升级使用
        _installing_deps: 内部参数，记录正在自动安装的依赖插件名集合，用于防止依赖递归死循环

    返回:
        bool: 安装成功返回 True，失败返回 False

    功能:
        1. 校验插件是否包含 config.yaml
        2. 按来源类型安装：git 克隆（保留 .git）、本地目录软链接、压缩文件解压
        3. 插件名从 config.yaml 的 name 字段获取，若无则使用目录名/文件名
        4. 版本控制：高版本插件可覆盖低版本，低版本不能覆盖高版本
        5. force=True 时忽略版本比较，强制覆盖
        6. git 来源记录来源元数据（.source 仓库地址 + .git-branch 分支），供更新检测/升级
    """
    import os
    import shutil
    import tarfile
    import zipfile
    import tempfile
    import yaml
    from pathlib import Path

    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.exception_utils import save_exception
    from jarvis.jarvis_utils.output import PrettyOutput

    temp_dir = None  # 预初始化，确保 except 分支可访问（ty 推断局限）

    # 判断来源类型：git 仓库 / 本地目录 / 压缩文件
    is_git = _is_git_repo_url(source_path)
    url: str = ""
    branch: str = ""
    source = None
    if is_git:
        # git 仓库来源：解析 url + branch，准备 git clone
        url, branch = _parse_git_source(source_path)
    else:
        # 非 git 来源：http(s) 链接仅支持 git 仓库，直接拒绝；否则按本地路径处理
        stripped = (source_path or "").strip()
        if stripped.startswith(("http://", "https://")):
            PrettyOutput.auto_print(
                "❌ 链接来源仅支持 git 仓库地址（如 https://github.com/owner/repo），"
                "不支持 http 下载链接"
            )
            return False
        source = Path(source_path).resolve()
        if not source.exists():
            PrettyOutput.auto_print(f"❌ 插件源路径不存在: {source_path}")
            return False

    try:
        # 获取 Jarvis 数据目录下的 plugins 目录
        data_dir = Path(get_data_dir())
        plugins_dir = data_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # 准备插件源目录与安装方式
        plugin_source_dir = None
        install_mode = None  # 'git' | 'symlink' | 'copy'
        if is_git:
            # git 来源：clone 到临时目录（保留 .git 元数据）
            temp_dir = tempfile.mkdtemp(prefix="jarvis_plugin_")
            clone_dest = Path(temp_dir) / "repo"
            try:
                _git_clone_plugin(url, branch, clone_dest)
            except RuntimeError as e:
                PrettyOutput.auto_print(f"❌ {str(e)}")
                return False
            plugin_source_dir = clone_dest
            install_mode = "git"
        else:
            assert source is not None  # 非 git 来源已在 try 外解析
            if source.is_dir():
                # 本地目录：软链接安装（本地代码更新后立即生效）
                plugin_source_dir = source
                install_mode = "symlink"
            elif source.is_file():
                # 压缩文件：解压安装
                suffixes = [s.lower() for s in source.suffixes]
                is_zip = ".zip" in suffixes
                is_tar = ".tar" in suffixes or ".tgz" in suffixes
                if not is_zip and not is_tar:
                    PrettyOutput.auto_print(
                        "❌ 不支持的文件格式，仅支持 .tar/.tar.gz/.tgz/.zip"
                    )
                    return False
                temp_dir = tempfile.mkdtemp(prefix="jarvis_plugin_")
                if is_zip:
                    with zipfile.ZipFile(source, "r") as zf:
                        # 校验成员，防止 zip slip 路径穿越（成员名含 ../ 或绝对路径）
                        for member in zf.infolist():
                            member_path = os.path.normpath(member.filename)
                            if member_path.startswith(
                                ("..", "/")
                            ) or ".." in member_path.split("/"):
                                raise ValueError(
                                    f"zip member escapes dest dir: {member.filename}"
                                )
                        zf.extractall(temp_dir)  # nosec B202 - 上方已校验成员
                else:  # tar formats (including .tar.gz, .tgz)
                    with tarfile.open(source, "r:*") as tf:
                        # 使用 filter='data' 防止路径遍历攻击 (CVE-2007-4559)
                        tf.extractall(temp_dir, filter="data")  # nosec B202
                # 解压后，查找包含 config.yaml 的目录
                extracted_items = list(Path(temp_dir).iterdir())
                if len(extracted_items) == 1 and extracted_items[0].is_dir():
                    plugin_source_dir = extracted_items[0]
                else:
                    plugin_source_dir = Path(temp_dir)
                install_mode = "copy"
            else:
                PrettyOutput.auto_print("❌ 无效的源路径类型")
                return False

        # 校验是否包含 config.yaml
        config_file = plugin_source_dir / "config.yaml"
        if not config_file.exists():
            PrettyOutput.auto_print("❌ 插件缺少 config.yaml 文件")
            return False

        # 读取 config.yaml 获取插件名与版本
        plugin_version = None
        plugin_dependencies = None
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_content = yaml.safe_load(f)
                if isinstance(config_content, dict):
                    plugin_name = config_content.get("name", None)
                    plugin_version = config_content.get("version", None)
                    plugin_dependencies = config_content.get("dependencies", None)
                else:
                    plugin_name = None
        except Exception:
            plugin_name = None

        # 如果没有 name 字段，使用源目录名/文件名
        if not plugin_name:
            if install_mode == "git":
                plugin_name = plugin_source_dir.name
            else:
                assert source is not None  # symlink/copy 均为本地来源
                if install_mode == "symlink":
                    plugin_name = source.name
                else:  # copy（压缩文件）
                    plugin_name = source.stem
                    if plugin_name.endswith(".tar"):
                        plugin_name = plugin_name[:-4]

        # 安全处理：只保留文件名部分，防止路径遍历攻击
        plugin_name = Path(plugin_name).name

        # 目标安装目录
        target_dir = plugins_dir / plugin_name

        # 依赖检查：插件声明的依赖必须已安装且版本兼容。
        # 对带 url 的 plugins 依赖，未安装时自动 git clone 安装；无 url 或安装失败的仍拒绝。
        if plugin_dependencies:
            # 初始化正在安装的依赖集合（用于防止依赖递归死循环，如 A->B->A）
            if _installing_deps is None:
                _installing_deps = set()
            if plugin_name in _installing_deps:
                PrettyOutput.auto_print(
                    f"❌ 检测到循环依赖: 插件 {plugin_name} 正在安装中，终止以避免死循环"
                )
                return False
            _installing_deps.add(plugin_name)

            missing_deps = _check_dependencies(plugin_dependencies, plugins_dir)
            auto_install_failed = False
            for dep in missing_deps:
                # 仅对带 url 的插件依赖尝试自动安装
                if dep.get("type") == "plugins" and dep.get("url"):
                    PrettyOutput.auto_print(
                        f"⬇️  检测到未满足的插件依赖 [{dep['name']}]，正在自动安装..."
                    )
                    dep_url = _resolve_plugin_dep_url(
                        dep.get("url"), dep.get("tag"), dep.get("branch")
                    )
                    ok = install_plugin(
                        dep_url,
                        source_url=dep_url,
                        _installing_deps=_installing_deps,
                    )
                    if not ok:
                        PrettyOutput.auto_print(
                            f"❌ 自动安装插件依赖失败: {dep['name']}"
                        )
                        auto_install_failed = True
                    continue
                # 无 url 的插件依赖或 python/commands 依赖，无法自动安装，报错
                type_labels = {
                    "plugins": "插件",
                    "python": "Python 包",
                    "commands": "系统命令",
                }
                label = type_labels.get(dep.get("type"), "依赖")
                PrettyOutput.auto_print(
                    f"❌ 依赖未满足: [{label}] {dep['name']} "
                    f"(需 {dep['version_constraint']}): {dep['reason']}"
                )
                auto_install_failed = True

            # 重新检查依赖：自动安装后可能仍不满足（如版本不兼容、无 url 依赖）
            if auto_install_failed or _check_dependencies(
                plugin_dependencies, plugins_dir
            ):
                PrettyOutput.auto_print(
                    f"❌ 依赖检查失败: 插件 {plugin_name} 的以下依赖未满足"
                )
                for dep in _check_dependencies(plugin_dependencies, plugins_dir):
                    type_labels = {
                        "plugins": "插件",
                        "python": "Python 包",
                        "commands": "系统命令",
                    }
                    label = type_labels.get(dep.get("type"), "依赖")
                    PrettyOutput.auto_print(
                        f"  - [{label}] {dep['name']} (需 {dep['version_constraint']}): {dep['reason']}"
                    )
                return False

        # 执行 pre-install 钩子（从源目录 config.yaml 读取）。
        # 失败则中止安装，避免产生半成品安装状态。
        if not _run_plugin_hooks(plugin_source_dir, "pre-install", phase="pre"):
            PrettyOutput.auto_print(f"❌ pre-install 钩子失败，中止安装: {plugin_name}")
            return False

        # 如果目标目录已存在，进行版本控制：高版本可覆盖低版本，低版本不能覆盖高版本
        if target_dir.exists():
            installed_version = None
            installed_config_file = target_dir / "config.yaml"
            if installed_config_file.exists():
                try:
                    with open(installed_config_file, "r", encoding="utf-8") as f:
                        installed_config = yaml.safe_load(f)
                        if isinstance(installed_config, dict):
                            installed_version = installed_config.get("version", None)
                except Exception:
                    installed_version = None

            # 强制覆盖：忽略版本比较
            if force:
                PrettyOutput.auto_print(
                    f"⚠️  强制覆盖插件目录: {target_dir}（忽略版本比较）"
                )
                _remove_plugin_dir(target_dir)
            # 双方都有版本号时进行比较
            elif installed_version and plugin_version:
                cmp = _compare_versions(plugin_version, installed_version)
                if cmp is not None and cmp < 0:
                    PrettyOutput.auto_print(
                        f"❌ 拒绝安装: 新版本 v{plugin_version} 低于已安装版本 "
                        f"v{installed_version}（插件 {plugin_name}）"
                    )
                    return False
                if cmp is not None and cmp >= 0:
                    PrettyOutput.auto_print(
                        f"⚠️  插件目录已存在，将覆盖: {target_dir} "
                        f"(v{installed_version} -> v{plugin_version})"
                    )
                else:
                    # 版本无法解析，保守允许覆盖（保持向后兼容）
                    PrettyOutput.auto_print(f"⚠️  插件目录已存在，将覆盖: {target_dir}")
                _remove_plugin_dir(target_dir)
            else:
                # 已安装插件无版本号（旧格式）或新插件无版本号，允许覆盖以兼容旧插件
                PrettyOutput.auto_print(f"⚠️  插件目录已存在，将覆盖: {target_dir}")
                _remove_plugin_dir(target_dir)

        # - git：把克隆产物（含 .git）移动到目标目录，并记录来源元数据
        # - symlink：本地目录建立软链接（本地代码更新后立即生效），不写 .source
        # - copy：压缩文件解压产物复制（无本地持续更新需求）
        assert plugin_source_dir is not None  # 来源准备阶段已赋值
        if install_mode == "git":
            shutil.move(str(plugin_source_dir), str(target_dir))
            _write_plugin_source(target_dir, url, branch)
        elif install_mode == "symlink":
            assert source is not None  # symlink 仅本地目录来源
            os.symlink(source, target_dir)
        else:  # copy
            shutil.copytree(plugin_source_dir, target_dir)

        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        # 执行 post-install 钩子（从已安装的 target 目录 config.yaml 读取）。
        # 失败仅警告，不阻断安装（主体文件已就位）。
        _run_plugin_hooks(target_dir, "post-install", phase="post")

        # 免重启重载配置：重新扫描 plugins 目录并合并扩展点，使新插件配置
        # 声明立即生效（Issue #234）。失败仅警告，不阻断安装。
        try:
            from jarvis.jarvis_utils.utils import reload_plugin_configs

            reload_plugin_configs()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件配置失败（可稍后重启生效）: {e}")

        PrettyOutput.auto_print(f"✅ 插件安装成功: {plugin_name} -> {target_dir}")
        return True

    except Exception as e:
        PrettyOutput.auto_print(f"❌ 插件安装失败: {str(e)}")
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.utils", function="install_plugin"
                )
                pass
        return False


def list_plugins() -> None:
    """
    列出所有已安装的插件

    功能:
        扫描 ~/.jarvis/plugins/ 目录，读取每个插件的 config.yaml
        并格式化输出插件信息（名称、描述、版本等）
    """
    from pathlib import Path
    import yaml
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.output import PrettyOutput

    plugins_dir = Path(get_data_dir()) / "plugins"

    if not plugins_dir.exists():
        PrettyOutput.auto_print("📦 未安装任何插件")
        return

    # 获取所有插件目录
    plugin_dirs = [d for d in plugins_dir.iterdir() if d.is_dir()]

    if not plugin_dirs:
        PrettyOutput.auto_print("📦 未安装任何插件")
        return

    PrettyOutput.auto_print(f"📦 已安装的插件 ({len(plugin_dirs)}个):\n")

    for plugin_dir in sorted(plugin_dirs):
        config_file = plugin_dir / "config.yaml"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if isinstance(config, dict):
                        name = config.get("name", plugin_dir.name)
                        description = config.get("description", "无描述")
                        version = config.get("version", "未知版本")
                        PrettyOutput.auto_print(f"  • {name} (v{version})")
                        PrettyOutput.auto_print(f"    {description}")
                        PrettyOutput.auto_print("")
                    else:
                        PrettyOutput.auto_print(f"  • {plugin_dir.name}")
                        PrettyOutput.auto_print("    配置文件格式错误")
                        PrettyOutput.auto_print("")
            except Exception as e:
                PrettyOutput.auto_print(f"  • {plugin_dir.name}")
                PrettyOutput.auto_print(f"    读取配置失败: {str(e)}")
                PrettyOutput.auto_print("")
        else:
            PrettyOutput.auto_print(f"  • {plugin_dir.name}")
            PrettyOutput.auto_print("    ⚠️ 缺少 config.yaml")
            PrettyOutput.auto_print("")


def list_plugins_info() -> List[dict]:
    """
    列出所有插件并返回结构化信息（供 HTTP API 使用）。

    同时枚举：
    - 内置插件：源码内置目录 builtin/plugins/（builtin: true，不复制、不可卸载/升级）
    - 外部插件：<data_dir>/plugins/ 目录
    若某插件名同时存在于内置目录与数据目录，以内置为准（跳过数据目录副本）。

    返回:
        list[dict]: 每个元素为插件信息字典，字段：
            - name: 插件名
            - description: 描述
            - version: 版本
            - dependencies: 依赖声明（若存在）
            - frontend: 前端扩展声明（若存在）
            - builtin: 是否内置插件
            - capabilities: 能力清单
            - installed: 是否可用（目录存在且 config 可读）
            - logo: 插件图标（SVG 内容，可选）
    """
    import yaml
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir

    # 收集内置插件目录（builtin/plugins/）
    builtin_dirs: List[Path] = []
    try:
        from jarvis.jarvis_utils.template_utils import _get_builtin_dir

        builtin_dir = _get_builtin_dir()
        if builtin_dir is not None:
            builtin_plugins_dir = builtin_dir / "plugins"
            if builtin_plugins_dir.exists() and builtin_plugins_dir.is_dir():
                builtin_dirs = [
                    d
                    for d in builtin_plugins_dir.iterdir()
                    if d.is_dir() and (d / "config.yaml").exists()
                ]
    except Exception:
        builtin_dirs = []

    # 收集外部插件目录（data_dir/plugins/），跳过与内置同名的副本
    plugins_dir = Path(get_data_dir()) / "plugins"
    external_dirs: List[Path] = []
    if plugins_dir.exists() and plugins_dir.is_dir():
        builtin_names = {d.name for d in builtin_dirs}
        external_dirs = [
            d
            for d in plugins_dir.iterdir()
            if d.is_dir() and d.name not in builtin_names
        ]

    result: List[dict] = []
    # 读取更新检测缓存（由独立定时任务每小时写入），避免列表请求触发网络 git fetch
    updates_cache = _load_plugin_updates_cache()
    for plugin_dir in sorted(builtin_dirs + external_dirs):
        config_file = plugin_dir / "config.yaml"
        is_builtin = plugin_dir in builtin_dirs
        info: dict = {
            "name": plugin_dir.name,
            "description": "",
            "version": None,
            "dependencies": None,
            "frontend": None,
            "builtin": is_builtin,
            "capabilities": [],
            "installed": False,
            "hasUpdate": False,
            "logo": "",
        }
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if isinstance(config, dict):
                    info["name"] = config.get("name", plugin_dir.name)
                    info["description"] = config.get("description", "")
                    info["version"] = config.get("version", None)
                    info["dependencies"] = config.get("dependencies", None)
                    info["frontend"] = config.get("frontend", None)
                    info["builtin"] = is_builtin or bool(config.get("builtin", False))
                    info["capabilities"] = _build_plugin_capabilities(
                        config, plugin_dir
                    )
                    info["logo"] = _read_plugin_logo(config, plugin_dir)
                    info["installed"] = True
                    # 非内置插件且检测到更新时标记 hasUpdate（与前端字段一致）
                    if not info["builtin"] and updates_cache.get(info["name"]):
                        info["hasUpdate"] = True
            except Exception:
                info["installed"] = False
        result.append(info)
    return result


def _read_plugin_logo(config: dict, plugin_dir) -> str:
    """读取插件的 logo 图标（SVG 内容）。

    config.yaml 的 `logo` 字段支持两种形式：
    - 内联 SVG 字符串（以 `<svg` 开头），直接返回；
    - 相对路径（如 `frontend/icon.svg`），读取该文件内容返回。
    无 logo 或读取失败时返回空字符串。
    """
    from pathlib import Path

    logo = config.get("logo")
    if not logo:
        return ""
    logo = str(logo).strip()
    if not logo:
        return ""
    if logo.startswith("<svg"):
        return logo
    # 相对路径：相对插件目录解析
    try:
        icon_file = Path(plugin_dir) / logo
        if icon_file.is_file():
            content = icon_file.read_text(encoding="utf-8").strip()
            if content.startswith("<svg"):
                return content
    except Exception:
        pass
    return ""


def _market_cache_dir_name(repo_url: str) -> str:
    """为市场仓库 URL 生成唯一且可读的本地缓存目录名（Issue #243）。

    基于仓库路径（owner/repo）拼接，避免不同组织的同名仓库
    （如 ``https://github.com/orgA/market`` 与 ``orgB/market``）共用同一
    缓存目录互相覆盖。兼容多种 URL 形态：

    - ``https://github.com/orgA/market`` / ``.../market.git``
    - ``git@github.com:orgA/market.git``（scp-like）
    - ``ssh://git@host:port/orgA/market``

    无法解析出 owner/repo 时回退为 URL 最后一段（去 .git），仍为空则用
    ``market``。
    """
    import re

    url = (repo_url or "").strip().rstrip("/")
    # 去掉 #branch 片段
    url = url.split("#", 1)[0].rstrip("/")
    # 提取路径部分：scp-like（git@host:path）与 URL（scheme://host/path）
    path = ""
    if "://" in url:
        # https://host/org/repo(.git)
        path = url.split("://", 1)[1]
        # 去掉 host[:port] 前缀
        path = re.sub(r"^[^/]+", "", path)
    elif ":" in url and "@" in url:
        # git@host:org/repo(.git)
        path = url.split(":", 1)[1]
    else:
        path = url
    path = path.strip("/").removesuffix(".git")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        # 取最后两段（owner/repo），用 __ 拼接避免歧义
        return "__".join(parts[-2:])
    if parts:
        return parts[-1]
    # 回退：URL 最后一段
    last = url.rsplit("/", 1)[-1].removesuffix(".git")
    return last or "market"


def list_market_plugins() -> List[dict]:
    """从插件市场仓库拉取并解析市场插件清单。

    市场仓库内含 `plugins/` 目录，每插件一个 YAML 文件描述插件元数据
    （id/name/description/repo/branch/author/license/categories）。
    本函数对每个配置的市场仓库（`get_plugin_market_repos`）克隆到数据目录缓存，
    扫描 `plugins/*.yaml` 解析为结构化插件列表。仓库不可达或清单解析失败时
    跳过该仓库/该条目，不阻断整体返回。

    返回:
        list[dict]: 每个元素为市场插件信息字典，字段：
            - id: 插件唯一标识
            - name: 展示名
            - description: 功能说明
            - repo: 插件源码仓库地址
            - branch: 发布分支
            - author: 作者
            - license: 开源协议
            - logo: 插件图标（URL，可选）
            - categories: 分类标签
            - market_repo: 来源市场仓库地址
    """
    import yaml
    from pathlib import Path

    from jarvis.jarvis_utils.config import get_data_dir, get_plugin_market_repos
    from jarvis.jarvis_utils.exception_utils import save_exception

    market_repos = get_plugin_market_repos()
    if not market_repos:
        return []

    data_dir = Path(get_data_dir())
    market_root = data_dir / "plugin_market"
    market_root.mkdir(parents=True, exist_ok=True)

    plugins: List[dict] = []
    for repo_url in market_repos:
        repo_url = (repo_url or "").strip().rstrip("/")
        if not repo_url:
            continue
        # 缓存目录名基于仓库路径（owner/repo）唯一化，避免不同组织的同名
        # 仓库（如 orgA/market 与 orgB/market）互相覆盖缓存（Issue #243）。
        cache_dir = market_root / _market_cache_dir_name(repo_url)
        try:
            if not cache_dir.exists():
                _git_clone_plugin(repo_url, "main", cache_dir)
            else:
                # 已有缓存：尝试 git pull 更新，失败则用缓存（离线可用）
                pull = _git_run(cache_dir, "pull", "--quiet")
                if pull.returncode != 0:
                    pass  # 保留缓存
        except Exception as e:
            # 仓库不可达：跳过该市场源，不影响其他源
            save_exception(
                e, module="jarvis_agent.utils", function="list_market_plugins"
            )
            continue

        plugins_dir = cache_dir / "plugins"
        if not plugins_dir.is_dir():
            continue
        for yaml_file in sorted(plugins_dir.glob("*.yaml")):
            if yaml_file.name.startswith("_"):
                # 跳过模板/占位文件（如 _example.yaml）
                continue
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                if not isinstance(cfg, dict):
                    continue
                pid = str(cfg.get("id") or yaml_file.stem)
                plugins.append(
                    {
                        "id": pid,
                        "name": str(cfg.get("name") or pid),
                        "description": str(cfg.get("description") or ""),
                        "repo": str(cfg.get("repo") or ""),
                        "branch": str(cfg.get("branch") or "main"),
                        "author": str(cfg.get("author") or ""),
                        "license": str(cfg.get("license") or ""),
                        "logo": str(cfg.get("logo") or ""),
                        "categories": cfg.get("categories") or [],
                        "market_repo": repo_url,
                    }
                )
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_agent.utils",
                    function="list_market_plugins",
                )
                continue
    return plugins


def _resolve_plugin_dir(plugin_dir) -> "pathlib.Path | None":
    """将插件目录参数归一化为 Path；无效时返回 None。"""
    from pathlib import Path

    if plugin_dir is None:
        return None
    try:
        return Path(plugin_dir)
    except Exception:
        return None


def _collect_plugin_files(dirs, plugin_dir, extensions) -> list:
    """收集扩展点目录下的实际文件（用于展示具体规则/工具）。

    dirs: config.yaml 中的目录列表（可能含 {{plugin_dir}} 占位或相对/绝对路径）
    plugin_dir: 插件目录，用于解析 {{plugin_dir}} 占位与相对路径
    extensions: 感兴趣的文件扩展名元组，如 (".md",) 或 (".py",)
    """
    import os
    from pathlib import Path

    base = _resolve_plugin_dir(plugin_dir)
    if base is None:
        return []
    if not isinstance(dirs, list):
        return []
    files: list = []
    seen: set = set()
    for d in dirs:
        if not isinstance(d, str):
            continue
        p = d.replace("{{plugin_dir}}", str(base))
        if not os.path.isabs(p):
            p = str(base / p)
        p_path = Path(p)
        if not p_path.exists() or not p_path.is_dir():
            continue
        for f in sorted(p_path.iterdir()):
            if f.is_file() and f.suffix in extensions and str(f) not in seen:
                seen.add(str(f))
                files.append(f)
    return files


def _read_rule_meta(rule_file):
    """解析规则 Markdown 的 YAML front matter，返回 (name, description)。

    规则文件以 `---` 开头，front matter 含 name/description。
    解析失败或缺少 name 时返回 (None, None)。
    """
    try:
        text = rule_file.read_text(encoding="utf-8")
    except Exception:
        return None, None
    if not text.startswith("---"):
        return None, None
    end = text.find("---", 3)
    if end == -1:
        return None, None
    try:
        import yaml

        meta = yaml.safe_load(text[3:end])
    except Exception:
        return None, None
    if not isinstance(meta, dict):
        return None, None
    return meta.get("name"), meta.get("description")


def _read_tool_meta(tool_file):
    """解析工具 Python 模块的 class name/description 属性，返回 (name, description)。

    工具类在模块内定义 name/description 字符串属性；解析失败或缺少 name 时返回 (None, None)。
    """
    import ast

    try:
        tree = ast.parse(tool_file.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = None
        desc = None
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "name" and isinstance(stmt.value, ast.Constant):
                    name = stmt.value.value
                elif target.id == "description" and isinstance(
                    stmt.value, ast.Constant
                ):
                    desc = stmt.value.value
        if name:
            return name, desc
    return None, None


def _read_agent_meta(agent_file):
    """解析 Agent 定义 YAML 的 name/description，返回 (name, description)。

    Agent 定义文件是带 YAML front matter 的 YAML，含 name/description。
    解析失败或缺少 name 时返回 (None, None)。
    """
    try:
        import yaml

        data = yaml.safe_load(agent_file.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None
    return data.get("name"), data.get("description")


def _build_plugin_capabilities(config: dict, plugin_dir=None) -> List[dict]:
    """
    从插件 config.yaml 构建能力清单（供前端展示，让用户了解插件提供了哪些操作）。

    自动从既有能力字段推导，并合并插件作者通过顶层 capabilities 字段声明的
    自定义能力（如事件钩子、@内置命令等）。

    规则与工具会进一步读取实际文件，展示具体规则名/工具名及其用途，
    让用户知道插件到底提供了什么、怎么用。

    参数:
        config: 插件 config.yaml 解析后的 dict
        plugin_dir: 插件目录（Path 或 str），用于解析相对路径读取规则/工具文件

    返回:
        list[dict]: 每个元素为 {type, name, description}，type 取值：
            rules / tools / agents / orchestration / frontend / replace_map / custom / mcp
    """
    capabilities: List[dict] = []

    def _append(ctype: str, name: str, desc: str) -> None:
        capabilities.append({"type": ctype, "name": name, "description": desc})

    # 规则：读取规则目录下实际文件，展示具体规则名与触发场景
    rules = config.get("rules_load_dirs")
    if rules:
        rule_files = _collect_plugin_files(rules, plugin_dir, (".md",))
        if rule_files:
            for rule_file in rule_files:
                name, desc = _read_rule_meta(rule_file)
                if name:
                    _append(
                        "rules",
                        f"规则：{name}",
                        desc or f"规则文件 {rule_file.name}，可被 Agent 自动发现并加载",
                    )
        else:
            _append(
                "rules",
                "规则",
                f"提供 {len(rules)} 个规则目录，可被 Agent 自动发现并加载",
            )
    # 工具：读取工具目录下实际文件，展示具体工具名与用途
    tools = config.get("tool_load_dirs")
    if tools:
        tool_files = _collect_plugin_files(tools, plugin_dir, (".py",))
        if tool_files:
            for tool_file in tool_files:
                name, desc = _read_tool_meta(tool_file)
                if name:
                    _append(
                        "tools",
                        f"工具：{name}",
                        desc or f"工具模块 {tool_file.name}，注册可调用工具",
                    )
        else:
            _append(
                "tools",
                "工具",
                f"提供 {len(tools)} 个工具目录，注册可调用的工具",
            )
    # Agent 定义：读取 agents 目录下实际 YAML，展示具体角色名与职责
    agents = config.get("agent_definition_dirs")
    if agents:
        agent_files = _collect_plugin_files(agents, plugin_dir, (".yaml", ".yml"))
        if agent_files:
            for agent_file in agent_files:
                name, desc = _read_agent_meta(agent_file)
                if name:
                    _append(
                        "agents",
                        f"Agent：{name}",
                        desc
                        or f"Agent 定义文件 {agent_file.name}，供内置配置选择器选用",
                    )
        else:
            _append(
                "agents",
                "Agent 定义",
                f"提供 {len(agents)} 个 Agent 定义目录，供内置配置选择器选用",
            )
    # 编排文件
    orchestration = config.get("orchestration")
    if isinstance(orchestration, list):
        for entry in orchestration:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("id")
                if name:
                    _append(
                        "orchestration",
                        f"编排：{name}",
                        str(entry.get("description", "") or "编排流水线模板"),
                    )
    # 前端扩展
    frontend = config.get("frontend")
    if isinstance(frontend, dict):
        frontend_parts = []
        for key in ("admin_tabs", "sidebar_views", "tool_panels"):
            if frontend.get(key):
                frontend_parts.append(key)
        if frontend_parts:
            _append(
                "frontend",
                "前端扩展",
                "提供前端界面扩展：" + "、".join(frontend_parts),
            )
    # 插件作者声明的自定义能力（事件钩子、@内置命令等）
    custom = config.get("capabilities")
    if isinstance(custom, list):
        for entry in custom:
            if isinstance(entry, dict):
                name = entry.get("name")
                if name:
                    _append(
                        "custom",
                        str(name),
                        str(entry.get("description", "") or ""),
                    )
    # 指令模板（replace_map）：用户在输入框输入 <tag> 即被替换为对应指令模板
    replace_map = config.get("replace_map")
    if isinstance(replace_map, dict):
        for tag, info in replace_map.items():
            if not isinstance(info, dict):
                continue
            desc = str(info.get("description", "") or "")
            append_mode = info.get("append")
            if append_mode:
                desc = (desc + "（追加到当前输入）") if desc else "追加到当前输入"
            _append(
                "replace_map",
                f"指令 <{tag}>",
                desc or f"输入 <{tag}> 触发对应指令模板",
            )
    # MCP 服务（mcpserver 扩展点）：插件声明的 MCP server 注册为 MCP 工具/资源
    mcpservers = config.get("mcpserver")
    if isinstance(mcpservers, list):
        for entry in mcpservers:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not name:
                continue
            mcp_type = str(entry.get("type", "") or "").strip()
            if not entry.get("enable", True):
                continue
            parts = [f"MCP 服务（{mcp_type}）" if mcp_type else "MCP 服务"]
            desc = str(entry.get("description", "") or "").strip()
            if desc:
                parts.append(desc)
            _append("mcp", f"MCP：{name}", "；".join(parts))

    return capabilities


def _is_builtin_plugin(plugin_dir) -> bool:
    """
    判断插件目录是否为内置插件。

    内置插件判定采用双保险：
    1. 插件 config.yaml 中声明 builtin: true；
    2. 插件名存在于源码内置目录 builtin/plugins/<name>（兼容已安装的旧副本，
       即便副本 config.yaml 未含 builtin 标记也能识别为内置插件）。

    Args:
        plugin_dir: 插件目录（Path 或 str）

    Returns:
        bool: 内置插件返回 True，否则返回 False
    """
    import yaml
    from pathlib import Path

    plugin_dir = Path(plugin_dir)
    plugin_name = plugin_dir.name

    # 方式1：config.yaml 声明 builtin: true
    config_file = plugin_dir / "config.yaml"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if isinstance(config, dict) and config.get("builtin", False):
                return True
        except Exception:
            pass

    # 方式2：插件名存在于源码内置目录 builtin/plugins/<name>
    try:
        from jarvis.jarvis_utils.template_utils import _get_builtin_dir

        builtin_dir = _get_builtin_dir()
        if builtin_dir is not None:
            builtin_plugin_dir = builtin_dir / "plugins" / plugin_name
            if builtin_plugin_dir.exists() and builtin_plugin_dir.is_dir():
                return True
    except Exception:
        pass

    return False


def list_plugin_orchestrations() -> List[dict]:
    """
    列出所有插件声明的编排流水线模板（供前端编排功能使用）。

    同时扫描内置插件（builtin/plugins/）与外部插件（<data_dir>/plugins/），
    读取每个插件的 config.yaml，渲染 {{plugin_dir}} 模板变量后提取
    orchestration 声明，返回模板列表。

    返回:
        list[dict]: 每个元素为编排模板信息字典，字段：
            - plugin: 来源插件名
            - name: 模板名
            - description: 模板描述
            - file: 编排文件绝对路径（{{plugin_dir}} 已渲染）
    """
    import yaml
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.template_utils import render_plugin_config_template

    # 收集内置插件目录（builtin/plugins/）
    builtin_dirs: List[Path] = []
    try:
        from jarvis.jarvis_utils.template_utils import _get_builtin_dir

        builtin_dir = _get_builtin_dir()
        if builtin_dir is not None:
            builtin_plugins_dir = builtin_dir / "plugins"
            if builtin_plugins_dir.exists() and builtin_plugins_dir.is_dir():
                builtin_dirs = [
                    d
                    for d in builtin_plugins_dir.iterdir()
                    if d.is_dir() and (d / "config.yaml").exists()
                ]
    except Exception:
        builtin_dirs = []

    # 收集外部插件目录（data_dir/plugins/），跳过与内置同名的副本
    plugins_dir = Path(get_data_dir()) / "plugins"
    external_dirs: List[Path] = []
    if plugins_dir.exists() and plugins_dir.is_dir():
        builtin_names = {d.name for d in builtin_dirs}
        external_dirs = [
            d
            for d in plugins_dir.iterdir()
            if d.is_dir() and d.name not in builtin_names
        ]

    result: List[dict] = []
    for plugin_dir in sorted(builtin_dirs + external_dirs):
        config_file = plugin_dir / "config.yaml"
        if not config_file.exists():
            continue
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_content = f.read()
            rendered = render_plugin_config_template(config_content, str(plugin_dir))
            config = yaml.safe_load(rendered)
            if not isinstance(config, dict):
                continue
            entries = config.get("orchestration")
            if not isinstance(entries, list):
                continue
            plugin_name = str(config.get("name") or plugin_dir.name)
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("id")
                file_path = entry.get("file") or entry.get("path")
                if not name or not file_path:
                    continue
                result.append(
                    {
                        "plugin": plugin_name,
                        "name": str(name),
                        "description": str(entry.get("description", "") or ""),
                        "file": str(file_path),
                    }
                )
        except Exception:
            continue
    return result


def uninstall_plugin(plugin_name: str) -> bool:
    """
    卸载插件

    Args:
        plugin_name: 插件名称

    Returns:
        bool: 卸载成功返回 True，失败返回 False
    """
    import os
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.output import PrettyOutput

    # 安全处理：只保留文件名部分，防止路径遍历攻击
    plugin_name = Path(plugin_name).name

    plugins_dir = Path(get_data_dir()) / "plugins"
    plugin_dir = plugins_dir / plugin_name

    # 用 lexists 判断存在性：软链接安装的插件若本地源码被删，链接悬空，
    # exists()/is_dir() 会返回 False 导致无法卸载；lexists 不跟随链接。
    if not os.path.lexists(plugin_dir):
        PrettyOutput.auto_print(f"⚠️ 插件不存在: {plugin_name}")
        return False

    if not plugin_dir.is_dir():
        PrettyOutput.auto_print(f"⚠️ 插件路径不是目录: {plugin_dir}")
        return False

    # 防御性拒绝卸载内置插件
    if _is_builtin_plugin(plugin_dir):
        PrettyOutput.auto_print(f"⛔ 内置插件不可卸载: {plugin_name}")
        return False

    # 卸载前预读 post-uninstall 钩子命令（目录删除后无法再读取 config.yaml）
    post_uninstall_commands = _read_plugin_hooks(plugin_dir).get("post-uninstall", [])

    # 执行 pre-uninstall 钩子（从插件目录 config.yaml 读取）。
    # 失败则中止卸载，避免资源未清理就删除目录。
    if not _run_plugin_hooks(plugin_dir, "pre-uninstall", phase="pre"):
        PrettyOutput.auto_print(f"❌ pre-uninstall 钩子失败，中止卸载: {plugin_name}")
        return False

    # 可逆效应：卸载前撤销该插件注册的工具/规则（若当前进程有已加载的
    # ToolRegistry / RulesManager 实例，则实际移除；否则仅清理登记，目录
    # 删除后下次启动自然不再加载）。
    try:
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        if registry.has_plugin(plugin_name):
            result = registry.revoke_plugin(plugin_name)
            if result.get("tools") or result.get("rules"):
                PrettyOutput.auto_print(
                    f"↩️  已撤销插件 '{plugin_name}' 注册的资源"
                    f"（工具 {result.get('tools', 0)} 个，规则 {result.get('rules', 0)} 个）"
                )
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 撤销插件资源失败（继续卸载）: {str(e)}")

    try:
        # 软链接只删链接本身，不误删其指向的本地源码
        _remove_plugin_dir(plugin_dir)
        PrettyOutput.auto_print(f"✅ 插件已卸载: {plugin_name}")
        # 执行 post-uninstall 钩子（命令已在删除前预读）。
        # 失败仅警告，不阻断卸载（目录已删除）。
        if post_uninstall_commands:
            _run_plugin_hook_commands(
                post_uninstall_commands,
                plugins_dir,
                "post-uninstall",
                phase="post",
            )
        # 免重启重载配置：重新扫描 plugins 目录并合并扩展点，使卸载后的
        # 插件配置声明立即移除（Issue #234）。失败仅警告，不阻断卸载。
        try:
            from jarvis.jarvis_utils.utils import reload_plugin_configs

            reload_plugin_configs()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件配置失败（可稍后重启生效）: {e}")
        return True
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 卸载插件失败: {str(e)}")
        return False


def check_plugin_update(plugin_name: str) -> bool:
    """检查 git 来源插件是否有新版本（Issue #213）。

    对保留 .git 元数据的 git 插件，执行 `git fetch` 后比较本地 HEAD 与
    远端分支 HEAD；不一致即视为有新版本。

    Args:
        plugin_name: 插件名称

    Returns:
        bool: 有新版本返回 True，否则返回 False。
            非 git 插件、网络失败或无法比较时保守返回 False（不误报）。
    """
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir

    # 安全处理：只保留文件名部分，防止路径遍历攻击
    plugin_name = Path(plugin_name).name

    plugins_dir = Path(get_data_dir()) / "plugins"
    plugin_dir = plugins_dir / plugin_name

    # 非 git 插件（无 .git 元数据）不做更新检测
    if not plugin_dir.exists() or not (plugin_dir / ".git").exists():
        return False

    branch = _read_plugin_branch(plugin_dir)

    try:
        # 浅克隆需先拉取指定分支的远端引用
        fetch = _git_run(plugin_dir, "fetch", "origin", branch)
        if fetch.returncode != 0:
            return False
        local_head = _git_run(plugin_dir, "rev-parse", "HEAD").stdout.strip()
        remote_head = _git_run(
            plugin_dir, "rev-parse", f"origin/{branch}"
        ).stdout.strip()
        return bool(local_head and remote_head and local_head != remote_head)
    except Exception:
        return False


def _plugin_updates_cache_path() -> "pathlib.Path":
    """返回插件更新检测缓存文件路径。"""
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir

    return Path(get_data_dir()) / "plugin_updates.json"


def _load_plugin_updates_cache() -> dict:
    """读取插件更新检测缓存（plugin_updates.json）。

    缓存由独立定时任务每小时调用 check_all_plugins_update 写入。
    返回 {插件名: bool}；文件不存在或解析失败返回空 dict。
    """
    import json

    try:
        cache_path = _plugin_updates_cache_path()
        if not cache_path.exists():
            return {}
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): bool(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_plugin_updates_cache(updates: dict) -> None:
    """写入插件更新检测缓存（plugin_updates.json）。"""
    import json

    try:
        cache_path = _plugin_updates_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(updates, f, ensure_ascii=False, indent=2)
    except Exception as e:
        from jarvis.jarvis_utils.exception_utils import save_exception

        save_exception(
            e, module="jarvis_agent.utils", function="_save_plugin_updates_cache"
        )


def check_all_plugins_update() -> dict:
    """检查所有 git 来源插件的更新，并把结果写入缓存（供前端消费）。

    供独立定时任务每小时调用（Issue #213）。对每个保留 .git 元数据的
    外部插件执行 check_plugin_update，汇总结果写入 plugin_updates.json。

    返回:
        dict: {插件名: bool}，表示该插件是否有新版本
    """
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir

    plugins_dir = Path(get_data_dir()) / "plugins"
    updates: dict = {}
    if not plugins_dir.exists() or not plugins_dir.is_dir():
        return updates

    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir():
            continue
        # 跳过内置插件
        if _is_builtin_plugin(plugin_dir):
            continue
        # 仅检查 git 来源插件（保留 .git 元数据）
        if not (plugin_dir / ".git").exists():
            continue
        updates[plugin_dir.name] = check_plugin_update(plugin_dir.name)

    _save_plugin_updates_cache(updates)
    return updates


def upgrade_plugin(plugin_name: str) -> bool:
    """
    升级插件（git 来源，Issue #213）。

    对通过 git 安装（存在 .source + .git 元数据）的插件，执行
    `git fetch origin <branch>` 后 `git reset --hard origin/<branch>`
    更新到远端最新提交。非 git 插件无法升级。

    Args:
        plugin_name: 插件名称

    Returns:
        bool: 升级成功返回 True，失败返回 False
    """
    import os
    from pathlib import Path
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_utils.output import PrettyOutput

    # 安全处理：只保留文件名部分，防止路径遍历攻击
    plugin_name = Path(plugin_name).name

    plugins_dir = Path(get_data_dir()) / "plugins"
    plugin_dir = plugins_dir / plugin_name

    if not plugin_dir.exists():
        PrettyOutput.auto_print(f"⚠️ 插件不存在: {plugin_name}")
        return False

    # 防御性拒绝升级内置插件
    if _is_builtin_plugin(plugin_dir):
        PrettyOutput.auto_print(f"⛔ 内置插件不可升级: {plugin_name}")
        return False

    # 本地软链接安装的插件：源码更新即生效，无需升级（升级会误删本地源码）
    if os.path.islink(plugin_dir):
        PrettyOutput.auto_print(
            f"ℹ️  插件 {plugin_name} 通过本地软链接安装，源码更新即生效，无需升级"
        )
        return False

    # 仅支持 git 来源插件（需保留 .git 元数据）
    if not (plugin_dir / ".git").exists():
        PrettyOutput.auto_print(
            f"⚠️ 插件 {plugin_name} 不是 git 来源安装（缺少 .git 元数据），无法升级"
        )
        return False

    source_url = _read_plugin_source(plugin_dir)
    if not source_url:
        PrettyOutput.auto_print(f"⚠️ 插件 {plugin_name} 未记录来源，无法升级")
        return False

    branch = _read_plugin_branch(plugin_dir)
    PrettyOutput.auto_print(
        f"⬆️  正在升级插件 {plugin_name}（来源: {source_url}，分支: {branch}）"
    )

    try:
        # 执行 pre-update 钩子（从当前插件目录 config.yaml 读取）。
        # 失败则中止升级，避免更新到半成品状态。
        if not _run_plugin_hooks(plugin_dir, "pre-update", phase="pre"):
            PrettyOutput.auto_print(f"❌ pre-update 钩子失败，中止升级: {plugin_name}")
            return False

        fetch = _git_run(plugin_dir, "fetch", "origin", branch)
        if fetch.returncode != 0:
            PrettyOutput.auto_print(
                f"❌ 升级失败（git fetch 失败）: "
                f"{fetch.stderr.strip() or fetch.stdout.strip()}"
            )
            return False
        reset = _git_run(plugin_dir, "reset", "--hard", f"origin/{branch}")
        if reset.returncode != 0:
            PrettyOutput.auto_print(
                f"❌ 升级失败（git reset 失败）: "
                f"{reset.stderr.strip() or reset.stdout.strip()}"
            )
            return False

        # 执行 post-update 钩子（从更新后的插件目录 config.yaml 读取）。
        # 失败仅警告，不阻断升级（代码已更新）。
        _run_plugin_hooks(plugin_dir, "post-update", phase="post")

        # 免重启重载配置：重新扫描 plugins 目录并合并扩展点，使升级后的
        # 插件配置声明立即生效（Issue #234）。失败仅警告，不阻断升级。
        try:
            from jarvis.jarvis_utils.utils import reload_plugin_configs

            reload_plugin_configs()
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件配置失败（可稍后重启生效）: {e}")

        PrettyOutput.auto_print(f"✅ 插件升级成功: {plugin_name}")
        return True
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 插件升级失败: {str(e)}")
        return False


__all__ = [
    "join_prompts",
    "is_auto_complete",
    "normalize_next_action",
    "fix_tool_call_with_llm",
    "install_plugin",
    "uninstall_plugin",
    "upgrade_plugin",
    "list_market_plugins",
]
