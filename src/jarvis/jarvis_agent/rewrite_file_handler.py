# -*- coding: utf-8 -*-
import os
import re
from typing import Any, Dict, List, Tuple

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot


class RewriteFileHandler(OutputHandler):
    """
    处理整文件重写指令的输出处理器。

    指令格式：
    <REWRITE file=文件路径>
    新的文件完整内容
    </REWRITE>

    等价支持以下写法：
    <REWRITE_FILE file=文件路径>
    新的文件完整内容
    </REWRITE_FILE>

    说明：
    - 该处理器用于完全重写文件内容，适用于新增文件或大范围改写
    - 内部直接执行写入，提供失败回滚能力
    - 支持同一响应中包含多个 REWRITE/REWRITE_FILE 块
    """

    def __init__(self) -> None:
        # 允许 file 参数为单引号、双引号或无引号
        # 兼容两种标签名称：<REWRITE ...> 和 <REWRITE_FILE ...>
        self.rewrite_pattern = re.compile(
            ot("REWRITE file=(?:'([^']+)'|\"([^\"]+)\"|([^>]+))")
            + r"\s*"
            + r"(.*?)"
            + r"\s*"
            + r"^"
            + ct("REWRITE"),
            re.DOTALL | re.MULTILINE,
        )
        # 兼容别名格式：<REWRITE_FILE ...> ... </REWRITE_FILE>
        self.rewrite_pattern_file = re.compile(
            ot("REWRITE_FILE file=(?:'([^']+)'|\"([^\"]+)\"|([^>]+))")
            + r"\s*"
            + r"(.*?)"
            + r"\s*"
            + r"^"
            + ct("REWRITE_FILE"),
            re.DOTALL | re.MULTILINE,
        )

    def name(self) -> str:
        """获取处理器名称，用于操作列表展示"""
        return "REWRITE_FILE"

    def prompt(self) -> str:
        """返回用户提示，描述使用方法与格式"""
        return f"""文件重写指令格式：
{ot("REWRITE file=文件路径")}
新的文件完整内容
{ct("REWRITE")}

等价支持以下写法：
{ot("REWRITE_FILE file=文件路径")}
新的文件完整内容
{ct("REWRITE_FILE")}

注意：
- {ot("REWRITE")}、{ct("REWRITE")} 或 {ot("REWRITE_FILE")}、{ct("REWRITE_FILE")} 必须出现在行首，否则不生效（会被忽略）
- 整文件重写会完全替换文件内容，如需局部修改请使用 PATCH 操作
- 该操作由处理器直接执行，具备失败回滚能力"""

    def can_handle(self, response: str) -> bool:
        """判断响应中是否包含 REWRITE/REWRITE_FILE 指令"""
        return bool(self.rewrite_pattern.search(response) or self.rewrite_pattern_file.search(response))

    def handle(self, response: str, agent: Any) -> Tuple[bool, str]:
        """解析并执行整文件重写指令"""
        rewrites = self._parse_rewrites(response)
        if not rewrites:
            return False, "未找到有效的文件重写指令"

        # 记录 REWRITE_FILE 操作调用统计
        try:
            from jarvis.jarvis_stats.stats import StatsManager

            StatsManager.increment("rewrite_file_handler", group="tool")
        except Exception:
            # 统计失败不影响主流程
            pass

        results: List[str] = []
        overall_success = True

        for file_path, content in rewrites:
            abs_path = os.path.abspath(file_path)
            original_content = None
            processed = False
            try:
                file_exists = os.path.exists(abs_path)
                if file_exists:
                    with open(abs_path, "r", encoding="utf-8") as rf:
                        original_content = rf.read()
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w", encoding="utf-8") as wf:
                    wf.write(content)
                processed = True
                results.append(f"✅ 文件 {abs_path} 重写成功")
                # 记录成功处理的文件（使用绝对路径）
                if agent:
                    files = agent.get_user_data("files")
                    if files:
                        if abs_path not in files:
                            files.append(abs_path)
                    else:
                        files = [abs_path]
                    agent.set_user_data("files", files)
            except Exception as e:
                overall_success = False
                # 回滚已修改内容
                try:
                    if processed:
                        if original_content is None:
                            if os.path.exists(abs_path):
                                os.remove(abs_path)
                        else:
                            with open(abs_path, "w", encoding="utf-8") as wf:
                                wf.write(original_content)
                except Exception:
                    pass
                PrettyOutput.print(f"文件重写失败: {str(e)}", OutputType.ERROR)
                results.append(f"❌ 文件 {abs_path} 重写失败: {str(e)}")

        summary = "\n".join(results)
        # 按现有 EditFileHandler 约定，始终返回 (False, summary) 以继续主循环
        return False, summary

    def _parse_rewrites(self, response: str) -> List[Tuple[str, str]]:
        """
        解析响应中的 REWRITE/REWRITE_FILE 指令块。
        返回列表 [(file_path, content), ...]，按在响应中的出现顺序排序
        """
        items: List[Tuple[str, str]] = []
        matches: List[Tuple[int, Any]] = []

        # 收集两种写法的匹配结果
        for m in self.rewrite_pattern.finditer(response):
            matches.append((m.start(), m))
        for m in self.rewrite_pattern_file.finditer(response):
            matches.append((m.start(), m))

        # 按出现顺序排序
        matches.sort(key=lambda x: x[0])

        for _, m in matches:
            file_path = m.group(1) or m.group(2) or m.group(3) or ""
            file_path = file_path.strip()
            content = m.group(4)
            if file_path:
                items.append((file_path, content))
        return items