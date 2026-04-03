# -*- coding: utf-8 -*-
"""Node 模式配置定义与校验。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


VALID_NODE_MODES = {"master", "child"}
DEFAULT_LOCAL_NODE_ID = "master"


@dataclass
class NodeRuntimeConfig:
    """Node 运行时配置。"""

    node_mode: str = "master"
    node_id: Optional[str] = None
    master_url: Optional[str] = None
    node_secret: Optional[str] = None

    @property
    def is_master(self) -> bool:
        return self.node_mode == "master"

    @property
    def is_child(self) -> bool:
        return self.node_mode == "child"

    @property
    def effective_node_id(self) -> str:
        if self.node_id and self.node_id.strip():
            return self.node_id.strip()
        return DEFAULT_LOCAL_NODE_ID

    def to_dict(self) -> dict:
        return {
            "node_mode": self.node_mode,
            "node_id": self.effective_node_id,
            "master_url": self.master_url,
            "node_secret": "***" if self.node_secret else None,
            "is_master": self.is_master,
            "is_child": self.is_child,
        }


def build_node_runtime_config(
    node_mode: Optional[str] = None,
    node_id: Optional[str] = None,
    master_url: Optional[str] = None,
    node_secret: Optional[str] = None,
) -> NodeRuntimeConfig:
    """构建并校验 NodeRuntimeConfig。"""

    normalized_mode = (node_mode or "master").strip().lower()
    if normalized_mode not in VALID_NODE_MODES:
        raise ValueError(
            f"INVALID_NODE_MODE: node_mode must be one of {sorted(VALID_NODE_MODES)}"
        )

    normalized_secret = (
        node_secret.strip()
        if isinstance(node_secret, str) and node_secret.strip()
        else None
    )

    config = NodeRuntimeConfig(
        node_mode=normalized_mode,
        node_id=(node_id.strip() if isinstance(node_id, str) and node_id.strip() else None),
        master_url=(
            master_url.strip() if isinstance(master_url, str) and master_url.strip() else None
        ),
        node_secret=normalized_secret,
    )
    validate_node_config(config)
    return config



def validate_node_config(config: NodeRuntimeConfig) -> None:
    """校验 node 配置。"""

    if config.node_mode not in VALID_NODE_MODES:
        raise ValueError(
            f"INVALID_NODE_MODE: node_mode must be one of {sorted(VALID_NODE_MODES)}"
        )

    if config.is_child:
        missing = []
        if not config.node_id:
            missing.append("node_id")
        if not config.master_url:
            missing.append("master_url")
        if not config.node_secret:
            missing.append("node_secret")
        if missing:
            raise ValueError(
                "MISSING_NODE_CONFIG: child mode requires " + ", ".join(missing)
            )
