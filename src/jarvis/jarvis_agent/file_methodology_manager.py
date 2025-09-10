# -*- coding: utf-8 -*-
"""
文件和方法论管理器模块
负责处理文件上传和方法论加载功能
"""
import os
import tempfile

from jarvis.jarvis_utils.methodology import load_methodology, upload_methodology
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class FileMethodologyManager:
    """文件和方法论管理器，负责处理文件上传和方法论相关功能"""

    def __init__(self, agent):
        """
        初始化文件和方法论管理器

        参数:
            agent: Agent实例
        """
        self.agent = agent

    def handle_files_and_methodology(self):
        """处理文件上传和方法论加载"""
        if self.agent.model and self.agent.model.support_upload_files():
            self._handle_file_upload_mode()
        else:
            self._handle_local_mode()

    def _handle_file_upload_mode(self):
        """处理支持文件上传的模式"""
        if self.agent.use_methodology:
            self._handle_methodology_upload()
        elif self.agent.files:
            self._handle_files_upload()

    def _handle_methodology_upload(self):
        """处理方法论上传"""
        if not upload_methodology(self.agent.model, other_files=self.agent.files):  # type: ignore
            if self.agent.files:
                PrettyOutput.print("文件上传失败，将忽略文件列表", OutputType.WARNING)
            # 上传失败则回退到本地加载
            self._load_local_methodology()
        else:
            # 上传成功

            if self.agent.files:
                self.agent.session.prompt = f"{self.agent.session.prompt}\n\n上传的文件包含历史对话信息和方法论文件，可以从中获取一些经验信息。"
            else:
                self.agent.session.prompt = f"{self.agent.session.prompt}\n\n上传的文件包含历史对话信息，可以从中获取一些经验信息。"

    def _handle_files_upload(self):
        """处理普通文件上传"""
        if not self.agent.model.upload_files(self.agent.files):  # type: ignore
            PrettyOutput.print("文件上传失败，将忽略文件列表", OutputType.WARNING)
        else:
            self.agent.session.prompt = f"{self.agent.session.prompt}\n\n上传的文件包含历史对话信息，可以从中获取一些经验信息。"

    def _handle_local_mode(self):
        """处理本地模式（不支持文件上传）"""
        if self.agent.files:
            PrettyOutput.print("不支持上传文件，将忽略文件列表", OutputType.WARNING)
        if self.agent.use_methodology:
            self._load_local_methodology()

    def _load_local_methodology(self):
        """加载本地方法论"""
        msg = self.agent.session.prompt
        for handler in self.agent.input_handler:
            msg, _ = handler(msg, self.agent)

        from jarvis.jarvis_agent.memory_manager import MemoryManager

        MemoryManager(self.agent)
        methodology = load_methodology(
            msg,
            self.agent.get_tool_registry(),
            platform_name=self.agent.model.platform_name(),
            model_name=self.agent.model.name(),
        )
        self.agent.session.prompt = f"{self.agent.session.prompt}\n\n以下是历史类似问题的执行经验，可参考：\n{methodology}"

    def handle_history_with_file_upload(self) -> str:
        """使用文件上传方式处理历史"""
        tmp_file_name = ""
        try:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, mode="w", encoding="utf-8"
            )
            tmp_file_name = tmp_file.name
            tmp_file.write(self.agent.session.prompt)
            tmp_file.close()

            self.agent.clear_history()

            if self.agent.model and self.agent.model.upload_files([tmp_file_name]):
                return "上传的文件是历史对话信息，请基于历史对话信息继续完成任务。"
            else:
                return ""
        finally:
            if tmp_file_name and os.path.exists(tmp_file_name):
                os.remove(tmp_file_name)
