# -*- coding: utf-8 -*-
"""LLM 模块规划 Agent 的图加载器。"""

from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Set
from typing import Tuple

from jarvis.jarvis_c2rust.llm_module_agent_types import FnMeta
from jarvis.jarvis_utils.jsonnet_compat import loads as json_loads


class GraphLoader:
    """
    仅从 symbols.jsonl 读取符号与调用关系，提供子图遍历能力：
    - 数据源：<project_root>/.jarvis/c2rust/symbols.jsonl 或显式传入的 .jsonl 文件
    - 不再支持任何回退策略（不考虑 symbols_raw.jsonl、functions.jsonl 等）
    """

    def __init__(self, db_path: Path, project_root: Path):
        self.project_root = Path(project_root).resolve()

        def _resolve_data_path(hint: Path) -> Path:
            p = Path(hint)
            # 仅支持 symbols.jsonl；不再兼容 functions.jsonl 或其他旧格式
            # 若直接传入文件路径且为 .jsonl，则直接使用（要求内部包含 category/ref 字段）
            if p.is_file() and p.suffix.lower() == ".jsonl":
                return p
            # 目录：仅支持 <dir>/.jarvis/c2rust/symbols.jsonl
            if p.is_dir():
                return p / ".jarvis" / "c2rust" / "symbols.jsonl"
            # 默认：项目 .jarvis/c2rust/symbols.jsonl
            return self.project_root / ".jarvis" / "c2rust" / "symbols.jsonl"

        self.data_path = _resolve_data_path(Path(db_path))
        if not self.data_path.exists():
            raise FileNotFoundError(f"未找到 symbols.jsonl: {self.data_path}")
        # Initialize in-memory graph structures
        self.adj: Dict[int, List[str]] = {}
        self.name_to_id: Dict[str, int] = {}
        self.fn_by_id: Dict[int, FnMeta] = {}

        # 从 symbols.jsonl 加载符号元数据与邻接关系（统一处理函数与类型，按 ref 构建名称邻接）
        rows_loaded = 0
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json_loads(line)
                    except Exception:
                        # 跳过无效的 JSON 行，但记录以便调试
                        continue
                    # 不区分函数与类型，统一处理 symbols.jsonl 中的所有记录
                    rows_loaded += 1
                    fid = int(obj.get("id") or rows_loaded)
                    nm = obj.get("name") or ""
                    qn = obj.get("qualified_name") or ""
                    sg = obj.get("signature") or ""
                    fp = obj.get("file") or ""
                    refs = obj.get("ref")
                    # 不兼容旧数据：严格要求为列表类型，缺失则视为空
                    if not isinstance(refs, list):
                        refs = []
                    refs = [c for c in refs if isinstance(c, str) and c]
                    self.adj[fid] = refs
                    # 建立名称索引与函数元信息，供子图遍历与上下文构造使用
                    if isinstance(nm, str) and nm:
                        self.name_to_id.setdefault(nm, fid)
                    if isinstance(qn, str) and qn:
                        self.name_to_id.setdefault(qn, fid)
                    try:
                        rel_file = self._rel_path(fp)
                    except (ValueError, OSError):
                        rel_file = fp
                    self.fn_by_id[fid] = FnMeta(
                        id=fid,
                        name=nm,
                        qname=qn,
                        signature=sg,
                        file=rel_file,
                        refs=refs,
                    )
        except FileNotFoundError:
            raise
        except (OSError, IOError) as e:
            raise RuntimeError(f"读取 symbols.jsonl 时发生错误: {e}") from e
        except Exception as e:
            raise RuntimeError(f"解析 symbols.jsonl 时发生未知错误: {e}") from e

    def _rel_path(self, abs_path: str) -> str:
        """将绝对路径转换为相对于项目根的相对路径。"""
        try:
            p = Path(abs_path).resolve()
            return str(p.relative_to(self.project_root))
        except Exception:
            return abs_path

    def collect_subgraph(self, root_id: int) -> Tuple[Set[int], Set[str]]:
        """
        从 root_id 出发，收集所有可达的内部函数 (visited_ids) 与外部调用名称 (externals)

        Args:
            root_id: 根函数 ID

        Returns:
            (visited_ids, externals) 元组
        """
        visited: Set[int] = set()
        externals: Set[str] = set()
        stack: List[int] = [root_id]
        visited.add(root_id)
        while stack:
            src = stack.pop()
            for callee in self.adj.get(src, []):
                cid = self.name_to_id.get(callee)
                if cid is not None:
                    if cid not in visited:
                        visited.add(cid)
                        stack.append(cid)
                else:
                    externals.add(callee)
        return visited, externals

    def build_roots_context(
        self,
        roots: List[int],
        max_functions_per_ns: int = 200,  # 保留参数以保持兼容性，但当前未使用
        max_namespaces_per_root: int = 50,  # 保留参数以保持兼容性，但当前未使用
    ) -> List[Dict[str, Any]]:
        """
        为每个根函数构造上下文（仅函数名的调用关系，且不包含任何其他信息）：
        - root_function: 根函数的简单名称（不包含签名/限定名）
        - functions: 该根函数子图内所有可达函数的简单名称列表（不包含签名/限定名），去重、排序、可选截断
        注意：
        - 不包含文件路径、签名、限定名、命名空间、外部符号等任何其他元信息
        """
        root_contexts: List[Dict[str, Any]] = []
        for rid in roots:
            meta = self.fn_by_id.get(rid)
            root_label = (meta.name or f"fn_{rid}") if meta else f"fn_{rid}"

            visited_ids, _externals = self.collect_subgraph(rid)
            # 收集所有简单函数名
            fn_names: List[str] = []
            for fid in sorted(visited_ids):
                m = self.fn_by_id.get(fid)
                if not m:
                    continue
                simple = m.name or f"fn_{fid}"
                fn_names.append(simple)

            # 去重并排序（优先使用 dict.fromkeys 保持顺序）
            try:
                fn_names = sorted(list(dict.fromkeys(fn_names)))
            except (TypeError, ValueError):
                # 如果 dict.fromkeys 失败（理论上不应该），回退到 set
                fn_names = sorted(list(set(fn_names)))

            root_contexts.append(
                {
                    "root_function": root_label,
                    "functions": fn_names,
                }
            )
        return root_contexts
