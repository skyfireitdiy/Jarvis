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
    """根据 tag/branch 解析插件依赖的下载 URL。

    当 url 是 GitHub 仓库地址（形如 https://github.com/owner/repo）且提供了
    tag 或 branch 时，自动构造对应 archive 下载地址：
        tag:    https://github.com/owner/repo/archive/refs/tags/<tag>.tar.gz
        branch: https://github.com/owner/repo/archive/refs/heads/<branch>.tar.gz
    否则（非 GitHub 地址，或已是完整下载地址）原样返回 url。

    参数:
        url: 依赖插件配置的 url
        tag: 依赖插件配置的 tag（可选）
        branch: 依赖插件配置的 branch（可选）

    返回:
        str: 解析后的下载 URL
    """
    if not url:
        return url
    if not tag and not branch:
        return url
    # 仅当 url 是 GitHub 仓库地址（不含已指定的后缀）时构造 archive URL
    url = url.rstrip("/")
    if "github.com/" not in url:
        return url
    # 提取 owner/repo（忽略可能的 .git 后缀）
    parts = url.split("github.com/", 1)
    if len(parts) != 2:
        return url
    repo_path = parts[1].rstrip("/")
    if repo_path.endswith(".git"):
        repo_path = repo_path[:-4]
    repo_path = "/".join(repo_path.split("/")[:2])
    if not repo_path or "/" not in repo_path:
        return url
    if tag:
        return f"https://github.com/{repo_path}/archive/refs/tags/{tag}.tar.gz"
    if branch:
        return f"https://github.com/{repo_path}/archive/refs/heads/{branch}.tar.gz"
    return url


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


