# -*- coding: utf-8 -*-
"""需求澄清模块

提供需求模糊度检测与澄清功能。
基于启发式规则判断用户需求是否含糊，并在交互模式下主动向用户澄清。
"""

import re
from typing import List, Tuple

# 模糊动词/表述模式（中文）
_AMBIGUOUS_PATTERNS_ZH = [
    r"看看",
    r"优化一下",
    r"优化优化",
    r"处理一下",
    r"弄一下",
    r"改改",
    r"改一下",
    r"改好看",
    r"提升一下",
    r"想想办法",
    r"写个脚本",
    r"写个爬虫",
    r"写个自动化测试",
    r"生成一份.*文档",
    r"部署一下",
    r"你懂的",
    r"随便",
    r"算了",
    r"先不管",
    r"那个",
    r"这个",
    r"它",
    r"那东西",
    r"那个东西",
    r"这个方案",
    r"怎么样",
]

# 模糊动词/表述模式（英文）
_AMBIGUOUS_PATTERNS_EN = [
    r"check this out",
    r"improve the error handling",
    r"never mind",
    r"write a script",
    r"process the data",
    r"optimize",
    r"fix the bug in that function",
]

# 具体性信号：文件路径、函数名、类名、变量名等
_SPECIFIC_SIGNALS = [
    # 文件路径
    r"[\w./\\-]+\.(py|js|ts|go|rs|c|cpp|h|java|json|yaml|yml|toml|md|txt|vue|css|html)\b",
    # 函数/类名（驼峰或下划线命名）
    r"\b[A-Z][a-zA-Z0-9_]*\b",  # 类名（大写开头）
    r"\b[a-z][a-zA-Z0-9_]*\(\)",  # 函数调用
    r"\b[a-z][a-zA-Z0-9_]*\b",  # 变量/函数名
    # 具体数值
    r"\b\d+\b",
    # 明确的操作动词 + 具体对象
    r"修改|添加|删除|重构|修复|实现|创建|生成|更新|增加|移除|替换|调整",
    r"add|remove|delete|fix|refactor|implement|create|update|modify|change",
    # 明确的范围词
    r"在.*中|给.*添加|把.*改成|将.*改为|从.*改成",
    r"in .*|for .*|to .*",
]

# 需要澄清的提示词
_CLARIFICATION_PROMPT = (
    "你的需求描述似乎有些含糊，请补充以下信息以便更准确地完成任务：\n"
    "1. 具体要操作的文件或对象是什么？\n"
    "2. 希望达成什么具体结果？\n"
    "3. 有没有具体的约束或偏好？\n"
    "（如果无需澄清，直接输入'继续'即可）"
)


def detect_ambiguous_requirement(user_input: str) -> Tuple[bool, List[str]]:
    """检测用户需求是否模糊

    使用启发式规则判断用户需求是否含糊不清。

    参数:
        user_input: 用户输入的需求描述

    返回:
        Tuple[bool, List[str]]: (是否模糊, 检测到的模糊特征列表)
    """
    if not user_input or not user_input.strip():
        return True, ["空输入"]

    text = user_input.strip()
    reasons: List[str] = []

    # 1. 文本过短（< 15 字符且不含具体信号）
    if len(text) < 15:
        if not _has_specific_signal(text):
            reasons.append(f"文本过短（{len(text)} 字符）且缺少具体对象")

    # 2. 检测模糊表述
    for pattern in _AMBIGUOUS_PATTERNS_ZH:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append(f"包含模糊表述「{pattern}」")
            break  # 每个模糊模式只记录一次

    for pattern in _AMBIGUOUS_PATTERNS_EN:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append(f"包含模糊表述「{pattern}」")
            break

    # 3. 缺少具体信号（文件路径、函数名、明确操作等）
    if not _has_specific_signal(text):
        reasons.append("缺少具体对象或明确操作")

    # 4. 纯模糊代词（如"那个东西"、"这个"）
    if re.match(
        r"^[\s\S]*(那个|这个|它|那东西|那个东西)[\s\S]*$", text
    ) and not _has_specific_signal(text):
        reasons.append("使用模糊代词且无具体对象")

    return len(reasons) > 0, reasons


def _has_specific_signal(text: str) -> bool:
    """检查文本中是否包含具体性信号（文件路径、函数名、明确操作等）"""
    for pattern in _SPECIFIC_SIGNALS:
        if re.search(pattern, text):
            return True
    return False


def build_clarification_prompt() -> str:
    """构建澄清提示词"""
    return _CLARIFICATION_PROMPT
