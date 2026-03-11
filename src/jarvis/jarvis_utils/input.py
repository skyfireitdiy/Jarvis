"""
输入处理模块
该模块提供了处理Jarvis系统中用户输入的实用工具。
包含：
- 支持历史记录的单行输入
- 增强补全功能的多行输入
- 带有模糊匹配的文件路径补全
- 用于输入控制的自定义键绑定
"""

import base64
import os
import sys
import threading
from abc import ABC
from abc import abstractmethod

from jarvis.jarvis_utils.output import PrettyOutput

# -*- coding: utf-8 -*-
from typing import Dict
from typing import Iterable
from typing import List
from typing import Any
from typing import Optional
from typing import Tuple

import wcwidth
from colorama import Fore
from colorama import Style as ColoramaStyle
from fuzzywuzzy import process
from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.completion import Completer
from prompt_toolkit.completion import Completion
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.filters import has_focus
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style as PromptStyle

from jarvis.jarvis_utils.clipboard import copy_to_clipboard
from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.config import get_replace_map
from jarvis.jarvis_utils.config import get_submit_keys
from jarvis.jarvis_utils.globals import get_message_history
from jarvis.jarvis_utils.tag import ot
from jarvis.jarvis_utils.utils import decode_output

# 在文件顶部导入需要在函数内部使用的模块
# (使用别名避免与内置模块冲突)
import os as _os
import subprocess as _subprocess
import shutil as _shutil

# Sentinel value to indicate that Ctrl+O was pressed
CTRL_O_SENTINEL = "__CTRL_O_PRESSED__"
# Sentinel value to indicate that Ctrl+X was pressed (exit program)
CTRL_X_SENTINEL = "__CTRL_X_PRESSED__"
# Sentinel prefix to indicate that Ctrl+F (fzf) inserted content should prefill next prompt
FZF_INSERT_SENTINEL_PREFIX = "__FZF_INSERT__::"
# Sentinel to request running fzf outside the prompt and then prefill next prompt
FZF_REQUEST_SENTINEL_PREFIX = "__FZF_REQUEST__::"
# Sentinel to request running fzf outside the prompt for all-files mode (exclude .git)
FZF_REQUEST_ALL_SENTINEL_PREFIX = "__FZF_REQUEST_ALL__::"
# Sentinel value to indicate that Ctrl+C was pressed
CTRL_C_SENTINEL = "__CTRL_C_PRESSED__"

# Persistent hint marker for multiline input (shown only once across runs)
_MULTILINE_HINT_MARK_FILE = os.path.join(get_data_dir(), "multiline_enter_hint_shown")

# 内置命令标记列表（用于自动补全和 fzf）
BUILTIN_COMMANDS = [
    ("Summary", "总结"),
    ("Pin", "固定/置顶内容"),
    ("Clear", "清除历史"),
    ("Commit", "提交代码"),
    ("ToolUsage", "工具使用说明"),
    ("ReloadConfig", "重新加载配置"),
    ("SaveSession", "保存当前会话"),
    ("RestoreSession", "恢复会话"),
    ("ListSessions", "列出所有会话"),
    ("ListRule", "列出所有规则"),
    ("Quiet", "无人值守模式"),
    ("FixToolCall", "修复工具调用"),
    ("SwitchModel", "切换模型组"),
]


class InputProviderTimeoutError(TimeoutError):
    """输入提供者等待用户输入超时。"""


class InputProviderDisconnectedError(RuntimeError):
    """输入提供者对应的远端会话已断开。"""


class InputProvider(ABC):
    """用户输入提供者抽象。"""

    @abstractmethod
    def get_multiline_input(
        self,
        tip: str,
        preset: Optional[str] = None,
        preset_cursor: Optional[int] = None,
    ) -> str:
        raise NotImplementedError


class CLIInputProvider(InputProvider):
    """默认本地 CLI 输入提供者，复用既有 prompt_toolkit 实现。"""

    def get_multiline_input(
        self,
        tip: str,
        preset: Optional[str] = None,
        preset_cursor: Optional[int] = None,
    ) -> str:
        return _get_multiline_input_internal(
            tip, preset=preset, preset_cursor=preset_cursor
        )


_default_input_provider: InputProvider = CLIInputProvider()
_input_provider_lock = threading.RLock()
_input_providers: Dict[str, InputProvider] = {}


def register_input_provider(provider_id: str, provider: InputProvider) -> None:
    """注册命名输入提供者，供远端会话或特定 Agent 绑定。"""
    with _input_provider_lock:
        _input_providers[provider_id] = provider


def unregister_input_provider(provider_id: str) -> None:
    """移除命名输入提供者；若不存在则忽略。"""
    with _input_provider_lock:
        _input_providers.pop(provider_id, None)


def set_default_input_provider(provider: InputProvider) -> None:
    """设置全局默认输入提供者。"""
    global _default_input_provider
    with _input_provider_lock:
        _default_input_provider = provider


def get_default_input_provider() -> InputProvider:
    """获取当前默认输入提供者。"""
    with _input_provider_lock:
        return _default_input_provider


def _resolve_input_provider_key(agent: Optional[Any]) -> Optional[str]:
    if agent is None:
        return None
    for attr_name in ("input_provider_key", "session_id"):
        try:
            value = getattr(agent, attr_name, None)
        except Exception:
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_current_input_provider() -> InputProvider:
    """获取当前 Agent 对应的输入提供者；未命中时回退到默认 CLI。"""
    agent = _get_current_agent_for_input()
    provider_key = _resolve_input_provider_key(agent)
    with _input_provider_lock:
        if provider_key and provider_key in _input_providers:
            return _input_providers[provider_key]
        return _default_input_provider


