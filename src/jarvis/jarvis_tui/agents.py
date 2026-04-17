"""Agent管理模块"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Agent信息"""

    agent_id: str
    name: str
    work_dir: str
    status: str = "stopped"
    node_id: str = "master"
    created_at: Optional[datetime] = None


class AgentManager:
    """Agent管理器"""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._current_agent_id: Optional[str] = None
        self._selected_agents: set = set()

    def get_agents(self) -> List[AgentInfo]:
        """获取所有Agent列表"""
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """获取指定Agent"""
        return self._agents.get(agent_id)

    def get_current_agent(self) -> Optional[AgentInfo]:
        """获取当前选中的Agent"""
        if self._current_agent_id:
            return self._agents.get(self._current_agent_id)
        return None

    def get_current_agent_id(self) -> Optional[str]:
        """获取当前Agent ID"""
        return self._current_agent_id

    def set_current_agent(self, agent_id: str) -> None:
        """设置当前Agent"""
        if agent_id in self._agents:
            self._current_agent_id = agent_id
            logger.info(f"Current agent set to: {agent_id}")
        else:
            raise AgentNotFoundError(f"Agent not found: {agent_id}")

    def add_agent(self, agent: AgentInfo) -> None:
        """添加Agent"""
        self._agents[agent.agent_id] = agent
        logger.info(f"Agent added: {agent.agent_id}")

    def remove_agent(self, agent_id: str) -> None:
        """移除Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]

            # 如果删除的是当前Agent，切换到其他Agent
            if self._current_agent_id == agent_id:
                if self._agents:
                    self._current_agent_id = next(iter(self._agents))
                else:
                    self._current_agent_id = None

            logger.info(f"Agent removed: {agent_id}")
        else:
            raise AgentNotFoundError(f"Agent not found: {agent_id}")

    def update_agent_status(self, agent_id: str, status: str) -> None:
        """更新Agent状态"""
        if agent_id in self._agents:
            self._agents[agent_id].status = status
            logger.debug(f"Agent {agent_id} status updated to: {status}")

    def clear(self) -> None:
        """清空所有Agent"""
        self._agents.clear()
        self._current_agent_id = None

    def process_agent_list(self, agents_data: List[Dict[str, Any]]) -> None:
        """处理从Gateway收到的Agent列表

        Args:
            agents_data: Agent数据列表
        """
        for agent_data in agents_data:
            agent_id = agent_data.get("agent_id")
            if not agent_id:
                continue

            agent = AgentInfo(
                agent_id=agent_id,
                name=agent_data.get("name", agent_id),
                work_dir=agent_data.get("work_dir", ""),
                status=agent_data.get("status", "stopped"),
                node_id=agent_data.get("node_id", "master"),
            )

            if agent_id in self._agents:
                # 更新现有Agent
                self._agents[agent_id].status = agent.status
                self._agents[agent_id].name = agent.name
            else:
                # 添加新Agent
                self._agents[agent_id] = agent

    async def rename_agent(self, agent_id: str, new_name: str) -> bool:
        """重命名Agent

        Args:
            agent_id: Agent ID
            new_name: 新名称

        Returns:
            bool: 重命名是否成功

        Raises:
            AgentNotFoundError: Agent不存在
            ValueError: 名称无效
        """
        if not new_name or len(new_name.strip()) == 0:
            raise ValueError("Agent名称不能为空")

        if len(new_name) > 64:
            raise ValueError("Agent名称不能超过64个字符")

        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent不存在: {agent_id}")

        self._agents[agent_id].name = new_name.strip()
        logger.info(f"Agent {agent_id} renamed to: {new_name}")
        return True

    def get_agent_by_name(self, name: str) -> Optional[AgentInfo]:
        """根据名称获取Agent"""
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    async def batch_delete_agents(self, agent_ids: List[str]) -> Dict[str, bool]:
        """批量删除Agent

        Args:
            agent_ids: Agent ID列表（最多50个）

        Returns:
            Dict[str, bool]: 每个Agent的删除结果
        """
        if len(agent_ids) > 50:
            raise ValueError("批量删除最多支持50个Agent")

        results: Dict[str, bool] = {}

        for agent_id in agent_ids:
            try:
                if agent_id in self._agents:
                    del self._agents[agent_id]

                    # 如果删除的是当前Agent，切换到其他Agent
                    if self._current_agent_id == agent_id:
                        if self._agents:
                            self._current_agent_id = next(iter(self._agents))
                        else:
                            self._current_agent_id = None

                    results[agent_id] = True
                    logger.info(f"Agent deleted: {agent_id}")
                else:
                    results[agent_id] = False
                    logger.warning(f"Agent not found: {agent_id}")
            except Exception as e:
                results[agent_id] = False
                logger.error(f"Failed to delete agent {agent_id}: {e}")

        return results

    def get_selected_agents(self) -> List[str]:
        """获取选中的Agent列表"""
        return list(self._selected_agents)

    def select_agent(self, agent_id: str) -> None:
        """选中Agent"""
        if agent_id in self._agents:
            self._selected_agents.add(agent_id)

    def deselect_agent(self, agent_id: str) -> None:
        """取消选中Agent"""
        self._selected_agents.discard(agent_id)

    def select_all_agents(self) -> None:
        """选中所有Agent"""
        self._selected_agents = set(self._agents.keys())

    def deselect_all_agents(self) -> None:
        """取消选中所有Agent"""
        self._selected_agents.clear()

    def is_agent_selected(self, agent_id: str) -> bool:
        """检查Agent是否被选中"""
        return agent_id in self._selected_agents


class AgentNotFoundError(Exception):
    """Agent不存在错误"""

    pass
