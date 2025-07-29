from typing import List
from .llm_interface import LLMInterface
from jarvis.jarvis_utils.output import PrettyOutput, OutputType


class QueryRewriter:
    """
    使用LLM将用户的查询重写为多个不同的搜索查询，以提高检索召回率。
    """

    def __init__(self, llm: LLMInterface):
        """
        初始化QueryRewriter。

        参数:
            llm: 实现LLMInterface接口的类的实例。
        """
        self.llm = llm
        self.rewrite_prompt_template = self._create_prompt_template()

    def _create_prompt_template(self) -> str:
        """为多查询重写任务创建提示模板。"""
        return """
你是一个精通检索和语言的AI助手。你的任务是将以下这个单一的用户问题，改写为几个语义相关但表达方式不同的搜索查询，并提供英文翻译。这有助于在多语言知识库中进行更全面的搜索。

请遵循以下原则：
1.  **保留核心意图**: 所有查询都必须围绕原始问题的核心意图。
2.  **查询类型**:
    - **同义词/相关术语查询**: 使用原始语言，通过替换同义词或相关术语来生成1-2个新的查询。
    - **英文翻译查询**: 将原始问题翻译成一个简洁的英文搜索查询。
3.  **简洁性**: 每个查询都应该是独立的、可以直接用于搜索的短语或问题。
4.  **严格格式要求**: 你必须将所有重写后的查询放置在 `<REWRITE>` 和 `</REWRITE>` 标签之间。每个查询占一行。不要在标签内外添加任何编号、前缀或解释。

示例输出格式:
<REWRITE>
使用不同表述的中文查询
另一个中文查询
English version of the query
</REWRITE>

原始问题:
---
{query}
---

请将改写后的查询包裹在 `<REWRITE>` 标签内:
"""

    def rewrite(self, query: str) -> List[str]:
        """
        使用LLM将用户查询重写为多个查询。

        参数:
            query: 原始用户查询。

        返回:
            一个经过重写、搜索优化的查询列表。
        """
        prompt = self.rewrite_prompt_template.format(query=query)
        PrettyOutput.print(
            "正在将原始查询重写为多个搜索查询...", output_type=OutputType.INFO, timestamp=False
        )

        import re

        max_retries = 3
        attempts = 0
        rewritten_queries = []
        response_text = ""

        while attempts < max_retries:
            attempts += 1
            response_text = self.llm.generate(prompt)
            match = re.search(r"<REWRITE>(.*?)</REWRITE>", response_text, re.DOTALL)

            if match:
                content = match.group(1).strip()
                rewritten_queries = [
                    line.strip() for line in content.split("\n") if line.strip()
                ]
                PrettyOutput.print(
                    f"成功从LLM响应中提取到内容 (尝试 {attempts}/{max_retries})。",
                    output_type=OutputType.SUCCESS,
                    timestamp=False,
                )
                break  # 提取成功，退出循环
            else:
                PrettyOutput.print(
                    f"未能从LLM响应中提取内容。正在重试... ({attempts}/{max_retries})",
                    output_type=OutputType.WARNING,
                    timestamp=False,
                )

        # 如果所有重试都失败，则跳过重写步骤
        if not rewritten_queries:
            PrettyOutput.print(
                "所有重试均失败。跳过查询重写，将仅使用原始查询。",
                output_type=OutputType.ERROR,
                timestamp=False,
            )

        # 同时包含原始查询以保证鲁棒性
        if query not in rewritten_queries:
            rewritten_queries.insert(0, query)

        PrettyOutput.print(
            f"生成了 {len(rewritten_queries)} 个查询变体。",
            output_type=OutputType.SUCCESS,
            timestamp=False,
        )
        return rewritten_queries
