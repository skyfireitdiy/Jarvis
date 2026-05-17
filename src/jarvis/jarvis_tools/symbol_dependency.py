# -*- coding: utf-8 -*-
"""
符号依赖查询工具

用途:
- 查询符号信息（按名称/文件路径）
- 查询符号依赖关系（调用者/被调用者）
- 查询文件的符号列表
- 图遍历（BFS/DFS）

参数:
- action (str): 操作类型，支持：
  - "find_symbol": 查找符号
  - "get_file_symbols": 获取文件的符号列表
  - "find_references": 查找符号引用
  - "find_dependencies": 查找符号依赖
  - "traverse": 图遍历
- project_path (str): 项目根目录路径
- symbol_name (str): 符号名称（find_symbol/find_references/find_dependencies需要）
- file_path (str): 文件路径（find_symbol/get_file_symbols需要）
- kind (str): 符号类型过滤（可选）
- direction (str): 遍历方向，"forward"/"backward"（traverse需要）
- max_depth (int): 最大遍历深度（traverse需要，默认10）

返回:
- success (bool)
- stdout (str): JSON文本，包含查询结果
- stderr (str)
"""

import json
import os
from typing import Any, Dict, List, Optional

from jarvis.jarvis_code_agent.code_analyzer.symbol_table_db import SymbolTableDB
from jarvis.jarvis_code_agent.code_analyzer.db.data_types import Node


