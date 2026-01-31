# -*- coding: utf-8 -*-
"""知识图谱工具

将知识图谱功能暴露给Agent使用，支持添加节点、查询节点、添加关系、获取相关知识。
"""

from typing import Any, Dict, Optional

from jarvis.jarvis_knowledge_graph.knowledge_graph import (
    KnowledgeGraph,
    NodeType,
    RelationType,
)


class KnowledgeGraphTool:
    """知识图谱工具

    支持以下操作：
    - add_node: 添加知识节点
    - query_nodes: 查询节点
    - add_edge: 添加关系
    - get_related: 获取相关知识
    """

    name = "knowledge_graph_tool"
    description = """管理知识图谱，支持添加节点、查询节点、添加关系、获取相关知识。

操作说明：
- add_node: 添加知识节点（方法论、规则、记忆、代码、文件、概念）
- query_nodes: 按类型、标签、名称查询节点
- add_edge: 添加两个节点之间的关系
- get_related: 获取与指定节点相关的知识"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["add_node", "query_nodes", "add_edge", "get_related"],
                "description": "操作类型",
            },
            "node_type": {
                "type": "string",
                "enum": ["methodology", "rule", "memory", "code", "file", "concept"],
                "description": "节点类型（add_node和query_nodes时使用）",
            },
            "name": {
                "type": "string",
                "description": "节点名称（add_node时必填，query_nodes时用于模糊匹配）",
            },
            "description": {
                "type": "string",
                "description": "节点描述（add_node时使用）",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签列表",
            },
            "source_path": {
                "type": "string",
                "description": "来源路径（add_node时使用，可选）",
            },
            "source_id": {
                "type": "string",
                "description": "源节点ID（add_edge时必填）",
            },
            "target_id": {
                "type": "string",
                "description": "目标节点ID（add_edge时必填）",
            },
            "relation_type": {
                "type": "string",
                "enum": [
                    "references",
                    "depends_on",
                    "similar_to",
                    "derived_from",
                    "implements",
                    "related_to",
                    "part_of",
                    "supersedes",
                ],
                "description": "关系类型（add_edge时必填）",
            },
            "strength": {
                "type": "number",
                "description": "关系强度，0-1之间（add_edge时使用，默认1.0）",
            },
            "node_id": {
                "type": "string",
                "description": "节点ID（get_related时必填）",
            },
            "depth": {
                "type": "integer",
                "description": "搜索深度（get_related时使用，默认2）",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量限制",
            },
        },
        "required": ["operation"],
    }

    def __init__(self) -> None:
        """初始化知识图谱工具"""
        self._graph: Optional[KnowledgeGraph] = None

    def _get_graph(self) -> KnowledgeGraph:
        """获取知识图谱实例（延迟初始化）"""
        if self._graph is None:
            self._graph = KnowledgeGraph()
        return self._graph

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行知识图谱操作"""
        operation = args.get("operation", "").strip()

        if not operation:
            return {"success": False, "stdout": "", "stderr": "缺少必要参数: operation"}

        try:
            if operation == "add_node":
                return self._add_node(args)
            elif operation == "query_nodes":
                return self._query_nodes(args)
            elif operation == "add_edge":
                return self._add_edge(args)
            elif operation == "get_related":
                return self._get_related(args)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作类型: {operation}",
                }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"执行失败: {str(e)}"}

    def _add_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """添加知识节点"""
        node_type_str = args.get("node_type", "").strip()
        name = args.get("name", "").strip()
        description = args.get("description", "").strip()
        tags = args.get("tags", [])
        source_path = args.get("source_path")

        if not node_type_str:
            return {"success": False, "stdout": "", "stderr": "缺少必要参数: node_type"}
        if not name:
            return {"success": False, "stdout": "", "stderr": "缺少必要参数: name"}
        if not description:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: description",
            }

        try:
            node_type = NodeType(node_type_str)
        except ValueError:
            valid_types = [t.value for t in NodeType]
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无效的节点类型: {node_type_str}，有效类型: {valid_types}",
            }

        graph = self._get_graph()
        node_id = graph.add_node(
            node_type=node_type,
            name=name,
            description=description,
            source_path=source_path,
            tags=tags if isinstance(tags, list) else [],
        )

        return {
            "success": True,
            "stdout": f"节点添加成功\n节点ID: {node_id}\n名称: {name}\n类型: {node_type_str}",
            "stderr": "",
        }

    def _query_nodes(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """查询知识节点"""
        node_type_str = args.get("node_type", "").strip()
        tags = args.get("tags", [])
        name_pattern = args.get("name", "").strip()
        limit = args.get("limit")

        node_type: Optional[NodeType] = None
        if node_type_str:
            try:
                node_type = NodeType(node_type_str)
            except ValueError:
                valid_types = [t.value for t in NodeType]
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"无效的节点类型: {node_type_str}，有效类型: {valid_types}",
                }

        graph = self._get_graph()
        nodes = graph.query_nodes(
            node_type=node_type,
            tags=tags if isinstance(tags, list) else None,
            name_pattern=name_pattern if name_pattern else None,
            limit=limit if isinstance(limit, int) else None,
        )

        if not nodes:
            return {"success": True, "stdout": "未找到匹配的节点", "stderr": ""}

        output_lines = [f"找到 {len(nodes)} 个节点:\n"]
        for i, node in enumerate(nodes, 1):
            output_lines.append(f"## 节点 {i}: {node.name}")
            output_lines.append(f"- ID: {node.node_id}")
            output_lines.append(f"- 类型: {node.node_type.value}")
            desc = (
                node.description[:100] + "..."
                if len(node.description) > 100
                else node.description
            )
            output_lines.append(f"- 描述: {desc}")
            if node.tags:
                output_lines.append(f"- 标签: {', '.join(node.tags)}")
            if node.source_path:
                output_lines.append(f"- 来源: {node.source_path}")
            output_lines.append(f"- 更新时间: {node.updated_at.isoformat()}")
            output_lines.append("")

        return {"success": True, "stdout": "\n".join(output_lines), "stderr": ""}

    def _add_edge(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """添加知识关系"""
        source_id = args.get("source_id", "").strip()
        target_id = args.get("target_id", "").strip()
        relation_type_str = args.get("relation_type", "").strip()
        strength = args.get("strength", 1.0)
        description = args.get("description", "").strip()

        if not source_id:
            return {"success": False, "stdout": "", "stderr": "缺少必要参数: source_id"}
        if not target_id:
            return {"success": False, "stdout": "", "stderr": "缺少必要参数: target_id"}
        if not relation_type_str:
            return {
                "success": False,
                "stdout": "",
                "stderr": "缺少必要参数: relation_type",
            }

        try:
            relation_type = RelationType(relation_type_str)
        except ValueError:
            valid_types = [t.value for t in RelationType]
            return {
                "success": False,
                "stdout": "",
                "stderr": f"无效的关系类型: {relation_type_str}，有效类型: {valid_types}",
            }

        graph = self._get_graph()
        edge_id = graph.add_edge(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=float(strength) if strength else 1.0,
            description=description if description else None,
        )

        if edge_id is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "添加关系失败：源节点或目标节点不存在",
            }

        return {
            "success": True,
            "stdout": f"关系添加成功\n边ID: {edge_id}\n源节点: {source_id}\n目标节点: {target_id}\n关系类型: {relation_type_str}",
            "stderr": "",
        }

    def _get_related(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取相关知识"""
        node_id = args.get("node_id", "").strip()
        depth = args.get("depth", 2)
        limit = args.get("limit", 10)

        if not node_id:
            return {"success": False, "stdout": "", "stderr": "缺少必要参数: node_id"}

        graph = self._get_graph()
        node = graph.get_node(node_id)
        if node is None:
            return {"success": False, "stdout": "", "stderr": f"节点不存在: {node_id}"}

        related_nodes = graph.get_related_knowledge(
            node_id=node_id,
            depth=int(depth) if depth else 2,
            limit=int(limit) if limit else 10,
        )

        if not related_nodes:
            return {
                "success": True,
                "stdout": f"节点 '{node.name}' 没有相关知识",
                "stderr": "",
            }

        output_lines = [f"节点 '{node.name}' 的相关知识 ({len(related_nodes)} 个):\n"]
        for i, rn in enumerate(related_nodes, 1):
            output_lines.append(f"## 相关节点 {i}: {rn.name}")
            output_lines.append(f"- ID: {rn.node_id}")
            output_lines.append(f"- 类型: {rn.node_type.value}")
            desc = (
                rn.description[:100] + "..."
                if len(rn.description) > 100
                else rn.description
            )
            output_lines.append(f"- 描述: {desc}")
            if rn.tags:
                output_lines.append(f"- 标签: {', '.join(rn.tags)}")
            output_lines.append("")

        return {"success": True, "stdout": "\n".join(output_lines), "stderr": ""}
