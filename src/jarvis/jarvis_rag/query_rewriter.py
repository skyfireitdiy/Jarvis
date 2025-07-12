from .llm_interface import LLMInterface


class QueryRewriter:
    """
    Uses an LLM to rewrite a user's query into a more precise and
    search-friendly format for technical knowledge bases.
    """

    def __init__(self, llm: LLMInterface):
        """
        Initializes the QueryRewriter.

        Args:
            llm: An instance of a class implementing LLMInterface.
        """
        self.llm = llm
        self.rewrite_prompt_template = self._create_prompt_template()

    def _create_prompt_template(self) -> str:
        """Creates the prompt template for the query rewriting task."""
        return """
你是一个精通检索的AI助手。你的任务是将以下这个可能比较口语化或模糊的用户问题，改写成一个更具体、更专业的搜索查询，以便在技术知识库中找到最相关的文档。

请遵循以下原则：
1.  **保留核心意图**：确保改写后的查询与原问题的核心意图一致。
2.  **补充关键词**：根据问题，适当补充可能出现在相关文档中的技术术语或关键词。
3.  **结构化**：使查询更像一个搜索关键词或一个清晰的问题描述，而不是一段对话。
4.  **直接输出**：请直接输出改写后的查询文本，不要包含任何额外的解释、介绍或前缀（例如，不要说“这是改写后的查询：”）。

原始问题:
---
{query}
---

改写后的查询:
"""

    def rewrite(self, query: str) -> str:
        """
        Rewrites the user query using the LLM.

        Args:
            query: The original user query.

        Returns:
            The rewritten, search-optimized query.
        """
        prompt = self.rewrite_prompt_template.format(query=query)
        print(f"✍️  正在将原始查询重写为搜索优化查询...")
        rewritten_query = self.llm.generate(prompt)
        print(f"✅ 重写后的查询: '{rewritten_query}'")
        return rewritten_query
