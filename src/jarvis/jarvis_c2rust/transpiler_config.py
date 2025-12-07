# -*- coding: utf-8 -*-
"""
配置和进度管理模块
"""

import json
from pathlib import Path
from typing import Any, Dict

import typer

from jarvis.jarvis_c2rust.constants import CONFIG_JSON
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.utils import read_json, write_json


class ConfigManager:
    """配置和进度管理器"""

    def __init__(self, data_dir: Path, progress_path: Path) -> None:
        self.data_dir = data_dir
        self.progress_path = progress_path
        self.progress: Dict[str, Any] = read_json(
            self.progress_path, {"current": None, "converted": []}
        )

    def save_progress(self) -> None:
        """保存进度，使用原子性写入"""
        write_json(self.progress_path, self.progress)

    def load_config(self) -> Dict[str, Any]:
        """
        从独立的配置文件加载配置。
        如果配置文件不存在，尝试从 progress.json 迁移配置（向后兼容）。
        """
        config_path = self.data_dir / CONFIG_JSON
        default_config = {
            "root_symbols": [],
            "disabled_libraries": [],
            "additional_notes": "",
        }

        # 尝试从配置文件读取
        if config_path.exists():
            config = read_json(config_path, default_config)
            if isinstance(config, dict):
                # 确保包含所有必需的键（向后兼容）
                if "additional_notes" not in config:
                    config["additional_notes"] = ""
                return config

        # 向后兼容：如果配置文件不存在，尝试从 progress.json 迁移
        progress_config = self.progress.get("config", {})
        if progress_config:
            # 迁移配置到独立文件
            migrated_config = {
                "root_symbols": progress_config.get("root_symbols", []),
                "disabled_libraries": progress_config.get("disabled_libraries", []),
                "additional_notes": progress_config.get("additional_notes", ""),
            }
            write_json(config_path, migrated_config)
            typer.secho(
                f"[c2rust-transpiler][config] 已从 progress.json 迁移配置到 {config_path}",
                fg=typer.colors.YELLOW,
            )
            return migrated_config

        return default_config

    def save_config(
        self,
        root_symbols: list,
        disabled_libraries: list,
        additional_notes: str,
    ) -> None:
        """保存配置到独立的配置文件"""
        config_path = self.data_dir / CONFIG_JSON
        config = {
            "root_symbols": root_symbols,
            "disabled_libraries": disabled_libraries,
            "additional_notes": additional_notes,
        }
        write_json(config_path, config)

    def load_order_index(
        self,
        order_jsonl: Path,
        fn_index_by_id: Dict[int, FnRecord],
        fn_name_to_id: Dict[str, int],
    ) -> None:
        """
        从自包含的 order.jsonl 中加载所有 records，建立：
        - fn_index_by_id: id -> FnRecord
        - fn_name_to_id: name/qname -> id
        若同一 id 多次出现，首次记录为准。
        """
        fn_index_by_id.clear()
        fn_name_to_id.clear()
        typer.secho(
            f"[c2rust-transpiler][index] 正在加载翻译顺序索引: {order_jsonl}",
            fg=typer.colors.BLUE,
        )
        try:
            with order_jsonl.open("r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        continue
                    # 仅支持新格式：items
                    recs = obj.get("items")
                    if not isinstance(recs, list):
                        continue
                    for r in recs:
                        if not isinstance(r, dict):
                            continue
                        # 构建 FnRecord
                        try:
                            rec_id = r.get("id")
                            if rec_id is None:
                                continue
                            fid = int(rec_id)
                        except Exception:
                            continue
                        if fid in fn_index_by_id:
                            # 已收录
                            continue
                        nm = r.get("name") or ""
                        qn = r.get("qualified_name") or ""
                        fp = r.get("file") or ""
                        refs = r.get("ref")
                        if not isinstance(refs, list):
                            refs = []
                        refs = [c for c in refs if isinstance(c, str) and c]
                        sr = int(r.get("start_line") or 0)
                        sc = int(r.get("start_col") or 0)
                        er = int(r.get("end_line") or 0)
                        ec = int(r.get("end_col") or 0)
                        sg = r.get("signature") or ""
                        rt = r.get("return_type") or ""
                        pr = (
                            r.get("params")
                            if isinstance(r.get("params"), list)
                            else None
                        )
                        lr = (
                            r.get("lib_replacement")
                            if isinstance(r.get("lib_replacement"), dict)
                            else None
                        )
                        rec = FnRecord(
                            id=fid,
                            name=nm,
                            qname=qn,
                            file=fp,
                            start_line=sr,
                            start_col=sc,
                            end_line=er,
                            end_col=ec,
                            refs=refs,
                            signature=str(sg or ""),
                            return_type=str(rt or ""),
                            params=pr,
                            lib_replacement=lr,
                        )
                        fn_index_by_id[fid] = rec
                        if nm:
                            fn_name_to_id.setdefault(nm, fid)
                        if qn:
                            fn_name_to_id.setdefault(qn, fid)
        except Exception:
            # 若索引构建失败，保持为空，后续流程将跳过
            pass
        typer.secho(
            f"[c2rust-transpiler][index] 索引构建完成: ids={len(fn_index_by_id)} names={len(fn_name_to_id)}",
            fg=typer.colors.BLUE,
        )
