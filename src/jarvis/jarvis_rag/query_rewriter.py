from typing import List
from .llm_interface import LLMInterface


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
你是一个精通检索的AI助手。你的任务是将以下这个单一的用户问题，从不同角度改写成 3 个不同的、但语义上相关的搜索查询。这有助于在知识库中进行更全面的搜索。

请遵循以下原则：
1.  **多样性**：生成的查询应尝试使用不同的关键词和表述方式。
2.  **保留核心意图**：所有查询都必须围绕原始问题的核心意图。
3.  **简洁性**：每个查询都应该是独立的、可以直接用于搜索的短语或问题。
4.  **格式要求**：请直接输出 3 个查询，每个查询占一行，用换行符分隔。不要添加任何编号、前缀或解释。

原始问题:
---
{query}
---

3个改写后的查询 (每行一个):
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
        print(f"✍️  正在将原始查询重写为多个搜索查询...")

        response_text = self.llm.generate(prompt)
        rewritten_queries = [
            line.strip() for line in response_text.strip().split("\n") if line.strip()
        ]

        # 同时包含原始查询以保证鲁棒性
        if query not in rewritten_queries:
            rewritten_queries.insert(0, query)

        print(f"✅ 生成了 {len(rewritten_queries)} 个查询变体。")
        return rewritten_queries