def _display_width(s: str) -> int:
    """计算字符串在终端中的可打印宽度(处理宽字符)。"""
    try:
        w = 0
        for ch in s:
            cw = wcwidth.wcwidth(ch)
            if cw is None or cw < 0:
                # Fallback for unknown width chars (e.g. emoji on some terminals)
                cw = 1
            w += cw
        return w
    except Exception:
        return len(s)


def _calc_prompt_rows(prev_text: str) -> int:
    """
    估算上一个提示占用了多少终端行数。
    考虑提示前缀和跨终端列的软换行。
    """
    try:
        cols = os.get_terminal_size().columns
    except Exception:
        cols = 80
    prefix = "👤 > "
    prefix_w = _display_width(prefix)

    lines = prev_text.splitlines()
    if not lines:
        lines = [""]
    # If the text ends with a newline, there is a visible empty line at the end.
    if prev_text.endswith("\n"):
        lines.append("")
    total_rows = 0
    for i, line in enumerate(lines):
        lw = _display_width(line)
        if i == 0:
            width = prefix_w + lw
        else:
            width = lw
        rows = max(1, (width + cols - 1) // cols)
        total_rows += rows
    return max(1, total_rows)


def _get_git_files() -> List[str]:
    """获取Git仓库中的文件列表。"""
    files = []
    try:
        r = _subprocess.run(
            ["git", "ls-files"],
            stdout=_subprocess.PIPE,
            stderr=_subprocess.PIPE,
            text=False,
        )
        if r.returncode == 0:
            files = [
                line for line in decode_output(r.stdout).splitlines() if line.strip()
            ]
    except Exception:
        files = []
    return files


def _get_all_files(exclude_git: bool = False) -> List[str]:
    """获取所有文件列表。

    Args:
        exclude_git: 是否排除.git目录
    """
    files = []
    try:
        import os as _os

        for root, dirs, fnames in _os.walk(".", followlinks=False):
            if exclude_git:
                # Exclude .git directories
                dirs[:] = [d for d in dirs if d != ".git"]
            for name in fnames:
                files.append(_os.path.relpath(_os.path.join(root, name), "."))
            if len(files) > 10000:
                break
    except Exception:
        files = []
    return files


def _get_files_for_fzf(use_git: bool = True) -> List[str]:
    """为FZF获取文件列表。

    Args:
        use_git: 是否优先使用git文件列表（失败则fallback到os.walk）
    """
    if use_git:
        files = _get_git_files()
        if files:
            return files
    return _get_all_files(exclude_git=True)


def _parse_fzf_payload(
    user_input: str, prefix: str
) -> Tuple[Optional[int], Optional[str]]:
    """解析FZF请求payload。

    Args:
        user_input: 用户输入，包含FZF前缀和payload
        prefix: FZF前缀（如FZF_REQUEST_SENTINEL_PREFIX）

    Returns:
        (cursor, text) 元组，解析失败时返回 (None, None)
    """
    try:
        payload = user_input[len(prefix) :]
        sep_index = payload.find(":")
        cursor = int(payload[:sep_index])
        text = base64.b64decode(payload[sep_index + 1 :].encode("ascii")).decode(
            "utf-8"
        )
        return cursor, text
    except Exception:
        return None, None


def _run_fzf_for_selection(files: List[str], prompt_text: str) -> Optional[str]:
    """运行FZF获取用户选择。

    Args:
        files: 文件列表
        prompt_text: FZF提示文本

    Returns:
        选中的文件路径，取消或错误时返回None
    """
    if _shutil.which("fzf") is None:
        PrettyOutput.auto_print("⚠️ 未检测到 fzf，无法打开文件选择器。")
        return None

    if not files:
        PrettyOutput.auto_print("ℹ️ 未找到可选择的文件。")
        return None

    # _get_fzf_completion_items会自动添加完整的BUILTIN_COMMANDS
    # 因此这里传入空列表，避免重复
    specials: List[str] = []
    items = _get_fzf_completion_items(specials, files)
    proc = _subprocess.run(
        [
            "fzf",
            "--prompt",
            prompt_text,
            "--height",
            "40%",
            "--border",
        ],
        input="\n".join(items),
        stdout=_subprocess.PIPE,
        stderr=_subprocess.PIPE,
        text=True,
    )
    sel = proc.stdout.strip()
    return sel if sel else None


def _insert_file_path(
    text: str, cursor: int, path: str, symbol: str
) -> Tuple[str, int]:
    """插入文件路径到文本中。

    Args:
        text: 原始文本
        cursor: 光标位置
        path: 要插入的文件路径
        symbol: 触发符号（'@' 或 '#'）

    Returns:
        (new_text, new_cursor) 元组
    """
    text_before = text[:cursor]
    last_symbol = text_before.rfind(symbol)
    if last_symbol != -1 and " " not in text_before[last_symbol + 1 :]:
        # Replace @... or #... segment
        inserted = f"'{path}'"
        new_text = text[:last_symbol] + inserted + text[cursor:]
        new_cursor = last_symbol + len(inserted)
    else:
        # Plain insert
        inserted = f"'{path}'"
        new_text = text[:cursor] + inserted + text[cursor:]
        new_cursor = cursor + len(inserted)
    return new_text, new_cursor


def _clear_previous_prompt(text: str) -> None:
    """清除上一条输入行。

    Args:
        text: 上一次的输入文本
    """
    try:
        rows_total = _calc_prompt_rows(text)
        for _ in range(rows_total):
            sys.stdout.write("\x1b[1A")  # 光标上移一行
            sys.stdout.write("\x1b[2K\r")  # 清除整行
        sys.stdout.flush()
    except Exception:
        pass


def _multiline_hint_already_shown() -> bool:
    """检查是否已显示过多行输入提示(持久化存储)。"""
    try:
        return os.path.exists(_MULTILINE_HINT_MARK_FILE)
    except Exception:
        return False


def _mark_multiline_hint_shown() -> None:
    """持久化存储多行输入提示已显示的状态。"""
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
    history_dir = get_data_dir()
    session: PromptSession[Any] = PromptSession(
        history=FileHistory(os.path.join(history_dir, "single_line_input_history"))
    )
    style = PromptStyle.from_dict(
        {"prompt": "ansicyan", "bottom-toolbar": "fg:#888888"}
    )
    prompt = FormattedText([("class:prompt", f"👤 > {tip}")])
    return str(session.prompt(prompt, default=default, style=style))


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
    def _(event: KeyPressEvent) -> None:
        nonlocal selected_index, start_index
        selected_index = (selected_index - 1 + len(choices)) % len(choices)
        if selected_index < start_index:
            start_index = selected_index
        elif selected_index == len(choices) - 1:  # 支持从第一项上翻到最后一项时滚动
            start_index = max(0, len(choices) - max_visible_choices)
        event.app.invalidate()

    @bindings.add("down")
    def _(event: KeyPressEvent) -> None:
        nonlocal selected_index, start_index
        selected_index = (selected_index + 1) % len(choices)
        if selected_index >= start_index + max_visible_choices:
            start_index = selected_index - max_visible_choices + 1
        elif selected_index == 0:  # 支持从最后一项下翻到第一项时滚动
            start_index = 0
        event.app.invalidate()

    @bindings.add("enter")
    def _(event: KeyPressEvent) -> None:
        event.app.exit(result=choices[selected_index])

    def get_prompt_tokens() -> FormattedText:
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

    app: Application[Any] = Application(
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

    def __init__(self) -> None:
        self.path_completer = PathCompleter()
        self.max_suggestions = 30
        self.min_score = 10
        self.replace_map = get_replace_map()
        # Caches for file lists to avoid repeated expensive scans
        self._git_files_cache: Optional[List[str]] = None
        self._all_files_cache: Optional[List[str]] = None
        self._max_walk_files = 10000
        # Cache for rules to avoid repeated loading
        self._rules_cache: Optional[List[Tuple[str, str]]] = None

    def _get_all_rule_completions(self) -> List[str]:
        """获取所有规则补全项的统一接口

        返回:
            List[str]: 格式为"<rule:{rule_name}>"的规则列表
        """
        all_rules = []
        try:
            from jarvis.jarvis_agent.rules_manager import RulesManager

            rules_manager = RulesManager(os.getcwd())
            available_rules = rules_manager.get_all_available_rule_names()

            # 添加内置规则
            if available_rules.get("builtin"):
                for rule_name in available_rules["builtin"]:
                    all_rules.append(f"<rule:{rule_name}>")

            # 添加文件规则
            if available_rules.get("files"):
                for rule_name in available_rules["files"]:
                    all_rules.append(f"<rule:{rule_name}>")

            # 添加YAML规则
            if available_rules.get("yaml"):
                for rule_name in available_rules["yaml"]:
                    all_rules.append(f"<rule:{rule_name}>")
        except ImportError:
            # 如果无法导入，只使用内置规则
            try:
                from jarvis.jarvis_agent.builtin_rules import list_builtin_rules

                for rule_name in list_builtin_rules():
                    all_rules.append(f"<rule:{rule_name}>")
            except ImportError:
                pass
        except Exception:
            # 任何错误都静默处理
            pass

        return all_rules

    def _get_all_rules(self) -> List[Tuple[str, str]]:
        """获取所有可用的规则，包括内置规则、文件规则和YAML规则

        返回:
            List[Tuple[str, str]]: (规则名称, 规则描述) 列表
        """
        if self._rules_cache is not None:
            return self._rules_cache

        all_rules = []

        try:
            # 导入必要的模块
            from jarvis.jarvis_agent.rules_manager import RulesManager

            # 创建RulesManager实例
            rules_manager = RulesManager(os.getcwd())

            # 获取所有可用规则
            available_rules = rules_manager.get_all_available_rule_names()

            # 添加内置规则
            if available_rules.get("builtin"):
                for rule_name in available_rules["builtin"]:
                    all_rules.append((rule_name, f"📚 内置规则: {rule_name}"))

            # 添加文件规则
            if available_rules.get("files"):
                for rule_name in available_rules["files"]:
                    all_rules.append((rule_name, f"📄 文件规则: {rule_name}"))

            # 添加YAML规则
            if available_rules.get("yaml"):
                for rule_name in available_rules["yaml"]:
                    all_rules.append((rule_name, f"📝 YAML规则: {rule_name}"))

        except ImportError:
            # 如果无法导入，只使用内置规则
            try:
                from jarvis.jarvis_agent.builtin_rules import list_builtin_rules

                for rule_name in list_builtin_rules():
                    all_rules.append((rule_name, f"📚 内置规则: {rule_name}"))
            except ImportError:
                pass
        except Exception:
            # 任何错误都静默处理
            pass

        self._rules_cache = all_rules
        return all_rules

    def get_completions(
        self, document: Document, _: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        cursor_pos = document.cursor_position

        # Support both '@' (git files) and '#' (all files excluding .git)
        sym_positions = [(i, ch) for i, ch in enumerate(text) if ch in ("@", "#")]
        if not sym_positions:
            return
        current_pos = None
        current_sym = None
        for i, ch in sym_positions:
            if i < cursor_pos:
                current_pos = i
                current_sym = ch
        if current_pos is None:
            return

        text_after = text[current_pos + 1 : cursor_pos]
        if " " in text_after:
            return

        token = text_after.strip()
        replace_length = len(text_after) + 1

        all_completions = []
        all_completions.extend(
            [(ot(tag), self._get_description(tag)) for tag in self.replace_map.keys()]
        )
        all_completions.extend([(ot(cmd), desc) for cmd, desc in BUILTIN_COMMANDS])
        # 添加所有规则（包括内置规则、文件规则、YAML规则）到补全列表
        rules = self._get_all_rules()
        for rule_name, rule_desc in rules:
            all_completions.append((f"<rule:{rule_name}>", rule_desc))

        # File path candidates
        try:
            if current_sym == "@":
                if self._git_files_cache is None:
                    result = _subprocess.run(
                        ["git", "ls-files"],
                        stdout=_subprocess.PIPE,
                        stderr=_subprocess.PIPE,
                        text=False,
                    )
                    if result.returncode == 0:
                        self._git_files_cache = [
                            p
                            for p in decode_output(result.stdout).splitlines()
                            if p.strip()
                        ]
                    else:
                        self._git_files_cache = []
                paths: List[str] = self._git_files_cache or []
            else:
                if self._all_files_cache is None:
                    files: List[str] = []
                    for root, dirs, fnames in _os.walk(".", followlinks=False):
                        # Explicitly include hidden directories (starting with .), but exclude .git, __pycache__, .pytest_cache, etc.
                        dirs[:] = [
                            d
                            for d in dirs
                            if d
                            not in {
                                ".git",
                                "__pycache__",
                                ".pytest_cache",
                                ".mypy_cache",
                                ".ruff_cache",
                                "node_modules",
                                "target",
                            }
                        ]
                        for name in fnames:
                            files.append(
                                _os.path.relpath(_os.path.join(root, name), ".")
                            )
                            if len(files) > self._max_walk_files:
                                break
                        if len(files) > self._max_walk_files:
                            break
                    self._all_files_cache = files
                paths = self._all_files_cache or []
            all_completions.extend([(path, "File") for path in paths])
        except Exception:
            pass

        if token:
            # Check if token contains only punctuation/special characters
            # This prevents fuzzywuzzy processor from reducing it to empty string
            token_stripped = token.strip()
            if token_stripped and not any(c.isalnum() for c in token_stripped):
                # Token contains only punctuation/special chars, skip fuzzy matching
                # to avoid warning from fuzzywuzzy processor
                for t, desc in all_completions[: self.max_suggestions]:
                    yield Completion(
                        text=f"'{t}'",
                        start_position=-replace_length,
                        display=t,
                        display_meta=desc,
                    )
            else:
                scored_items = process.extract(
                    token,
                    [item[0] for item in all_completions],
                    limit=self.max_suggestions,
                )
                scored_items = [
                    (item[0], item[1])
                    for item in scored_items
                    if item[1] > self.min_score
                ]
                completion_map = {item[0]: item[1] for item in all_completions}
                for t, score in scored_items:
                    display_text = f"{t} ({score}%)" if score < 100 else t
                    yield Completion(
                        text=f"'{t}'",
                        start_position=-replace_length,
                        display=display_text,
                        display_meta=completion_map.get(t, ""),
                    )
        else:
            for t, desc in all_completions[: self.max_suggestions]:
                yield Completion(
                    text=f"'{t}'",
                    start_position=-replace_length,
                    display=t,
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


def get_all_rules_formatted() -> List[str]:
    """
    获取所有可用规则的格式化列表，包括内置、文件和YAML规则。

    返回:
        List[str]: 格式化的规则列表，每个规则以"<rule:规则名>"格式返回

    异常处理:
        - 处理RulesManager导入失败的情况
        - 处理内置规则导入失败的情况
        - 在任何错误情况下返回空列表而不是抛出异常
    """
    all_rules = []
    try:
        try:
            from jarvis.jarvis_agent.rules_manager import RulesManager

            rules_manager = RulesManager(os.getcwd())
            available_rules = rules_manager.get_all_available_rule_names()

            # 添加内置规则
            if available_rules.get("builtin"):
                for rule_name in available_rules["builtin"]:
                    all_rules.append(f"<rule:{rule_name}>")

            # 添加文件规则
            if available_rules.get("files"):
                for rule_name in available_rules["files"]:
                    all_rules.append(f"<rule:{rule_name}>")

            # 添加YAML规则
            if available_rules.get("yaml"):
                for rule_name in available_rules["yaml"]:
                    all_rules.append(f"<rule:{rule_name}>")
        except ImportError:
            # 如果无法导入RulesManager，只使用内置规则
            try:
                from jarvis.jarvis_agent.builtin_rules import list_builtin_rules

                for rule_name in list_builtin_rules():
                    all_rules.append(f"<rule:{rule_name}>")
            except ImportError:
                pass
    except Exception:
        # 任何异常都返回空列表
        all_rules = []

    return all_rules


def _get_fzf_completion_items(specials: List[str], files: List[str]) -> List[str]:
    """
    获取fzf补全所需的完整项目列表。

    该函数统一处理fzf补全所需的各类项目，包括特殊符号、内置标签、规则、文件等，
    消除了两处fzf补全代码中的重复逻辑。

    参数:
        specials: 特殊符号列表
        files: 文件列表

    返回:
        List[str]: 合并后的完整项目列表，按特定顺序排列
    """
    items = []

    # 添加特殊符号（过滤空字符串）
    items.extend([s for s in specials if isinstance(s, str) and s.strip()])

    # 添加内置标签
    try:
        from jarvis.jarvis_utils.config import get_replace_map
        from jarvis.jarvis_utils.tag import ot

        replace_map = get_replace_map()
        builtin_tags = [
            ot(tag)
            for tag in replace_map.keys()
            if isinstance(tag, str) and tag.strip()
        ]
        items.extend(builtin_tags)

        # 添加内置命令标记
        builtin_commands = [ot(cmd) for cmd, _ in BUILTIN_COMMANDS]
        items.extend(builtin_commands)
    except Exception:
        # 标签获取失败时跳过
        pass

    # 添加规则
    try:
        builtin_rules = get_all_rules_formatted()
        items.extend(builtin_rules)
    except Exception:
        # 规则获取失败时跳过
        pass

    # 添加文件
    items.extend(files)

    return items


# -+
# 公共判定辅助函数（按当前Agent优先）
# ---------------------
def _get_current_agent_for_input() -> Optional[Any]:
    try:
        import jarvis.jarvis_utils.globals as g

        current_name = g.get_current_agent_name()
        if current_name:
            return g.get_agent(current_name)
    except Exception:
        pass
    return None


def _is_non_interactive_for_current_agent() -> bool:
    try:
        from jarvis.jarvis_utils.config import is_non_interactive

        ag = _get_current_agent_for_input()
        try:
            return (
                bool(getattr(ag, "non_interactive", False))
                if ag
                else bool(is_non_interactive())
            )
        except Exception:
            return bool(is_non_interactive())
    except Exception:
        return False


def _is_auto_complete_for_current_agent() -> bool:
    try:
        ag = _get_current_agent_for_input()
        if ag is not None and hasattr(ag, "auto_complete"):
            try:
                return bool(getattr(ag, "auto_complete", False))
            except Exception:
                pass
        return False
    except Exception:
        return False


def _get_agent_hint() -> str:
    """获取当前Agent的提示信息（可用智能体列表）。"""
    try:
        ag = _get_current_agent_for_input()
        ohs = getattr(ag, "output_handler", [])
        available_agents: List[str] = []
        for oh in ohs or []:
            cfgs = getattr(oh, "agents_config", None)
            if isinstance(cfgs, list):
                for c in cfgs:
                    try:
                        name = c.get("name")
                    except Exception:
                        name = None
                    if isinstance(name, str) and name.strip():
                        available_agents.append(name.strip())
        if available_agents:
            # 去重但保留顺序
            seen = set()
            ordered = []
            for n in available_agents:
                if n not in seen:
                    seen.add(n)
                    ordered.append(n)
            return (
                "\n当前可用智能体: "
                + ", ".join(ordered)
                + f"\n如需将任务交给其他智能体，请使用 {ot('SEND_MESSAGE')} 块。"
            )
    except Exception:
        pass
    return ""


def _get_non_interactive_response(auto_complete: bool) -> str:
    """获取非交互模式下的响应文本。"""
    hint = _get_agent_hint()
    if auto_complete:
        base_msg = (
            "当前是非交互模式，所有的事情你都自我决策，如果无法决策，就完成任务。输出"
            + ot("!!!COMPLETE!!!")
        )
        return base_msg + hint
    else:
        return "当前是非交互模式，所有的事情你都自我决策" + hint


def user_confirm(tip: str, default: bool = True) -> bool:
    """提示用户确认是/否问题（按当前Agent优先判断非交互）"""
    try:
        if _is_non_interactive_for_current_agent():
            return default

        # 获取当前agent名称并添加到提示前缀
        agent_name = ""
        try:
            ag = _get_current_agent_for_input()
            if ag is not None:
                name = getattr(ag, "name", None)
                if name:
                    agent_name = f"[{name}] "
        except Exception:
            pass

        suffix = "[Y/n]" if default else "[y/N]"
        ret = get_single_line_input(f"{agent_name}{tip} {suffix}: ")
        return default if ret == "" else ret.lower() == "y"
    except KeyboardInterrupt:
        return False


def _show_history_and_copy() -> None:
    """
    显示消息历史记录并处理复制到剪贴板。
    此函数使用标准I/O，可在提示会话之外安全调用。
    """

    history = get_message_history()
    if not history:
        PrettyOutput.auto_print("ℹ️ 没有可复制的消息")
        return

    # 为避免 PrettyOutput 在循环中为每行加框，先拼接后统一打印
    lines = []
    lines.append("\n" + "=" * 20 + " 📜 消息历史记录 " + "=" * 20)
    for i, msg in enumerate(history):
        cleaned_msg = msg.replace("\n", r"\n")
        display_msg = (
            (cleaned_msg[:70] + "...") if len(cleaned_msg) > 70 else cleaned_msg
        )
        lines.append(f"  {i + 1}: {display_msg.strip()}")
        lines.append("=" * 58 + "\n")
    PrettyOutput.auto_print("\n".join(lines))

    while True:
        try:
            prompt_text = f"{Fore.CYAN}请输入要复制的条目序号 (或输入c取消, 直接回车选择最后一条): {ColoramaStyle.RESET_ALL}"
            choice_str = input(prompt_text)

            if not choice_str:  # User pressed Enter
                if not history:
                    PrettyOutput.auto_print("ℹ️ 没有历史记录可供选择。")
                    break
                choice = len(history) - 1
            elif choice_str.lower() == "c":
                PrettyOutput.auto_print("ℹ️ 已取消")
                break
            else:
                choice = int(choice_str) - 1

            if 0 <= choice < len(history):
                selected_msg = history[choice]
                copy_to_clipboard(selected_msg)
                PrettyOutput.auto_print(f"✅ 已复制消息: {selected_msg[:70]}...")
                break
            else:
                PrettyOutput.auto_print("⚠️ 无效的序号，请重试。")
        except ValueError:
            PrettyOutput.auto_print("⚠️ 无效的输入，请输入数字。")
        except (KeyboardInterrupt, EOFError):
            PrettyOutput.auto_print("ℹ️ 操作取消")
            break


def _get_multiline_input_internal(
    tip: str, preset: Optional[str] = None, preset_cursor: Optional[int] = None
) -> str:
    """
    Internal function to get multiline input using prompt_toolkit.
    Returns a sentinel value if Ctrl+O is pressed.
    """
    bindings = KeyBindings()

    # Show a one-time hint on the first Enter press in this invocation (disabled; using inlay toolbar instead)
    first_enter_hint_shown = True

    @bindings.add("enter")
    def _(event: KeyPressEvent) -> None:
        nonlocal first_enter_hint_shown
        if not first_enter_hint_shown and not _multiline_hint_already_shown():
            first_enter_hint_shown = True

            # 生成快捷键显示文本
            submit_keys = get_submit_keys()
            submit_keys_display = " 或 ".join(
                [k.replace("c-", "Ctrl+").upper() for k in submit_keys]
            )

            def _show_notice() -> None:
                PrettyOutput.auto_print(
                    f"ℹ️ 提示：当前支持多行输入。输入完成请使用 {submit_keys_display} 确认；Enter 仅用于换行。"
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

    # 从配置获取提交快捷键列表
    submit_keys = get_submit_keys()
    for key in submit_keys:

        @bindings.add(key, filter=has_focus(DEFAULT_BUFFER))
        def _(event: KeyPressEvent) -> None:
            event.current_buffer.validate_and_handle()

    @bindings.add("c-o", filter=has_focus(DEFAULT_BUFFER))
    def _(event: KeyPressEvent) -> None:
        """Handle Ctrl+O by exiting the prompt and returning the sentinel value."""
        event.app.exit(result=CTRL_O_SENTINEL)

    @bindings.add("c-x", filter=has_focus(DEFAULT_BUFFER))
    def _(event: KeyPressEvent) -> None:
        """Handle Ctrl+X by exiting the prompt and requesting program exit."""
        event.app.exit(result=CTRL_X_SENTINEL)

    @bindings.add("c-t", eager=True)
    def _(event: KeyPressEvent) -> None:
        """Return a shell command like '!bash' for upper input_handler to execute.

        This binding works globally (without focus filter) so it can be triggered
        even when LLM is outputting or after interrupting output with Ctrl+C.
        """

        def _gen_shell_cmd() -> str:
            try:
                if _os.name == "nt":
                    # Prefer PowerShell if available, otherwise fallback to cmd
                    for name in ("pwsh", "powershell", "cmd"):
                        if name == "cmd" or _shutil.which(name):
                            if name == "cmd":
                                # Keep session open with /K and set env for the spawned shell
                                return "!cmd /K set terminal=1"
                            else:
                                # PowerShell or pwsh: set env then remain in session
                                return f"!{name} -NoExit -Command \"$env:terminal='1'\""
                else:
                    shell_path = os.environ.get("SHELL", "")
                    if shell_path:
                        base = os.path.basename(shell_path)
                        if base:
                            return f"!env terminal=1 {base}"
                    for name in ("fish", "zsh", "bash", "sh"):
                        if _shutil.which(name):
                            return f"!env terminal=1 {name}"
                    return "!env terminal=1 bash"
            except Exception:
                return "!env terminal=1 bash"
            # Fallback for all cases
            return "!env terminal=1 bash"

        # Append a special marker to indicate no-confirm execution in shell_input_handler
        event.app.exit(result=_gen_shell_cmd() + " # JARVIS-NOCONFIRM")

    @bindings.add("@", filter=has_focus(DEFAULT_BUFFER), eager=True)
    def _(event: KeyPressEvent) -> None:
        """
        使用 @ 触发 fzf（当 fzf 存在）；否则仅插入 @ 以启用内置补全
        逻辑：
        - 若检测到系统存在 fzf，则先插入 '@'，随后请求外层运行 fzf 并在返回后进行替换/插入
        - 若不存在 fzf 或发生异常，则直接插入 '@' 并触发补全
        """
        try:
            buf = event.current_buffer
            if _shutil.which("fzf") is None:
                buf.insert_text("@")
                # 手动触发补全，以便显示 rule 和其他补全选项
                buf.start_completion(select_first=False)
                return
            # 先插入 '@'，以便外层根据最后一个 '@' 进行片段替换
            buf.insert_text("@")
            doc = buf.document
            text = doc.text
            cursor = doc.cursor_position
            payload = (
                f"{cursor}:{base64.b64encode(text.encode('utf-8')).decode('ascii')}"
            )
            event.app.exit(result=FZF_REQUEST_SENTINEL_PREFIX + payload)
            return
        except Exception:
            try:
                buf = event.current_buffer
                buf.insert_text("@")
                # 即使发生异常，也尝试触发补全
                buf.start_completion(select_first=False)
            except Exception:
                pass

    @bindings.add("#", filter=has_focus(DEFAULT_BUFFER), eager=True)
    def _(event: KeyPressEvent) -> None:
        """
        使用 # 触发 fzf（当 fzf 存在），以“全量文件模式”进行选择（排除 .git）；否则仅插入 # 启用内置补全
        """
        try:
            buf = event.current_buffer
            if _shutil.which("fzf") is None:
                buf.insert_text("#")
                # 手动触发补全，以便显示 rule 和其他补全选项
                buf.start_completion(select_first=False)
                return
            # 先插入 '#'
            buf.insert_text("#")
            doc = buf.document
            text = doc.text
            cursor = doc.cursor_position
            payload = (
                f"{cursor}:{base64.b64encode(text.encode('utf-8')).decode('ascii')}"
            )
            event.app.exit(result=FZF_REQUEST_ALL_SENTINEL_PREFIX + payload)
            return
        except Exception:
            try:
                buf = event.current_buffer
                buf.insert_text("#")
                # 即使发生异常，也尝试触发补全
                buf.start_completion(select_first=False)
            except Exception:
                pass

    style = PromptStyle.from_dict(
        {
            "prompt": "ansibrightmagenta bold",
            "bottom-toolbar": "bg:#4b145b #ffd6ff bold",
            "bt.tip": "bold fg:#ff5f87",
            "bt.sep": "fg:#ffb3de",
            "bt.key": "bg:#d7005f #ffffff bold",
            "bt.label": "fg:#ffd6ff",
            "placeholder": "italic fg:#888888",
        }
    )

    # 获取提交快捷键显示文本
    submit_keys = get_submit_keys()
    # 将快捷键转换为显示格式（如 "c-j" -> "Ctrl+J"）
    submit_keys_display = "/".join(
        [k.replace("c-", "Ctrl+").upper() for k in submit_keys]
    )

    def _bottom_toolbar() -> Any:
        return FormattedText(
            [
                ("class:bt.label", "快捷键: "),
                ("class:bt.key", "@"),
                ("class:bt.label", " 文件补全 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", submit_keys_display),
                ("class:bt.label", " 提交 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+O"),
                ("class:bt.label", " 复制历史信息 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+T"),
                ("class:bt.label", " 终端(!SHELL) "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+X"),
                ("class:bt.label", " 退出程序 "),
                ("class:bt.sep", " • "),
                ("class:bt.key", "Ctrl+C/D"),
                ("class:bt.label", " 取消 "),
            ]
        )

    history_dir = get_data_dir()
    session: PromptSession[Any] = PromptSession(
        history=FileHistory(os.path.join(history_dir, "multiline_input_history")),
        completer=FileCompleter(),
        key_bindings=bindings,
        complete_while_typing=True,
        multiline=True,
        vi_mode=False,
        mouse_support=False,
    )

    # Tip is shown in placeholder; avoid extra print
    prompt = FormattedText([("class:prompt", "👤 > ")])

    def _pre_run() -> None:
        try:
            from prompt_toolkit.application.current import get_app as _ga

            app = _ga()
            buf = app.current_buffer
            if preset is not None and preset_cursor is not None:
                cp = max(0, min(len(buf.text), preset_cursor))
                buf.cursor_position = cp
        except Exception:
            pass

    try:
        result = session.prompt(
            prompt,
            style=style,
            pre_run=_pre_run,
            bottom_toolbar=_bottom_toolbar,
            placeholder=FormattedText([("class:placeholder", tip)]),
            default=(preset or ""),
        )
        return str(result).strip() if result else ""
    except (KeyboardInterrupt, EOFError):
        return CTRL_C_SENTINEL


def get_multiline_input(tip: str, print_on_empty: bool = True) -> str:
    """
    获取带有增强补全和确认功能的多行输入。
    此函数处理控制流，允许在不破坏终端状态的情况下处理历史记录复制。

    参数:
        tip: 提示文本，将显示在底部工具栏中
        print_on_empty: 当输入为空字符串时，是否打印“输入已取消”提示。默认打印。
    """
    # 获取提交快捷键配置，用于生成提示文本
    submit_keys = get_submit_keys()
    submit_keys_display = "/".join(
        [k.replace("c-", "Ctrl+").upper() for k in submit_keys]
    )

    preset: Optional[str] = None
    preset_cursor: Optional[int] = None
    while True:
        # 基于“当前Agent”精确判断非交互与自动完成，避免多Agent相互干扰
        if _is_non_interactive_for_current_agent():
            return _get_non_interactive_response(_is_auto_complete_for_current_agent())

        def _get_input_via_provider() -> str:
            provider = get_current_input_provider()
            return provider.get_multiline_input(
                tip, preset=preset, preset_cursor=preset_cursor
            )

        gateway = None
        GatewayInputRequest = None
        try:
            from jarvis.jarvis_gateway.events import (
                GatewayInputRequest as _GatewayInputRequest,
            )
            from jarvis.jarvis_gateway.manager import get_current_gateway

            gateway = get_current_gateway()
            GatewayInputRequest = _GatewayInputRequest
            print(f"🔍 [DEBUG] get_multiline_input: gateway={type(gateway).__name__ if gateway else None}")
        except Exception as e:
            gateway = None
            print(f"🔍 [DEBUG] get_multiline_input: Failed to get gateway: {e}")

        try:
            if gateway is not None and GatewayInputRequest is not None:
                print(f"🔍 [DEBUG] get_multiline_input: Using Gateway path, tip={tip}")
                request = GatewayInputRequest(
                    tip=tip,
                    mode='multi',
                    preset=preset,
                    preset_cursor=preset_cursor,
                )
                print("🔍 [DEBUG] get_multiline_input: Calling gateway.request_input")
                result = gateway.request_input(request)
                print(f"🔍 [DEBUG] get_multiline_input: gateway.request_input returned, text={repr(result.text[:50] if result.text else '') if result else 'None'}")
                user_input = result.text if result is not None else ""
            else:
                print(f"🔍 [DEBUG] get_multiline_input: Using provider path (gateway={gateway}, GatewayInputRequest={GatewayInputRequest})")
                user_input = _get_input_via_provider()
        except InputProviderTimeoutError:
            PrettyOutput.auto_print("⚠️ 输入等待超时，已取消本次输入")
            return ""
        except InputProviderDisconnectedError:
            PrettyOutput.auto_print("⚠️ 远端输入连接已断开，已取消本次输入")
            return ""
        except Exception:
            user_input = _get_input_via_provider()

        if user_input == CTRL_O_SENTINEL:
            _show_history_and_copy()
            tip = f"请继续输入（或按{submit_keys_display}确认）:"
            continue
        if user_input == CTRL_X_SENTINEL:
            PrettyOutput.auto_print("🛑 用户请求退出程序...")
            raise SystemExit(0)
        elif isinstance(user_input, str) and user_input.startswith(
            FZF_REQUEST_SENTINEL_PREFIX
        ):
            # Handle fzf request outside the prompt, then prefill new text.
            cursor, text = _parse_fzf_payload(user_input, FZF_REQUEST_SENTINEL_PREFIX)
            if cursor is None or text is None:
                # Malformed payload; just continue without change.
                preset = None
                tip = "FZF 预填失败，继续输入:"
                continue

            # Run fzf to get a file selection synchronously (outside prompt)
            files = _get_files_for_fzf(use_git=True)
            selected_path = _run_fzf_for_selection(files, "Files> ")

            # Compute new text based on selection (or keep original if none)
            if selected_path:
                preset, preset_cursor = _insert_file_path(
                    text, cursor, selected_path, "@"
                )
                tip = f"已插入文件，继续编辑或按{submit_keys_display}确认:"
            else:
                # No selection; keep original text and cursor
                preset = text
                preset_cursor = cursor
                tip = "未选择文件或已取消，继续编辑:"
            _clear_previous_prompt(text)
            continue
        elif isinstance(user_input, str) and user_input.startswith(
            FZF_REQUEST_ALL_SENTINEL_PREFIX
        ):
            # Handle fzf request (all-files mode, excluding .git) outside the prompt, then prefill new text.
            cursor, text = _parse_fzf_payload(
                user_input, FZF_REQUEST_ALL_SENTINEL_PREFIX
            )
            if cursor is None or text is None:
                # Malformed payload; just continue without change.
                preset = None
                tip = "FZF 预填失败，继续输入:"
                continue

            # Run fzf to get a file selection synchronously (outside prompt) with all files (exclude .git)
            files = _get_all_files(exclude_git=True)
            selected_path = _run_fzf_for_selection(files, "Files(all)> ")

            # Compute new text based on selection (or keep original if none)
            if selected_path:
                preset, preset_cursor = _insert_file_path(
                    text, cursor, selected_path, "#"
                )
                tip = f"已插入文件，继续编辑或按{submit_keys_display}确认:"
            else:
                # No selection; keep original text and cursor
                preset = text
                preset_cursor = cursor
                tip = "未选择文件或已取消，继续编辑:"
            _clear_previous_prompt(text)
            continue
        elif isinstance(user_input, str) and user_input.startswith(
            FZF_INSERT_SENTINEL_PREFIX
        ):
            # 从哨兵载荷中提取新文本，作为下次进入提示的预填内容
            preset = user_input[len(FZF_INSERT_SENTINEL_PREFIX) :]
            preset_cursor = len(preset)

            # 清除上一条输入行（多行安全），避免多清，保守仅按提示行估算
            try:
                rows_total = _calc_prompt_rows(preset)
                for _ in range(rows_total):
                    sys.stdout.write("\x1b[1A")
                    sys.stdout.write("\x1b[2K\r")
                sys.stdout.flush()
            except Exception:
                pass
            tip = f"已插入文件，继续编辑或按{submit_keys_display}确认:"
            continue
        else:
            if user_input == CTRL_C_SENTINEL:
                # Ctrl+C pressed, allow exit and return empty string
                return ""
            elif not user_input:
                # Empty submission, require user to input something
                continue
            else:
                return user_input
