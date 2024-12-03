# -*- coding: utf-8 -*-
"""
UserInteractionHandler: 抽象用户交互（多行输入与确认）逻辑，便于将来替换为 TUI/WebUI。

阶段一（最小变更）：
- 仅提供封装，不直接修改 Agent 的现有调用
- 后续步骤在 Agent 中以旁路方式接入，保持向后兼容
"""

from typing import Callable


class UserInteractionHandler:
    def __init__(
        self,
        multiline_inputer: Callable[..., str],
        confirm_func: Callable[[str, bool], bool],
    ) -> None:
        """
        参数:
          - multiline_inputer: 提供多行输入的函数，优先支持 (tip, print_on_empty=bool)，兼容仅接受 (tip) 的实现
          - confirm_func: 用户确认函数 (tip: str, default: bool) -> bool
        """
        self._multiline_inputer = multiline_inputer
        self._confirm = confirm_func

    def multiline_input(self, tip: str, print_on_empty: bool) -> str:
        """
        多行输入封装：兼容两类签名
        1) func(tip, print_on_empty=True/False)
        2) func(tip)
        """
        try:
            return self._multiline_inputer(tip, print_on_empty=print_on_empty)
        except TypeError:
            return self._multiline_inputer(tip)

    def confirm(self, tip: str, default: bool = True) -> bool:
        """
        用户确认封装，直接委派
        """
        return self._confirm(tip, default)
