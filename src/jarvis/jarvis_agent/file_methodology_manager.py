# -*- coding: utf-8 -*-
"""
文件和方法论管理器模块
负责处理文件上传和方法论加载功能
"""

from typing import Any

from jarvis.jarvis_agent.utils import join_prompts
from jarvis.jarvis_utils.methodology import load_methodology
from jarvis.jarvis_utils.output import PrettyOutput


class FileMethodologyManager:
    """文件和方法论管理器，负责处理文件上传和方法论相关功能"""

    def __init__(self, agent: Any) -> None:
        """
        初始化文件和方法论管理器

        参数:
            agent: Agent实例
        """
        self.agent: Any = agent

    def handle_files_and_methodology(self) -> None:
        """处理文件上传和方法论加载"""
        self._handle_local_mode()

    def _handle_local_mode(self) -> None:
        """处理本地模式（不支持文件上传）"""
        if self.agent.files:
            PrettyOutput.auto_print("⚠️ 不支持上传文件，将忽略文件列表")
        if self.agent.use_methodology:
            self._load_local_methodology()

    def _load_local_methodology(self) -> None:
        """加载本地方法论"""
        msg = self.agent.session.prompt
        for handler in self.agent.input_handler:
            msg, _ = handler(msg, self.agent)

        from jarvis.jarvis_agent.memory_manager import MemoryManager

        MemoryManager(self.agent)
        # 使用normal模型加载方法论，传递 Agent 的 llm_group 以确保使用正确的配置
        methodology = load_methodology(msg, self.agent.get_tool_registry())
        self.agent.session.prompt = join_prompts(
            [
                self.agent.session.prompt,
                f"以下是历史类似问题的执行经验，可参考：\n{methodology}",
            ]
        )

        # 方法论加载完成后，自动选择规则
        self._auto_select_rule(msg)

    def _auto_select_rule(self, task_description: str) -> None:
        """根据任务描述自动选择规则

        参数:
            task_description: 任务描述字符串
        """
        try:
            # 调用规则管理器的自动选择方法
            selected_rule = self.agent.rules_manager.select_rule_by_task(
                task_description
            )

            # 如果成功选择了规则，将其添加到已加载规则列表中
            if selected_rule:
                # 检查规则是否已经在列表中
                if selected_rule not in self.agent.loaded_rule_names:
                    self.agent.loaded_rule_names.append(selected_rule)

                    # 重新加载所有规则，包括新选择的规则
                    self.agent.loaded_rules, _ = (
                        self.agent.rules_manager.load_all_rules(
                            ",".join(self.agent.loaded_rule_names)
                        )
                    )

                    PrettyOutput.auto_print(
                        f"✅ 已根据任务自动选择规则: {selected_rule}"
                    )
                else:
                    PrettyOutput.auto_print(f"ℹ️ 规则已存在: {selected_rule}")
        except Exception as e:
            # 规则选择失败不影响主流程，静默处理
            PrettyOutput.auto_print(f"⚠️ 自动选择规则失败: {e}")
