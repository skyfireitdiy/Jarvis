# -*- coding: utf-8 -*-
"""库替换器的检查点管理模块。"""

import json
import time
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_c2rust.constants import DEFAULT_CHECKPOINT_INTERVAL
from jarvis.jarvis_c2rust.constants import JSON_INDENT
from jarvis.jarvis_c2rust.library_replacer_utils import normalize_list
from jarvis.jarvis_c2rust.library_replacer_utils import normalize_list_lower


def make_checkpoint_key(
    sjsonl: Path,
    library_name: str,
    llm_group: Optional[str],
    candidates: Optional[List[str]],
    disabled_libraries: Optional[List[str]],
    max_funcs: Optional[int],
) -> Dict[str, Any]:
    """构建检查点键"""
    try:
        abs_sym = str(Path(sjsonl).resolve())
    except Exception:
        abs_sym = str(sjsonl)
    key: Dict[str, Any] = {
        "symbols": abs_sym,
        "library_name": str(library_name),
        "llm_group": str(llm_group or ""),
        "candidates": normalize_list(candidates),
        "disabled_libraries": normalize_list_lower(disabled_libraries),
        "max_funcs": (
            int(max_funcs)
            if isinstance(max_funcs, int)
            or (isinstance(max_funcs, float) and max_funcs.is_integer())  # type: ignore
            else None
        ),
    }
    return key


def load_checkpoint_if_match(
    ckpt_path: Path,
    resume: bool,
    checkpoint_key: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """加载匹配的检查点"""
    try:
        if not resume:
            return None
        if not ckpt_path.exists():
            return None
        obj = json.loads(ckpt_path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return None
        if obj.get("key") != checkpoint_key:
            return None
        return obj
    except Exception:
        return None


def atomic_write(path: Path, content: str) -> None:
    """原子写入文件"""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        try:
            path.write_text(content, encoding="utf-8")
        except Exception:
            pass


def create_checkpoint_state(
    checkpoint_key: Dict[str, Any],
    eval_counter: int,
    processed_roots: set,
    pruned_dynamic: set,
    selected_roots: list,
) -> Dict[str, Any]:
    """创建检查点状态字典"""
    try:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    except Exception:
        ts = ""
    return {
        "key": checkpoint_key,
        "eval_counter": eval_counter,
        "processed_roots": sorted(list(processed_roots)),
        "pruned_dynamic": sorted(list(pruned_dynamic)),
        "selected_roots": [{"fid": fid, "res": res} for fid, res in selected_roots],
        "timestamp": ts,
    }


def periodic_checkpoint_save(
    ckpt_path: Path,
    checkpoint_state: Dict[str, Any],
    eval_counter: int,
    last_ckpt_saved: int,
    checkpoint_interval: int,
    resume: bool,
) -> int:
    """
    定期保存检查点。

    Returns:
        更新后的 last_ckpt_saved 值
    """
    if not resume:
        return last_ckpt_saved
    try:
        interval = int(checkpoint_interval)
    except Exception:
        interval = DEFAULT_CHECKPOINT_INTERVAL
    need_save = (interval <= 0) or ((eval_counter - last_ckpt_saved) >= interval)
    if not need_save:
        return last_ckpt_saved
    try:
        atomic_write(
            ckpt_path,
            json.dumps(checkpoint_state, ensure_ascii=False, indent=JSON_INDENT),
        )
        return eval_counter
    except Exception:
        return last_ckpt_saved
