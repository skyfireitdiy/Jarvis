# -*- coding: utf-8 -*-
"""
C2Rust 转译器工具函数
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
from jarvis.jarvis_c2rust.constants import ORDER_JSONL
from jarvis.jarvis_c2rust.scanner import compute_translation_order_jsonl
from jarvis.jarvis_utils.config import get_max_input_token_count
from jarvis.jarvis_utils.git_utils import get_diff
from jarvis.jarvis_utils.git_utils import get_diff_file_list
from jarvis.jarvis_utils.jsonnet_compat import loads as json5_loads


def ensure_order_file(project_root: Path) -> Path:
    """确保 translation_order.jsonl 存在且包含有效步骤；仅基于 symbols.jsonl 生成，不使用任何回退。"""
    data_dir = project_root / C2RUST_DIRNAME
    order_path = data_dir / ORDER_JSONL
    PrettyOutput.auto_print(f"📋 [c2rust-transpiler][order] 目标顺序文件: {order_path}")

    def _has_steps(p: Path) -> bool:
        try:
            steps = iter_order_steps(p)
            return bool(steps)
        except Exception:
            return False

    # 已存在则校验是否有步骤
    PrettyOutput.auto_print(
        f"🔍 [c2rust-transpiler][order] 检查现有顺序文件有效性: {order_path}"
    )
    if order_path.exists():
        if _has_steps(order_path):
            PrettyOutput.auto_print(
                f"✅ [c2rust-transpiler][order] 现有顺序文件有效，将使用 {order_path}"
            )
            return order_path
        # 为空或不可读：基于标准路径重新计算（仅 symbols.jsonl）
        PrettyOutput.auto_print(
            "⚠️ [c2rust-transpiler][order] 现有顺序文件为空/无效，正基于 symbols.jsonl 重新计算"
        )
        try:
            compute_translation_order_jsonl(data_dir, out_path=order_path)
        except Exception as e:
            raise RuntimeError(f"重新计算翻译顺序失败: {e}")
        return order_path

    # 不存在：按标准路径生成到固定文件名（仅 symbols.jsonl）
    try:
        compute_translation_order_jsonl(data_dir, out_path=order_path)
    except Exception as e:
        raise RuntimeError(f"计算翻译顺序失败: {e}")

    PrettyOutput.auto_print(
        f"📋 [c2rust-transpiler][order] 已生成顺序文件: {order_path} (exists={order_path.exists()})"
    )
    if not order_path.exists():
        raise FileNotFoundError(f"计算后未找到 translation_order.jsonl: {order_path}")

    # 最终校验：若仍无有效步骤，直接报错并提示先执行 scan 或检查 symbols.jsonl
    if not _has_steps(order_path):
        raise RuntimeError(
            "translation_order.jsonl 无有效步骤。请先执行 'jarvis-c2rust scan' 生成 symbols.jsonl 并重试。"
        )

    return order_path


def iter_order_steps(order_jsonl: Path) -> List[List[int]]:
    """
    读取翻译顺序（兼容新旧格式），返回按步骤的函数id序列列表。
    新格式：每行包含 "ids": [int, ...] 以及 "items": [完整符号对象,...]。
    不再兼容旧格式（不支持 "records"/"symbols" 键）。
    """
    # 旧格式已移除：不再需要基于 symbols.jsonl 的 name->id 映射

    steps: List[List[int]] = []
    with order_jsonl.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue

            ids = obj.get("ids")
            if isinstance(ids, list) and ids:
                # 新格式：仅支持 ids
                try:
                    ids_int = [
                        int(x)
                        for x in ids
                        if isinstance(x, (int, str)) and str(x).strip()
                    ]
                except Exception:
                    ids_int = []
                if ids_int:
                    steps.append(ids_int)
                continue
            # 不支持旧格式（无 ids 则跳过该行）
    return steps


def dir_tree(root: Path) -> str:
    """格式化 crate 目录结构（过滤部分常见目录）"""
    lines: List[str] = []
    exclude = {".git", "target", ".jarvis"}
    if not root.exists():
        return ""
    for p in sorted(root.rglob("*")):
        if any(part in exclude for part in p.parts):
            continue
        rel = p.relative_to(root)
        depth = len(rel.parts) - 1
        indent = "  " * depth
        name = rel.name + ("/" if p.is_dir() else "")
        lines.append(f"{indent}- {name}")
    return "\n".join(lines)


def default_crate_dir(project_root: Path) -> Path:
    """遵循 llm_module_agent 的默认crate目录选择：<parent>/<cwd.name>_rs（与当前目录同级）当传入为 '.' 时"""
    try:
        cwd = Path(".").resolve()
        if project_root.resolve() == cwd:
            return cwd.parent / f"{cwd.name}_rs"
        else:
            return project_root
    except Exception:
        return project_root


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json(path: Path, obj: Any) -> None:
    """原子性写入JSON文件：先写入临时文件，再重命名"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 使用临时文件确保原子性
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 原子性重命名
        temp_path.replace(path)
    except Exception:
        # 如果原子写入失败，回退到直接写入
        try:
            path.write_text(
                json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def extract_json_from_summary(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    从 Agent summary 中提取结构化数据（使用 JSON 格式）：
    - 仅在 <SUMMARY>...</SUMMARY> 块内查找；
    - 直接解析 <SUMMARY> 块内的内容为 JSON 对象（不需要额外的 <json> 标签）；
    - 使用 jsonnet 解析，支持更宽松的 JSON 语法（如尾随逗号、注释等）；
    返回(解析结果, 错误信息)
    如果解析成功，返回(data, None)
    如果解析失败，返回({}, 错误信息)
    """
    if not isinstance(text, str) or not text.strip():
        return {}, "摘要文本为空"

    # 提取 <SUMMARY> 块
    m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", text, flags=re.IGNORECASE)
    block = (m.group(1) if m else text).strip()

    if not block:
        return {}, "未找到 <SUMMARY> 或 </SUMMARY> 标签，或标签内容为空"

    try:
        try:
            obj = json5_loads(block)
        except Exception as json_err:
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return {}, error_msg
        if isinstance(obj, dict):
            return obj, None
        return {}, f"JSON 解析结果不是字典，而是 {type(obj).__name__}"
    except Exception as e:
        return {}, f"解析过程发生异常: {str(e)}"


def detect_test_deletion(log_prefix: str = "[c2rust]") -> Optional[Dict[str, Any]]:
    """
    检测是否错误删除了 #[test] 或 #[cfg(test)]。

    参数:
        log_prefix: 日志前缀（如 "[c2rust-transpiler]" 或 "[c2rust-optimizer]"）

    返回:
        如果检测到删除，返回包含 'diff', 'files', 'deleted_tests' 的字典；否则返回 None
    """
    try:
        diff = get_diff()
        if not diff:
            return None

        # 检查 diff 中是否包含删除的 #[test] 或 #[cfg(test)]
        test_patterns = [
            r"^-\s*#\[test\]",
            r"^-\s*#\[cfg\(test\)\]",
            r"^-\s*#\[cfg\(test\)",
        ]

        deleted_tests = []
        lines = diff.split("\n")
        current_file = None

        for i, line in enumerate(lines):
            # 检测文件路径
            if (
                line.startswith("diff --git")
                or line.startswith("---")
                or line.startswith("+++")
            ):
                # 尝试从 diff 行中提取文件名
                if line.startswith("---"):
                    parts = line.split()
                    if len(parts) > 1:
                        current_file = parts[1].lstrip("a/").lstrip("b/")
                elif line.startswith("+++"):
                    parts = line.split()
                    if len(parts) > 1:
                        current_file = parts[1].lstrip("a/").lstrip("b/")
                continue

            # 检查是否匹配删除的测试标记
            for pattern in test_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # 检查上下文，确认是删除而不是修改
                    if i > 0 and lines[i - 1].startswith("-"):
                        # 可能是删除的一部分
                        deleted_tests.append(
                            {
                                "file": current_file or "unknown",
                                "line": line,
                                "line_number": i + 1,
                            }
                        )
                    elif not (i < len(lines) - 1 and lines[i + 1].startswith("+")):
                        # 下一行不是添加，说明是删除
                        deleted_tests.append(
                            {
                                "file": current_file or "unknown",
                                "line": line,
                                "line_number": i + 1,
                            }
                        )
                    break

        if deleted_tests:
            modified_files = get_diff_file_list()
            return {
                "diff": diff,
                "files": modified_files,
                "deleted_tests": deleted_tests,
            }
        return None
    except Exception as e:
        PrettyOutput.auto_print(
            f"⚠️ {log_prefix}[test-detection] 检测测试删除时发生异常: {e}"
        )
        return None


def ask_llm_about_test_deletion(
    detection_result: Dict[str, Any], agent: Any, log_prefix: str = "[c2rust]"
) -> bool:
    """
    询问 LLM 是否错误删除了测试代码。

    参数:
        detection_result: 检测结果字典，包含 'diff', 'files', 'deleted_tests'
        agent: 代码生成或修复的 agent 实例，使用其 model 进行询问
        log_prefix: 日志前缀（如 "[c2rust-transpiler]" 或 "[c2rust-optimizer]"）

    返回:
        bool: 如果 LLM 认为删除不合理返回 True（需要回退），否则返回 False
    """
    if not agent or not hasattr(agent, "model"):
        # 如果没有 agent 或 agent 没有 model，默认认为有问题（保守策略）
        return True

    try:
        deleted_tests = detection_result.get("deleted_tests", [])
        diff = detection_result.get("diff", "")
        files = detection_result.get("files", [])

        # 构建预览（限制长度）
        preview_lines = []
        preview_lines.append("检测到可能错误删除了测试代码标记：")
        preview_lines.append("")
        for item in deleted_tests[:10]:  # 最多显示10个
            preview_lines.append(f"- 文件: {item.get('file', 'unknown')}")
            preview_lines.append(f"  行: {item.get('line', '')}")
        if len(deleted_tests) > 10:
            preview_lines.append(f"... 还有 {len(deleted_tests) - 10} 个删除的测试标记")

        # 限制 diff 长度
        diff_preview = diff[:5000] if len(diff) > 5000 else diff
        if len(diff) > 5000:
            diff_preview += "\n... (diff 内容过长，已截断)"

        prompt = f"""检测到代码变更中可能错误删除了测试代码标记（#[test] 或 #[cfg(test)]），请判断是否合理：

删除的测试标记统计：
- 删除的测试标记数量: {len(deleted_tests)}
- 涉及的文件: {", ".join(files[:5])}{" ..." if len(files) > 5 else ""}

删除的测试标记详情：
{chr(10).join(preview_lines)}

代码变更预览（diff）：
{diff_preview}

请仔细分析以上代码变更，判断这些测试代码标记的删除是否合理。可能的情况包括：
1. 重构代码，将测试代码移动到其他位置（这种情况下应该看到对应的添加）
2. 删除过时或重复的测试代码
3. 错误地删除了重要的测试代码标记，导致测试无法运行

请使用以下协议回答（必须包含且仅包含以下标记之一）：
- 如果认为这些删除是合理的（测试代码被正确移动或确实需要删除），回答: <!!!YES!!!>
- 如果认为这些删除不合理或存在风险（可能错误删除了测试代码），回答: <!!!NO!!!>

请严格按照协议格式回答，不要添加其他内容。
"""

        PrettyOutput.auto_print(
            f"🤔 {log_prefix}[test-detection] 正在询问 LLM 判断测试代码删除是否合理..."
        )
        response = agent.model.chat_until_success(prompt)
        response_str = str(response or "")

        # 使用确定的协议标记解析回答
        if "<!!!NO!!!>" in response_str:
            PrettyOutput.auto_print("❌ LLM 确认：测试代码删除不合理，需要回退")
            return True  # 需要回退
        elif "<!!!YES!!!>" in response_str:
            PrettyOutput.auto_print("✅ LLM 确认：测试代码删除合理")
            return False  # 不需要回退
        else:
            # 如果无法找到协议标记，默认认为有问题（保守策略）
            PrettyOutput.auto_print(
                f"⚠️ 无法找到协议标记，默认认为有问题。回答内容: {response_str[:200]}"
            )
            return True  # 保守策略：默认回退
    except Exception as e:
        # 如果询问失败，默认认为有问题（保守策略）
        PrettyOutput.auto_print(f"⚠️ 询问 LLM 失败: {str(e)}，默认认为有问题")
        return True  # 保守策略：默认回退


def check_and_handle_test_deletion(
    before_commit: Optional[str],
    agent: Any,
    reset_to_commit_fn: Callable[[str], bool],
    log_prefix: str = "[c2rust]",
) -> bool:
    """
    检测并处理测试代码删除。

    参数:
        before_commit: agent 运行前的 commit hash
        agent: 代码生成或修复的 agent 实例，使用其 model 进行询问
        reset_to_commit_fn: 回退到指定 commit 的函数，接受 commit hash 作为参数，返回是否成功
        log_prefix: 日志前缀（如 "[c2rust-transpiler]" 或 "[c2rust-optimizer]"）

    返回:
        bool: 如果检测到问题且已回退，返回 True；否则返回 False
    """
    if not before_commit:
        # 没有记录 commit，无法回退
        return False

    detection_result = detect_test_deletion(log_prefix)
    if not detection_result:
        # 没有检测到删除
        return False

    PrettyOutput.auto_print(
        f"⚠️ {log_prefix}[test-detection] 检测到可能错误删除了测试代码标记"
    )

    # 询问 LLM（使用传入的 agent 的 model）
    need_reset = ask_llm_about_test_deletion(detection_result, agent, log_prefix)

    if need_reset:
        PrettyOutput.auto_print(
            f"❌ {log_prefix}[test-detection] LLM 确认删除不合理，正在回退到 commit: {before_commit}"
        )
        if reset_to_commit_fn(before_commit):
            PrettyOutput.auto_print(
                f"✅ {log_prefix}[test-detection] 已回退到之前的 commit"
            )
            return True
        else:
            PrettyOutput.auto_print(f"❌ {log_prefix}[test-detection] 回退失败")
            return False

    return False


def extract_files_from_git_diff(git_diff: str) -> List[str]:
    """
    从 git diff 字符串中提取所有修改的文件列表。

    参数:
        git_diff: git diff 内容

    返回:
        List[str]: 修改的文件路径列表（去重）
    """
    if not git_diff or not git_diff.strip():
        return []

    files = set()
    # 匹配 "diff --git a/path b/path" 格式
    # git diff 标准格式：diff --git a/path b/path
    pattern = r"^diff --git a/([^\s]+) b/([^\s]+)$"
    for line in git_diff.split("\n"):
        match = re.match(pattern, line)
        if match:
            # 通常 a/path 和 b/path 相同，但处理重命名时可能不同
            file_a = match.group(1)
            file_b = match.group(2)
            # 优先使用 b 路径（新路径），如果不同则都添加
            files.add(file_b)
            if file_a != file_b:
                files.add(file_a)

    return sorted(list(files))


def get_modified_files_from_git(
    base_commit: Optional[str], crate_dir: Optional[Path]
) -> List[str]:
    """
    使用 git 命令获取修改的文件列表。

    参数:
        base_commit: 基准 commit（如果为 None，则与 HEAD 比较）
        crate_dir: crate 根目录（如果为 None，则使用当前目录）

    返回:
        List[str]: 修改的文件路径列表
    """
    if not crate_dir:
        return []

    try:
        # 构建 git diff 命令
        if base_commit:
            cmd = ["git", "diff", "--name-only", base_commit]
        else:
            cmd = ["git", "diff", "--name-only", "HEAD"]

        result = subprocess.run(
            cmd,
            cwd=crate_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
            return sorted(files)
        else:
            # 如果命令失败，返回空列表
            return []
    except Exception:
        # 如果出现任何异常，返回空列表
        return []


def truncate_git_diff_with_context_limit(
    git_diff: str,
    agent: Optional[Any] = None,
    llm_group: Optional[str] = None,
    token_ratio: float = 0.3,
    base_commit: Optional[str] = None,
    crate_dir: Optional[Path] = None,
) -> str:
    """
    限制 git diff 的长度，避免上下文过大。

    参数:
        git_diff: 原始的 git diff 内容
        agent: 可选的 agent 实例，用于获取剩余 token 数量（更准确，考虑对话历史）
        llm_group: 可选的 LLM 组名称，用于获取输入窗口限制（当 agent 不可用时使用）
        token_ratio: token 使用比例（默认 0.3，即 30%）
        base_commit: 可选的基准 commit，如果提供则使用 git 命令获取文件列表
        crate_dir: 可选的 crate 根目录，如果提供则使用 git 命令获取文件列表

    返回:
        str: 限制长度后的 git diff（如果超出限制则截断并添加提示和文件列表）
    """
    if not git_diff or not git_diff.strip():
        return git_diff

    max_diff_chars = None

    # 优先尝试使用 agent 获取剩余 token（更准确，包含对话历史）
    if agent:
        try:
            remaining_tokens = agent.get_remaining_token_count()
            if remaining_tokens > 0:
                # 使用剩余 token 的指定比例作为字符限制（1 token ≈ 4字符）
                max_diff_chars = int(remaining_tokens * token_ratio * 4)
                if max_diff_chars <= 0:
                    max_diff_chars = None
        except Exception:
            pass

    # 回退方案：使用输入窗口的指定比例转换为字符数
    if max_diff_chars is None:
        try:
            max_input_tokens = get_max_input_token_count(llm_group)
            max_diff_chars = int(max_input_tokens * token_ratio * 4)
        except Exception:
            # 如果获取失败，使用默认值（约 10000 字符）
            max_diff_chars = 10000

    # 应用长度限制
    if len(git_diff) > max_diff_chars:
        # 优先使用 git 命令获取文件列表（更可靠）
        if base_commit is not None and crate_dir:
            modified_files = get_modified_files_from_git(base_commit, crate_dir)
        else:
            # 回退到从 diff 内容中提取
            modified_files = extract_files_from_git_diff(git_diff)

        truncated_diff = git_diff[:max_diff_chars] + "\n... (差异内容过长，已截断)"

        # 如果有修改的文件，添加文件列表
        if modified_files:
            truncated_diff += "\n\n**修改的文件列表（共 {} 个文件）：**\n".format(
                len(modified_files)
            )
            for file_path in modified_files:
                truncated_diff += f"  - {file_path}\n"

        return truncated_diff

    return git_diff
