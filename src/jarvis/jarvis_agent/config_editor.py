# -*- coding: utf-8 -*-
"""配置编辑器模块，负责配置文件的编辑功能"""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer

from jarvis.jarvis_utils.output import PrettyOutput


class ConfigEditor:
    """配置文件编辑器"""

    @staticmethod
    def get_default_editor() -> Optional[str]:
        """根据操作系统获取默认编辑器"""
        if platform.system() == "Windows":
            # 优先级：终端工具 -> 代码编辑器 -> 通用文本编辑器
            editors = ["nvim", "vim", "nano", "code", "notepad++", "notepad"]
        else:
            # 优先级：终端工具 -> 代码编辑器 -> 通用文本编辑器
            editors = ["nvim", "vim", "vi", "nano", "emacs", "code", "gedit", "kate"]

        return next((e for e in editors if shutil.which(e)), None)

    @staticmethod
    def edit_config(config_file: Optional[str] = None) -> None:
        """编辑配置文件"""
        config_file_path = (
            Path(config_file)
            if config_file
            else Path(os.path.expanduser("~/.jarvis/config.yaml"))
        )

        editor = ConfigEditor.get_default_editor()

        if editor:
            try:
                subprocess.run(
                    [editor, str(config_file_path)],
                    check=True,
                    shell=(platform.system() == "Windows"),
                )
                raise typer.Exit(code=0)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                PrettyOutput.auto_print(f"❌ Failed to open editor: {e}")
                raise typer.Exit(code=1)
        else:
            PrettyOutput.auto_print(
                "❌ No suitable editor found. Please install one of: vim, nano, emacs, code"
            )
            raise typer.Exit(code=1)
