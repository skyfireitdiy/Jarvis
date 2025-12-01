# -*- coding: utf-8 -*-
"""库替换器的输出写入模块。"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def write_output_symbols(
    all_records: List[Dict[str, Any]],
    pruned_funcs: Set[int],
    selected_roots: List[Tuple[int, Dict[str, Any]]],
    out_symbols_path: Path,
    out_symbols_prune_path: Path,
) -> List[Dict[str, Any]]:
    """写出新符号表，返回替代映射列表"""
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    kept_ids: Set[int] = set()
    for rec in all_records:
        fid = int(rec.get("id"))
        cat = rec.get("category") or ""
        if cat == "function":
            if fid in pruned_funcs:
                continue
            kept_ids.add(fid)
        else:
            kept_ids.add(fid)

    sel_root_ids = set(fid for fid, _ in selected_roots)
    replacements: List[Dict[str, Any]] = []

    with (
        open(out_symbols_path, "w", encoding="utf-8") as fo,
        open(out_symbols_prune_path, "w", encoding="utf-8") as fo2,
    ):
        for rec in all_records:
            fid = int(rec.get("id"))
            if fid not in kept_ids:
                continue

            rec_out = dict(rec)
            if (rec.get("category") or "") == "function" and fid in sel_root_ids:
                # 以库级替代为语义：不要求具体 API；将根 ref 设置为库占位符（支持多库组合）
                conf = 0.0
                api = ""
                apis = None
                libraries_out: List[str] = []
                notes_out: str = ""
                lib_single: str = ""
                for rf, rres in selected_roots:
                    if rf == fid:
                        api = str(rres.get("api") or rres.get("function") or "")
                        apis = rres.get("apis")
                        libs_val = rres.get("libraries")
                        if isinstance(libs_val, list):
                            libraries_out = [str(x) for x in libs_val if str(x)]
                        lib_single = str(rres.get("library") or "").strip()
                        try:
                            conf = float(rres.get("confidence") or 0.0)
                        except Exception:
                            conf = 0.0
                        notes_val = rres.get("notes")
                        if isinstance(notes_val, str):
                            notes_out = notes_val
                        break
                # 若 libraries 存在则使用多库占位；否则若存在单个 library 字段则使用之；否则置空
                if libraries_out:
                    lib_markers = [f"lib::{lb}" for lb in libraries_out]
                elif lib_single:
                    lib_markers = [f"lib::{lib_single}"]
                else:
                    lib_markers = []
                rec_out["ref"] = lib_markers
                try:
                    rec_out["updated_at"] = now_ts
                except Exception:
                    pass
                # 保存库替代元数据到符号表，供后续转译阶段作为上下文使用
                try:
                    meta_apis = (
                        apis if isinstance(apis, list) else ([api] if api else [])
                    )
                    lib_primary = libraries_out[0] if libraries_out else lib_single
                    rec_out["lib_replacement"] = {
                        "libraries": libraries_out,
                        "library": lib_primary or "",
                        "apis": meta_apis,
                        "api": api,
                        "confidence": float(conf)
                        if isinstance(conf, (int, float))
                        else 0.0,
                        "notes": notes_out,
                        "mode": "llm",
                        "updated_at": now_ts,
                    }
                except Exception:
                    # 忽略写入元数据失败，不阻塞主流程
                    pass
                rep_obj: Dict[str, Any] = {
                    "id": fid,
                    "name": rec.get("name") or "",
                    "qualified_name": rec.get("qualified_name") or "",
                    "library": (libraries_out[0] if libraries_out else lib_single),
                    "libraries": libraries_out,
                    "function": api,
                    "confidence": conf,
                    "mode": "llm",
                }
                if isinstance(apis, list):
                    rep_obj["apis"] = apis
                if notes_out:
                    rep_obj["notes"] = notes_out
                replacements.append(rep_obj)

            line = json.dumps(rec_out, ensure_ascii=False) + "\n"
            fo.write(line)
            fo2.write(line)
            # 不覆写 symbols.jsonl（保留原始扫描/整理结果作为基线）

    return replacements