class SymbolDependencyTool:
    """符号依赖查询工具"""

    # 文件名必须与工具名一致，便于注册表自动加载
    name = "symbol_dependency"
    description = "查询符号依赖关系，支持符号查找、引用查询、依赖分析和图遍历"

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": [
                    "find_symbol",
                    "get_file_symbols",
                    "find_references",
                    "find_dependencies",
                    "traverse",
                ],
            },
            "project_path": {"type": "string", "description": "项目根目录路径"},
            "symbol_name": {
                "type": "string",
                "description": "符号名称（find_symbol/find_references/find_dependencies需要）",
            },
            "file_path": {
                "type": "string",
                "description": "文件路径（find_symbol/get_file_symbols需要）",
            },
            "kind": {
                "type": "string",
                "description": "符号类型过滤（可选）",
                "enum": [
                    "function",
                    "class",
                    "method",
                    "variable",
                    "constant",
                    "module",
                    "interface",
                    "type",
                    "enum",
                    "struct",
                    "trait",
                    "impl",
                    "namespace",
                    "import",
                ],
            },
            "direction": {
                "type": "string",
                "description": "遍历方向（traverse需要）",
                "enum": ["forward", "backward"],
            },
            "max_depth": {
                "type": "integer",
                "description": "最大遍历深度（traverse需要，默认10）",
                "default": 10,
            },
        },
        "required": ["action", "project_path"],
    }

    def __init__(self):
        self._db_cache: Dict[str, SymbolTableDB] = {}

    def _get_db(self, project_path: str) -> SymbolTableDB:
        """获取或创建SymbolTableDB实例"""
        project_path = os.path.abspath(project_path)
        if project_path not in self._db_cache:
            cache_dir = os.path.join(project_path, ".jarvis", "symbol_cache")
            os.makedirs(cache_dir, exist_ok=True)
            self._db_cache[project_path] = SymbolTableDB(cache_dir)
        return self._db_cache[project_path]

    def _node_to_dict(self, node: Node) -> Dict[str, Any]:
        """将Node对象转换为字典"""
        return {
            "id": node.id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind.value if hasattr(node.kind, "value") else str(node.kind),
            "file_path": node.file_path,
            "language": node.language,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "start_column": node.start_column,
            "end_column": node.end_column,
            "signature": node.signature,
            "docstring": node.docstring,
            "parent_id": node.parent_id,
            "visibility": node.visibility,
            "is_exported": node.is_exported,
            "is_async": node.is_async,
            "is_static": node.is_static,
        }

    def _find_symbol(
        self,
        db: SymbolTableDB,
        symbol_name: str,
        file_path: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查找符号"""
        results = []

        # 使用find_symbol方法，第二个参数是file_path
        nodes = db.find_symbol(symbol_name, file_path)

        for node in nodes:
            # 按kind过滤
            if (
                kind is None
                or (hasattr(node.kind, "value") and node.kind.value == kind)
                or str(node.kind) == kind
            ):
                results.append(self._node_to_dict(node))

        return results

    def _get_file_symbols(
        self, db: SymbolTableDB, file_path: str, kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取文件的符号列表"""
        symbols = db.get_file_symbols(file_path)
        results = []

        for sym in symbols:
            if (
                kind is None
                or (hasattr(sym.kind, "value") and sym.kind.value == kind)
                or str(sym.kind) == kind
            ):
                results.append(self._node_to_dict(sym))

        return results

    def _find_references(
        self, db: SymbolTableDB, symbol_name: str, file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """查找符号引用"""
        # 先找到符号
        symbols = self._find_symbol(db, symbol_name, file_path)
        if not symbols:
            return []

        results = []
        for sym_info in symbols:
            node_id = sym_info["id"]
            # 查找引用该符号的边（incoming edges）
            edges = db.queries.get_incoming_edges(node_id)
            for edge in edges:
                # 获取引用者的详细信息
                ref_node = db.queries.get_node_by_id(edge.source)
                if ref_node:
                    results.append(
                        {
                            "reference": self._node_to_dict(ref_node),
                            "edge_kind": edge.kind.value
                            if hasattr(edge.kind, "value")
                            else str(edge.kind),
                            "symbol": sym_info,
                        }
                    )

        return results

    def _find_dependencies(
        self, db: SymbolTableDB, symbol_name: str, file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """查找符号依赖"""
        # 先找到符号
        symbols = self._find_symbol(db, symbol_name, file_path)
        if not symbols:
            return []

        results = []
        for sym_info in symbols:
            node_id = sym_info["id"]
            # 查找该符号依赖的边（outgoing edges）
            edges = db.queries.get_outgoing_edges(node_id)
            for edge in edges:
                # 获取被依赖者的详细信息
                dep_node = db.queries.get_node_by_id(edge.target)
                if dep_node:
                    results.append(
                        {
                            "dependency": self._node_to_dict(dep_node),
                            "edge_kind": edge.kind.value
                            if hasattr(edge.kind, "value")
                            else str(edge.kind),
                            "symbol": sym_info,
                        }
                    )

        return results

    def _traverse(
        self,
        db: SymbolTableDB,
        symbol_name: str,
        file_path: Optional[str] = None,
        direction: str = "forward",
        max_depth: int = 10,
    ) -> Dict[str, Any]:
        """图遍历"""
        # 先找到符号
        symbols = self._find_symbol(db, symbol_name, file_path)
        if not symbols:
            return {"nodes": [], "edges": []}

        traverser = db.get_traverser()
        start_node_id = symbols[0]["id"]

        # direction: forward=正向遍历(outgoing), backward=反向遍历(incoming)
        traverse_direction = "outgoing" if direction == "forward" else "incoming"
        subgraph = traverser.traverse_bfs(
            start_node_id, max_depth=max_depth, direction=traverse_direction
        )

        # 转换结果
        nodes = [self._node_to_dict(node) for node in subgraph.nodes]
        edges = [
            {
                "source": edge.source,
                "target": edge.target,
                "kind": edge.kind.value
                if hasattr(edge.kind, "value")
                else str(edge.kind),
            }
            for edge in subgraph.edges
        ]

        return {"nodes": nodes, "edges": edges}

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        try:
            action = args.get("action")
            project_path = args.get("project_path")

            if not action:
                return {"success": False, "stdout": "", "stderr": "缺少 action 参数"}

            if not project_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少 project_path 参数",
                }

            if not os.path.isdir(project_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"项目路径不存在: {project_path}",
                }

            db = self._get_db(project_path)

            symbol_name = args.get("symbol_name")
            file_path = args.get("file_path")
            kind = args.get("kind")

            if action == "find_symbol":
                if not symbol_name and not file_path:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "find_symbol 需要 symbol_name 或 file_path 参数",
                    }
                results = self._find_symbol(db, symbol_name or "", file_path, kind)
                return {
                    "success": True,
                    "stdout": json.dumps(results, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            elif action == "get_file_symbols":
                if not file_path:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "get_file_symbols 需要 file_path 参数",
                    }
                results = self._get_file_symbols(db, file_path, kind)
                return {
                    "success": True,
                    "stdout": json.dumps(results, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            elif action == "find_references":
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "find_references 需要 symbol_name 参数",
                    }
                results = self._find_references(db, symbol_name, file_path)
                return {
                    "success": True,
                    "stdout": json.dumps(results, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            elif action == "find_dependencies":
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "find_dependencies 需要 symbol_name 参数",
                    }
                results = self._find_dependencies(db, symbol_name, file_path)
                return {
                    "success": True,
                    "stdout": json.dumps(results, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            elif action == "traverse":
                if not symbol_name:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "traverse 需要 symbol_name 参数",
                    }
                direction = args.get("direction", "forward")
                max_depth = args.get("max_depth", 10)
                results = self._traverse(
                    db, symbol_name, file_path, direction, max_depth
                )
                return {
                    "success": True,
                    "stdout": json.dumps(results, ensure_ascii=False, indent=2),
                    "stderr": "",
                }

            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作: {action}",
                }

        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"工具执行失败: {str(e)}"}
