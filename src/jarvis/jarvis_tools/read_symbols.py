"""
按需读取 symbols.jsonl 的工具。

用途:
- 避免Agent直接完整读取体积较大的符号表文件；
- 通过提供符号表路径与符号名称列表，仅返回匹配的符号记录。

参数:
- symbols_file (str): 符号表文件路径（.jsonl），或项目根目录/包含 .jarvis/c2rust 的目录
- symbols (List[str]): 需要读取的符号名称列表（支持 name 与 qualified_name 匹配）

返回:
- success (bool)
- stdout (str): JSON文本，包含查询结果
- stderr (str)
"""

import json
import os

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List


class ReadSymbolsTool:
    # 文件名必须与工具名一致，便于注册表自动加载
    name = "read_symbols"
    description = "从symbols.jsonl按需读取指定符号记录"
    parameters = {
        "type": "object",
        "properties": {
            "symbols_file": {
                "type": "string",
                "description": "符号表文件路径（.jsonl）。若为目录，则解析为 <dir>/.jarvis/c2rust/symbols.jsonl",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要检索的符号名称列表（支持 name 或 qualified_name 完全匹配）",
            },
        },
        "required": ["symbols_file", "symbols"],
    }

    @staticmethod
    def check() -> bool:
        """
        检查工具是否可用。
        仅在 c2rust 环境中启用（通过环境变量 c2rust_enabled 判断）。
        """
        return os.environ.get("c2rust_enabled") == "1"

    @staticmethod
    def _resolve_symbols_jsonl_path(path_hint: str) -> Path:
        """
        解析符号表路径：
        - 若为目录，返回 <dir>/.jarvis/c2rust/symbols.jsonl
        - 若为文件，直接返回
        """
        p = Path(os.path.abspath(os.path.expanduser(path_hint)))
        if p.is_dir():
            candidate = p / ".jarvis" / "c2rust" / "symbols.jsonl"
            return candidate
        return p

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            symbols_file_arg = args.get("symbols_file")
            symbols_arg = args.get("symbols")

            if not isinstance(symbols_file_arg, str) or not symbols_file_arg.strip():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少或无效的 symbols_file 参数",
                }

            if not isinstance(symbols_arg, list) or not all(
                isinstance(s, str) for s in symbols_arg
            ):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "symbols 参数必须是字符串列表",
                }

            symbols_path = self._resolve_symbols_jsonl_path(symbols_file_arg)
            PrettyOutput.auto_print(
                f"[read_symbols] Resolved symbols file path: {symbols_path}"
            )
            if not symbols_path.exists():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"符号表文件不存在: {symbols_path}",
                }
            if not symbols_path.is_file():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"符号表路径不是文件: {symbols_path}",
                }

            # 使用集合提升匹配效率；保持原请求顺序以便输出
            requested: List[str] = [s.strip() for s in symbols_arg if s and s.strip()]
            wanted_set = set(requested)
            PrettyOutput.auto_print(
                f"[read_symbols] Requested {len(wanted_set)} unique symbols."
            )

            results: Dict[str, List[Dict[str, Any]]] = {s: [] for s in requested}

            # 流式读取，避免载入整个大文件
            with open(symbols_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    name = obj.get("name") or ""
                    qname = obj.get("qualified_name") or ""

                    # 仅当命中请求的符号时才记录
                    if name in wanted_set:
                        results[name].append(obj)
                    if qname in wanted_set and qname != name:
                        results[qname].append(obj)

            not_found = [s for s in requested if not results.get(s)]
            if not_found:
                PrettyOutput.auto_print(
                    f"[read_symbols] Symbols not found: {not_found}"
                )
            found_counts = {s: len(results.get(s, [])) for s in requested}

            out_obj: Dict[str, Any] = {
                "symbols_file": str(symbols_path),
                "requested": requested,
                "found_counts": found_counts,
                "not_found": not_found,
                "items": results,
            }

            stdout = json.dumps(out_obj, ensure_ascii=False, indent=2)
            # 简要状态打印（不包含具体内容）
            try:
                status_lines = []
                for s in requested:
                    cnt = found_counts.get(s, 0)
                    status_lines.append(f"[read_symbols] {s}: {cnt} 条匹配")
                if status_lines:
                    PrettyOutput.auto_print("\n".join(status_lines))
            except Exception:
                pass

            return {"success": True, "stdout": stdout, "stderr": ""}

        except Exception as e:
            PrettyOutput.auto_print(f"❌ {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"读取符号表失败: {str(e)}",
            }
