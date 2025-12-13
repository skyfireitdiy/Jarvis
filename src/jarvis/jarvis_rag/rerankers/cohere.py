"""
Cohere 重排模型实现。
"""

from typing import List
from typing import Optional

from .base import OnlineReranker


class CohereReranker(OnlineReranker):
    """
    Cohere 重排模型的实现。

    使用 Cohere 的 rerank API。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "rerank-english-v3.0",
        **kwargs,
    ):
        """
        初始化 Cohere 重排模型。

        参数:
            api_key: Cohere API密钥。如果为None，将从COHERE_API_KEY环境变量读取。
            model_name: 要使用的模型名称（如 'rerank-english-v3.0'）。
            **kwargs: 传递给父类的其他参数。
        """
        super().__init__(
            api_key=api_key,
            api_key_env="COHERE_API_KEY",
            model_name=model_name,
            **kwargs,
        )

    def _call_api(self, query: str, documents: List[str]) -> List[tuple[int, float]]:
        """
        调用 Cohere API 获取重排分数。
        """
        try:
            import cohere

            client = cohere.Client(api_key=self.api_key)

            response = client.rerank(
                model=self.model_name,
                query=query,
                documents=documents,
                top_n=len(documents),  # 获取所有文档的分数
            )

            # 返回 (索引, 分数) 元组列表，按分数降序排序
            results = [
                (result.index, result.relevance_score) for result in response.results
            ]
            results.sort(key=lambda x: x[1], reverse=True)

            return results
        except ImportError:
            raise ImportError(
                "使用 CohereReranker 需要安装 cohere 包: pip install cohere"
            )
        except Exception as e:
            raise RuntimeError(f"调用 Cohere API 时出错: {e}")
