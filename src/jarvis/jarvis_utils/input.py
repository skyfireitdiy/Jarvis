# -*- coding: utf-8 -*-
"""
输入处理模块
该模块提供了处理Jarvis系统中用户输入的实用工具。
包含：
- 支持历史记录的单行输入
- 增强补全功能的多行输入
- 带有模糊匹配的文件路径补全
- 用于输入控制的自定义键绑定
"""
from colorama import Fore  # type: ignore
from colorama import Style as ColoramaStyle  # type: ignore
from fuzzywuzzy import process  # type: ignore
from prompt_toolkit import PromptSession  # type: ignore
from prompt_toolkit.completion import (
    CompleteEvent,
    Completer,
    Completion,  # type: ignore
    PathCompleter,
)  # type: ignore
from prompt_toolkit.document import Document  # type: ignore
from prompt_toolkit.formatted_text import FormattedText  # type: ignore
from prompt_toolkit.key_binding import KeyBindings  # type: ignore
from prompt_toolkit.styles import Style as PromptStyle  # type: ignore

from jarvis.jarvis_utils.config import get_replace_map
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import copy_to_clipboard


def get_single_line_input(tip: str) -> str:
    """
    获取支持历史记录的单行输入。

    参数：
        tip: 要显示的提示信息

    返回：
        str: 用户的输入
    """
    session: PromptSession = PromptSession(history=None)
    style = PromptStyle.from_dict(
        {
            "prompt": "ansicyan",
        }
    )
    return session.prompt(f"{tip}", style=style)


