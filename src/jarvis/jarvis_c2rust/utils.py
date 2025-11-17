# -*- coding: utf-8 -*-
"""
C2Rust 转译器工具函数
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME, ORDER_JSONL
from jarvis.jarvis_c2rust.scanner import compute_translation_order_jsonl
from jarvis.jarvis_utils.jsonnet_compat import loads as json5_loads


def ensure_order_file(project_root: Path) -> Path:
    """确保 translation_order.jsonl 存在且包含有效步骤；仅基于 symbols.jsonl 生成，不使用任何回退。"""
    data_dir = project_root / C2RUST_DIRNAME
    order_path = data_dir / ORDER_JSONL
    typer.secho(f"[c2rust-transpiler][order] 目标顺序文件: {order_path}", fg=typer.colors.BLUE)

    def _has_steps(p: Path) -> bool:
        try:
            steps = iter_order_steps(p)
            return bool(steps)
        except Exception:
            return False

    # 已存在则校验是否有步骤
    typer.secho(f"[c2rust-transpiler][order] 检查现有顺序文件有效性: {order_path}", fg=typer.colors.BLUE)
    if order_path.exists():
        if _has_steps(order_path):
            typer.secho(f"[c2rust-transpiler][order] 现有顺序文件有效，将使用 {order_path}", fg=typer.colors.GREEN)
            return order_path
        # 为空或不可读：基于标准路径重新计算（仅 symbols.jsonl）
        typer.secho("[c2rust-transpiler][order] 现有顺序文件为空/无效，正基于 symbols.jsonl 重新计算", fg=typer.colors.YELLOW)
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

    typer.secho(f"[c2rust-transpiler][order] 已生成顺序文件: {order_path} (exists={order_path.exists()})", fg=typer.colors.BLUE)
    if not order_path.exists():
        raise FileNotFoundError(f"计算后未找到 translation_order.jsonl: {order_path}")

    # 最终校验：若仍无有效步骤，直接报错并提示先执行 scan 或检查 symbols.jsonl
    if not _has_steps(order_path):
        raise RuntimeError("translation_order.jsonl 无有效步骤。请先执行 'jarvis-c2rust scan' 生成 symbols.jsonl 并重试。")

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
                    ids_int = [int(x) for x in ids if isinstance(x, (int, str)) and str(x).strip()]
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
        temp_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        # 原子性重命名
        temp_path.replace(path)
    except Exception:
        # 如果原子写入失败，回退到直接写入
        try:
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
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

