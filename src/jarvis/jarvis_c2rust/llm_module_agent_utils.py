"""LLM 模块规划 Agent 的工具函数。"""

import json
import shutil

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
import sys
from pathlib import Path
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from jarvis.jarvis_utils.input import user_confirm
from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads


def perform_pre_cleanup_for_planner(project_root: Union[Path, str]) -> None:
    """
    预清理：如存在将删除将要生成的 crate 目录、当前目录的 workspace 文件 Cargo.toml、
    以及 project_root/.jarvis/c2rust 下的 progress.json 与 symbol_map.jsonl。
    用户不同意则直接退出。
    """
    try:
        cwd = Path(".").resolve()
    except (OSError, ValueError) as e:
        raise RuntimeError(f"无法解析当前工作目录: {e}") from e

    try:
        requested_root = Path(project_root).resolve()
    except (OSError, ValueError):
        requested_root = Path(project_root)

    created_dir = (
        cwd.parent / f"{cwd.name}_rs" if requested_root == cwd else requested_root
    )

    cargo_path = cwd / "Cargo.toml"
    data_dir = requested_root / ".jarvis" / "c2rust"
    progress_path = data_dir / "progress.json"
    symbol_map_jsonl_path = data_dir / "symbol_map.jsonl"

    targets: List[str] = []
    if created_dir.exists():
        targets.append(f"- 删除 crate 目录（如存在）：{created_dir}")
    if cargo_path.exists():
        targets.append(f"- 删除工作区文件：{cargo_path}")
    if progress_path.exists():
        targets.append(f"- 删除进度文件：{progress_path}")
    if symbol_map_jsonl_path.exists():
        targets.append(f"- 删除符号映射文件：{symbol_map_jsonl_path}")

    if not targets:
        return

    tip_lines = ["将执行以下清理操作："] + targets + ["", "是否继续？"]
    if not user_confirm("\n".join(tip_lines), default=False):
        PrettyOutput.auto_print("[c2rust-llm-planner] 用户取消清理操作，退出。")
        sys.exit(0)

    # 执行清理操作
    try:
        if created_dir.exists():
            shutil.rmtree(created_dir, ignore_errors=True)
        if cargo_path.exists():
            cargo_path.unlink()
        if progress_path.exists():
            progress_path.unlink()
        if symbol_map_jsonl_path.exists():
            symbol_map_jsonl_path.unlink()
    except (OSError, PermissionError) as e:
        raise RuntimeError(f"清理操作失败: {e}") from e


def resolve_created_dir(target_root: Union[Path, str]) -> Path:
    """
    解析 crate 目录路径：
    - 若 target_root 为 "." 或解析后等于当前工作目录，则返回 "<cwd.name>_rs" 目录；
    - 否则返回解析后的目标路径；
    - 解析失败则回退到 Path(target_root)。
    """
    try:
        cwd = Path(".").resolve()
        try:
            resolved_target = Path(target_root).resolve()
        except Exception:
            resolved_target = Path(target_root)
        if target_root == "." or resolved_target == cwd:
            return cwd.parent / f"{cwd.name}_rs"
        return resolved_target
    except Exception:
        return Path(target_root)


def parse_project_json_entries_fallback(json_text: str) -> List[Any]:
    """
    Fallback 解析器：当 jsonnet 解析失败时，尝试使用标准 json 解析。
    注意：此函数主要用于兼容性，正常情况下应使用 jsonnet 解析。
    """
    try:
        import json as std_json

        data = std_json.loads(json_text)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def parse_project_json_entries(json_text: str) -> Tuple[List[Any], Optional[str]]:
    """
    使用 jsonnet 解析 <PROJECT> 块中的目录结构 JSON 为列表结构:
    - 文件项: 字符串，如 "lib.rs"
    - 目录项: 字典，形如 {"src/": [ ... ]} 或 {"src": [ ... ]}
    返回(解析结果, 错误信息)
    如果解析成功，返回(data, None)
    如果解析失败，返回([], 错误信息)
    使用 jsonnet 解析，支持更宽松的 JSON 语法（如尾随逗号、注释等）。
    """
    try:
        try:
            data = json_loads(json_text)
            if isinstance(data, list):
                return data, None
            # 如果解析结果不是列表
            return [], f"JSON 解析结果不是数组，而是 {type(data).__name__}"
        except Exception as json_err:
            # JSON 解析错误
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return [], error_msg
    except Exception as e:
        # 其他未知错误
        return [], f"解析过程发生异常: {str(e)}"


def entries_to_json(entries: List[Any]) -> str:
    """
    将解析后的 entries 列表序列化为 JSON 文本（目录使用对象表示，文件为字符串）

    Args:
        entries: 解析后的目录结构列表

    Returns:
        JSON 文本
    """
    return json.dumps(entries, ensure_ascii=False, indent=2)
