# -*- coding: utf-8 -*-
"""
编译命令处理模块
"""

import json
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import typer


class CompileCommandsManager:
    """编译命令管理器"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._compile_commands_cache: Optional[List[Dict[str, Any]]] = None
        self._compile_commands_path: Optional[Path] = None

    def _find_compile_commands(self) -> Optional[Path]:
        """
        查找 compile_commands.json 文件。
        搜索顺序：
        1. project_root / compile_commands.json
        2. project_root / build / compile_commands.json
        3. project_root 的父目录及向上查找（最多向上3层）
        """
        # 首先在 project_root 下查找
        candidates = [
            self.project_root / "compile_commands.json",
            self.project_root / "build" / "compile_commands.json",
        ]
        # 向上查找（最多3层）
        current = self.project_root.parent
        for _ in range(3):
            if current and current.exists():
                candidates.append(current / "compile_commands.json")
                current = current.parent
            else:
                break

        for path in candidates:
            if path.exists() and path.is_file():
                return path.resolve()
        return None

    def load_compile_commands(self) -> Optional[List[Dict[str, Any]]]:
        """
        加载 compile_commands.json 文件。
        如果已缓存，直接返回缓存结果。
        """
        if self._compile_commands_cache is not None:
            return self._compile_commands_cache

        compile_commands_path = self._find_compile_commands()
        if compile_commands_path is None:
            self._compile_commands_cache = []
            self._compile_commands_path = None
            return None

        try:
            with compile_commands_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._compile_commands_cache = data
                    self._compile_commands_path = compile_commands_path
                    typer.secho(
                        f"[c2rust-transpiler][compile_commands] 已加载: {compile_commands_path} ({len(data)} 条记录)",
                        fg=typer.colors.BLUE,
                    )
                    return data
        except Exception as e:
            typer.secho(
                f"[c2rust-transpiler][compile_commands] 加载失败: {compile_commands_path}: {e}",
                fg=typer.colors.YELLOW,
            )
            self._compile_commands_cache = []
            self._compile_commands_path = None
            return None

        self._compile_commands_cache = []
        self._compile_commands_path = None
        return None

    def extract_compile_flags(self, c_file_path: Union[str, Path]) -> Optional[str]:
        """
        从 compile_commands.json 中提取指定 C 文件的编译参数。

        如果 compile_commands.json 中存在 arguments 字段，则用空格连接该数组并返回。
        如果只有 command 字段，则直接返回 command 字符串。

        返回格式：
        - 如果存在 arguments：用空格连接的参数字符串，例如 "-I/usr/include -DDEBUG"
        - 如果只有 command：完整的编译命令字符串，例如 "gcc -I/usr/include -DDEBUG file.c"

        如果未找到或解析失败，返回 None。
        """
        compile_commands = self.load_compile_commands()
        if not compile_commands:
            return None

        # 规范化目标文件路径
        try:
            target_path = Path(c_file_path)
            if not target_path.is_absolute():
                target_path = (self.project_root / target_path).resolve()
            target_path = target_path.resolve()
        except Exception:
            return None

        # 查找匹配的编译命令
        for entry in compile_commands:
            if not isinstance(entry, dict):
                continue  # type: ignore

            entry_file = entry.get("file")
            if not entry_file:
                continue

            try:
                entry_path = Path(entry_file)
                if not entry_path.is_absolute() and entry.get("directory"):
                    directory = entry.get("directory")
                    if directory is not None:
                        entry_path = (Path(directory) / entry_path).resolve()
                entry_path = entry_path.resolve()

                # 路径匹配（支持相对路径和绝对路径）
                if entry_path == target_path:
                    # 如果存在 arguments，用空格连接并返回
                    arguments = entry.get("arguments")
                    if isinstance(arguments, list):
                        # 过滤掉空字符串，然后用空格连接
                        args = [str(arg) for arg in arguments if arg]
                        return " ".join(args) if args else None
                    # 如果只有 command，直接返回 command 字符串
                    elif entry.get("command"):
                        command = entry.get("command", "")
                        return command if command else None
            except Exception:
                continue

        return None
