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
import os
from typing import Iterable

from colorama import Fore
from colorama import Style as ColoramaStyle  # type: ignore
from fuzzywuzzy import process  # type: ignore
from prompt_toolkit import PromptSession  # type: ignore
from prompt_toolkit.completion import CompleteEvent  # type: ignore
from prompt_toolkit.completion import (
    Completer,
    Completion,
    PathCompleter,
)
from prompt_toolkit.document import Document  # type: ignore
from prompt_toolkit.formatted_text import FormattedText  # type: ignore
from prompt_toolkit.history import FileHistory  # type: ignore
from prompt_toolkit.key_binding import KeyBindings  # type: ignore
from prompt_toolkit.styles import Style as PromptStyle  # type: ignore

from jarvis.jarvis_utils.config import get_data_dir, get_replace_map
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import copy_to_clipboard

# Sentinel value to indicate that Ctrl+O was pressed
CTRL_O_SENTINEL = "__CTRL_O_PRESSED__"


def get_single_line_input(tip: str) -> str:
    """
    获取支持历史记录的单行输入。
    """
    session: PromptSession = PromptSession(history=None)
    style = PromptStyle.from_dict({"prompt": "ansicyan"})
    return session.prompt(f"{tip}", style=style)


class FileCompleter(Completer):
    """
    带有模糊匹配的文件路径自定义补全器。
    """

    def __init__(self):
        self.path_completer = PathCompleter()
        self.max_suggestions = 10
        self.min_score = 10
        self.replace_map = get_replace_map()

    def get_completions(
        self, document: Document, _: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        cursor_pos = document.cursor_position
        at_positions = [i for i, char in enumerate(text) if char == "@"]
        if not at_positions:
            return
        current_at_pos = at_positions[-1]
        if cursor_pos <= current_at_pos:
            return
        text_after_at = text[current_at_pos + 1 : cursor_pos]
        if " " in text_after_at:
            return

        file_path = text_after_at.strip()
        replace_length = len(text_after_at) + 1

        all_completions = []
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

        if file_path:
            scored_items = process.extract(
                file_path,
                [item[0] for item in all_completions],
                limit=self.max_suggestions,
            )
            scored_items = [
                (item[0], item[1]) for item in scored_items if item[1] > self.min_score
            ]
            completion_map = {item[0]: item[1] for item in all_completions}
            for text, score in scored_items:
                display_text = f"{text} ({score}%)" if score < 100 else text
                yield Completion(
                    text=f"'{text}'",
                    start_position=-replace_length,
                    display=display_text,
                    display_meta=completion_map.get(text, ""),
                )
        else:
            for text, desc in all_completions[: self.max_suggestions]:
                yield Completion(
                    text=f"'{text}'",
                    start_position=-replace_length,
                    display=text,
                    display_meta=desc,
                )

    def _get_description(self, tag: str) -> str:
        if tag in self.replace_map:
            return (
                self.replace_map[tag].get("description", tag) + "(Append)"
                if "append" in self.replace_map[tag] and self.replace_map[tag]["append"]
                else "(Replace)"
            )
        return tag


def user_confirm(tip: str, default: bool = True) -> bool:
    """提示用户确认是/否问题"""
    try:
        suffix = "[Y/n]" if default else "[y/N]"
        ret = get_single_line_input(f"{tip} {suffix}: ")
        return default if ret == "" else ret.lower() == "y"
    except KeyboardInterrupt:
        return False


def _show_history_and_copy():
    """
    Displays message history and handles copying to clipboard.
    This function uses standard I/O and is safe to call outside a prompt session.
    """
    from jarvis.jarvis_utils.globals import get_message_history

    history = get_message_history()
    if not history:
        PrettyOutput.print("没有可复制的消息", OutputType.INFO)
        return

    print("\n" + "=" * 20 + " 消息历史记录 " + "=" * 20)
    for i, msg in enumerate(history):
        cleaned_msg = msg.replace("\n", r"\n")
        display_msg = (cleaned_msg[:70] + "...") if len(cleaned_msg) > 70 else cleaned_msg
        print(f"  {i + 1}: {display_msg.strip()}")
    print("=" * 58 + "\n")

    while True:
        try:
            prompt_text = f"{Fore.CYAN}请输入要复制的条目序号 (或输入c取消, 直接回车选择最后一条): {ColoramaStyle.RESET_ALL}"
            choice_str = input(prompt_text)

            if not choice_str:  # User pressed Enter
                if not history:
                    print("没有历史记录可供选择。")
                    break
                choice = len(history) - 1
            elif choice_str.lower() == "c":
                print("已取消")
                break
            else:
                choice = int(choice_str) - 1

            if 0 <= choice < len(history):
                selected_msg = history[choice]
                copy_to_clipboard(selected_msg)
                PrettyOutput.print(
                    f"已复制消息: {selected_msg[:70]}...", OutputType.SUCCESS
                )
                break
            else:
                print("无效的序号，请重试。")
        except ValueError:
            print("无效的输入，请输入数字。")
        except (KeyboardInterrupt, EOFError):
            print("\n操作取消")
            break


def _get_multiline_input_internal(tip: str) -> str:
    """
    Internal function to get multiline input using prompt_toolkit.
    Returns a sentinel value if Ctrl+O is pressed.
    """
    bindings = KeyBindings()

    @bindings.add("enter")
    def _(event):
        if event.current_buffer.complete_state:
            event.current_buffer.apply_completion(
                event.current_buffer.complete_state.current_completion
            )
        else:
            event.current_buffer.insert_text("\n")

    @bindings.add("c-j")
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add("c-o")
    def _(event):
        """Handle Ctrl+O by exiting the prompt and returning the sentinel value."""
        event.app.exit(result=CTRL_O_SENTINEL)

    style = PromptStyle.from_dict({"prompt": "ansicyan"})

    history_dir = get_data_dir()
    session: PromptSession = PromptSession(
        history=FileHistory(os.path.join(history_dir, "multiline_input_history")),
        completer=FileCompleter(),
        key_bindings=bindings,
        complete_while_typing=True,
        multiline=True,
        vi_mode=False,
        mouse_support=False,
    )

    print(f"{Fore.GREEN}{tip}{ColoramaStyle.RESET_ALL}")
    prompt = FormattedText([("class:prompt", ">>> ")])

    try:
        return session.prompt(prompt, style=style, pre_run=lambda: None).strip()
    except (KeyboardInterrupt, EOFError):
        return ""


def get_multiline_input(tip: str) -> str:
    """
    获取带有增强补全和确认功能的多行输入。
    此函数处理控制流，允许在不破坏终端状态的情况下处理历史记录复制。
    """
    PrettyOutput.section(
        "用户输入 - 使用 @ 触发文件补全，Tab 选择补全项，Ctrl+J 提交，Ctrl+O 从历史记录中选择消息复制，按 Ctrl+C/D 取消输入",
        OutputType.USER,
    )

    while True:
        user_input = _get_multiline_input_internal(tip)

        if user_input == CTRL_O_SENTINEL:
            _show_history_and_copy()
            tip = "请继续输入（或按Ctrl+J提交）:"
            continue
        else:
            if not user_input:
                PrettyOutput.print("\n输入已取消", OutputType.INFO)
            return user_input