def install_plugin(
    source_path: str,
    force: bool = False,
    source_url: Optional[str] = None,
    _installing_deps: Optional[set] = None,
) -> bool:
    """安装插件到 Jarvis 数据目录

    参数:
        source_path: 插件源路径，可以是目录、压缩文件（tar/tar.gz/zip）或 http(s) URL
        force: 是否强制覆盖已安装的插件（忽略版本比较），默认 False
        source_url: 来源 URL（可选），安装成功后记录到插件目录，供升级使用
        _installing_deps: 内部参数，记录正在自动安装的依赖插件名集合，用于防止依赖递归死循环

    返回:
        bool: 安装成功返回 True，失败返回 False

    功能:
        1. 校验插件是否包含 config.yaml
        2. 复制或解压到 ~/.jarvis/plugins/插件名/ 下
        3. 插件名从 config.yaml 的 name 字段获取，若无则使用目录名/文件名
        4. 版本控制：高版本插件可覆盖低版本，低版本不能覆盖高版本
        5. force=True 时忽略版本比较，强制覆盖
        6. 支持从 URL 下载安装，并记录来源 URL 供升级
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
    from jarvis.jarvis_utils.http import get as http_get
    from jarvis.jarvis_utils.output import PrettyOutput

    temp_dir = None  # 预初始化，确保 except 分支可访问（ty 推断局限）
    download_path = None  # URL 下载的临时文件路径
    try:
        # 支持 http(s) URL：下载到临时文件后按压缩文件处理
        if source_path.startswith("http://") or source_path.startswith("https://"):
            PrettyOutput.auto_print(f"⬇️  正在从 URL 下载插件: {source_path}")
            try:
                response = http_get(source_path, stream=True)
                download_path = tempfile.mkstemp(
                    prefix="jarvis_plugin_dl_", suffix=".tar.gz"
                )[1]
                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                source_path = download_path
            except Exception as e:
                PrettyOutput.auto_print(f"❌ 下载插件失败: {str(e)}")
                return False

        source = Path(source_path).resolve()

        if not source.exists():
            PrettyOutput.auto_print(f"❌ 插件源路径不存在: {source_path}")
            return False

        # 获取 Jarvis 数据目录下的 plugins 目录
        data_dir = Path(get_data_dir())
        plugins_dir = data_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # 临时目录用于处理压缩文件
        temp_dir = None
        plugin_source_dir = None

        # 判断源类型：目录还是文件
        if source.is_dir():
            # 直接是目录
            plugin_source_dir = source
        elif source.is_file():
            # 是压缩文件，需要解压
            # 使用 suffixes 获取完整后缀列表，正确识别 .tar.gz 等复合后缀
            suffixes = [s.lower() for s in source.suffixes]
            is_zip = ".zip" in suffixes
            is_tar = ".tar" in suffixes or ".tgz" in suffixes

            if not is_zip and not is_tar:
                PrettyOutput.auto_print(
                    "❌ 不支持的文件格式，仅支持 .tar/.tar.gz/.tgz/.zip"
                )
                return False

            # 创建临时目录解压
            temp_dir = tempfile.mkdtemp(prefix="jarvis_plugin_")

            if is_zip:
                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(temp_dir)
            else:  # tar formats (including .tar.gz, .tgz)
                with tarfile.open(source, "r:*") as tf:
                    # 使用 filter='data' 防止路径遍历攻击 (CVE-2007-4559)
                    tf.extractall(temp_dir, filter="data")

            # 解压后，查找包含 config.yaml 的目录
            extracted_items = list(Path(temp_dir).iterdir())
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                # 只有一个目录，直接使用
                plugin_source_dir = extracted_items[0]
            else:
                # 多个文件/目录，使用临时目录本身
                plugin_source_dir = Path(temp_dir)
        else:
            PrettyOutput.auto_print("❌ 无效的源路径类型")
            return False

        # 校验是否包含 config.yaml
        config_file = plugin_source_dir / "config.yaml"
        if not config_file.exists():
            PrettyOutput.auto_print("❌ 插件缺少 config.yaml 文件")
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
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
            if source.is_dir():
                plugin_name = source.name
            else:
                # 使用文件名（去掉扩展名）
                plugin_name = source.stem
                # 如果是 .tar.gz，需要去掉两个扩展名
                if plugin_name.endswith(".tar"):
                    plugin_name = plugin_name[:-4]

        # 安全处理：只保留文件名部分，防止路径遍历攻击
        plugin_name = Path(plugin_name).name

        # 目标安装目录
        target_dir = plugins_dir / plugin_name

        # 依赖检查：插件声明的依赖必须已安装且版本兼容。
        # 对带 url 的 plugins 依赖，未安装时自动下载安装；无 url 或安装失败的仍拒绝。
        if plugin_dependencies:
            # 初始化正在安装的依赖集合（用于防止依赖递归死循环，如 A->B->A）
            if _installing_deps is None:
                _installing_deps = set()
            if plugin_name in _installing_deps:
                PrettyOutput.auto_print(
                    f"❌ 检测到循环依赖: 插件 {plugin_name} 正在安装中，终止以避免死循环"
                )
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
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
                # 清理临时目录
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
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
                shutil.rmtree(target_dir)
            # 双方都有版本号时进行比较
            elif installed_version and plugin_version:
                cmp = _compare_versions(plugin_version, installed_version)
                if cmp is not None and cmp < 0:
                    PrettyOutput.auto_print(
                        f"❌ 拒绝安装: 新版本 v{plugin_version} 低于已安装版本 "
                        f"v{installed_version}（插件 {plugin_name}）"
                    )
                    # 清理临时目录
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    return False
                if cmp is not None and cmp >= 0:
                    PrettyOutput.auto_print(
                        f"⚠️  插件目录已存在，将覆盖: {target_dir} "
                        f"(v{installed_version} -> v{plugin_version})"
                    )
                else:
                    # 版本无法解析，保守允许覆盖（保持向后兼容）
                    PrettyOutput.auto_print(f"⚠️  插件目录已存在，将覆盖: {target_dir}")
                shutil.rmtree(target_dir)
            else:
                # 已安装插件无版本号（旧格式）或新插件无版本号，允许覆盖以兼容旧插件
                PrettyOutput.auto_print(f"⚠️  插件目录已存在，将覆盖: {target_dir}")
                shutil.rmtree(target_dir)

        # 复制插件到目标目录
        shutil.copytree(plugin_source_dir, target_dir)

        # 记录来源 URL（供升级机制使用）
        if source_url:
            try:
                with open(target_dir / ".source", "w", encoding="utf-8") as f:
                    f.write(source_url)
            except Exception as e:
                save_exception(
                    e, module="jarvis_agent.utils", function="install_plugin"
                )

        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        # 清理下载的临时文件
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass

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


def uninstall_plugin(plugin_name: str) -> bool:
    """
    卸载插件

    Args:
        plugin_name: 插件名称

    Returns:
        bool: 卸载成功返回 True，失败返回 False
    """
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

    if not plugin_dir.is_dir():
        PrettyOutput.auto_print(f"⚠️ 插件路径不是目录: {plugin_dir}")
        return False

    try:
        import shutil

        shutil.rmtree(plugin_dir)
        PrettyOutput.auto_print(f"✅ 插件已卸载: {plugin_name}")
        return True
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 卸载插件失败: {str(e)}")
        return False


def upgrade_plugin(plugin_name: str) -> bool:
    """
    升级插件

    从插件记录的来源 URL 重新下载最新版并覆盖安装。
    仅支持通过 URL 安装的插件（存在 .source 文件）。

    Args:
        plugin_name: 插件名称

    Returns:
        bool: 升级成功返回 True，失败返回 False
    """
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

    # 读取来源 URL
    source_file = plugin_dir / ".source"
    if not source_file.exists():
        PrettyOutput.auto_print(f"⚠️ 插件 {plugin_name} 不是通过 URL 安装的，无法升级")
        return False

    try:
        source_url = source_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 读取插件来源失败: {str(e)}")
        return False

    if not source_url:
        PrettyOutput.auto_print(f"⚠️ 插件 {plugin_name} 未记录来源 URL，无法升级")
        return False

    PrettyOutput.auto_print(f"⬆️  正在升级插件 {plugin_name}（来源: {source_url}）")
    return install_plugin(source_url, force=True, source_url=source_url)


__all__ = [
    "join_prompts",
    "is_auto_complete",
    "normalize_next_action",
    "fix_tool_call_with_llm",
    "install_plugin",
    "uninstall_plugin",
    "upgrade_plugin",
]
