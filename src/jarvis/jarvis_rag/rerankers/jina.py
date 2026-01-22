"""
Jina 重排模型实现。
"""

from typing import List
from typing import Optional

from .base import OnlineReranker


class JinaReranker(OnlineReranker):
    """
    Jina 重排模型的实现。

    使用 Jina 的 rerank API。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "jina-reranker-v1-base-en",
        base_url: str = "https://api.jina.ai/v1/rerank",
        **kwargs,
    ):
        """
        初始化 Jina 重排模型。

        参数:
            api_key: Jina API密钥。如果为None，将从JINA_API_KEY环境变量读取。
            model_name: 要使用的模型名称。
            base_url: API的基础URL。
            **kwargs: 传递给父类的其他参数。
        """
        super().__init__(
            api_key=api_key,
            api_key_env="JINA_API_KEY",
            base_url=base_url,
            model_name=model_name,
            **kwargs,
        )

    def _call_api(self, query: str, documents: List[str]) -> List[tuple[int, float]]:
        """
        调用 Jina API 获取重排分数。
        """
        try:
            import requests

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            payload = {
                "model": self.model_name,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            }

            response = requests.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()

            # Jina API 返回格式: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
            results = [
                (item["index"], item["relevance_score"])
                for item in data.get("results", [])
            ]
            results.sort(key=lambda x: x[1], reverse=True)

            return results
        except ImportError:
            raise ImportError(
                "使用 JinaReranker 需要安装 requests 包: pip install requests"
            )
        except Exception as e:
            raise RuntimeError(f"调用 Jina API 时出错: {e}")