class FileCompleter(Completer):
    """
    带有模糊匹配的文件路径自定义补全器。

    属性：
        path_completer: 基础路径补全器
        max_suggestions: 显示的最大建议数量
        min_score: 建议的最小匹配分数
    """

    def __init__(self):
        """使用默认设置初始化文件补全器。"""
        self.path_completer = PathCompleter()
        self.max_suggestions = 10
        self.min_score = 10
        self.replace_map = get_replace_map()

    def get_completions(self, document: Document, _: CompleteEvent) -> Completion:  # type: ignore
        """
        生成带有模糊匹配的文件路径补全建议。

        参数：
            document: 当前正在编辑的文档
            complete_event: 补全事件

        生成：
            Completion: 建议的补全项
        """
        text = document.text_before_cursor
        cursor_pos = document.cursor_position
        # 查找文本中的所有@位置
        at_positions = [i for i, char in enumerate(text) if char == "@"]
        if not at_positions:
            return
        # 获取最后一个@位置
        current_at_pos = at_positions[-1]
        # 如果光标不在最后一个@之后，则不补全
        if cursor_pos <= current_at_pos:
            return
        # 检查@之后是否有空格
        text_after_at = text[current_at_pos + 1 : cursor_pos]
        if " " in text_after_at:
            return

        # 获取当前@之后的文本
        file_path = text_after_at.strip()
        # 计算替换长度
        replace_length = len(text_after_at) + 1

        # 获取所有可能的补全项
        all_completions = []

        # 1. 添加特殊标记
        all_completions.extend(
            [(ot(tag), self._get_description(tag)) for tag in self.replace_map.keys()]
        )
        all_completions.extend(
            [
                (ot("Summary"), "总结"),
                (ot("Clear"), "清除历史"),
                (ot("ToolUsage"), "工具使用说明"),
                (ot("ReloadConfig"), "重新加载配置"),
                (ot("SaveSession"), "保存当前会话"),
            ]
        )

        # 2. 添加文件列表
        try:
            import subprocess

            result = subprocess.run(
                ["git", "ls-files"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                all_completions.extend(
                    [
                        (path, "File")
                        for path in result.stdout.splitlines()
                        if path.strip()
                    ]
                )
        except Exception:
            pass

        # 统一过滤和排序
        if file_path:
            # 使用模糊匹配过滤
            scored_items = process.extract(
                file_path,
                [item[0] for item in all_completions],
                limit=self.max_suggestions,
            )
            scored_items = [
                (item[0], item[1]) for item in scored_items if item[1] > self.min_score
            ]
            # 创建映射以便查找描述
            completion_map = {item[0]: item[1] for item in all_completions}
            # 生成补全项
            for text, score in scored_items:
                display_text = text
                if score < 100:
                    display_text = f"{text} ({score}%)"
                yield Completion(
                    text=f"'{text}'",
                    start_position=-replace_length,
                    display=display_text,
                    display_meta=completion_map.get(text, ""),
                )  # type: ignore
        else:
            # 没有输入时返回前max_suggestions个建议
            for text, desc in all_completions[: self.max_suggestions]:
                yield Completion(
                    text=f"'{text}'",
                    start_position=-replace_length,
                    display=text,
                    display_meta=desc,
                )  # type: ignore

    def _get_description(self, tag: str) -> str:
        """获取标记的描述信息"""
        if tag in self.replace_map:
            return (
                self.replace_map[tag].get("description", tag) + "(Append)"
                if "append" in self.replace_map[tag] and self.replace_map[tag]["append"]
                else "(Replace)"
            )
        return tag


def user_confirm(tip: str, default: bool = True) -> bool:
    """提示用户确认是/否问题

    参数:
        tip: 显示给用户的消息
        default: 用户直接回车时的默认响应

    返回:
        bool: 用户确认返回True，否则返回False
    """
    try:
        suffix = "[Y/n]" if default else "[y/N]"
        ret = get_single_line_input(f"{tip} {suffix}: ")
        return default if ret == "" else ret.lower() == "y"
    except KeyboardInterrupt:
        return False


def get_multiline_input(tip: str) -> str:
    """
    获取带有增强补全和确认功能的多行输入。

    参数：
        tip: 要显示的提示信息

    返回：
        str: 用户的输入，如果取消则返回空字符串
    """
    # 显示输入说明
    PrettyOutput.section(
        "用户输入 - 使用 @ 触发文件补全，Tab 选择补全项，Ctrl+J 提交，Ctrl+O 从历史记录中选择消息复制，按 Ctrl+C 取消输入",
        OutputType.USER,
    )
    print(f"{Fore.GREEN}{tip}{ColoramaStyle.RESET_ALL}")
    # 配置键绑定
    bindings = KeyBindings()

    @bindings.add("enter")
    def _(event):
        """处理回车键以进行补全或换行。"""
        if event.current_buffer.complete_state:
            event.current_buffer.apply_completion(
                event.current_buffer.complete_state.current_completion
            )
        else:
            event.current_buffer.insert_text("\n")

    @bindings.add("c-j")
    def _(event):
        """处理Ctrl+J以提交输入。"""
        event.current_buffer.validate_and_handle()

    @bindings.add("c-o")
    def _(event):
        """处理Ctrl+O以从历史记录中选择并复制消息。"""
        from jarvis.jarvis_utils.globals import get_message_history

        history = get_message_history()
        if not history:
            PrettyOutput.print("没有可复制的消息", OutputType.INFO)
            return

        # 暂停当前App，显示选择列表
        app = event.app
        app.suspend_to_background()

        try:
            print("消息历史记录:")
            for i, msg in enumerate(history):
                # 缩短长消息以提高可读性
                display_msg = (msg[:70] + "...") if len(msg) > 70 else msg
                print(f"  {i + 1}: {display_msg.strip()}")

            # 提示用户选择
            while True:
                try:
                    choice_str = get_single_line_input("请输入要复制的条目序号 (或输入c取消): ")
                    if choice_str.lower() == "c":
                        print("已取消")
                        return
                    choice = int(choice_str) - 1
                    if 0 <= choice < len(history):
                        selected_msg = history[choice]
                        copy_to_clipboard(selected_msg)
                        PrettyOutput.print(f"已复制消息: {selected_msg[:70]}...", OutputType.SUCCESS)
                        break
                    else:
                        print("无效的序号，请重试。")
                except ValueError:
                    print("无效的输入，请输入数字。")
                except Exception:
                    break
        finally:
            # 恢复App
            app.resume_from_background()

    # 配置提示会话
    style = PromptStyle.from_dict(
        {
            "prompt": "ansicyan",
        }
    )
    try:
        import os

        from prompt_toolkit.history import FileHistory  # type: ignore

        from jarvis.jarvis_utils.config import get_data_dir

        # 获取数据目录路径
        history_dir = get_data_dir()
        # 初始化带历史记录的会话
        session: PromptSession = PromptSession(
            history=FileHistory(os.path.join(history_dir, "multiline_input_history")),
            completer=FileCompleter(),
            key_bindings=bindings,
            complete_while_typing=True,
            multiline=True,
            vi_mode=False,
            mouse_support=False,
        )
        prompt = FormattedText([("class:prompt", ">>> ")])
        # 获取输入
        text = session.prompt(
            prompt,
            style=style,
        ).strip()
        return text
    except KeyboardInterrupt:
        PrettyOutput.print("输入已取消", OutputType.INFO)
        return ""
