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
from typing import Iterable, List

from colorama import Fore
from colorama import Style as ColoramaStyle
from fuzzywuzzy import process
from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.completion import (
    Completer,
    Completion,
    PathCompleter,
)
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style as PromptStyle

from jarvis.jarvis_utils.clipboard import copy_to_clipboard
from jarvis.jarvis_utils.config import get_data_dir, get_replace_map
from jarvis.jarvis_utils.globals import get_message_history
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ot

# Sentinel value to indicate that Ctrl+O was pressed
CTRL_O_SENTINEL = "__CTRL_O_PRESSED__"

# Persistent hint marker for multiline input (shown only once across runs)
_MULTILINE_HINT_MARK_FILE = os.path.join(get_data_dir(), "multiline_enter_hint_shown")


def _multiline_hint_already_shown() -> bool:
    """Check if the multiline Enter hint has been shown before (persisted)."""
    try:
        return os.path.exists(_MULTILINE_HINT_MARK_FILE)
    except Exception:
        return False


def _mark_multiline_hint_shown() -> None:
    """Persist that the multiline Enter hint has been shown."""
    try:
        os.makedirs(os.path.dirname(_MULTILINE_HINT_MARK_FILE), exist_ok=True)
        with open(_MULTILINE_HINT_MARK_FILE, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        # Non-critical persistence failure; ignore to avoid breaking input flow
        pass


def get_single_line_input(tip: str, default: str = "") -> str:
    """
    获取支持历史记录的单行输入。
    """
    session: PromptSession = PromptSession(history=None)
    style = PromptStyle.from_dict({"prompt": "ansicyan", "bottom-toolbar": "fg:#888888"})
    prompt = FormattedText([("class:prompt", f"👤 ❯ {tip}")])
    return session.prompt(prompt, default=default, style=style)


def get_choice(tip: str, choices: List[str]) -> str:
    """
    提供一个可滚动的选择列表供用户选择。
    """
    if not choices:
        raise ValueError("Choices cannot be empty.")

    try:
        terminal_height = os.get_terminal_size().lines
    except OSError:
        terminal_height = 25  # 如果无法确定终端大小，则使用默认高度

    # 为提示和缓冲区保留行
    max_visible_choices = max(5, terminal_height - 4)

    bindings = KeyBindings()
    selected_index = 0
    start_index = 0

    @bindings.add("up")
    def _(event):
        nonlocal selected_index, start_index
        selected_index = (selected_index - 1 + len(choices)) % len(choices)
        if selected_index < start_index:
            start_index = selected_index
        elif selected_index == len(choices) - 1:  # 支持从第一项上翻到最后一项时滚动
            start_index = max(0, len(choices) - max_visible_choices)
        event.app.invalidate()

    @bindings.add("down")
    def _(event):
        nonlocal selected_index, start_index
        selected_index = (selected_index + 1) % len(choices)
        if selected_index >= start_index + max_visible_choices:
            start_index = selected_index - max_visible_choices + 1
        elif selected_index == 0:  # 支持从最后一项下翻到第一项时滚动
            start_index = 0
        event.app.invalidate()

    @bindings.add("enter")
    def _(event):
        event.app.exit(result=choices[selected_index])

    def get_prompt_tokens():
        tokens = [("class:question", f"{tip} (使用上下箭头选择, Enter确认)\n")]

        end_index = min(start_index + max_visible_choices, len(choices))
        visible_choices_slice = choices[start_index:end_index]

        if start_index > 0:
            tokens.append(("class:indicator", "  ... (更多选项在上方) ...\n"))

        for i, choice in enumerate(visible_choices_slice, start=start_index):
            if i == selected_index:
                tokens.append(("class:selected", f"> {choice}\n"))
            else:
                tokens.append(("", f"  {choice}\n"))

        if end_index < len(choices):
            tokens.append(("class:indicator", "  ... (更多选项在下方) ...\n"))

        return FormattedText(tokens)

    style = PromptStyle.from_dict(
        {
            "question": "bold",
            "selected": "bg:#696969 #ffffff",
            "indicator": "fg:gray",
        }
    )

    layout = Layout(
        container=Window(
            content=FormattedTextControl(
                text=get_prompt_tokens,
                focusable=True,
                key_bindings=bindings,
            )
        )
    )

    app: Application = Application(
        layout=layout,
        key_bindings=bindings,
        style=style,
        mouse_support=True,
        full_screen=True,
    )

    try:
        result = app.run()
        return result if result is not None else ""
    except (KeyboardInterrupt, EOFError):
        return ""


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

    history = get_message_history()
    if not history:
        PrettyOutput.print("没有可复制的消息", OutputType.INFO)
        return

    print("\n" + "=" * 20 + " 消息历史记录 " + "=" * 20)
    for i, msg in enumerate(history):
        cleaned_msg = msg.replace("\n", r"\n")
        display_msg = (
            (cleaned_msg[:70] + "...") if len(cleaned_msg) > 70 else cleaned_msg
        )
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

    # Show a one-time hint on the first Enter press in this invocation (disabled; using inlay toolbar instead)
    first_enter_hint_shown = True

    @bindings.add("enter")
    def _(event):
        nonlocal first_enter_hint_shown
        if not first_enter_hint_shown and not _multiline_hint_already_shown():
            first_enter_hint_shown = True

            def _show_notice():
                print(
                    f"{Fore.YELLOW}提示：当前支持多行输入。输入完成请使用 Ctrl+J 确认；Enter 仅用于换行。{ColoramaStyle.RESET_ALL}"
                )
                try:
                    input("按回车继续...")
                except Exception:
                    pass
                # Persist the hint so it won't be shown again in future runs
                try:
                    _mark_multiline_hint_shown()
                except Exception:
                    pass

            run_in_terminal(_show_notice)
            return

        if event.current_buffer.complete_state:
            completion = event.current_buffer.complete_state.current_completion
            if completion:
                event.current_buffer.apply_completion(completion)
            else:
                event.current_buffer.insert_text("\n")
        else:
            event.current_buffer.insert_text("\n")

    @bindings.add("c-j")
    def _(event):
        event.current_buffer.validate_and_handle()

    @bindings.add("c-o")
    def _(event):
        """Handle Ctrl+O by exiting the prompt and returning the sentinel value."""
        event.app.exit(result=CTRL_O_SENTINEL)

    style = PromptStyle.from_dict(
        {
            "prompt": "ansibrightmagenta bold",
            "bottom-toolbar": "bg:#4b145b #ffd6ff bold",
            "bt.tip": "bold fg:#ff5f87",
            "bt.sep": "fg:#ffb3de",
            "bt.key": "bg:#d7005f #ffffff bold",
            "bt.label": "fg:#ffd6ff",
        }
    )

    def _bottom_toolbar():
        return FormattedText(
            [
                ("class:bt.tip", f" {tip} "),
                ("class:bt.sep", " • "),
                ("class:bt.label", "快捷键: "),
                ("class:bt.key", "@"),
                ("class:bt.label", " 文件补全 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Tab"),
                ("class:bt.label", " 选择 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+J"),
                ("class:bt.label", " 确认 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+O"),
                ("class:bt.label", " 历史复制 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+C/D"),
                ("class:bt.label", " 取消 "),
            ]
        )
    
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

    # Tip is shown in bottom toolbar; avoid extra print
    prompt = FormattedText([("class:prompt", "👤 ❯ ")])

    try:
        return session.prompt(
            prompt,
            style=style,
            pre_run=lambda: None,
            bottom_toolbar=_bottom_toolbar,
        ).strip()
    except (KeyboardInterrupt, EOFError):
        return ""


def get_multiline_input(tip: str, print_on_empty: bool = True) -> str:
    """
    获取带有增强补全和确认功能的多行输入。
    此函数处理控制流，允许在不破坏终端状态的情况下处理历史记录复制。

    参数:
        tip: 提示文本，将显示在底部工具栏中
        print_on_empty: 当输入为空字符串时，是否打印“输入已取消”提示。默认打印。
    """
    while True:
        user_input = _get_multiline_input_internal(tip)

        if user_input == CTRL_O_SENTINEL:
            _show_history_and_copy()
            tip = "请继续输入（或按Ctrl+J确认）:"
            continue
        else:
            if not user_input and print_on_empty:
                PrettyOutput.print("\n输入已取消", OutputType.INFO)
            return user_input
