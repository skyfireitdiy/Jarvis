# -*- coding: utf-8 -*-
"""Node 模式基础运行时数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .node_config import DEFAULT_LOCAL_NODE_ID, NodeRuntimeConfig


@dataclass
class NodeInfo:
    node_id: str
    status: str = "online"
    connected_at: Optional[str] = None
    last_heartbeat_at: Optional[str] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)
    connection_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRouteInfo:
    agent_id: str
    node_id: str
    status: str = "running"
    working_dir: Optional[str] = None
    port: Optional[int] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "node_id": self.node_id,
            "status": self.status,
            "working_dir": self.working_dir,
            "port": self.port,
            "updated_at": self.updated_at,
        }


class AgentRouteRegistry:
    def __init__(self) -> None:
        self._routes: Dict[str, AgentRouteInfo] = {}

    def register(self, route: AgentRouteInfo) -> None:
        route.updated_at = datetime.utcnow().isoformat()
        self._routes[route.agent_id] = route

    def get(self, agent_id: str) -> Optional[AgentRouteInfo]:
        return self._routes.get(agent_id)

    def remove(self, agent_id: str) -> None:
        self._routes.pop(agent_id, None)

    def list_all(self) -> list[dict]:
        return [route.to_dict() for route in self._routes.values()]


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: Dict[str, NodeInfo] = {}

    def upsert(self, node_info: NodeInfo) -> None:
        if node_info.connected_at is None:
            node_info.connected_at = datetime.utcnow().isoformat()
        node_info.last_heartbeat_at = datetime.utcnow().isoformat()
        self._nodes[node_info.node_id] = node_info

    def mark_heartbeat(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            return
        node.last_heartbeat_at = datetime.utcnow().isoformat()
        node.status = "online"

    def mark_offline(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            return
        node.status = "offline"

    def get(self, node_id: str) -> Optional[NodeInfo]:
        return self._nodes.get(node_id)

    def list_all(self) -> list[dict]:
        return [node.__dict__.copy() for node in self._nodes.values()]


class NodeTokenSyncState:
    def __init__(self) -> None:
        self.last_synced_at: Optional[str] = None
        self.sync_status: str = "pending"
        self.source_node_id: Optional[str] = None
        self.error_message: Optional[str] = None

    def mark_success(self, source_node_id: str) -> None:
        self.last_synced_at = datetime.utcnow().isoformat()
        self.sync_status = "success"
        self.source_node_id = source_node_id
        self.error_message = None

    def mark_failed(self, error_message: str, source_node_id: Optional[str] = None) -> None:
        self.last_synced_at = datetime.utcnow().isoformat()
        self.sync_status = "failed"
        self.source_node_id = source_node_id
        self.error_message = error_message


class NodeRuntime:
    def __init__(self, config: NodeRuntimeConfig) -> None:
        self.config = config
        self.local_node_id = config.effective_node_id if config.is_child else DEFAULT_LOCAL_NODE_ID
        self.node_registry = NodeRegistry()
        self.agent_route_registry = AgentRouteRegistry()
        self.token_sync_state = NodeTokenSyncState()
        self.status = "bootstrapping"

    @property
    def is_ready(self) -> bool:
        if self.config.is_master:
            return self.status == "ready"
        return self.status == "ready" and self.token_sync_state.sync_status == "success"

    def mark_ready(self) -> None:
        self.status = "ready"

    def mark_degraded(self) -> None:
        self.status = "degraded"
